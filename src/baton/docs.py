"""Step records, run summaries and the readable event trace (§10.6).

Everything here is derived from the run's events, its CAS and the packet
manifests the runtime wrote, so records can be deleted and regenerated at
any time. They are written under ``runs/<run_id>/docs/`` and committed with
the run::

    docs/<step_path>.md   one per step that has had any event
    docs/SUMMARY.md       the work item, recipe and versions, steps, timeline,
                          escalations and leases
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from . import diag
from . import groups, locks
from .data import read_text
from .models import Event, Group, recorded_questions
from .packet import RunContext
from .store import StoreError, atomic_write

JSON_BLOCK_LIMIT = 16 * 1024


def _fence(value: Any) -> list[str]:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    if len(text) > JSON_BLOCK_LIMIT:
        return [f"_{len(text)} bytes; see the CAS blob._"]
    return ["```json", text, "```"]


def _cas_json(ctx: RunContext, sha: str | None) -> Any:
    if not sha:
        return None
    try:
        return json.loads(ctx.log.cas.read(sha))
    except (StoreError, ValueError) as e:
        diag.note("docs.record_unreadable", "docs:_cas_json", error=f"{type(e).__name__}: {e}")
        return None


def _title(ctx: RunContext, step_path: str) -> str:
    loc = groups.locate(ctx.recipe, step_path)
    node = loc.node if loc is not None else None
    return (node.title if node is not None and node.title else None) or step_path.rsplit("/", 1)[-1]


def _gate_line(ev: Event) -> str:
    d = ev.data
    gate = d.get("gate")
    label = "provenance" if gate == "provenance" else f"{gate} {d.get('type', '')}".strip()
    adv = " (advisory)" if d.get("advisory") else ""
    verdict = "passed" if ev.type == "gate_passed" else "failed"
    if d.get("waived"):
        verdict = f"**waived** (waiver seq {d.get('waiver_seq')}; would have failed: {'; '.join(r.splitlines()[0] for r in d.get('waived_reasons') or [])})"
    elif d.get("approved"):
        verdict = "passed (the owner approved the change)"
    line = f"  - {label}{adv}: {verdict}"
    if d.get("command"):
        line += f" — `{d['command']}` exit {d.get('exit_code')}"
    reasons = [r.splitlines()[0] for r in d.get("reasons") or []]
    if ev.type == "gate_failed" and reasons:
        line += f" — {'; '.join(reasons)}"
    return line


def step_record(ctx: RunContext, step_path: str, events: list[Event] | None = None) -> str:
    events = ctx.log.events() if events is None else events
    mine = [e for e in events if e.step_path == step_path]
    state = ctx.log.state().step(step_path)
    lines = [
        f"# `{step_path}`: {_title(ctx, step_path)}",
        "",
        f"- Run: `{ctx.run_id}`",
        f"- Recipe: `{ctx.recipe.recipe.ref}`",
        f"- State: **{state.state}**",
        f"- Attempts: {state.attempt}",
        "",
    ]
    attempts = sorted({e.attempt for e in mine if e.attempt is not None})
    for n in attempts:
        lines += _attempt_section(ctx, step_path, n, [e for e in mine if e.attempt == n], mine)
    final = next((e for e in reversed(mine) if e.type in ("step_passed", "step_imported")), None)
    if final is not None:
        lines += ["## Accepted output", ""]
        lines += _fence(_cas_json(ctx, final.data.get("output_sha256"))) + [""]
        arts = final.data.get("artifacts") or {}
        if arts:
            lines += ["## Artifacts", ""]
            for name in sorted(arts):
                a = arts[name]
                mt = f" ({a['media_type']})" if a.get("media_type") else ""
                lines.append(f"- `{name}`{mt}: CAS `{a['sha256']}`")
            lines.append("")
    lines += _deliverable_lines(step_path, mine, events)
    reviews_ = [e for e in mine if e.type in ("finding_dispositioned", "gate_waived")]
    if reviews_:
        lines += ["## Dispositions and waivers", ""]
        for e in reviews_:
            d = e.data
            if e.type == "finding_dispositioned":
                ev_ = f" — evidence `{d['evidence']}`" if d.get("evidence") else ""
                dec = f" — owner decision {d['decision_id']}" if d.get("decision_id") else ""
                prov = " (provisional until the next review)" if d.get("provisional") else ""
                lines.append(f"- {e.ts} `{d.get('finding')}` **{d.get('disposition')}** by {d.get('by')}{prov}{ev_}{dec}")
            else:
                lines.append(f"- {e.ts} gate {d.get('gate')} waived ({d.get('scope')}, {d.get('decision_id')}): \"{d.get('reason')}\"")
        lines.append("")
    upstream = _upstream_waivers(ctx, step_path, events)
    if upstream:
        lines += ["## Upstream waivers", ""]
        lines += [f"- `{e.step_path}` gate {e.data.get('gate')} ({e.data.get('scope')}, {e.data.get('decision_id')}): \"{e.data.get('reason')}\"" for e in upstream]
        lines.append("")
    lines += _tailoring_lines(step_path, mine, events)
    other = [e for e in mine if e.attempt is None and e.type in ("step_escalated", "step_abandoned", "human_decision")]
    if other:
        lines += ["## Other events", ""]
        lines += [f"- {e.ts} {e.type} by {e.actor}: {_brief(e)}" for e in other] + [""]
    return "\n".join(lines)


def _deliverable_lines(step_path: str, mine: list[Event], events: list[Event]) -> list[str]:
    """Publishing, drift and human revisions of this step's artifacts (§10.4, §10.5); flags from upstream revisions."""
    out: list[str] = []
    for e in mine:
        d = e.data
        if e.type == "artifact_published":
            if d.get("kept"):
                out.append(f"- {e.ts} `{d.get('artifact')}` not published: the owner kept the existing `{d.get('path')}` ({d.get('decision_id')})")
            else:
                how = " (already identical)" if d.get("unchanged") else " (overwrote, owner decision)" if d.get("overwrote") else ""
                how = f" (alternate name, {d.get('decision_id')})" if d.get("alternate") else how
                how = f" (revision {d.get('revision')})" if d.get("revision") else how
                out.append(f"- {e.ts} `{d.get('artifact')}` published to `{d.get('path')}`{how}: `{d.get('sha256')}`")
        elif e.type == "drift_detected":
            what = "deleted" if d.get("current_sha256") is None else f"edited (now `{d.get('current_sha256')}`)"
            out.append(f"- {e.ts} drift: `{d.get('path')}` {what}")
        elif e.type == "human_decision" and d.get("kind") == "drift" and d.get("decision") == "leave":
            out.append(f"- {e.ts} drift of `{d.get('path')}` left as is ({d.get('decision_id')}): \"{d.get('note')}\"")
        elif e.type == "human_revision_ingested":
            src = "an expert's answer" if d.get("source") == "sme" else "the edited published file"
            feeds = "not-yet-started dependents and " if d.get("feed") == "dependents" else ""
            out.append(f"- {e.ts} revision {d.get('revision')} of `{d.get('artifact')}` ingested from {src} ({d.get('decision_id')}): "
                       f"`{d.get('sha256')}`, fed to {feeds}`human_revision.{step_path}.{d.get('artifact')}` inputs")
            if d.get("possibly_stale"):
                out.append(f"  - possibly stale (passed before it): {', '.join(f'`{p}`' for p in d['possibly_stale'])}")
    flags = [e for e in events if e.type == "human_revision_ingested" and step_path in (e.data.get("possibly_stale") or [])]
    for e in flags:
        out.append(f"- **Possibly stale:** passed before revision {e.data.get('revision')} of `{e.data.get('artifact')}` from `{e.step_path}` was ingested")
    return ["## Deliverables", "", *out, ""] if out else []


