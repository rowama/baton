"""Diagnostics: what the runtime works around, recorded apart from the event log (§8.3, Decision 0094).

``note(code, where, **data)`` records one diagnostic. It never raises and never blocks work. Records go to
``$BATON_HOME/diag/raw/<YYYY-MM-DD>/<pid>-<rand>.jsonl`` (UTC day), one file per process, so writers never
interleave and no lock is needed. Every string is redacted on write. Nothing here is a source of truth: the
state machine never reads it and nothing is decided from it.

Storage is bounded without a daemon. The first ``note`` of a UTC day that wins an exclusive create of
``diag/.maintained-<day>`` runs maintenance (``doctor`` runs it too): raw days are rolled up into
``diag/counts/<day>.json``, then pruned by usage-day age and by total size, and old counts are pruned. A
*usage day* is a UTC day with at least one record on this machine, so idle weeks age nothing out.
"""

from __future__ import annotations

import atexit
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redact import redact_text

DEFAULTS = {
    "raw_days": 14,
    "raw_max_bytes": 64 * 1024 * 1024,
    "count_days": 180,
    "burst": 100,
}
SAMPLE_EVERY = 100  # after the burst, one record in this many is written (carrying the ones it stands for)
_CONTEXT_KEYS = ("project", "run", "step_path", "attempt")

# Process state: a file per (process, day), per-code counters per day, and the failures swallowed so far.
_rand = secrets.token_hex(4)
_failures = 0
_seen: dict[tuple[str, str], int] = {}  # (day, code) -> notes so far in this process
_pending: dict[tuple[str, str], int] = {}  # (day, code) -> suppressed notes not yet written
_maintaining = False
_burst_cache: int | None = None
_atexit_registered = False


def home() -> Path:
    return Path(os.environ.get("BATON_HOME") or Path.home() / ".baton")


def diag_dir() -> Path:
    return home() / "diag"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def failures() -> int:
    """How many failures ``note`` has swallowed in this process."""
    return _failures


def limits() -> dict[str, int]:
    """The machine's limits: the defaults, overridden by integers in the optional ``$BATON_HOME/diag.yaml``."""
    out = dict(DEFAULTS)
    try:
        import yaml

        raw = yaml.safe_load((home() / "diag.yaml").read_text(encoding="utf-8")) or {}
        for k in out:
            v = raw.get(k) if isinstance(raw, dict) else None
            if isinstance(v, int) and not isinstance(v, bool) and v > 0:
                out[k] = v
    except Exception:  # diag: absent or unreadable settings mean the defaults
        pass
    return out


