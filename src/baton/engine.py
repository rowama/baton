"""The Director API (§13.1), shared by the CLI and (later) the MCP server.

Only this module sequences step events: ``packet.py`` builds packets and
``intake.py`` evaluates results and gates, and the functions here turn their
answers into transitions, one event each (§8.1).

The module-level functions are the core of a step's life over one run
context: ``start`` → ``begin_attempt`` (packet built, attempt dispatched and
running) → the worker writes ``result/`` → ``submit`` (intake and gates) →
``decide`` for owner decisions. ``Api`` wraps them for a whole project:
vendored recipes, profiles and adapters, leases, records and checkpoint
commits, resume and check.

Failure handling: a rejected result, a failed blocking gate, a ``failed``
worker or a rejected human gate sends the step back to ``ready`` while
attempts remain (the next packet carries the reasons as ``prior_feedback``),
and to ``escalated`` once ``max_attempts`` is used. A ``blocked`` result and a
gate that cannot be configured escalate at once.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from .intake import read_result, run_script_gate
from .models import EVENTS_FORMATS, Group, HumanGate, Plan, SchemaGate, ScriptGate, Step, WorkerProfile
from .packet import (
    PROTOCOL,
    BuiltPacket,
    EngineError,
    HandoffError,  # noqa: F401 - re-exported for callers
    RunContext,
    build_packet,
    gate_included,
    node_for,
    remove_tree,
)
from .recipe import LoadedRecipe, build_plan, load_recipe
from .redact import redact_text
from .state import SATISFIES_DEPS, IllegalTransition
from .store import Store, canonical_json
from .supervisor import ChildResult

__all__ = [
    "Api", "EngineError", "HandoffError", "IntegrityError", "Outcome", "RunContext",
    "abandon_run", "begin_attempt", "decide", "escalate_no_worker", "finish_child", "open_run", "pending_decisions", "plan",
    "refresh", "start", "submit",
]


def plan(recipe: str | Path, level: str | None = None) -> Plan:
    """Per-level step and gate table for a recipe directory. Raises ``RecipeError``."""
    return build_plan(load_recipe(recipe), level=level)


@dataclass
class Outcome:
    """What happened to a step after ``submit`` or ``decide``."""

    step_path: str
    attempt: int
    outcome: str  # passed | needs_human | retry | escalated
    reasons: list[str] = field(default_factory=list)
    ready: list[str] = field(default_factory=list)  # steps that became ready as a result
    run_completed: bool = False


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def start(
    store: Store,
    recipe: LoadedRecipe,
    inputs: dict[str, Any],
    *,
    title: str | None = None,
    run_id: str | None = None,
    project: dict[str, Any] | None = None,
    actor: str = "director",
    work_item: dict[str, Any] | None = None,
) -> RunContext:
    """Validate run inputs, open a run pinned to this recipe, and ready its first steps.

    ``work_item`` adds the project-level facts of ``run_started`` (§8.9):
    ``kind``, ``slug``, ``branch``.
    """
    if not isinstance(inputs, dict):
        raise EngineError("run.inputs_invalid", "run inputs must be a JSON object")
    if recipe.recipe.run_inputs is not None:
        schema = recipe.schemas[recipe.recipe.run_inputs.schema_]
        v = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        errors = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(inputs)]
        if errors:
            raise EngineError("run.inputs_invalid", "run inputs do not match the recipe's schema: " + "; ".join(errors))
    blob = canonical_json(inputs).encode("utf-8")
    data = {
        "title": title if title is not None else inputs.get("title"),
        "recipe": recipe.recipe.ref,
        "recipe_sha256": recipe.sha256,
        "formats": {"events": EVENTS_FORMATS[-1], "packet": PROTOCOL, "recipe": recipe.recipe.format},
        "capabilities_vocab": recipe.recipe.capabilities_vocab,
        "max_attempts": recipe.recipe.defaults.max_attempts,
        "inputs_sha256": hashlib.sha256(blob).hexdigest(),
        **(work_item or {}),
    }
    log = store.start_run(data, actor=actor, run_id=run_id)
    log.cas.put(blob)  # the run directory exists only once the run has started
    ctx = RunContext(store, log.run_id, recipe, project or {})
    refresh(ctx)
    return ctx


def open_run(store: Store, run_id: str, recipe: LoadedRecipe, project: dict[str, Any] | None = None) -> RunContext:
    """A context for an existing run. The recipe must be the exact package the run is pinned to."""
    ctx = RunContext(store, run_id, recipe, project or {})
    started = ctx.record().started
    if started.get("recipe") != recipe.recipe.ref or started.get("recipe_sha256") != recipe.sha256:
        raise EngineError(
            "run.recipe_mismatch",
            f"run {run_id} is pinned to {started.get('recipe')} ({started.get('recipe_sha256')}); "
            f"got {recipe.recipe.ref} ({recipe.sha256})",
        )
    return ctx


def refresh(ctx: RunContext) -> list[str]:
    """Ready every top-level step whose dependencies are satisfied; complete the run when all are.

    Steps with ``applies_to`` wait until a complexity level is set (§5.5);
    groups wait for the groups layer.
    """
    log = ctx.log
    rs = log.state()
    if rs.state != "active":
        return []
    level = ctx.record().level()
    readied = []
    for node in ctx.recipe.recipe.steps:
        if isinstance(node, Group) or rs.step(node.id).state != "blocked_on_deps":
            continue
        if node.applies_to is not None and (level is None or level not in node.applies_to):
            continue
        if all(rs.step(d).state in SATISFIES_DEPS for d in node.depends_on):
            log.append("step_ready", step_path=node.id)
            readied.append(node.id)
    rs = log.state()
    if all(rs.step(n.id).state in SATISFIES_DEPS for n in ctx.recipe.recipe.steps):
        log.append("run_completed")
    return readied


def _completed(ctx: RunContext) -> bool:
    return ctx.log.state().state == "completed"


# ---------------------------------------------------------------------------
# Attempts
# ---------------------------------------------------------------------------


def begin_attempt(
    ctx: RunContext,
    step_path: str,
    profile_name: str,
    profile: WorkerProfile,
    *,
    deadline: str | None = None,
    actor: str = "director",
    dispatch_id: str | None = None,
    adapter: str | None = None,
    guidance: str | None = None,
    preflight: Callable[[BuiltPacket], list[str]] | None = None,
    dispatch_data: dict[str, Any] | None = None,
) -> BuiltPacket:
    """Build the packet for the step's next attempt and mark the attempt dispatched and running.

    ``preflight`` may refuse the built packet for this worker (e.g. inputs too
    large for an API model, §18 #1); the packet is then removed. Raises
    ``HandoffError`` or ``EngineError`` with nothing written.
    """
    built = build_packet(ctx, step_path, profile_name, profile, deadline=deadline, guidance=guidance)
    if preflight is not None:
        problems = preflight(built)
        if problems:
            remove_tree(built.dir.parent)
            raise EngineError("dispatch.worker_cannot_take_packet", f"{profile_name} cannot take {step_path}: " + "; ".join(problems))
    log, n = ctx.log, built.attempt
    selected: dict[str, Any] = {"profile": profile_name, "vendor": profile.vendor}  # recorded for independence (§8.4)
    if profile.model:
        selected["model"] = profile.model
    log.append("worker_selected", actor=actor, step_path=step_path, attempt=n, data=selected)
    pb = {"packet_sha256": built.sha256, "profile": profile_name, "worker_profile_sha256": built.manifest["worker_profile_sha256"]}
    if guidance:
        pb["guidance"] = guidance
    log.append("packet_built", step_path=step_path, attempt=n, data=pb)
    disp: dict[str, Any] = {"profile": profile_name, "packet_sha256": built.sha256}
    if dispatch_id:
        disp["dispatch_id"] = dispatch_id
    if adapter:
        disp["adapter"] = adapter
    disp.update(dispatch_data or {})
    log.append("dispatched", actor=actor, step_path=step_path, attempt=n, data=disp)
    log.append("step_running", step_path=step_path, attempt=n)
    return built


def _step(ctx: RunContext, step_path: str) -> Step:
    node = node_for(ctx.recipe, step_path)
    if not isinstance(node, Step):
        raise EngineError("engine.unknown_step", f"{step_path} is not a runnable step of {ctx.recipe.recipe.ref}")
    return node


def submit(ctx: RunContext, step_path: str, *, actor: str = "runtime") -> Outcome:
    """Run intake on the step's running attempt: read ``result/``, then run its gates in order."""
    step = _step(ctx, step_path)
    log = ctx.log
    current = log.state().step(step_path)
    if current.state != "running":
        raise EngineError("engine.not_running", f"{step_path} is {current.state}; only a running attempt can be submitted")
    n = current.attempt
    record = ctx.record()
    built = record.last("packet_built", step_path, n)
    if built is None:  # pragma: no cover - begin_attempt always records it
        raise EngineError("engine.no_packet", f"{step_path} attempt {n} has no recorded packet")
    adir = ctx.attempt_dir(step_path, n)
    sub = read_result(ctx, step, adir / "result", adir / "packet", built.data["packet_sha256"])

    log.append(
        "result_submitted",
        actor=actor,
        step_path=step_path,
        attempt=n,
        data={"result_sha256": sub.result_sha256, "status": sub.status, **sub.registered()},
    )
    log.append("verification_started", step_path=step_path, attempt=n)
    if sub.problems:
        log.append("result_rejected", step_path=step_path, attempt=n, data={"reasons": sub.problems})
        return _failed(ctx, step_path, n, sub.problems)
    if sub.status == "blocked":
        reasons = ["the worker needs answers from the owner"]
        log.append(
            "step_escalated",
            step_path=step_path,
            attempt=n,
            data={"reason": "blocked", "questions": sub.questions, "notes": sub.notes},
        )
        return Outcome(step_path, n, "escalated", reasons)
    if sub.status == "failed":
        reasons = [f"the worker reported failure: {sub.notes}" if sub.notes else "the worker reported failure"]
        log.append("result_rejected", step_path=step_path, attempt=n, data={"reasons": reasons, "worker_status": "failed"})
        return _failed(ctx, step_path, n, reasons)
    log.append(
        "gate_passed",
        step_path=step_path,
        attempt=n,
        data={"gate": "provenance", "type": "provenance", "implicit": True, "artifacts": sorted(sub.artifacts)},
    )
    return _run_gates(ctx, step, step_path, n, 0)


def _run_gates(ctx: RunContext, step: Step, step_path: str, n: int, start: int) -> Outcome:
    log = ctx.log
    level = ctx.record().level()
    for i, gate in enumerate(step.gates):
        if i < start or not gate_included(gate, level):
            continue
        base = {"gate": i, "type": gate.type, "advisory": gate.advisory}
        if isinstance(gate, SchemaGate):
            log.append("gate_passed", step_path=step_path, attempt=n, data=base)  # validated at intake
        elif isinstance(gate, ScriptGate):
            res = run_script_gate(ctx, gate, step_path)
            log.append(
                "gate_passed" if res.passed else "gate_failed",
                step_path=step_path,
                attempt=n,
                data={**base, **res.data, "reasons": res.reasons},
            )
            if res.passed or gate.advisory:
                continue
            if res.configuration_error:
                log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": "configuration", "reasons": res.reasons})
                return Outcome(step_path, n, "escalated", res.reasons)
            return _failed(ctx, step_path, n, res.reasons)
        elif isinstance(gate, HumanGate):
            log.append("human_gate_opened", step_path=step_path, attempt=n, data={**base, "prompt": gate.prompt, "ref": step_path})
            return Outcome(step_path, n, "needs_human", [gate.prompt])
        else:  # pragma: no cover - refused before the packet was built
            raise EngineError("engine.unsupported_gate", f"{gate.type} gates arrive with the reviews layer")
    submitted = ctx.record().last("result_submitted", step_path, n)
    registered = {k: submitted.data.get(k) for k in ("output_sha256", "artifacts")}
    log.append("step_passed", step_path=step_path, attempt=n, data=registered)
    ready = refresh(ctx)
    return Outcome(step_path, n, "passed", [], ready, _completed(ctx))


def _failed(ctx: RunContext, step_path: str, n: int, reasons: list[str]) -> Outcome:
    """Back to ``ready`` for another attempt, or ``escalated`` when the budget is used."""
    try:
        ctx.log.append("step_ready", step_path=step_path, data={"retry_of": n})
        return Outcome(step_path, n, "retry", reasons)
    except IllegalTransition as e:
        if e.code != "state.attempts_exhausted":
            raise
    ctx.log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": "attempts_exhausted", "reasons": reasons})
    return Outcome(step_path, n, "escalated", reasons)


FAILURE_LINE = re.compile(r"baton-worker: failure=(\w+) code=(\w+) message=(.*)")


def classify_exit(child: ChildResult) -> dict[str, Any]:
    """Failure class for a worker that exited without a result (§8.8; full rules arrive in Phase 7)."""
    tail = child.tail.decode("utf-8", errors="replace")
    m = None
    for m in FAILURE_LINE.finditer(tail):
        pass
    if m is not None:
        return {"class": m.group(1), "code": m.group(2), "message": redact_text(m.group(3).strip())}
    if child.exit_code == 127:
        return {"class": "platform", "code": "executable_not_found", "message": "the worker's command was not found (exit 127)"}
    last = [ln for ln in tail.splitlines() if ln.strip()][-1:] or [""]
    return {"class": "unknown", "code": f"exit_{child.exit_code}", "message": redact_text(last[0][:300])}


def finish_child(ctx: RunContext, step_path: str, n: int, child: ChildResult, *, actor: str = "runtime") -> Outcome:
    """Take in an attached worker's ending: intake when it wrote a result, else classify.

    Over the time limit: ``step_timed_out``, then retry or escalate like a failed
    gate. Exited without ``result.json``: ``attempt_orphaned``, classified, and
    escalated with its class (platform failures wait for a fix, §8.8).
    """
    log = ctx.log
    if child.timed_out:
        log.append("step_timed_out", step_path=step_path, attempt=n, data=child.as_dict())
        reason = f"the worker did not finish within {child.duration_s:.0f} s"
        log.append("failure_classified", step_path=step_path, attempt=n, data={"class": "subject", "code": "timeout", "message": reason})
        return _failed(ctx, step_path, n, [reason])
    if (ctx.attempt_dir(step_path, n) / "result" / "result.json").is_file():
        return submit(ctx, step_path, actor=actor)
    cls = classify_exit(child)
    log.append("attempt_orphaned", step_path=step_path, attempt=n, data=child.as_dict())
    log.append("failure_classified", step_path=step_path, attempt=n, data=cls)
    reasons = [f"{cls['class']} failure ({cls['code']}): {cls['message']}"]
    log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": cls["class"], "code": cls["code"], "reasons": reasons})
    return Outcome(step_path, n, "escalated", reasons)


def escalate_no_worker(ctx: RunContext, step_path: str, excluded: list[dict[str, Any]], *, actor: str = "runtime") -> Outcome:
    """A ready step with no eligible worker escalates (§8.4; §18 #2: never fails the run)."""
    reasons = [f"{e['profile']}: {'; '.join(e['reasons'])}" for e in excluded] or ["no worker profiles on this machine"]
    ctx.log.append("step_escalated", actor=actor, step_path=step_path, data={"reason": "no_eligible_worker", "reasons": reasons})
    return Outcome(step_path, ctx.log.state().step(step_path).attempt, "escalated", reasons)


# ---------------------------------------------------------------------------
# Owner decisions
# ---------------------------------------------------------------------------

GATE_DECISIONS = ("approve", "reject")
ESCALATION_DECISIONS = ("retry", "abandon")


def pending_decisions(ctx: RunContext) -> list[dict[str, Any]]:
    """Decisions owed by the owner, each with the ``ref`` to pass to ``decide``.

    ``gate``: a step awaiting a human gate (``approve`` | ``reject``).
    ``escalation``: an escalated step (``retry`` with a fresh attempt budget | ``abandon``).
    """
    out = []
    record = ctx.record()
    for path, st in sorted(ctx.log.state().steps.items()):
        if st.state == "awaiting_human":
            opened = record.last("human_gate_opened", path, st.attempt)
            out.append(
                {
                    "ref": path, "step_path": path, "attempt": st.attempt, "kind": "gate",
                    "prompt": opened.data["prompt"] if opened else "", "options": list(GATE_DECISIONS),
                }
            )
        elif st.state == "escalated":
            esc = record.last("step_escalated", path)
            d = esc.data if esc else {}
            out.append(
                {
                    "ref": path, "step_path": path, "attempt": st.attempt, "kind": "escalation",
                    "reason": d.get("reason"), "reasons": d.get("reasons") or [], "questions": d.get("questions") or [],
                    "options": list(ESCALATION_DECISIONS),
                }
            )
    return out


def decide(
    ctx: RunContext, ref: str, decision: str, note: str = "", *, actor: str = "human", recorded_by: str | None = None
) -> Outcome:
    """Record the owner's decision, verbatim, then continue the step.

    ``ref`` is the step path of a step awaiting a human gate or escalated.
    Gate: ``approve`` passes the gate and runs any later gates; ``reject``
    fails it, and the note becomes the next attempt's feedback. Escalation:
    ``retry`` readies the step with a fresh attempt budget (the note is the
    owner's answer, carried as the next attempt's feedback); ``abandon``
    abandons the step.
    """
    log = ctx.log
    current = log.state().step(ref)
    extra = {"recorded_by": recorded_by} if recorded_by else {}
    if current.state == "escalated":
        return _decide_escalation(ctx, ref, decision, note, actor, extra)
    if decision not in GATE_DECISIONS:
        raise EngineError("decide.bad_decision", f"decision must be one of {GATE_DECISIONS}, got {decision!r}")
    if current.state != "awaiting_human":
        raise EngineError("decide.nothing_pending", f"{ref} has no open owner decision (it is {current.state})")
    step = _step(ctx, ref)
    n = current.attempt
    opened = ctx.record().last("human_gate_opened", ref, n)
    gate_index = opened.data["gate"]
    log.append(
        "human_decision",
        actor=actor,
        step_path=ref,
        attempt=n,
        data={"ref": ref, "kind": "gate", "gate": gate_index, "decision": decision, "note": note, **extra},
    )
    base = {"gate": gate_index, "type": "human", "advisory": step.gates[gate_index].advisory}
    if decision == "approve":
        log.append("gate_passed", step_path=ref, attempt=n, data=base)
        return _run_gates(ctx, step, ref, n, gate_index + 1)
    reasons = [f"the owner did not approve: {note}" if note else "the owner did not approve"]
    log.append("gate_failed", step_path=ref, attempt=n, data={**base, "reasons": reasons})
    if step.gates[gate_index].advisory:
        return _run_gates(ctx, step, ref, n, gate_index + 1)
    return _failed(ctx, ref, n, reasons)


def _decide_escalation(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any]) -> Outcome:
    if decision not in ESCALATION_DECISIONS:
        raise EngineError("decide.bad_decision", f"{ref} is escalated; decision must be one of {ESCALATION_DECISIONS}, got {decision!r}")
    log = ctx.log
    n = log.state().step(ref).attempt
    log.append(
        "human_decision",
        actor=actor,
        step_path=ref,
        attempt=n or None,  # escalated before any attempt (no eligible worker)
        data={"ref": ref, "kind": "escalation", "decision": decision, "note": note, **extra},
    )
    if decision == "retry":
        log.append("step_ready", step_path=ref, data={"after_decision": True})
        return Outcome(ref, n, "retry", [note] if note else [])
    log.append("step_abandoned", step_path=ref, data={"note": note})
    return Outcome(ref, n, "abandoned", [note] if note else [])


