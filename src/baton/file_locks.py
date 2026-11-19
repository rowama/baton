"""Approved file sets (§9.4; Decision 0173).

A ``human`` gate may declare ``locks: [globs]`` (or ``{paths, on_violation}``).
When the owner approves it, ``files_locked`` records the sha256 of every file
matching the globs. Every step of the run dispatched afterwards is bound by
the lock:

- at its dispatch, a difference (made outside any step) refuses the dispatch;
  the owner accepts the change (``decide lock:<step>#<gate> accept``) or the
  files are restored;
- at its intake, a difference it made is the implicit ``locked`` gate: ``warn``
  waits on the owner (approve keeps the change and records the set again),
  ``fail`` fails the gate.

A lock is released when its step is revised or goes stale; approving the gate
again records a new set. Everything here is derived from the run's events; the
only events are ``files_locked`` and ``locked_path_modified``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import reviews


@dataclass
class Lock:
    key: str  # the gate, with instance ids dropped: a new approval of the same gate supersedes the old set
    step_path: str  # the step whose gate's approval recorded it
    gate: int
    globs: list[str]
    mode: str  # warn | fail
    files: dict[str, str]  # {path: sha256} as approved (and as the owner later accepted)
    seq: int  # the files_locked event that set it
    decision_id: str | None
    commit: str | None = None
    history: list[int] = field(default_factory=list)  # every files_locked seq for this key, oldest first

    @property
    def ref(self) -> str:
        return f"lock:{self.step_path}#{self.gate}"

    def as_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "step_path": self.step_path, "gate": self.gate, "globs": self.globs, "mode": self.mode,
                "files": len(self.files), "decision_id": self.decision_id, "locked_seq": self.seq,
                **({"commit": self.commit} if self.commit else {})}


def key_of(recipe_ref: str, step_path: str, gate: int) -> str:
    from .sme import qualified

    return f"{qualified(recipe_ref, step_path)}#{gate}"


def live(events: Iterable[Any]) -> dict[str, Lock]:
    """The run's live locks, by key. None once the run has ended."""
    out: dict[str, Lock] = {}
    for e in events:
        d = e.data or {}
        if e.type in ("run_completed", "run_abandoned"):
            return {}
        if e.type == "files_locked":
            prev = out.get(d["key"])
            out[d["key"]] = Lock(
                key=d["key"], step_path=e.step_path, gate=d["gate"], globs=list(d["globs"]), mode=d.get("mode", "warn"),
                files={p["path"]: p["sha256"] for p in d.get("paths") or []}, seq=e.seq, decision_id=d.get("decision_id"),
                commit=d.get("commit"), history=[*(prev.history if prev else []), e.seq],
            )
        elif e.type in ("step_revised", "step_stale"):
            for k in [k for k, lk in out.items() if lk.step_path == e.step_path]:
                del out[k]  # released with the approval it came from (Decision 0173, item 3)
        elif e.type == "artifact_published" and not d.get("kept"):
            # The lock's own step publishing its approved deliverable, or a publish the owner decided, is part of the set.
            for lk in out.values():
                if reviews.matches(d["path"], lk.globs) and (e.step_path == lk.step_path or d.get("decision_id")):
                    lk.files[d["path"]] = d["sha256"]
    return out


def differences(root: Path, lock: Lock) -> list[str]:
    """What differs between the approved set and the files now: ``path``, ``path (added)``, ``path (deleted)``."""
    return reviews.protected_changes(lock.files, reviews.protected_snapshot(root, lock.globs))


def changed_paths(changes: list[str]) -> list[str]:
    return [c.rsplit(" (", 1)[0] if c.endswith((" (added)", " (deleted)")) else c for c in changes]