def _clean(v: Any) -> Any:
    if isinstance(v, str):
        return redact_text(v)
    if isinstance(v, dict):
        return {redact_text(str(k)): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [_clean(x) for x in v]
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return redact_text(str(v))


def _append(day: str, record: dict[str, Any]) -> None:
    d = diag_dir() / "raw" / day
    d.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    # One file per process and day; opened for append per record, so a long-lived process holds no handle.
    with open(d / f"{os.getpid()}-{_rand}.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def note(code: str, where: str, **data: Any) -> None:
    """Record a diagnostic. ``project``, ``run``, ``step_path`` and ``attempt`` in ``data`` are lifted to the record."""
    global _failures, _atexit_registered
    try:
        now = _now()
        day = now.strftime("%Y-%m-%d")
        key = (day, code)
        n = _seen[key] = _seen.get(key, 0) + 1
        burst = _burst()
        count, suppressed = 1, 0
        if n > burst:
            if (n - burst) % SAMPLE_EVERY:
                _pending[key] = _pending.get(key, 0) + 1
                if not _atexit_registered:
                    atexit.register(flush)
                    _atexit_registered = True
                return
            suppressed = SAMPLE_EVERY - 1
            count = SAMPLE_EVERY
            _pending.pop(key, None)
        rec: dict[str, Any] = {
            "ts": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "code": _clean(code),
            "where": _clean(where),
            "pid": os.getpid(),
        }
        for k in _CONTEXT_KEYS:
            if data.get(k) is not None:
                rec[k] = _clean(data.pop(k))
            else:
                data.pop(k, None)
        rec["data"] = _clean(data)
        rec["count"] = count
        if suppressed:
            rec["suppressed"] = suppressed
        _append(day, rec)
        _maintain_once(day)
    except Exception:  # diag: note never raises; the failure is counted
        _failures += 1


def _burst() -> int:
    """The burst limit, read once per process (``reset`` forgets it)."""
    global _burst_cache
    if _burst_cache is None:
        _burst_cache = limits()["burst"]
    return _burst_cache


def reset() -> None:
    """Forget this process's counters, file name and cached limits (for tests)."""
    global _rand, _failures, _burst_cache, _maintaining
    _seen.clear()
    _pending.clear()
    _rand = secrets.token_hex(4)
    _failures = 0
    _burst_cache = None
    _maintaining = False


def flush() -> None:
    """Write the suppressed notes still pending, so counts stay exact when the process ends."""
    global _failures
    try:
        for (day, code), n in list(_pending.items()):
            _append(day, {"ts": _now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "code": code, "where": "diag:flush",
                          "pid": os.getpid(), "data": {}, "count": n, "suppressed": n})
            del _pending[(day, code)]
    except Exception:  # diag: flush is best effort
        _failures += 1


# -- reading ------------------------------------------------------------------------------------------------


def _raw_days(root: Path | None = None) -> list[str]:
    """UTC days with raw records, oldest first."""
    raw = (root or diag_dir()) / "raw"
    try:
        return sorted(p.name for p in raw.iterdir() if p.is_dir() and any(f.stat().st_size for f in p.glob("*.jsonl")))
    except OSError:
        return []


def read_records(day: str) -> list[dict[str, Any]]:
    """The raw records of one day, oldest first (lines that do not parse are skipped)."""
    out: list[dict[str, Any]] = []
    try:
        files = sorted((diag_dir() / "raw" / day).glob("*.jsonl"))
    except OSError:
        return out
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and "code" in rec:
                out.append(rec)
    return sorted(out, key=lambda r: str(r.get("ts", "")))


def _tally(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """{project: {code: count}}, where each record stands for ``count`` notes."""
    out: dict[str, dict[str, int]] = {}
    for r in records:
        c = r.get("count")
        out.setdefault(str(r.get("project") or ""), {}).setdefault(str(r["code"]), 0)
        out[str(r.get("project") or "")][str(r["code"])] += c if isinstance(c, int) and c > 0 else 1
    return out


def _count_days() -> list[str]:
    try:
        return sorted(p.stem for p in (diag_dir() / "counts").glob("*.json"))
    except OSError:
        return []


def daily_counts() -> dict[str, dict[str, dict[str, int]]]:
    """{day: {project: {code: count}}} for every usage day on record: raw where it still exists, else the rollup."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    for day in _count_days():
        try:
            data = json.loads((diag_dir() / "counts" / f"{day}.json").read_text(encoding="utf-8"))
            out[day] = {p: {c: int(n) for c, n in codes.items()} for p, codes in data["counts"].items()}
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            continue  # diag: an unreadable rollup is skipped; the raw day, if kept, still counts below
    for day in _raw_days():
        out[day] = _tally(read_records(day))
    return dict(sorted(out.items()))


# -- maintenance --------------------------------------------------------------------------------------------


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def rollup(day: str) -> None:
    """Write ``counts/<day>.json`` from the day's raw records (atomic; the same raw gives the same file)."""
    counts = _tally(read_records(day))
    _write_atomic(diag_dir() / "counts" / f"{day}.json", json.dumps({"day": day, "counts": counts}, sort_keys=True, indent=1) + "\n")


def _rm_raw_day(day: str) -> None:
    d = diag_dir() / "raw" / day
    for f in d.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        d.rmdir()
    except OSError:
        pass


def _day_bytes(day: str) -> int:
    total = 0
    for f in (diag_dir() / "raw" / day).glob("*"):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def maintain(today: str | None = None) -> None:
    """Roll up raw days before today, then prune raw days (usage-day age, total size) and old counts. May raise."""
    today = today or _today()
    lim = limits()
    days = _raw_days()
    for d in days:
        if d != today:
            rollup(d)
    keep = set(days[-lim["raw_days"]:]) | {today}
    for d in days:
        if d not in keep:
            _rm_raw_day(d)
    days = [d for d in _raw_days() if d != today]
    total = sum(_day_bytes(d) for d in _raw_days())
    for d in days:  # oldest first
        if total <= lim["raw_max_bytes"]:
            break
        total -= _day_bytes(d)
        _rm_raw_day(d)
    counted = _count_days()
    for d in counted[: max(0, len(counted) - lim["count_days"])]:
        try:
            (diag_dir() / "counts" / f"{d}.json").unlink()
        except OSError:
            pass


def maintain_once(day: str | None = None) -> bool:
    """Run maintenance if no process has yet today on this machine. Returns whether this call ran it. Never raises."""
    global _maintaining
    day = day or _today()
    if _maintaining:
        return False
    try:
        d = diag_dir()
        d.mkdir(parents=True, exist_ok=True)
        fd = os.open(d / f".maintained-{day}", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except OSError:
        return False  # someone has, or the home is unwritable
    _maintaining = True
    try:
        maintain(day)
        for old in d.glob(".maintained-*"):
            if old.name != f".maintained-{day}":
                try:
                    old.unlink()
                except OSError:
                    pass
    except Exception as e:  # diag: noted once, never raised
        _maintaining = False
        note("diag.maintenance_failed", "diag:maintain", error=f"{type(e).__name__}: {e}")
    finally:
        _maintaining = False
    return True


def _maintain_once(day: str) -> None:
    maintain_once(day)


# -- reporting (baton diag, doctor; Decision 0094) --------------------------------------------------------------

RECENT_DAYS = 7  # the usage days a summary and the unusual rule look at
BASELINE_DAYS = 30  # the usage days before those, which set a code's normal rate
UNUSUAL_MIN_COUNT = 5
UNUSUAL_FACTOR = 3.0


def _by_code(day: dict[str, dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for codes in day.values():
        for c, n in codes.items():
            out[c] = out.get(c, 0) + n
    return out


def unusual_codes(daily: dict[str, dict[str, dict[str, int]]] | None = None) -> list[dict[str, Any]]:
    """Codes whose last 7 usage days are unusual for this machine: at least 5 notes, and either more than 3 times the
    per-usage-day rate of the 30 usage days before those, or no such baseline (first seen). Machine-wide, all projects."""
    daily = daily_counts() if daily is None else daily
    days = sorted(daily)
    recent = days[-RECENT_DAYS:]
    base = days[max(0, len(days) - RECENT_DAYS - BASELINE_DAYS): max(0, len(days) - RECENT_DAYS)]
    now = _by_code({d: _merge(daily[d]) for d in recent})
    before = _by_code({d: _merge(daily[d]) for d in base})
    out = []
    for code, n in now.items():
        if n < UNUSUAL_MIN_COUNT:
            continue
        b = before.get(code, 0)
        if b == 0:
            first = next(d for d in days if code in _merge(daily[d]))
            out.append({"code": code, "last_7d": n, "baseline_per_day": 0.0, "first_seen": first})
        elif n / len(recent) > UNUSUAL_FACTOR * (b / len(base)):
            out.append({"code": code, "last_7d": n, "baseline_per_day": round(b / len(base), 2)})
    return sorted(out, key=lambda u: (-u["last_7d"], u["code"]))


def _merge(projects: dict[str, dict[str, int]]) -> dict[str, int]:
    """One day's counts, summed over projects: {code: n}."""
    return _by_code(projects)


def _window(days: list[str], since: str | int | None) -> list[str]:
    if since is None:
        return days[-RECENT_DAYS:]
    if isinstance(since, int) or str(since).isdigit():
        return days[-int(since):] if int(since) > 0 else []
    return [d for d in days if d >= str(since)]


def records(*, since: str | int | None = None, code: str | None = None, run: str | None = None, limit: int | None = 200) -> list[dict[str, Any]]:
    """Raw records in the window, oldest first (the newest ``limit`` of them), optionally of one code prefix or run."""
    out: list[dict[str, Any]] = []
    for day in _window(_raw_days(), since):
        for r in read_records(day):
            if (code is None or str(r["code"]).startswith(code)) and (run is None or r.get("run") == run):
                out.append(r)
    return out[-limit:] if limit else out


def records_for(run: str, step_path: str | None, attempt: int | None) -> list[dict[str, Any]]:
    """Every raw record of this run (and step, and attempt, where the record names them): an incident's evidence."""
    out = []
    for day in _raw_days():
        for r in read_records(day):
            if r.get("run") != run:
                continue
            if step_path is not None and r.get("step_path") not in (None, step_path):
                continue
            if attempt is not None and r.get("attempt") not in (None, attempt):
                continue
            out.append(r)
    return out


def summary(*, since: str | int | None = None, code: str | None = None, run: str | None = None) -> dict[str, Any]:
    """Counts per code over the window next to each code's baseline, unusual codes first."""
    daily = daily_counts()
    days = sorted(daily)
    window = _window(days, since)
    if run is not None:  # a run is known only in raw records
        counts: dict[str, int] = {}
        for r in records(since=since, code=code, run=run, limit=None):
            counts[str(r["code"])] = counts.get(str(r["code"]), 0) + (r.get("count") if isinstance(r.get("count"), int) else 1)
    else:
        counts = _by_code({d: _merge(daily[d]) for d in window})
        if code:
            counts = {c: n for c, n in counts.items() if c.startswith(code)}
    unusual = {u["code"]: u for u in unusual_codes(daily)}
    base = days[max(0, len(days) - RECENT_DAYS - BASELINE_DAYS): max(0, len(days) - RECENT_DAYS)]
    before = _by_code({d: _merge(daily[d]) for d in base})
    rows = []
    for c, n in counts.items():
        row: dict[str, Any] = {"code": c, "count": n, "baseline_per_day": round(before.get(c, 0) / len(base), 2) if base else 0.0,
                               "unusual": c in unusual}
        if c in unusual and "first_seen" in unusual[c]:
            row["first_seen"] = unusual[c]["first_seen"]
        rows.append(row)
    rows.sort(key=lambda r: (not r["unusual"], -r["count"], r["code"]))
    return {"usage_days": len(window), "since": window[0] if window else None, "codes": rows,
            "unusual": [u for u in unusual.values() if not code or u["code"].startswith(code)]}


def worker_logs(home_dir: Path | None = None) -> dict[str, Any]:
    """Total size of the raw worker logs and the age of the oldest one. Reported, never pruned."""
    root = (home_dir or home()) / "logs"
    total, files, oldest = 0, 0, None
    try:
        for f in root.rglob("*"):
            try:
                if not f.is_file():
                    continue
                st = f.stat()
            except OSError:
                continue
            total += st.st_size
            files += 1
            oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
    except OSError:
        pass
    age = None if oldest is None else round(max(0.0, (_now().timestamp() - oldest) / 86400), 1)
    return {"bytes": total, "files": files, "oldest_age_days": age}
