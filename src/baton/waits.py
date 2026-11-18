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


# -- what is waiting (criterion 8) ------------------------------------------------

#: The interval used when no waiting step gives ``every``, and the shortest allowed (Decision 0165, item 4).
DEFAULT_EVERY_S = 30 * 60
MIN_EVERY_S = 5 * 60


def describe(ctx: Any, baton_dir: Path) -> list[dict[str, Any]]:
    """Each waiting step of a run, in plain terms: what it waits for, since when, until when, last checked."""
    from .groups import locate

    out = []
    record = ctx.record()
    for path, st in sorted(ctx.log.state().steps.items()):
        if st.state != "waiting":
            continue
        ev = record.last("wait_started", path, st.attempt)
        d = ev.data if ev is not None else {}
        loc = locate(ctx.recipe, path)
        title = getattr(loc.node, "title", None) if loc is not None else None
        cached = entry(baton_dir, ctx.run_id, path, st.attempt)
        item: dict[str, Any] = {
            "step_path": path, "attempt": st.attempt, "waits_for": title or path, "tool": d.get("tool"),
            "since": ev.ts if ev is not None else None, "deadline": d.get("deadline"), "every": d.get("every"),
            "on_expire": d.get("on_expire", "escalate"), "last_checked": cached.get("last_checked"),
            "failed_checks": int(cached.get("failures") or 0),
        }
        if d.get("cut_to"):
            item["cut_to"] = d["cut_to"]
        if cached.get("last_failure") and item["failed_checks"]:
            item["last_failure"] = cached["last_failure"]
        out.append(item)
    return out


def interval_seconds(everies: list[str | None]) -> float:
    """The scheduler's interval: the shortest ``every`` given, never under five minutes; 30 minutes when none is."""
    from .models import duration_seconds

    given = [duration_seconds(e) for e in everies if e]
    return max(MIN_EVERY_S, min(given)) if given else DEFAULT_EVERY_S


# -- the optional helper: a scheduler entry (criterion 6; Decision 0165, items 6 and 7) --

#: The comment that marks this project's crontab line, so it is found again and removed.
CRON_MARK = "# baton-waits "


def platform_name() -> str:
    """``linux`` | ``macos`` | ``wsl`` | ``windows``."""
    import platform
    import sys

    if os.name == "nt":
        return "windows"
    if "microsoft" in platform.uname().release.lower():
        return "wsl"
    return "macos" if sys.platform == "darwin" else "linux"


def task_name(root: Path) -> str:
    import hashlib

    return "Baton waits " + hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:8]


def baton_command() -> list[str]:
    """How a scheduler starts ``baton``: the launcher on the path, else this interpreter."""
    import shutil
    import sys

    found = shutil.which("baton")
    return [found] if found else [sys.executable, "-m", "baton"]


def _quote_posix(word: str) -> str:
    import shlex

    return shlex.quote(word)