def _tailoring_lines(step_path: str, mine: list[Event], events: list[Event]) -> list[str]:
    """Skips, imports and pre-retriage flags (§5.5, §11.4)."""
    out: list[str] = []
    for e in mine:
        d = e.data
        if e.type == "step_skipped":
            out.append(f"- {e.ts} skipped at level **{d.get('level')}** ({d.get('cause')})")
        elif e.type == "step_unskipped":
            out.append(f"- {e.ts} included again at level **{d.get('level')}** ({d.get('cause')})")
        elif e.type == "step_imported":
            att = d.get("attested") or {}
            out.append(f"- {e.ts} **imported** from existing work, attested by the baseline of adoption `{att.get('adoption')}` ({att.get('decision_id')})")
            for f in d.get("evidence") or []:
                out.append(f"  - evidence `{f.get('path')}` (`{f.get('sha256')}`)")
            for g in d.get("gates") or []:
                out.append(f"  - gate {g.get('gate')} ({g.get('type')}): {g.get('status')}")
    for e in events:
        if e.type == "retriage_applied" and step_path in (e.data.get("pre_retriage") or []):
            out.append(f"- **pre-retriage:** accepted at level {e.data.get('previous_level')}; level {e.data.get('level')} (re-triaged {e.ts}) would have skipped or gated it differently")
    return ["## Tailoring and adoption", "", *out, ""] if out else []


