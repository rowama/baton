#!/usr/bin/env python
"""The test tiers of §17.1 (change 2026-11-fast-tests): the quick gate.

    python tools/testrun.py quick [--dry-run]
    python tools/testrun.py start [SHA]
    python tools/testrun.py status [--red]
    python tools/testrun.py require-green [SHA] [--wait]

``start`` runs the full suite for one commit in a separate git worktree, detached, and records the result per SHA in
a ledger under the git directory (never committed; shared by every worktree of the repository). ``status`` lists the
ledger. ``require-green`` exits 0 only for a finished, green record of that exact commit; for ``HEAD`` the worktree
must also be clean. It is the finish gate (AGENTS.md).

``quick`` runs the tests a slice's changes can affect, minus the ``slow`` ones, in parallel. It never runs less
than is safe:

- no testmon data, or no record of the last commit it passed on: every non-``slow`` test;
- a changed file that is neither under ``docs/`` nor a ``.py`` file: every non-``slow`` test;
- ``.py`` changes: the tests ``pytest-testmon`` says they affect;
- a change under ``docs/``: also ``tests/test_docs.py``.

Code that runs only in child processes is invisible to testmon; those paths are covered by the ``slow`` tests, which
only the full suite (background run, CI, finish gate) runs. Plain Python, no dependency beyond pytest, xdist and testmon.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PYTEST = [sys.executable, "-m", "pytest", "-n", "auto", "--dist", "worksteal", "-q"]
QUICK_MARK = ["-m", "not slow"]
NOTHING_COLLECTED = 5  # pytest's exit code when testmon selects nothing


@dataclass(frozen=True)
class Plan:
    mode: str  # "all" (every non-slow test), "affected" (testmon selects), "docs" (only the docs test)
    reason: str
    docs_test: bool = False  # also run tests/test_docs.py

    def commands(self) -> list[list[str]]:
        if self.mode == "docs":
            return [[*PYTEST, "tests/test_docs.py"]]
        select = "--testmon-noselect" if self.mode == "all" else "--testmon-forceselect"
        cmds = [[*PYTEST, *QUICK_MARK, select]]
        if self.docs_test:
            cmds.append([*PYTEST, "tests/test_docs.py"])
        return cmds


def plan(changed: list[str], have_data: bool, have_base: bool) -> Plan:
    """Choose what the quick gate runs. ``changed`` are repo-relative paths with forward slashes."""
    if not have_data:
        return Plan("all", "no testmon data yet")
    if not have_base:
        return Plan("all", "no record of the last commit the quick gate passed on")
    odd = sorted(p for p in changed if not (p.startswith("docs/") or p.endswith(".py")))
    if odd:
        return Plan("all", f"non-Python file outside docs/ changed: {odd[0]}")
    docs = any(p.startswith("docs/") for p in changed)
    if changed and all(p.startswith("docs/") for p in changed):
        return Plan("docs", "only docs/ changed")
    return Plan("affected", "Python changes: testmon selects", docs_test=docs)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def repo_root(start: Path | None = None) -> Path:
    return Path(_git(start or Path.cwd(), "rev-parse", "--show-toplevel").strip())


def _base_file(root: Path) -> Path:
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir").strip())
    return git_dir / "baton-quick-base"


def read_base(root: Path) -> str | None:
    """The commit the quick gate last passed on, if it is still in this repository."""
    f = _base_file(root)
    if not f.exists():
        return None
    sha = f.read_text(encoding="utf-8").strip()
    ok = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True)
    return sha if sha and ok.returncode == 0 else None


def write_base(root: Path) -> None:
    f = _base_file(root)
    f.write_text(_git(root, "rev-parse", "HEAD").strip() + "\n", encoding="utf-8")


def changed_files(root: Path, base: str | None) -> list[str]:
    """Files that differ from ``base`` in commits, the index or the working tree, plus untracked ones."""
    names: set[str] = set()
    if base:
        names.update(_git(root, "diff", "--name-only", "-z", "--no-renames", base).split("\0"))
    names.update(_git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0"))
    names.discard("")
    return sorted(str(PurePosixPath(n)) for n in names)


def quick(root: Path, dry_run: bool = False) -> int:
    base = read_base(root)
    p = plan(changed_files(root, base), (root / ".testmondata").exists(), base is not None)
    print(f"quick gate: {p.mode} ({p.reason})", flush=True)
    if dry_run:
        for cmd in p.commands():
            print("  " + " ".join(cmd[2:]))
        return 0
    for cmd in p.commands():
        rc = subprocess.run(cmd, cwd=root).returncode
        if rc not in (0, NOTHING_COLLECTED):
            return rc
    write_base(root)
    return 0


# --- the ledger and the background full run -------------------------------------------------------------------

LEDGER_DIR = "baton-testruns"


def ledger_dir(root: Path) -> Path:
    common = Path(_git(root, "rev-parse", "--git-common-dir").strip())
    d = (common if common.is_absolute() else root / common) / LEDGER_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def resolve(root: Path, rev: str) -> str:
    return _git(root, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def read_record(root: Path, sha: str) -> dict | None:
    f = ledger_dir(root) / f"{sha}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_record(root: Path, rec: dict) -> None:
    f = ledger_dir(root) / f"{rec['sha']}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)


def state_of(rec: dict | None) -> str:
    """none | running | green | red | lost (the run died without recording a result) | error."""
    if rec is None:
        return "none"
    if rec.get("state") == "running":
        from baton.supervisor import pid_alive

        return "running" if pid_alive(rec.get("pid")) else "lost"
    if rec.get("state") == "error":
        return "error"
    return "green" if rec.get("passed") else "red"


def default_workers() -> int:
    """One fewer than the cores, so the quick gate beside a background run is not starved."""
    return max(1, (os.cpu_count() or 2) - 1)


def start(root: Path, sha: str, *, workers: int | None = None, use_venv: bool = True, force: bool = False) -> dict:
    """Launch the full suite for ``sha`` in the background; returns its (running) record."""
    existing = read_record(root, sha)
    if existing and not force and state_of(existing) in ("running", "green"):
        return existing
    from baton.supervisor import _detached

    n = workers or default_workers()
    rec = {"sha": sha, "tree": _git(root, "rev-parse", f"{sha}^{{tree}}").strip(), "state": "running", "started": _now(),
           "finished": None, "passed": None, "failed": [], "wall_s": None, "workers": n,
           "python": platform.python_version(), "os": platform.platform()}
    log = ledger_dir(root) / f"{sha}.log"
    argv = [sys.executable, str(Path(__file__).resolve()), "_run", sha, "--workers", str(n), "--root", str(root)]
    if not use_venv:
        argv.append("--no-venv")
    with open(log, "wb") as out:
        proc = _detached(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, cwd=root)
    rec["pid"] = proc.pid
    write_record(root, rec)
    return rec


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _make_run_env(wt: Path) -> Path:
    """A venv whose ``baton`` is this worktree's ``src`` and whose other packages are the current environment's.

    The development install points at the main checkout, which would test the wrong code. Children that tests spawn
    (``sys.executable -m baton``) find the worktree's source through the venv's own .pth, whatever env they are given.
    """
    venv = wt / ".venv-run"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True)
    site = Path(_git(wt, "rev-parse", "--show-toplevel").strip())  # the worktree root, normalised
    purelib = Path(subprocess.run([str(_venv_python(venv)), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                                  check=True, capture_output=True, text=True).stdout.strip())
    purelib.mkdir(parents=True, exist_ok=True)
    (purelib / "baton-run.pth").write_text(f"{site / 'src'}\n{sysconfig.get_paths()['purelib']}\n", encoding="utf-8")
    return _venv_python(venv)


FAILED_LINE = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


def run_full(root: Path, sha: str, *, workers: int, use_venv: bool = True) -> dict:
    """The body of a background run: worktree, full suite, record, clean up. Blocks until the suite ends."""
    ldir = ledger_dir(root)
    rec = read_record(root, sha) or {"sha": sha, "tree": _git(root, "rev-parse", f"{sha}^{{tree}}").strip(), "started": _now()}
    wt = ldir / f"wt-{sha[:12]}"
    t0 = time.monotonic()
    try:
        if wt.exists():
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(wt)], capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
        _git(root, "worktree", "add", "--detach", str(wt), sha)
        python = _make_run_env(wt) if use_venv else Path(sys.executable)
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        cmd = [str(python), "-m", "pytest", "-n", str(workers), "--dist", "worksteal", "-q", "-rfE", "-p", "no:cacheprovider"]
        done = subprocess.run(cmd, cwd=wt, env=env, capture_output=True, text=True)
        output = done.stdout + done.stderr
        sys.stdout.write(output)
        rec.update(state="finished", passed=done.returncode == 0, failed=sorted(set(FAILED_LINE.findall(output))),
                   summary=(output.strip().splitlines() or [""])[-1])
    except Exception as e:  # recorded, so a lost run is never mistaken for a green one
        rec.update(state="error", passed=False, error=f"{type(e).__name__}: {e}")
    finally:
        subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(wt)], capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "-C", str(root), "worktree", "prune"], capture_output=True)
    rec.update(finished=_now(), wall_s=round(time.monotonic() - t0, 1))
    write_record(root, rec)
    return rec


def wait_for(root: Path, sha: str, timeout: float | None = None, poll: float = 2.0) -> dict | None:
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        rec = read_record(root, sha)
        if state_of(rec) != "running":
            return rec
        if deadline is not None and time.monotonic() > deadline:
            return rec
        time.sleep(poll)


def is_clean(root: Path) -> bool:
    return _git(root, "status", "--porcelain").strip() == ""


def require_green(root: Path, rev: str = "HEAD", *, wait: bool = False) -> tuple[bool, str]:
    sha = resolve(root, rev)
    rec = wait_for(root, sha) if wait else read_record(root, sha)
    st = state_of(rec)
    if st != "green":
        extra = f" (failed: {', '.join(rec['failed'][:5])})" if st == "red" and rec and rec["failed"] else ""
        return False, f"{sha[:12]}: full suite is {st}, not green{extra}"
    if rec["sha"] != sha:  # pragma: no cover - the file name is the sha
        return False, f"{sha[:12]}: ledger record is for {rec['sha'][:12]}"
    if sha == resolve(root, "HEAD") and not is_clean(root):
        return False, f"{sha[:12]}: green, but the working tree has uncommitted changes"
    return True, f"{sha[:12]}: full suite green ({rec['wall_s']} s, {rec.get('summary', '')})"


def records(root: Path) -> list[dict]:
    out = []
    for f in ledger_dir(root).glob("*.json"):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("started", ""), reverse=True)


def status(root: Path, red_only: bool = False, limit: int = 15) -> list[str]:
    lines = []
    for rec in records(root)[:limit if not red_only else None]:
        st = state_of(rec)
        if red_only and st not in ("red", "error", "lost"):
            continue
        if red_only:
            lines.append(rec["sha"])
            continue
        subject = _git(root, "log", "-1", "--format=%s", rec["sha"]).strip() if _exists(root, rec["sha"]) else "(commit gone)"
        detail = f"{len(rec.get('failed') or [])} failed" if st in ("red",) else (f"{rec['wall_s']} s" if rec.get("wall_s") else "")
        lines.append(f"{rec['sha'][:12]}  {st.upper():8} {detail:10} {subject}")
    return lines


def _exists(root: Path, sha: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("quick", help="run the quick gate")
    q.add_argument("--dry-run", action="store_true", help="print what would run")
    st = sub.add_parser("start", help="run the full suite for a commit in the background")
    st.add_argument("sha", nargs="?", default="HEAD")
    st.add_argument("--workers", type=int)
    st.add_argument("--force", action="store_true", help="start again even if a run is going or green")
    sts = sub.add_parser("status", help="list recent full runs")
    sts.add_argument("--red", action="store_true", help="print only the SHAs of red runs (for git bisect skip)")
    rg = sub.add_parser("require-green", help="exit 0 only if the full suite is green on this exact commit")
    rg.add_argument("sha", nargs="?", default="HEAD")
    rg.add_argument("--wait", action="store_true", help="wait for a running suite to finish")
    run = sub.add_parser("_run")  # internal: the detached body of `start`
    run.add_argument("sha")
    run.add_argument("--workers", type=int, required=True)
    run.add_argument("--root", required=True)
    run.add_argument("--no-venv", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "_run":
        rec = run_full(Path(args.root), args.sha, workers=args.workers, use_venv=not args.no_venv)
        return 0 if rec["passed"] else 1
    root = repo_root()
    if args.cmd == "quick":
        return quick(root, dry_run=args.dry_run)
    if args.cmd == "start":
        rec = start(root, resolve(root, args.sha), workers=args.workers, force=args.force)
        print(f"{rec['sha'][:12]}: full suite {state_of(rec)} (pid {rec.get('pid')}); results: python tools/testrun.py status")
        return 0
    if args.cmd == "status":
        print("\n".join(status(root, red_only=args.red)))
        return 0
    ok, msg = require_green(root, args.sha, wait=args.wait)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
