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
import json
import socket
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from . import classify, groups, refs
from .intake import read_result, run_script_gate
from .models import EVENTS_FORMATS, FindingsGate, Group, HumanGate, Plan, SchemaGate, ScriptGate, Step, WorkerProfile
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
    view_of,
)
from .recipe import LoadedRecipe, build_plan, load_recipe
from .redact import redact_text
from .state import SATISFIES_DEPS, IllegalTransition
from .store import Store, canonical_json
from .supervisor import ChildResult

__all__ = [
    "Api", "EngineError", "HandoffError", "IntegrityError", "Outcome", "RunContext",
    "abandon_run", "begin_attempt", "decide", "escalate_no_worker", "finish_child", "open_run", "pending_decisions", "plan",
    "resolve_effort",
    "refresh", "revise", "start", "submit",
]


def plan(recipe: str | Path, level: str | None = None) -> Plan:
    """Per-level step and gate table for a recipe directory. Raises ``RecipeError``."""
    return build_plan(load_recipe(recipe), level=level)


@dataclass
class Outcome:
    """What happened to a step after ``submit`` or ``decide``."""

    step_path: str
    attempt: int
    outcome: str  # passed | needs_human | retry | escalated | abandoned | next_iteration | iteration_limit | revised
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
    """Move the run forward as far as the record allows; complete it when every top-level node is done.

    Readies every step (top level or inside a group's current iteration) whose
    dependencies are satisfied, including ``stale`` steps (re-run, §8.9);
    expands and re-expands groups; starts instances as ``concurrency`` allows;
    ends iterations judged unmet and starts the next one, or escalates at
    ``max_iterations`` (§8.5). Steps with ``applies_to`` wait until a
    complexity level is set (§5.5). One event at a time, each from a fresh view.
    """
    log = ctx.log
    if log.state().state != "active":
        return []
    readied: list[str] = []
    while _advance(ctx, view_of(ctx), ctx.recipe.recipe.steps, None, readied):
        pass
    view = view_of(ctx)
    if all(view.node_state(n, n.id, None) in SATISFIES_DEPS for n in ctx.recipe.recipe.steps):
        log.append("run_completed")
    return readied


def _advance(ctx: RunContext, view: groups.View, nodes: list[Any], frame: groups.Frame | None, readied: list[str]) -> bool:
    """Append the next event this scope calls for; ``True`` if one was appended."""
    for node in nodes:
        if node.applies_to is not None and (view.level is None or view.level not in node.applies_to):
            continue
        path = groups.child_path(frame, node.id)
        if not view.deps_met(node, frame):
            continue
        if isinstance(node, Step):
            state = view.rs.step(path).state
            if state in ("blocked_on_deps", "stale"):
                ctx.log.append("step_ready", step_path=path, data={"rerun": True} if state == "stale" else {})
                readied.append(path)
                return True
        elif _advance_group(ctx, view, node, path, frame, readied):
            return True
    return False


def _advance_group(ctx: RunContext, view: groups.View, group: Group, path: str, outer: groups.Frame | None, readied: list[str]) -> bool:
    log = ctx.log
    if view.needs_expansion(group, path, outer):
        data = view.build_expansion(group, path, outer)
        log.append("group_expanded", step_path=path, data=data)
        if data.get("changed"):
            # Same id, changed item: the instance's accepted work is stale and re-runs (§8.5).
            fresh = view_of(ctx)
            for inst in data["changed"]:
                f = fresh.frame(group, path, inst)
                for p in fresh.effective_paths(f) if f else []:
                    if fresh.rs.step(p).state in ("passed", "imported"):
                        log.append("step_stale", step_path=p, data={"cause": "item_changed", "instance": f"{path}/{inst}"})
        return True
    items = view.live_items(path)
    active = sum(1 for i in items if view.instance_state(group, path, i["id"]) in ("active", "escalated"))
    for item in items:
        ipath = f"{path}/{item['id']}"
        state = view.instance_state(group, path, item["id"])
        if state == "not_started":
            if active < group.concurrency:
                log.append("iteration_started", step_path=ipath, data={"iteration": 1, "from": group.steps[0].id, "budget_base": 0})
                return True
            continue
        if state in ("abandoned", "superseded", "escalated", "passed"):
            continue
        f = view.frame(group, path, item["id"])
        assert f is not None
        failed = view.judged_failed(f)
        if failed is not None:
            if view.limit_for(ipath, failed) is not None:
                continue
            cur, base = view.current_iteration(ipath) or (1, 0)
            reasons = (failed.data.get("condition") or {}).get("reasons") or []
            if group.max_iterations is not None and cur - base >= group.max_iterations:
                log.append(
                    "iteration_limit_reached", step_path=ipath,
                    data={"iteration": cur, "max_iterations": group.max_iterations, "judged": failed.step_path, "judged_seq": failed.seq, "reasons": reasons},
                )
            else:
                log.append(
                    "iteration_started", step_path=ipath,
                    data={"iteration": cur + 1, "from": group.repeat_from or group.steps[0].id, "budget_base": base, "after": failed.step_path},
                )
            return True
        if _advance(ctx, view, group.steps, f, readied):
            return True
    return False


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
    effort: str | None = None,
) -> BuiltPacket:
    """Build the packet for the step's next attempt and mark the attempt dispatched and running.

    ``preflight`` may refuse the built packet for this worker (e.g. inputs too
    large for an API model, §18 #1); the packet is then removed. Raises
    ``HandoffError`` or ``EngineError`` with nothing written.
    """
    built = build_packet(ctx, step_path, profile_name, profile, deadline=deadline, guidance=guidance, effort=effort)
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


