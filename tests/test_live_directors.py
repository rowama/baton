"""Phase 14 live test (opt-in, ``BATON_LIVE=1``): real harnesses as Directors.

Claude Code (``claude -p``) directs through MCP only (every built-in tool off);
Codex (``codex exec``) directs through the CLI only. Each completes ``fit-check``
with different worker assignments (scripted ``command`` workers), records the
owner's decision as given, and is asked one subject question, which must go to
the project expert (a scripted SME), not be answered from its own inference.

Transcripts are saved to ``$BATON_LIVE_OUT`` (default: the test's tmp dir) for
the owner's review; the test checks what can be checked mechanically: the tools
or commands each Director used, and the record (every result from a worker,
the owner's words verbatim, an expert consulted).

Uses the owner's CLI subscriptions; costs a few Director turns per harness.
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
from projectkit import FIT_INPUTS, GOOD_PROFILE, OWNER_PROFILE, VERDICT, Cli, git, make_git_project, make_home

pytestmark = pytest.mark.skipif(os.environ.get("BATON_LIVE") != "1", reason="live harness test: set BATON_LIVE=1")

FAKES = Path(__file__).parent / "fakes"
CAPS = ["structured_output", "long_form_writing", "technical_reasoning"]
OWNER_WORDS = "Agreed: it fits."
QUESTION = "Is two days a typical time to review a vendor contract?"
EXPERT_ANSWER = "Two days is typical for a mid-size vendor contract; large ones take a week."


def _setup(base: Path) -> tuple[Path, Path]:
    work = base / "work"
    work.mkdir(parents=True)
    (work / "outputs.json").write_text(json.dumps({"describe": GOOD_PROFILE, "assess": VERDICT}), encoding="utf-8")
    (work / "sme.json").write_text(json.dumps({"answer": EXPERT_ANSWER}), encoding="utf-8")

    def profile(name: str, vendor: str, script: str, data: str) -> str:
        line = shlex.join([sys.executable, str(FAKES / script), "{packet}", "{result}", str(work / data)])
        return f"{name}:\n  adapter: command\n  vendor: {vendor}\n  command: {json.dumps(line)}\n  capabilities: {json.dumps(CAPS)}\n  tier: strong\n"

    profiles = OWNER_PROFILE + profile("alpha", "acme", "step_worker.py", "outputs.json") + profile("beta", "globex", "step_worker.py", "outputs.json") \
        + profile("sage", "initech", "fake_sme.py", "sme.json")
    project = make_git_project(base / "proj")
    home = make_home(base / "home", profiles)
    cli = Cli(project, home)
    cli.run("init", str(project))
    cli.run("vendor", str(FIT_CHECK))
    py = project / ".baton" / "project.yaml"
    py.write_text(py.read_text(encoding="utf-8") + "sme:\n  project: { preferred_profiles: [sage] }\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return project, home


def _env(project: Path, home: Path, director: str, harness: str) -> dict[str, str]:
    return {"BATON_HOME": str(home), "BATON_PROJECT": str(project), "BATON_DIRECTOR": director, "BATON_HARNESS": harness,
            "PYTHONPATH": str(ROOT / "src")}


def _task(project: Path, describe: str, assess: str, how: str) -> str:
    return (
        f"You are the Director of the Baton project at {project}. {how}\n\n"
        f"The owner wants to know whether this idea suits Baton. Start a run of the vendored recipe fit-check with run inputs "
        f"{json.dumps(FIT_INPUTS)} and take it to completion. The owner's routing for this session: step describe to worker "
        f"{describe}, step assess to worker {assess}. Use wait so each dispatch finishes before you go on.\n"
        f"When the verdict gate waits on the owner: the owner has already decided to approve it, and their words are exactly: "
        f"\"{OWNER_WORDS}\"\n"
        f"The owner also asks, about this run's idea: \"{QUESTION}\" Handle that question as the director skill says, waiting "
        f"for the answer, and include it in your final message.\n"
        f"Finish with a brief report to the owner."
    )


def _skill() -> str:
    return (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")


def _out_dir(tmp_path: Path) -> Path:
    out = Path(os.environ.get("BATON_LIVE_OUT") or tmp_path / "transcripts")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _run_events(project: Path) -> dict[str, list[dict]]:
    runs = {}
    for d in (project / ".baton" / "runs").iterdir():
        runs[d.name] = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    return runs


def _check_record(project: Path, director: str, workers: list[str]) -> str:
    runs = {rid: evs for rid, evs in _run_events(project).items()
            if any(e["type"] == "lease_claimed" and e["data"]["director_id"] == director for e in evs)}
    assert len(runs) == 1, f"{director} started {len(runs)} runs"
    rid, evs = next(iter(runs.items()))
    assert any(e["type"] == "run_completed" for e in evs), f"{rid} did not complete"
    submitted = [(e["step_path"], e["actor"]) for e in evs if e["type"] == "result_submitted"]
    assert submitted == [("describe", f"worker:{workers[0]}"), ("assess", f"worker:{workers[1]}")], submitted
    decision = [e for e in evs if e["type"] == "human_decision"]
    assert len(decision) == 1 and decision[0]["data"]["note"] == OWNER_WORDS and decision[0]["actor"] == "human"
    pevs = project / ".baton" / "project" / "events.jsonl"
    sme = [e for e in evs if e["type"] == "sme_requested"] + (
        [json.loads(x) for x in pevs.read_text(encoding="utf-8").splitlines() if '"sme_requested"' in x] if pevs.exists() else [])
    assert any(e["data"]["subject"] == "project" and e["actor"].startswith(f"director:{director}") for e in sme), "no project expert consulted"
    return rid


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_code_directs_over_mcp(tmp_path):
    project, home = _setup(tmp_path)
    out = _out_dir(tmp_path)
    director = "claude-director@live"
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"baton": {"command": sys.executable, "args": ["-m", "baton", "mcp"],
                                                        "env": _env(project, home, director, "claude_code")}}}), encoding="utf-8")
    prompt = _task(project, "alpha", "beta", "Your only interface is the baton MCP tools.")
    proc = subprocess.run(
        ["claude", "-p", prompt, "--mcp-config", str(cfg), "--strict-mcp-config", "--tools", "", "--allowedTools", "mcp__baton",
         "--append-system-prompt", _skill(), "--output-format", "stream-json", "--verbose", "--no-session-persistence"],
        cwd=project, capture_output=True, text=True, timeout=1800)
    (out / "claude-director.jsonl").write_text(proc.stdout, encoding="utf-8")
    (out / "claude-director.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[-2000:]
    tools = []
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "assistant":
            tools += [c["name"] for c in msg["message"].get("content", []) if c.get("type") == "tool_use"]
    assert tools and all(t.startswith("mcp__baton__") for t in tools), tools
    assert "mcp__baton__ask_sme" in tools
    _check_record(project, director, ["alpha", "beta"])


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
def test_codex_directs_over_cli(tmp_path):
    project, home = _setup(tmp_path)
    out = _out_dir(tmp_path)
    director = "codex-director@live"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "baton"
    exports = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in _env(project, home, director, "codex").items())
    wrapper.write_text(f"#!/bin/sh\n{exports}exec {shlex.quote(sys.executable)} -m baton \"$@\"\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    how = f"Your only interface is the baton CLI, run as `{wrapper}` (always with --json); never touch .baton/ or any packet or result file yourself."
    prompt = "Follow this skill:\n\n" + _skill() + "\n\n---\n\n" + _task(project, "beta", "alpha", how)
    proc = subprocess.run(
        ["codex", "exec", "--json", "--sandbox", "workspace-write", "--add-dir", str(home), "--add-dir", str(tmp_path / "work"),
         "--skip-git-repo-check", "--color", "never", "--ephemeral", "-C", str(project), prompt],
        cwd=project, capture_output=True, text=True, timeout=1800, env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})
    (out / "codex-director.jsonl").write_text(proc.stdout, encoding="utf-8")
    (out / "codex-director.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[-2000:]
    commands = []
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = ev.get("item") or {}
        if ev.get("type") == "item.completed" and item.get("type") == "command_execution":
            commands.append(item.get("command", ""))
    (out / "codex-director.commands.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    assert commands and all("baton" in c for c in commands), commands
    assert not [c for c in commands if "result.json" in c or "> " in c.replace("2>", "")], "a command wrote a file"
    assert any("ask-sme" in c for c in commands)
    _check_record(project, director, ["beta", "alpha"])
