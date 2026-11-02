"""Helpers for project-level tests: a git project with Baton initialized, a manual profile, the CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from baton.cli import app

from conftest import FIT_CHECK

OWNER_PROFILE = """\
owner:
  adapter: manual
  vendor: human
  person: owner
  capabilities: [human_judgment, structured_output, long_form_writing, technical_reasoning, file_write]
  tier: strong
"""

FIT_INPUTS = {"title": "Contract review", "idea": "Review each vendor contract before signing."}
BAD_PROFILE = {"summary": "missing the occurrence block"}
GOOD_PROFILE = {
    "summary": "Vendor contract review",
    "occurrence": {
        "frequency": "a few per month",
        "judgment": "high",
        "duration": "two days",
        "participants": ["legal agent", "owner"],
        "human_signoffs": True,
        "audit_trail": "benefit",
        "latency_sensitive": False,
        "live_integration": False,
    },
}
VERDICT = {
    "verdict": "fits",
    "reasons": [{"row": "occurrences", "leans": "baton", "reason": "a few per month"}],
    "next_step": "Author a contract-review recipe.",
}


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def make_git_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "owner@example.com")
    git(root, "config", "user.name", "Owner")
    return root


def make_home(home: Path, profiles: str = OWNER_PROFILE) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    (home / "workers.yaml").write_text(profiles, encoding="utf-8")
    return home


class Cli:
    """Invoke ``baton`` against one project as one Director."""

    def __init__(self, project: Path, home: Path, director: str = "alice@host1"):
        self.project = project
        self.home = home
        self.director = director

    def __call__(self, *args: str, expect: int | None = 0) -> Any:
        runner = CliRunner(env={"BATON_HOME": str(self.home), "BATON_DIRECTOR": self.director, "BATON_PROJECT": str(self.project)})
        res = runner.invoke(app, [*args, "--json"])
        if expect is not None:
            assert res.exit_code == expect, f"baton {' '.join(args)} exited {res.exit_code} (wanted {expect}):\n{res.stdout}\n{res.stderr}"
        res.payload = json.loads(res.stdout) if res.stdout.strip() else None  # type: ignore[attr-defined]
        return res

    def run(self, *args: str, expect: int | None = 0) -> dict:
        return self(*args, expect=expect).payload


def setup_fit_check(tmp_path: Path, name: str = "proj") -> tuple[Cli, Path]:
    """A committed git project with fit-check vendored, plus a machine home with the owner profile."""
    project = make_git_project(tmp_path / name)
    home = make_home(tmp_path / "home")
    cli = Cli(project, home)
    cli.run("init", str(project))
    cli.run("vendor", str(FIT_CHECK))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return cli, project


def write_result(packet_dir: Path, output: Any, *, status: str = "completed", **extra: Any) -> None:
    """Play the manual worker: write result.json into the attempt's result/ directory."""
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    result = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": status, "output": output, **extra}
    rdir = packet_dir.parent / "result"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "result.json").write_text(json.dumps(result), encoding="utf-8")


def packet_dir(project: Path, run_id: str, step: str, attempt: int) -> Path:
    return project / ".baton" / "runs" / run_id / "steps" / step / f"attempt-{attempt}" / "packet"