def abandon_run(ctx: RunContext, reason: str, *, actor: str = "director") -> None:
    """End the run without completing it (§13.1 ``abandon``)."""
    if not reason.strip():
        raise EngineError("abandon.reason_required", "abandoning a run needs a reason")
    ctx.log.append("run_abandoned", actor=actor, data={"reason": reason})


# ---------------------------------------------------------------------------
# The Director API over a project (§13.1): what the CLI and MCP server call
# ---------------------------------------------------------------------------

#: Events after which the run's record is committed (§10.1). ``lease_released``
#: is included so a handoff travels through git.
CHECKPOINT_TRIGGERS = ("human_decision", "step_passed", "step_escalated", "run_completed", "run_abandoned", "lease_released")


class Api:
    """One Director's view of one project. Every method returns plain JSON-able data.

    Mutating calls hold the run's lease (``locks.py``), then regenerate the
    run's records (``docs.py``) and, if a checkpoint event happened, commit
    them (``gitops.py``). ``needs_owner`` in a payload means the run now waits
    on an owner decision (CLI exit code 4).
    """

    def __init__(self, project: Any, director: Any):
        self.project = project
        self.director = director

    @classmethod
    def open(
        cls,
        root: str | Path | None = None,
        *,
        director_id: str | None = None,
        harness: str | None = None,
        home: str | Path | None = None,
        clock: Any = None,
    ) -> Api:
        from .locks import Director
        from .project import Project
        from .store import utc_now

        return cls(Project.open(root, home=home, clock=clock or utc_now), Director.current(director_id, harness))

    @staticmethod
    def init(root: str | Path) -> dict[str, Any]:
        from .project import init

        return init(root)

    def close(self) -> None:
        self.project.store.close()

    # -- helpers ------------------------------------------------------------

    def _leases(self, ctx: RunContext) -> Any:
        from .locks import Leases

        return Leases(ctx.log, self.director, self.project.branch(), self.project.config.leases.minutes)

    def _ctx(self, run_id: str) -> RunContext:
        return self.project.context(run_id)

    def _mutate(self, run_id: str, body: Any, *, allow_closed: bool = False) -> dict[str, Any]:
        """Hold the lease, run ``body(ctx) -> dict``, then write records and checkpoint."""
        ctx = self._ctx(run_id)
        if not allow_closed and ctx.log.state().state != "active":
            raise EngineError("run.closed", f"run {run_id} is {ctx.log.state().state}")
        leases = self._leases(ctx)
        leases.ensure()
        before = ctx.log.state().last_seq
        out = body(ctx) or {}
        self._after(ctx, leases, before, out)
        return out

    def _after(self, ctx: RunContext, leases: Any, before: int, out: dict[str, Any]) -> None:
        from . import docs

        if ctx.log.state().state in ("completed", "abandoned") and leases.current() is not None:
            leases.release(actor="runtime")
        docs.write_records(ctx)
        new = [e for e in ctx.log.events() if e.seq > before]
        cp = self._checkpoint(ctx, new)
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        pending = pending_decisions(ctx)
        out["pending_decisions"] = pending
        out["needs_owner"] = bool(pending)

    def _checkpoint(self, ctx: RunContext, new: list[Any]) -> Any:
        from . import docs, gitops

        triggers = [e for e in new if e.type in CHECKPOINT_TRIGGERS]
        if not triggers:
            return None
        if not self.project.config.checkpoints.commit:
            return gitops.Checkpoint(False, reason="checkpoint commits are off in project.yaml")
        pf = gitops.preflight(self.project.root, [ctx.run_dir])
        if isinstance(pf, str):
            return gitops.Checkpoint(False, reason=pf)
        top, rels = pf
        subject, body = _checkpoint_message(ctx, triggers, new)
        ctx.log.append("checkpoint_committed", data={"triggers": [e.type for e in triggers], "through_seq": triggers[-1].seq, "subject": subject})
        docs.write_records(ctx)
        if gitops.lfs_available(top):
            gitops.lfs_attributes(ctx.run_dir, int(self.project.config.lfs.threshold_mb * 1024 * 1024))
        try:
            sha = gitops.commit(top, rels, subject, body)
        except gitops.GitError as e:
            return gitops.Checkpoint(False, subject=subject, reason=str(e))
        return gitops.Checkpoint(sha is not None, sha, subject, None if sha else "nothing to commit")

    # -- recipes ------------------------------------------------------------

    def vendor(self, src: str | Path) -> dict[str, Any]:
        from .project import vendor

        return vendor(self.project, src)

    def recipes(self) -> dict[str, Any]:
        out = []
        for ref in self.project.vendored():
            entry = {"recipe": ref, "sha256": self.project.lock()["recipes"][ref]["sha256"]}
            try:
                loaded = self.project.recipe(ref)
                entry["description"] = loaded.recipe.description
                entry["ok"] = True
            except EngineError as e:
                entry.update(ok=False, error=str(e), code=e.code)
            out.append(entry)
        return {"recipes": out}

    def plan(self, recipe: str, level: str | None = None) -> Plan:
        """Plan for a vendored recipe ref, or a recipe directory."""
        if Path(recipe).is_dir():
            return plan(recipe, level)
        return build_plan(self.project.recipe(recipe), level=level)

    # -- runs ---------------------------------------------------------------

    def start(self, recipe: str, inputs: dict[str, Any], *, title: str | None = None, run_id: str | None = None) -> dict[str, Any]:
        loaded = self.project.recipe(recipe)
        title = title if title is not None else (inputs.get("title") if isinstance(inputs, dict) else None)
        work_item = {
            "kind": inputs.get("kind") if isinstance(inputs, dict) else None,
            "slug": self.project.render_slug(inputs if isinstance(inputs, dict) else {}, title),
            "branch": self.project.branch(),
        }
        ctx = start(
            self.project.store, loaded, inputs, title=title, run_id=run_id, project=self.project.variables(),
            actor=self.director.actor, work_item=work_item,
        )
        leases = self._leases(ctx)
        leases.ensure()
        out: dict[str, Any] = {"run_id": ctx.run_id}
        self._after(ctx, leases, 0, out)
        out.update(self.status(ctx.run_id))
        return out

    def status(self, run_id: str) -> dict[str, Any]:
        from . import gitops, locks

        ctx = self._ctx(run_id)
        events = ctx.log.events()
        rs = ctx.log.state()
        started = events[0].data
        steps = {}
        for node in ctx.recipe.recipe.steps:
            st = rs.step(node.id)
            steps[node.id] = {"state": st.state, "attempt": st.attempt}
        running = []
        for path, st in sorted(rs.steps.items()):
            if st.state in ("dispatched", "running"):
                disp = _last_data(events, "dispatched", path, st.attempt)
                adir = ctx.attempt_dir(path, st.attempt)
                running.append(
                    {
                        "step_path": path, "attempt": st.attempt,
                        "profile": disp.get("profile"), "adapter": disp.get("adapter"), "dispatch_id": disp.get("dispatch_id"),
                        "packet": str(adir / "packet"), "result": str(adir / "result"),
                    }
                )
        lease = locks.current(events)
        now = ctx.log.clock()
        lease_info = None
        if lease is not None:
            lease_info = {
                "director_id": lease.director_id, "harness": lease.harness, "host": lease.host, "branch": lease.branch,
                "expires_at": lease.expires_at, "expired": lease.expired(now),
                "yours": lease.held_by(self.director, self.project.branch()),
            }
        pending = pending_decisions(ctx)
        return {
            "run_id": run_id,
            "title": started.get("title"),
            "recipe": started.get("recipe"),
            "state": rs.state,
            "level": ctx.record().level(),
            "steps": steps,
            "ready": [p for p, s in steps.items() if s["state"] == "ready"],
            "running": running,
            "pending_decisions": pending,
            "needs_owner": bool(pending),
            "lease": lease_info,
            "last_checkpoint": gitops.last_checkpoint(self.project.root, run_id),
            "last_seq": rs.last_seq,
        }

    def _routing(self, ctx: RunContext, step_path: str) -> Any:
        from .routing import PreferencesError, eligible_workers, load_preferences

        node = node_for(ctx.recipe, step_path)
        if not isinstance(node, Step):
            raise EngineError("engine.unknown_step", f"{step_path} is not a runnable step of {ctx.recipe.recipe.ref}")
        try:
            prefs = load_preferences(self.project.baton)
        except PreferencesError as e:
            raise EngineError("configuration.preferences", str(e)) from e
        return eligible_workers(
            node, step_path, self.project.profiles(), ctx.recipe.vocab, events=ctx.log.events(), preferences=prefs
        )

    def eligible(self, run_id: str, step_path: str) -> dict[str, Any]:
        """Ordered eligible profiles with reasons, and every exclusion (§8.4).

        A ready step with none escalates (``no_eligible_worker``); the owner's
        ``decide <step> retry`` readies it again once a worker exists.
        """
        ctx = self._ctx(run_id)
        result = self._routing(ctx, step_path)
        out: dict[str, Any] = {"run_id": run_id, **result.as_dict()}
        if result.eligible or ctx.log.state().step(step_path).state != "ready":
            out["escalated"] = False
            return out

        def body(c: RunContext) -> dict[str, Any]:
            escalate_no_worker(c, step_path, result.excluded, actor=self.director.actor)
            return {"run_id": run_id, **result.as_dict(), "escalated": True}

        return self._mutate(run_id, body)

    def dispatch(self, run_id: str, step_path: str, worker: str, *, guidance: str | None = None) -> dict[str, Any]:
        """Build the packet and hand it to the worker's adapter.

        The worker must be in the step's eligible set (§8.4). Manual workers
        then ``submit``; process workers (API models) run attached here, and
        intake runs when they exit, all in this one call.
        """
        import secrets

        from . import adapters
        from .profiles import SetupError, build_env
        from .supervisor import run_child

        profiles = self.project.profiles()
        if worker not in profiles:
            raise EngineError("configuration.unknown_profile", f"no worker profile {worker!r} on this machine (known: {', '.join(sorted(profiles)) or 'none'})")
        profile = profiles[worker]
        adapter = adapters.get(profile.adapter)
        if profile.isolation != "none":
            raise EngineError("configuration.isolation_unsupported", f"{worker}: isolation {profile.isolation!r} is not supported by this runtime yet; use none")
        ctx0 = self._ctx(run_id)
        routing = self._routing(ctx0, step_path)
        if worker not in routing.names():
            why = "; ".join(routing.reasons_for(worker)) or "not eligible"
            raise EngineError("routing.ineligible", f"{worker} is not eligible for {step_path}: {why} (see `baton eligible {run_id} {step_path}`)")

        def body(ctx: RunContext) -> dict[str, Any]:
            dispatch_id = f"d_{secrets.token_hex(4)}"
            n_next = ctx.log.state().step(step_path).attempt + 1
            adir = ctx.attempt_dir(step_path, n_next)
            node = node_for(ctx.recipe, step_path)
            workspace = self.project.root if getattr(node, "workspace", "none") != "none" else None
            env = None
            try:
                adapter.check_profile(profile)
                if adapter.name != "manual":
                    env = build_env(
                        profile, home=self.project.home, packet_dir=adir / "packet", result_dir=adir / "result",
                        workspace=workspace, config_home_var=adapter.config_home_var, resolve=adapter.needs_executable,
                    )
            except SetupError as e:
                raise EngineError(e.code, str(e)) from e
            extra: dict[str, Any] = {"env": env.describe()} if env is not None else {}
            built = begin_attempt(
                ctx, step_path, worker, profile, actor=self.director.actor, dispatch_id=dispatch_id, adapter=adapter.name,
                guidance=guidance, preflight=lambda b: adapter.preflight(profile, b.dir), dispatch_data=extra,
            )
            out: dict[str, Any] = {
                "run_id": ctx.run_id, "step_path": step_path, "attempt": built.attempt, "dispatch_id": dispatch_id,
                "worker": worker, "adapter": adapter.name, "packet_sha256": built.sha256,
                "packet": str(built.dir), "result": str(built.result_dir),
                "handoff": adapter.handoff(profile, built.dir, built.result_dir),
            }
            argv = adapter.command(profile, built.dir, built.result_dir, workspace, getattr(node, "workspace", "none"))
            if argv is None or env is None:
                return out  # a person does the work; the Director submits
            log_path = self.project.home / "logs" / ctx.run_id / step_path / f"attempt-{built.attempt}.log"
            child = run_child(argv, env=env.env, cwd=workspace or built.dir.parent, log_path=log_path)
            outcome = finish_child(ctx, step_path, built.attempt, child, actor=f"worker:{worker}")
            out.update(_outcome_dict(outcome))
            out["worker_exit"] = {**child.as_dict(), "log": str(log_path)}
            return out

        return self._mutate(run_id, body)

    def doctor(self, profile: str | None = None, *, run_noop: bool = True) -> dict[str, Any]:
        from .doctor import doctor

        return doctor(self.project, profile, run_noop=run_noop)

    def retry(self, run_id: str, step_path: str, worker: str | None = None, guidance: str | None = None) -> dict[str, Any]:
        """A new attempt of a step whose previous attempt was not accepted. Guidance is additive only."""
        ctx = self._ctx(run_id)
        st = ctx.log.state().step(step_path)
        if st.state == "escalated":
            raise EngineError("retry.escalated", f"{step_path} is escalated; record the owner's decision first (decide {step_path} retry)")
        if st.state != "ready" or st.attempt == 0:
            raise EngineError("retry.not_retryable", f"{step_path} is {st.state} with {st.attempt} attempts; retry needs a ready step with a previous attempt")
        if worker is None:
            worker = _last_data(ctx.log.events(), "dispatched", step_path, st.attempt).get("profile")
        return self.dispatch(run_id, step_path, worker, guidance=guidance)

    def submit(self, run_id: str, step_path: str, result_dir: str | Path | None = None) -> dict[str, Any]:
        """Run intake on a running attempt. ``result_dir`` is copied into the attempt's ``result/`` first."""
        import shutil

        def body(ctx: RunContext) -> dict[str, Any]:
            st = ctx.log.state().step(step_path)
            if st.state != "running":
                raise EngineError("engine.not_running", f"{step_path} is {st.state}; only a running attempt can be submitted")
            target = ctx.attempt_dir(step_path, st.attempt) / "result"
            if result_dir is not None and Path(result_dir).resolve() != target.resolve():
                src = Path(result_dir)
                if not (src / "result.json").is_file():
                    raise EngineError("submit.no_result", f"{src} has no result.json")
                if (target / "result.json").exists():
                    raise EngineError("submit.result_exists", f"{target} already holds a result")
                shutil.copytree(src, target, dirs_exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            profile = _last_data(ctx.log.events(), "dispatched", step_path, st.attempt).get("profile")
            outcome = submit(ctx, step_path, actor=f"worker:{profile}" if profile else "worker")
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        return self._mutate(run_id, body)

    def decide(self, run_id: str, ref: str, decision: str, note: str = "") -> dict[str, Any]:
        """Record the owner's decision verbatim (gates and escalations)."""

        def body(ctx: RunContext) -> dict[str, Any]:
            outcome = decide(ctx, ref, decision, note, actor="human", recorded_by=self.director.actor)
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        return self._mutate(run_id, body)

    def abandon(self, run_id: str, reason: str) -> dict[str, Any]:
        def body(ctx: RunContext) -> dict[str, Any]:
            abandon_run(ctx, reason, actor=self.director.actor)
            return {"run_id": ctx.run_id, "state": "abandoned"}

        return self._mutate(run_id, body)

    # -- continuity ---------------------------------------------------------

    def resume(self, run_id: str) -> dict[str, Any]:
        """Verify, rebuild, reconcile and claim the lease (§10.3); returns status.

        Raises ``LeaseHeld`` (with the status attached) when another Director
        holds the lease.
        """
        from .check import run_integrity
        from .locks import LeaseHeld

        store = self.project.store
        store.run(run_id)
        problems = run_integrity(store, run_id)
        if problems:
            raise IntegrityError(run_id, problems)
        store.rebuild_run(run_id)
        ctx = self._ctx(run_id)
        # Reconcile in-flight attempts. Manual attempts wait for submit; git does
        # not keep empty directories, so recreate their result directories.
        reconciled = []
        rs = ctx.log.state()
        for path, st in sorted(rs.steps.items()):
            if st.state == "running":
                (ctx.attempt_dir(path, st.attempt) / "result" / "artifacts").mkdir(parents=True, exist_ok=True)
                reconciled.append({"step_path": path, "attempt": st.attempt, "action": "waiting_for_submit"})
        out: dict[str, Any] = {}
        if rs.state == "active":
            leases = self._leases(ctx)
            before = rs.last_seq
            try:
                leases.ensure()
            except LeaseHeld as e:
                e.status = {**self.status(run_id), "reconciled": reconciled}  # type: ignore[attr-defined]
                raise
            self._after(ctx, leases, before, out)
        out.update(self.status(run_id))
        out["reconciled"] = reconciled
        return out

    def lease(self, run_id: str, action: str, reason: str | None = None) -> dict[str, Any]:
        """``claim`` | ``release`` | ``take_over`` (with a reason; owner approval is the skill's rule)."""
        ctx = self._ctx(run_id)
        leases = self._leases(ctx)
        before = ctx.log.state().last_seq
        if action == "claim":
            leases.ensure()
        elif action == "take_over":
            leases.take_over(reason or "")
        elif action == "release":
            leases.release()
        else:
            raise EngineError("lease.bad_action", f"lease action must be claim, release or take_over, got {action!r}")
        out: dict[str, Any] = {"run_id": run_id, "action": action}
        self._after(ctx, leases, before, out)
        out["lease"] = self.status(run_id)["lease"]
        return out

    # -- records ------------------------------------------------------------

    def record(self, run_id: str, step_path: str) -> str:
        from . import docs

        ctx = self._ctx(run_id)
        if node_for(ctx.recipe, step_path) is None:
            raise EngineError("engine.unknown_step", f"{step_path} is not a step of {ctx.recipe.recipe.ref}")
        return docs.step_record(ctx, step_path)

    def summary(self, run_id: str) -> str:
        from . import docs

        return docs.summary(self._ctx(run_id))

    def trace(self, run_id: str, limit: int | None = 20) -> list[str]:
        from . import docs

        return docs.trace(self.project.store.run(run_id).events(), limit)

    def check(self) -> list[Any]:
        from .check import check

        return check(self.project.root)


class IntegrityError(EngineError):
    """A run's log or CAS failed verification; nothing was changed."""

    def __init__(self, run_id: str, issues: list[Any]):
        super().__init__("resume.integrity", f"run {run_id} failed verification: " + "; ".join(f"{i.where}: {i.message}" for i in issues))
        self.issues = issues


def _last_data(events: list[Any], etype: str, step_path: str, attempt: int) -> dict[str, Any]:
    for ev in reversed(events):
        if ev.type == etype and ev.step_path == step_path and ev.attempt == attempt:
            return ev.data
    return {}


def _outcome_dict(o: Outcome) -> dict[str, Any]:
    return {
        "step_path": o.step_path, "attempt": o.attempt, "outcome": o.outcome, "reasons": o.reasons,
        "ready": o.ready, "run_completed": o.run_completed,
    }


def _checkpoint_message(ctx: RunContext, triggers: list[Any], new: list[Any]) -> tuple[str, list[str]]:
    """``baton(<run_id>): <step_path> passed [attempt 1, <profile>]`` (§10.1), one phrase per trigger."""
    events = ctx.log.events()

    def profile(e: Any) -> str:
        return _last_data(events, "dispatched", e.step_path, e.attempt).get("profile") or "?"

    phrases: list[str] = []
    ended = any(e.type in ("run_completed", "run_abandoned") for e in triggers)
    for e in triggers:
        if e.type == "step_passed":
            phrases.append(f"{e.step_path} passed [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "step_escalated":
            phrases.append(f"{e.step_path} escalated ({e.data.get('reason')}) [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "human_decision":
            phrases.append(f"{e.step_path} decision {e.data.get('decision')}" + (f" [attempt {e.attempt}]" if e.attempt else ""))
        elif e.type == "run_completed":
            phrases.append("run completed")
        elif e.type == "run_abandoned":
            phrases.append("run abandoned")
        elif e.type == "lease_released" and not ended:
            phrases.append(f"lease released by {e.data.get('director_id')}")
    subject = f"baton({ctx.run_id}): " + "; ".join(phrases)
    body = [f"seq {e.seq} {e.type}" + (f" {e.step_path}" if e.step_path else "") + (f"#{e.attempt}" if e.attempt else "") for e in new]
    return subject, body