def _upstream_waivers(ctx: RunContext, step_path: str, events: list[Event]) -> list[Event]:
    """Waivers on steps this step depends on (§9.3: waivers show in every dependent record)."""
    loc = groups.locate(ctx.recipe, step_path)
    if loc is None:
        return []

    def closure(nodes: list, start: str) -> set[str]:
        by_id = {n.id: n for n in nodes}
        out: set[str] = set()
        todo = list(by_id[start].depends_on) if start in by_id else []
        while todo:
            d = todo.pop()
            if d not in out and d in by_id:
                out.add(d)
                todo += by_id[d].depends_on
        return out

    top_id = step_path.split("/", 1)[0].split("~", 1)[0]
    top = closure(ctx.recipe.recipe.steps, top_id)
    inner: set[str] = set()
    prefix = ""
    if loc.frame is not None:
        inner = closure(loc.frame.group.steps, loc.node.id.split("~", 1)[0])
        prefix = loc.frame.instance_path + "/"
    out = []
    for e in events:
        if e.type != "gate_waived" or e.step_path == step_path:
            continue
        if e.step_path.split("/", 1)[0].split("~", 1)[0] in top:
            out.append(e)
        elif prefix and e.step_path.startswith(prefix) and e.step_path.rsplit("/", 1)[-1].split("~", 1)[0] in inner:
            out.append(e)
    return out


def _brief(ev: Event) -> str:
    d = ev.data
    if ev.type == "human_decision":
        note = f' — "{d.get("note")}"' if d.get("note") else ""
        return f"{d.get('decision')}{note}"
    return d.get("reason") or ""