def record(log: Any, root: Path, *, key: str, step_path: str, gate: int, globs: list[str], mode: str, decision_id: str | None,
           cause: str, attempt: int | None = None, base: Lock | None = None, accept: list[str] | None = None) -> None:
    """Append ``files_locked``: the set now (a new approval), or ``base`` with ``accept``ed paths taken as they are now."""
    now = reviews.protected_snapshot(root, globs)
    if base is None or accept is None:
        files = now
    else:
        files = dict(base.files)
        for p in accept:
            if p in now:
                files[p] = now[p]
            else:
                files.pop(p, None)
    commit = reviews.repo_head(root)
    data: dict[str, Any] = {
        "key": key, "gate": gate, "globs": globs, "mode": mode, "cause": cause,
        "paths": [{"path": p, "sha256": h} for p, h in sorted(files.items())],
        **({"decision_id": decision_id} if decision_id else {}), **({"commit": commit} if commit else {}),
    }
    log.append("files_locked", step_path=step_path, attempt=attempt, data=data)


def dispatch_problem(events: list[Any], root: Path) -> tuple[list[dict[str, Any]], str | None]:
    """``(the live locks to record on the dispatch, why it is refused or None)``."""
    locks = live(events)
    held: list[str] = []
    for lk in locks.values():
        diff = differences(root, lk)
        if diff:
            shown = ", ".join(diff[:10]) + (f" and {len(diff) - 10} more" if len(diff) > 10 else "")
            held.append(f"{shown} (approved at {lk.step_path}, gate {lk.gate}; `decide {lk.ref} accept` keeps the change, "
                        f"or restore the files{' from ' + lk.commit[:12] if lk.commit else ''})")
    recorded = [{"key": lk.key, "seq": lk.seq} for lk in locks.values()]
    if held:
        return recorded, "files the owner approved were changed outside the process: " + "; ".join(held)
    return recorded, None


def in_flight_keys(ctx: Any) -> set[str]:
    """Locks bound to an attempt still in flight: its intake decides the difference, not a separate decision."""
    from .groups import IN_FLIGHT

    rs = ctx.log.state()
    out: set[str] = set()
    for p, st in rs.steps.items():
        if st.state not in IN_FLIGHT:
            continue
        rec = ctx.record()
        if any(e.type in ("gate_passed", "gate_failed") and (e.data or {}).get("gate") == "locked" for e in rec.attempt_events(p, st.attempt)):
            continue  # its intake already judged the locks; a later difference is not its own
        disp = rec.last("dispatched", p, st.attempt)
        for r in (disp.data.get("locks") or []) if disp else []:
            out.add(r["key"])
    return out


def pending(ctx: Any) -> list[dict[str, Any]]:
    """A ``locked_change`` decision per live lock whose files differ, unless an attempt in flight owns the difference."""
    from . import labels

    if ctx.log.state().state != "active":
        return []
    busy = in_flight_keys(ctx)
    out = []
    for lk in live(ctx.log.events()).values():
        if lk.key in busy:
            continue
        diff = differences(ctx.store.root, lk)
        if not diff:
            continue
        shown = ", ".join(diff[:20]) + (f" and {len(diff) - 20} more" if len(diff) > 20 else "")
        out.append({
            "ref": lk.ref, "step_path": lk.step_path, "kind": "locked_change", "reason": "locked_change", "changed": diff,
            "reasons": [f"files approved at {lk.step_path} were changed: {shown}"],
            "prompt": f"Files you approved at {lk.step_path} were changed outside the process: {shown}. Keep the change? "
                      f"(Otherwise restore them{' from commit ' + lk.commit[:12] if lk.commit else ''}; the next part waits until then.)",
            "options": labels.options("locked_change", ("accept",)),
        })
    return out


def find(events: list[Any], ref: str) -> Lock | None:
    return next((lk for lk in live(events).values() if lk.ref == ref), None)


def status(events: list[Any], root: Path) -> list[dict[str, Any]]:
    out = []
    for lk in live(events).values():
        diff = differences(root, lk)
        out.append({**lk.as_dict(), **({"changed": diff} if diff else {})})
    return out
