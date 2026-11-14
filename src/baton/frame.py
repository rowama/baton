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

from . import diag
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


def _summary(loaded: Any, vendored: bool, with_scope: bool = False) -> dict[str, Any]:
    r = loaded.recipe
    schema = loaded.schemas[r.run_inputs.schema_] if r.run_inputs is not None else None
    out = {
        "id": r.id, "version": r.version, "description": r.description or "",
        "levels": list(r.complexity.levels) if r.complexity else [], "run_inputs": schema, "vendored": vendored,
    }
    if with_scope:  # the `catalog.summaries` input (§5.2) also carries what the recipe covers (§5.1)
        out["scope"] = r.scope.model_dump(mode="json") if r.scope is not None else None
        if r.project_inputs:  # and the project documents it can build on, by role (Decisions 0142, 0148)
            out["project_inputs"] = [p.model_dump(mode="json", exclude_none=True) for p in r.project_inputs]
    return out


def recipe_listing(project: Any, with_scope: bool = False) -> list[dict[str, Any]]:
    """Every recipe a part may propose: each vendored recipe (its newest version), then each shipped one not vendored.

    Also the ``catalog.summaries`` input of an ordinary step (§5.2; Decision 0106), which adds each recipe's ``scope``.
    """
    from .project import catalog

    from .packet import EngineError

    out: dict[str, dict[str, Any]] = {}
    try:
        vendored = project.vendored()
    except EngineError as e:  # a bare store with no lockfile (a test or an unadopted directory) vendors nothing
        if e.code != "project.no_lock":
            raise
        vendored = []
    for ref in vendored:
        loaded = project.recipe(ref)
        prev = out.get(loaded.recipe.id)
        if prev is None or loaded.recipe.version > prev["version"]:
            out[loaded.recipe.id] = _summary(loaded, True, with_scope)
    for rid, loaded in catalog().items():
        if rid not in out:
            out[rid] = _summary(loaded, False, with_scope)
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


PLAN_ARTIFACT = "process_plan"
#: Folders used when project.yaml maps no ``paths.process_plans`` / ``paths.notes`` (Decision 0069).
DEFAULT_PATHS = {"process_plans": "docs", "notes": "docs"}


SLUG_MAX = 40
# Words an opening request starts with before it names the goal: a subject pronoun, wanting or
# asking verbs, an action verb, an article ("I want to start a", "help me build a", "I need a").
LEAD_WORDS = frozenset(
    "i we me us my our you im d m ll ve s please can could would will shall should let lets "
    "want wanna wants need needs like love hope help plan planning going gonna try trying "
    "to start starting begin build create make launch open set up get run figure out "
    "write develop design do a an the".split()
)
# Common words dropped, anywhere, when the goal still does not fit.
COMMON_WORDS = frozenset(
    "a an the and or but nor of in on at to for with by from as into onto about over so "
    "my our your their its his her this that these those some few is are be been will "
    "it them then than once just very".split()
)


def goal_slug(words: str) -> str:
    """The goal slug of a process plan's file name (Decision 0073).

    Accents are folded, then: at most ``SLUG_MAX`` characters it is kept whole; otherwise the
    request's lead-in words are cut; if still too long, common words are dropped and the rest is
    cut at the last whole word that fits. Never summarized."""
    import unicodedata

    from .project import slugify

    folded = "".join(c for c in unicodedata.normalize("NFKD", str(words)) if not unicodedata.combining(c))
    slug = slugify(folded, 10_000)
    if len(slug) <= SLUG_MAX:
        return slug
    parts = slug.split("-")
    i = 0
    while i < len(parts) and parts[i] in LEAD_WORDS:
        i += 1
    if i < len(parts):
        parts = parts[i:]
    if len("-".join(parts)) > SLUG_MAX:
        parts = [w for w in parts if w not in COMMON_WORDS] or parts
    slug = "-".join(parts)
    if len(slug) > SLUG_MAX:
        cut = slug[: SLUG_MAX + 1]
        slug = cut[: cut.rfind("-")] if "-" in cut else slug[:SLUG_MAX]
    return slug


def plan_target(paths: dict[str, Any] | None, words: str) -> str:
    """Where a framing run's process plan goes: ``<paths.process_plans>/<goal-slug>-process-plan.md`` (Decisions 0069, 0073)."""
    folder = str((paths or {}).get("process_plans") or DEFAULT_PATHS["process_plans"]).replace("\\", "/").rstrip("/")
    return f"{folder}/{goal_slug(words) or 'goal'}-process-plan.md"


