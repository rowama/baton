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
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from jsonschema import Draft202012Validator

from . import __version__, classify, groups, labels, refs, reviews, versions
from .intake import read_result, run_script_gate
from .models import FindingsGate, Group, HumanGate, Plan, Protect, ReviewGate, SchemaGate, ScriptGate, Step, WorkerProfile, recorded_questions
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
    revision_of,
    view_of,
)
from .recipe import LoadedRecipe, build_plan, load_recipe
from .redact import redact_text
from .state import SATISFIES_DEPS, IllegalTransition
from .store import Store, StoreError, canonical_json
from .supervisor import ChildResult

__all__ = [
    "Api", "EngineError", "HandoffError", "IntegrityError", "Outcome", "RunContext",
    "abandon_run", "begin_attempt", "decide", "disposition", "escalate_no_worker", "waive", "finish_child", "open_run", "pending_decisions", "plan",
    "resolve_effort",
    "refresh", "retriage", "revise", "start", "submit",
]


def plan(recipe: str | Path, level: str | None = None) -> Plan:
    """Per-level step and gate table for a recipe directory. Raises ``RecipeError``."""
    return build_plan(load_recipe(recipe), level=level)


@dataclass
class Outcome:
    """What happened to a step after ``submit`` or ``decide``."""

    step_path: str
    attempt: int
    outcome: str  # passed | needs_human | needs_review | retry | escalated | abandoned | next_iteration | iteration_limit | revised | recorded | waived | waiver_pending
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
        "runtime": __version__,
        "formats": {"events": versions.current_format("events"), "packet": PROTOCOL, "recipe": recipe.recipe.format},
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


def awaiting_baseline(events: list[Any], *, kind: str = "work_item") -> bool:
    """Whether a run waits for its adoption's baseline (§11.1).

    ``work_item``: a run created by adoption (it readies only its triage step
    until then). ``adoption``: the adoption run itself (it completes only then).
    """
    if not events or events[0].type != "run_started":
        return False
    d = events[0].data
    if kind == "adoption" and d.get("kind") != "adoption":
        return False
    if kind == "work_item" and not d.get("adoption"):
        return False
    return not any(e.type == "baseline_established" for e in events)


#: ``importer(path, node, frame) -> step_imported data | None``: a seed for a step about to be readied (§11.4).
Importer = Callable[[str, Step, "groups.Frame | None"], "dict[str, Any] | None"]


def refresh(ctx: RunContext, importer: Importer | None = None) -> list[str]:
    """Move the run forward as far as the record allows; complete it when every top-level node is done.

    Readies every step (top level or inside a group's current iteration) whose
    dependencies are satisfied. ``stale`` steps are left stale: once their
    dependencies pass they are runnable (dispatch re-runs them, or the owner
    confirms them, §8.1);
    expands and re-expands groups; starts instances as ``concurrency`` allows;
    ends iterations judged unmet and starts the next one, or escalates at
    ``max_iterations`` (§8.5). Steps with ``applies_to`` wait until a
    complexity level is set, and are then marked ``skipped`` when it excludes
    them (§5.5). A run created by adoption readies only its triage step until
    its baseline is established; an adoption run completes only then (§11.1).
    ``importer`` turns a step about to be readied into ``step_imported`` (the
    baseline's seeds, §11.4). One event at a time, each from a fresh view.
    """
    log = ctx.log
    if log.state().state != "active":
        return []
    from . import publish

    publish.publish_due(ctx)  # step_passed → publish, before dependents move on (§8.10)
    readied: list[str] = []
    events = log.events()
    if importer is None:
        importer = _baseline_importer(ctx, events)
    hold = awaiting_baseline(events)
    nodes = ctx.recipe.recipe.steps
    if hold:
        cx = ctx.recipe.recipe.complexity
        nodes = [n for n in nodes if cx is not None and n.id == cx.triage_step]
    while _advance(ctx, view_of(ctx), nodes, None, readied, importer):
        pass
    from .frame import awaiting_selection

    if hold or awaiting_baseline(events, kind="adoption") or awaiting_selection(events):
        return readied
    view = view_of(ctx)
    if all(view.node_state(n, n.id, None) in SATISFIES_DEPS for n in ctx.recipe.recipe.steps) and not publish.outstanding(ctx):
        log.append("run_completed")  # a pending publish conflict or drift holds completion (§10.4, §10.5)
    return readied


def _baseline_importer(ctx: RunContext, events: list[Any]) -> Importer | None:
    """Seeds the run's baseline holds, imported as their steps come due (§11.4).

    The seeds are data in ``baseline_established``, so an instance that starts
    later (``concurrency``) still has its finished steps imported, never re-run.
    Only steps with no events of their own, and only in an instance's first
    iteration, are imported.
    """
    ev = next((e for e in events if e.type == "baseline_established" and e.data.get("seeds")), None)
    if ev is None:
        return None
    seeds = {(x["step"], x.get("item")): x["data"] for x in ev.data["seeds"]}

    def imp(path: str, node: Step, frame: groups.Frame | None) -> dict[str, Any] | None:
        if path in ctx.log.state().steps:
            return None
        if frame is None:
            key: tuple[str, int | None] = (node.id, None)
        else:
            if "/" in frame.group_path or frame.iteration != 1:
                return None  # seeds reach one level of groups, first iterations only
            idx = None
            if frame.group.foreach:
                exp = view_of(ctx).expansion(frame.group_path) or {}
                if exp.get("mode") == "foreach":
                    idx = next((i for i, it in enumerate(exp.get("items") or []) if it["id"] == frame.instance), None)
            key = (f"{frame.group.id}/{node.id}", idx)
        data = seeds.get(key)
        return dict(data) if data is not None else None

    return imp


def _advance(
    ctx: RunContext, view: groups.View, nodes: list[Any], frame: groups.Frame | None, readied: list[str], importer: Importer | None = None,
) -> bool:
    """Append the next event this scope calls for; ``True`` if one was appended."""
    for node in nodes:
        path = groups.child_path(frame, node.id)
        if node.applies_to is not None:
            if view.level is None:
                continue  # waits for triage (§5.5)
            if view.level not in node.applies_to:
                if view.rs.step(path).state == "blocked_on_deps" and (isinstance(node, Step) or view.expansion(path) is None):
                    ctx.log.append("step_skipped", step_path=path, data={"level": view.level, "cause": "complexity"})
                    return True
                continue
        if not view.deps_met(node, frame):
            continue
        if isinstance(node, Step):
            state = view.rs.step(path).state
            if state == "blocked_on_deps":
                seed = importer(path, node, frame) if importer is not None else None
                if seed is not None:
                    waivers = seed.pop("waivers", [])
                    ctx.log.append("step_imported", actor="human", step_path=path, data=seed)
                    for w in waivers:  # proposed by the baseline: a gate passed outside Baton without evidence (§11.4)
                        ctx.log.append("gate_waived", actor="human", step_path=path, data={**w, "scope": "imported"})
                    return True
                ctx.log.append("step_ready", step_path=path, data={})
                readied.append(path)
                return True
        elif _advance_group(ctx, view, node, path, frame, readied, importer):
            return True
    return False


def _advance_group(
    ctx: RunContext, view: groups.View, group: Group, path: str, outer: groups.Frame | None, readied: list[str], importer: Importer | None = None,
) -> bool:
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
        if _advance(ctx, view, group.steps, f, readied, importer):
            return True
    return False


def _completed(ctx: RunContext) -> bool:
    return ctx.log.state().state == "completed"


# ---------------------------------------------------------------------------
# Tailoring: triage, complexity levels, re-triage (§5.5)
# ---------------------------------------------------------------------------


def _is_triage(ctx: RunContext, step_path: str) -> bool:
    cx = ctx.recipe.recipe.complexity
    return cx is not None and step_path == cx.triage_step


def _triage_output(ctx: RunContext, step_path: str, n: int) -> dict[str, Any]:
    sha = _registered(ctx, step_path, n).get("output_sha256")
    out = json.loads(ctx.log.cas.read(sha)) if sha else {}
    return out if isinstance(out, dict) else {}


def pending_retriage(events: list[Any]) -> Any:
    """The open ``retriage_requested`` event, if a re-triage waits to be applied or rejected."""
    req = None
    for e in events:
        if e.type == "retriage_requested":
            req = e
        elif req is not None and (e.type == "retriage_applied" or (e.type == "step_passed" and e.data.get("retriage_rejected"))):
            req = None
    return req


def _reasons_of(out: dict[str, Any]) -> list[str]:
    r = out.get("reasons")
    if isinstance(r, list):
        return [str(x) for x in r]
    return [str(r)] if isinstance(r, str) and r else []


def _triage_gate(ctx: RunContext, step_path: str, n: int) -> Outcome | None:
    """The implicit approval of a triage result (§5.5, §18 #8); ``None`` when none is needed (or it passed)."""
    if not _is_triage(ctx, step_path):
        return None
    log = ctx.log
    events = log.events()
    record = ctx.record()
    if any(e.type == "gate_passed" and e.data.get("gate") == "triage" for e in record.attempt_events(step_path, n)):
        return None
    if awaiting_baseline(events):
        return None  # the baseline approves the level (§11.5)
    cx = ctx.recipe.recipe.complexity
    assert cx is not None
    out = _triage_output(ctx, step_path, n)
    level = out.get("level")
    req = pending_retriage(events)
    if req is None and (level == cx.levels[0] or record.level() is not None):
        return None
    why = _reasons_of(out)
    because = f" because: {'; '.join(why)}" if why else ""
    if req is not None:
        prev = req.data.get("previous_level")
        prompt = (f"Re-triage ({req.data.get('reason')}): apply level {level!r} instead of {prev!r}{because}? "
                  f"Approve applies it to steps not yet started; reject keeps {prev!r}.")
    else:
        prompt = f"Triage rated this work {level!r} (levels: {', '.join(cx.levels)}){because}. Approve this level? (Reject: triage is tried again with your note.)"
    data = {"gate": "triage", "type": "triage", "implicit": True, "advisory": False, "prompt": prompt, "ref": step_path, "level": level}
    if req is not None:
        data["retriage"] = True
    log.append("human_gate_opened", step_path=step_path, attempt=n, data=data)
    return Outcome(step_path, n, "needs_human", [prompt])


def _apply_triage(ctx: RunContext, step_path: str, n: int) -> None:
    """After the triage step passed: set the level, or apply a re-triage (§5.5)."""
    if not _is_triage(ctx, step_path):
        return
    events = ctx.log.events()
    if awaiting_baseline(events):
        return
    out = _triage_output(ctx, step_path, n)
    level = out.get("level")
    approved = next((e for e in ctx.record().attempt_events(step_path, n) if e.type == "human_decision" and e.data.get("gate") == "triage"), None)
    req = pending_retriage(events)
    if req is not None:
        _apply_retriage(ctx, level, req, approved.seq if approved else None)
        return
    if ctx.record().level() is not None:
        return
    data: dict[str, Any] = {"level": level, "approval": "owner" if approved else "auto"}
    if approved is not None:
        data["decision_seq"] = approved.seq
    if _reasons_of(out):
        data["reasons"] = _reasons_of(out)
    ctx.log.append("complexity_set", step_path=step_path, data=data)


def _not_started(st: Any) -> bool:
    return st.state == "blocked_on_deps" or (st.state == "ready" and st.attempt == 0)


def _apply_retriage(ctx: RunContext, level: str, req: Any, decision_seq: int | None) -> None:
    """Re-evaluate every step that has not started at the new level; flag accepted steps it would treat differently."""
    log = ctx.log
    old = ctx.record().level()
    view = view_of(ctx)
    rs = view.rs
    skip: list[str] = []
    unskip: list[str] = []
    pre: list[str] = []

    def included(node: Any, lv: str | None) -> bool:
        return node.applies_to is None or lv in node.applies_to

    def walk(nodes: list[Any], frame: groups.Frame | None) -> None:
        for node in nodes:
            path = groups.child_path(frame, node.id)
            if frame is not None and path in seen:
                continue  # a step before repeat_from, judged in its first iteration
            seen.add(path)
            st = rs.step(path)
            new_in = included(node, level)
            if st.state == "skipped":
                if new_in:
                    unskip.append(path)
                continue
            if isinstance(node, Step):
                if not new_in and _not_started(st):
                    skip.append(path)
                elif st.state in ("passed", "imported"):
                    differs = any(gate_included(g, old) != gate_included(g, level) for g in node.gates)
                    if not new_in or differs:
                        pre.append(path)
                continue
            if view.expansion(path) is None:
                if not new_in and st.state == "blocked_on_deps":
                    skip.append(path)
                continue
            for item in view.live_items(path):
                f = view.frame(node, path, item["id"])
                if f is not None and view.instance_state(node, path, item["id"]) not in ("abandoned", "superseded"):
                    walk(node.steps, f)

    seen: set[str] = set()
    walk(ctx.recipe.recipe.steps, None)
    log.append(
        "retriage_applied", step_path=req.step_path,
        data={"level": level, "previous_level": old, "reason": req.data.get("reason"), "decision_seq": decision_seq,
              "skipped": skip, "unskipped": unskip, "pre_retriage": pre},
    )
    for p in skip:
        log.append("step_skipped", step_path=p, data={"level": level, "cause": "retriage"})
    for p in unskip:
        log.append("step_unskipped", step_path=p, data={"level": level, "cause": "retriage"})


def retriage(ctx: RunContext, reason: str, *, actor: str = "director") -> Outcome:
    """Rerun triage behind the owner's approval (§5.5): the new level applies only to work not yet started."""
    if not reason.strip():
        raise EngineError("retriage.reason_required", "re-triage needs a reason")
    cx = ctx.recipe.recipe.complexity
    if cx is None:
        raise EngineError("retriage.no_levels", f"{ctx.recipe.recipe.ref} declares no complexity levels")
    log = ctx.log
    events = log.events()
    if awaiting_baseline(events):
        raise EngineError("retriage.awaiting_baseline", "this run's level is set by its adoption baseline; change it there")
    record = ctx.record()
    level = record.level()
    if level is None:
        raise EngineError("retriage.no_level", "triage has not set a level yet; finish triage first")
    if pending_retriage(events) is not None:
        raise EngineError("retriage.pending", "a re-triage is already waiting to be decided")
    rs = log.state()
    busy = sorted(p for p, st in rs.steps.items() if st.state in groups.IN_FLIGHT)
    if busy:
        raise EngineError("retriage.in_flight", f"cannot re-triage while work is in flight: {', '.join(busy)}")
    tpath = cx.triage_step
    st = rs.step(tpath)
    if st.state not in ("passed", "imported"):
        raise EngineError("retriage.triage_not_accepted", f"{tpath} is {st.state}; re-triage needs an accepted triage result")
    log.append("retriage_requested", actor=actor, step_path=tpath, data={"reason": reason, "previous_level": level})
    log.append("step_revised", actor=actor, step_path=tpath, data={"reason": reason, "retriage": True})
    log.append("step_ready", step_path=tpath, data={"revision": True, "retriage": True})
    return Outcome(tpath, st.attempt, "retriage_requested", [reason], [tpath])


def _decide_triage(ctx: RunContext, step: Step, ref: str, n: int, decision: str, note: str) -> Outcome:
    """The owner's answer at the implicit triage gate (§5.5)."""
    log = ctx.log
    opened = ctx.record().last("human_gate_opened", ref, n)
    base: dict[str, Any] = {"gate": "triage", "type": "triage", "implicit": True, "level": opened.data.get("level") if opened else None}
    if decision == "approve":
        log.append("gate_passed", step_path=ref, attempt=n, data={**base, "approved": True})
        return _run_gates(ctx, step, ref, n, len(step.gates))
    reasons = [f"the owner did not approve the level: {note}" if note else "the owner did not approve the level"]
    log.append("gate_failed", step_path=ref, attempt=n, data={**base, "reasons": reasons})
    req = pending_retriage(log.events())
    if req is None:
        return _failed(ctx, ref, n, reasons)
    rev = revision_of(ctx.record(), ref)
    assert rev is not None
    revised, previous = rev
    decision_ev = ctx.record().last("human_decision", ref, n)
    data = {k: v for k, v in previous.data.items() if k not in ("confirmed", "retriage_rejected")}
    data["retriage_rejected"] = {"decision_seq": decision_ev.seq if decision_ev else None, "previous_seq": previous.seq, "requested_seq": req.seq}
    log.append("step_passed", step_path=ref, attempt=n, data=data)
    ready = refresh(ctx)
    return Outcome(ref, n, "retriage_rejected", reasons, ready, _completed(ctx))


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
    if log.state().step(step_path).state == "stale":
        log.append("step_ready", step_path=step_path, data={"rerun": True})  # a runnable stale step re-runs (§8.1)
    node = node_for(ctx.recipe, step_path)
    dispatch_data = dict(dispatch_data or {})
    if isinstance(node, Step) and node.protect is not None and "protected" not in dispatch_data:
        # Protected paths are hashed before the worker starts and compared at intake (§9.4).
        dispatch_data["protected"] = reviews.protected_snapshot(ctx.store.root, node.protect_paths())
    if reviews.is_reviewer(node):
        head = reviews.repo_head(ctx.store.root)
        if head:
            dispatch_data["head"] = head  # the reviewed commit (§9.2: rejections cite it)
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
    disp.update(dispatch_data)
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
    claims: list[dict[str, Any]] = []
    if sub.status == "completed" and not sub.problems:
        loc = groups.locate(ctx.recipe, step_path)
        assert loc is not None
        sub.problems += view_of(ctx).foreach_id_problems(loc, sub.output)
        if sub.dispositions:
            claims, problems = _worker_dispositions(ctx, loc, sub.dispositions)
            sub.problems += problems

    log.append(
        "result_submitted",
        actor=actor,
        step_path=step_path,
        attempt=n,
        data={"result_sha256": sub.result_sha256, "status": sub.status, **sub.registered(), **({"worker_exit": worker_exit} if worker_exit else {})},
    )
    _record_worker_feedback(ctx, step_path, n, actor, sub.process_feedback)
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
    for c in claims:
        log.append("finding_dispositioned", actor=actor, step_path=c.pop("step_path"), data=c)
    log.append(
        "gate_passed",
        step_path=step_path,
        attempt=n,
        data={"gate": "provenance", "type": "provenance", "implicit": True, "artifacts": sorted(sub.artifacts)},
    )
    if step.protect is not None:
        held = _protected_gate(ctx, step, step_path, n)
        if held is not None:
            return held
    return _run_gates(ctx, step, step_path, n, 0)


def _record_worker_feedback(ctx: RunContext, step_path: str, n: int, actor: str, items: list[Any]) -> None:
    """A worker's ``process_feedback`` (§7.2) goes to the project log, keyed by qualified step id (§12.4)."""
    if not items:
        return
    from . import sme
    from .locks import project_lock
    from .redact import redact_text

    with project_lock(ctx.store.baton):
        plog = ctx.store.project_log()
        for it in items:
            d = it if isinstance(it, dict) else {"text": str(it)}
            kind = d.get("kind") if d.get("kind") in sme.FEEDBACK_KINDS and d.get("kind") != "skipped_step" else "friction"
            text = redact_text(str(d.get("text") or json.dumps(d, sort_keys=True)))[:2000]
            plog.append("process_feedback", actor=actor, data={
                "kind": kind, "text": text, "run": ctx.run_id, "step_path": step_path, "attempt": n,
                "qualified": sme.qualified(ctx.recipe.recipe.ref, step_path),
            })