def submit(
    ctx: RunContext, step_path: str, *, actor: str = "runtime", workspace_changes: list[str] | None = None,
    worker_exit: dict[str, Any] | None = None,
) -> Outcome:
    """Run intake on the step's running attempt: read ``result/``, then run its gates in order.

    ``workspace_changes`` (from the runtime's tree check on ``read`` / ``none``
    steps) fails the implicit ``workspace`` gate and escalates the step,
    whatever the result says: the tree is the owner's to inspect or revert.
    """
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
    if sub.status == "completed" and not sub.problems:
        loc = groups.locate(ctx.recipe, step_path)
        assert loc is not None
        sub.problems += view_of(ctx).foreach_id_problems(loc, sub.output)

    log.append(
        "result_submitted",
        actor=actor,
        step_path=step_path,
        attempt=n,
        data={"result_sha256": sub.result_sha256, "status": sub.status, **sub.registered(), **({"worker_exit": worker_exit} if worker_exit else {})},
    )
    log.append("verification_started", step_path=step_path, attempt=n)
    if workspace_changes:
        return _workspace_modified(ctx, step_path, n, workspace_changes)
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
            cls = None
            if not res.data.get("timed_out"):
                sha = res.data.get("output_sha256")
                cls = classify.classify_gate(res.data.get("exit_code"), ctx.log.cas.read(sha) if sha else b"")
            if cls is not None and cls["class"] != "subject":
                # The gate command could not run here: the platform's problem, not the step's (§8.8).
                log.append("failure_classified", step_path=step_path, attempt=n, data={**cls, "gate": i})
                reasons = [f"{cls['class']} failure ({cls['code']}) running gate {i}: {cls['message']}", *res.reasons]
                log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": cls["class"], "code": cls["code"], "reasons": reasons})
                return Outcome(step_path, n, "escalated", reasons)
            return _gate_failed(ctx, step_path, n, i, res.reasons)
        elif isinstance(gate, FindingsGate):
            passed, data = _findings_gate(ctx, gate, step_path, n)
            log.append("findings_recorded", step_path=step_path, attempt=n, data={"gate": i, **data["recorded"]})
            log.append("gate_passed" if passed else "gate_failed", step_path=step_path, attempt=n, data={**base, **data["gate"]})
            if passed or gate.advisory:
                continue
            return _gate_failed(ctx, step_path, n, i, data["gate"]["reasons"])
        elif isinstance(gate, HumanGate):
            log.append("human_gate_opened", step_path=step_path, attempt=n, data={**base, "prompt": gate.prompt, "ref": step_path})
            return Outcome(step_path, n, "needs_human", [gate.prompt])
        else:  # pragma: no cover - refused before the packet was built
            raise EngineError("engine.unsupported_gate", f"{gate.type} gates arrive with the reviews layer")
    data = _registered(ctx, step_path, n)
    loc = groups.locate(ctx.recipe, step_path)
    if loc is not None and groups.is_judge(loc):
        data["condition"] = {"gates_passed": True}
    log.append("step_passed", step_path=step_path, attempt=n, data=data)
    ready = refresh(ctx)
    return Outcome(step_path, n, "passed", [], ready, _completed(ctx))


def _registered(ctx: RunContext, step_path: str, n: int) -> dict[str, Any]:
    submitted = ctx.record().last("result_submitted", step_path, n)
    return {k: submitted.data.get(k) for k in ("output_sha256", "artifacts")}


def _findings_gate(ctx: RunContext, gate: FindingsGate, step_path: str, n: int) -> tuple[bool, dict[str, Any]]:
    """Evaluate a ``findings`` gate on the step's own ``baton:findings`` output (§9.1, §9.2).

    Every finding is open until dispositions exist (Phase 9). The gate fails
    when an open finding has a ``block_on`` severity. ``coverage.complete:
    false`` marks the result partial.
    """
    sha = _registered(ctx, step_path, n).get("output_sha256")
    output = json.loads(ctx.log.cas.read(sha)) if sha else {}
    findings = [f for f in output.get("findings") or [] if isinstance(f, dict)]
    coverage = output.get("coverage") or {}
    block = set(gate.block_on or [])
    blocking = [f for f in findings if f.get("severity") in block]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.get("severity", "?")] = counts.get(f.get("severity", "?"), 0) + 1
    partial = coverage.get("complete") is False
    reasons = [
        f"open {f.get('severity')} finding {f.get('id')}: {f.get('title')}" + (f" ({f['location']})" if f.get("location") else "")
        for f in blocking
    ]
    recorded = {"counts": counts, "open": [f.get("id") for f in findings], "blocking": [f.get("id") for f in blocking], "partial": partial}
    if coverage.get("notes"):
        recorded["coverage_notes"] = coverage["notes"]
    return not blocking, {"recorded": recorded, "gate": {"blocking": recorded["blocking"], "partial": partial, "reasons": reasons}}


def _gate_failed(ctx: RunContext, step_path: str, n: int, gate: int, reasons: list[str]) -> Outcome:
    """A declared blocking gate failed: retry the step, or, for an iteration's judge, end the iteration.

    A judge (a step named in its group's ``repeat_until``) did its work; its
    gate says the iteration's work is not done. Its result is kept and the
    next iteration starts (or the instance escalates at ``max_iterations``).
    """
    loc = groups.locate(ctx.recipe, step_path)
    if loc is None or not groups.is_judge(loc):
        return _failed(ctx, step_path, n, reasons)
    assert loc.frame is not None
    data = {**_registered(ctx, step_path, n), "condition": {"gates_passed": False, "gate": gate, "reasons": reasons}}
    ctx.log.append("step_passed", step_path=step_path, attempt=n, data=data)
    ready = refresh(ctx)
    ipath = loc.frame.instance_path
    limit = ctx.record().last("iteration_limit_reached", ipath)
    if limit is not None and limit.data.get("judged") == step_path and limit.data.get("judged_seq") == ctx.record().last("step_passed", step_path, n).seq:
        return Outcome(step_path, n, "iteration_limit", [f"{ipath} reached {limit.data['max_iterations']} iterations", *reasons], ready, _completed(ctx))
    return Outcome(step_path, n, "next_iteration", reasons, ready, _completed(ctx))


