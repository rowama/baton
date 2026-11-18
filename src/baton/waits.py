"""Waiting steps (§8.7; Decisions 0154 item 5, 0165): what is kept between checks.

A waiting step is held as state in its run's log (``waiting``), with no Baton
process alive. ``baton waits check`` runs each waiting step's check once and
exits; this module keeps what a check that finds nothing leaves behind, so the
log records only that a wait started, was met or expired (criterion 10):

* ``.baton/cache/waits.json`` (machine-local): per waiting attempt, when it was
  last checked, and the count of failed checks in a row with the last
  failure's reason. A good check resets the count; the third failure in a row
  escalates the step (Decision 0165, item 2).
* ``.baton/cache/locks/waits.lock``: held for a whole ``waits check``, so two
  checks never overlap; a second one reports that it is busy and exits.
"""

from __future__ import annotations

import json
import os
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from . import diag, locks

#: Failed checks in a row after which the step waits on the owner (Decision 0165, item 2).
FAILED_CHECKS_LIMIT = 3


def cache_path(baton_dir: Path) -> Path:
    return baton_dir / "cache" / "waits.json"


def key(run_id: str, step_path: str, attempt: int) -> str:
    return f"{run_id}/{step_path}#{attempt}"


def read(baton_dir: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(cache_path(baton_dir).read_text(encoding="utf-8"))
    except FileNotFoundError:  # expected: nothing checked yet on this machine
        return {}
    except (OSError, ValueError) as e:
        diag.note("waits.cache_unreadable", "waits:read", error=f"{type(e).__name__}: {e}")
        return {}
    return raw if isinstance(raw, dict) else {}


def entry(baton_dir: Path, run_id: str, step_path: str, attempt: int) -> dict[str, Any]:
    return read(baton_dir).get(key(run_id, step_path, attempt)) or {}


def update(baton_dir: Path, run_id: str, step_path: str, attempt: int, **changes: Any) -> dict[str, Any]:
    """Merge ``changes`` into one attempt's entry and drop entries of runs that are gone; returns the entry."""
    with locks.project_lock(baton_dir):
        data = read(baton_dir)
        k = key(run_id, step_path, attempt)
        mine = data[k] = {**(data.get(k) or {}), **changes}
        runs = baton_dir / "runs"
        data = {kk: v for kk, v in data.items() if (runs / kk.split("/", 1)[0]).is_dir()}
        p = cache_path(baton_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)
        return mine


def forget(baton_dir: Path, run_id: str, step_path: str, attempt: int) -> None:
    """Drop one attempt's entry: its wait ended."""
    with locks.project_lock(baton_dir):
        data = read(baton_dir)
        if data.pop(key(run_id, step_path, attempt), None) is None:
            return
        p = cache_path(baton_dir)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)


def check_lock(baton_dir: Path) -> AbstractContextManager[bool]:
    """Held for a whole ``waits check``: True when taken, False when another check holds it."""
    return locks.try_file_lock(baton_dir / "cache" / "locks" / "waits.lock")
