"""Framing new work (§11.6): an owner's goal becomes work items they choose from.

The selection is not framing's alone (Decision 0152): any recipe step that declares
``proposes_runs`` (output ``baton-proposals/1``) gets the same implicit ``select`` gate,
starts, gaps, process plan and ``start --from-plan``. Framing is its first user; the
events keep framing's names (``framing_selected``, ``framing_started_later``,
``run_started.framing``) and mean "a proposing step's selection".

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

from . import diag, tailoring
from .packet import EngineError

FRAME_RECIPE = "baton-frame@2"  # new framing runs; a run started on baton-frame@1 keeps it
FRAME_STEP = "frame"
SELECT_GATE = "select"
FRAME_DECISIONS = ("select", "reject")
FIT_CHECK = "fit-check"
FRAME_ID = "baton-frame"
PROPOSALS_REF = "baton:proposals"
#: Built-in recipes that predate ``proposes_runs``, with their proposing step (a pinned run's recipe hash cannot change).
LEGACY_PROPOSING: dict[str, str] = {"baton-frame@1": FRAME_STEP}


def is_framing(events: list[Any]) -> bool:
    """A run ``baton frame`` started (``work_item.kind: framing``)."""
    return bool(events) and events[0].type == "run_started" and events[0].data.get("kind") == "framing"


def proposing_step(loaded: Any) -> str | None:
    """The id of the recipe's step that proposes runs (§5.1; Decision 0152), or ``None``."""
    r = loaded.recipe
    for s in r.steps:
        if not s.is_group and s.proposes_runs:
            return s.id
    return LEGACY_PROPOSING.get(r.ref)


def proposer(ctx: Any) -> str | None:
    """The proposing step of the run's recipe, or ``None``."""
    return proposing_step(ctx.recipe)


def selected(events: list[Any]) -> bool:
    return any(e.type == "framing_selected" for e in events)


def awaiting_selection(ctx: Any, events: list[Any]) -> bool:
    """Whether a run with a proposing step still waits for the owner's selection to be applied (it completes only then)."""
    step = proposer(ctx)
    if step is None or selected(events):
        return False
    return ctx.log.state().step(step).state != "skipped"


def proposal_errors(out: Any) -> list[str]:
    """Where a proposing step's output does not fit ``baton-proposals/1``; empty when it fits."""
    from .versions import proposals_json_schema

    v = Draft202012Validator(proposals_json_schema(), format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(out)]
    ids = [p.get("id") for p in (out.get("parts") or []) if isinstance(p, dict)] if isinstance(out, dict) else []
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"parts: ids are repeated: {', '.join(map(str, dupes))}")
    return errors


# ---------------------------------------------------------------------------
# Run inputs
# ---------------------------------------------------------------------------


def _summary(loaded: Any, vendored: bool, with_scope: bool = False, with_axes: bool = True) -> dict[str, Any]:
    r = loaded.recipe
    schema = loaded.schemas[r.run_inputs.schema_] if r.run_inputs is not None else None
    out = {
        "id": r.id, "version": r.version, "description": r.description or "",
        "levels": list(r.complexity.levels) if r.complexity and r.complexity.levels else [], "run_inputs": schema, "vendored": vendored,
    }
    if with_axes and tailoring.is_multi(r.complexity):  # a recipe that rates work on axes (§5.5)
        from .adopt import axes_summary

        out["axes"] = axes_summary(r.complexity)
    if with_scope:  # the `catalog.summaries` input (§5.2) also carries what the recipe covers (§5.1)
        out["scope"] = r.scope.model_dump(mode="json") if r.scope is not None else None
        if r.project_inputs:  # and the project documents it can build on, by role (Decisions 0142, 0148)
            out["project_inputs"] = [p.model_dump(mode="json", exclude_none=True) for p in r.project_inputs]
    return out