def _attempt_section(ctx: RunContext, step_path: str, n: int, evs: list[Event], mine: list[Event]) -> list[str]:
    lines = [f"## Attempt {n}", ""]
    disp = next((e for e in evs if e.type == "dispatched"), None)
    if disp is not None:
        lines.append(f"- Worker: `{disp.data.get('profile')}`, dispatched by {disp.actor} at {disp.ts}")
    gates_open = False
    for ev in evs:
        d = ev.data
        if ev.type in ("gate_passed", "gate_failed", "human_gate_opened") and not gates_open:
            lines.append("- Gates:")
            gates_open = True
        if ev.type == "packet_built":
            lines.append(f"- Packet: `{d.get('packet_sha256')}` (worker profile `{d.get('worker_profile_sha256')}`)")
            if d.get("guidance"):
                lines.append(f"- Retry guidance: {d['guidance']}")
            lines += _inputs(ctx, step_path, n)
        elif ev.type == "result_submitted":
            lines.append(f"- Result: {d.get('status')} at {ev.ts} (`result.json` `{d.get('result_sha256')}`)")
        elif ev.type in ("gate_passed", "gate_failed"):
            lines.append(_gate_line(ev))
        elif ev.type == "result_rejected":
            lines.append("- Rejected:")
            lines += [f"  - {r.splitlines()[0]}" for r in d.get("reasons") or []]
        elif ev.type == "human_gate_opened":
            lines.append(f"  - {d.get('gate')} human: opened — {d.get('prompt')}")
        elif ev.type == "human_decision":
            note = f' — "{d.get("note")}"' if d.get("note") else ""
            by = f", recorded by {d['recorded_by']}" if d.get("recorded_by") else ""
            indent = "  " if d.get("kind") == "gate" else ""
            lines.append(f"{indent}- Owner decision{by}: **{d.get('decision')}**{note}")
            if d.get("kind") == "answers":
                lines += [f"  - answer {a['id']}: {a['answer'] if isinstance(a['answer'], str) else ', '.join(a['answer'])}"
                          f' (owner: "{a["owner_words"]}")' for a in d.get("answers") or []]
        elif ev.type == "findings_recorded":
            counts = ", ".join(f"{n} {sev}" for sev, n in sorted((d.get("counts") or {}).items())) or "none"
            partial = " — **partial** coverage" if d.get("partial") else ""
            by = f" by review `{d['review']}` ({d.get('reviewer')})" if d.get("review") else ""
            lines.append(f"  - findings{by}: {counts}{partial}")
            if d.get("coverage_notes"):
                lines.append(f"    - coverage notes: {d['coverage_notes']}")
            for f in d.get("findings") or []:
                extra = " (reported again after it was marked " + f["reopened"] + ")" if f.get("reopened") else ""
                loc = f" at `{f['location']}`" if f.get("location") else ""
                lines.append(f"    - `{f['id']}` {f.get('severity')} **{f.get('status')}**: {f.get('title')}{loc}{extra}")
            for r in d.get("resolved") or []:
                how = f"; {r['disposition']}" + (" confirmed" if r.get("confirmed") else "") if r.get("disposition") else ""
                lines.append(f"    - `{r['id']}` not reported again (resolved{how})")
        elif ev.type == "protected_path_modified":
            lines.append(f"- Protected paths modified ({d.get('mode')}): {', '.join(d.get('changed') or [])}")
        elif ev.type == "step_passed" and d.get("confirmed"):
            lines.append(f"- Outcome: **confirmed unchanged by the owner** (stale after a revision; earlier result kept) at {ev.ts}")
        elif ev.type == "step_passed" and (d.get("condition") or {}).get("gates_passed") is False:
            lines.append(f"- Outcome: **result kept, iteration not done** (gate {d['condition'].get('gate')} failed) at {ev.ts}")
        elif ev.type == "step_passed":
            lines.append(f"- Outcome: **passed** at {ev.ts}")
        elif ev.type == "step_escalated":
            lines.append(f"- Outcome: **escalated** ({d.get('reason')}) at {ev.ts}")
            if d.get("questions"):
                lines += [f"  - question {q['id']}: {q['ask']}" for q in recorded_questions(d["questions"])]
    # A retry is recorded as step_ready with retry_of = n (the event carries no attempt).
    if any(e.type == "step_ready" and e.data.get("retry_of") == n for e in mine):
        lines.append(f"- Outcome: not accepted; ready for attempt {n + 1}")
    lines.append("")
    return lines


def _inputs(ctx: RunContext, step_path: str, n: int) -> list[str]:
    mpath = ctx.attempt_dir(step_path, n) / "packet" / "manifest.json"
    if not mpath.is_file():
        return []
    try:
        manifest = json.loads(read_text(mpath))
    except ValueError:  # expected: no readable manifest means no published documents
        return []
    out = []
    for i in manifest.get("inputs") or []:
        src = i.get("source")
        doc = f" ({_document_text(src)})" if src else ""
        out.append(f"  - input `{i['name']}`" + (f" #{i['index']}" if i.get("index") else "") + f" from `{i.get('from')}`: `{i['sha256']}`{doc}")
    for na in manifest.get("not_applicable") or []:
        out.append(f"  - input `{na['name']}`: not applicable ({na.get('reason')})")
    return (["- Inputs:"] + out) if out else []


def _document_text(src: dict[str, Any]) -> str:
    """A bound project document's provenance, in a record (§10.6)."""
    if src.get("kind") == "attested":
        how = f"attested by the owner ({src.get('decision_id')})"
    else:
        how = f"published by `{src.get('step')}.{src.get('artifact')}` of run `{src.get('run')}`" + (f", revision {src['revision']}" if src.get("revision") else "")
    edited = ", edited since accepted" if src.get("edited_since_accepted") else ""
    return f"project document `{src.get('path')}` version {src.get('version')}, {how}{edited}"


