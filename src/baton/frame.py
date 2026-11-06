"""Framing new work (§11.6): an owner's goal becomes work items they choose from.

A **framing run** is a run of the built-in recipe ``baton-frame@1``. Its one step,
``frame``, proposes ``parts`` (``baton-frame/1``); once its declared gates pass, an
implicit human gate ``select`` waits on the owner. ``decide <run> frame select
--items <ids> --note "<words>"`` records the decision, starts one run per selected
part with its proposed recipe and inputs (``run_started.framing {run, part}``),
and records ``framing_selected``; the framing run then completes. A part whose
recipe is shipped with the runtime but not vendored here has it vendored on
selection: the owner's selection is the approval (a shipped recipe is as trusted
as the runtime). A proposal that cannot start is a gap, never a run.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .packet import EngineError

FRAME_RECIPE = "baton-frame@1"
FRAME_STEP = "frame"
SELECT_GATE = "select"
FRAME_DECISIONS = ("select", "reject")
FIT_CHECK = "fit-check"


def is_framing(events: list[Any]) -> bool:
    return bool(events) and events[0].type == "run_started" and events[0].data.get("kind") == "framing"


def awaiting_selection(events: list[Any]) -> bool:
    """Whether a framing run still waits for the owner's selection to be applied (it completes only then)."""
    return is_framing(events) and not any(e.type == "framing_selected" for e in events)


# ---------------------------------------------------------------------------
# Run inputs
# ---------------------------------------------------------------------------


def _summary(loaded: Any, vendored: bool) -> dict[str, Any]:
    r = loaded.recipe
    schema = loaded.schemas[r.run_inputs.schema_] if r.run_inputs is not None else None
    return {
        "id": r.id, "version": r.version, "description": r.description or "",
        "levels": list(r.complexity.levels) if r.complexity else [], "run_inputs": schema, "vendored": vendored,
    }


def recipe_listing(project: Any) -> list[dict[str, Any]]:
    """Every recipe a part may propose: each vendored recipe (its newest version), then each shipped one not vendored."""
    from .project import catalog

    out: dict[str, dict[str, Any]] = {}
    for ref in project.vendored():
        loaded = project.recipe(ref)
        prev = out.get(loaded.recipe.id)
        if prev is None or loaded.recipe.version > prev["version"]:
            out[loaded.recipe.id] = _summary(loaded, True)
    for rid, loaded in catalog().items():
        if rid not in out:
            out[rid] = _summary(loaded, False)
    return [out[k] for k in sorted(out)]


def rubric(project: Any) -> str | None:
    """fit-check's rubric: from the vendored fit-check (newest version), else the shipped one."""
    from .project import catalog

    for ref in reversed(project.vendored()):
        if ref.split("@", 1)[0] == FIT_CHECK:
            p = project.recipe(ref).root / "static" / "rubric.md"
            if p.is_file():
                return p.read_text(encoding="utf-8-sig")
    shipped = catalog().get(FIT_CHECK)
    if shipped is not None and (shipped.root / "static" / "rubric.md").is_file():
        return (shipped.root / "static" / "rubric.md").read_text(encoding="utf-8-sig")
    return None


def inputs_for(project: Any, words: str) -> dict[str, Any]:
    title = " ".join(words.split())
    out: dict[str, Any] = {
        "title": "Frame: " + (title if len(title) <= 60 else title[:57].rstrip() + "..."),
        "words": words, "recipes": recipe_listing(project),
    }
    rb = rubric(project)
    if rb is not None:
        out["rubric"] = rb
    return out


# ---------------------------------------------------------------------------
# The implicit select gate
# ---------------------------------------------------------------------------


def frame_output(ctx: Any, n: int) -> dict[str, Any]:
    import json

    sub = next((e for e in reversed(ctx.record().attempt_events(FRAME_STEP, n)) if e.type == "result_submitted"), None)
    sha = (sub.data.get("output_sha256") if sub else None)
    return json.loads(ctx.log.cas.read(sha)) if sha else {}