def _workspace_reasons(step_path: str, changes: list[str]) -> list[str]:
    shown = ", ".join(changes[:20]) + (f" and {len(changes) - 20} more" if len(changes) > 20 else "")
    return [f"{step_path} may not change the working tree, but it changed: {shown}"]


def _workspace_modified(ctx: RunContext, step_path: str, n: int, changes: list[str]) -> Outcome:
    """The implicit ``workspace`` gate failed: escalate (never reverted, never retried on a changed tree)."""
    reasons = _workspace_reasons(step_path, changes)
    ctx.log.append(
        "gate_failed", step_path=step_path, attempt=n,
        data={"gate": "workspace", "type": "workspace", "implicit": True, "changed": changes, "reasons": reasons},
    )
    ctx.log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": "workspace_modified", "changed": changes, "reasons": reasons})
    return Outcome(step_path, n, "escalated", reasons)


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


def classify_exit(child: ChildResult, signals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Failure class for a worker that exited without a result (§8.8; rules in ``classify.py``)."""
    return classify.classify_exit(child.exit_code, child.tail, signals)


def finish_child(
    ctx: RunContext,
    step_path: str,
    n: int,
    child: ChildResult,
    *,
    actor: str = "runtime",
    signals: list[dict[str, Any]] | None = None,
    workspace_changes: list[str] | None = None,
) -> Outcome:
    """Take in an attached worker's ending: intake when it wrote a result, else classify.

    Over the time limit: ``step_timed_out``, then retry or escalate like a failed
    gate. Exited without ``result.json``: ``attempt_orphaned``, classified, and
    escalated with its class (platform failures wait for a fix, §8.8).
    """
    log = ctx.log
    if child.timed_out:
        log.append("step_timed_out", step_path=step_path, attempt=n, data=child.as_dict())
        if workspace_changes:
            reasons = _workspace_reasons(step_path, workspace_changes)
            log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": "workspace_modified", "changed": workspace_changes, "reasons": reasons})
            return Outcome(step_path, n, "escalated", reasons)
        cls = classify.timed_out(child.duration_s)
        log.append("failure_classified", step_path=step_path, attempt=n, data=cls)
        return _failed(ctx, step_path, n, [cls["message"]])
    if (ctx.attempt_dir(step_path, n) / "result" / "result.json").is_file():
        return submit(ctx, step_path, actor=actor, workspace_changes=workspace_changes, worker_exit=child.as_dict())
    cls = classify_exit(child, signals)
    log.append("attempt_orphaned", step_path=step_path, attempt=n, data=child.as_dict())
    log.append("failure_classified", step_path=step_path, attempt=n, data=cls)
    reasons = [f"{cls['class']} failure ({cls['code']}): {cls['message']}"]
    esc: dict[str, Any] = {"reason": cls["class"], "code": cls["code"], "reasons": reasons}
    if workspace_changes:
        reasons += _workspace_reasons(step_path, workspace_changes)
        esc["changed"] = workspace_changes
    log.append("step_escalated", step_path=step_path, attempt=n, data=esc)
    return Outcome(step_path, n, "escalated", reasons)


def resolve_effort(ctx: RunContext, node: Any, config: Any, step_path: str | None = None) -> tuple[str, str]:
    """The step's effort (``S`` | ``M`` | ``L``) and where it came from (§8.7).

    ``effort`` on the step; else ``effort_from`` resolved from the record; else
    (or when that does not resolve to a known effort) ``effort.default`` from
    ``project.yaml`` (§18 #9: M).
    """
    from .models import EFFORTS
    from .packet import _NotApplicable, _resolve, _Unresolvable

    if getattr(node, "effort", None):
        return node.effort, "step"
    ref = getattr(node, "effort_from", None)
    if ref:
        try:
            loc = groups.locate(ctx.recipe, step_path or node.id)
            value = _resolve(ctx, ctx.record(), "effort", ref, loc).inline
        except (_Unresolvable, _NotApplicable, EngineError) as e:
            return config.default, f"default ({ref} did not resolve: {e})"
        if value in EFFORTS:
            return value, "effort_from"
        return config.default, f"default ({ref} is {value!r}, not one of {', '.join(EFFORTS)})"
    return config.default, "default"


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
    view = view_of(ctx)
    for path, st in sorted(ctx.log.state().steps.items()):
        if st.state in ("awaiting_human", "escalated") and "/" in path and view.live_reason(path, dispatch=False):
            continue  # inside a superseded or abandoned instance, or an earlier iteration
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
    for ipath, lim in view.pending_limits():
        d = lim.data
        out.append(
            {
                "ref": ipath, "step_path": ipath, "kind": "iteration_limit", "iteration": d.get("iteration"),
                "max_iterations": d.get("max_iterations"), "reason": "iteration_limit",
                "reasons": [f"{ipath} reached {d.get('max_iterations')} iterations without meeting its exit condition", *(d.get("reasons") or [])],
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
    extra = {"recorded_by": recorded_by} if recorded_by else {}
    if groups.locate_instance(ctx.recipe, ref) is not None:
        return _decide_iteration_limit(ctx, ref, decision, note, actor, extra)
    current = log.state().step(ref)
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
    return _gate_failed(ctx, ref, n, gate_index, reasons)


def _decide_iteration_limit(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any]) -> Outcome:
    """The owner's answer to an instance at ``max_iterations`` (§8.5).

    ``retry``: a fresh budget of ``max_iterations``; the next iteration starts at
    ``repeat_from`` (the note reaches it with the open findings). ``abandon``:
    the instance is abandoned and the group cannot pass.
    """
    if decision not in ESCALATION_DECISIONS:
        raise EngineError("decide.bad_decision", f"{ref} reached its iteration limit; decision must be one of {ESCALATION_DECISIONS}, got {decision!r}")
    hit = groups.locate_instance(ctx.recipe, ref)
    assert hit is not None
    loc, inst = hit
    assert isinstance(loc.node, Group)
    view = view_of(ctx)
    lim = view.pending_limit(loc.node, loc.path, inst)
    if lim is None:
        raise EngineError("decide.nothing_pending", f"{ref} has no open owner decision")
    cur = int(lim.data["iteration"])
    ctx.log.append(
        "human_decision", actor=actor, step_path=ref,
        data={"ref": ref, "kind": "iteration_limit", "iteration": cur, "decision": decision, "note": note, **extra},
    )
    if decision == "retry":
        data: dict[str, Any] = {"iteration": cur + 1, "from": loc.node.repeat_from or loc.node.steps[0].id, "budget_base": cur, "after_decision": True}
        if note:
            data["note"] = note
        ctx.log.append("iteration_started", step_path=ref, data=data)
    ready = refresh(ctx)
    return Outcome(ref, cur, "next_iteration" if decision == "retry" else "abandoned", [note] if note else [], ready, _completed(ctx))


def revise(ctx: RunContext, step_path: str, reason: str, *, actor: str = "director") -> Outcome:
    """Correct an earlier step of this run (§8.9); the owner's approval is the director skill's rule.

    The step's accepted result becomes ``superseded`` and the step is ready for
    a new attempt whose packet holds the previous result and the reason. Every
    accepted dependent in this run becomes ``stale`` (re-run once its
    dependencies pass again), except the instances of a group whose ``foreach``
    source is the revised step: re-expansion judges those item by item. Other
    runs are never touched. Refused while a dependent attempt is in flight.
    """
    if not reason.strip():
        raise EngineError("revise.reason_required", "revising a step needs a reason")
    loc = groups.locate(ctx.recipe, step_path)
    if loc is None or not isinstance(loc.node, Step):
        raise EngineError("engine.unknown_step", f"{step_path} is not a step of {ctx.recipe.recipe.ref}")
    if loc.frames:
        raise EngineError("revise.inside_group", f"{step_path} is inside a group; revising steps inside groups is not supported yet (revise the group's source or an earlier step)")
    log = ctx.log
    rs = log.state()
    st = rs.step(step_path)
    if st.state not in ("passed", "imported"):
        raise EngineError("revise.not_accepted", f"{step_path} is {st.state}; only an accepted (passed or imported) step can be revised")
    top = ctx.recipe.recipe.steps
    dependents: list[Any] = []
    frontier = {step_path}
    while frontier:
        nxt = {n.id for n in top if n not in dependents and frontier & set(n.depends_on)}
        dependents += [n for n in top if n.id in nxt]
        frontier = nxt
    dep_ids = {n.id for n in dependents}
    busy = sorted(p for p, s in rs.steps.items() if s.state in groups.IN_FLIGHT and p.split("/", 1)[0] in dep_ids)
    if busy:
        raise EngineError("revise.in_flight", f"cannot revise {step_path} while dependent work is in flight: {', '.join(busy)}")
    log.append("step_revised", actor=actor, step_path=step_path, attempt=None, data={"reason": reason})
    log.append("step_ready", step_path=step_path, data={"revision": True})
    view = view_of(ctx)
    stale: list[str] = []
    for node in dependents:
        if isinstance(node, Step):
            stale.append(node.id)
            continue
        if node.foreach and refs.parse(node.foreach).kind == "step_output" and refs.parse(node.foreach).step == step_path:
            continue  # re-expansion decides, item by item (§8.5)
        for item in view.live_items(node.id):
            f = view.frame(node, node.id, item["id"])
            stale += view.effective_paths(f) if f else []
    for p in stale:
        if view.rs.step(p).state in ("passed", "imported"):
            log.append("step_stale", step_path=p, data={"cause": "revised", "revised": step_path})
    return Outcome(step_path, st.attempt, "revised", [reason], [step_path], False)



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
CHECKPOINT_TRIGGERS = (
    "human_decision", "step_passed", "step_escalated", "iteration_limit_reached", "run_completed", "run_abandoned", "lease_released",
)


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
        with self._run_lock(run_id):
            ctx = self._ctx(run_id)
            if not allow_closed and ctx.log.state().state != "active":
                raise EngineError("run.closed", f"run {run_id} is {ctx.log.state().state}")
            leases = self._leases(ctx)
            leases.ensure()
            before = ctx.log.state().last_seq
            out = body(ctx) or {}
            self._after(ctx, leases, before, out)
            return out

    def _run_lock(self, run_id: str) -> Any:
        from .locks import run_lock

        return run_lock(self.project.baton, run_id)

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
        from .locks import project_lock

        try:
            with project_lock(self.project.baton):
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
        from . import gitops, locks, supervisor

        ctx = self._ctx(run_id)
        events = ctx.log.events()
        rs = ctx.log.state()
        started = events[0].data
        view = view_of(ctx)
        steps: dict[str, Any] = {}
        group_info: dict[str, Any] = {}
        for node in ctx.recipe.recipe.steps:
            if isinstance(node, Group):
                info = groups.describe(view, node, node.id)
                group_info[node.id] = {**info, "summary": groups.summary_line(info, node)}
                steps[node.id] = {"state": info["state"], "group": True}
            else:
                st = rs.step(node.id)
                steps[node.id] = {"state": st.state, "attempt": st.attempt}
        ready = [p for p, st in sorted(rs.steps.items(), key=lambda kv: kv[1].last_seq) if st.state == "ready" and view.live_reason(p) is None]
        running = []
        for path, st in sorted(rs.steps.items()):
            if st.state in ("dispatched", "running"):
                disp = _last_data(events, "dispatched", path, st.attempt)
                adir = ctx.attempt_dir(path, st.attempt)
                item = {
                    "step_path": path, "attempt": st.attempt,
                    "profile": disp.get("profile"), "adapter": disp.get("adapter"), "dispatch_id": disp.get("dispatch_id"),
                    "packet": str(adir / "packet"), "result": str(adir / "result"), "deadline": disp.get("deadline"),
                }
                if disp.get("adapter") != "manual" and disp.get("dispatch_id"):
                    item["liveness"] = supervisor.liveness(self.project.baton, disp["dispatch_id"]).as_dict()
                running.append(item)
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
            "groups": group_info,
            "ready": ready,
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
        loc = groups.locate(ctx.recipe, step_path)
        source = None
        if node.independence is not None and loc is not None:
            source = step_path if node.independence.from_step == node.id else groups.child_path(loc.frame, node.independence.from_step)
        return eligible_workers(
            node, step_path, self.project.profiles(), ctx.recipe.vocab, events=ctx.log.events(), preferences=prefs, source_path=source
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

    def dispatch(self, run_id: str, step_path: str, worker: str, *, guidance: str | None = None, wait: bool = False) -> dict[str, Any]:
        """Build the packet and hand it to the worker's adapter (§8.7).

        The worker must be in the step's eligible set (§8.4). Manual workers
        then ``submit``. Process workers (API models, harness CLIs, commands)
        run under a detached supervisor: this call returns once the worker has
        started, with the dispatch id and deadline; the supervisor runs intake
        when it ends. ``wait=True`` then blocks until that is recorded.
        """
        import secrets

        from . import adapters, supervisor
        from .profiles import SetupError, build_env

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
            mode = getattr(node, "workspace", "none")
            workspace = self.project.root if mode != "none" else None
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
            effort, effort_source = resolve_effort(ctx, node, self.project.config.effort, step_path)
            band_s = self.project.config.effort.seconds(effort)
            deadline = supervisor.fmt(ctx.log.clock() + timedelta(seconds=band_s))
            extra: dict[str, Any] = {"auth_mode": profile.auth.mode, "workspace_mode": mode, "effort": effort, "deadline": deadline}
            if effort_source != "step":
                extra["effort_source"] = effort_source
            if env is not None:
                extra["env"] = env.describe()
            built = begin_attempt(
                ctx, step_path, worker, profile, actor=self.director.actor, dispatch_id=dispatch_id, adapter=adapter.name,
                guidance=guidance, preflight=lambda b: adapter.preflight(profile, b.dir), dispatch_data=extra,
                deadline=deadline, effort=effort,
            )
            out: dict[str, Any] = {
                "run_id": ctx.run_id, "step_path": step_path, "attempt": built.attempt, "dispatch_id": dispatch_id,
                "worker": worker, "adapter": adapter.name, "packet_sha256": built.sha256,
                "packet": str(built.dir), "result": str(built.result_dir),
                "effort": effort, "deadline": deadline,
                "handoff": adapter.handoff(profile, built.dir, built.result_dir),
                "warnings": [],
            }
            argv = adapter.command(profile, built.dir, built.result_dir, workspace, mode)
            if argv is None or env is None:
                return out  # a person does the work (no supervisor, no timeout); the Director submits
            if env.resolved is not None:
                argv = [env.resolved.executable, *argv[1:]]
            # read / none steps may not change the tree; CLI flags cannot confine
            # writes to result/, so the runtime compares before and after (§6.3).
            # The runtime's own run and project records are excluded: they change
            # while the worker runs.
            check_tree = getattr(adapter, "touches_files", False) and mode != "write"
            rel_baton = self.project.baton.resolve().relative_to(self.project.root.resolve()).as_posix()
            log_path = self.project.home / "logs" / ctx.run_id / step_path / f"attempt-{built.attempt}.log"
            spec = {
                "root": str(self.project.root), "home": str(self.project.home), "director": self.director.id,
                "run_id": ctx.run_id, "step_path": step_path, "attempt": built.attempt, "dispatch_id": dispatch_id,
                "worker": worker, "adapter": adapter.name, "argv": argv, "env": env.env, "secret_names": env.secrets,
                "cwd": str(workspace or built.dir.parent), "log_path": str(log_path),
                "deadline": deadline, "band_s": band_s, "effort": effort, "extend_once": self.project.config.effort.extend_once,
                "check_tree": check_tree, "exclude": [f"{rel_baton}/runs", f"{rel_baton}/project"],
            }
            proc = supervisor.spawn(spec, log_path.with_suffix(".supervisor.log"))
            marker = supervisor.await_start(self.project.baton, dispatch_id, proc)
            if marker is None:
                # The supervisor never came up: nothing is running this attempt.
                ctx.log.append("attempt_orphaned", step_path=step_path, attempt=built.attempt, data={"supervisor": "did not start"})
                cls = {"class": "platform", "code": "supervisor_failed", "message": f"the supervisor did not start (see {log_path.with_suffix('.supervisor.log')})"}
                ctx.log.append("failure_classified", step_path=step_path, attempt=built.attempt, data=cls)
                reasons = [f"platform failure (supervisor_failed): {cls['message']}"]
                ctx.log.append("step_escalated", step_path=step_path, attempt=built.attempt, data={"reason": "platform", "code": "supervisor_failed", "reasons": reasons})
                out.update(_outcome_dict(Outcome(step_path, built.attempt, "escalated", reasons)))
                return out
            out["supervisor_pid"] = marker.get("supervisor_pid")
            out["worker_pid"] = marker.get("worker_pid")
            out["log"] = str(log_path)
            if not wait and not supervisor.hooks_configured(self.project):
                out["warnings"].append(
                    "no completion hook is configured: nothing will wake you when this finishes; "
                    f"check with `baton status {ctx.run_id}` or `baton wait {ctx.run_id}`"
                )
            return out

        out = self._mutate(run_id, body)
        if wait and "outcome" not in out and out.get("supervisor_pid"):
            waited = self.wait(run_id, out["dispatch_id"])
            res = waited["results"][0] if waited["results"] else {}
            for k in ("outcome", "reasons", "ready", "run_completed", "pending_decisions", "needs_owner", "worker_exit"):
                if k in res or k in waited:
                    out[k] = res.get(k, waited.get(k))
        return out

    # -- async: wait, reconcile, completion (§8.7) --------------------------

    def _process_attempts(self, ctx: RunContext, dispatch_id: str | None = None) -> list[tuple[str, int, dict[str, Any]]]:
        """``(step_path, attempt, dispatched data)`` for running attempts of process workers."""
        out = []
        events = ctx.log.events()
        for path, st in sorted(ctx.log.state().steps.items()):
            if st.state not in ("dispatched", "running"):
                continue
            d = _last_data(events, "dispatched", path, st.attempt)
            if d.get("adapter") == "manual" or not d.get("dispatch_id"):
                continue
            if dispatch_id is None or d["dispatch_id"] == dispatch_id:
                out.append((path, st.attempt, d))
        return out

    def wait(self, run_id: str, dispatch_id: str | None = None, timeout: float | None = None) -> dict[str, Any]:
        """Block until the dispatch (default: every running process attempt of the run) is recorded.

        Reconciles dead supervisors on the way (§10.3 step 3). Returns each
        attempt's outcome as recorded; ``timed_out`` when ``timeout`` passed first.
        """
        import time as _time

        from . import supervisor

        ctx = self._ctx(run_id)
        events = ctx.log.events()
        targets: list[tuple[str, int, str]] = []
        if dispatch_id is not None:
            for ev in events:
                if ev.type == "dispatched" and ev.data.get("dispatch_id") == dispatch_id:
                    targets.append((ev.step_path, ev.attempt, dispatch_id))
            if not targets:
                raise EngineError("wait.unknown_dispatch", f"run {run_id} has no dispatch {dispatch_id}")
        else:
            targets = [(p, n, d["dispatch_id"]) for p, n, d in self._process_attempts(ctx)]
        end = None if timeout is None else _time.monotonic() + timeout
        manual = []
        for path, n, did in targets:
            if _last_data(events, "dispatched", path, n).get("adapter") == "manual":
                manual.append(did)
        while True:
            self.reconcile(run_id)
            ctx = self._ctx(run_id)
            rs = ctx.log.state()
            pending = [
                (p, n, d) for p, n, d in targets
                if d not in manual and ((rs.step(p).state in ("dispatched", "running") and rs.step(p).attempt == n)
                                        or supervisor.read_marker(self.project.baton, d) is not None)
            ]
            if not pending or (end is not None and _time.monotonic() >= end):
                break
            _time.sleep(0.1)
        results = [self._attempt_result(ctx, p, n) | {"dispatch_id": d} for p, n, d in targets]
        pend = pending_decisions(ctx)
        return {
            "run_id": run_id, "results": results, "timed_out": bool(pending), "waiting_for_submit": manual,
            "pending_decisions": pend, "needs_owner": bool(pend),
        }

    def _attempt_result(self, ctx: RunContext, step_path: str, n: int) -> dict[str, Any]:
        """What happened to one attempt, from the record."""
        record = ctx.record()
        st = ctx.log.state().step(step_path)
        mine = [e for e in ctx.log.events() if e.step_path == step_path and e.attempt == n]
        types = [e.type for e in mine]
        reasons: list[str] = []
        for e in mine:
            if e.type == "result_rejected" or (e.type == "gate_failed" and not e.data.get("advisory")):
                reasons += e.data.get("reasons") or []
            elif e.type == "step_escalated":
                reasons += [r for r in e.data.get("reasons") or [] if r not in reasons]
            elif e.type == "failure_classified" and not any(e.data.get("message", "") in r for r in reasons):
                reasons.append(f"{e.data.get('class')} failure ({e.data.get('code')}): {e.data.get('message')}")
        if st.attempt == n and st.state in ("dispatched", "running"):
            outcome = "running"
        elif "step_passed" in types:
            outcome = _passed_outcome(ctx, next(e for e in reversed(mine) if e.type == "step_passed"))
        elif st.attempt == n and st.state == "awaiting_human":
            outcome = "needs_human"
            opened = record.last("human_gate_opened", step_path, n)
            reasons = [opened.data.get("prompt", "")] if opened else []
        elif "step_escalated" in types:
            outcome = "escalated"
        elif "step_abandoned" in types or st.state == "abandoned":
            outcome = "abandoned"
        else:
            outcome = "retry"
        exit_ev = next((e for e in reversed(mine) if e.type in ("attempt_orphaned", "step_timed_out")), None)
        sub = next((e for e in reversed(mine) if e.type == "result_submitted" and "worker_exit" in e.data), None)
        out = {
            "step_path": step_path, "attempt": n, "outcome": outcome, "reasons": reasons,
            "ready": [p for p, s in ctx.log.state().steps.items() if s.state == "ready"],
            "run_completed": _completed(ctx),
        }
        if exit_ev is not None:
            out["worker_exit"] = exit_ev.data
        elif sub is not None:
            out["worker_exit"] = sub.data["worker_exit"]
        log = _last_data(ctx.log.events(), "dispatched", step_path, n)
        if log.get("adapter") not in (None, "manual") and "worker_exit" in out:
            out["worker_exit"] = {**out["worker_exit"], "log": str(self.project.home / "logs" / ctx.run_id / step_path / f"attempt-{n}.log")}
        return out

    def reconcile(self, run_id: str) -> list[dict[str, Any]]:
        """Apply the running-marker table (§8.7) to the run's in-flight process attempts.

        Marker present and supervisor alive → left running (``overdue`` past the
        deadline). Supervisor dead with a result written → intake now. Dead with
        no result → ``attempt_orphaned``, classified ``platform`` /
        ``supervisor_died``, escalated. No marker for a running attempt is
        treated as a dead supervisor. A marker whose attempt is already recorded
        is removed. Hooks fire for every outcome recorded here.
        """
        from . import supervisor

        actions: list[dict[str, Any]] = []
        with self._run_lock(run_id):
            ctx = self._ctx(run_id)
            live = {d["dispatch_id"] for _p, _n, d in self._process_attempts(ctx)}
            for m in supervisor.markers(self.project.baton):
                if m.get("run_id") == run_id and m.get("dispatch_id") not in live and m.get("host") == socket.gethostname():
                    if not supervisor.pid_alive(m.get("supervisor_pid")):
                        supervisor.remove_marker(self.project.baton, m["dispatch_id"])
            if ctx.log.state().state != "active":
                return actions
            for path, n, d in self._process_attempts(ctx):
                did = d["dispatch_id"]
                lv = supervisor.liveness(self.project.baton, did)
                if lv.elsewhere:
                    actions.append({"step_path": path, "attempt": n, "dispatch_id": did, "action": "running_elsewhere", "host": lv.marker.get("host")})
                    continue
                if lv.supervisor_alive:
                    actions.append({"step_path": path, "attempt": n, "dispatch_id": did, "action": "running", "overdue": lv.overdue, "deadline": lv.marker.get("deadline")})
                    continue
                if lv.worker_alive:
                    supervisor.kill_tree_pid(lv.marker["worker_pid"])  # unsupervised: stop it before judging
                has_result = (ctx.attempt_dir(path, n) / "result" / "result.json").is_file()
                changes = self._reconcile_tree(did, d)
                if has_result:
                    outcome = submit(ctx, path, actor=f"worker:{d.get('profile')}", workspace_changes=changes)
                    action = "intake"
                else:
                    cls = classify.supervisor_died()
                    data: dict[str, Any] = {"supervisor": "dead", "marker": lv.marker is not None}
                    ctx.log.append("attempt_orphaned", step_path=path, attempt=n, data=data)
                    ctx.log.append("failure_classified", step_path=path, attempt=n, data=cls)
                    reasons = [f"platform failure (supervisor_died): {cls['message']}"]
                    esc: dict[str, Any] = {"reason": "platform", "code": "supervisor_died", "reasons": reasons}
                    if changes:
                        reasons += _workspace_reasons(path, changes)
                        esc["changed"] = changes
                    ctx.log.append("step_escalated", step_path=path, attempt=n, data=esc)
                    outcome = Outcome(path, n, "escalated", reasons)
                    action = "orphaned"
                actions.append({"step_path": path, "attempt": n, "dispatch_id": did, "action": action, "outcome": outcome.outcome})
                before = ctx.log.state().last_seq
                self._finish_records(ctx, before, {})
                self._fire_and_record(ctx, path, n, did)
                supervisor.remove_marker(self.project.baton, did)
        return actions

    def _reconcile_tree(self, dispatch_id: str, dispatched: dict[str, Any]) -> list[str]:
        from . import gitops, supervisor

        p = supervisor.tree_path(self.project.baton, dispatch_id)
        if dispatched.get("workspace_mode") == "write" or not p.is_file():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        rel_baton = self.project.baton.resolve().relative_to(self.project.root.resolve()).as_posix()
        after = gitops.tree_snapshot(self.project.root, [f"{rel_baton}/runs", f"{rel_baton}/project"])
        return gitops.tree_changes(gitops.TreeSnapshot(raw.get("head"), raw.get("files") or {}), after)

    def _finish_records(self, ctx: RunContext, before: int, out: dict[str, Any]) -> None:
        """Records, lease release on completion and the checkpoint, without requiring the lease (runtime work)."""
        self._after(ctx, self._leases(ctx), before, out)

    def complete(
        self, run_id: str, step_path: str, attempt: int, dispatch_id: str, *, child: ChildResult,
        workspace_changes: list[str], adapter: str, worker: str,
    ) -> dict[str, Any] | None:
        """The supervisor's end of a dispatch: intake, records, checkpoint, hooks (§8.7).

        Returns None when the attempt was already recorded (e.g. reconciled by
        a Director who judged this supervisor dead).
        """
        from . import adapters, docs

        with self._run_lock(run_id):
            ctx = self._ctx(run_id)
            st = ctx.log.state().step(step_path)
            if ctx.log.state().state != "active" or st.state not in ("dispatched", "running") or st.attempt != attempt:
                return None
            before = ctx.log.state().last_seq
            signals = getattr(adapters.get(adapter), "failure_signals", None)
            outcome = finish_child(ctx, step_path, attempt, child, actor=f"worker:{worker}", signals=signals, workspace_changes=workspace_changes)
            out = _outcome_dict(outcome)
            docs.write_records(ctx)  # so BATON_RECORD is current when the hooks run
        self._fire_and_record(ctx, step_path, attempt, dispatch_id, before=before)
        return out

    def overdue(self, run_id: str, step_path: str, attempt: int, dispatch_id: str, previous: str, deadline: str, effort: str | None) -> None:
        """An overdue worker got one more band: record it and fire the hook with outcome ``overdue``."""
        with self._run_lock(run_id):
            ctx = self._ctx(run_id)
            st = ctx.log.state().step(step_path)
            if st.state != "running" or st.attempt != attempt:
                return
            before = ctx.log.state().last_seq
            ctx.log.append(
                "deadline_extended", step_path=step_path, attempt=attempt,
                data={"dispatch_id": dispatch_id, "previous_deadline": previous, "deadline": deadline, "band": effort},
            )
        self._fire_and_record(ctx, step_path, attempt, dispatch_id, before=before, outcome="overdue")

    def _hook_info(self, ctx: RunContext, step_path: str, n: int, dispatch_id: str, outcome: str | None) -> dict[str, Any]:
        mine = [e for e in ctx.log.events() if e.step_path == step_path and e.attempt == n]
        types = {e.type for e in mine}
        cls_ev = next((e for e in reversed(mine) if e.type == "failure_classified"), None)
        esc = next((e for e in reversed(mine) if e.type == "step_escalated"), None)
        st = ctx.log.state().step(step_path)
        state = st.state if st.attempt == n else "ready"
        passed_ev = next((e for e in reversed(mine) if e.type == "step_passed"), None)
        judged = _passed_outcome(ctx, passed_ev) if passed_ev is not None else None
        if outcome is None:
            if judged == "iteration_limit":
                outcome = "needs_human"
            elif judged == "next_iteration":
                outcome = "gate_failed"
            elif "step_passed" in types:
                outcome = "passed"
            elif "step_timed_out" in types:
                outcome = "timed_out"
            elif "attempt_orphaned" in types:
                outcome = "failed"
            elif state == "awaiting_human" or (esc is not None and esc.data.get("reason") == "blocked"):
                outcome = "needs_human"
            elif esc is not None and esc.data.get("reason") in ("platform", "configuration", "unknown"):
                outcome = "failed"
            else:
                outcome = "gate_failed"
        record = ctx.run_dir / "docs" / f"{step_path}.md"
        return {
            "run_id": ctx.run_id, "step_path": step_path, "attempt": n, "dispatch_id": dispatch_id, "outcome": outcome,
            "classification": cls_ev.data.get("class") if cls_ev is not None else None,
            "step_state": state,
            "needs_owner": (state in ("awaiting_human", "escalated") or judged == "iteration_limit") and outcome != "overdue",
            "record": str(record),
        }

    def _fire_and_record(self, ctx: RunContext, step_path: str, n: int, dispatch_id: str, *, before: int | None = None, outcome: str | None = None) -> None:
        """Fire hooks outside the run lock, then record them, write records and checkpoint."""
        from . import supervisor

        info = self._hook_info(ctx, step_path, n, dispatch_id, outcome)
        fired = supervisor.fire_hooks(self.project, info)
        with self._run_lock(ctx.run_id):
            ctx = self._ctx(ctx.run_id)
            start = ctx.log.state().last_seq if before is None else before
            for data in fired:
                ctx.log.append(
                    "completion_hook_fired" if data.get("ok") else "completion_hook_failed",
                    step_path=step_path, attempt=n, data=data,
                )
            if before is not None or fired:
                self._finish_records(ctx, start, {})

    def doctor(self, profile: str | None = None, *, run_noop: bool = True) -> dict[str, Any]:
        from .doctor import doctor

        return doctor(self.project, profile, run_noop=run_noop)

    def retry(self, run_id: str, step_path: str, worker: str | None = None, guidance: str | None = None, *, wait: bool = False) -> dict[str, Any]:
        """A new attempt of a step whose previous attempt was not accepted. Guidance is additive only."""
        ctx = self._ctx(run_id)
        st = ctx.log.state().step(step_path)
        if st.state == "escalated":
            raise EngineError("retry.escalated", f"{step_path} is escalated; record the owner's decision first (decide {step_path} retry)")
        if st.state != "ready" or st.attempt == 0:
            raise EngineError("retry.not_retryable", f"{step_path} is {st.state} with {st.attempt} attempts; retry needs a ready step with a previous attempt")
        if worker is None:
            worker = _last_data(ctx.log.events(), "dispatched", step_path, st.attempt).get("profile")
        return self.dispatch(run_id, step_path, worker, guidance=guidance, wait=wait)

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

    def revise(self, run_id: str, step_path: str, reason: str) -> dict[str, Any]:
        """Correct an earlier step of this run (§8.9). Owner approval is the director skill's rule."""

        def body(ctx: RunContext) -> dict[str, Any]:
            outcome = revise(ctx, step_path, reason, actor=self.director.actor)
            stale = [e.step_path for e in ctx.log.events() if e.type == "step_stale" and e.data.get("revised") == step_path and e.seq > ctx.record().last("step_revised", step_path).seq]
            return {"run_id": ctx.run_id, **_outcome_dict(outcome), "stale": stale}

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
        # Reconcile in-flight attempts with their running markers (§8.7, §10.3).
        reconciled = self.reconcile(run_id)
        ctx = self._ctx(run_id)
        # Manual attempts wait for submit; git does not keep empty directories,
        # so recreate their result directories.
        rs = ctx.log.state()
        events = ctx.log.events()
        for path, st in sorted(rs.steps.items()):
            if st.state == "running" and _last_data(events, "dispatched", path, st.attempt).get("adapter") in ("manual", None):
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


def _passed_outcome(ctx: RunContext, ev: Any) -> str:
    """``passed``, or for a judge whose gate failed: ``next_iteration`` | ``iteration_limit``."""
    cond = ev.data.get("condition") or {}
    if cond.get("gates_passed") is not False:
        return "passed"
    loc = groups.locate(ctx.recipe, ev.step_path)
    if loc is not None and loc.frame is not None:
        for e in ctx.log.events():
            if e.type == "iteration_limit_reached" and e.step_path == loc.frame.instance_path and e.data.get("judged_seq") == ev.seq:
                return "iteration_limit"
    return "next_iteration"


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
        if e.type == "step_passed" and (e.data.get("condition") or {}).get("gates_passed") is False:
            phrases.append(f"{e.step_path} judged not done [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "step_passed":
            phrases.append(f"{e.step_path} passed [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "step_escalated":
            phrases.append(f"{e.step_path} escalated ({e.data.get('reason')}) [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "human_decision":
            phrases.append(f"{e.step_path} decision {e.data.get('decision')}" + (f" [attempt {e.attempt}]" if e.attempt else ""))
        elif e.type == "iteration_limit_reached":
            phrases.append(f"{e.step_path} reached {e.data.get('max_iterations')} iterations")
        elif e.type == "run_completed":
            phrases.append("run completed")
        elif e.type == "run_abandoned":
            phrases.append("run abandoned")
        elif e.type == "lease_released" and not ended:
            phrases.append(f"lease released by {e.data.get('director_id')}")
    subject = f"baton({ctx.run_id}): " + "; ".join(phrases)
    body = [f"seq {e.seq} {e.type}" + (f" {e.step_path}" if e.step_path else "") + (f"#{e.attempt}" if e.attempt else "") for e in new]
    return subject, body