def recipe_listing(project: Any, with_scope: bool = False, governing: list[dict[str, str]] | None = None,
                   with_axes: bool = True) -> list[dict[str, Any]]:
    """Every recipe a part may propose: each vendored recipe (its newest version), then each shipped one not vendored.

    Also the ``catalog.summaries`` input of an ordinary step (§5.2; Decision 0106), which adds each recipe's ``scope``,
    and ``governs`` (the kinds of work the project policy's ``governing`` gives it, §13.7) for a recipe that has some.
    ``with_axes=False`` leaves out a recipe's ``axes``, for ``baton-frame@1``, whose published schema predates them.
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
            out[loaded.recipe.id] = _summary(loaded, True, with_scope, with_axes)
    for rid, loaded in catalog().items():
        if rid not in out:
            out[rid] = _summary(loaded, False, with_scope, with_axes)
    for g in governing or []:
        if g["recipe"] in out:
            out[g["recipe"]].setdefault("governs", []).append(g["work"])
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


def document_listing(project: Any) -> list[dict[str, Any]]:
    """The project documents a proposal may bind (§8.6): path, kind, media type and state, never contents. Deleted ones are left out."""
    from .documents import list_documents

    return [{k: d.get(k) for k in ("path", "kind", "media_type", "state")} for d in list_documents(project.store) if d["state"] != "deleted"]


def inputs_for(project: Any, words: str, ref: str | None = None) -> dict[str, Any]:
    """A framing run's inputs: the owner's words, every recipe and fit-check's rubric; for ``baton-frame@2`` (the default)
    each recipe also carries its scope and roles, and the project's documents are listed."""
    title = " ".join(words.split())
    v2 = (ref or FRAME_RECIPE) != "baton-frame@1"
    out: dict[str, Any] = {
        "title": "Frame: " + (title if len(title) <= 60 else title[:57].rstrip() + "..."),
        "words": words, "recipes": recipe_listing(project, with_scope=v2, with_axes=v2),
    }
    if v2:
        out["documents"] = document_listing(project)
    rb = rubric(project)
    if rb is not None:
        out["rubric"] = rb
    return out


# ---------------------------------------------------------------------------
# The implicit select gate
# ---------------------------------------------------------------------------


def frame_output(ctx: Any, n: int) -> dict[str, Any]:
    """The proposing step's output at attempt ``n``."""
    import json

    sub = next((e for e in reversed(ctx.record().attempt_events(proposer(ctx) or FRAME_STEP, n)) if e.type == "result_submitted"), None)
    sha = (sub.data.get("output_sha256") if sub else None)
    return json.loads(ctx.log.cas.read(sha)) if sha else {}


def _is_frame(ctx: Any) -> bool:
    """A framing recipe, which keeps its own wording (§11.6)."""
    return ctx.recipe.recipe.id == FRAME_ID


def select_prompt(ctx: Any, out: dict[str, Any]) -> str:
    listing = "; ".join(str(p.get("label")) for p in out.get("parts") or [])
    if _is_frame(ctx):
        return (f"Goal: {out.get('goal', '')} Parts: {listing}. Which should be included now? "
                "Each chosen part starts what its option's next says, usually a first look rather than the work itself. "
                "(Select any or all; selecting none ends framing. Reject: the breakdown is redone with your note.)")
    lead = f"{out['goal']} " if out.get("goal") else ""
    return (f"{lead}Proposed: {listing}. Which should start now? Each chosen one starts what its option's next says. "
            "(Select any or none; selecting none starts nothing. Reject: the proposals are redone with your note.)")


def reject_next(ctx: Any) -> str:
    return REJECT_NEXT if _is_frame(ctx) else "the proposals are redone with what you said"


def reject_reasons(ctx: Any, note: str) -> list[str]:
    """Why a ``select`` gate failed when the owner rejected the proposals."""
    what = "the breakdown" if _is_frame(ctx) else "the proposals"
    return [f"the owner did not accept {what}: {note}" if note else f"the owner did not accept {what}"]