def started_parts(events: list[Any]) -> dict[str, dict[str, Any]]:
    """Every part of a framing run that has a run, ``{part: {part, run, recipe}}``, from the record."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.type == "framing_selected":
            for r in e.data.get("runs") or []:
                out[r["part"]] = r
        elif e.type == "framing_started_later":
            out[e.data["part"]] = {k: e.data[k] for k in ("part", "run", "recipe")}
    return out


def render_plan(api: Any, run_id: str, out: dict[str, Any], started: dict[str, dict[str, Any]], gaps: dict[str, dict[str, Any]]) -> str:
    """The process plan (Decisions 0064, 0068, 0069): every part, what choosing it starts, and where it stands.

    Rendered from the record, never by a worker. It lists; it never orders or schedules."""
    active = _active_others(api, run_id)
    lines = [f"# Process plan: {out.get('goal') or ''}".rstrip(), "",
             "The parts of this goal, what choosing each one starts, and where each stands. "
             "Nothing here is scheduled: a part starts only when you choose it.", ""]
    for p in out.get("parts") or []:
        pid = p.get("id")
        lines += [f"## {p.get('label') or pid}", ""]
        if (p.get("description") or "").strip():
            lines += [str(p["description"]).strip(), ""]
        if pid in started:
            r = started[pid]
            lines.append(f"- **Status:** started ({str(r['recipe']).split('@')[0]}, run {r['run']})")
        else:
            if pid in gaps:
                lines.append(f"- **Status:** chosen, but it could not start: {gaps[pid].get('reason')}")
            else:
                lines.append("- **Status:** for later")
            lines.append(f"- **Choosing it starts:** {part_next(api, p, active)}")
        lines += [f"- **Ref:** `{run_id}/{pid}`", ""]
    return "\n".join(lines).rstrip() + "\n"


def plan_due(ctx: Any, events: list[Any], done: set[Any]) -> list[Any]:
    """The framing run's process plan, when its latest rendering is not yet published (§10.4; Decision 0068)."""
    from . import publish

    if not is_framing(events):
        return []
    ev = next((e for e in reversed(events) if e.type in ("framing_selected", "framing_started_later") and e.data.get("plan")), None)
    if ev is None or ev.type != "framing_selected" or (FRAME_STEP, PLAN_ARTIFACT, ev.seq) in done:
        return []  # a later rendering belongs to the run that start began (plan_due_started)
    plan = ev.data["plan"]
    try:
        target = publish.check_target(publish.project_root(ctx), plan["path"])
    except EngineError as e:
        return [publish.Due(FRAME_STEP, PLAN_ARTIFACT, ev, plan["sha256"], None, str(e), True)]
    return [publish.Due(FRAME_STEP, PLAN_ARTIFACT, ev, plan["sha256"], target, publish.conflict_reason(ctx, FRAME_STEP, target, plan["sha256"]))]


def _framing_ctx(ctx: Any, run_id: str) -> Any:
    from .packet import RunContext
    from .project import builtin_recipe

    return RunContext(ctx.store, run_id, builtin_recipe(FRAME_RECIPE), ctx.project)


def plan_due_started(ctx: Any, events: list[Any]) -> list[Any]:
    """For a run started later from a process plan: the plan's re-publication, while it is due (Decision 0072).

    The publication is recorded on the framing run (it stays the plan's publisher); a conflict is
    this run's pending decision and holds its completion."""
    from . import publish

    if not events or events[0].type != "run_started":
        return []
    origin = events[0].data.get("framing") or {}
    fr = origin.get("run")
    if not fr or fr not in ctx.store.run_ids():
        return []
    fevents = ctx.store.run(fr).events()
    ev = next((e for e in reversed(fevents) if e.type in ("framing_selected", "framing_started_later") and e.data.get("plan")), None)
    if ev is None or ev.type != "framing_started_later" or ev.data.get("run") != ctx.run_id:
        return []
    if any(e.type == "artifact_published" and e.data.get("artifact") == PLAN_ARTIFACT and e.data.get("passed_seq") == ev.seq for e in fevents):
        return []
    octx = _framing_ctx(ctx, fr)
    plan = ev.data["plan"]
    try:
        target = publish.check_target(publish.project_root(ctx), plan["path"])
    except EngineError as e:
        return [publish.Due(FRAME_STEP, PLAN_ARTIFACT, ev, plan["sha256"], None, str(e), True, owner=octx)]
    return [publish.Due(FRAME_STEP, PLAN_ARTIFACT, ev, plan["sha256"], target,
                        publish.conflict_reason(octx, FRAME_STEP, target, plan["sha256"]), owner=octx)]


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