def _project_document_lines(ctx: RunContext, events: list[Event]) -> list[str]:
    """Each role of the recipe and every binding of it, oldest first (§10.6)."""
    roles = ctx.recipe.recipe.project_inputs
    if not roles:
        return []
    lines = ["", "## Project documents", ""]
    decisions = {e.data.get("decision_id"): e for e in events if e.type == "human_decision" and e.data.get("kind") == "bind"}
    for r in roles:
        binds = [e for e in events if e.type == "project_input_bound" and e.data.get("role") == r.role]
        lines.append(f"- `{r.role}` ({r.description}): " + ("not bound" if not binds else f"bound {len(binds)} time{'s' if len(binds) != 1 else ''}"))
        for e in binds:
            dec = decisions.get(e.data.get("decision_id"))
            note = f' — "{dec.data.get("note")}"' if dec is not None and dec.data.get("note") else ""
            for d in e.data.get("documents") or []:
                src = {"kind": d.get("kind"), "path": d.get("path"), "version": d.get("version"), **(d.get("source") or {}),
                       **({"edited_since_accepted": True} if d.get("edited_since_accepted") else {})}
                lines.append(f"  - {e.ts}: {_document_text(src)}, `{d.get('sha256')}` ({e.data.get('decision_id')}){note}")
    return lines


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

_TIMELINE = {
    "run_started", "result_rejected", "gate_failed", "human_decision", "step_passed", "step_escalated",
    "step_abandoned", "run_completed", "run_abandoned", "lease_taken_over",
    "group_expanded", "iteration_started", "iteration_limit_reached", "step_revised", "step_stale",
    "complexity_set", "retriage_requested", "retriage_applied", "step_imported", "research_recorded", "baseline_established",
    "sme_requested", "sme_answered", "sme_promoted",
}


def _group_lines(group: Group, info: dict[str, Any]) -> list[str]:
    lines = [f"### `{group.id}`: {group.title or group.id}", ""]
    if not info["instances"]:
        return lines + [f"- {info['state']}", ""]
    for i in info["instances"]:
        it = f", iteration {i['iteration']}" + (f" of {i['max_iterations']}" if i.get("max_iterations") else "") if i.get("iteration") else ""
        name = f"{i['title']} (`{i['id']}`)" if i.get("title") else f"`{i['id']}`"
        steps = ", ".join(f"{k} {v}" for k, v in (i.get("steps") or {}).items())
        lines.append(f"- {name}: **{i['state'].replace('_', ' ')}**{it}" + (f" — {steps}" if steps else ""))
    return lines + [""]