def _protected_gate(ctx: RunContext, step: Step, step_path: str, n: int) -> Outcome | None:
    """The implicit ``protected`` gate (§9.4): ``None`` to go on with the declared gates.

    Protected files are hashed when the attempt is dispatched and again now. A
    change records ``protected_path_modified``. ``fail``: the gate fails.
    ``warn``: the step waits on the owner like a human gate (approve keeps the
    change; reject fails the gate). A pending waiver lets one change through.
    """
    log = ctx.log
    before = _last_data(log.events(), "dispatched", step_path, n).get("protected")
    if before is None:
        return None
    changed = reviews.protected_changes(before, reviews.protected_snapshot(ctx.store.root, step.protect_paths()))
    base = {"gate": "protected", "type": "protected", "implicit": True}
    if not changed:
        log.append("gate_passed", step_path=step_path, attempt=n, data=base)
        return None
    mode = step.protect.on_violation if isinstance(step.protect, Protect) else "warn"
    log.append("protected_path_modified", step_path=step_path, attempt=n, data={"changed": changed, "mode": mode})
    shown = ", ".join(changed[:20]) + (f" and {len(changed) - 20} more" if len(changed) > 20 else "")
    reasons = [f"protected paths were modified: {shown}"]
    w = reviews.pending_waiver(log.events(), step_path, "protected")
    if w is not None:
        log.append("gate_passed", step_path=step_path, attempt=n, data={**base, "changed": changed, "waived": True, "waiver_seq": w.seq, "waived_reasons": reasons})
        return None
    if mode == "fail":
        log.append("gate_failed", step_path=step_path, attempt=n, data={**base, "changed": changed, "reasons": reasons})
        return _gate_failed(ctx, step_path, n, "protected", reasons)
    prompt = f"{step_path} modified protected paths: {shown}. Approve keeping the change (reject: the attempt fails and the step is retried)?"
    log.append("human_gate_opened", step_path=step_path, attempt=n, data={**base, "advisory": False, "prompt": prompt, "ref": step_path, "changed": changed})
    return Outcome(step_path, n, "needs_human", [prompt])


def _worker_dispositions(ctx: RunContext, loc: groups.Located, items: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Check a worker's ``dispositions`` (§9.2, §18 #12): ``(events to record, problems)``.

    A worker may mark ``fixed`` or ``rejected``, with evidence, only findings it
    was shown: those of its own review and findings gates, and those of the
    judges of an enclosing loop. Its claims are provisional until a review
    confirms them.
    """
    events = ctx.log.events()
    lines = _visible_lines(loc)
    head = reviews.repo_head(ctx.store.root)
    out: list[dict[str, Any]] = []
    problems: list[str] = []
    for k, d in enumerate(items):
        where = f"dispositions[{k}]"
        cands = [ln for ln in lines if _line_matches(ctx, ln, d.step)]
        hits = []
        for ln in cands:
            ev = reviews.latest_evaluation(events, ln)
            if ev is not None and any(f["id"] == d.finding for f in ev.data.get("findings") or []):
                hits.append((ln, ev))
        if not hits:
            problems.append(f"{where}: no finding {d.finding!r} of {d.step!r} was shown to this step")
            continue
        if len(hits) > 1:
            problems.append(f"{where}: finding {d.finding!r} of {d.step!r} is ambiguous ({', '.join(h[0] for h in hits)}); give the step path")
            continue
        ln, ev = hits[0]
        bad = reviews.check_evidence(ctx.store.root, d.disposition, d.evidence, reviewed_commit=ev.data.get("reviewed_commit"), head=head)
        if bad:
            problems += [f"{where} ({d.disposition} {d.finding}): {b}" for b in bad]
            continue
        out.append({
            "step_path": ev.step_path, "line": ln, "finding": d.finding, "evaluation_seq": ev.seq, "disposition": d.disposition,
            "evidence": d.evidence, "by": "worker", "provisional": True,
        })
    return out, problems


def _visible_lines(loc: groups.Located) -> list[str]:
    """Findings lines a step at ``loc`` was shown: its own gates', and its enclosing loops' judges'."""
    node = loc.node
    lines = [reviews.line_of(loc, i) for i, g in enumerate(node.gates) if isinstance(g, (FindingsGate, ReviewGate))]
    for f in loc.frames:
        if not f.group.repeat_until:
            continue
        for j in groups.judges(f.group):
            judge = next((c for c in f.group.steps if c.id == j), None)
            if isinstance(judge, Step):
                lines += [f"{f.instance_path}/{j}#{i}" for i, g in enumerate(judge.gates) if isinstance(g, (FindingsGate, ReviewGate))]
    return lines


def _line_matches(ctx: RunContext, line: str, spec: str) -> bool:
    """Whether a step named as an id or a step path recorded findings on ``line``."""
    base = line.split("#", 1)[0]
    if spec == base or spec == base.rsplit("/", 1)[-1]:
        return True
    loc = groups.locate(ctx.recipe, spec)
    return loc is not None and isinstance(loc.node, Step) and reviews.line_of(loc, int(line.rsplit("#", 1)[1])) == line


def _gate_result(ctx: RunContext, step_path: str, n: int, gate: int | str, passed: bool, data: dict[str, Any], advisory: bool) -> bool:
    """Record a gate's outcome, applying a pending waiver (§9.3); ``True`` when it counts as passed.

    A waiver covers the next evaluation of the gate whatever its outcome: a
    failure is recorded as ``gate_passed`` with ``waived`` (and the reasons it
    would have failed for), a pass with ``waiver_unused``.
    """
    log = ctx.log
    w = None if advisory else reviews.pending_waiver(log.events(), step_path, gate)
    if w is None:
        log.append("gate_passed" if passed else "gate_failed", step_path=step_path, attempt=n, data=data)
        return passed
    if passed:
        log.append("gate_passed", step_path=step_path, attempt=n, data={**data, "waiver_seq": w.seq, "waiver_unused": True})
    else:
        body = {k: v for k, v in data.items() if k != "reasons"}
        log.append("gate_passed", step_path=step_path, attempt=n, data={**body, "waived": True, "waiver_seq": w.seq, "waived_reasons": data.get("reasons") or []})
    return True


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
            data = {**base, **res.data, "reasons": res.reasons}
            if res.passed or gate.advisory:
                log.append("gate_passed" if res.passed else "gate_failed", step_path=step_path, attempt=n, data=data)
                continue
            if res.configuration_error:
                log.append("gate_failed", step_path=step_path, attempt=n, data=data)
                log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": "configuration", "reasons": res.reasons})
                return Outcome(step_path, n, "escalated", res.reasons)
            cls = None
            if not res.data.get("timed_out"):
                sha = res.data.get("output_sha256")
                cls = classify.classify_gate(res.data.get("exit_code"), ctx.log.cas.read(sha) if sha else b"")
            if cls is not None and cls["class"] != "subject":
                # The gate command could not run here: the platform's problem, not the step's (§8.8).
                log.append("gate_failed", step_path=step_path, attempt=n, data=data)
                log.append("failure_classified", step_path=step_path, attempt=n, data={**cls, "gate": i})
                reasons = [f"{cls['class']} failure ({cls['code']}) running gate {i}: {cls['message']}", *res.reasons]
                log.append("step_escalated", step_path=step_path, attempt=n, data={"reason": cls["class"], "code": cls["code"], "reasons": reasons})
                return Outcome(step_path, n, "escalated", reasons)
            if _gate_result(ctx, step_path, n, i, False, data, False):
                continue
            return _gate_failed(ctx, step_path, n, i, res.reasons)
        elif isinstance(gate, FindingsGate):
            loc = groups.locate(ctx.recipe, step_path)
            assert loc is not None
            sha = _registered(ctx, step_path, n).get("output_sha256")
            output = json.loads(ctx.log.cas.read(sha)) if sha else {}
            out = _evaluate(ctx, step_path, n, reviews.line_of(loc, i), gate, output if isinstance(output, dict) else {}, i,
                            _last_data(log.events(), "dispatched", step_path, n).get("head"))
            if out is None:
                continue
            return out
        elif isinstance(gate, ReviewGate):
            return _open_review(ctx, step, step_path, n, i)
        elif isinstance(gate, HumanGate):
            log.append("human_gate_opened", step_path=step_path, attempt=n, data={**base, "prompt": gate.prompt, "ref": step_path})
            return Outcome(step_path, n, "needs_human", [gate.prompt])
        else:  # pragma: no cover - every gate type is handled above
            raise EngineError("engine.unsupported_gate", f"unknown gate type {gate.type}")
    held = _triage_gate(ctx, step_path, n)
    if held is not None:
        return held
    from .frame import open_select_gate

    held = open_select_gate(ctx, step_path, n)
    if held is not None:
        return held
    data = _registered(ctx, step_path, n)
    loc = groups.locate(ctx.recipe, step_path)
    if loc is not None and groups.is_judge(loc):
        data["condition"] = {"gates_passed": True}
    log.append("step_passed", step_path=step_path, attempt=n, data=data)
    _apply_triage(ctx, step_path, n)
    if reviews.review_target(step) is not None:
        return _review_finished(ctx, step, step_path, n)
    ready = refresh(ctx)
    return Outcome(step_path, n, "passed", [], ready, _completed(ctx))


def _evaluate(
    ctx: RunContext, step_path: str, n: int, line: str, gate: FindingsGate | ReviewGate, output: dict[str, Any], i: int,
    reviewed_commit: str | None, extra: dict[str, Any] | None = None,
) -> Outcome | None:
    """Record one evaluation of a findings line and the gate's outcome; ``None`` to go on with later gates.

    A finding is open unless the owner accepted it as a risk at the previous
    evaluation and it is reported again (§9.2). The gate fails when an open
    finding has a ``block_on`` severity. ``coverage.complete: false`` marks
    the evaluation partial.
    """
    log = ctx.log
    data = reviews.evaluate(log.events(), line, output, gate.block_on)
    data["gate"] = i
    if reviewed_commit:
        data["reviewed_commit"] = reviewed_commit
    data.update(extra or {})
    log.append("findings_recorded", step_path=step_path, attempt=n, data=data)
    reasons = reviews.blocking_reasons(data)
    gdata = {"gate": i, "type": gate.type, "advisory": gate.advisory, "blocking": data["blocking"], "partial": data["partial"], "reasons": reasons}
    if _gate_result(ctx, step_path, n, i, not data["blocking"], gdata, gate.advisory) or gate.advisory:
        return None
    return _gate_failed(ctx, step_path, n, i, reasons)


def _open_review(ctx: RunContext, step: Step, step_path: str, n: int, i: int) -> Outcome:
    """A ``review`` gate (§9.1): the step waits in ``verifying`` while its review step is done.

    The review path (``<step_path>~review``) becomes ready; the Director picks
    a reviewer from ``eligible`` and dispatches it. A review left from an
    earlier attempt is marked stale first, so each attempt gets its own review.
    """
    log = ctx.log
    rpath = reviews.review_path(step_path, step, i)
    st = log.state().step(rpath).state
    if st in ("passed", "imported"):
        log.append("step_stale", step_path=rpath, data={"cause": "new_attempt", "review_of": step_path})
    elif st not in ("blocked_on_deps", "stale", "escalated"):
        raise EngineError("engine.review_busy", f"{rpath} is {st}; it cannot start a review of {step_path} attempt {n}")
    log.append("step_ready", step_path=rpath, data={"review_of": step_path, "attempt": n, "gate": i})
    return Outcome(step_path, n, "needs_review", [f"{rpath} is ready: dispatch a reviewer (see `baton eligible {ctx.run_id} {rpath}`)"], [rpath])


def _review_request(ctx: RunContext, rpath: str) -> tuple[str, int, int] | None:
    """``(step path, attempt, gate)`` the review at ``rpath`` was readied for."""
    ev = ctx.record().last("step_ready", rpath)
    while ev is not None and "review_of" not in ev.data:
        prior = [e for e in ctx.log.events() if e.type == "step_ready" and e.step_path == rpath and e.seq < ev.seq]
        ev = prior[-1] if prior else None
    if ev is None:
        return None
    return ev.data["review_of"], int(ev.data["attempt"]), int(ev.data["gate"])


def _review_finished(ctx: RunContext, review: Step, rpath: str, rn: int) -> Outcome:
    """The review step passed: its findings decide the reviewed step's gate, then that step goes on."""
    req = _review_request(ctx, rpath)
    target = reviews.review_target(review)
    assert target is not None
    parent, gi = target
    if req is None:  # pragma: no cover - a review is only readied by _open_review
        return Outcome(rpath, rn, "passed")
    ppath, pn, _ = req
    st = ctx.log.state().step(ppath)
    if st.state != "verifying" or st.attempt != pn:
        return Outcome(rpath, rn, "passed", [f"{ppath} attempt {pn} is no longer waiting for this review"])
    passed = ctx.record().last("step_passed", rpath, rn)
    output = json.loads(ctx.log.cas.read(passed.data["output_sha256"])) if passed and passed.data.get("output_sha256") else {}
    loc = groups.locate(ctx.recipe, ppath)
    assert loc is not None
    gate = parent.gates[gi]
    assert isinstance(gate, ReviewGate)
    events = ctx.log.events()
    reviewer = _last_data(events, "dispatched", rpath, rn).get("profile")
    out = _evaluate(
        ctx, ppath, pn, reviews.line_of(loc, gi), gate, output if isinstance(output, dict) else {}, gi,
        _last_data(events, "dispatched", rpath, rn).get("head"), {"review": rpath, "review_attempt": rn, "reviewer": reviewer},
    )
    if out is None:
        return _run_gates(ctx, parent, ppath, pn, gi + 1)
    return out


def _registered(ctx: RunContext, step_path: str, n: int) -> dict[str, Any]:
    submitted = ctx.record().last("result_submitted", step_path, n)
    return {k: submitted.data.get(k) for k in ("output_sha256", "artifacts")}


def _gate_failed(ctx: RunContext, step_path: str, n: int, gate: int | str, reasons: list[str]) -> Outcome:
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


def _gate_options(ctx: RunContext, path: str, gate: Any) -> list[dict[str, Any]]:
    """A human gate's options with labels: the implicit triage, protected and framing gates, or a recipe's gate."""
    if gate in ("triage", "protected"):
        return labels.options(gate, GATE_DECISIONS)
    if gate == "select":
        from .frame import FRAME_DECISIONS

        return labels.options("frame", FRAME_DECISIONS)
    over: dict[str, str] = {}
    if isinstance(gate, int):
        try:
            g = _step(ctx, path).gates[gate]
            if getattr(g, "labels", None) is not None:
                over = g.labels.model_dump(exclude_none=True)
        except (EngineError, IndexError):
            pass
    return labels.options("gate", GATE_DECISIONS, over)


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
        if st.state == "escalated" and reviews.split_review(path):
            req = _review_request(ctx, path)
            if req is None or ctx.log.state().step(req[0]).state != "verifying" or ctx.log.state().step(req[0]).attempt != req[1]:
                continue  # its step has moved on; the next attempt readies the review again
        if st.state == "awaiting_human":
            opened = record.last("human_gate_opened", path, st.attempt)
            out.append(
                {
                    "ref": path, "step_path": path, "attempt": st.attempt, "kind": "gate",
                    "prompt": opened.data["prompt"] if opened else "",
                    "options": _gate_options(ctx, path, opened.data.get("gate") if opened else None),
                }
            )
        elif st.state == "escalated":
            esc = record.last("step_escalated", path)
            d = esc.data if esc else {}
            entry = {
                "ref": path, "step_path": path, "attempt": st.attempt, "kind": "escalation",
                "reason": d.get("reason"), "reasons": d.get("reasons") or [],
                "questions": recorded_questions(d.get("questions")),
                "options": labels.options("blocked" if d.get("reason") == "blocked" else "escalation", ESCALATION_DECISIONS),
            }
            if d.get("reason") in ("platform", "unknown"):
                from .sme import incident_for

                inc = incident_for(ctx.store.project_log().events(), ctx.run_id, path, st.attempt)
                if inc is not None and inc["status"] == "open":
                    entry["incident"] = inc["id"]  # the step waits on the incident (§8.8)
            out.append(entry)
    if awaiting_baseline(ctx.log.events(), kind="adoption"):
        from .adopt import baseline_path

        bp = baseline_path(ctx.store.baton, ctx.run_id)
        if bp.is_file():
            out.append({
                "ref": "baseline", "step_path": None, "kind": "baseline", "path": bp.relative_to(ctx.store.root).as_posix(),
                "prompt": f"Review the adoption baseline ({bp.relative_to(ctx.store.root).as_posix()}), edit it if needed, then establish it",
                "options": [labels.option("baseline", "establish", command=f"baton establish-baseline {ctx.run_id} --note \"<your words>\"")],
            })
    for ipath, lim in view.pending_limits():
        d = lim.data
        out.append(
            {
                "ref": ipath, "step_path": ipath, "kind": "iteration_limit", "iteration": d.get("iteration"),
                "max_iterations": d.get("max_iterations"), "reason": "iteration_limit",
                "reasons": [f"{ipath} reached {d.get('max_iterations')} iterations without meeting its exit condition", *(d.get("reasons") or [])],
                "options": labels.options("iteration_limit", ESCALATION_DECISIONS),
            }
        )
    out += skip_notices(ctx)
    if ctx.log.state().state == "active":
        from . import publish

        out += publish.pending(ctx)
    return out


def decide(
    ctx: RunContext, ref: str, decision: str, note: str = "", *, actor: str = "human", recorded_by: str | None = None,
    path: str | None = None, answers: Any = None, partial: bool = False,
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
    if ref.startswith("skip:"):
        return _decide_skip_notice(ctx, ref, decision, note, actor, extra)
    if ref.startswith(("publish:", "drift:")):
        return _decide_deliverable(ctx, ref, decision, note, actor, extra, path)
    if path is not None:
        raise EngineError("decide.bad_decision", "--path is only for a publish conflict (alternate)")
    if answers is not None or partial:
        return _decide_answers(ctx, ref, decision, note, actor, extra, answers, partial)
    if "#" in ref:
        return _decide_finding(ctx, ref, decision, note, actor, extra)
    if groups.locate_instance(ctx.recipe, ref) is not None:
        return _decide_iteration_limit(ctx, ref, decision, note, actor, extra)
    current = log.state().step(ref)
    if current.state == "escalated":
        return _decide_escalation(ctx, ref, decision, note, actor, extra)
    if current.state == "stale":
        return _decide_stale(ctx, ref, decision, note, actor, extra)
    opened_gate = None
    if current.state == "awaiting_human":
        o = ctx.record().last("human_gate_opened", ref, current.attempt)
        opened_gate = o.data.get("gate") if o else None
    if opened_gate == "select" and decision != "reject":
        raise EngineError("decide.bad_decision", f"{ref} waits on the owner's selection: decide select --items <ids>, or reject")
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
    if gate_index == "triage":  # the implicit approval of a triage result (§5.5)
        return _decide_triage(ctx, step, ref, n, decision, note)
    if gate_index == "select":  # a framing run's implicit selection (§11.6); select itself goes through frame.select
        reasons = [f"the owner did not accept the breakdown: {note}" if note else "the owner did not accept the breakdown"]
        log.append("gate_failed", step_path=ref, attempt=n, data={"gate": "select", "type": "select", "implicit": True, "reasons": reasons})
        return _failed(ctx, ref, n, reasons)
    if gate_index == "protected":  # the implicit protected gate in warn mode (§9.4)
        base: dict[str, Any] = {"gate": "protected", "type": "protected", "implicit": True}
        if decision == "approve":
            log.append("gate_passed", step_path=ref, attempt=n, data={**base, "approved": True})
            return _run_gates(ctx, step, ref, n, 0)
        reasons = [f"the owner did not accept the change to protected paths: {note}" if note else "the owner did not accept the change to protected paths"]
        log.append("gate_failed", step_path=ref, attempt=n, data={**base, "reasons": reasons})
        return _gate_failed(ctx, ref, n, "protected", reasons)
    base = {"gate": gate_index, "type": "human", "advisory": step.gates[gate_index].advisory}
    if decision == "approve":
        log.append("gate_passed", step_path=ref, attempt=n, data=base)
        return _run_gates(ctx, step, ref, n, gate_index + 1)
    reasons = [f"the owner did not approve: {note}" if note else "the owner did not approve"]
    log.append("gate_failed", step_path=ref, attempt=n, data={**base, "reasons": reasons})
    if step.gates[gate_index].advisory:
        return _run_gates(ctx, step, ref, n, gate_index + 1)
    return _gate_failed(ctx, ref, n, gate_index, reasons)


def _decide_deliverable(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any], path: str | None) -> Outcome:
    """A publish conflict (overwrite | keep | alternate) or drift (leave), §10.4, §10.5."""
    from . import publish

    if ref.startswith("publish:"):
        res = publish.decide_conflict(ctx, ref, decision, note, actor, extra, path)
    else:
        if path is not None:
            raise EngineError("decide.bad_decision", "--path is only for a publish conflict (alternate)")
        res = publish.decide_drift(ctx, ref, decision, note, actor, extra)
    sp = ref.split(":", 1)[1].rsplit(".", 1)[0]
    ready = refresh(ctx)
    return Outcome(sp, ctx.log.state().step(sp).attempt, "recorded", [f"{decision}: {res.get('path') or ''}".rstrip(": ")], ready, _completed(ctx))


FINDING_DECISIONS = ("accept-risk",)
SKIP_DECISIONS = ("acknowledge",)


def skip_notices(ctx: RunContext) -> list[dict[str, Any]]:
    """Reports of a blocking gate or approval skipped outside Baton (§12.4) not yet acknowledged by the owner."""
    acked = {e.data.get("ref") for e in ctx.log.events() if e.type == "human_decision" and e.data.get("kind") == "skip_notice"}
    plog = ctx.store.project_log().events()
    texts = {e.seq: e.data for e in plog if e.type == "process_feedback"}
    out = []
    for e in plog:
        if e.type == "step_skip_recorded" and e.data.get("run") == ctx.run_id and e.data.get("surfaced") and f"skip:{e.seq}" not in acked:
            fb = texts.get(e.data.get("feedback_seq"), {})
            gate = e.data.get("gate")
            what = f"gate {gate} of {e.data.get('step_path')}" if gate is not None else f"step {e.data.get('step_path')}"
            out.append({
                "ref": f"skip:{e.seq}", "step_path": e.data.get("step_path"), "kind": "skip_notice",
                "prompt": f"Reported: {what} was skipped outside Baton: {fb.get('text', '')}"
                          + (" (the owner was told at the time)" if e.data.get("informed_owner") else ""),
                "options": labels.options("skip_notice", SKIP_DECISIONS),
            })
    return out


def _gate_index(step: Step, spec: str) -> int:
    """A declared gate named by index, or by type when the step declares exactly one of it."""
    s = str(spec).strip()
    if s.isdigit() and int(s) < len(step.gates):
        return int(s)
    hits = [i for i, g in enumerate(step.gates) if g.type == s]
    if len(hits) != 1:
        raise EngineError("feedback.unknown_gate", f"{step.id} has no single gate {s!r}; name it by index (0-{len(step.gates) - 1}) or a type it declares once")
    return hits[0]


def _decide_skip_notice(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any]) -> Outcome:
    if decision not in SKIP_DECISIONS:
        raise EngineError("decide.bad_decision", f"{ref} is a skip notice; decision must be one of {SKIP_DECISIONS}, got {decision!r}")
    notice = next((n for n in skip_notices(ctx) if n["ref"] == ref), None)
    if notice is None:
        raise EngineError("decide.nothing_pending", f"{ref} is not a pending skip notice of run {ctx.run_id}")
    ctx.log.append("human_decision", actor=actor, data={"ref": ref, "kind": "skip_notice", "decision": "acknowledge", "note": note,
                                                         "step_path": notice["step_path"], **extra})
    return Outcome(notice["step_path"] or ref, 0, "recorded", [f"{ref} acknowledged"])