def open_select_gate(ctx: Any, step_path: str, n: int) -> Any:
    """After a proposing step's declared gates pass: the owner chooses parts (§11.6). ``None`` when not applicable."""
    from .engine import Outcome, _failed

    if step_path != proposer(ctx):
        return None
    if any(e.type == "gate_passed" and e.data.get("gate") == SELECT_GATE for e in ctx.record().attempt_events(step_path, n)):
        return None
    out = frame_output(ctx, n)
    errors = proposal_errors(out)
    if errors:  # deterministic: selection reads ids, labels and proposals (§0 rule 2)
        reasons = [f"the output is not a baton-proposals/1 list: {e}" for e in errors]
        ctx.log.append("gate_failed", step_path=step_path, attempt=n,
                       data={"gate": "proposals", "type": "schema", "implicit": True, "reasons": reasons})
        return _failed(ctx, step_path, n, reasons)
    parts = out.get("parts") or []
    prompt = select_prompt(ctx, out)
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
    bind, why = _check_bind(project, loaded, part.get("bind") or {})
    if why is not None:
        return None, why
    limit = project.config.limits.active_runs
    if limit is not None and active >= limit:
        return None, f"project.yaml limits.active_runs is {limit} and that many pieces of work are already active"
    return {"part": part["id"], "recipe": loaded, "vendor_from": vendor_from, "inputs": inputs,
            "title": inputs.get("title") or part.get("label"), "bind": bind}, None


def _check_bind(project: Any, loaded: Any, bind: dict[str, list[str]]) -> tuple[list[tuple[Any, list[dict[str, Any]]]], str | None]:
    """A proposal's ``bind``, checked like ``start --bind`` (§8.6): ``(checked bindings, None)`` or ``([], reason)``."""
    from .documents import check_binding

    out = []
    for role, paths in bind.items():
        try:
            out.append(check_binding(project.store, loaded.recipe, role, list(paths)))
        except EngineError as e:
            return [], f"the proposed document for {role} ({', '.join(paths)}) cannot be used: {e}"
    return out, None


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


def plan_path(ctx: Any, paths: dict[str, Any] | None, out: dict[str, Any]) -> str:
    """Where a proposing run's process plan goes: framing's from the goal (Decision 0073); any other proposing run's
    ``<paths.process_plans>/<recipe id>-<run id>-process-plan.md``, so repeated reviews never share a file."""
    if _is_frame(ctx):
        return plan_target(paths, run_words(ctx) or out.get("goal") or ctx.run_id)
    folder = str((paths or {}).get("process_plans") or DEFAULT_PATHS["process_plans"]).replace("\\", "/").rstrip("/")
    return f"{folder}/{ctx.recipe.recipe.id}-{ctx.run_id}-process-plan.md"


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


