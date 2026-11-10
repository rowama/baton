"""Machine-wide quota exhaustion (§8.8; Decision 0114).

A route that reports its quota used up (a free route's daily limit, a
subscription's limit) is left out of routing until the quota resets, so the
step re-routes to the next eligible worker instead of trying it again.
Kept in ``~/.baton/quota.yaml`` by profile name, never in a profile file, so
recording one changes no profile hash (as capability states, 0084).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

FILE = "quota.yaml"
FORMAT = "baton-quota/1"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def next_reset(now: dt.datetime) -> dt.datetime:
    """The next UTC midnight: when daily request quotas (OpenRouter's free models) reset."""
    return (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def load(home: Path, now: dt.datetime | None = None) -> dict[str, dt.datetime]:
    """Profile -> the time its quota resets, for entries still in the future. An unreadable file means none."""
    now = now or _now()
    try:
        raw = yaml.safe_load((Path(home) / FILE).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):  # expected: no or unreadable file means no recorded exhaustion
        return {}
    out: dict[str, dt.datetime] = {}
    for name, until in (raw.get("profiles") or {}).items():
        try:
            t = dt.datetime.fromisoformat(str(until))
        except ValueError:  # expected: a bad entry is ignored
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        if t > now:
            out[str(name)] = t
    return out


def record(home: Path, profile: str, now: dt.datetime | None = None) -> dt.datetime:
    """Record ``profile``'s quota exhausted until the next reset; returns that time."""
    now = now or _now()
    until = next_reset(now)
    entries = load(home, now)
    entries[profile] = until
    path = Path(home) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"format": FORMAT, "profiles": {n: t.isoformat() for n, t in sorted(entries.items())}}
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    return until