def open_select_gate(ctx: Any, step_path: str, n: int) -> Any:
    """After ``frame``'s declared gates pass: the owner chooses parts (§11.6). ``None`` when not applicable."""
    from .engine import Outcome

    if step_path != FRAME_STEP or not is_framing(ctx.log.events()):
        return None
    if any(e.type == "gate_passed" and e.data.get("gate") == SELECT_GATE for e in ctx.record().attempt_events(step_path, n)):
        return None
    out = frame_output(ctx, n)
    parts = out.get("parts") or []
    listing = "; ".join(str(p.get("label")) for p in parts)
    prompt = (f"Goal: {out.get('goal', '')} Parts: {listing}. Which should be included now? "
              "Each chosen part starts what its option's next says, usually a first look rather than the work itself. "
              "(Select any or all; selecting none ends framing. Reject: the breakdown is redone with your note.)")
    ctx.log.append("human_gate_opened", step_path=step_path, attempt=n, data={
        "gate": SELECT_GATE, "type": SELECT_GATE, "implicit": True, "advisory": False, "prompt": prompt, "ref": step_path,
        "parts": [{"id": p.get("id"), "label": p.get("label")} for p in parts],
    })
    return Outcome(step_path, n, "needs_human", [prompt])


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _plan_part(api: Any, part: dict[str, Any], active: int) -> tuple[dict[str, Any] | None, str | None]:
    """``(plan, None)``: what to start for one selected part; ``(None, reason)``: a gap."""
    from . import publish
    from .project import catalog

    project = api.project
    prop = part.get("proposal") or {}
    if "fit_check" in prop:
        rid = FIT_CHECK
        fc = prop["fit_check"]
        inputs: Any = {"title": fc.get("title") or part.get("label") or part.get("id"), "idea": fc["idea"]}
    else:
        rid = str(prop.get("recipe") or "")
        inputs = prop.get("inputs")
    want_id, _, want_ver = rid.partition("@")
    loaded = None
    vendor_from = None
    try:
        loaded = project.recipe(project.resolve_ref(rid))
    except EngineError:
        shipped = catalog().get(want_id)
        if shipped is not None and (not want_ver or int(want_ver) == shipped.recipe.version):
            loaded, vendor_from = shipped, shipped.root
    if loaded is None:
        return None, f"the proposed process {rid!r} is neither in this project nor shipped with Baton"
    if not isinstance(inputs, dict):
        return None, f"no starting details were proposed for {loaded.recipe.ref}"
    if loaded.recipe.run_inputs is not None:
        v = Draft202012Validator(loaded.schemas[loaded.recipe.run_inputs.schema_], format_checker=Draft202012Validator.FORMAT_CHECKER)
        errors = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(inputs)]
        if errors:
            return None, f"the proposed starting details do not fit {loaded.recipe.ref}: " + "; ".join(errors)
    missing = publish.missing_path_keys(loaded.recipe, project.config.paths)
    if missing:
        return None, (f"{loaded.recipe.ref} delivers files to paths.{', paths.'.join(missing)}, which project.yaml does not map "
                      "(add them under paths:)")
    limit = project.config.limits.active_runs
    if limit is not None and active >= limit:
        return None, f"project.yaml limits.active_runs is {limit} and that many pieces of work are already active"
    return {"part": part["id"], "recipe": loaded, "vendor_from": vendor_from, "inputs": inputs,
            "title": inputs.get("title") or part.get("label")}, None


FIT_CHECK_NEXT = "a fit check: a few questions and a recommendation, no commitment"
REJECT_NEXT = "the breakdown is redone with what you said"


def _active_others(api: Any, run_id: str) -> int:
    store = api.project.store
    return sum(1 for r in store.run_ids() if r != run_id and store.run(r).state().state == "active")


def part_next(api: Any, part: dict[str, Any], active: int) -> str:
    """What choosing one part triggers, in process-neutral words (§11.6; Decision 0071)."""
    plan, why = _plan_part(api, part, active)
    if plan is None:
        return f"can't start yet: {why}"
    r = plan["recipe"].recipe
    if r.id == FIT_CHECK and "fit_check" in (part.get("proposal") or {}):
        return FIT_CHECK_NEXT
    return f"starts {r.id}: {r.description or ''}".rstrip(": ")


