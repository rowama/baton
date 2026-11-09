#!/usr/bin/env python
"""The test tiers of §17.1 (change 2026-11-fast-tests): the quick gate.

    python tools/testrun.py quick [--dry-run]

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
import subprocess
import sys
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("quick", help="run the quick gate")
    q.add_argument("--dry-run", action="store_true", help="print what would run")
    args = ap.parse_args(argv)
    return quick(repo_root(), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