STALE_DECISIONS = ("confirm",)


def stale_runnable(ctx: RunContext, path: str, view: groups.View | None = None) -> str | None:
    """Why a ``stale`` step cannot be re-run or confirmed yet, or ``None`` when it is runnable (§8.1)."""
    view = view or view_of(ctx)
    if view.rs.step(path).state != "stale":
        return f"{path} is {view.rs.step(path).state}, not stale"
    loc = groups.locate(ctx.recipe, path)
    if loc is None:
        return f"{path} is not a step of {ctx.recipe.recipe.ref}"
    why = view.live_reason(path)
    if why:
        return why
    if not view.deps_met(loc.node, loc.frame):
        unmet = [d for d in loc.node.depends_on if view.state(groups.child_path(loc.frame, d)) not in SATISFIES_DEPS]
        return f"its dependencies are not satisfied again yet: {', '.join(unmet)}"
    return None


def _decide_stale(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any]) -> Outcome:
    """The owner confirms a stale step unchanged: its earlier accepted result stands (§8.1, §8.9)."""
    if decision not in STALE_DECISIONS:
        raise EngineError("decide.bad_decision", f"{ref} is stale; the owner may {STALE_DECISIONS[0]!r} it unchanged (or dispatch it to re-run), got {decision!r}")
    why = stale_runnable(ctx, ref)
    if why:
        raise EngineError("decide.stale_not_runnable", f"{ref} cannot be confirmed yet: {why}")
    log = ctx.log
    n = log.state().step(ref).attempt
    prev = next(e for e in reversed(log.events()) if e.step_path == ref and e.type in ("step_passed", "step_imported"))
    hd = log.append(
        "human_decision", actor=actor, step_path=ref, attempt=None,
        data={"ref": ref, "kind": "stale", "decision": decision, "note": note, **extra},
    )
    data = {k: v for k, v in prev.data.items() if k != "confirmed"}
    data["confirmed"] = {"decision_seq": hd.seq, "previous_seq": prev.seq}
    log.append("step_passed", step_path=ref, attempt=n or None, data=data)
    ready = refresh(ctx)
    return Outcome(ref, n, "confirmed", [note] if note else [], ready, _completed(ctx))


def _finding_ref(ctx: RunContext, step_path: str, finding: str) -> tuple[Any, dict[str, Any]]:
    """``(findings_recorded event, finding)`` for a finding recorded on ``step_path`` (``F1`` or ``<gate>:F1``).

    Only the latest evaluation of a line can be dispositioned: a later review
    has superseded an earlier one.
    """
    gate = None
    fid = finding
    if ":" in finding and finding.split(":", 1)[0].isdigit():
        g, fid = finding.split(":", 1)
        gate = int(g)
    events = ctx.log.events()
    evs = [e for e in events if e.type == "findings_recorded" and e.step_path == step_path and (gate is None or e.data.get("gate") == gate)
           and any(f["id"] == fid for f in e.data.get("findings") or [])]
    if not evs:
        raise EngineError("disposition.unknown_finding", f"no finding {fid!r} was recorded on {step_path}" + (f" by gate {gate}" if gate is not None else ""))
    lines = {e.data["line"] for e in evs}
    if len(lines) > 1:
        raise EngineError("disposition.ambiguous_finding", f"{fid!r} was recorded on {step_path} by several gates; name it as <gate>:{fid}")
    ev = evs[-1]
    latest = reviews.latest_evaluation(events, ev.data["line"])
    if latest is not None and latest.seq != ev.seq:
        raise EngineError("disposition.superseded", f"finding {fid!r} of {step_path} was reviewed again since (at {latest.step_path}); disposition the latest review's findings")
    return ev, next(f for f in ev.data["findings"] if f["id"] == fid)


def _decide_finding(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any]) -> Outcome:
    """The owner accepts a finding as a risk (``<step_path>#<finding>``, decision ``accept-risk``, §9.2)."""
    step_path, finding = ref.split("#", 1)
    if decision not in FINDING_DECISIONS:
        raise EngineError("decide.bad_decision", f"{ref} is a finding; decision must be one of {FINDING_DECISIONS}, got {decision!r}")
    ev, f = _finding_ref(ctx, step_path, finding)
    log = ctx.log
    decision_id = f"d{log.state().last_seq + 1}"
    log.append(
        "human_decision", actor=actor, step_path=step_path,
        data={"ref": ref, "kind": "finding", "decision": "accepted-risk", "note": note, "decision_id": decision_id, "finding": f["id"], **extra},
    )
    log.append(
        "finding_dispositioned", actor=actor, step_path=step_path,
        data={"line": ev.data["line"], "finding": f["id"], "evaluation_seq": ev.seq, "disposition": "accepted-risk", "decision_id": decision_id, "by": "owner"},
    )
    return Outcome(step_path, ev.attempt or 0, "recorded", [f"{f['id']} accepted as a risk ({decision_id})"])


def disposition(
    ctx: RunContext, step_path: str, finding: str, value: str, evidence: str | None = None, *, actor: str = "director"
) -> Outcome:
    """Record a disposition of a finding (§9.2): the Director relaying evidence, or an owner decision.

    ``fixed`` needs a commit or ``file:line``; ``rejected`` a ``file:line`` at the
    reviewed commit or a test reference; ``accepted-risk`` the id of the owner's
    decision accepting that finding (``decide <step>#<finding> accept-risk``).
    A disposition takes effect at the next evaluation of the finding's line:
    the next review re-reporting a ``fixed`` or ``rejected`` finding reopens it.
    """
    if value not in reviews.DISPOSITIONS:
        raise EngineError("disposition.bad_value", f"disposition must be one of {reviews.DISPOSITIONS}, got {value!r}")
    ev, f = _finding_ref(ctx, step_path, finding)
    data: dict[str, Any] = {"line": ev.data["line"], "finding": f["id"], "evaluation_seq": ev.seq, "disposition": value}
    if value == "accepted-risk":
        dec = ctx.record().decision((evidence or "").strip())
        if dec is None or dec.data.get("kind") != "finding" or dec.step_path != step_path or dec.data.get("finding") != f["id"]:
            raise EngineError(
                "disposition.needs_owner_decision",
                f"accepted-risk needs the owner's decision on this finding: record it with `baton decide {ctx.run_id} '{step_path}#{f['id']}' accept-risk --note \"<the owner's words>\"`",
            )
        data.update(decision_id=dec.data["decision_id"], by="owner")
    else:
        bad = reviews.check_evidence(ctx.store.root, value, evidence, reviewed_commit=ev.data.get("reviewed_commit"), head=reviews.repo_head(ctx.store.root))
        if bad:
            raise EngineError("disposition.bad_evidence", f"{value} {f['id']} refused: " + "; ".join(bad))
        data.update(evidence=evidence, by="director", provisional=False)
    ctx.log.append("finding_dispositioned", actor=actor, step_path=step_path, data=data)
    return Outcome(step_path, ev.attempt or 0, "recorded", [f"{f['id']} {value}"])


def waive(ctx: RunContext, step_path: str, gate: str, reason: str, *, actor: str = "human", recorded_by: str | None = None) -> Outcome:
    """Waive one occurrence of a gate on one step (§9.3); the reason is the owner's decision, verbatim.

    Covers the failed occurrence the step still holds (an escalated step whose
    last attempt failed this gate: the step goes on with its later gates; a
    judge at its iteration limit: the iteration goes on as if the judge had
    passed), else the next occurrence (a pending waiver, consumed by the next
    evaluation of the gate, or for ``independence`` by the next dispatch).
    """
    if not reason.strip():
        raise EngineError("waive.reason_required", "a waiver needs the owner's reason")
    loc = groups.locate(ctx.recipe, step_path)
    if loc is None or not isinstance(loc.node, Step):
        raise EngineError("engine.unknown_step", f"{step_path} is not a step of {ctx.recipe.recipe.ref}")
    step = loc.node
    g = reviews.resolve_gate(step, gate)
    log = ctx.log
    rs = log.state()
    st = rs.step(step_path)
    record = ctx.record()
    held = None
    if g != "independence" and st.state == "escalated":
        esc = record.last("step_escalated", step_path, st.attempt)
        failed = [e for e in record.attempt_events(step_path, st.attempt) if e.type == "gate_failed" and not e.data.get("advisory")]
        if esc is not None and esc.data.get("reason") == "attempts_exhausted" and failed and failed[-1].data.get("gate") == g:
            held = "escalated"
    elif g != "independence" and st.state == "passed" and groups.is_judge(loc):
        cond = groups.View(ctx.recipe, log.events(), rs, log.cas).condition(step_path) or {}
        lim = None
        if cond.get("gates_passed") is False and cond.get("gate") == g:
            assert loc.frame is not None
            f = loc.frame
            lim = view_of(ctx).pending_limit(f.group, f.group_path, f.instance)
        if lim is not None and lim.data.get("judged") == step_path:
            level = record.level()
            later = [i for i, x in enumerate(step.gates) if isinstance(g, int) and i > g and gate_included(x, level) and not x.advisory and not isinstance(x, SchemaGate)]
            if later:
                raise EngineError("waive.later_gates", f"gates {later} of {step_path} never ran after gate {g} failed; decide {f.instance_path} retry instead")
            held = "judge"
    if held is None and reviews.pending_waiver(log.events(), step_path, g) is not None:
        raise EngineError("waive.already_pending", f"{step_path} already has a pending waiver of gate {g}")
    decision_id = f"d{rs.last_seq + 1}"
    log.append(
        "human_decision", actor=actor, step_path=step_path,
        data={"ref": step_path, "kind": "waiver", "gate": g, "decision": "waive", "note": reason, "decision_id": decision_id, **({"recorded_by": recorded_by} if recorded_by else {})},
    )
    base = {"gate": g, "reason": reason, "decision_id": decision_id}
    if held == "escalated":
        n = st.attempt
        log.append("gate_waived", actor=actor, step_path=step_path, data={**base, "scope": "held", "attempt": n})
        log.append("verification_started", step_path=step_path, attempt=n, data={"after_waiver": decision_id})
        if g == "protected":
            return _run_gates(ctx, step, step_path, n, 0)
        assert isinstance(g, int)
        return _run_gates(ctx, step, step_path, n, g + 1)
    if held == "judge":
        judged = ctx.record().last("step_passed", step_path)
        log.append("gate_waived", actor=actor, step_path=step_path, data={**base, "scope": "held", "attempt": st.attempt, "judged_seq": judged.seq})
        ready = refresh(ctx)
        return Outcome(step_path, st.attempt, "waived", [reason], ready, _completed(ctx))
    log.append("gate_waived", actor=actor, step_path=step_path, data={**base, "scope": "next"})
    return Outcome(step_path, st.attempt, "waiver_pending", [f"the next {g if isinstance(g, str) else f'evaluation of gate {g}'} of {step_path} is waived"])


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
    if _is_triage(ctx, step_path):
        raise EngineError("revise.triage", f"{step_path} is the triage step; change the level with `retriage` instead")
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



def check_answers(questions: list[dict[str, Any]], answers: Any, partial: bool) -> list[dict[str, Any]]:
    """The owner's confirmed answers to a ``blocked`` step's questions (§13.8), checked; raises ``EngineError``.

    Each answer is ``{id, answer, owner_words}``: ``answer`` the confirmed restatement (a string, or a list
    of strings for a multi-select question), ``owner_words`` what the owner said for it, including the
    confirmation. Every id must name one of the step's last questions, once; every ``needed`` question
    must be answered unless ``partial``.
    """
    if not isinstance(answers, list):
        raise EngineError("answers.invalid", "answers must be a JSON list of {id, answer, owner_words}")
    known = {q["id"]: q for q in questions}
    problems: list[str] = []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for n, a in enumerate(answers, start=1):
        if not isinstance(a, dict):
            problems.append(f"answer {n} is not an object {{id, answer, owner_words}}")
            continue
        extra_keys = sorted(set(a) - {"id", "answer", "owner_words"})
        if extra_keys:
            problems.append(f"answer {n}: unknown keys {', '.join(extra_keys)}")
        qid = a.get("id")
        if not isinstance(qid, str) or qid not in known:
            problems.append(f"answer {n}: {qid!r} is not one of the step's questions ({', '.join(known) or 'none'})")
            continue
        if qid in seen:
            problems.append(f"answer {n}: question {qid} is answered more than once")
            continue
        seen.add(qid)
        ans = a.get("answer")
        ok = (isinstance(ans, str) and ans.strip()) or (
            isinstance(ans, list) and ans and all(isinstance(x, str) and x.strip() for x in ans))
        if not ok:
            problems.append(f"answer {n} ({qid}): answer must be a non-empty string (or list of strings)")
        words = a.get("owner_words")
        if not isinstance(words, str) or not words.strip():
            problems.append(f"answer {n} ({qid}): owner_words is required: quote what the owner said, including the confirmation")
        out.append({"id": qid, "answer": ans, "owner_words": words})
    missing = [q["id"] for q in questions if q.get("priority", "needed") == "needed" and q["id"] not in seen]
    if missing and not partial:
        problems.append(f"needed questions not answered: {', '.join(missing)} (pass --partial to record a deliberately partial set)")
    if problems:
        raise EngineError("answers.invalid", "; ".join(problems))
    return out


def _decide_answers(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any],
                    answers: Any, partial: bool) -> Outcome:
    """``decide <run> <step> retry --answers <file>``: the owner's confirmed answers to a blocked step (§13.8)."""
    from .models import recorded_questions

    if answers is None:
        raise EngineError("decide.bad_decision", "--partial goes with --answers")
    if decision != "retry":
        raise EngineError("decide.bad_decision", f"answers go with retry, got {decision!r}")
    log = ctx.log
    st = log.state().step(ref)
    esc = ctx.record().last("step_escalated", ref) if st.state == "escalated" else None
    if esc is None or esc.data.get("reason") != "blocked":
        raise EngineError("decide.nothing_pending", f"{ref} is not waiting on answers to its questions (it is {st.state})")
    if not note.strip():
        raise EngineError("decide.note_required", "--note is required: the owner's words")
    checked = check_answers(recorded_questions(esc.data.get("questions")), answers, partial)
    n = st.attempt
    decision_id = f"d{log.state().last_seq + 1}"
    log.append(
        "human_decision", actor=actor, step_path=ref, attempt=n,
        data={"ref": ref, "kind": "answers", "decision": "retry", "answers": checked, "note": note, "decision_id": decision_id,
              **({"partial": True} if partial else {}), **extra},
    )
    log.append("step_ready", step_path=ref, data={"after_decision": True})
    return Outcome(ref, n, "retry", [f"{len(checked)} answer(s) recorded ({decision_id})"])


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
    req = _review_request(ctx, ref) if reviews.split_review(ref) else None
    if req is not None and log.state().step(req[0]).state == "verifying" and log.state().step(req[0]).attempt == req[1]:
        # Abandoning a review fails the reviewed step's gate; the review stays escalated
        # (it is readied again by the step's next attempt).
        ppath, pn, gi = req
        reasons = [f"the owner abandoned the review {ref}" + (f": {note}" if note else "")]
        node = _step(ctx, ppath)
        log.append("gate_failed", step_path=ppath, attempt=pn, data={"gate": gi, "type": "review", "advisory": node.gates[gi].advisory, "reasons": reasons})
        if node.gates[gi].advisory:
            return _run_gates(ctx, node, ppath, pn, gi + 1)
        return _gate_failed(ctx, ppath, pn, gi, reasons)
    log.append("step_abandoned", step_path=ref, data={"note": note})
    return Outcome(ref, n, "abandoned", [note] if note else [])


