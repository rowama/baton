"""The Director API (§13.1), shared by the CLI and (later) the MCP server.

Only this module sequences step events: ``packet.py`` builds packets and
``intake.py`` evaluates results and gates, and the functions here turn their
answers into transitions, one event each (§8.1).

Phase 3 provides the core of a step's life without adapters or supervision:
``start`` → ``begin_attempt`` (packet built, attempt dispatched and running) →
the worker writes ``result/`` → ``submit`` (intake and gates) → ``decide`` for
human gates. ``dispatch`` with real adapters builds on ``begin_attempt``.

Failure handling: a rejected result, a failed blocking gate, a ``failed``
worker or a rejected human gate sends the step back to ``ready`` while
attempts remain (the next packet carries the reasons as ``prior_feedback``),
and to ``escalated`` once ``max_attempts`` is used. A ``blocked`` result and a
gate that cannot be configured escalate at once.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
)
from .recipe import LoadedRecipe, build_plan, load_recipe
from .state import SATISFIES_DEPS, IllegalTransition
from .store import Store, canonical_json

__all__ = [
    "EngineError", "HandoffError", "Outcome", "RunContext",
    "begin_attempt", "decide", "open_run", "pending_decisions", "plan", "refresh", "start", "submit",
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
) -> RunContext:
    """Validate run inputs, open a run pinned to this recipe, and ready its first steps."""
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
) -> BuiltPacket:
    """Build the packet for the step's next attempt and mark the attempt dispatched and running.

    Raises ``HandoffError`` or ``EngineError`` with nothing written.
    """
    built = build_packet(ctx, step_path, profile_name, profile, deadline=deadline)
    log, n = ctx.log, built.attempt
    log.append("worker_selected", actor=actor, step_path=step_path, attempt=n, data={"profile": profile_name})
    log.append(
        "packet_built",
        step_path=step_path,
        attempt=n,
        data={"packet_sha256": built.sha256, "profile": profile_name, "worker_profile_sha256": built.manifest["worker_profile_sha256"]},
    )
    log.append("dispatched", actor=actor, step_path=step_path, attempt=n, data={"profile": profile_name, "packet_sha256": built.sha256})
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


# ---------------------------------------------------------------------------
# Owner decisions
# ---------------------------------------------------------------------------

GATE_DECISIONS = ("approve", "reject")


def pending_decisions(ctx: RunContext) -> list[dict[str, Any]]:
    """Open human gates: one per step awaiting a human, with the ``ref`` to pass to ``decide``."""
    out = []
    record = ctx.record()
    for path, st in sorted(ctx.log.state().steps.items()):
        if st.state == "awaiting_human":
            opened = record.last("human_gate_opened", path, st.attempt)
            out.append({"ref": path, "step_path": path, "attempt": st.attempt, "kind": "gate", "prompt": opened.data["prompt"] if opened else ""})
    return out


def decide(ctx: RunContext, ref: str, decision: str, note: str = "", *, actor: str = "human") -> Outcome:
    """Record the owner's decision on an open human gate, verbatim, then continue the step.

    ``ref`` is the step path of a step that is awaiting a human. ``approve``
    passes the gate and runs any later gates; ``reject`` fails it, and the note
    becomes the next attempt's feedback.
    """
    if decision not in GATE_DECISIONS:
        raise EngineError("decide.bad_decision", f"decision must be one of {GATE_DECISIONS}, got {decision!r}")
    log = ctx.log
    current = log.state().step(ref)
    if current.state != "awaiting_human":
        raise EngineError("decide.nothing_pending", f"{ref} has no open human gate (it is {current.state})")
    step = _step(ctx, ref)
    n = current.attempt
    opened = ctx.record().last("human_gate_opened", ref, n)
    gate_index = opened.data["gate"]
    log.append(
        "human_decision",
        actor=actor,
        step_path=ref,
        attempt=n,
        data={"ref": ref, "kind": "gate", "gate": gate_index, "decision": decision, "note": note},
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