def summary(ctx: RunContext, events: list[Event] | None = None) -> str:
    events = ctx.log.events() if events is None else events
    started = events[0].data
    rs = ctx.log.state()
    formats = started.get("formats") or {}
    lines = [
        f"# Run `{ctx.run_id}`: {started.get('title') or '(untitled)'}",
        "",
        f"- Work item: {started.get('title') or '–'}" + (f" ({started['kind']})" if started.get("kind") else ""),
        f"- Slug: `{started.get('slug') or '–'}`",
        f"- Branch: `{started.get('branch') or '–'}`",
        f"- Recipe: `{started.get('recipe')}` (`{started.get('recipe_sha256')}`)",
        f"- Formats: {', '.join(f'{k} `{v}`' for k, v in sorted(formats.items()))}",
        f"- Max attempts per step: {started.get('max_attempts')}",
        f"- State: **{rs.state}**",
        *([f"- Complexity level: **{level}**" if (level := ctx.record().level()) else "- Complexity level: not set yet"] if ctx.recipe.recipe.complexity else []),
        *([f"- Adopted: from adoption run `{started['adoption']['run']}` (work item `{started['adoption']['work_item']}`)"] if started.get("adoption") else []),
        "",
        "## Steps",
        "",
        "| Step | Title | State | Attempts | Last worker |",
        "|---|---|---|---|---|",
    ]
    view = groups.View(ctx.recipe, events, rs, ctx.log.cas)
    group_lines: list[str] = []
    for node in ctx.recipe.recipe.steps:
        if isinstance(node, Group):
            info = groups.describe(view, node, node.id)
            lines.append(f"| `{node.id}` (group) | {node.title or ''} | {groups.summary_line(info, node)} | – | – |")
            group_lines += _group_lines(node, info)
            continue
        st = rs.step(node.id)
        worker = next((e.data.get("profile") for e in reversed(events) if e.type == "dispatched" and e.step_path == node.id), None)
        lines.append(f"| `{node.id}` | {node.title or ''} | {st.state} | {st.attempt} | {worker or '–'} |")
    if group_lines:
        lines += ["", "## Groups", ""] + group_lines
    lines += _project_document_lines(ctx, events)
    lines += ["", "## Timeline", ""]
    for ev in events:
        if ev.type not in _TIMELINE or (ev.type == "gate_failed" and ev.data.get("advisory")):
            continue
        where = f" `{ev.step_path}`" + (f" attempt {ev.attempt}" if ev.attempt else "") if ev.step_path else ""
        lines.append(f"- {ev.ts}{where}: {_timeline_text(ev)}")
    lines += ["", "## Escalations", ""]
    esc = [e for e in events if e.type == "step_escalated"]
    lines += [f"- {e.ts} `{e.step_path}` attempt {e.attempt}: {e.data.get('reason')}" for e in esc] or ["None."]
    lines += ["", "## Leases", ""]
    lease_events = locks.history(events)
    lines += [f"- {e.ts} {_lease_text(e)}" for e in lease_events] or ["None."]
    lines.append("")
    return "\n".join(lines)


def _timeline_text(ev: Event) -> str:
    d = ev.data
    t = ev.type
    if t == "run_started":
        return f"run started by {ev.actor}"
    if t == "result_rejected":
        return "result rejected: " + "; ".join(r.splitlines()[0] for r in d.get("reasons") or [])
    if t == "gate_failed":
        return f"gate {d.get('gate')} ({d.get('type')}) failed"
    if t == "human_decision" and d.get("kind") == "bind":
        note = f' — "{d.get("note")}"' if d.get("note") else ""
        return f"owner bound `{d.get('role')}` to {', '.join(f'`{p}`' for p in d.get('paths') or [])}{note}"
    if t == "step_stale" and d.get("cause") == "rebound":
        return f"stale (`{d.get('role')}` was rebound)"
    if t == "human_decision" and d.get("kind") != "sme":
        note = f' — "{d.get("note")}"' if d.get("note") else ""
        return f"owner decided **{d.get('decision')}**{note}"
    if t == "complexity_set":
        how = {"auto": "applied at once (lowest level)", "owner": "approved by the owner", "baseline": "set by the adoption baseline"}.get(d.get("approval"), "")
        return f"level **{d.get('level')}**" + (f", {how}" if how else "")
    if t == "retriage_requested":
        return f"re-triage requested (level {d.get('previous_level')}): {d.get('reason')}"
    if t == "retriage_applied":
        return f"re-triage applied: level {d.get('previous_level')} → **{d.get('level')}**"
    if t == "step_passed" and d.get("retriage_rejected"):
        return "re-triage rejected by the owner; the earlier level and result stand"
    if t == "step_imported":
        return "imported from existing work, attested by the adoption baseline"
    if t == "research_recorded":
        runs = d.get("runs") or {}
        return "research recorded" + (f"; work-item runs started: {', '.join(f'{k} `{v}`' for k, v in sorted(runs.items()))}" if runs else "")
    if t == "baseline_established":
        return "adoption baseline established"
    if t == "step_passed" and d.get("confirmed"):
        return "confirmed unchanged (earlier result kept)"
    if t == "step_passed" and (d.get("condition") or {}).get("gates_passed") is False:
        return "judged not done; iteration ends"
    if t == "step_passed":
        return "passed"
    if t == "group_expanded":
        ids = [i["id"] for i in d.get("items") or []]
        if "superseded" in d:
            return f"re-expanded ({d.get('mode')}): kept {len(d.get('kept') or [])}, changed {len(d.get('changed') or [])}, added {len(d.get('added') or [])}, superseded {len(d.get('superseded') or [])}"
        return f"expanded ({d.get('mode')}) into {len(ids)} instance{'s' if len(ids) != 1 else ''}"
    if t == "iteration_started":
        return f"iteration {d.get('iteration')} started at {d.get('from')}" + (" after the owner's decision" if d.get("after_decision") else "")
    if t == "iteration_limit_reached":
        return f"iteration limit reached ({d.get('max_iterations')}); waiting for the owner"
    if t == "step_revised":
        return f"revised: {d.get('reason')}"
    if t == "step_stale":
        return f"stale ({d.get('cause')})"
    if t == "step_escalated":
        return f"escalated ({d.get('reason')})"
    if t == "step_abandoned":
        return "abandoned"
    if t == "run_completed":
        return "run completed"
    if t == "run_abandoned":
        return f"run abandoned: {d.get('reason') or ''}".rstrip(": ")
    if t == "sme_requested" and d.get("mode") == "handoff":
        return f"{d.get('subject')} expert consultation `{d.get('consultation')}` handed off to the owner"
    if t == "sme_requested":
        return f"{d.get('subject')} expert consulted (`{d.get('consultation')}` turn {d.get('turn')}, {d.get('worker')})"
    if t == "sme_answered":
        return f"expert consultation `{d.get('consultation')}` turn {d.get('turn')}: {d.get('status')}"
    if t == "sme_promoted":
        return f"expert answer `{d.get('consultation')}` promoted as a {d.get('target')} with the owner's agreement"
    if t == "human_decision" and d.get("kind") == "sme":
        return f"owner promoted an expert answer as decision `{d.get('decision_id')}`" + (f' — "{d.get("note")}"' if d.get("note") else "")
    if t == "lease_taken_over":
        return f"lease taken over by {d.get('director_id')} from {d.get('from_director_id')}: {d.get('reason')}"
    return t  # pragma: no cover


