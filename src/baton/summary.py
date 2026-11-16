"""``project.summary`` (§5.2; Decision 0152): the project's state, for a step that reviews it.

Built by the runtime from the records (every run's log, the project log, the project documents and
the run's pinned policy), deterministically: the same records give the same blob. It is metadata
only: no document's contents ever appear in it; contents reach a step only through its declared
roles (§8.6). The run being built is left out, so two reviews of the same state are comparable by
the summary's hash.
"""

from __future__ import annotations

import json
from typing import Any

#: Step states that say nothing about where a run is (finished, or not reachable yet).
_QUIET = frozenset({"passed", "skipped", "imported", "blocked_on_deps"})


def build(store: Any, exclude_run: str | None = None, policy_sha256: str | None = None) -> dict[str, Any]:
    """The summary of every run but ``exclude_run``, the project's documents and the policy ``policy_sha256`` names."""
    from . import documents

    docs = documents.collect(store)
    runs, bindings, upstream, plans = [], [], [], []
    for rid in sorted(store.run_ids()):
        if rid == exclude_run:
            continue
        events = store.run(rid).events()
        if not events:
            continue
        entry, ctx = _run(store, rid, events)
        runs.append(entry)
        if entry["state"] == "active":
            for role, ev in sorted(documents.bound(events).items()):
                bindings.append({"run": rid, "role": role,
                                 "documents": [{"path": d["path"], "version": d.get("version")} for d in ev.data.get("documents") or []]})
            upstream += [{k: c[k] for k in ("run", "role", "path", "change", "bound_version", "current_version")}
                         for c in documents.upstream_changes(store, rid, events, docs)]
        plan = _plan(rid, events, ctx) if ctx is not None else None
        if plan is not None:
            plans.append(plan)
    listed = []
    for d in documents.list_documents(store):
        src = {k: v for k, v in (d.get("source") or {}).items() if k != "note"}  # the owner's words stay in the record
        listed.append({"path": d["path"], "kind": d["kind"], "media_type": d["media_type"], "version": d["version"],
                       "state": d["state"], "source": src})
    return {"runs": runs, "documents": listed, "bindings": bindings, "upstream_changes": upstream, "process_plans": plans,
            "policy": _policy(store, policy_sha256)}


def _run(store: Any, rid: str, events: list[Any]) -> tuple[dict[str, Any], Any]:
    """One run's entry, and its context when its recipe loads (``None`` otherwise: the entry says so)."""
    from .engine import pending_decisions
    from .packet import EngineError, RunContext, RunRecord
    from .project import Project

    started = events[0].data
    rs = store.run(rid).state()
    record = RunRecord(events)
    entry: dict[str, Any] = {"run": rid, "recipe": started.get("recipe"), "title": started.get("title"), "kind": started.get("kind"),
                             "state": rs.state}
    ratings = record.ratings()
    if ratings:  # {"level": ...} for a one-axis recipe (§5.5)
        entry["ratings"] = dict(sorted(ratings.items()))
    if started.get("framing"):
        entry["proposed_by"] = dict(started["framing"])
    ctx = None
    try:
        ctx = RunContext(store, rid, Project.over_store(store).recipe_for_run(rid), {})
    except EngineError as e:  # a run whose recipe no longer loads is still listed, as such
        entry["unreadable"] = e.code
    if rs.state == "active":
        entry["steps"] = {p: st.state for p, st in sorted(rs.steps.items()) if st.state not in _QUIET}
        if ctx is not None:
            entry["waiting_on_owner"] = [{"ref": p.get("ref"), "kind": p.get("kind")} for p in pending_decisions(ctx)]
    return entry, ctx


def _plan(rid: str, events: list[Any], ctx: Any) -> dict[str, Any] | None:
    """A finished selection's process plan: every part, started (with its run), a gap (with why) or for later."""
    from . import frame

    sel = next((e for e in events if e.type == "framing_selected"), None)
    step = frame.proposer(ctx)
    if sel is None or step is None:
        return None
    out = frame.frame_output(ctx, ctx.log.state().step(step).attempt)
    started = frame.started_parts(events)
    gaps = {g["part"]: g.get("reason") for g in sel.data.get("gaps") or []}
    parts = []
    for p in out.get("parts") or []:
        pid = p.get("id")
        item: dict[str, Any] = {"id": pid, "label": p.get("label")}
        if pid in started:
            item.update(status="started", run=started[pid]["run"], recipe=started[pid]["recipe"])
        elif pid in gaps:
            item.update(status="gap", reason=gaps[pid])
        else:
            item["status"] = "later"
        parts.append(item)
    return {"run": rid, "recipe": events[0].data.get("recipe"), "goal": out.get("goal"),
            "path": (sel.data.get("plan") or {}).get("path"), "parts": parts}


def _policy(store: Any, sha: str | None) -> dict[str, Any] | None:
    """The policy the reviewing run is under, or ``None`` when the project has none in force."""
    if not sha:
        return None
    return {"sha256": sha, **json.loads(store.project_cas.read(sha))}
