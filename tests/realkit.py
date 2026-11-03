"""Phase 16 helpers: a toy software project using the shipped ``software-feature`` recipe, scripted workers.

Workers are ``command`` profiles running ``fakes/recipe_worker.py``: ``builder``
(vendor acme) and ``checker`` (vendor globex) can do any step; ``owner`` is the
person (manual). The project's test command is ``check.py``, which fails when a
committed ``src/*.py`` contains ``BROKEN``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

from conftest import SOFTWARE_FEATURE
from projectkit import OWNER_PROFILE, Cli, git, make_git_project, make_home, packet_dir, write_result

WORKER = Path(__file__).parent / "fakes" / "recipe_worker.py"
ALL_CAPS = ["structured_output", "long_form_writing", "technical_reasoning", "tool_use", "file_write", "shell", "code_exec",
            "repo_workspace", "workspace_read"]
CHECK_PY = """\
import pathlib, sys
bad = [p.name for p in pathlib.Path("src").glob("*.py") if "BROKEN" in p.read_text(encoding="utf-8")]
print("broken:", bad) if bad else print("ok")
sys.exit(1 if bad else 0)
"""
SPEC = "# Acceptance specs\n\nLocked by the owner.\n"


def cmdline(argv: list[str]) -> str:
    return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)


def profiles(script: Path) -> str:
    line = cmdline([sys.executable, str(WORKER), "{packet}", "{result}", str(script), "{workspace}"])
    git_dir = str(Path(shutil.which("git")).parent)  # the worker commits; Windows' minimal system PATH has no git
    return OWNER_PROFILE + "".join(
        f"{name}:\n  adapter: command\n  vendor: {vendor}\n  command: {json.dumps(line)}\n  capabilities: {json.dumps(ALL_CAPS)}\n"
        f"  tier: strong\n  context_tokens: 128000\n  path: {json.dumps({'prepend': [git_dir]})}\n"
        for name, vendor in (("builder", "acme"), ("checker", "globex")))


def configure(root: Path, **changes: Any) -> None:
    py = root / ".baton" / "project.yaml"
    cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
    for k, v in changes.items():
        cfg[k] = {**cfg.get(k, {}), **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def make_toy_project(tmp_path: Path, script: dict, *, name: str = "app", home: Path | None = None) -> tuple[Cli, Path, Path]:
    """A committed toy repo with Baton initialized and software-feature vendored. Returns (cli, project, script path)."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    script_file = work / "script.json"
    script_file.write_text(json.dumps(script), encoding="utf-8")
    project = make_git_project(tmp_path / name)
    for rel, text in (("check.py", CHECK_PY), ("src/__init__.py", ""), ("tests/acceptance/specs/login.md", SPEC), ("README.md", "# App\n")):
        f = project / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(text.encode("utf-8"))
    home = make_home(home or tmp_path / "home", profiles(script_file))
    cli = Cli(project, home)
    cli.run("init", str(project))
    cli.run("vendor", str(SOFTWARE_FEATURE))
    configure(project, paths={"specs": "docs/specs", "designs": "docs/design"},
              project={"test_command": cmdline([sys.executable, "check.py"])})
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Toy app with Baton")
    return cli, project, script_file


def calls(script_file: Path) -> list[dict]:
    f = script_file.parent / "calls.jsonl"
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def run_events(project: Path, run: str) -> list[dict]:
    f = project / ".baton" / "runs" / run / "events.jsonl"
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]


def worker_for(step_path: str) -> str:
    """The scripted Director's routing: reviews go to the other vendor, acceptance to the person."""
    step = step_path.rsplit("/", 1)[-1]
    if step == "accept":
        return "owner"
    if step == "code_review" or step.endswith("~review"):
        return "checker"
    return "builder"


def owner_does(cli: Cli, project: Path, run: str, step_path: str, output: Any) -> dict:
    """The person does a manual step: the Director dispatches, the person writes the result, `submit` hands it in."""
    d = cli.run("dispatch", run, step_path, "--worker", "owner")
    write_result(packet_dir(project, run, step_path, d["attempt"]), output)
    return cli("submit", run, step_path, expect=None).payload


class Director:
    """A scripted Director over the CLI: dispatches every ready step, relays the owner's scripted decisions.

    ``acceptance`` is the person's output for an ``accept`` step (or a function of the project root);
    ``decisions`` maps a decision ref's last segment (``triage``, ``plan``, ``accept``, …) to
    a list of ``(decision, note)`` used in order (the last repeats); default approve.
    """

    def __init__(self, cli: Cli, project: Path, run: str, decisions: dict[str, list[tuple[str, str]]] | None = None,
                 acceptance: Any = None, route: Callable[[str], str] = worker_for):
        self.cli, self.project, self.run = cli, project, run
        self.route = route  # step path -> profile
        self.decisions = decisions or {}
        self.used: dict[str, int] = {}
        self.acceptance = acceptance or {"accepted": True, "notes": "Tried each criterion against the commit."}
        self.owner_decisions: list[tuple[str, str]] = []
        self.last_acceptance: dict | None = None
        self.dispatches: list[tuple[str, str]] = []

    def decide(self, p: dict) -> None:
        key = p["ref"].rsplit("/", 1)[-1]
        options = self.decisions.get(key) or [("approve", "Looks right.")]
        last = self.last_acceptance
        if key == "accept" and key not in self.decisions and last is not None and not last.get("accepted"):
            options = [("reject", last.get("notes") or "Not accepted.")]  # the person's own check failed
        i = self.used.get(key, 0)
        self.used[key] = i + 1
        decision, note = options[min(i, len(options) - 1)]
        assert decision in p["options"], (p, decision)
        self.owner_decisions.append((p["ref"], decision))
        self.cli("decide", self.run, p["ref"], decision, "--note", note, expect=None)

    def drive(self, limit: int = 60) -> dict:
        for _ in range(limit):
            st = self.cli("status", self.run, expect=None).payload
            if st["state"] in ("completed", "abandoned"):
                return st
            if st["pending_decisions"]:
                self.decide(st["pending_decisions"][0])
                continue
            assert st["ready"], st
            step = st["ready"][0]
            worker = self.route(step)
            self.dispatches.append((step, worker))
            if worker == "owner":
                self.last_acceptance = self.acceptance(self.project) if callable(self.acceptance) else self.acceptance
                owner_does(self.cli, self.project, self.run, step, self.last_acceptance)
            else:
                self.cli("dispatch", self.run, step, "--worker", worker, "--wait", expect=None)
        raise AssertionError(f"run {self.run} did not finish in {limit} moves")