def _web_advice(api: Any, parts: list[dict[str, Any]], active: int) -> dict[str, Any] | None:
    """When the proposed parts' recipes have web steps no worker here can do: which parts, and how to get one (§11.6, §13.4)."""
    from .routing import WEB_ADVICE, web_advice

    try:
        profiles = api.project.profiles()
    except Exception as e:  # noqa: BLE001 - advice never stops framing
        diag.note("frame.profiles_unreadable", "frame:_web_advice", error=f"{type(e).__name__}: {e}")
        return None
    hit = []
    for q in parts:
        plan, _why = _plan_part(api, q, active)
        if plan is not None and web_advice(plan["recipe"].recipe, profiles) is not None:
            hit.append({"part": q.get("id"), "label": q.get("label"), "recipe": plan["recipe"].recipe.ref})
    return {"parts": hit, "advice": WEB_ADVICE} if hit else None


def annotate_next(api: Any, ctx: Any, pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give a framing run's select options their ``next``, computed from the record (Decision 0071)."""
    if not pending or not is_framing(ctx.log.events()):
        return pending
    for p in pending:
        if p.get("ref") != FRAME_STEP or p.get("kind") != "gate":
            continue
        out = frame_output(ctx, p["attempt"])
        active = _active_others(api, ctx.run_id)
        advice = _web_advice(api, out.get("parts") or [], active)
        if advice is not None:
            p["web_advice"] = advice
        for o in p.get("options") or []:
            if o["decision"] == "select":
                o["next"] = [{"part": q.get("id"), "label": q.get("label"), "next": part_next(api, q, active)}
                             for q in out.get("parts") or []]
            elif o["decision"] == "reject":
                o["next"] = REJECT_NEXT
    return pending


def start_part(api: Any, framing_run: str, plan: dict[str, Any], paths: list[Any], actor: str = "runtime") -> tuple[Any, str, list[str]]:
    """Start one planned part (vendoring a shipped recipe first): ``(run context, recipe ref, recipes vendored)``."""
    from .engine import start
    from .project import vendor

    loaded = plan["recipe"]
    vendored: list[str] = []
    if plan["vendor_from"] is not None:
        res = vendor(api.project, plan["vendor_from"])
        if res["changed"]:
            vendored.append(res["recipe"])
        loaded = api.project.recipe(res["recipe"])
        paths += [api.project.recipes_dir / res["recipe"], api.project.baton / "baton.lock"]
    inputs = plan["inputs"]
    wctx = start(
        api.project.store, loaded, inputs, title=plan["title"], project=api.project.variables(), actor=actor,
        work_item={"kind": inputs.get("kind"), "slug": api.project.render_slug(inputs, plan["title"]),
                   "branch": api.project.branch(), "framing": {"run": framing_run, "part": plan["part"]}},
    )
    return wctx, loaded.recipe.ref, vendored


def find_part(api: Any, ref: str) -> tuple[Any, dict[str, Any]]:
    """``<framing run>/<part>`` or a part id unique across finished framing runs: ``(framing run context, part)``."""
    store = api.project.store
    fr, _, pid = ref.rpartition("/")
    candidates: list[tuple[str, dict[str, Any]]] = []
    for rid in ([fr] if fr else store.run_ids()):
        if rid not in store.run_ids():
            raise EngineError("frame.unknown_run", f"no run {rid!r}")
        events = store.run(rid).events()
        if not is_framing(events) or not any(e.type == "framing_selected" for e in events):
            if fr:
                raise EngineError("frame.not_selected", f"run {rid} is not a framing run whose selection was made")
            continue
        fctx = api._ctx(rid)
        part = next((p for p in frame_output(fctx, fctx.log.state().step(FRAME_STEP).attempt).get("parts") or [] if p.get("id") == pid), None)
        if part is not None:
            candidates.append((rid, part))
    if not candidates:
        raise EngineError("frame.unknown_part", f"no framing run's process plan has a part {pid!r}" + (f" (looked in {fr})" if fr else ""))
    if len(candidates) > 1:
        raise EngineError("frame.ambiguous_part", f"part {pid!r} is in more than one process plan; name one of "
                          + ", ".join(f"{r}/{pid}" for r, _ in candidates))
    rid, part = candidates[0]
    return api._ctx(rid), part


def start_from_plan(api: Any, ref: str, paths: list[Any]) -> tuple[Any, dict[str, Any]]:
    """``start --from-plan <part>`` (Decision 0066): start a part exactly as its framing run recorded it.

    Reads the proposal from the record, never from the published file. Returns ``(new run context, result)``."""
    from . import docs

    fctx, part = find_part(api, ref)
    log = fctx.log
    if log.state().state != "completed":
        raise EngineError("frame.not_finished", f"framing run {fctx.run_id} is still waiting on the owner; settle that first")
    events = log.events()
    started = started_parts(events)
    pid = part["id"]
    if pid in started:
        raise EngineError("frame.part_started", f"{part.get('label') or pid} was already started, as run {started[pid]['run']}")
    plan, why = _plan_part(api, part, _active_others(api, fctx.run_id))
    if plan is None:
        raise EngineError("frame.gap", f"{part.get('label') or pid} cannot start: {why}")
    wctx, recipe_ref, vendored = start_part(api, fctx.run_id, plan, paths, actor=api.director.actor)
    started[pid] = {"part": pid, "run": wctx.run_id, "recipe": recipe_ref}
    sel = next(e for e in events if e.type == "framing_selected")
    out = frame_output(fctx, log.state().step(FRAME_STEP).attempt)
    content = render_plan(api, fctx.run_id, out, started, {g["part"]: g for g in sel.data.get("gaps") or []})
    target = (sel.data.get("plan") or {}).get("path") or plan_target(api.project.config.paths, run_words(fctx) or out.get("goal") or fctx.run_id)
    plan_ref = {"path": target, "sha256": log.cas.put(content.encode("utf-8"))}
    log.append("framing_started_later", actor=api.director.actor, data={
        "part": pid, "run": wctx.run_id, "recipe": recipe_ref, "plan": plan_ref, **({"vendored": vendored} if vendored else {}),
    })
    docs.write_records(fctx)
    paths.append(fctx.run_dir)
    return wctx, {"framing": fctx.run_id, "part": pid, "recipe": recipe_ref, "plan": target, "vendored": vendored}


def select(api: Any, ctx: Any, ref: str, decision: str, note: str, items: list[str] | None, paths: list[Any]) -> dict[str, Any]:
    """``decide <framing run> frame select --items <ids> --note "<owner's words>"`` (§11.6)."""
    from . import docs
    from .engine import _registered, refresh

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
        wctx, ref, changed = start_part(api, ctx.run_id, plan, paths)
        vendored += changed
        docs.write_records(wctx)
        paths.append(wctx.run_dir)
        runs.append({"part": plan["part"], "run": wctx.run_id, "recipe": ref})
    words = run_words(ctx)
    content = render_plan(api, ctx.run_id, out, {r["part"]: r for r in runs}, {g["part"]: g for g in gaps})
    plan_ref = {"path": plan_target(api.project.config.paths, words or out.get("goal") or ctx.run_id),
                "sha256": log.cas.put(content.encode("utf-8"))}
    log.append("framing_selected", actor="human", data={
        "decision_id": decision_id, "selected": chosen, "runs": runs, "gaps": gaps, **({"vendored": vendored} if vendored else {}),
        "plan": plan_ref,
    })
    refresh(ctx)  # publishes the process plan, or holds completion on its conflict (§10.4)
    return {"framing": ctx.run_id, "decision_id": decision_id, "selected": chosen, "runs": runs, "gaps": gaps, "vendored": vendored,
            "plan": plan_ref["path"], "state": log.state().state, "outcome": "selected", "step_path": FRAME_STEP, "attempt": n}


def run_words(ctx: Any) -> str | None:
    """The owner's words a framing run started from."""
    import json

    try:
        return json.loads(ctx.log.cas.read(ctx.record().started["inputs_sha256"])).get("words")
    except Exception:  # expected: informational: the word count is simply not shown (noqa: BLE001 - informational only)
        return None


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
    out["words"] = run_words(ctx)
    if step.state == "awaiting_human" or sel is not None:
        fo = frame_output(ctx, step.attempt)
        out["goal"] = fo.get("goal")
        out["parts"] = fo.get("parts") or []
        out["assumptions"] = fo.get("assumptions") or []
    if sel is not None:
        out.update(selected=sel.data.get("selected"), runs=sel.data.get("runs"), gaps=sel.data.get("gaps"))
        if sel.data.get("plan"):
            out["plan"] = sel.data["plan"]["path"]
        out["next"] = "framing finished"
    elif step.state == "awaiting_human":
        out["next"] = (f"confirm the goal with the owner, let them choose parts, confirm back, then "
                       f"`baton decide {run_id} frame select --items <ids> --note \"<their words>\"`")
    elif step.state == "escalated":
        out["next"] = "the framing step needs the owner (see pending_decisions)"
    else:
        out["next"] = f"dispatch the framing step (`baton eligible {run_id} frame`)"
    return out