def annotate_next(api: Any, ctx: Any, pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give a framing run's select options their ``next``, computed from the record (Decision 0071)."""
    if not pending or not is_framing(ctx.log.events()):
        return pending
    for p in pending:
        if p.get("ref") != FRAME_STEP or p.get("kind") != "gate":
            continue
        out = frame_output(ctx, p["attempt"])
        active = _active_others(api, ctx.run_id)
        for o in p.get("options") or []:
            if o["decision"] == "select":
                o["next"] = [{"part": q.get("id"), "label": q.get("label"), "next": part_next(api, q, active)}
                             for q in out.get("parts") or []]
            elif o["decision"] == "reject":
                o["next"] = REJECT_NEXT
    return pending


def select(api: Any, ctx: Any, ref: str, decision: str, note: str, items: list[str] | None, paths: list[Any]) -> dict[str, Any]:
    """``decide <framing run> frame select --items <ids> --note "<owner's words>"`` (§11.6)."""
    from . import docs
    from .engine import _registered, refresh, start
    from .project import vendor

    log = ctx.log
    if not is_framing(log.events()):
        raise EngineError("frame.not_framing", f"run {ctx.run_id} is not a framing run; select is only for a framing run's {FRAME_STEP} gate")
    if decision != "select":
        raise EngineError("decide.bad_decision", "--items goes with the select decision")
    if ref != FRAME_STEP:
        raise EngineError("decide.bad_decision", f"select is decided on {FRAME_STEP!r}, got {ref!r}")
    st = log.state().step(FRAME_STEP)
    n = st.attempt
    opened = ctx.record().last("human_gate_opened", FRAME_STEP, n) if st.state == "awaiting_human" else None
    if opened is None or opened.data.get("gate") != SELECT_GATE:
        raise EngineError("decide.nothing_pending", f"{FRAME_STEP} is not waiting on the owner's selection (it is {st.state})")
    if not note.strip():
        raise EngineError("decide.note_required", "--note is required: the owner's words, including their confirmation")
    chosen = list(items or [])
    out = frame_output(ctx, n)
    parts = {p["id"]: p for p in out.get("parts") or []}
    unknown = [i for i in chosen if i not in parts]
    if unknown:
        raise EngineError("frame.unknown_part", f"unknown part(s) {', '.join(unknown)}; the parts are {', '.join(parts)}")
    if len(set(chosen)) != len(chosen):
        raise EngineError("frame.duplicate_part", "a part is selected more than once")

    store = api.project.store
    active = sum(1 for r in store.run_ids() if store.run(r).state().state == "active" and r != ctx.run_id)
    plans: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for pid in chosen:
        plan, why = _plan_part(api, parts[pid], active)
        if plan is None:
            gaps.append({"part": pid, "label": parts[pid].get("label"), "reason": why})
        else:
            plans.append(plan)
            active += 1

    decision_id = f"d{log.state().last_seq + 1}"
    log.append("human_decision", actor="human", step_path=FRAME_STEP, attempt=n, data={
        "ref": FRAME_STEP, "kind": "frame", "gate": SELECT_GATE, "decision": "select", "items": chosen, "note": note,
        "decision_id": decision_id, "recorded_by": api.director.actor,
    })
    log.append("gate_passed", step_path=FRAME_STEP, attempt=n, data={"gate": SELECT_GATE, "type": SELECT_GATE, "implicit": True, "items": chosen})
    log.append("step_passed", step_path=FRAME_STEP, attempt=n, data=_registered(ctx, FRAME_STEP, n))

    vendored: list[str] = []
    runs: list[dict[str, Any]] = []
    for plan in plans:
        loaded = plan["recipe"]
        if plan["vendor_from"] is not None:
            res = vendor(api.project, plan["vendor_from"])
            if res["changed"]:
                vendored.append(res["recipe"])
            loaded = api.project.recipe(res["recipe"])
            paths += [api.project.recipes_dir / res["recipe"], api.project.baton / "baton.lock"]
        inputs = plan["inputs"]
        wctx = start(
            store, loaded, inputs, title=plan["title"], project=api.project.variables(), actor="runtime",
            work_item={"kind": inputs.get("kind"), "slug": api.project.render_slug(inputs, plan["title"]),
                       "branch": api.project.branch(), "framing": {"run": ctx.run_id, "part": plan["part"]}},
        )
        docs.write_records(wctx)
        paths.append(wctx.run_dir)
        runs.append({"part": plan["part"], "run": wctx.run_id, "recipe": loaded.recipe.ref})
    log.append("framing_selected", actor="human", data={
        "decision_id": decision_id, "selected": chosen, "runs": runs, "gaps": gaps, **({"vendored": vendored} if vendored else {}),
    })
    refresh(ctx)
    return {"framing": ctx.run_id, "decision_id": decision_id, "selected": chosen, "runs": runs, "gaps": gaps, "vendored": vendored,
            "state": log.state().state, "outcome": "selected", "step_path": FRAME_STEP, "attempt": n}


def status(api: Any, run_id: str) -> dict[str, Any]:
    """Where a framing run stands: the step, the proposed parts once it has them, and what was started."""
    ctx = api._ctx(run_id)
    events = ctx.log.events()
    if not is_framing(events):
        raise EngineError("frame.not_framing", f"run {run_id} is not a framing run")
    st = api.status(run_id)
    step = ctx.log.state().step(FRAME_STEP)
    sel = ctx.record().last("framing_selected")
    out: dict[str, Any] = {
        "framing": run_id, "state": st["state"], "step": step.state, "words": None,
        "pending_decisions": st["pending_decisions"], "needs_owner": st["needs_owner"], "ready": st["ready"],
    }
    import json

    started = ctx.record().started
    try:
        out["words"] = json.loads(ctx.log.cas.read(started["inputs_sha256"])).get("words")
    except Exception:  # noqa: BLE001 - informational only
        pass
    if step.state == "awaiting_human" or sel is not None:
        fo = frame_output(ctx, step.attempt)
        out["goal"] = fo.get("goal")
        out["parts"] = fo.get("parts") or []
        out["assumptions"] = fo.get("assumptions") or []
    if sel is not None:
        out.update(selected=sel.data.get("selected"), runs=sel.data.get("runs"), gaps=sel.data.get("gaps"))
        out["next"] = "framing finished"
    elif step.state == "awaiting_human":
        out["next"] = (f"confirm the goal with the owner, let them choose parts, confirm back, then "
                       f"`baton decide {run_id} frame select --items <ids> --note \"<their words>\"`")
    elif step.state == "escalated":
        out["next"] = "the framing step needs the owner (see pending_decisions)"
    else:
        out["next"] = f"dispatch the framing step (`baton eligible {run_id} frame`)"
    return out
