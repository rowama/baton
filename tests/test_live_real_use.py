"""Phase 16 live test (opt-in, ``BATON_LIVE=1``): ``software-feature`` at ``minor`` with real harness workers.

A toy Python repository gets a small change: Codex (``codex exec``, its stored
login) triages and reviews; Claude Code (``claude -p``, its stored login)
implements and commits; the person accepts after running the tests
themselves. The recipe is the shipped one, unchanged; the Director is the
scripted one of the suite. The run's record (summary and step records) is
copied to ``$BATON_LIVE_OUT`` (default: the test's tmp dir) for the owner's review.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SOFTWARE_FEATURE
from harnesskit import harness_profile
from projectkit import OWNER_PROFILE, Cli, git, make_git_project, make_home
from realkit import Director, cmdline, configure, run_events

pytestmark = [pytest.mark.slow, pytest.mark.skipif(os.environ.get("BATON_LIVE") != "1", reason="live harness test: set BATON_LIVE=1")]

CAPS = ["structured_output", "long_form_writing", "technical_reasoning", "tool_use", "file_write", "shell", "code_exec",
        "repo_workspace", "workspace_read"]
REQUEST = {
    "title": "Slugify helper",
    "kind": "increment",
    "feature_request": (
        "Add a function slugify(text: str) -> str to src/textutil.py. It lowercases the text, replaces every run of "
        "characters that are not ASCII letters or digits with a single hyphen, and strips hyphens from both ends "
        "(slugify('  Hello, World! ') == 'hello-world'; slugify('') == ''). Add unit tests in tests/test_textutil.py."
    ),
}
STARTER_TEST = """\
import unittest


class Smoke(unittest.TestCase):
    def test_package_imports(self):
        import src  # noqa: F401


if __name__ == "__main__":
    unittest.main()
"""


def test_live_software_feature_minor(tmp_path):
    if not (shutil.which("claude") and shutil.which("codex")):
        pytest.skip("claude and codex CLIs not installed")
    project = make_git_project(tmp_path / "toy")
    for rel, text in (("src/__init__.py", ""), ("src/textutil.py", '"""Text helpers."""\n'), ("tests/__init__.py", ""),
                      ("tests/test_smoke.py", STARTER_TEST), ("tests/acceptance/specs/README.md", "Locked specs.\n"),
                      ("README.md", "# Toy\n\nRun the tests with `python -m unittest discover -s tests -t .`\n")):
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_bytes(text.encode("utf-8"))
    claude_dir = str(Path(shutil.which("claude")).parent)
    profiles = (
        OWNER_PROFILE
        + harness_profile("claude-sub", "claude_code", "anthropic", executable="claude", capabilities=CAPS,
                          path={"search": [claude_dir]}, env_deny=["ANTHROPIC_API_KEY"])
        + harness_profile("codex-sub", "codex", "openai", executable="codex", capabilities=CAPS,
                          path={"search": ["nvm"]}, env_deny=["OPENAI_API_KEY", "CODEX_API_KEY"])
    )
    cli = Cli(project, make_home(tmp_path / "home", profiles))
    cli.run("init", str(project))
    cli.run("vendor", str(SOFTWARE_FEATURE))
    test_command = cmdline([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."])
    configure(project, paths={"specs": "docs/specs", "designs": "docs/design"}, project={"test_command": test_command})
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Toy repo with Baton")

    checks: list[dict] = []

    def accept(root: Path) -> dict:
        """The person runs the tests themselves and tries the example from the request."""
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=root, capture_output=True, text=True)
        probe = subprocess.run([sys.executable, "-c", "from src.textutil import slugify; print(slugify('  Hello, World! '))"],
                               cwd=root, capture_output=True, text=True)
        ok = tests.returncode == 0 and probe.stdout.strip() == "hello-world"
        checks.append({"accepted": ok, "notes": f"tests exit {tests.returncode}; slugify example gave {probe.stdout.strip()!r}"})
        return checks[-1]

    def route(step_path: str) -> str:
        """Implementation by claude; triage and review by codex (a different vendor, as independence requires)."""
        step = step_path.rsplit("/", 1)[-1]
        return {"implement": "claude-sub", "accept": "owner"}.get(step, "codex-sub")

    run = cli.run("start", "software-feature", "--inputs", json.dumps(REQUEST))["run_id"]
    d = Director(cli, project, run, acceptance=accept, route=route)
    try:
        st = d.drive(limit=40)
    finally:
        out = Path(os.environ.get("BATON_LIVE_OUT") or tmp_path / "record")
        if (project / ".baton" / "runs" / run / "docs").is_dir():
            shutil.copytree(project / ".baton" / "runs" / run / "docs", out / run, dirs_exist_ok=True)
        print(f"record: {out / run}")
        print(json.dumps(d.dispatches, indent=1))
    assert st["state"] == "completed" and st["level"] == "minor", st
    evs = run_events(project, run)
    by = {(e["step_path"].rsplit("/", 1)[-1], e["data"]["profile"]) for e in evs if e["type"] == "dispatched"}
    assert ("implement", "claude-sub") in by and ("code_review", "codex-sub") in by
    assert all(e["actor"].startswith("worker:") for e in evs if e["type"] == "result_submitted")
    assert checks and checks[-1]["accepted"], checks  # the person's own check of the final iteration passed
    assert cli("check").exit_code == 0
    assert (project / "src" / "textutil.py").read_text(encoding="utf-8").count("def slugify") == 1