def cron_spec(seconds: float) -> str:
    minutes = max(1, int(seconds // 60))
    if minutes < 60:
        return f"*/{minutes} * * * *"
    hours = minutes // 60
    return f"0 */{hours} * * *" if hours < 24 else "0 0 * * *"


def cron_line(root: Path, home: Path, seconds: float, command: list[str] | None = None) -> str:
    cmd = " ".join(_quote_posix(w) for w in [*(command or baton_command()), "--project", str(root), "waits", "check"])
    log = _quote_posix(str(home / "logs" / "waits-check.log"))
    return f"{cron_spec(seconds)} {cmd} >> {log} 2>&1 {CRON_MARK}{root}"


def task_command(root: Path, system: str, command: list[str] | None = None) -> str:
    """What Task Scheduler runs: ``baton`` on Windows, or ``baton`` inside this WSL distribution (item 7)."""
    import subprocess

    words = [*(command or baton_command()), "--project", str(root), "waits", "check"]
    if system == "wsl":
        distro = os.environ.get("WSL_DISTRO_NAME", "")
        inner = " ".join(_quote_posix(w) for w in words)
        return subprocess.list2cmdline(["wsl.exe", *(["-d", distro] if distro else []), "--", "sh", "-c", inner])
    return subprocess.list2cmdline(words)


def task_args(root: Path, system: str, seconds: float, command: list[str] | None = None) -> list[str]:
    minutes = max(1, int(seconds // 60))
    when = ["/SC", "MINUTE", "/MO", str(minutes)] if minutes <= 1439 else ["/SC", "DAILY"]
    return ["/Create", "/F", "/TN", task_name(root), *when, "/TR", task_command(root, system, command)]


def _run(argv: list[str], stdin: str | None = None) -> tuple[int, str]:
    """Run a scheduler command; (exit code, output). A missing program is exit 127."""
    import subprocess

    try:
        p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:  # expected: no crontab or schtasks here; reported as not available
        return 127, f"{argv[0]} is not available"
    except subprocess.TimeoutExpired:  # expected: a scheduler that hangs; reported to the owner as not answering
        return 124, f"{argv[0]} did not answer within a minute"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _schtasks(system: str) -> str:
    return "schtasks.exe" if system == "wsl" else "schtasks"


def _crontab() -> tuple[bool, list[str]]:
    code, text = _run(["crontab", "-l"])
    if code == 127:
        return False, []
    return True, [ln for ln in text.splitlines() if ln.strip()] if code == 0 else []


def plan(root: Path, home: Path, seconds: float, system: str | None = None) -> dict[str, Any]:
    """The entry ``waits schedule`` would install on this machine, and what it does."""
    system = system or platform_name()
    every = _every_text(seconds)
    does = f"runs `baton waits check` for this project every {every}: it checks each waiting step once and exits"
    if system in ("windows", "wsl"):
        args = task_args(root, system, seconds)
        scheduler = "Task Scheduler"
        entry_text = " ".join([_schtasks(system), *args])
        if system == "wsl":
            does += "; it starts the check inside WSL, so it runs even when no Linux terminal is open"
    else:
        scheduler = "cron"
        entry_text = cron_line(root, home, seconds)
    return {"platform": system, "scheduler": scheduler, "entry": entry_text, "interval_s": seconds, "every": every, "does": does,
            "task_name": task_name(root) if scheduler == "Task Scheduler" else None}


def _every_text(seconds: float) -> str:
    """``30 minutes``, ``2 hours``, ``day``: the interval in plain words."""
    minutes = max(1, int(seconds // 60))
    if minutes < 60:
        return f"{minutes} minutes" if minutes != 1 else "minute"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours" if hours != 1 else "hour"
    return "day"


def notice(state: dict[str, Any], system: str) -> str | None:
    """What to tell the owner when waiting steps have nothing scheduled to check them (criterion 8), or None."""
    if is_scheduled(state, system):
        return None
    if system == "wsl" and state.get("cron"):
        return ("a cron entry checks waiting steps, but cron runs only while WSL is running; "
                "`baton waits schedule --install` adds a Windows Task Scheduler entry that runs the check inside WSL")
    return ("nothing on this machine is scheduled to check waiting steps: they are checked only when `baton waits check` runs "
            "(the assistant runs it when it resumes); `baton waits schedule` shows the entry that would check them regularly")


def installed(root: Path, system: str | None = None) -> dict[str, Any]:
    """Whether this project's entry is installed: ``{cron, task}``, each True, False, or None when that scheduler is not available."""
    system = system or platform_name()
    out: dict[str, Any] = {"cron": None, "task": None}
    if system != "windows":
        ok, lines = _crontab()
        out["cron"] = any(ln.endswith(f"{CRON_MARK}{root}") for ln in lines) if ok else None
    if system in ("windows", "wsl"):
        code, _text = _run([_schtasks(system), "/Query", "/TN", task_name(root)])
        out["task"] = None if code == 127 else code == 0
    return out


def is_scheduled(state: dict[str, Any], system: str) -> bool:
    """A check is scheduled that keeps running: on WSL only a Task Scheduler entry does (cron stops with WSL; item 7)."""
    return bool(state.get("task")) if system == "wsl" else bool(state.get("cron") or state.get("task"))


def install(root: Path, home: Path, seconds: float, system: str | None = None) -> dict[str, Any]:
    """Install the entry (replacing this project's earlier one). Only when the owner asked: ``waits schedule --install``."""
    system = system or platform_name()
    p = plan(root, home, seconds, system)
    if p["scheduler"] == "cron":
        ok, lines = _crontab()
        if not ok:
            return {**p, "installed": False, "problem": "crontab is not available on this machine"}
        keep = [ln for ln in lines if not ln.endswith(f"{CRON_MARK}{root}")]
        code, text = _run(["crontab", "-"], "\n".join([*keep, cron_line(root, home, seconds)]) + "\n")
    else:
        code, text = _run([_schtasks(system), *task_args(root, system, seconds)])
    if code != 0:
        return {**p, "installed": False, "problem": text.strip() or f"exit {code}"}
    return {**p, "installed": True}


def remove(root: Path, system: str | None = None) -> dict[str, Any]:
    """Remove this project's entry from every scheduler that has it."""
    system = system or platform_name()
    removed: list[str] = []
    problems: list[str] = []
    if system != "windows":
        ok, lines = _crontab()
        if ok and any(ln.endswith(f"{CRON_MARK}{root}") for ln in lines):
            keep = [ln for ln in lines if not ln.endswith(f"{CRON_MARK}{root}")]
            code, text = _run(["crontab", "-"], "\n".join(keep) + "\n" if keep else "")
            (removed.append("cron") if code == 0 else problems.append(text.strip() or f"crontab exit {code}"))
    if system in ("windows", "wsl"):
        code, _t = _run([_schtasks(system), "/Query", "/TN", task_name(root)])
        if code == 0:
            code, text = _run([_schtasks(system), "/Delete", "/F", "/TN", task_name(root)])
            (removed.append("Task Scheduler") if code == 0 else problems.append(text.strip() or f"schtasks exit {code}"))
    return {"platform": system, "removed": removed, "problems": problems}
