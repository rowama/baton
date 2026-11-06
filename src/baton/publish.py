"""Deliverables (§10.4, §10.5): publishing, conflicts, drift and human revisions.

Publishing is for artifacts a worker returns in ``result/artifacts/``
(documents, drawings, photos). A workspace step's output *is* the project tree
and never goes through here.

**Two copies.** The CAS copy is the record and is what every later packet
reads; the published copy at the project path is the living file. Everything
below is derived from the run's events plus the files on disk:

* A **deliverable** is ``(step, artifact)`` for a top-level step whose artifact
  declares ``publish``. Its pass is *due* when the step's latest
  ``step_passed`` registered the artifact and no ``artifact_published`` names
  that pass (``passed_seq``). Imported steps are never published.
* A due pass is written silently only when the target is absent, already
  holds the artifact's bytes, or was last published (across all runs) by this
  run and step and still has the hash Baton wrote. Anything else is a
  **conflict**: a pending owner decision ``publish:<step>.<artifact>``
  (``overwrite`` | ``keep`` | ``alternate``). Conflicts are computed from the
  disk each time, so a file the owner moves away themselves stops conflicting.
* The **expected** hash of a published file is the one Baton last wrote,
  ingested, or was told to leave. A file whose hash differs (or that is gone)
  has **drifted**: a pending owner decision ``drift:<step>.<artifact>``
  (``decide … leave`` or ``ingest_revision``). Drift is tracked only while the
  run is active.
* Pending conflicts and drift hold run completion (``outstanding``).
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import jinja2
from jinja2 import nodes as jnodes

from . import labels
from .models import Step
from .packet import EngineError, RunContext
from .store import BATON_DIR

CONFLICT_DECISIONS = ("overwrite", "keep", "alternate")
DRIFT_DECISIONS = ("leave",)
FEEDS = ("revision_inputs", "dependents")

_env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False, keep_trailing_newline=False)


class PublishError(EngineError):
    pass


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def published_artifacts(recipe: Any) -> list[tuple[str, Any]]:
    """``(step id, artifact)`` for every top-level step artifact that declares ``publish``."""
    return [(n.id, a) for n in recipe.steps if isinstance(n, Step) for a in n.artifacts if a.publish is not None]


def path_keys(template: str) -> set[str]:
    """The ``paths.<key>`` names a publish template uses."""
    out = set()
    for node in _env.parse(template).find_all(jnodes.Getattr):
        if isinstance(node.node, jnodes.Name) and node.node.name == "paths":
            out.add(node.attr)
    return out


def missing_path_keys(recipe: Any, paths: dict[str, Any]) -> list[str]:
    """``paths.*`` keys the recipe publishes to that ``project.yaml`` does not map (§10.4: a start-time error)."""
    keys: set[str] = set()
    for _, art in published_artifacts(recipe):
        keys |= path_keys(art.publish.to)
    return sorted(k for k in keys if k not in (paths or {}))


def _run_vars(ctx: RunContext) -> dict[str, Any]:
    import json

    started = ctx.record().started
    sha = started.get("inputs_sha256")
    inputs = json.loads(ctx.log.cas.read(sha)) if sha and ctx.log.cas.has(sha) else {}
    return {"id": ctx.run_id, "slug": started.get("slug") or ctx.run_id, "title": started.get("title"), "kind": started.get("kind"), "inputs": inputs}


def check_target(root: Path, rel: str) -> str:
    """A target in POSIX form relative to the project root; raises ``PublishError`` when it leaves the project."""
    rel = rel.replace("\\", "/").strip()
    p = PurePosixPath(rel)
    if not rel or p.is_absolute() or (p.parts and ":" in p.parts[0]) or ".." in p.parts:
        raise PublishError("publish.bad_target", f"publish target {rel!r} must be a relative path inside the project")
    parts = [x for x in p.parts if x != "."]
    if not parts or parts[0] in (".git", BATON_DIR):
        raise PublishError("publish.bad_target", f"publish target {rel!r} may not be inside .git or {BATON_DIR}")
    full = (root / Path(*parts)).resolve()
    if not full.is_relative_to(root.resolve()):
        raise PublishError("publish.bad_target", f"publish target {rel!r} resolves outside the project")
    return "/".join(parts)


def render_target(ctx: RunContext, template: str) -> str:
    variables = {"paths": (ctx.project or {}).get("paths") or {}, "project": (ctx.project or {}).get("project") or {}, "run": _run_vars(ctx)}
    try:
        text = _env.from_string(template).render(**variables)
    except jinja2.TemplateError as e:
        missing = sorted(k for k in path_keys(template) if k not in variables["paths"])
        why = f"project.yaml paths has no {', '.join(missing)}" if missing else str(e)
        raise PublishError("publish.unrenderable", f"publish target {template!r} cannot be rendered: {why}") from e
    return check_target(project_root(ctx), text)


def project_root(ctx: RunContext) -> Path:
    return ctx.store.root


def file_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_file(path: Path, data: bytes) -> None:
    """Atomic write of a deliverable (ordinary permissions: it is a project file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".baton-tmp-{secrets.token_hex(6)}"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def alternate_name(rel: str, run_id: str) -> str:
    p = PurePosixPath(rel)
    return str(p.with_name(f"{p.stem}.{run_id}{p.suffix}"))


# ---------------------------------------------------------------------------
# History (derived from events)
# ---------------------------------------------------------------------------


def last_written(store: Any, rel: str) -> tuple[str, Any] | None:
    """``(run id, artifact_published event)`` that last wrote ``rel``, across every run of the project."""
    best: tuple[str, Any] | None = None
    for rid in store.run_ids():
        for e in store.run(rid).events():
            if e.type == "artifact_published" and e.data.get("path") == rel and not e.data.get("kept"):
                if best is None or (e.ts, rid, e.seq) >= (best[1].ts, best[0], best[1].seq):
                    best = (rid, e)
    return best


@dataclass
class Tracked:
    """What Baton knows about one deliverable's published file."""

    step_path: str
    artifact: str
    path: str | None = None  # where it was last written (None: never written, or kept)
    expected: str | None = None  # the hash the file should have
    written: str | None = None  # the hash Baton last wrote there
    since_seq: int = 0  # the event that set ``expected``
    reported: set[str | None] = field(default_factory=set)  # drift hashes already recorded since then
    revisions: list[Any] = field(default_factory=list)  # human_revision_ingested events


def tracked(events: Iterable[Any]) -> dict[tuple[str, str], Tracked]:
    out: dict[tuple[str, str], Tracked] = {}
    for e in events:
        if e.type not in ("artifact_published", "human_revision_ingested", "human_decision", "drift_detected"):
            continue
        d = e.data
        if e.type == "human_decision":
            if d.get("kind") != "drift" or d.get("decision") != "leave":
                continue
        key = (e.step_path or d.get("step_path"), d.get("artifact"))
        if key[0] is None or key[1] is None:
            continue
        t = out.setdefault(key, Tracked(key[0], key[1]))
        if e.type == "artifact_published":
            if d.get("kept"):
                if t.path == d.get("path"):
                    t.path = None  # the existing file stays; it is no longer Baton's to track
                continue
            t.path, t.expected, t.written, t.since_seq, t.reported = d["path"], d["sha256"], d["sha256"], e.seq, set()
        elif e.type == "human_revision_ingested":
            t.revisions.append(e)
            if t.path is not None and d.get("path") == t.path:
                t.expected, t.since_seq, t.reported = d["sha256"], e.seq, set()
        elif e.type == "human_decision":
            t.expected, t.since_seq, t.reported = d.get("current_sha256"), e.seq, set()
        else:
            t.reported.add(d.get("current_sha256"))
    return out


def drift(events: list[Any], root: Path) -> list[dict[str, Any]]:
    """Published files of an active run whose hash differs from what Baton expects (§10.5)."""
    if not events or any(e.type in ("run_completed", "run_abandoned") for e in events):
        return []
    out = []
    for (sp, art), t in sorted(tracked(events).items()):
        if t.path is None:
            continue
        now = file_sha(root / t.path)
        if now == t.expected:
            continue
        out.append({"step_path": sp, "artifact": art, "path": t.path, "published_sha256": t.expected, "current_sha256": now,
                    "ref": f"drift:{sp}.{art}", "recorded": now in t.reported})
    return out


# ---------------------------------------------------------------------------
# Due passes and conflicts
# ---------------------------------------------------------------------------


@dataclass
class Due:
    step_path: str
    artifact: str
    passed: Any  # the step_passed event
    sha256: str
    target: str | None
    conflict: str | None  # why it cannot be written silently
    unrenderable: bool = False

    @property
    def ref(self) -> str:
        return f"publish:{self.step_path}.{self.artifact}"


def _last_passed(events: list[Any], step_path: str) -> Any:
    return next((e for e in reversed(events) if e.step_path == step_path and e.type in ("step_passed", "step_imported", "step_revised")), None)


def due(ctx: RunContext) -> list[Due]:
    """Deliverables whose latest accepted pass is not yet published (or kept), with any conflict."""
    events = ctx.log.events()
    rs = ctx.log.state()
    done = {(e.step_path, e.data.get("artifact"), e.data.get("passed_seq")) for e in events if e.type == "artifact_published"}
    root = project_root(ctx)
    out = []
    for sid, art in published_artifacts(ctx.recipe.recipe):
        if rs.step(sid).state != "passed":
            continue
        ev = _last_passed(events, sid)
        if ev is None or ev.type != "step_passed":
            continue
        reg = (ev.data.get("artifacts") or {}).get(art.name)
        if reg is None or (sid, art.name, ev.seq) in done:
            continue
        try:
            target = render_target(ctx, art.publish.to)
        except PublishError as e:
            out.append(Due(sid, art.name, ev, reg["sha256"], None, str(e), True))
            continue
        out.append(Due(sid, art.name, ev, reg["sha256"], target, conflict_reason(ctx, sid, target, reg["sha256"])))
    from .frame import plan_due

    return out + plan_due(ctx, events, done)  # a framing run's process plan, rendered by the runtime (§11.6)


def conflict_reason(ctx: RunContext, step_path: str, target: str, sha: str) -> str | None:
    """``None`` when ``target`` may be written silently, else why not (§10.4)."""
    now = file_sha(project_root(ctx) / target)
    if now is None and not (project_root(ctx) / target).exists():
        return None
    if now is None:
        return f"{target} exists and is not a file"
    if now == sha:
        return None
    last = last_written(ctx.store, target)
    if last is None:
        return f"{target} already exists and was not written by Baton"
    rid, ev = last
    if rid != ctx.run_id or ev.step_path != step_path:
        return f"{target} was last published by {'run ' + rid if rid != ctx.run_id else 'this run'} (step {ev.step_path})"
    if now != ev.data.get("sha256"):
        return f"{target} was edited since Baton published it"
    return None


def publish_due(ctx: RunContext) -> list[str]:
    """Write every due deliverable that has no conflict; the paths written or confirmed."""
    out = []
    for d in due(ctx):
        if d.conflict is None and d.target is not None:
            _write(ctx, d, d.target)
            out.append(d.target)
    return out


def _write(ctx: RunContext, d: Due, target: str, *, actor: str = "runtime", extra: dict[str, Any] | None = None) -> None:
    full = project_root(ctx) / target
    unchanged = file_sha(full) == d.sha256
    if not unchanged:
        write_file(full, ctx.log.cas.read(d.sha256))
    data = {"artifact": d.artifact, "path": target, "sha256": d.sha256, "attempt": d.passed.attempt, "passed_seq": d.passed.seq,
            **({"unchanged": True} if unchanged else {}), **(extra or {})}
    ctx.log.append("artifact_published", actor=actor, step_path=d.step_path, data=data)


def conflicts(ctx: RunContext) -> list[Due]:
    return [d for d in due(ctx) if d.conflict is not None]


def outstanding(ctx: RunContext) -> bool:
    """Whether a publish conflict or drift is pending (either holds run completion)."""
    return bool(conflicts(ctx)) or bool(drift(ctx.log.events(), project_root(ctx)))


def pending(ctx: RunContext) -> list[dict[str, Any]]:
    """The owner decisions deliverables owe (§10.4, §10.5), in ``pending_decisions`` form."""
    out: list[dict[str, Any]] = []
    for d in conflicts(ctx):
        opts = labels.options("publish_conflict", [o for o in CONFLICT_DECISIONS if not (d.unrenderable and o == "overwrite")])
        out.append({
            "ref": d.ref, "step_path": d.step_path, "kind": "publish_conflict", "artifact": d.artifact, "path": d.target,
            "reason": "publish_conflict", "reasons": [d.conflict],
            "prompt": f"Publishing {d.artifact} of {d.step_path}: {d.conflict}. Overwrite it, keep the existing file, or publish under another name?",
            "options": opts,
        })
    held = {(d.step_path, d.artifact) for d in conflicts(ctx)}
    for x in drift(ctx.log.events(), project_root(ctx)):
        if (x["step_path"], x["artifact"]) in held:
            continue  # the pending conflict decides this file
        gone = x["current_sha256"] is None
        out.append({
            "ref": x["ref"], "step_path": x["step_path"], "kind": "drift", "artifact": x["artifact"], "path": x["path"],
            "current_sha256": x["current_sha256"],
            "prompt": (f"{x['path']} ({x['artifact']} of {x['step_path']}) was deleted after publishing; later steps keep the recorded version"
                       if gone else f"{x['path']} ({x['artifact']} of {x['step_path']}) was edited after publishing; later steps still get the recorded version"),
            "options": [labels.option("drift", "leave")] + ([] if gone else [labels.option(
                "drift", "ingest", command=f"baton ingest-revision {ctx.run_id} {x['step_path']} {x['artifact']} --note \"<your words>\"")]),
        })
    return out


def record_drift(ctx: RunContext) -> int:
    """Record ``drift_detected`` once per new hash (mutating calls only). The number recorded."""
    n = 0
    for x in drift(ctx.log.events(), project_root(ctx)):
        if not x["recorded"]:
            ctx.log.append("drift_detected", step_path=x["step_path"], data={k: x[k] for k in ("artifact", "path", "published_sha256", "current_sha256")})
            n += 1
    return n


def deliverable_paths(ctx: RunContext) -> list[Path]:
    """This run's published files that exist, for its checkpoint commits (§10.1)."""
    root = project_root(ctx)
    paths = {e.data["path"] for e in ctx.log.events() if e.type == "artifact_published" and not e.data.get("kept")}
    return [root / p for p in sorted(paths) if (root / p).is_file()]


# ---------------------------------------------------------------------------
# Owner decisions
# ---------------------------------------------------------------------------


def _split_ref(ref: str, prefix: str) -> tuple[str, str]:
    body = ref[len(prefix):]
    if "." not in body:
        raise EngineError("decide.bad_ref", f"{ref!r} must be {prefix}<step_path>.<artifact>")
    sp, art = body.rsplit(".", 1)
    return sp, art


def decide_conflict(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    d = next((x for x in conflicts(ctx) if x.ref == ref), None)
    if d is None:
        raise EngineError("decide.nothing_pending", f"{ref} has no pending publish conflict")
    if decision not in CONFLICT_DECISIONS:
        raise EngineError("decide.bad_decision", f"decision must be one of {CONFLICT_DECISIONS}, got {decision!r}")
    if decision == "overwrite" and d.target is None:
        raise EngineError("decide.bad_decision", f"{ref}: the target cannot be rendered ({d.conflict}); keep it or publish it at --path")
    if path is not None and decision != "alternate":
        raise EngineError("decide.bad_decision", "--path is only for alternate")
    target = d.target
    if decision == "alternate":
        if path is not None:
            target = check_target(project_root(ctx), path)
        elif d.target is None:
            raise EngineError("decide.needs_path", f"{ref}: the target cannot be rendered; give the path to publish at with --path")
        else:
            target = alternate_name(d.target, ctx.run_id)
        why = conflict_reason(ctx, d.step_path, target, d.sha256)
        if why is not None:
            raise EngineError("publish.conflict", f"the alternate target conflicts too: {why}; give another --path")
    decision_id = f"d{ctx.log.state().last_seq + 1}"
    ctx.log.append("human_decision", actor=actor, step_path=d.step_path, data={
        "ref": ref, "kind": "publish", "decision": decision, "note": note, "decision_id": decision_id, "artifact": d.artifact,
        "path": target, "reason": d.conflict, **extra,
    })
    if decision == "keep":
        ctx.log.append("artifact_published", actor=actor, step_path=d.step_path, data={
            "artifact": d.artifact, "path": d.target, "sha256": d.sha256, "attempt": d.passed.attempt, "passed_seq": d.passed.seq,
            "kept": True, "decision_id": decision_id,
        })
    else:
        assert target is not None
        _write(ctx, d, target, actor=actor, extra={"decision_id": decision_id, decision if decision == "alternate" else "overwrote": target if decision == "alternate" else True})
    return {"ref": ref, "decision": decision, "path": target, "decision_id": decision_id}


def decide_drift(ctx: RunContext, ref: str, decision: str, note: str, actor: str, extra: dict[str, Any]) -> dict[str, Any]:
    x = next((x for x in drift(ctx.log.events(), project_root(ctx)) if x["ref"] == ref), None)
    if x is None:
        raise EngineError("decide.nothing_pending", f"{ref} has no pending drift")
    if decision not in DRIFT_DECISIONS:
        raise EngineError("decide.bad_decision", f"decision must be leave (or use ingest-revision), got {decision!r}")
    if not x["recorded"]:
        ctx.log.append("drift_detected", step_path=x["step_path"], data={k: x[k] for k in ("artifact", "path", "published_sha256", "current_sha256")})
    decision_id = f"d{ctx.log.state().last_seq + 1}"
    ctx.log.append("human_decision", actor=actor, step_path=x["step_path"], data={
        "ref": ref, "kind": "drift", "decision": "leave", "note": note, "decision_id": decision_id, "artifact": x["artifact"],
        "path": x["path"], "current_sha256": x["current_sha256"], **extra,
    })
    return {"ref": ref, "decision": "leave", "decision_id": decision_id}


def possibly_stale(ctx: RunContext, step_id: str) -> list[str]:
    """Passed or imported steps downstream of ``step_id`` (transitively, through groups)."""
    nodes = {n.id: n for n in ctx.recipe.recipe.steps}
    down: set[str] = set()
    changed = True
    while changed:
        changed = False
        for n in nodes.values():
            if n.id not in down and any(dep == step_id or dep in down for dep in n.depends_on):
                down.add(n.id)
                changed = True
    out = []
    for path, st in sorted(ctx.log.state().steps.items()):
        if path.split("/")[0] in down and st.state in ("passed", "imported"):
            out.append(path)
    return out


def ingest(ctx: RunContext, step_path: str, artifact: str, content: bytes, *, note: str, feed: str, actor: str,
           source: str, extra: dict[str, Any], decision: dict[str, Any], path: str | None) -> dict[str, Any]:
    """Store a human revision of a published artifact and record what it feeds (§10.5)."""
    if feed not in FEEDS:
        raise EngineError("revision.bad_feed", f"feed must be one of {FEEDS}, got {feed!r}")
    sha = ctx.log.cas.put(content)
    t = tracked(ctx.log.events()).get((step_path, artifact))
    n = len(t.revisions) + 1 if t else 1
    decision_id = f"d{ctx.log.state().last_seq + 1}"
    ctx.log.append("human_decision", actor=actor, step_path=step_path, data={**decision, "note": note, "decision_id": decision_id, "artifact": artifact, **extra})
    stale = possibly_stale(ctx, step_path)
    data = {"artifact": artifact, "path": path, "sha256": sha, "revision": n, "feed": feed, "possibly_stale": stale,
            "decision_id": decision_id, "source": source, "size": len(content)}
    ctx.log.append("human_revision_ingested", actor=actor, step_path=step_path, data=data)
    return {"step_path": step_path, "artifact": artifact, "revision": n, "sha256": sha, "decision_id": decision_id, "possibly_stale": stale,
            "reference": f"human_revision.{step_path}.{artifact}"}


def ingest_drift(ctx: RunContext, step_path: str, artifact: str, note: str, feed: str, actor: str, extra: dict[str, Any]) -> dict[str, Any]:
    ref = f"drift:{step_path}.{artifact}"
    x = next((x for x in drift(ctx.log.events(), project_root(ctx)) if x["ref"] == ref), None)
    if x is None:
        raise EngineError("revision.no_drift", f"{step_path}.{artifact}: the published file has not changed; there is nothing to ingest")
    if x["current_sha256"] is None:
        raise EngineError("revision.deleted", f"{x['path']} was deleted; a deleted file can only be left (decide {ref} leave)")
    if not note.strip():
        raise EngineError("revision.no_note", "ingesting a revision is the owner's decision; give their words with --note")
    if not x["recorded"]:
        ctx.log.append("drift_detected", step_path=step_path, data={k: x[k] for k in ("artifact", "path", "published_sha256", "current_sha256")})
    content = (project_root(ctx) / x["path"]).read_bytes()
    return ingest(ctx, step_path, artifact, content, note=note, feed=feed, actor=actor, source="drift", extra=extra,
                  decision={"ref": ref, "kind": "drift", "decision": "ingest"}, path=x["path"])


def latest_revision(events: list[Any], step_path: str, artifact: str, *, feed_before: int | None = None) -> Any:
    """The latest ``human_revision_ingested`` for an artifact; with ``feed_before``, the latest one that feeds
    dependents and was recorded before that seq (a step's first dispatch) or at any time when ``0``."""
    best = None
    for e in events:
        if e.type == "human_revision_ingested" and e.step_path == step_path and e.data.get("artifact") == artifact:
            if feed_before is None:
                best = e
            elif e.data.get("feed") == "dependents" and (feed_before == 0 or e.seq < feed_before):
                best = e
    return best


def revision_for_dependent(events: list[Any], source: str, artifact: str, step_path: str) -> Any:
    """The revision a dependent step's ``steps.<source>.artifacts.<artifact>`` input gets, if any.

    Fed only to a step that had not started (no attempt dispatched) when the
    revision was ingested with ``feed: dependents``; a step already under way
    keeps the recorded artifact for every later attempt."""
    first = next((e.seq for e in events if e.type == "dispatched" and e.step_path == step_path), 0)
    return latest_revision(events, source, artifact, feed_before=first)


def possibly_stale_flags(events: list[Any]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        if e.type == "human_revision_ingested":
            for p in e.data.get("possibly_stale") or []:
                out.append({"step_path": p, "source": e.step_path, "artifact": e.data.get("artifact"), "revision": e.data.get("revision")})
    return out



def ingest_sme(ctx: RunContext, step_path: str, artifact: str, content: bytes, *, note: str, feed: str, actor: str,
               extra: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """An expert's content promoted as a revision (§12.2): ingested, then written to the published path."""
    if (step_path, artifact) not in {(s, a.name) for s, a in published_artifacts(ctx.recipe.recipe)}:
        raise EngineError("revision.not_published", f"{step_path}.{artifact} is not a published artifact of {ctx.recipe.recipe.ref}")
    events = ctx.log.events()
    t = tracked(events).get((step_path, artifact))
    if t is None or t.path is None or any(d.step_path == step_path and d.artifact == artifact for d in due(ctx)):
        raise EngineError("revision.not_published", f"{step_path}.{artifact} has no published file to revise yet")
    full = project_root(ctx) / t.path
    if file_sha(full) != t.expected:
        raise EngineError("revision.drifted", f"{t.path} changed since Baton published it; settle that drift first (leave or ingest it)")
    passed = _last_passed(events, step_path)
    res = ingest(ctx, step_path, artifact, content, note=note, feed=feed, actor=actor, source="sme", extra=extra, decision=decision, path=t.path)
    write_file(full, content)
    ctx.log.append("artifact_published", actor=actor, step_path=step_path, data={
        "artifact": artifact, "path": t.path, "sha256": res["sha256"], "attempt": passed.attempt if passed else None,
        "passed_seq": passed.seq if passed else None, "revision": res["revision"], "decision_id": res["decision_id"],
    })
    return {**res, "path": t.path}
