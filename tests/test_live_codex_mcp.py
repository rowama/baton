"""Live test (opt-in, ``BATON_LIVE=1``): Codex as Director in its own sandbox
(change 2026-11-codex-director-sandbox, slice 3; decisions 0053, 0054).

Codex runs ``codex exec --sandbox workspace-write`` with ``/tmp`` and ``$TMPDIR``
closed to its commands, so its shell can write only the project, and the
network is off. The Baton home lives under ``/tmp``, outside the project.

* **Over MCP** (criterion 5): Baton is connected as an MCP server through
  ``-c mcp_servers.baton.*`` overrides, so the owner's ``~/.codex/config.toml``
  is never edited. ``default_tools_approval_mode = "approve"`` is needed
  because ``codex exec`` runs with approval policy ``never`` and otherwise
  refuses every MCP tool call ("MCP tool call requires approval"). Codex
  completes ``fit-check``. ``describe`` is a real dispatch to the owner's
  Claude Code subscription worker (its own login and network, under a
  supervisor the MCP server started); ``assess`` is scripted.
* **From its shell** (the negative control): ``baton detect --json`` gets
  ``director_sandboxed``, and the test records which signal fired.

Transcripts go to ``$BATON_LIVE_OUT`` (default: the test's tmp dir) for the
owner's review. Uses the owner's Codex and Claude Code subscriptions.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FIT_CHECK, ROOT
from harnesskit import harness_profile
from projectkit import FIT_INPUTS, OWNER_PROFILE, VERDICT, Cli, git, make_git_project, make_home

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("BATON_LIVE") != "1", reason="live harness test: set BATON_LIVE=1"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed"),
    pytest.mark.skipif(sys.platform != "linux", reason="the change doc's live check is on Linux"),
]

FAKES = Path(__file__).parent / "fakes"
OWNER_WORDS = "Agreed: it fits."
DIRECTOR = "codex-director@live"
#: The sandbox under test: workspace-write, nothing writable outside the project, no network.
SANDBOX = ["--sandbox", "workspace-write", "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
           "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true", "-c", "sandbox_workspace_write.network_access=false"]


def _out_dir(tmp_path: Path) -> Path:
    out = Path(os.environ.get("BATON_LIVE_OUT") or tmp_path / "transcripts")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _env(project: Path, home: Path) -> dict[str, str]:
    return {"BATON_HOME": str(home), "BATON_PROJECT": str(project), "BATON_DIRECTOR": DIRECTOR, "BATON_HARNESS": "codex",
            "PYTHONPATH": str(ROOT / "src"), "HOME": os.environ["HOME"], "PATH": os.environ["PATH"]}


def _setup(base: Path) -> tuple[Path, Path]:
    work = base / "work"
    work.mkdir(parents=True)
    (work / "outputs.json").write_text(json.dumps({"assess": VERDICT}), encoding="utf-8")
    line = shlex.join([sys.executable, str(FAKES / "step_worker.py"), "{packet}", "{result}", str(work / "outputs.json")])
    scripted = ("beta:\n  adapter: command\n  vendor: globex\n  command: " + json.dumps(line)
                + '\n  capabilities: ["structured_output", "technical_reasoning"]\n  tier: strong\n')
    claude = shutil.which("claude")
    real = harness_profile("claude-sub", "claude_code", "anthropic", executable="claude",
                           capabilities=["structured_output", "long_form_writing", "technical_reasoning"],
                           path={"search": [str(Path(claude).parent)]}, env_deny=["ANTHROPIC_API_KEY"])
    project = make_git_project(base / "proj")
    home = make_home(base / "home", OWNER_PROFILE + real + scripted)
    cli = Cli(project, home)
    cli.run("init", str(project))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return project, home


def _events(stdout: str) -> list[dict]:
    out = []
    for line in stdout.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _items(events: list[dict], kind: str) -> list[dict]:
    return [e["item"] for e in events if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == kind]


def _codex(project: Path, prompt: str, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["codex", "exec", "--json", *SANDBOX, "--ignore-user-config", "--skip-git-repo-check", "--color", "never", "--ephemeral",
         "-C", str(project), *extra, prompt],
        cwd=project, capture_output=True, text=True, timeout=1800, env=env)


def test_codex_shell_in_its_sandbox_gets_director_sandboxed(tmp_path):
    project, home = _setup(tmp_path)
    out = _out_dir(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "baton"
    exports = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in _env(project, home).items() if k not in ("HOME", "PATH"))
    wrapper.write_text(f"#!/bin/sh\n{exports}exec {shlex.quote(sys.executable)} -m baton \"$@\"\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    proc = _codex(project, f"Run exactly this shell command once, and nothing else: {wrapper} detect --json   "
                           "Then reply with its output unchanged.",
                  env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})
    (out / "codex-shell-detect.jsonl").write_text(proc.stdout, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[-2000:]
    (cmd,) = [c for c in _items(_events(proc.stdout), "command_execution") if "detect" in c.get("command", "")]
    result = json.loads(cmd["aggregated_output"])
    (out / "codex-shell-detect.result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    b = result["blocking"]
    assert b["code"] == "director_sandboxed" and result["problems"] == [f"director_sandboxed: {b['title']} (fix: {b['fix']})"]
    # Which signal fired, for the record (2026-11-04, codex-cli 0.166.0 on Linux: both).
    print(f"director_sandboxed cause: {b['cause']}; harness hint: {b['harness']}")
    assert b["cause"]["home"] or b["cause"]["network"] == "denied"


def test_codex_directs_over_mcp_in_its_sandbox(tmp_path):
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not installed (the real worker)")
    project, home = _setup(tmp_path)
    out = _out_dir(tmp_path)
    env = _env(project, home)
    toml_env = "{" + ",".join(f"{k}={json.dumps(v)}" for k, v in env.items()) + "}"
    mcp = ["-c", f"mcp_servers.baton.command={json.dumps(sys.executable)}", "-c", 'mcp_servers.baton.args=["-m","baton","mcp"]',
           "-c", f"mcp_servers.baton.env={toml_env}", "-c", 'mcp_servers.baton.default_tools_approval_mode="approve"',
           "-c", "mcp_servers.baton.tool_timeout_sec=900"]
    skill = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    prompt = (
        "Follow this skill:\n\n" + skill + "\n\n---\n\n"
        f"You are the Director of the Baton project at {project}. Your only interface is the baton MCP tools; run no shell commands.\n\n"
        f"The owner wants to know whether this idea suits Baton. Start a run of the vendored recipe fit-check with run inputs "
        f"{json.dumps(FIT_INPUTS)} and take it to completion. The owner's routing for this session: step describe to worker "
        f"claude-sub, step assess to worker beta. Use wait so each dispatch finishes before you go on.\n"
        "If a step stops with questions for the owner, the owner's answer to each is its best guess, and their words are exactly: "
        "\"Go with your best guesses.\"\n"
        f"When the verdict gate waits on the owner: the owner has already decided to approve it, and their words are exactly: "
        f"\"{OWNER_WORDS}\"\n"
        "Finish with a brief report to the owner."
    )
    proc = _codex(project, prompt, *mcp)
    (out / "codex-mcp-director.jsonl").write_text(proc.stdout, encoding="utf-8")
    (out / "codex-mcp-director.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[-2000:]
    events = _events(proc.stdout)
    calls = _items(events, "mcp_tool_call")
    (out / "codex-mcp-director.tools.txt").write_text("\n".join(f"{c['tool']} {c.get('status')}" for c in calls) + "\n", encoding="utf-8")
    assert calls and all(c["server"] == "baton" for c in calls), calls
    assert not [c for c in calls if c.get("error")], [c["error"] for c in calls if c.get("error")]
    assert not _items(events, "command_execution"), "the Director ran shell commands"

    runs = list((project / ".baton" / "runs").iterdir())
    assert len(runs) == 1, runs
    evs = [json.loads(x) for x in (runs[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["type"] == "run_completed" for e in evs), "the run did not complete"
    submitted = [(e["step_path"], e["actor"]) for e in evs if e["type"] == "result_submitted"]
    assert ("describe", "worker:claude-sub") in submitted and submitted[-1] == ("assess", "worker:beta"), submitted
    gate = [e for e in evs if e["type"] == "human_decision" and e["data"].get("kind") != "answers"]
    assert [e["data"]["note"] for e in gate] == [OWNER_WORDS]
    # The supervisor the MCP server started wrote the worker's log under the Baton home, outside Codex's sandbox.
    logs = home / "logs" / runs[0].name
    assert logs.is_dir() and any(logs.rglob("*.log")), f"no worker logs under {logs}"