def render_plan(api: Any, run_id: str, out: dict[str, Any], started: dict[str, dict[str, Any]], gaps: dict[str, dict[str, Any]],
                framing: bool = True) -> str:
    """The process plan (Decisions 0064, 0068, 0069): every part, what choosing it starts, and where it stands.

    Rendered from the record, never by a worker. Framing's lists and never orders. Any other proposing step's (a project
    review the owner chose, Decision 0150) also gives each part's reasons and, where it suggests them, its place in a
    suggested order and what it waits on: advice, never a schedule."""
    active = _active_others(api, run_id)
    parts = out.get("parts") or []
    labels = {p.get("id"): p.get("label") or p.get("id") for p in parts}
    ordered = not framing and any(p.get("position") or p.get("waits_on") for p in parts)
    intro = ("The parts of this goal, what choosing each one starts, and where each stands. "
             "Nothing here is scheduled: a part starts only when you choose it.") if framing else (
             "The recommended pieces of work, why each is recommended, what choosing each one starts, and where each stands. "
             + ("The order suggested is advice, with its reasons. " if ordered else "")
             + "Nothing here is scheduled: a piece starts only when you choose it.")
    lines = [f"# Process plan: {out.get('goal') or ''}".rstrip(), "", intro, ""]
    for p in parts:
        pid = p.get("id")
        lines += [f"## {p.get('label') or pid}", ""]
        if (p.get("description") or "").strip():
            lines += [str(p["description"]).strip(), ""]
        if not framing:
            reasons = [str(r).strip() for r in p.get("reasons") or [] if str(r).strip()]
            if reasons:
                lines.append("- **Why:** " + " ".join(r if r.endswith((".", "!", "?")) else r + "." for r in reasons))
            if p.get("position"):
                lines.append(f"- **Suggested order:** {p['position']['rank']}: {p['position']['reason']}")
            for w in p.get("waits_on") or []:
                lines.append(f"- **Waits on:** {labels.get(w['on'], w['on'])}: {w['reason']}")
        if p.get("bind"):  # only a proposal that builds on project documents (baton-frame@2, other proposing steps)
            lines.append("- **Builds on:** " + "; ".join(f"{', '.join(f'`{x}`' for x in paths)} ({role})" for role, paths in p["bind"].items()))
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
    """A proposing run's process plan, when its latest rendering is not yet published (§10.4; Decision 0068)."""
    from . import publish

    step = proposer(ctx)
    if step is None:
        return []
    ev = next((e for e in reversed(events) if e.type in ("framing_selected", "framing_started_later") and e.data.get("plan")), None)
    if ev is None or ev.type != "framing_selected" or (step, PLAN_ARTIFACT, ev.seq) in done:
        return []  # a later rendering belongs to the run that start began (plan_due_started)
    plan = ev.data["plan"]
    try:
        target = publish.check_target(publish.project_root(ctx), plan["path"])
    except EngineError as e:
        return [publish.Due(step, PLAN_ARTIFACT, ev, plan["sha256"], None, str(e), True)]
    return [publish.Due(step, PLAN_ARTIFACT, ev, plan["sha256"], target, publish.conflict_reason(ctx, step, target, plan["sha256"]))]


def _framing_ctx(ctx: Any, run_id: str) -> Any:
    """The context of the run whose plan a later start re-publishes (its own pinned recipe)."""
    from .packet import RunContext
    from .project import Project

    return RunContext(ctx.store, run_id, Project.over_store(ctx.store).recipe_for_run(run_id), ctx.project)


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
    step = proposer(octx) or FRAME_STEP
    plan = ev.data["plan"]
    try:
        target = publish.check_target(publish.project_root(ctx), plan["path"])
    except EngineError as e:
        return [publish.Due(step, PLAN_ARTIFACT, ev, plan["sha256"], None, str(e), True, owner=octx)]
    return [publish.Due(step, PLAN_ARTIFACT, ev, plan["sha256"], target,
                        publish.conflict_reason(octx, step, target, plan["sha256"]), owner=octx)]


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
    text = f"starts {r.id}: {r.description or ''}".rstrip(": ")
    paths = [p for ps in (part.get("bind") or {}).values() for p in ps]
    text += f", building on {', '.join(paths)}" if paths else ""
    for f in tool_flags_for(api, plan):  # choosing the part approves the tool, so the owner hears what it is first (§5.9)
        text += f"; it brings a program that runs on this computer ({f['tool']}): {f['does']} It needs {f['needs']}; it {f['touches']}"
    return text