def apply_baseline(ctx: RunContext, item: dict[str, Any], *, adoption: str, decision_id: str) -> Outcome:
    """Apply one work item of an established baseline to its run (§11.5).

    Records ``baseline_established`` (with the seeds, stored in this run's CAS),
    ``complexity_set`` at the baseline's level, then lets ``refresh`` skip,
    import and ready steps in dependency order. ``create: false`` abandons the run.
    """
    from .adopt import _project_file

    log = ctx.log
    if not awaiting_baseline(log.events()):
        raise EngineError("baseline.applied", f"run {ctx.run_id} has no pending baseline")
    if not item.get("create", True):
        log.append("baseline_established", actor="human", data={"adoption": adoption, "decision_id": decision_id, "create": False})
        log.append("run_abandoned", actor="human", data={"reason": f"left out by the adoption baseline ({adoption}, {decision_id})"})
        return Outcome("", 0, "abandoned")
    cas = log.cas
    root = ctx.store.root
    attested = {"adoption": adoption, "decision_id": decision_id}
    waivers: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for w in item.get("waivers") or []:
        waivers.setdefault((w["step"], w.get("item")), []).append({"gate": w["gate"], "reason": w["reason"], "decision_id": decision_id})
    seeds = []
    for e in item.get("seeds") or []:
        if not e.get("import"):
            continue
        node = node_for(ctx.recipe, e["step"].split("/", 1)[0])
        if isinstance(node, Group):
            node = next(n for n in node.steps if n.id == e["step"].split("/", 1)[1])
        data: dict[str, Any] = {"output_sha256": cas.put(canonical_json(e.get("output")).encode("utf-8")) if "output" in e else None, "artifacts": {}}
        for name, a in sorted((e.get("artifacts") or {}).items()):
            p = _project_file(root, a["path"])
            assert p is not None  # checked by check_baseline
            decl = next((x for x in node.artifacts if x.name == name), None)
            entry = {"sha256": cas.put_file(p), "filename": PurePosixPath(a["path"]).name, "source": a["path"]}
            if decl is not None and decl.media_type:
                entry["media_type"] = decl.media_type
            data["artifacts"][name] = entry
        evidence = []
        for x in e.get("evidence") or []:
            p = _project_file(root, x["path"])
            evidence.append({"path": x["path"], "sha256": cas.put_file(p) if p is not None else x["sha256"]})
        data.update(evidence=evidence, gates=e.get("gates") or [], attested=attested)
        wv = waivers.get((e["step"], e.get("item")))
        if wv:
            data["waivers"] = wv
        seeds.append({"step": e["step"], **({"item": e["item"]} if e.get("item") is not None else {}), "data": data})
    level = item.get("level")
    log.append("baseline_established", actor="human", data={"adoption": adoption, "decision_id": decision_id, "level": level, "seeds": seeds})
    if level is not None:
        cs: dict[str, Any] = {"level": level, "approval": "baseline", "decision_id": decision_id}
        if item.get("level_reasons"):
            cs["reasons"] = list(item["level_reasons"])
        cx = ctx.recipe.recipe.complexity
        log.append("complexity_set", step_path=cx.triage_step if cx else None, data=cs)
    ready = refresh(ctx)
    return Outcome("", 0, "baseline_established", [], ready, _completed(ctx))


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
    def init(root: str | Path, *, agents_md: bool = True, bare: bool = False) -> dict[str, Any]:
        from .project import init

        return init(root, agents_md=agents_md, bare=bare)

    def close(self) -> None:
        self.project.store.close()

    # -- helpers ------------------------------------------------------------

    def _leases(self, ctx: RunContext) -> Any:
        from .locks import Leases

        return Leases(ctx.log, self.director, self.project.branch(), self.project.config.leases.minutes)

    def _ctx(self, run_id: str) -> RunContext:
        return self.project.context(run_id)

    def _mutate(self, run_id: str, body: Any, *, allow_closed: bool = False, extra: list[Path] | None = None) -> dict[str, Any]:
        """Hold the lease, run ``body(ctx) -> dict``, then write records and checkpoint.

        ``extra``: further paths (filled in by ``body``) the checkpoint commits with this run's.
        """
        with self._run_lock(run_id):
            ctx = self._ctx(run_id)
            if not allow_closed and ctx.log.state().state != "active":
                raise EngineError("run.closed", f"run {run_id} is {ctx.log.state().state}")
            leases = self._leases(ctx)
            leases.ensure()
            before = ctx.log.state().last_seq
            out = body(ctx) or {}
            self._after(ctx, leases, before, out, extra)
            return out

    def _run_lock(self, run_id: str) -> Any:
        from .locks import run_lock

        return run_lock(self.project.baton, run_id)

    def _after(self, ctx: RunContext, leases: Any, before: int, out: dict[str, Any], extra: list[Path] | None = None) -> None:
        from . import docs, publish

        if ctx.log.state().state == "active":
            publish.record_drift(ctx)  # drift is recorded by mutating calls only (§10.5)
            refresh(ctx)  # a conflict or drift the owner settled on disk no longer holds the run
        if ctx.log.state().state in ("completed", "abandoned") and leases.current() is not None:
            leases.release(actor="runtime")
        self._open_incidents(ctx, [e for e in ctx.log.events() if e.seq > before])
        paths = list(extra or []) + publish.deliverable_paths(ctx) + self._adoption_progress(ctx) + self._project_paths()
        docs.write_records(ctx)
        new = [e for e in ctx.log.events() if e.seq > before]
        cp = self._checkpoint(ctx, new, paths)
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        pending = pending_decisions(ctx)
        out["pending_decisions"] = pending
        out["needs_owner"] = bool(pending)

    def _checkpoint(self, ctx: RunContext, new: list[Any], extra: list[Path] | None = None) -> Any:
        from . import docs, gitops

        triggers = [e for e in new if e.type in CHECKPOINT_TRIGGERS]
        if not triggers:
            return None
        if not self.project.config.checkpoints.commit:
            return gitops.Checkpoint(False, reason="checkpoint commits are off in project.yaml")
        from .locks import project_lock

        # Under the project lock: another run's checkpoint cannot stage its files
        # between this preflight and this commit (§8.9).
        with project_lock(self.project.baton):
            pf = gitops.preflight(self.project.root, [ctx.run_dir, *(extra or [])])
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

    def vendor(self, src: str | Path, *, approved: bool = False, note: str | None = None) -> dict[str, Any]:
        """Vendor a recipe package. A version that changes a kept step id's signature or reuses a retired
        id (§5.8) returns ``needs_owner`` with its flags; the owner's approval is the same call with
        ``approved`` and their words, recorded as ``human_decision {kind: vendor}`` and in the lock entry."""
        from . import sme
        from .locks import project_lock
        from .project import vendor

        out = vendor(self.project, src)
        if not out["needs_owner"] or not approved:
            return out
        if not (note or "").strip():
            raise EngineError("vendor.note", "an approval needs the owner's words (--note), recorded verbatim")
        with project_lock(self.project.baton):
            decision_id = f"d{len(self.project.store.project_log().events()) + 1}"
        sme.project_append(self.project, "human_decision", {"kind": "vendor", "recipe": out["recipe"], "decision": "approve",
                                                            "note": note, "decision_id": decision_id, "flags": out["flags"]}, actor="human")
        out = vendor(self.project, src, decision={"decision_id": decision_id, "note": note})
        out["decision_id"] = decision_id
        cp = self._project_checkpoint(f"vendoring {out['recipe']} approved")
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        return out

    # -- versioning (§14) -----------------------------------------------------

    def _commit_paths(self, subject: str, paths: list[Path]) -> Any:
        """One commit of exactly ``paths`` (outside any run's checkpoint), under the project lock."""
        from . import gitops
        from .locks import project_lock

        if not self.project.config.checkpoints.commit:
            return gitops.Checkpoint(False, reason="checkpoint commits are off in project.yaml")
        with project_lock(self.project.baton):
            pf = gitops.preflight(self.project.root, [p for p in paths if p.exists()])
            if isinstance(pf, str):
                return gitops.Checkpoint(False, reason=pf)
            top, rels = pf
            try:
                sha = gitops.commit(top, rels, subject, [])
            except gitops.GitError as e:
                return gitops.Checkpoint(False, subject=subject, reason=str(e))
        return gitops.Checkpoint(sha is not None, sha, subject, None if sha else "nothing to commit")

    def upgrade(self, to: str | None = None) -> dict[str, Any]:
        """Pin this runtime in baton.lock and re-vendor the skills, in one commit (§14.3).

        ``to`` must be this runtime's version: the launcher runs ``upgrade --to <v>`` under ``<v>``.
        """
        from .project import LOCK_FILE, SKILLS, SKILLS_DIR

        out = versions.upgrade_lock(self.project, to)
        if out["changed"]:
            paths = [self.project.baton / LOCK_FILE] + [self.project.root / SKILLS_DIR / n / "SKILL.md" for n in SKILLS]
            cp = self._commit_paths(f"baton(project): upgrade runtime {out['previous']} -> {out['runtime']}", paths)
            out["checkpoint"] = cp.as_dict()
        return out

    def migrate(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Bring stored files below the readable window to the current formats (§14.2).

        Explicit and previewable: ``dry_run`` reports the plan and writes nothing. Never rewrites
        an event; recorded as ``migrated``; committed on its own (``baton(migrate): …``).
        """
        from .locks import project_lock
        from .supervisor import running_dir

        plan = versions.migration_plan(self.project)
        out: dict[str, Any] = {"dry_run": dry_run, **plan, "migrated": False}
        if plan["problems"]:
            raise EngineError("migrate.unreadable", "migration cannot help: " + "; ".join(plan["problems"]))
        if dry_run or not plan["items"]:
            if not plan["items"]:
                out["message"] = "nothing to migrate: every stored file is readable by this runtime"
            return out
        rd = running_dir(self.project.baton)
        if rd.is_dir() and any(rd.glob("*.json")):
            raise EngineError("migrate.in_flight", "workers are running; migrate once they finish (`baton board` shows them)")
        with project_lock(self.project.baton):
            paths = versions.apply_migration(self.project, plan)
        summary = ", ".join(sorted({i["family"] for i in plan["items"]}))
        cp = self._commit_paths(f"baton(migrate): {len(plan['items'])} file(s) to current formats ({summary})", paths)
        out.update(migrated=True, checkpoint=cp.as_dict())
        return out

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
        limit = self.project.config.limits.active_runs
        if limit is not None:
            active = [r for r in self.project.store.run_ids() if self.project.store.run(r).state().state == "active"]
            if len(active) >= limit:
                raise EngineError("limits.active_runs", f"{len(active)} runs are active and project.yaml limits.active_runs is {limit}; finish or abandon one first ({', '.join(active)})")
        from . import publish

        missing = publish.missing_path_keys(loaded.recipe, self.project.config.paths)
        if missing:
            raise EngineError("configuration.publish_path", f"{loaded.recipe.ref} publishes to paths.{', paths.'.join(missing)}, which project.yaml does not map; add them under paths:")
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

    def board(self, *, needs_me: bool = False) -> dict[str, Any]:
        """Every non-terminal run (§8.9): position, running and queued work, pending decisions, lease holder.

        ``needs_me`` keeps only runs with a pending owner decision.
        """
        from . import locks

        runs: list[dict[str, Any]] = []
        for rid in self.project.store.run_ids():
            try:
                st = self.status(rid)
            except (EngineError, StoreError) as e:
                runs.append({"run_id": rid, "error": str(e), "code": getattr(e, "code", "store.error")})
                continue
            if st["state"] != "active" or (needs_me and not st["needs_owner"]):
                continue
            runs.append({
                "run_id": rid, "title": st["title"], "recipe": st["recipe"], "level": st["level"],
                "position": _position(st), "groups": {g: i["summary"] for g, i in st["groups"].items()},
                "ready": st["ready"], "stale": [s["step_path"] for s in st["stale"]],
                "running": [{k: r.get(k) for k in ("step_path", "attempt", "profile", "dispatch_id", "deadline")}
                            | ({"alive": r["liveness"].get("supervisor_alive"), "overdue": r["liveness"].get("overdue")} if r.get("liveness") else {})
                            for r in st["running"]],
                "queued": st["queued"], "pending_decisions": st["pending_decisions"], "needs_owner": st["needs_owner"],
                "lease": st["lease"],
            })
        holder = locks.workspace_holder(self.project.baton)
        ws = {"holder": {k: holder.get(k) for k in ("run_id", "step_path", "dispatch_id", "attempt") if k in holder} if holder else None,
              "queued": len(locks.read_queue(self.project.baton))}
        from .sme import incidents

        open_inc = [{k: i.get(k) for k in ("id", "run", "step_path", "attempt", "class", "code", "message")}
                    for i in incidents(self.project.store.project_log().events()).values() if i["status"] == "open"]
        return {"runs": runs, "workspace": ws, "incidents": open_inc, "needs_owner": any(r.get("needs_owner") for r in runs)}

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
                for gi in reviews.review_gate_indices(node):
                    rpath = reviews.review_path(node.id, node, gi)
                    if rpath in rs.steps:
                        steps[rpath] = {"state": rs.steps[rpath].state, "attempt": rs.steps[rpath].attempt, "review_of": node.id}
        latest: dict[str, Any] = {}
        for e in events:
            if e.type == "findings_recorded":
                latest[e.data.get("line")] = e
        findings = []
        for ln, e in sorted(latest.items(), key=lambda kv: kv[1].seq):
            now_open = [f["id"] for f in reviews.effective(events, e) if f.get("status") == "open"]
            entry = {"line": ln, "step_path": e.step_path, "attempt": e.attempt, "open": now_open,
                     "blocking": [i for i in e.data.get("blocking") or [] if i in now_open], "partial": bool(e.data.get("partial"))}
            if now_open or entry["partial"]:
                findings.append(entry)
        def deps_now(p: str) -> bool:
            # A ready step whose dependencies are no longer met (a re-triage brought an
            # upstream step back, or one is being re-triaged) waits; dispatch refuses it.
            loc = groups.locate(ctx.recipe, p)
            return loc is None or view.deps_met(loc.node, loc.frame)

        ready = [p for p, st in sorted(rs.steps.items(), key=lambda kv: kv[1].last_seq)
                 if (st.state == "ready" and view.live_reason(p) is None and deps_now(p)) or (st.state == "stale" and stale_runnable(ctx, p, view) is None)]
        stale = []
        for p, st in sorted(rs.steps.items()):
            if st.state == "stale" and (view.live_reason(p, dispatch=False) is None):
                ev = ctx.record().last("step_stale", p)
                why = stale_runnable(ctx, p, view)
                stale.append({"step_path": p, "cause": ev.data.get("cause") if ev else None, "revised": ev.data.get("revised") if ev else None,
                              "runnable": why is None, **({"waiting": why} if why else {"options": ["dispatch (re-run)", "decide confirm"]})})
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
        from . import publish

        drifted = {(x["step_path"], x["artifact"]): x for x in publish.drift(events, self.project.root)}
        deliverables = []
        for (sp, art), t in sorted(publish.tracked(events).items()):
            if t.path is None:
                continue
            x = drifted.get((sp, art))
            deliverables.append({"step_path": sp, "artifact": art, "path": t.path, "sha256": t.expected,
                                 "revisions": len(t.revisions), **({"drift": {"current_sha256": x["current_sha256"]}} if x else {})})
        return {
            "run_id": run_id,
            "deliverables": deliverables,
            "drift": [x for x in drifted.values()],
            "possibly_stale": publish.possibly_stale_flags(events),
            "title": started.get("title"),
            "recipe": started.get("recipe"),
            "state": rs.state,
            "level": ctx.record().level(),
            "steps": steps,
            "groups": group_info,
            "findings": findings,
            "ready": ready,
            "stale": stale,
            "running": running,
            "queued": self._queued_for(run_id),
            "pending_decisions": pending,
            "needs_owner": bool(pending),
            "lease": lease_info,
            **({"adoption": started["adoption"], "awaiting_baseline": awaiting_baseline(events)} if started.get("adoption") else {}),
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
        source, own = None, None
        if node.independence is not None and loc is not None:
            split = reviews.split_review(step_path)
            parent = reviews.review_target(node)
            if split is not None and parent is not None and node.independence.from_step == parent[0].id:
                source, own = split[0], True  # the reviewed step's attempt under review
            else:
                source = step_path if node.independence.from_step == node.id else groups.child_path(loc.frame, node.independence.from_step)
        events = ctx.log.events()
        waiver = reviews.pending_waiver(events, step_path, "independence") if node.independence is not None else None
        return eligible_workers(
            node, step_path, self.project.profiles(), ctx.recipe.vocab, events=events, preferences=prefs, source_path=source,
            source_own=own, independence_waiver=waiver.data.get("decision_id") if waiver is not None else None,
        ), waiver

    def eligible(self, run_id: str, step_path: str) -> dict[str, Any]:
        """Ordered eligible profiles with reasons, and every exclusion (§8.4).

        A ready step with none escalates (``no_eligible_worker``); the owner's
        ``decide <step> retry`` readies it again once a worker exists.
        """
        ctx = self._ctx(run_id)
        result, _w = self._routing(ctx, step_path)
        wake = self._step_wake(ctx, step_path, result.eligible)
        out: dict[str, Any] = {"run_id": run_id, **result.as_dict(), "wake": wake}
        if result.eligible or ctx.log.state().step(step_path).state != "ready":
            out["escalated"] = False
            return out

        def body(c: RunContext) -> dict[str, Any]:
            escalate_no_worker(c, step_path, result.excluded, actor=self.director.actor)
            return {"run_id": run_id, **result.as_dict(), "wake": wake, "escalated": True}

        return self._mutate(run_id, body)

    def _step_wake(self, ctx: RunContext, step_path: str, eligible: list[dict[str, Any]]) -> dict[str, Any]:
        """Would anything wake the Director when this step ends waiting on the owner (§8.7, decision 0059)?

        No notice when every eligible worker is a person (decision 0060): the
        Director hands the result in with ``submit``, so nothing ends unseen.
        """
        from . import supervisor

        cfg = self.project.config.effort
        seconds = None
        if not eligible or any(e.get("adapter") != "manual" for e in eligible):
            effort, _src = resolve_effort(ctx, node_for(ctx.recipe, step_path), cfg, step_path)
            seconds = cfg.seconds(effort)
        return supervisor.wake_info(self.project, seconds, cfg.extend_once)

    def dispatch(self, run_id: str, step_path: str, worker: str, *, guidance: str | None = None, wait: bool = False) -> dict[str, Any]:
        """Build the packet and hand it to the worker's adapter (§8.7).

        The worker must be in the step's eligible set (§8.4). Manual workers
        then ``submit``. Process workers (API models, harness CLIs, commands)
        run under a detached supervisor: this call returns once the worker has
        started, with the dispatch id and deadline; the supervisor runs intake
        when it ends. ``wait=True`` then blocks until that is recorded.

        A write-mode step needs the workspace lock (§8.9): while another
        dispatch holds the working tree, or others are already waiting, the
        request is queued (``queued: true``, with the holder and position) and
        started later by whatever releases the lock.
        """
        out = self._dispatch(run_id, step_path, worker, guidance=guidance, wait=wait)
        if out.get("queued"):
            for r in self.start_queued():  # the tree may be free with entries ahead of this one
                if r["queue_id"] == out["queue_id"]:
                    out["started_from_queue"] = r
        return out

    def _dispatch(
        self, run_id: str, step_path: str, worker: str, *, guidance: str | None = None, wait: bool = False,
        queue_entry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import secrets

        from . import adapters, locks, supervisor
        from .profiles import SetupError, build_env

        profiles = self.project.profiles()
        if worker not in profiles:
            raise EngineError("configuration.unknown_profile", f"no worker profile {worker!r} on this machine (known: {', '.join(sorted(profiles)) or 'none'})")
        profile = profiles[worker]
        adapter = adapters.get(profile.adapter)
        if profile.isolation != "none":
            raise EngineError("configuration.isolation_unsupported", f"{worker}: isolation {profile.isolation!r} is not supported by this runtime yet; use none")
        ctx0 = self._ctx(run_id)
        routing, waiver = self._routing(ctx0, step_path)
        if worker not in routing.names():
            why = "; ".join(routing.reasons_for(worker)) or "not eligible"
            raise EngineError("routing.ineligible", f"{worker} is not eligible for {step_path}: {why} (see `baton eligible {run_id} {step_path}`)")

        def body(ctx: RunContext) -> dict[str, Any]:
            dispatch_id = f"d_{secrets.token_hex(4)}"
            n_next = ctx.log.state().step(step_path).attempt + 1
            node = node_for(ctx.recipe, step_path)
            mode = getattr(node, "workspace", "none")
            if mode != "write":
                return _start(ctx, dispatch_id, n_next, node, mode, False)
            st = ctx.log.state().step(step_path)
            view = view_of(ctx)
            why = (view.live_reason(step_path) if st.state == "ready" else
                   stale_runnable(ctx, step_path, view) if st.state == "stale" else f"{step_path} is {st.state}, not ready")
            if why:
                raise EngineError("packet.not_ready", why)
            baton = self.project.baton
            with locks.project_lock(baton):
                holder = locks.workspace_holder(baton)
                queue = locks.read_queue(baton)
                if queue_entry is None and (holder is not None or queue):
                    return self._enqueue(ctx, step_path, worker, guidance, holder, queue)
                if holder is not None and not (queue_entry is not None and holder.get("reserved") == queue_entry["queue_id"]):
                    raise EngineError("workspace.busy", f"the working tree is held by {_holder_text(holder)}")
                locks.take_workspace(baton, {
                    "dispatch_id": dispatch_id, "run_id": ctx.run_id, "step_path": step_path, "attempt": n_next,
                    "manual": adapter.name == "manual", "director": self.director.id, "since": supervisor.fmt(ctx.log.clock()),
                })
            try:
                out = _start(ctx, dispatch_id, n_next, node, mode, True)
            except BaseException:
                with locks.project_lock(baton):
                    locks.release_workspace(baton, dispatch_id=dispatch_id)
                raise
            if out.get("outcome") == "escalated":  # the supervisor never came up
                with locks.project_lock(baton):
                    locks.release_workspace(baton, dispatch_id=dispatch_id)
            elif out.get("supervisor_pid"):
                with locks.project_lock(baton):
                    locks.update_workspace(baton, "dispatch_id", dispatch_id, supervisor_pid=out["supervisor_pid"])
            return out

        def _start(ctx: RunContext, dispatch_id: str, n_next: int, node: Any, mode: str, locked: bool) -> dict[str, Any]:
            adir = ctx.attempt_dir(step_path, n_next)
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
                if e.failure_class == "platform":
                    # Nothing was dispatched; the step stays ready and the incident says why (§12.3).
                    inc = self._open_incident({"run": ctx.run_id, "step_path": step_path, "attempt": None, "class": "platform",
                                               "code": e.code.split(".")[-1], "message": redact_text(str(e)), "worker": worker})
                    raise EngineError(e.code, f"{e} (platform incident {inc} opened)") from e
                raise EngineError(e.code, str(e)) from e
            if env is not None:
                self._observed_fact(worker, env.resolved)
            effort, effort_source = resolve_effort(ctx, node, self.project.config.effort, step_path)
            band_s = self.project.config.effort.seconds(effort)
            deadline = supervisor.fmt(ctx.log.clock() + timedelta(seconds=band_s))
            extra: dict[str, Any] = {"auth_mode": profile.auth.mode, "workspace_mode": mode, "effort": effort, "deadline": deadline}
            if waiver is not None:
                # One waiver covers one dispatch (§9.3), whichever worker is chosen.
                extra.update(waiver_seq=waiver.seq, independence_waived=waiver.data.get("decision_id"))
            if effort_source != "step":
                extra["effort_source"] = effort_source
            if env is not None:
                extra["env"] = env.describe()
            built = begin_attempt(
                ctx, step_path, worker, profile, actor=self.director.actor, dispatch_id=dispatch_id, adapter=adapter.name,
                guidance=guidance, preflight=lambda b: adapter.preflight(profile, b.dir), dispatch_data=extra,
                deadline=deadline, effort=effort,
            )
            if queue_entry is not None:
                ctx.log.append("dispatch_dequeued", step_path=step_path, data={"queue_id": queue_entry["queue_id"], "started": True, "dispatch_id": dispatch_id})
            out: dict[str, Any] = {
                "run_id": ctx.run_id, "step_path": step_path, "attempt": built.attempt, "dispatch_id": dispatch_id,
                "worker": worker, "adapter": adapter.name, "packet_sha256": built.sha256,
                "packet": str(built.dir), "result": str(built.result_dir),
                "effort": effort, "deadline": deadline,
                "handoff": adapter.handoff(profile, built.dir, built.result_dir),
                "warnings": [],
            }
            if locked:
                out["workspace_lock"] = True
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
            if supervisor.wake_path(self.project) is None:
                out["warnings"].append(
                    f"{supervisor.NO_WAKE_WARNING}; check with `baton status {ctx.run_id}` or `baton wait {ctx.run_id}`"
                )
            return out

        out = self._mutate(run_id, body)
        if out.get("queued"):
            if adapter.name != "manual" and supervisor.wake_path(self.project) is None:
                out.setdefault("warnings", []).append(f"{supervisor.NO_WAKE_WARNING}; check with `baton status {run_id}`")
            return out
        if wait and "outcome" not in out and out.get("supervisor_pid"):
            waited = self.wait(run_id, out["dispatch_id"])
            res = waited["results"][0] if waited["results"] else {}
            for k in ("outcome", "reasons", "ready", "run_completed", "pending_decisions", "needs_owner", "worker_exit"):
                if k in res or k in waited:
                    out[k] = res.get(k, waited.get(k))
        return out

    # -- the workspace queue (§8.9) -----------------------------------------

    def _enqueue(self, ctx: RunContext, step_path: str, worker: str, guidance: str | None, holder: dict[str, Any] | None, queue: list[dict[str, Any]]) -> dict[str, Any]:
        """Queue a write-mode dispatch behind the workspace holder (called under the project lock)."""
        import secrets

        from . import locks, supervisor

        if any(e.get("run_id") == ctx.run_id and e.get("step_path") == step_path for e in queue):
            raise EngineError("dispatch.already_queued", f"{step_path} of run {ctx.run_id} is already queued for the working tree (withdraw it with `baton cancel {ctx.run_id} {step_path}`)")
        entry = {
            "queue_id": f"q_{secrets.token_hex(4)}", "run_id": ctx.run_id, "step_path": step_path, "worker": worker,
            "director_id": self.director.id, "harness": self.director.harness, "queued_at": supervisor.fmt(ctx.log.clock()),
        }
        if guidance:
            entry["guidance"] = guidance
        queue.append(entry)
        locks.write_queue(self.project.baton, queue)
        held = {k: holder.get(k) for k in ("run_id", "step_path", "dispatch_id")} if holder and not holder.get("reserved") else None
        data: dict[str, Any] = {"queue_id": entry["queue_id"], "worker": worker, "position": len(queue), "holder": held}
        if guidance:
            data["guidance"] = guidance
        ctx.log.append("dispatch_queued", actor=self.director.actor, step_path=step_path, data=data)
        return {
            "run_id": ctx.run_id, "step_path": step_path, "queued": True, "queue_id": entry["queue_id"], "worker": worker,
            "position": len(queue), "holder": held, "warnings": [],
        }

    def start_queued(self) -> list[dict[str, Any]]:
        """Start queued write-mode dispatches while the working tree is free (§8.9).

        Called by whatever releases the workspace lock (the supervisor after
        intake, ``submit``, reconciliation, abandoning a run) and by a dispatch
        that queued. Each entry starts as the Director who queued it, with its
        packet built now; one that can no longer start is dropped, recorded and
        reported through the hooks (outcome ``not_started``).
        """
        from . import locks
        from .locks import Director

        baton = self.project.baton
        results: list[dict[str, Any]] = []
        while True:
            with locks.project_lock(baton):
                if locks.workspace_holder(baton) is not None:
                    break
                queue = locks.read_queue(baton)
                if not queue:
                    break
                entry = queue.pop(0)
                locks.write_queue(baton, queue)
                locks.take_workspace(baton, {"reserved": entry["queue_id"], "run_id": entry["run_id"], "step_path": entry["step_path"]})
            base = {"queue_id": entry["queue_id"], "run_id": entry["run_id"], "step_path": entry["step_path"]}
            api = Api(self.project, Director(entry.get("director_id") or self.director.id, entry.get("harness") or "cli", socket.gethostname()))
            try:
                out = api._dispatch(entry["run_id"], entry["step_path"], entry["worker"], guidance=entry.get("guidance"), queue_entry=entry)
                results.append({**base, "started": True, "dispatch_id": out.get("dispatch_id"), "outcome": out.get("outcome")})
            except (EngineError, HandoffError) as e:
                with locks.project_lock(baton):
                    locks.release_workspace(baton, reserved=entry["queue_id"])
                reason = str(e)
                self._drop_queued(entry, reason, getattr(e, "code", "handoff.missing_inputs"))
                results.append({**base, "started": False, "reason": reason})
        return results

    def _drop_queued(self, entry: dict[str, Any], reason: str, code: str, *, actor: str = "runtime", fire: bool = True) -> None:
        """Record that a queued dispatch will not start, and wake the Director."""
        from . import docs

        run_id, step_path = entry["run_id"], entry["step_path"]
        try:
            with self._run_lock(run_id):
                ctx = self._ctx(run_id)
                ctx.log.append("dispatch_dequeued", actor=actor, step_path=step_path,
                               data={"queue_id": entry["queue_id"], "started": False, "reason": reason, "code": code})
                docs.write_records(ctx)
        except (EngineError, StoreError):
            return  # the run is gone or unreadable: nothing to record it in
        if fire:
            self._fire_and_record(ctx, step_path, ctx.log.state().step(step_path).attempt or None, entry["queue_id"], outcome="not_started")  # type: ignore[arg-type]

    def _queued_for(self, run_id: str) -> list[dict[str, Any]]:
        from . import locks

        queue = locks.read_queue(self.project.baton)
        return [
            {"step_path": e["step_path"], "queue_id": e["queue_id"], "worker": e.get("worker"), "position": i + 1, "queued_at": e.get("queued_at")}
            for i, e in enumerate(queue) if e.get("run_id") == run_id
        ]

    def _release_workspace(self, *, dispatch_id: str | None = None, run_id: str | None = None) -> bool:
        from . import locks

        with locks.project_lock(self.project.baton):
            return locks.release_workspace(self.project.baton, dispatch_id=dispatch_id, run_id=run_id)

    def cancel(self, run_id: str, step_path: str) -> dict[str, Any]:
        """Withdraw a queued write-mode dispatch (§8.9)."""
        from . import locks

        def body(ctx: RunContext) -> dict[str, Any]:
            baton = self.project.baton
            with locks.project_lock(baton):
                queue = locks.read_queue(baton)
                entry = next((e for e in queue if e.get("run_id") == run_id and e.get("step_path") == step_path), None)
                if entry is None:
                    raise EngineError("cancel.not_queued", f"{step_path} of run {run_id} is not queued")
                locks.write_queue(baton, [e for e in queue if e is not entry])
            ctx.log.append("dispatch_dequeued", actor=self.director.actor, step_path=step_path,
                           data={"queue_id": entry["queue_id"], "started": False, "reason": "withdrawn by the Director", "code": "cancelled"})
            return {"run_id": run_id, "step_path": step_path, "queue_id": entry["queue_id"], "cancelled": True}

        return self._mutate(run_id, body, allow_closed=True)

    def _drop_run_entries(self, run_id: str, reason: str) -> None:
        """Remove a run's queued dispatches and its hold on the working tree (the run ended)."""
        from . import locks

        baton = self.project.baton
        with locks.project_lock(baton):
            queue = locks.read_queue(baton)
            mine = [e for e in queue if e.get("run_id") == run_id]
            if mine:
                locks.write_queue(baton, [e for e in queue if e.get("run_id") != run_id])
            locks.release_workspace(baton, run_id=run_id)
        for e in mine:
            self._drop_queued(e, reason, "run_ended", fire=False)

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
        elif st.attempt == n and st.state == "verifying" and any(e.type == "step_ready" and e.data.get("review_of") == step_path and e.data.get("attempt") == n for e in ctx.log.events()):
            outcome = "needs_review"
            reasons = [f"{e.step_path} is ready for a reviewer" for e in ctx.log.events() if e.type == "step_ready" and e.data.get("review_of") == step_path and e.data.get("attempt") == n][-1:]
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
                self._release_finished_holder(ctx)
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
                before = ctx.log.state().last_seq
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
                self._finish_records(ctx, before, {})
                self._release_workspace(dispatch_id=did)
                self._fire_and_record(ctx, path, n, did)
                supervisor.remove_marker(self.project.baton, did)
            self._release_finished_holder(ctx)
        self.start_queued()
        return actions

    def _release_finished_holder(self, ctx: RunContext) -> None:
        """Release this run's hold on the working tree if its attempt is no longer in flight (e.g. a crashed ``submit``)."""
        from . import locks

        with locks.project_lock(self.project.baton):
            h = locks.workspace_holder(self.project.baton)
            if h is None or h.get("run_id") != ctx.run_id or h.get("reserved"):
                return
            st = ctx.log.state().step(h.get("step_path", ""))
            if ctx.log.state().state != "active" or st.attempt != h.get("attempt") or st.state not in ("dispatched", "running", "submitted", "verifying"):
                locks.release_workspace(self.project.baton, dispatch_id=h.get("dispatch_id"))

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
        return gitops.tree_changes(gitops.TreeSnapshot(raw.get("head"), raw.get("files") or {}), after, self.project.root)

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
            # Before the hooks, so on_platform_failure can hand the incident to the platform expert (§12.3).
            self._open_incidents(ctx, [e for e in ctx.log.events() if e.seq > before])
            docs.write_records(ctx)  # so BATON_RECORD is current when the hooks run
        self._release_workspace(dispatch_id=dispatch_id)
        self._fire_and_record(ctx, step_path, attempt, dispatch_id, before=before)
        self.start_queued()
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
            elif state == "verifying" and any(e.type == "step_ready" and e.data.get("review_of") == step_path and e.data.get("attempt") == n for e in ctx.log.events()):
                outcome = "needs_review"  # the Director dispatches a reviewer (§9.1)
            elif state == "awaiting_human" or (esc is not None and esc.data.get("reason") == "blocked"):
                outcome = "needs_human"
            elif esc is not None and esc.data.get("reason") in ("platform", "configuration", "unknown"):
                outcome = "failed"
            else:
                outcome = "gate_failed"
        record = ctx.run_dir / "docs" / f"{step_path}.md"
        from .sme import incident_for

        inc = incident_for(self.project.store.project_log().events(), ctx.run_id, step_path, n) if cls_ev is not None else None
        return {
            "incident": inc["id"] if inc else None,
            "run_id": ctx.run_id, "step_path": step_path, "attempt": n, "dispatch_id": dispatch_id, "outcome": outcome,
            "classification": cls_ev.data.get("class") if cls_ev is not None else None,
            "step_state": state,
            "needs_owner": (state in ("awaiting_human", "escalated") or judged == "iteration_limit" or self._review_needs_owner(ctx, step_path)) and outcome != "overdue",
            "record": str(record),
        }

    @staticmethod
    def _review_needs_owner(ctx: RunContext, step_path: str) -> bool:
        """After a review: whether the reviewed step now waits on the owner."""
        if reviews.split_review(step_path) is None:
            return False
        req = _review_request(ctx, step_path)
        return req is not None and ctx.log.state().step(req[0]).state in ("awaiting_human", "escalated")

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
            disp = _last_data(ctx.log.events(), "dispatched", step_path, st.attempt)
            profile = disp.get("profile")
            outcome = submit(ctx, step_path, actor=f"worker:{profile}" if profile else "worker")
            if disp.get("dispatch_id"):
                self._release_workspace(dispatch_id=disp["dispatch_id"])  # a manual write step held the tree until now
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        out = self._mutate(run_id, body)
        self.start_queued()
        return out

    def decide(self, run_id: str, ref: str, decision: str, note: str = "", *, path: str | None = None,
               answers: Any = None, partial: bool = False, items: list[str] | None = None) -> dict[str, Any]:
        """Record the owner's decision verbatim (gates, escalations, findings, stale steps, notices, deliverables,
        a blocked step's confirmed answers, a framing selection)."""

        extra: list[Path] = []

        def body(ctx: RunContext) -> dict[str, Any]:
            if items is not None or decision == "select":
                from . import frame as framing

                return {"run_id": ctx.run_id, **framing.select(self, ctx, ref, decision, note, items, extra)}
            outcome = decide(ctx, ref, decision, note, actor="human", recorded_by=self.director.actor, path=path,
                             answers=answers, partial=partial)
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        return self._mutate(run_id, body, extra=extra)

    def waive(self, run_id: str, step_path: str, gate: str, reason: str) -> dict[str, Any]:
        """Waive one gate occurrence (§9.3). The reason is the owner's decision; the director skill requires it."""

        def body(ctx: RunContext) -> dict[str, Any]:
            outcome = waive(ctx, step_path, gate, reason, actor="human", recorded_by=self.director.actor)
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        return self._mutate(run_id, body)

    def disposition(self, run_id: str, step_path: str, finding: str, value: str, evidence: str | None = None) -> dict[str, Any]:
        """Record a finding's disposition (§9.2): fixed / rejected with evidence, or accepted-risk with the owner's decision id."""

        def body(ctx: RunContext) -> dict[str, Any]:
            outcome = disposition(ctx, step_path, finding, value, evidence, actor=self.director.actor)
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        return self._mutate(run_id, body)

    def revise(self, run_id: str, step_path: str, reason: str) -> dict[str, Any]:
        """Correct an earlier step of this run (§8.9). Owner approval is the director skill's rule."""

        def body(ctx: RunContext) -> dict[str, Any]:
            outcome = revise(ctx, step_path, reason, actor=self.director.actor)
            stale = [e.step_path for e in ctx.log.events() if e.type == "step_stale" and e.data.get("revised") == step_path and e.seq > ctx.record().last("step_revised", step_path).seq]
            return {"run_id": ctx.run_id, **_outcome_dict(outcome), "stale": stale}

        return self._mutate(run_id, body)

    def retriage(self, run_id: str, reason: str) -> dict[str, Any]:
        """Rerun triage (§5.5); the new level waits on the owner's decision at the triage step."""

        def body(ctx: RunContext) -> dict[str, Any]:
            outcome = retriage(ctx, reason, actor=self.director.actor)
            return {"run_id": ctx.run_id, **_outcome_dict(outcome)}

        return self._mutate(run_id, body)

    def ingest_revision(self, run_id: str, step_path: str, artifact: str, note: str, *, feed: str = "revision_inputs") -> dict[str, Any]:
        """Accept a drifted published file as a human revision (§10.5); the note is the owner's decision."""
        from . import publish

        def body(ctx: RunContext) -> dict[str, Any]:
            res = publish.ingest_drift(ctx, step_path, artifact, note, feed, "human", {"recorded_by": self.director.actor})
            refresh(ctx)
            return {"run_id": ctx.run_id, **res}

        return self._mutate(run_id, body)

    def abandon(self, run_id: str, reason: str) -> dict[str, Any]:
        def body(ctx: RunContext) -> dict[str, Any]:
            abandon_run(ctx, reason, actor=self.director.actor)
            return {"run_id": ctx.run_id, "state": "abandoned"}

        out = self._mutate(run_id, body)
        self._drop_run_entries(run_id, "the run was abandoned")
        self.start_queued()
        return out

    # -- adoption (§11) -----------------------------------------------------

    # -- experts, platform area, process feedback (§12) ----------------------

    def _project_paths(self) -> list[Path]:
        """Project-level records (§4.3) that ride along with the next checkpoint when they changed."""
        b = self.project.baton
        return [p for p in (b / "project", b / "platform", b / "process") if p.exists()]

    def _project_checkpoint(self, phrase: str) -> Any:
        """Commit project-level records after a call that touches no run (§10.1)."""
        from . import gitops
        from .locks import project_lock

        if not self.project.config.checkpoints.commit:
            return gitops.Checkpoint(False, reason="checkpoint commits are off in project.yaml")
        with project_lock(self.project.baton):
            paths = self._project_paths()
            if not paths:
                return None
            pf = gitops.preflight(self.project.root, paths)
            if isinstance(pf, str):
                return gitops.Checkpoint(False, reason=pf)
            top, rels = pf
            subject = f"baton(project): {phrase}"
            self.project.store.project_log().append("checkpoint_committed", data={"subject": subject})
            try:
                sha = gitops.commit(top, rels, subject, [])
            except gitops.GitError as e:
                return gitops.Checkpoint(False, subject=subject, reason=str(e))
        return gitops.Checkpoint(sha is not None, sha, subject, None if sha else "nothing to commit")

    def _open_incident(self, data: dict[str, Any]) -> str:
        import secrets

        from . import sme

        inc = f"inc_{secrets.token_hex(3)}"
        run, path, n = data.get("run"), data.get("step_path"), data.get("attempt")
        refs = ["facts"] + ([f"log:{run}:{path}@{n}"] if run and path and n else [])
        sme.project_append(self.project, "platform_incident_opened", {"incident": inc, **data, "refs": refs})
        return inc

    def _open_incidents(self, ctx: RunContext, new: list[Any]) -> list[str]:
        """Open a platform incident for every new ``platform`` / ``unknown`` classification (§12.3)."""
        from . import sme

        opened = []
        for e in new:
            if e.type != "failure_classified" or e.data.get("class") not in ("platform", "unknown"):
                continue
            if sme.incident_for(self.project.store.project_log().events(), ctx.run_id, e.step_path, e.attempt) is not None:
                continue
            data = {"run": ctx.run_id, "step_path": e.step_path, "attempt": e.attempt, "class": e.data.get("class"),
                    "code": e.data.get("code"), "message": e.data.get("message")}
            if "gate" in e.data:
                data["gate"] = e.data["gate"]
            opened.append(self._open_incident(data))
        return opened

    def platform_incident(self, action: str = "list", incident: str | None = None, fix: str | None = None) -> dict[str, Any]:
        """``list`` incidents, ``show`` one, or ``resolve`` one with the fix (§12.3).

        Resolving readies each step the incident escalated, once: the "one automatic
        retry" of a platform failure (§8.8). The Director then dispatches it.
        """
        from . import sme

        found = sme.incidents(self.project.store.project_log().events())
        if action == "list":
            return {"incidents": list(found.values()), "open": [i["id"] for i in found.values() if i["status"] == "open"]}
        if incident not in found:
            raise EngineError("incident.unknown", f"no platform incident {incident!r} (open: {', '.join(i for i, v in found.items() if v['status'] == 'open') or 'none'})")
        inc = found[incident]
        if action == "show":
            return {"incident": inc}
        if action != "resolve":
            raise EngineError("incident.bad_action", f"action must be list, show or resolve, got {action!r}")
        if inc["status"] != "open":
            raise EngineError("incident.resolved", f"{incident} is already resolved")
        if not (fix or "").strip():
            raise EngineError("incident.no_fix", "resolving an incident needs the fix that was made (--fix)")
        retry: list[dict[str, Any]] = []
        run, path, n = inc.get("run"), inc.get("step_path"), inc.get("attempt")
        if run and path and n:
            try:
                st = self.project.store.run(run).state()
                if st.state == "active" and st.step(path).state == "escalated" and st.step(path).attempt == n:
                    retry.append({"run": run, "step_path": path, "attempt": n})
            except StoreError:
                pass
        sme.project_append(self.project, "platform_incident_resolved", {"incident": incident, "fix": redact_text(fix or ""), "retried": retry},
                           actor=self.director.actor)
        readied = []
        for r in retry:
            def body(ctx: RunContext, r: dict[str, Any] = r) -> dict[str, Any]:
                st = ctx.log.state().step(r["step_path"])
                if st.state == "escalated" and st.attempt == r["attempt"]:
                    ctx.log.append("step_ready", step_path=r["step_path"], data={"after_incident": incident})
                    return {"readied": True}
                return {}
            try:
                if self._mutate(r["run"], body).get("readied"):
                    readied.append(r)
            except EngineError as e:
                readied.append({**r, "not_readied": str(e)})
        out: dict[str, Any] = {"incident": incident, "resolved": True, "readied": readied}
        cp = self._project_checkpoint(f"incident {incident} resolved")
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        return out

    def platform_fact(self, text: str, source: str = "owner") -> dict[str, Any]:
        """Record a durable platform fact (§12.3) in the project log and ``.baton/platform/facts.md``."""
        from . import sme

        if not text.strip():
            raise EngineError("fact.empty", "a platform fact needs text")
        entry = sme.add_fact(self.project.baton, text, source, self.project.store.clock())
        ev = sme.project_append(self.project, "platform_fact_recorded", {"fact": redact_text(text), "source": source}, actor=self.director.actor)
        out: dict[str, Any] = {"recorded": True, "seq": ev.seq, "entry": entry}
        cp = self._project_checkpoint("platform fact recorded")
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        return out

    # -- action permissions (§13.7) ------------------------------------------

    def push(self, *, approved: bool = False, note: str | None = None) -> dict[str, Any]:
        """Push the current branch under ``permissions.push``.

        The commits being pushed are sorted into ``docs_only`` / ``after_verified`` /
        ``other`` (``permissions.py``). ``deny`` is refused and never attempted; ``ask``
        records ``permission_requested`` and returns ``needs_owner``; the owner's approval is
        the same call with ``approved`` and their words. An allowed push records
        ``permission_used`` and commits that record first, so it travels with the push.
        """
        from . import gitops, permissions

        try:
            plan = permissions.plan_push(self.project.root, self.project.store, self.project.config.docs_only_globs)
        except gitops.GitError as e:
            raise EngineError("push.git", str(e)) from e
        if not plan.commits:
            return {"pushed": False, "reason": "nothing to push", **plan.summary(), "needs_owner": False}
        rule = permissions.rule_for(self.project.config, "push", plan.category)
        out = self._permit("push", rule, plan.summary(), approved, note, label=f"push ({plan.category.replace('_', '-')})")
        if not out["granted"]:
            return out
        args = ["push", "--porcelain"] + (["--set-upstream"] if plan.upstream is None else []) + [plan.remote, f"HEAD:refs/heads/{plan.branch}"]
        proc = gitops.git(self.project.root, *args, check=False)
        if proc.returncode != 0:
            raise EngineError("push.failed", f"git push failed: {redact_text((proc.stderr or proc.stdout).strip())}")
        out["pushed"] = True
        return out

    def permission(self, action: str, detail: str | None = None, *, approved: bool = False, note: str | None = None) -> dict[str, Any]:
        """Check an action the Director takes outside the runtime (tag, merge, deploy, force_push).

        ``allow`` records ``permission_used`` and grants it; ``deny`` is refused; ``ask`` records
        ``permission_requested`` and returns ``needs_owner`` until the call is repeated with the
        owner's approval in their own words.
        """
        from . import permissions

        if action == "push":
            raise EngineError("permission.use_push", "the runtime does the pushing: use `baton push`, which checks permissions.push itself")
        try:
            rule = permissions.rule_for(self.project.config, action)
        except ValueError as e:
            raise EngineError("permission.unknown_action", str(e)) from e
        return self._permit(action, rule, {"detail": detail} if detail else {}, approved, note, label=action.replace("_", "-"))

    def _permit(self, action: str, rule: str, detail: dict[str, Any], approved: bool, note: str | None, *, label: str) -> dict[str, Any]:
        from . import sme

        actor = self.director.actor
        base = {"action": action, "rule": rule, **detail}
        if rule == "deny":
            raise EngineError("permission.denied", f"{label} is denied by project.yaml permissions; it is never attempted")
        out: dict[str, Any] = {**base}
        if rule == "ask" and not approved:
            ev = sme.project_append(self.project, "permission_requested", base, actor=actor)
            cp = self._project_checkpoint(f"permission requested: {label}")
            out.update(granted=False, permission="ask", requested_seq=ev.seq, needs_owner=True,
                       message=f"{label} needs the owner's approval; repeat with --approved --note \"<the owner's words>\"")
            if cp is not None:
                out["checkpoint"] = cp.as_dict()
            return out
        data = dict(base)
        if rule == "ask":
            if not (note or "").strip():
                raise EngineError("permission.note", "an approval needs the owner's words (--note), recorded verbatim")
            log = self.project.store.project_log()
            decision_id = f"d{len(log.events()) + 1}"
            sme.project_append(self.project, "human_decision", {"kind": "permission", "action": action, "decision": "approve",
                                                                 "note": note, "decision_id": decision_id, **detail}, actor="human")
            data["decision_id"] = decision_id
            out["decision_id"] = decision_id
        ev = sme.project_append(self.project, "permission_used", data, actor=actor)
        cp = self._project_checkpoint(f"permission used: {label}")
        out.update(granted=True, permission="approved" if rule == "ask" else "allow", used_seq=ev.seq, needs_owner=False)
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        return out

    # -- explain (§10.6) -------------------------------------------------------

    def explain(self, run_id: str) -> dict[str, Any]:
        """Process facts only: what is done, where the run is, what remains at this level and what other levels would change.

        Never step outputs or artifacts: the Director can describe progress without loading subject matter.
        """
        st = self.status(run_id)
        ctx = self._ctx(run_id)
        level = st["level"]
        full = build_plan(ctx.recipe)
        levels = [lv.level for lv in full.levels]
        by_level = {lv.level: [s for s in lv.steps if s.depth == 0] for lv in full.levels}
        titles = {s.path: s.title for lv in full.levels for s in lv.steps}
        done = {"passed": [], "imported": [], "skipped": []}
        for path, info in st["steps"].items():
            if info.get("review_of"):
                continue
            state = info["state"]
            key = {"passed": "passed", "imported": "imported", "skipped": "skipped"}.get(state)
            if key:
                done[key].append({"step": path, "title": titles.get(path, path)})
        finished = {d["step"] for k in done.values() for d in k}
        current = by_level.get(level) if level is not None or None in by_level else None

        def remaining_at(lv: str | None) -> list[dict[str, Any]]:
            rows = []
            for s in by_level.get(lv, []):
                if not s.included or s.path in finished:
                    continue
                gates = [g.type for g in s.gates if g.included]
                rows.append({"step": s.path, "title": s.title, "kind": s.kind, "state": st["steps"].get(s.path, {}).get("state"),
                             "gates": gates, **({"group": s.group} if s.group else {})})
            return rows

        remaining = remaining_at(level) if current is not None else []
        other_levels: dict[str, Any] = {}
        if level is not None and len(levels) > 1:
            here = {s.path for s in by_level[level] if s.included}
            for lv in levels:
                if lv == level:
                    continue
                there = {s.path for s in by_level[lv] if s.included}
                other_levels[lv] = {"adds": sorted(there - here), "drops": sorted(here - there)}
        branches: list[str] = []
        for r in remaining:
            if "human" in r["gates"]:
                branches.append(f"{r['step']}: the owner approves or rejects (a rejection sends it back for another attempt)")
            if "review" in r["gates"] or "findings" in r["gates"]:
                branches.append(f"{r['step']}: open blocking findings send the work back before it can pass")
            if r.get("group") and r["group"].get("max_iterations"):
                branches.append(f"{r['step']}: repeats until its judges pass, at most {r['group']['max_iterations']} iterations, then the owner decides")
        if level is None and len(levels) > 1 and levels[0] is not None:
            branches.append(f"triage sets the level ({', '.join(levels)}); the level decides which steps and gates run")
        position = {
            "running": [r["step_path"] for r in st["running"]], "queued": [q["step_path"] for q in st["queued"]],
            "ready": st["ready"], "stale": [x["step_path"] for x in st["stale"]],
            "owner_decisions": [{"ref": p["ref"], "kind": p["kind"]} for p in st["pending_decisions"]],
            "groups": {g: i["summary"] for g, i in st["groups"].items()},
        }
        lines = [f"{run_id} ({st['title'] or 'untitled'}), recipe {st['recipe']}" + (f" at level {level}" if level else "") + f": {st['state']}."]
        for k, label in (("passed", "Done"), ("imported", "Imported from the prior process"), ("skipped", "Skipped at this level")):
            if done[k]:
                lines.append(f"{label}: " + ", ".join(d["step"] for d in done[k]) + ".")
        for k, label in (("running", "Running"), ("queued", "Queued for the working tree"), ("ready", "Ready to dispatch"), ("stale", "Stale")):
            if position[k]:
                lines.append(f"{label}: " + ", ".join(position[k]) + ".")
        for g, summary in position["groups"].items():
            lines.append(f"{g}: {summary}.")
        if position["owner_decisions"]:
            lines.append("Waiting on the owner: " + ", ".join(d["ref"] for d in position["owner_decisions"]) + ".")
        if st["state"] == "active":
            todo = [r["step"] for r in remaining if r["step"] not in position["ready"] and r["step"] not in position["running"]]
            if level is None and len(levels) > 1 and levels[0] is not None:
                lines.append("The level is not set yet; what remains depends on triage.")
            elif todo:
                lines.append("Still to come at this level: " + ", ".join(todo) + ".")
        for lv, diff in other_levels.items():
            bits = ([f"adds {', '.join(diff['adds'])}"] if diff["adds"] else []) + ([f"drops {', '.join(diff['drops'])}"] if diff["drops"] else [])
            if bits:
                lines.append(f"At {lv}: " + "; ".join(bits) + ".")
        lines += [f"Possible: {b}." for b in branches]
        return {"run_id": run_id, "title": st["title"], "recipe": st["recipe"], "state": st["state"], "level": level, "levels": levels,
                "done": done, "position": position, "remaining": remaining, "other_levels": other_levels, "branches": branches,
                "text": "\n".join(lines), "pending_decisions": st["pending_decisions"], "needs_owner": st["needs_owner"]}

    def _observed_fact(self, worker: str, resolved: Any) -> None:
        """A harness CLI found only through ``path.search`` is an observed platform fact (§6.2, §12.3)."""
        from . import sme

        if resolved is None or not resolved.how.startswith("search:"):
            return
        text = f"{worker}: `{Path(resolved.executable).name}` resolves to {resolved.executable} via {resolved.how[7:]} on this host"
        if sme.fact_known(self.project.baton, text):
            return
        sme.add_fact(self.project.baton, text, "runtime", self.project.store.clock(), observed=True)
        sme.project_append(self.project, "platform_fact_recorded", {"fact": text, "source": "runtime", "observed": True})

    def feedback(self, kind: str, text: str, run_id: str | None = None, step_path: str | None = None,
                 gate: str | None = None, informed_owner: bool = False) -> dict[str, Any]:
        """Record process feedback (§12.4). A report that a blocking gate or approval was skipped outside
        Baton (``skipped_step``) is surfaced to the owner at once: ``on_needs_human`` fires and a notice
        stays pending (``decide <run> skip:<seq> acknowledge``) until the owner acknowledges it.
        """
        from . import docs, sme, supervisor

        if kind not in sme.FEEDBACK_KINDS:
            raise EngineError("feedback.bad_kind", f"kind must be one of {', '.join(sme.FEEDBACK_KINDS)}, got {kind!r}")
        if not text.strip():
            raise EngineError("feedback.empty", "feedback needs text")
        ctx = self._ctx(run_id) if run_id else None
        blocking = None
        if kind == "skipped_step":
            if ctx is None or not step_path:
                raise EngineError("feedback.needs_step", "a skipped_step report names the run and the step (--run, --step)")
            node = node_for(ctx.recipe, step_path)
            if not isinstance(node, Step):
                raise EngineError("feedback.unknown_step", f"{step_path} is not a step of run {run_id}")
            blocking = True
            if gate is not None:
                gi = _gate_index(node, gate)
                blocking = not node.gates[gi].advisory
        elif gate is not None:
            raise EngineError("feedback.gate", "--gate applies only to skipped_step reports")
        data: dict[str, Any] = {"kind": kind, "text": redact_text(text)}
        if run_id:
            data["run"] = run_id
        if step_path:
            data["step_path"] = step_path
            if ctx is not None:
                data["qualified"] = sme.qualified(ctx.recipe.recipe.ref, step_path)
        if gate is not None:
            data["gate"] = gate
        if informed_owner:
            data["informed_owner"] = True
        fb = sme.project_append(self.project, "process_feedback", data, actor=self.director.actor)
        out: dict[str, Any] = {"recorded": True, "seq": fb.seq}
        if kind == "skipped_step":
            assert ctx is not None
            skip = sme.project_append(self.project, "step_skip_recorded", {
                "feedback_seq": fb.seq, "run": run_id, "step_path": step_path, "gate": gate, "blocking": blocking,
                "surfaced": blocking, "informed_owner": informed_owner,
            })
            if blocking:
                ref = f"skip:{skip.seq}"
                out["notice"] = ref
                st = ctx.log.state().step(step_path or "")
                fired = supervisor.fire_hooks(self.project, {
                    "run_id": run_id, "step_path": step_path, "outcome": "needs_human", "needs_owner": True, "classification": None,
                    "dispatch_id": None, "step_state": st.state, "record": str(ctx.run_dir / "docs" / f"{step_path}.md"),
                })
                with self._run_lock(ctx.run_id):
                    for d in fired:
                        ctx.log.append("completion_hook_fired" if d.get("ok") else "completion_hook_failed", data={**d, "notice": ref})
                    docs.write_records(ctx)
                out["hooks"] = fired
                out["pending_decisions"] = pending_decisions(ctx)
                out["needs_owner"] = True
        cp = self._project_checkpoint(f"process feedback ({kind})")
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        return out

    # consultations

    def _sme_routing(self, subject: str, ctx: RunContext | None) -> tuple[Any, Any, list[dict[str, Any]], list[dict[str, Any]]]:
        from . import sme
        from .vocab import DEFAULT, load

        recipe = ctx.recipe if ctx is not None else None
        vocab = recipe.vocab if recipe is not None else load(DEFAULT)
        req = sme.requirements(subject, recipe, vocab)
        cfg = self.project.config.sme.get(subject)  # type: ignore[call-overload]
        el, ex = sme.eligible(subject, req, self.project.profiles(), vocab, cfg.preferred_profiles if cfg else [])
        return req, vocab, el, ex

    def sme_eligible(self, subject: str, run_id: str | None = None) -> dict[str, Any]:
        """The profiles that may answer as this subject's expert, in order, and those excluded with reasons."""
        from . import sme

        if subject not in sme.SUBJECTS:
            raise EngineError("sme.bad_subject", f"subject must be one of {', '.join(sme.SUBJECTS)}")
        from . import supervisor

        req, _v, el, ex = self._sme_routing(subject, self._ctx(run_id) if run_id else None)
        cfg = self.project.config.effort
        # A turn gets the default band and is never extended; an expert is never a person (decision 0045).
        wake = supervisor.wake_info(self.project, cfg.seconds(cfg.default), False, what="the expert's answer comes back")
        return {"subject": subject, "requires": req.model_dump(exclude_none=True), "eligible": el, "excluded": ex, "wake": wake}

    def _sme_locked(self, run_id: str | None, body: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Run ``body`` holding the run's lease and lock (run consultations) or the project lock."""
        from .locks import project_lock

        if run_id is not None:
            return self._mutate(run_id, lambda _ctx: body(), allow_closed=True)
        with project_lock(self.project.baton):
            return body()

    def ask_sme(self, subject: str, question: str, refs: list[str] | None = None, *, run_id: str | None = None, mode: str = "relay",
                worker: str | None = None, contact: str | None = None, wait: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """Consult an expert by subject (§12.1). ``relay`` dispatches a turn; ``handoff`` returns a prompt to paste elsewhere."""
        from . import sme

        if subject not in sme.SUBJECTS:
            raise EngineError("sme.bad_subject", f"subject must be one of {', '.join(sme.SUBJECTS)}, got {subject!r}")
        if mode not in sme.MODES:
            raise EngineError("sme.bad_mode", f"mode must be relay or handoff, got {mode!r}")
        if not question.strip():
            raise EngineError("sme.no_question", "a consultation needs a question")
        if run_id is not None:
            self._ctx(run_id)  # the run must exist
        c_id = sme.new_id()
        try:
            if mode == "handoff":
                return self._sme_handoff(c_id, subject=subject, run_id=run_id, contact=contact, refs=list(refs or []), question=question)
            return self._sme_turn(c_id, 1, subject=subject, run_id=run_id, question=question, refs=list(refs or []), contact=contact,
                                  attach=[], worker=worker, wait=wait, timeout=timeout)
        except sme.SmeError as e:
            raise EngineError(e.code, str(e)) from e

    def sme_followup(self, c_id: str, question: str | None = None, refs: list[str] | None = None, attach: list[str] | None = None,
                     *, worker: str | None = None, wait: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """The next relay turn (§12.1): the prior turns plus new refs, a new question, or attachments (e.g. a person's reply)."""
        from . import sme

        try:
            w = sme.locate(self.project, c_id)
            cons = sme.consultation(w.log.events(), c_id)
            if cons["turns"] and cons["turns"][-1]["answer"] is None:
                raise sme.SmeError("sme.in_flight", f"{c_id} turn {cons['turns'][-1]['turn']} has no answer yet (wait for it)")
            if not (question or refs or attach):
                raise sme.SmeError("sme.empty_followup", "a follow-up needs a question, refs, or an attachment")
            if worker is None and cons["turns"]:
                worker = cons["turns"][-1]["requested"].get("worker")
                req, _v, el, _x = self._sme_routing(cons["subject"], self._ctx(w.run_id) if w.run_id else None)
                if worker not in [e["profile"] for e in el]:
                    worker = None
            turn = (cons["turns"][-1]["turn"] + 1) if cons["turns"] else 1
            return self._sme_turn(c_id, turn, subject=cons["subject"], run_id=w.run_id, question=question, refs=list(refs or []),
                                  contact=cons.get("contact"), attach=list(attach or []), worker=worker, wait=wait, timeout=timeout)
        except sme.SmeError as e:
            raise EngineError(e.code, str(e)) from e

    def _sme_turn(self, c_id: str, turn: int, *, subject: str, run_id: str | None, question: str | None, refs: list[str],
                  contact: str | None, attach: list[str], worker: str | None, wait: bool, timeout: float | None) -> dict[str, Any]:
        import secrets

        from . import adapters, sme, supervisor
        from .profiles import SetupError, build_env

        att_items = sme.attachments(attach, contact, self.project.root)  # read before any lock (paths are the caller's)

        def body() -> dict[str, Any]:
            ctx = self._ctx(run_id) if run_id else None
            req, _vocab, el, ex = self._sme_routing(subject, ctx)
            names = [e["profile"] for e in el]
            chosen = worker or (names[0] if names else None)
            if chosen is None:
                why = "; ".join(f"{x['profile']}: {'; '.join(x['reasons'])}" for x in ex) or "no worker profiles on this machine"
                raise sme.SmeError("sme.no_eligible_worker", f"no profile can answer as the {subject} expert ({why})")
            if chosen not in names:
                why = next(("; ".join(x["reasons"]) for x in ex if x["profile"] == chosen), "no such profile on this machine")
                raise sme.SmeError("sme.ineligible", f"{chosen} cannot answer as the {subject} expert: {why}")
            profile = self.project.profiles()[chosen]
            adapter = adapters.get(profile.adapter)
            src = sme.Sources(self.project, ctx)
            items, auto = sme.assemble(src, subject, refs)
            w = sme.where(self.project, c_id, run_id)
            cons = sme.consultation(w.log.events(), c_id)
            prior = sme.prior_items(w, cons, turn)
            idx = sme.index(src, subject, set(refs) | set(auto))
            mode = sme.workspace_mode(req)
            workspace = self.project.root if mode != "none" else None
            tdir = sme.turn_dir(w, turn)
            try:
                adapter.check_profile(profile)
                env = build_env(profile, home=self.project.home, packet_dir=tdir / "packet", result_dir=tdir / "result",
                                workspace=workspace, config_home_var=adapter.config_home_var, resolve=adapter.needs_executable)
            except SetupError as e:
                raise sme.SmeError(e.code, str(e)) from e
            cfg = self.project.config.effort
            band_s = cfg.seconds(cfg.default)
            deadline = supervisor.fmt(self.project.store.clock() + timedelta(seconds=band_s))
            sel = [i for i in items if i.ref in refs]
            aut = [i for i in items if i.ref not in refs]
            built = sme.build_packet(
                w, consultation_id=c_id, turn=turn, subject=subject, question=question, contact=contact,
                groups={"prior": prior, "attachments": att_items, "selected": sel, "auto": aut}, idx=idx, worker=chosen, profile=profile,
                deadline=deadline, workspace=mode, recipe=ctx.recipe.recipe.ref if ctx else None,
            )
            dispatch_id = f"d_{secrets.token_hex(4)}"

            def ents(group: str) -> list[dict[str, Any]]:
                return [{k: e[k] for k in ("ref", "label", "path", "sha256")} for e in built.entries if e["group"] == group]

            data: dict[str, Any] = {
                "consultation": c_id, "turn": turn, "subject": subject, "mode": "relay", "question": redact_text(question or ""),
                "refs": ents("selected"), "auto": ents("auto"), "attachments": ents("attachments"), "index": len(idx),
                "worker": chosen, "vendor": profile.vendor, "model": profile.model, "adapter": profile.adapter,
                "packet_sha256": built.sha256, "dispatch_id": dispatch_id, "deadline": deadline, "workspace": mode,
                "env": env.describe(),
            }
            if run_id:
                data["run"] = run_id
            if contact:
                data["contact"] = redact_text(contact)
            w.log.append("sme_requested", actor=self.director.actor, data=data)
            argv = adapter.command(profile, built.dir, built.result_dir, workspace, mode)
            if env.resolved is not None:
                argv = [env.resolved.executable, *argv[1:]]
            rel_baton = self.project.baton.resolve().relative_to(self.project.root.resolve()).as_posix()
            log_path = self.project.home / "logs" / (run_id or "project") / "sme" / c_id / f"turn-{turn}.log"
            spec = {
                "root": str(self.project.root), "home": str(self.project.home), "director": self.director.id,
                "run_id": run_id or "", "step_path": f"sme/{c_id}", "attempt": turn, "dispatch_id": dispatch_id,
                "worker": chosen, "adapter": adapter.name, "argv": argv, "env": env.env, "secret_names": env.secrets,
                "cwd": str(workspace or tdir), "log_path": str(log_path), "deadline": deadline, "band_s": band_s, "effort": cfg.default,
                "extend_once": False, "check_tree": getattr(adapter, "touches_files", False),
                "exclude": [f"{rel_baton}/runs", f"{rel_baton}/project"],
                "sme": {"consultation": c_id, "turn": turn, "run": run_id, "packet_sha256": built.sha256},
            }
            proc = supervisor.spawn(spec, log_path.with_suffix(".supervisor.log"))
            marker = supervisor.await_start(self.project.baton, dispatch_id, proc)
            out = {"consultation": c_id, "turn": turn, "subject": subject, "run_id": run_id, "worker": chosen, "dispatch_id": dispatch_id,
                   "packet": str(built.dir), "packet_sha256": built.sha256, "deadline": deadline, "warnings": []}
            if marker is None:
                w.log.append("sme_answered", data={"consultation": c_id, "turn": turn, "status": "failed", "classification": "platform",
                                                   "code": "supervisor_failed", "reasons": ["the supervisor did not start"]})
                out["state"] = "failed"
            elif supervisor.wake_path(self.project) is None:
                out["warnings"].append(f"{supervisor.NO_WAKE_WARNING}; check with `baton sme {c_id}` or `baton sme {c_id} --wait`")
            return out

        out = self._sme_locked(run_id, body)
        if wait and out.get("state") != "failed":
            return {**out, **self.sme_status(c_id, wait=True, timeout=timeout)}
        return out

    def sme_complete(self, spec: dict[str, Any], child: Any, changes: list[str]) -> dict[str, Any] | None:
        """The supervisor's end of a consultation turn: record the answer (or why there is none), fire hooks."""
        from . import adapters, sme, supervisor
        from .locks import project_lock

        info = spec["sme"]
        c_id, turn, run_id = info["consultation"], info["turn"], info.get("run")
        lock = self._run_lock(run_id) if run_id else project_lock(self.project.baton)
        with lock:
            w = sme.where(self.project, c_id, run_id)
            cons = sme.consultation(w.log.events(), c_id)
            t = next((x for x in cons["turns"] if x["turn"] == turn), None)
            if t is None or t["answer"] is not None:
                return None
            signals = getattr(adapters.get(spec["adapter"]), "failure_signals", None)
            data = self._sme_outcome(w, turn, info["packet_sha256"], child, changes, signals)
            w.log.append("sme_answered", actor=f"worker:{spec['worker']}", data={"consultation": c_id, "turn": turn, **data})
        outcome = "answered" if data["status"] == "answered" else "failed"
        fired = supervisor.fire_hooks(self.project, {
            "run_id": run_id or "", "step_path": f"sme/{c_id}", "outcome": outcome, "classification": data.get("classification"),
            "dispatch_id": spec["dispatch_id"], "needs_owner": False, "step_state": data["status"], "record": str(sme.turn_dir(w, turn)),
        })
        lock = self._run_lock(run_id) if run_id else project_lock(self.project.baton)
        with lock:
            for d in fired:
                w.log.append("completion_hook_fired" if d.get("ok") else "completion_hook_failed", data={**d, "consultation": c_id, "turn": turn})
        return data

    def _sme_outcome(self, w: Any, turn: int, packet_sha256: str, child: Any, changes: list[str], signals: Any) -> dict[str, Any]:
        from . import sme

        if changes:
            return {"status": "failed", "code": "workspace_modified", "changed": changes,
                    "reasons": [f"the expert changed the working tree ({', '.join(changes[:5])}); inspect it, Baton does not revert it"]}
        if child is not None and child.timed_out:
            return {"status": "failed", "classification": "subject", "code": "timeout", "reasons": [f"no answer within the time limit ({child.duration_s}s)"]}
        if (sme.turn_dir(w, turn) / "result" / "result.json").is_file():
            return sme.intake(w, turn, packet_sha256)
        cls = classify.classify_exit(child.exit_code, child.tail, signals) if child is not None else classify.supervisor_died()
        return {"status": "failed", "classification": cls["class"], "code": cls["code"], "reasons": [f"{cls['class']} failure ({cls['code']}): {cls['message']}"]}

    def sme_status(self, c_id: str, *, wait: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """A consultation: turns, answers (text), the expert's artifacts, what it waits for. ``wait`` blocks for the latest answer."""
        import time

        from . import sme, supervisor
        from .locks import project_lock

        try:
            w = sme.locate(self.project, c_id)
        except sme.SmeError as e:
            raise EngineError(e.code, str(e)) from e
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            cons = sme.consultation(w.log.events(), c_id)
            last = cons["turns"][-1] if cons["turns"] else None
            if last is None or last["answer"] is not None:
                break
            did = last["requested"].get("dispatch_id")
            lv = supervisor.liveness(self.project.baton, did)
            if not lv.elsewhere and not lv.supervisor_alive:
                # The supervisor is gone without recording the turn (§8.7 table): finish it here.
                if lv.worker_alive:
                    supervisor.kill_tree_pid(lv.marker["worker_pid"])
                lock = self._run_lock(w.run_id) if w.run_id else project_lock(self.project.baton)
                with lock:
                    cons2 = sme.consultation(w.log.events(), c_id)
                    if cons2["turns"][-1]["answer"] is None:
                        data = self._sme_outcome(w, last["turn"], last["requested"]["packet_sha256"], None, [], None)
                        w.log.append("sme_answered", data={"consultation": c_id, "turn": last["turn"], **data})
                supervisor.remove_marker(self.project.baton, did)
                continue
            if not wait or (end is not None and time.monotonic() >= end):
                break
            time.sleep(0.2)
        turns = []
        for t in cons["turns"]:
            a = t["answer"]
            entry: dict[str, Any] = {"turn": t["turn"], "question": t["requested"].get("question"), "worker": t["requested"].get("worker"),
                                     "refs": [r["ref"] for r in t["requested"].get("refs") or []], "auto": [r["ref"] for r in t["requested"].get("auto") or []],
                                     "attachments": [r["label"] for r in t["requested"].get("attachments") or []],
                                     "packet": str(sme.turn_dir(w, t["turn"]) / "packet")}
            if a is not None:
                entry["status"] = a["status"]
                if a.get("answer_sha256"):
                    entry["answer"] = json.loads(w.cas.read(a["answer_sha256"]))
                for k in ("reasons", "classification", "code", "awaiting"):
                    if a.get(k):
                        entry[k] = a[k]
                if a.get("artifacts"):
                    entry["artifacts"] = {n: str(sme.turn_dir(w, t["turn"]) / x["path"]) for n, x in a["artifacts"].items()}
            else:
                entry["status"] = "waiting_on_expert"
            turns.append(entry)
        return {"consultation": c_id, "subject": cons.get("subject"), "run_id": w.run_id, "contact": cons.get("contact"),
                "state": cons["state"], "turns": turns, "handoffs": cons["handoffs"], "promotions": cons["promotions"]}

    def sme_handoff(self, c_id: str) -> dict[str, Any]:
        """A copy-and-paste prompt to continue this consultation with the expert directly (§18 #17)."""
        from . import sme

        try:
            w = sme.locate(self.project, c_id)
            cons = sme.consultation(w.log.events(), c_id)
            refs: list[str] = []
            for t in cons["turns"]:
                refs += [r["ref"] for r in t["requested"].get("refs") or [] if r["ref"] not in refs]
            adapter = cons["turns"][-1]["requested"].get("adapter") if cons["turns"] else None
            return self._sme_handoff(c_id, subject=cons["subject"], run_id=w.run_id, contact=cons.get("contact"), refs=refs,
                                     question=None, adapter=adapter)
        except sme.SmeError as e:
            raise EngineError(e.code, str(e)) from e

    def _sme_handoff(self, c_id: str, *, subject: str, run_id: str | None, contact: str | None, refs: list[str],
                     question: str | None, adapter: str | None = None) -> dict[str, Any]:
        from . import sme

        def body() -> dict[str, Any]:
            ctx = self._ctx(run_id) if run_id else None
            req, _v, _el, _ex = self._sme_routing(subject, ctx)
            refusal = sme.handoff_refusal(req, adapter)
            if refusal:
                raise sme.SmeError("sme.handoff_refused", refusal)
            w = sme.where(self.project, c_id, run_id)
            cons = sme.consultation(w.log.events(), c_id)
            if question:
                cons["turns"] = [{"requested": {"question": question}}]
            items, _auto = sme.assemble(sme.Sources(self.project, ctx), subject, refs)
            prior = sme.prior_items(w, sme.consultation(w.log.events(), c_id), 10**9)
            text = sme.render_handoff(cons, subject, contact, items, prior)
            n = len(cons["handoffs"]) + 1
            path = sme.ensure_dir(w.dir) / ("handoff.md" if n == 1 else f"handoff-{n}.md")
            path.write_bytes(text.encode("utf-8"))
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            data: dict[str, Any] = {"consultation": c_id, "mode": "handoff", "subject": subject, "question": redact_text(question or ""),
                                    "refs": [{"ref": i.ref, "label": i.label, "sha256": i.sha256} for i in items],
                                    "path": path.relative_to(self.project.root).as_posix(), "handoff_sha256": sha}
            if run_id:
                data["run"] = run_id
            if contact:
                data["contact"] = redact_text(contact)
            w.log.append("sme_requested", actor=self.director.actor, data=data)
            return {"consultation": c_id, "mode": "handoff", "path": str(path), "sha256": sha, "handoff": text}

        return self._sme_locked(run_id, body)

    def promote_sme(self, c_id: str, target: str, note: str, *, text: str | None = None, turn: int | None = None,
                    artifact: str | None = None, from_artifact: str | None = None, feed: str = "revision_inputs") -> dict[str, Any]:
        """Bring an expert's answer into the work with the owner's agreement (§12.2), recorded verbatim.

        ``decision``: a ``human_decision`` steps may reference as ``human.<decision_id>`` (needs a run);
        ``fact``: a platform fact; ``lesson``: ``.baton/process/lessons.md``; ``proposal``: a process
        proposal file under ``.baton/process/proposals/`` (applied as a new recipe version by its maintainer);
        ``revision``: a human revision of a published artifact (``artifact`` = ``<step_path>.<name>``; the
        content is the expert's artifact ``from_artifact``, else the answer or ``text``), written to its
        published path (§10.5).
        """
        from . import sme

        if target not in sme.PROMOTE_TARGETS:
            raise EngineError("sme.bad_target", f"target must be one of {', '.join(sme.PROMOTE_TARGETS)}, got {target!r}")
        if not note.strip():
            raise EngineError("sme.no_note", "promotion needs the owner's agreement in their own words (--note)")
        try:
            w = sme.locate(self.project, c_id)
        except sme.SmeError as e:
            raise EngineError(e.code, str(e)) from e
        cons = sme.consultation(w.log.events(), c_id)
        answered = [t for t in cons["turns"] if t["answer"] and t["answer"]["status"] == "answered"]
        chosen = next((t for t in answered if t["turn"] == turn), None) if turn is not None else (answered[-1] if answered else None)
        if turn is not None and chosen is None:
            raise EngineError("sme.no_answer", f"{c_id} has no answered turn {turn}")
        if target == "revision":
            return self._promote_revision(w, cons, chosen, c_id, note, text, artifact, from_artifact, feed)
        if artifact is not None or from_artifact is not None:
            raise EngineError("sme.bad_target", "--artifact and --from are only for target revision")
        if chosen is None and not (text or "").strip():
            raise EngineError("sme.no_answer", f"{c_id} has no recorded answer; give the content to promote with --text")
        content = text if (text or "").strip() else json.loads(w.cas.read(chosen["answer"]["answer_sha256"]))["answer"]
        content = redact_text(content)
        n = chosen["turn"] if chosen else None
        now = self.project.store.clock()
        promoted: dict[str, Any] = {"consultation": c_id, "turn": n, "target": target, "note": note,
                                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(), "edited": bool((text or "").strip())}
        out: dict[str, Any] = {"consultation": c_id, "target": target, "turn": n}
        if target == "decision":
            if w.run_id is None:
                raise EngineError("sme.decision_needs_run", "only a consultation about a run can be promoted to a decision of that run")

            def body(ctx: RunContext) -> dict[str, Any]:
                decision_id = f"d{ctx.log.state().last_seq + 1}"
                ctx.log.append("human_decision", actor="human", data={
                    "ref": f"sme:{c_id}", "kind": "sme", "decision": content, "note": note, "decision_id": decision_id,
                    "consultation": c_id, "turn": n, "recorded_by": self.director.actor,
                })
                ctx.log.append("sme_promoted", actor="human", data={**promoted, "decision_id": decision_id})
                return {"decision_id": decision_id, "reference": f"human.{decision_id}"}

            return {**out, **self._mutate(w.run_id, body, allow_closed=True)}
        source = f"expert consultation {c_id}" + (f" turn {n}" if n else "") + f"; owner: \"{redact_text(note)}\""
        if target == "fact":
            out["entry"] = sme.add_fact(self.project.baton, content, source, now)
            sme.project_append(self.project, "platform_fact_recorded", {"fact": content, "source": f"consultation {c_id}", "consultation": c_id,
                                                                        "turn": n, "note": note}, actor="human")
        elif target == "lesson":
            out["entry"] = sme.add_lesson(self.project.baton, content, f"consultation {c_id}", now)
        else:
            p = sme.write_proposal(self.project.baton, c_id, n or 0, content, note, cons.get("subject") or "?", now)
            out["path"] = str(p)
            promoted["path"] = p.relative_to(self.project.root).as_posix()

        def record() -> dict[str, Any]:
            w.log.append("sme_promoted", actor="human", data=promoted)
            return {}

        self._sme_locked(w.run_id, record)
        cp = self._project_checkpoint(f"expert answer {c_id} promoted ({target})")
        if cp is not None:
            out["checkpoint"] = cp.as_dict()
        return out

    def _promote_revision(self, w: Any, cons: dict[str, Any], chosen: Any, c_id: str, note: str, text: str | None,
                          artifact: str | None, from_artifact: str | None, feed: str) -> dict[str, Any]:
        from . import publish

        if w.run_id is None:
            raise EngineError("sme.revision_needs_run", "only a consultation about a run can be promoted to a revision of that run's artifact")
        if not artifact or "." not in artifact:
            raise EngineError("sme.revision_needs_artifact", "give the artifact to revise as --artifact <step_path>.<name>")
        step_path, name = artifact.rsplit(".", 1)
        if from_artifact is not None:
            turns = [chosen] if chosen is not None else []
            arts = ((turns[0]["answer"] or {}).get("artifacts") or {}) if turns else {}
            if from_artifact not in arts:
                raise EngineError("sme.no_artifact", f"{c_id} turn {chosen['turn'] if chosen else '?'} returned no artifact {from_artifact!r} (it has {sorted(arts) or 'none'})")
            content = w.cas.read(arts[from_artifact]["sha256"])
            try:
                content = redact_text(content.decode("utf-8")).encode("utf-8")
            except UnicodeDecodeError:
                pass
        elif (text or "").strip():
            content = redact_text(text or "").encode("utf-8")
        elif chosen is not None:
            content = redact_text(json.loads(w.cas.read(chosen["answer"]["answer_sha256"]))["answer"]).encode("utf-8")
        else:
            raise EngineError("sme.no_answer", f"{c_id} has no recorded answer; give the content with --text or --from")
        n = chosen["turn"] if chosen else None

        def body(ctx: RunContext) -> dict[str, Any]:
            res = publish.ingest_sme(ctx, step_path, name, content, note=note, feed=feed, actor="human",
                                     extra={"recorded_by": self.director.actor, "consultation": c_id, "turn": n},
                                     decision={"ref": f"sme:{c_id}", "kind": "sme", "decision": "revision"})
            ctx.log.append("sme_promoted", actor="human", data={
                "consultation": c_id, "turn": n, "target": "revision", "note": note, "content_sha256": res["sha256"],
                "decision_id": res["decision_id"], "artifact": artifact, "path": res["path"], **({"from": from_artifact} if from_artifact else {}),
            })
            return res

        return {"consultation": c_id, "target": "revision", "turn": n, **self._mutate(w.run_id, body)}

    def detect(self) -> dict[str, Any]:
        from .adopt import detect

        return detect(self.project.root, home=self.project.home, director=self.director)

    def _active_adoption(self) -> str | None:
        for rid in self.project.store.run_ids():
            log = self.project.store.run(rid)
            ev = log.events()
            if ev and ev[0].data.get("kind") == "adoption" and log.state().state == "active":
                return rid
        return None

    def frame(self, words: str) -> dict[str, Any]:
        """Start a framing run from the owner's goal in their words (§11.6), or report the one awaiting its decision."""
        from . import frame as framing
        from .project import slugify

        for rid in self.project.store.run_ids():
            log = self.project.store.run(rid)
            if framing.is_framing(log.events()) and log.state().state == "active":
                return {**framing.status(self, rid), "started": False}
        if not (words or "").strip():
            raise EngineError("frame.no_words", "framing starts from the owner's goal in their own words (--note)")
        inputs = framing.inputs_for(self.project, words)
        ctx = start(self.project.store, self.project.recipe(framing.FRAME_RECIPE), inputs, title=inputs["title"],
                    project=self.project.variables(), actor=self.director.actor,
                    work_item={"kind": "framing", "slug": slugify(inputs["title"]), "branch": self.project.branch()})
        leases = self._leases(ctx)
        leases.ensure()
        self._after(ctx, leases, 0, {})
        return {**framing.status(self, ctx.run_id), "started": True}

    def frame_status(self, run_id: str) -> dict[str, Any]:
        from . import frame as framing

        return framing.status(self, run_id)

    def adopt(self, recipe: str, *, crosswalk: str | None = None, scope: list[str] | None = None) -> dict[str, Any]:
        """Start an adoption run (§11.1), or report the one in progress."""
        from . import adopt as ad

        active = self._active_adoption()
        if active is not None:
            return {**self.adoption_status(active), "started": False}
        ref = self.vendor(recipe)["recipe"] if Path(recipe).is_dir() else self.project.resolve_ref(recipe)
        loaded = self.project.recipe(ref)
        root = self.project.root
        files = ad.scope_files(root, scope)
        counts = ad.check_scope(files)
        cw = ad.load_crosswalk(crosswalk, loaded, root) if crosswalk else None
        situation = ad.detect(root, home=self.project.home, director=self.director, machine=False)
        inputs: dict[str, Any] = {
            "title": f"Adopt {root.name} into {ref}", "recipe": ad.recipe_summary(loaded), "candidates": ad.match_candidates(cw, files, root),
            "scope": list(scope or ["."]), "situation": {"project": situation["project"], "runs": situation["runs"]},
        }
        if cw is not None:
            inputs["crosswalk"] = cw
        from .project import slugify

        work_item = {"kind": "adoption", "slug": slugify(f"adopt-{ref}"), "branch": self.project.branch(), "adoption_of": ref}
        if cw is not None:
            work_item["crosswalk"] = cw["id"]
        ctx = start(self.project.store, self.project.recipe(ad.ADOPT_RECIPE), inputs, title=inputs["title"], project=self.project.variables(),
                    actor=self.director.actor, work_item=work_item)
        ctx.log.append("situation_detected", data={"situation": inputs["situation"], "scope": {"paths": inputs["scope"], **counts}, "recipe": ref,
                                                   **({"crosswalk": cw["id"]} if cw else {}), "candidates": len(inputs["candidates"])})
        leases = self._leases(ctx)
        leases.ensure()
        self._after(ctx, leases, 0, {})
        return {**self.adoption_status(ctx.run_id), "started": True}

    def adoption_status(self, adoption: str) -> dict[str, Any]:
        """Where an adoption stands: research, the work-item runs and their triage, the baseline."""
        from .adopt import baseline_path

        ctx = self._ctx(adoption)
        started = ctx.record().started
        if started.get("kind") != "adoption":
            raise EngineError("adopt.not_adoption", f"run {adoption} is not an adoption run")
        st = self.status(adoption)
        rr = ctx.record().last("research_recorded")
        items: dict[str, Any] = {}
        pending_triage = []
        for key, rid in sorted((rr.data.get("runs") if rr else {}).items()):
            wst = self.status(rid)
            cx = self.project.recipe_for_run(rid).recipe.complexity
            tri = wst["steps"].get(cx.triage_step, {}).get("state") if cx else None
            items[key] = {"run_id": rid, "title": wst["title"], "state": wst["state"], "triage": tri}
            if cx and wst["state"] == "active" and tri != "passed":
                pending_triage.append(f"{rid} {cx.triage_step}")
        bp = baseline_path(self.project.baton, adoption)
        research = st["steps"]["research"]["state"]
        if st["state"] != "active":
            nxt = "adoption finished"
        elif research != "passed":
            nxt = f"dispatch research (`baton eligible {adoption} research`)"
        elif pending_triage:
            nxt = "dispatch triage in each work-item run: " + ", ".join(pending_triage)
        elif bp.is_file():
            nxt = f"the owner reviews {bp.relative_to(self.project.root).as_posix()}, then `baton establish-baseline {adoption} --note \"<their words>\"`"
        else:
            nxt = "waiting for the baseline proposal"
        return {
            "adoption": adoption, "recipe": started.get("adoption_of"), "crosswalk": started.get("crosswalk"), "state": st["state"],
            "research": research, "runs": items, "history": (rr.data.get("history") if rr else []) or [], "gaps": (rr.data.get("gaps") if rr else []) or [],
            "baseline": bp.relative_to(self.project.root).as_posix() if bp.is_file() else None, "next": nxt,
            "ready": st["ready"], "pending_decisions": st["pending_decisions"], "needs_owner": st["needs_owner"],
        }

    def _adoption_progress(self, ctx: RunContext) -> list[Path]:
        """After a change to an adoption or work-item run: start the work-item runs, then write the baseline proposal (§11.1).

        Returns the files and run directories the checkpoint must commit with this run.
        """
        from . import adopt as ad

        started = ctx.record().started
        if started.get("kind") == "adoption":
            actx = ctx
        elif started.get("adoption"):
            actx = self._ctx(started["adoption"]["run"])
        else:
            return []
        if actx.log.state().state != "active" or not awaiting_baseline(actx.log.events(), kind="adoption"):
            return []
        if actx.log.state().step("research").state != "passed":
            return []
        extra: list[Path] = []
        rr = actx.record().last("research_recorded")
        if rr is None:
            if actx is not ctx:
                return []
            extra += self._start_work_items(actx)
            rr = actx.record().last("research_recorded")
        bp = ad.baseline_path(self.project.baton, actx.run_id)
        if bp.is_file():
            return extra
        runs = {}
        for key, rid in (rr.data.get("runs") or {}).items():
            rctx = ctx if rid == ctx.run_id else self._ctx(rid)
            if rctx.log.state().state != "active":
                continue
            cx = rctx.recipe.recipe.complexity
            if cx is not None and rctx.log.state().step(cx.triage_step).state != "passed":
                return extra  # still being triaged
            runs[key] = rctx
        research = json.loads(actx.log.cas.read(actx.record().registered("research")["output_sha256"]))
        doc = ad.propose(self.project, actx, research, runs, rr.data.get("history") or [], rr.data.get("gaps") or [])
        from .locks import project_lock

        with project_lock(self.project.baton):
            ad.write_baseline(bp, doc)
        return [*extra, bp]

    def _start_work_items(self, actx: RunContext) -> list[Path]:
        """One run of the target recipe per in-flight work item research found (§11.1 step 3)."""
        from . import adopt as ad, docs

        reg = actx.record().registered("research")
        research = json.loads(actx.log.cas.read(reg["output_sha256"]))
        target = self.project.recipe(actx.record().started["adoption_of"])
        items, history, gaps = ad.work_items(research, target)
        runs: dict[str, str] = {}
        paths: list[Path] = []
        for w in items:
            inputs = w["inputs"]
            wctx = start(
                self.project.store, target, inputs, title=w["title"], project=self.project.variables(), actor="runtime",
                work_item={"kind": inputs.get("kind"), "slug": self.project.render_slug(inputs, w["title"]), "branch": self.project.branch(),
                           "adoption": {"run": actx.run_id, "work_item": w["key"]}},
            )
            sha = wctx.log.cas.put(canonical_json({**research, "work_item": w["key"]}).encode("utf-8"))
            wctx.log.append("research_recorded", data={"research_sha256": sha, "adoption": actx.run_id, "work_item": w["key"]})
            docs.write_records(wctx)
            runs[w["key"]] = wctx.run_id
            paths.append(wctx.run_dir)
        actx.log.append("research_recorded", data={"research_sha256": reg["output_sha256"], "runs": runs, "history": history, "gaps": gaps})
        return paths

    def establish_baseline(self, adoption: str, note: str) -> dict[str, Any]:
        """Apply the (owner-reviewed) baseline proposal as the owner's one adoption decision (§11.5)."""
        from . import adopt as ad, docs
        from .project import PROJECT_FILE

        if not note.strip():
            raise EngineError("baseline.note_required", "establishing the baseline is the owner's decision; record their words with --note")
        extra: list[Path] = []

        def body(actx: RunContext) -> dict[str, Any]:
            if actx.record().started.get("kind") != "adoption":
                raise EngineError("adopt.not_adoption", f"run {adoption} is not an adoption run")
            if not awaiting_baseline(actx.log.events(), kind="adoption"):
                raise EngineError("baseline.not_pending", f"adoption {adoption} has no baseline waiting")
            rr = actx.record().last("research_recorded")
            bp = ad.baseline_path(self.project.baton, adoption)
            if rr is None or not bp.is_file():
                raise EngineError("baseline.not_ready", f"adoption {adoption} has no baseline proposal yet: {self.adoption_status(adoption)['next']}")
            doc = ad.load_baseline(bp)
            runs = {k: c for k, rid in (rr.data.get("runs") or {}).items() if (c := self._ctx(rid)).log.state().state == "active"}
            problems = ad.check_baseline(self.project, actx, doc, runs, doc)
            if problems:
                raise EngineError("baseline.invalid", "the baseline cannot be applied: " + "; ".join(problems))
            for wctx in runs.values():
                self._leases(wctx).ensure()  # before anything is recorded: a run held elsewhere refuses the whole baseline
            bsha = actx.log.cas.put(bp.read_bytes())
            decision_id = f"d{actx.log.state().last_seq + 1}"
            actx.log.append("human_decision", actor="human", data={
                "ref": "baseline", "kind": "baseline", "decision": "establish", "note": note, "decision_id": decision_id,
                "baseline_sha256": bsha, "recorded_by": self.director.actor,
            })
            applied: dict[str, Any] = {}
            for key, wctx in runs.items():
                item = next(w for w in doc["work_items"] if w.get("key") == key)
                with self._run_lock(wctx.run_id):
                    o = apply_baseline(wctx, item, adoption=adoption, decision_id=decision_id)
                    docs.write_records(wctx)
                applied[key] = {"run_id": wctx.run_id, "outcome": o.outcome, "ready": o.ready, "state": wctx.log.state().state}
                extra.append(wctx.run_dir)
            actx.log.append("baseline_established", actor="human", data={
                "baseline_sha256": bsha, "decision_id": decision_id, "note": note, "runs": {k: c.run_id for k, c in runs.items()},
            })
            if ad.merge_project_yaml(self.project.baton / PROJECT_FILE, doc.get("project_yaml") or {}):
                extra.append(self.project.baton / PROJECT_FILE)
            if ad.apply_agents_md(self.project.root, doc.get("agents_md") or {}):
                extra.append(self.project.root / ((doc.get("agents_md") or {}).get("path") or "AGENTS.md"))
            extra.append(bp)
            refresh(actx)
            return {"adoption": adoption, "decision_id": decision_id, "runs": applied, "state": actx.log.state().state}

        return self._mutate(adoption, body, extra=extra)

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


def _position(st: dict[str, Any]) -> dict[str, Any]:
    """Where a run is: top-level steps done of total, and the ones in progress."""
    top = {p: s for p, s in st["steps"].items() if "review_of" not in s}
    done = [p for p, s in top.items() if s["state"] in ("passed", "skipped", "imported")]
    current = [p for p, s in top.items() if s["state"] not in ("passed", "skipped", "imported", "blocked_on_deps")]
    return {"done": len(done), "total": len(top), "current": current}


def _holder_text(h: dict[str, Any]) -> str:
    if h.get("reserved"):
        return f"a queued dispatch of {h.get('step_path')} (run {h.get('run_id')}) that is starting"
    return f"{h.get('step_path')} of run {h.get('run_id')} (dispatch {h.get('dispatch_id')})"


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
        if e.type == "step_passed" and e.data.get("confirmed"):
            phrases.append(f"{e.step_path} confirmed unchanged by the owner")
        elif e.type == "step_passed" and (e.data.get("condition") or {}).get("gates_passed") is False:
            phrases.append(f"{e.step_path} judged not done [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "step_passed":
            phrases.append(f"{e.step_path} passed [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "step_escalated":
            phrases.append(f"{e.step_path} escalated ({e.data.get('reason')}) [attempt {e.attempt}, {profile(e)}]")
        elif e.type == "human_decision" and e.data.get("kind") == "sme":
            phrases.append(f"expert answer promoted ({e.data.get('consultation')}) as {e.data.get('decision_id')}")
        elif e.type == "human_decision" and e.data.get("kind") == "skip_notice":
            phrases.append(f"{e.data.get('ref')} acknowledged")
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