def _lease_text(ev: Event) -> str:
    d = ev.data
    if ev.type == "lease_claimed":
        return f"claimed by {d['director_id']} until {d['expires_at']}"
    if ev.type == "lease_renewed":
        return f"renewed by {d['director_id']} until {d['expires_at']}"
    if ev.type == "lease_taken_over":
        return f"taken over by {d['director_id']} from {d.get('from_director_id')} until {d['expires_at']}: {d.get('reason')}"
    return f"released by {ev.actor}"


# ---------------------------------------------------------------------------
# Writing and tracing
# ---------------------------------------------------------------------------


def write_records(ctx: RunContext) -> list[Path]:
    """Regenerate every step record and the summary; returns the files that changed."""
    events = ctx.log.events()
    docs = ctx.run_dir / "docs"
    outputs: dict[Path, str] = {docs / "SUMMARY.md": summary(ctx, events)}
    for path in sorted({e.step_path for e in events if e.step_path}):
        loc = groups.locate(ctx.recipe, path)
        if loc is None or isinstance(loc.node, Group):
            continue  # group and instance paths are described in the summary
        outputs[docs / PurePosixPath(path + ".md")] = step_record(ctx, path, events)
    changed = []
    for p, text in outputs.items():
        data = text.encode("utf-8")
        if not p.is_file() or p.read_bytes() != data:
            atomic_write(p, data)
            changed.append(p)
    return changed


def trace(events: list[Event], limit: int | None = 20) -> list[str]:
    """One readable line per event, newest last."""
    chosen = events if not limit else events[-limit:]
    out = []
    for e in chosen:
        where = (e.step_path or "") + (f"#{e.attempt}" if e.attempt else "")
        detail = {k: v for k, v in e.data.items() if k in ("reason", "decision", "profile", "outcome", "director_id", "gate", "type", "status")}
        extra = " " + json.dumps(detail, sort_keys=True, ensure_ascii=False) if detail else ""
        out.append(f"{e.seq:>4} {e.ts} {e.type:<22} {where:<24} {e.actor}{extra}".rstrip())
    return out