def tool_flags_for(api: Any, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The tools a part's shipped recipe brings that this project has not approved (§5.9; criterion 10)."""
    if plan.get("vendor_from") is None:
        return []
    from .project import tool_flags

    return tool_flags(api.project.lock(), plan["recipe"])


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
    """Give a proposing run's select options their ``next``, computed from the record (Decision 0071)."""
    step = proposer(ctx) if pending else None
    if step is None:
        return pending
    for p in pending:
        if p.get("ref") != step or p.get("kind") != "gate":
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
                o["next"] = reject_next(ctx)
    return pending


def start_part(api: Any, framing_run: str, plan: dict[str, Any], paths: list[Any], actor: str = "runtime",
               note: str = "") -> tuple[Any, str, list[str]]:
    """Start one planned part (vendoring a shipped recipe first), binding its proposed documents with the owner's words
    (``note``): ``(run context, recipe ref, recipes vendored)``."""
    from .documents import record_binding
    from .engine import start
    from .project import vendor

    loaded = plan["recipe"]
    vendored: list[str] = []
    if plan["vendor_from"] is not None:
        res = vendor(api.project, plan["vendor_from"])
        if res["needs_owner"]:
            if any(f["code"] != "tool" for f in res["flags"]) or not note.strip():
                raise EngineError("frame.vendor_needs_owner", f"{res['recipe']} needs the owner's decision before it is vendored: {res['message']}")
            # The owner chose this part after hearing what its tools do (``part_next``): their words approve them.
            res = vendor(api.project, plan["vendor_from"], decision={"decision_id": _vendor_decision(api, res, note, framing_run), "note": note})
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
    for role, entries in plan.get("bind") or []:  # checked when planned; the role is re-read from the recipe vendored now
        role = loaded.recipe.role(role.role) or role
        record_binding(wctx, role, entries, note, recorded_by=api.director.actor)
    return wctx, loaded.recipe.ref, vendored


def _vendor_decision(api: Any, res: dict[str, Any], note: str, framing_run: str) -> str:
    """Record the owner's approval of a shipped recipe's tools, given by choosing its part (project log)."""
    from . import sme
    from .locks import project_lock

    with project_lock(api.project.baton):
        decision_id = f"d{len(api.project.store.project_log().events()) + 1}"
    sme.project_append(api.project, "human_decision", {"kind": "vendor", "recipe": res["recipe"], "decision": "approve", "note": note,
                                                       "decision_id": decision_id, "flags": res["flags"], "via": framing_run}, actor="human")
    return decision_id


def find_part(api: Any, ref: str) -> tuple[Any, dict[str, Any]]:
    """``<run>/<part>`` or a part id unique across the process plans of finished selections: ``(that run's context, part)``."""
    store = api.project.store
    fr, _, pid = ref.rpartition("/")
    candidates: list[tuple[str, dict[str, Any]]] = []
    for rid in ([fr] if fr else store.run_ids()):
        if rid not in store.run_ids():
            raise EngineError("frame.unknown_run", f"no run {rid!r}")
        if not selected(store.run(rid).events()):  # only a proposing step's selection records it
            if fr:
                raise EngineError("frame.not_selected", f"run {rid} is not a framing run whose selection was made")
            continue
        fctx = api._ctx(rid)
        step = proposer(fctx)
        if step is None:  # pragma: no cover - framing_selected is recorded only for a proposing step
            continue
        part = next((p for p in frame_output(fctx, fctx.log.state().step(step).attempt).get("parts") or [] if p.get("id") == pid), None)
        if part is not None:
            candidates.append((rid, part))
    if not candidates:
        raise EngineError("frame.unknown_part", f"no framing run's process plan has a part {pid!r}" + (f" (looked in {fr})" if fr else ""))
    if len(candidates) > 1:
        raise EngineError("frame.ambiguous_part", f"part {pid!r} is in more than one process plan; name one of "
                          + ", ".join(f"{r}/{pid}" for r, _ in candidates))
    rid, part = candidates[0]
    return api._ctx(rid), part


def start_from_plan(api: Any, ref: str, paths: list[Any], note: str = "") -> tuple[Any, dict[str, Any]]:
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
    if plan["bind"] and not (note or "").strip():
        raise EngineError("bind.note_required", f"{part.get('label') or pid} builds on project documents; binding them is the owner's "
                          "decision: give their words with --note")
    if tool_flags_for(api, plan) and not (note or "").strip():
        raise EngineError("vendor.note", f"{part.get('label') or pid} brings a program that runs on this computer; approving it is the "
                          "owner's decision: give their words with --note")
    wctx, recipe_ref, vendored = start_part(api, fctx.run_id, plan, paths, actor=api.director.actor, note=note)
    started[pid] = {"part": pid, "run": wctx.run_id, "recipe": recipe_ref}
    sel = next(e for e in events if e.type == "framing_selected")
    out = frame_output(fctx, log.state().step(proposer(fctx) or FRAME_STEP).attempt)
    content = render_plan(api, fctx.run_id, out, started, {g["part"]: g for g in sel.data.get("gaps") or []}, framing=_is_frame(fctx))
    target = (sel.data.get("plan") or {}).get("path") or plan_path(fctx, api.project.config.paths, out)
    plan_ref = {"path": target, "sha256": log.cas.put(content.encode("utf-8"))}
    log.append("framing_started_later", actor=api.director.actor, data={
        "part": pid, "run": wctx.run_id, "recipe": recipe_ref, "plan": plan_ref, **({"vendored": vendored} if vendored else {}),
        **({"bound": _bound(plan)} if plan["bind"] else {}),
    })
    docs.write_records(fctx)
    paths.append(fctx.run_dir)
    return wctx, {"framing": fctx.run_id, "part": pid, "recipe": recipe_ref, "plan": target, "vendored": vendored,
                  **({"bound": _bound(plan)} if plan["bind"] else {})}


def _bound(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """What a started part bound, for the proposing run's record: ``[{role, paths}]``."""
    return [{"role": role.role, "paths": [e["info"]["path"] for e in entries]} for role, entries in plan["bind"]]


def select(api: Any, ctx: Any, ref: str, decision: str, note: str, items: list[str] | None, paths: list[Any]) -> dict[str, Any]:
    """``decide <run> <proposing step> select --items <ids> --note "<owner's words>"`` (§11.6; Decision 0152)."""
    from . import docs
    from .engine import _registered, refresh

    log = ctx.log
    step = proposer(ctx)
    if step is None:
        raise EngineError("frame.not_framing", f"run {ctx.run_id} has no step that proposes runs; select is only for such a step's gate")
    if decision != "select":
        raise EngineError("decide.bad_decision", "--items goes with the select decision")
    if ref != step:
        raise EngineError("decide.bad_decision", f"select is decided on {step!r}, got {ref!r}")
    st = log.state().step(step)
    n = st.attempt
    opened = ctx.record().last("human_gate_opened", step, n) if st.state == "awaiting_human" else None
    if opened is None or opened.data.get("gate") != SELECT_GATE:
        raise EngineError("decide.nothing_pending", f"{step} is not waiting on the owner's selection (it is {st.state})")
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
    log.append("human_decision", actor="human", step_path=step, attempt=n, data={
        "ref": step, "kind": "frame", "gate": SELECT_GATE, "decision": "select", "items": chosen, "note": note,
        "decision_id": decision_id, "recorded_by": api.director.actor,
    })
    log.append("gate_passed", step_path=step, attempt=n, data={"gate": SELECT_GATE, "type": SELECT_GATE, "implicit": True, "items": chosen})
    log.append("step_passed", step_path=step, attempt=n, data=_registered(ctx, step, n))

    vendored: list[str] = []
    runs: list[dict[str, Any]] = []
    for plan in plans:
        wctx, ref, changed = start_part(api, ctx.run_id, plan, paths, note=note)
        vendored += changed
        docs.write_records(wctx)
        paths.append(wctx.run_dir)
        runs.append({"part": plan["part"], "run": wctx.run_id, "recipe": ref, **({"bound": _bound(plan)} if plan["bind"] else {})})
    content = render_plan(api, ctx.run_id, out, {r["part"]: r for r in runs}, {g["part"]: g for g in gaps}, framing=_is_frame(ctx))
    plan_ref = {"path": plan_path(ctx, api.project.config.paths, out),
                "sha256": log.cas.put(content.encode("utf-8"))}
    log.append("framing_selected", actor="human", data={
        "decision_id": decision_id, "selected": chosen, "runs": runs, "gaps": gaps, **({"vendored": vendored} if vendored else {}),
        "plan": plan_ref,
    })
    refresh(ctx)  # publishes the process plan, or holds completion on its conflict (§10.4)
    return {"framing": ctx.run_id, "decision_id": decision_id, "selected": chosen, "runs": runs, "gaps": gaps, "vendored": vendored,
            "plan": plan_ref["path"], "state": log.state().state, "outcome": "selected", "step_path": step, "attempt": n}


def run_words(ctx: Any) -> str | None:
    """The owner's words a framing run (or another proposing run with a ``words`` input) started from."""
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
