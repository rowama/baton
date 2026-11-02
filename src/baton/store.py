"""Event logs, the content-addressed store, and the SQLite cache (§8.3).

Layout under ``<project>/.baton/``::

    runs/<run_id>/events.jsonl     run log (hash-chained, append-only)
    runs/<run_id>/cas/<aa>/<sha>   content-addressed blobs
    project/events.jsonl           project log
    cache/state.db                 derived cache; delete it at any time

**The logs are the source of truth.** Every append is checked by the state
machine (``state.py``) against the current state *before* anything is
written, so a log only ever holds legal sequences. The cache is updated after
each append and is trusted only while it matches the log's size and last
hash; otherwise the run is replayed from its log ("events always win").

**Line format.** Each event is one line of canonical JSON (sorted keys, no
insignificant whitespace, UTF-8, LF). ``sha256`` covers the event without its
``sha256`` key; ``prev_sha256`` is the previous event's ``sha256``. ``seq``
starts at 1 and has no gaps. See ``models.Event``.

**Writers.** One writer per log at a time is assumed; an append refuses if
the log changed since its state was read. Real locking (leases, project
lock) is Phase 10 (``locks.py``).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from pydantic import ValidationError

from .models import (
    EVENT_TYPES,
    EVENTS_FORMATS,
    PROJECT_EVENT_TYPES,
    RUN_EVENT_TYPES,
    Event,
    Issue,
    RunStatus,
    StepStatus,
)
from .state import IllegalTransition, RunState, StepState

BATON_DIR = ".baton"
EVENTS_FILE = "events.jsonl"
CACHE_SCHEMA_VERSION = "1"
_CHUNK = 1 << 20

Clock = Callable[[], datetime]


class StoreError(Exception):
    """A log, blob or cache problem. ``issues`` lists every problem found."""

    def __init__(self, message: str, issues: list[Issue] | None = None):
        super().__init__(message)
        self.issues = issues or []


class ConcurrentAppend(StoreError):
    """The log changed between reading its state and appending."""


# ---------------------------------------------------------------------------
# Hashing and files
# ---------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """Sorted keys, no insignificant whitespace, non-ASCII kept as UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def event_sha256(event: dict[str, Any]) -> str:
    """SHA-256 of an event's canonical JSON without its ``sha256`` key."""
    body = {k: v for k, v in event.items() if k != "sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents), user-only on POSIX (§15.1)."""
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def atomic_write(path: Path, data: bytes, *, read_only: bool = False) -> None:
    """Write via a temp file in the same directory, fsync, rename."""
    ensure_dir(path.parent)
    tmp = path.parent / f".tmp-{secrets.token_hex(8)}"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if read_only:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            _force_unlink(tmp)


def _force_unlink(p: Path) -> None:
    try:
        os.chmod(p, stat.S_IWUSR | stat.S_IRUSR)
    except OSError:
        pass
    p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CAS
# ---------------------------------------------------------------------------


class CAS:
    """Content-addressed blobs at ``<root>/<sha[:2]>/<sha>``, written atomically, read-only."""

    def __init__(self, root: Path):
        self.root = root

    def path(self, sha: str) -> Path:
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError(f"not a SHA-256 hex digest: {sha!r}")
        return self.root / sha[:2] / sha

    def has(self, sha: str) -> bool:
        return self.path(sha).is_file()

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        target = self.path(sha)
        if not target.is_file():
            atomic_write(target, data, read_only=True)
        return sha

    def put_file(self, src: Path) -> str:
        """Ingest a file without holding it in memory."""
        h = hashlib.sha256()
        shard_tmp = ensure_dir(self.root) / f".tmp-{secrets.token_hex(8)}"
        try:
            with open(src, "rb") as fin, open(shard_tmp, "wb") as fout:
                for chunk in iter(lambda: fin.read(_CHUNK), b""):
                    h.update(chunk)
                    fout.write(chunk)
                fout.flush()
                os.fsync(fout.fileno())
            sha = h.hexdigest()
            target = self.path(sha)
            if not target.is_file():
                ensure_dir(target.parent)
                os.chmod(shard_tmp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                os.replace(shard_tmp, target)
            return sha
        finally:
            if shard_tmp.exists():
                _force_unlink(shard_tmp)

    def read(self, sha: str, *, verify: bool = True) -> bytes:
        p = self.path(sha)
        if not p.is_file():
            raise StoreError(f"blob {sha} missing", [Issue(code="cas.missing", where=str(p), message="blob missing")])
        data = p.read_bytes()
        if verify and hashlib.sha256(data).hexdigest() != sha:
            raise StoreError(f"blob {sha} corrupt", [Issue(code="cas.corrupt", where=str(p), message="content does not match its hash")])
        return data

    def verify(self, expected: set[str] | None = None) -> list[Issue]:
        """Every blob matches its name; with ``expected``, every expected blob exists."""
        issues: list[Issue] = []
        if self.root.is_dir():
            for p in sorted(self.root.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(self.root).as_posix()
                if p.name.startswith(".tmp-"):
                    issues.append(Issue(code="cas.stray_temp", where=str(p), message="leftover temporary file", severity="warning"))
                    continue
                parts = rel.split("/")
                if len(parts) != 2 or parts[0] != p.name[:2] or len(p.name) != 64:
                    issues.append(Issue(code="cas.stray_file", where=str(p), message="not a CAS blob path"))
                    continue
                if _file_sha256(p) != p.name:
                    issues.append(Issue(code="cas.corrupt", where=str(p), message="content does not match its hash"))
        for sha in sorted(expected or ()):
            if not self.has(sha):
                issues.append(Issue(code="cas.missing", where=str(self.path(sha)), message="referenced blob missing"))
        return issues


def _file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Event logs
# ---------------------------------------------------------------------------


class EventLog:
    """An append-only, hash-chained JSONL log.

    The base class checks the envelope and the chain. ``RunLog`` adds the
    state machine and the cache.
    """

    kind = "project"

    def __init__(self, path: Path, run_id: str | None, allowed: frozenset[str], clock: Clock):
        self.path = path
        self.run_id = run_id
        self.allowed = allowed
        self.clock = clock

    # -- reading ------------------------------------------------------------

    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except FileNotFoundError:
            return 0

    def _lines(self) -> Iterator[tuple[int, bytes, bool]]:
        """(line number, raw bytes without LF, complete?)."""
        if not self.path.is_file():
            return
        raw = self.path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]  # tolerate a BOM (§15.1)
        chunks = raw.split(b"\n")
        tail = chunks.pop()  # b"" when the file ends with LF
        for i, chunk in enumerate(chunks, start=1):
            yield i, chunk, True
        if tail:
            yield len(chunks) + 1, tail, False

    def scan(self, fold: RunState | None = None) -> tuple[list[Event], list[Issue]]:
        """Read and check every line. With ``fold``, also replay it through the state machine."""
        events: list[Event] = []
        issues: list[Issue] = []
        prev_sha: str | None = None
        expected_seq = 1
        where_base = str(self.path)

        def err(line: int, code: str, message: str) -> None:
            issues.append(Issue(code=code, where=f"{where_base}:{line}", message=message))

        for line, raw, complete in self._lines():
            if not complete:
                err(line, "events.truncated", "last line is incomplete (no line ending)")
                break
            try:
                obj = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                err(line, "events.unparsable", f"not valid JSON: {e}")
                break
            if not isinstance(obj, dict):
                err(line, "events.unparsable", "not a JSON object")
                break
            try:
                ev = Event.model_validate(obj)
            except ValidationError as e:
                err(line, "events.invalid", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
                break
            if event_sha256(obj) != ev.sha256:
                err(line, "events.hash_mismatch", f"event seq {ev.seq} does not match its sha256")
                break
            if ev.prev_sha256 != prev_sha:
                err(line, "events.chain_broken", f"prev_sha256 of seq {ev.seq} does not match the previous event")
                break
            if ev.seq != expected_seq:
                err(line, "events.seq_gap", f"expected seq {expected_seq}, found {ev.seq}")
                break
            if ev.format not in EVENTS_FORMATS:
                err(line, "events.unknown_format", f"format {ev.format!r} is not readable by this runtime")
                break
            if ev.type not in self.allowed:
                code = "events.unknown_type" if ev.type not in EVENT_TYPES else "events.wrong_log"
                err(line, code, f"event type {ev.type!r} does not belong in a {self.kind} log")
                break
            if ev.run_id != self.run_id:
                err(line, "events.wrong_run", f"run_id {ev.run_id!r} in the log of {self.run_id!r}")
                break
            if fold is not None:
                try:
                    fold.apply(ev.model_dump())
                except IllegalTransition as e:
                    err(line, "events.impossible_state", f"seq {ev.seq}: {e}")
                    break
            events.append(ev)
            prev_sha = ev.sha256
            expected_seq += 1
        return events, issues

    def events(self) -> list[Event]:
        events, issues = self.scan()
        if issues:
            raise StoreError(f"{self.path}: log is invalid", issues)
        return events

    def verify(self) -> list[Issue]:
        """Every problem with the log (empty when the chain and content check out)."""
        return self.scan(RunState(self.run_id) if self.kind == "run" else None)[1]

    # -- writing ------------------------------------------------------------

    def _tail(self) -> tuple[int, str | None, int]:
        """(last seq, last sha256, file size) for the base log, by reading it."""
        size = self.size()
        events = self.events()
        if not events:
            return 0, None, size
        return events[-1].seq, events[-1].sha256, size

    def _build(
        self, etype: str, actor: str, step_path: str | None, attempt: int | None, data: dict | None, last_seq: int, last_sha: str | None
    ) -> dict[str, Any]:
        if etype not in self.allowed:
            known = etype in EVENT_TYPES
            raise StoreError(
                f"event type {etype!r} " + ("does not belong in a " + self.kind + " log" if known else "is unknown"),
                [Issue(code="events.wrong_log" if known else "events.unknown_type", message=etype)],
            )
        ev: dict[str, Any] = {
            "format": EVENTS_FORMATS[-1],
            "seq": last_seq + 1,
            "ts": format_ts(self.clock()),
            "run_id": self.run_id,
            "step_path": step_path,
            "attempt": attempt,
            "type": etype,
            "actor": actor,
            "data": data or {},
            "prev_sha256": last_sha,
        }
        try:
            canonical_json(ev)  # data must be plain JSON
        except (TypeError, ValueError) as e:
            raise StoreError(f"event data is not JSON-serializable: {e}") from e
        ev["sha256"] = event_sha256(ev)
        Event.model_validate(ev)  # envelope check (actor, attempt >= 1, ...)
        return ev

    def _write(self, ev: dict[str, Any], expected_size: int) -> None:
        ensure_dir(self.path.parent)
        line = (canonical_json(ev) + "\n").encode("utf-8")
        with open(self.path, "ab") as f:
            if f.tell() != expected_size:
                raise ConcurrentAppend(f"{self.path} changed while appending; re-read and retry")
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def append(
        self, etype: str, *, actor: str = "runtime", step_path: str | None = None, attempt: int | None = None, data: dict | None = None
    ) -> Event:
        last_seq, last_sha, size = self._tail()
        ev = self._build(etype, actor, step_path, attempt, data, last_seq, last_sha)
        self._write(ev, size)
        return Event.model_validate(ev)


class RunLog(EventLog):
    """A run's log. Appends go through the state machine and keep the cache current."""

    kind = "run"

    def __init__(self, store: Store, run_id: str):
        super().__init__(store.run_dir(run_id) / EVENTS_FILE, run_id, RUN_EVENT_TYPES, store.clock)
        self.store = store
        self.cas = CAS(store.run_dir(run_id) / "cas")

    def state(self) -> RunState:
        return self.store._state(self)[0]

    def append(
        self, etype: str, *, actor: str = "runtime", step_path: str | None = None, attempt: int | None = None, data: dict | None = None
    ) -> Event:
        """Append one event, or raise ``IllegalTransition`` / ``StoreError`` and write nothing."""
        current, size = self.store._state(self)
        ev = self._build(etype, actor, step_path, attempt, data, current.last_seq, current.last_sha256)
        new = RunState(
            run_id=current.run_id,
            state=current.state,
            max_attempts=current.max_attempts,
            last_seq=current.last_seq,
            last_sha256=current.last_sha256,
            steps=dict(current.steps),
        )
        new.apply(ev)
        self._write(ev, size)
        self.store._save(self, new, changed=step_path)
        return Event.model_validate(ev)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta  (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs  (run_id TEXT PRIMARY KEY, state TEXT, max_attempts INTEGER,
                                  last_seq INTEGER NOT NULL, last_sha256 TEXT, log_size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS steps (run_id TEXT NOT NULL, step_path TEXT NOT NULL, state TEXT NOT NULL,
                                  attempt INTEGER NOT NULL, budget_base INTEGER NOT NULL, last_seq INTEGER NOT NULL,
                                  PRIMARY KEY (run_id, step_path));
"""


class _Cache:
    def __init__(self, path: Path):
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def conn(self) -> sqlite3.Connection:
        if self._conn is not None and not self.path.exists():
            self.close()  # deleted underneath us: start fresh
        if self._conn is None:
            ensure_dir(self.path.parent)
            self._conn = sqlite3.connect(self.path)
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if row is None or row[0] != CACHE_SCHEMA_VERSION:
                with self._conn:
                    self._conn.execute("DELETE FROM runs")
                    self._conn.execute("DELETE FROM steps")
                    self._conn.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (CACHE_SCHEMA_VERSION,))
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def load(self, run_id: str) -> tuple[RunState, int] | None:
        c = self.conn()
        row = c.execute("SELECT state, max_attempts, last_seq, last_sha256, log_size FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        rs = RunState(run_id=run_id, state=row[0], max_attempts=row[1], last_seq=row[2], last_sha256=row[3])
        for path, st, attempt, base, seq in c.execute(
            "SELECT step_path, state, attempt, budget_base, last_seq FROM steps WHERE run_id=?", (run_id,)
        ):
            rs.steps[path] = StepState(state=st, attempt=attempt, budget_base=base, last_seq=seq)
        return rs, row[4]

    def save(self, rs: RunState, log_size: int, changed: str | None | object) -> None:
        """Write the run row and the changed step (or all steps when ``changed`` is ``ALL``)."""
        c = self.conn()
        with c:
            c.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
                (rs.run_id, rs.state, rs.max_attempts, rs.last_seq, rs.last_sha256, log_size),
            )
            if changed is _ALL:
                c.execute("DELETE FROM steps WHERE run_id=?", (rs.run_id,))
                paths = list(rs.steps)
            else:
                paths = [changed] if changed in rs.steps else []
            for p in paths:
                s = rs.steps[p]
                c.execute("INSERT OR REPLACE INTO steps VALUES (?,?,?,?,?,?)", (rs.run_id, p, s.state, s.attempt, s.budget_base, s.last_seq))

    def clear(self) -> None:
        c = self.conn()
        with c:
            c.execute("DELETE FROM runs")
            c.execute("DELETE FROM steps")


_ALL = object()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class Store:
    """Everything under ``<project>/.baton/`` that Phase 2 owns."""

    def __init__(self, project_root: str | Path, *, clock: Clock = utc_now):
        self.root = Path(project_root)
        self.baton = self.root / BATON_DIR
        self.clock = clock
        self._cache = _Cache(self.baton / "cache" / "state.db")

    # -- paths --------------------------------------------------------------

    @property
    def runs_dir(self) -> Path:
        return self.baton / "runs"

    @property
    def cache_path(self) -> Path:
        return self._cache.path

    def run_dir(self, run_id: str) -> Path:
        if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
            raise ValueError(f"invalid run id {run_id!r}")
        return self.runs_dir / run_id

    def run_ids(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(p.name for p in self.runs_dir.iterdir() if (p / EVENTS_FILE).is_file())

    # -- logs ---------------------------------------------------------------

    def run(self, run_id: str) -> RunLog:
        if not (self.run_dir(run_id) / EVENTS_FILE).is_file():
            raise StoreError(f"no run {run_id!r}", [Issue(code="store.no_run", message=run_id)])
        return RunLog(self, run_id)

    def project_log(self) -> EventLog:
        return EventLog(self.baton / "project" / EVENTS_FILE, None, PROJECT_EVENT_TYPES, self.clock)

    def new_run_id(self) -> str:
        day = self.clock().astimezone(timezone.utc).strftime("%Y%m%d")
        while True:
            rid = f"r_{day}_{secrets.token_hex(2)}"
            if not self.run_dir(rid).exists():
                return rid

    def start_run(self, data: dict[str, Any], *, actor: str = "runtime", run_id: str | None = None) -> RunLog:
        """Create a run directory and append ``run_started``.

        ``data`` is the work item, recipe and versions (§8.9);
        ``data.max_attempts`` bounds retries (``state.py``).
        """
        rid = run_id or self.new_run_id()
        rdir = self.run_dir(rid)
        if rdir.exists():
            raise StoreError(f"run {rid!r} already exists", [Issue(code="store.run_exists", message=rid)])
        ensure_dir(rdir)
        log = RunLog(self, rid)
        log.append("run_started", actor=actor, data=data)
        return log

    # -- state and cache ----------------------------------------------------

    def _state(self, log: RunLog) -> tuple[RunState, int]:
        """(current state, log size): the cache when it matches the log, otherwise a replay."""
        hit = self._cache.load(log.run_id)
        size = log.size()
        if hit is not None and hit[1] == size:
            return hit[0], size
        return self._replay(log, size), size

    def _replay(self, log: RunLog, size: int | None = None) -> RunState:
        size = log.size() if size is None else size
        rs = RunState(log.run_id)
        _, issues = log.scan(rs)
        if issues:
            raise StoreError(f"run {log.run_id}: log is invalid", issues)
        self._cache.save(rs, size, _ALL)
        return rs

    def _save(self, log: RunLog, rs: RunState, changed: str | None) -> None:
        self._cache.save(rs, log.size(), changed)

    def status(self, run_id: str) -> RunStatus:
        rs = self.run(run_id).state()
        return RunStatus(
            run_id=run_id,
            state=rs.state or "not_started",
            last_seq=rs.last_seq,
            last_sha256=rs.last_sha256,
            steps={p: StepStatus(state=s.state, attempt=s.attempt, last_seq=s.last_seq) for p, s in sorted(rs.steps.items())},
        )

    def rebuild(self) -> list[Issue]:
        """Discard the cache and replay every run. Returns problems; runs with problems are left uncached."""
        self._cache.clear()
        issues: list[Issue] = []
        for rid in self.run_ids():
            try:
                self._replay(RunLog(self, rid))
            except StoreError as e:
                issues.extend(e.issues)
        return issues

    def verify(self) -> list[Issue]:
        """Chain and state checks for every log, and integrity of every run's CAS."""
        issues = self.project_log().verify()
        for rid in self.run_ids():
            log = RunLog(self, rid)
            issues += log.verify()
            issues += log.cas.verify()
        return issues

    def close(self) -> None:
        self._cache.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
