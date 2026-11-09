"""Phase 17 live test (opt-in, ``BATON_LIVE=1``): a real Director talks with a scripted owner.

Claude Code (``claude -p``, resumed for each owner turn) directs through the baton CLI only.
The owner is a fixed list of replies, one per turn, starting from a goal (the water-vending
scenario of §16 Phase 17). Workers are scripted ``command`` fakes: framing proposes two
parts; ``fit-check``'s ``describe`` asks structured questions until it gets confirmed answers.

Checked mechanically: the record (a framing selection in the owner's words; confirmed answers
with ``owner_words``; every result from a worker). Judged by the owner, not here: the transcript
(saved to ``$BATON_LIVE_OUT``) against §13.8 *Review*: Baton vocabulary reaching the owner,
questions forwarded unconverted, decisions recorded without a confirm-back, subject questions
answered by the Director. A helper prints each Director message with the owner's reply.

Uses the owner's Claude subscription; costs about a dozen Director turns.
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

from conftest import ROOT
from projectkit import GOOD_PROFILE, VERDICT, Cli, git, make_git_project, make_home

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("BATON_LIVE") != "1", reason="live harness test: set BATON_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed"),
]

FAKES = Path(__file__).parent / "fakes"
CAPS = ["structured_output", "long_form_writing", "technical_reasoning"]
GOAL = "I want to start a pure-water vending business. A few self-serve machines around town to start."
OWNER_REPLIES = [
    GOAL,
    "Yes, that's it. Let's start with setting up the business and figuring out the day-to-day running. Not the signs yet.",
    "Yes, those two.",
    "One machine per site to start. And I'll handle the permits myself.",
    "Yes, that's right.",
    "That makes sense to me. Yes, I agree with that verdict.",
    "Yes.",
    "Thanks, that's all for today.",
]
FRAME = {
    "goal": "Start a business selling purified water from a few self-serve machines around town.",
    "parts": [
        {"id": "setup", "label": "Setting up the business", "description": "Registering the business, banking, insurance and permits.",
         "kind": "project", "proposal": {"fit_check": {"idea": "Set up a small water-vending business: registration, insurance, permits.",
                                                       "title": "Business setup"}}, "reasons": ["No listed process covers business setup"]},
        {"id": "running", "label": "Running the machines day to day", "description": "Refilling, cleaning and collecting payments.",
         "kind": "operations", "proposal": {"fit_check": {"idea": "Run water machines day to day: refills, cleaning, payments.",
                                                          "title": "Daily operations"}}, "reasons": ["Day-to-day work is an operations question"]},
        {"id": "signage", "label": "Signs for the sites", "description": "Signs that tell passers-by what the machine is.",
         "kind": "project", "proposal": {"recipe": "backyard-project", "inputs": {"title": "Signs", "description": "Signs at each site."}},
         "reasons": ["Physical build work"]},
    ],
    "assumptions": [{"about": "scale", "value": "a handful of machines", "basis": "the owner said a few around town"}],
}
QUESTIONS = [
    {"id": "site", "ask": "Will each site have one machine, or several?", "why": "Sets how much equipment to plan for",
     "best_guess": "One machine per site at first", "options": [{"id": "one", "label": "One machine"}, {"id": "several", "label": "Several"}]},
    {"id": "permits", "ask": "Will you handle the permits yourself, or hire someone?", "why": "Decides who is involved in opening each site"},
]


def _setup(base: Path) -> tuple[Path, Path, Path]:
    work = base / "work"
    work.mkdir(parents=True)
    profile = {**GOOD_PROFILE, "assumptions": [{"field": "occurrence.frequency", "value": "a few site openings a year",
                                                 "basis": "a few machines around town"}]}
    (work / "outputs.json").write_text(json.dumps({"frame": FRAME, "describe": {"blocked": QUESTIONS, "output": profile}, "assess": VERDICT}),
                                       encoding="utf-8")
    line = shlex.join([sys.executable, str(FAKES / "conversation_worker.py"), "{packet}", "{result}", str(work / "outputs.json")])
    profiles = f"alpha:\n  adapter: command\n  vendor: acme\n  command: {json.dumps(line)}\n  capabilities: {json.dumps(CAPS)}\n  tier: strong\n"
    project = make_git_project(base / "proj")
    home = make_home(base / "home", profiles)
    Cli(project, home).run("init", str(project))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return project, home, work


def _wrapper(base: Path, project: Path, home: Path, director: str) -> Path:
    env = {"BATON_HOME": str(home), "BATON_PROJECT": str(project), "BATON_DIRECTOR": director, "BATON_HARNESS": "claude_code",
           "PYTHONPATH": str(ROOT / "src")}
    bin_dir = base / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "baton"
    exports = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in env.items())
    wrapper.write_text(f"#!/bin/sh\n{exports}exec {shlex.quote(sys.executable)} -m baton \"$@\"\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper


def _system(wrapper: Path, base: Path) -> str:
    skill = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    return (skill + f"\n\n---\n\nYou are the Director for the owner's Baton project. Your only interface to Baton is `{wrapper}` "
            f"(always with --json); never touch .baton/ or any packet or result file. Write any answers file under {base / 'scratch'}. "
            "Each of your turns ends with your message to the owner; their reply is the next prompt. Use `wait` after each dispatch. "
            "Work the routing out from `eligible` yourself; the owner has no preference.")


def _messages(stdout: str) -> tuple[str | None, str, list[str]]:
    session, text, commands = None, "", []
    for line in stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        session = msg.get("session_id") or session
        if msg.get("type") == "assistant":
            for c in msg["message"].get("content", []):
                if c.get("type") == "tool_use":
                    commands.append(json.dumps(c.get("input")))
        if msg.get("type") == "result":
            text = msg.get("result") or text
    return session, text, commands


def test_director_holds_the_conversation(tmp_path):
    project, home, work = _setup(tmp_path)
    (tmp_path / "scratch").mkdir()
    wrapper = _wrapper(tmp_path, project, home, "claude-director@live")
    out = Path(os.environ.get("BATON_LIVE_OUT") or tmp_path / "transcripts")
    out.mkdir(parents=True, exist_ok=True)
    session = None
    transcript: list[dict] = []
    for n, reply in enumerate(OWNER_REPLIES):
        cmd = ["claude", "-p", reply, "--output-format", "stream-json", "--verbose", "--tools", "Bash",
               "--allowedTools", f"Bash({wrapper}:*)", "--append-system-prompt", _system(wrapper, tmp_path)]
        if session:
            cmd += ["--resume", session]
        proc = subprocess.run(cmd, cwd=tmp_path / "scratch", capture_output=True, text=True, timeout=1800)
        (out / f"turn-{n + 1}.jsonl").write_text(proc.stdout, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr[-2000:]
        session, text, commands = _messages(proc.stdout)
        transcript.append({"owner": reply, "director": text, "commands": commands})
    (out / "conversation.md").write_text("\n\n".join(f"**Owner:** {t['owner']}\n\n**Director:** {t['director']}" for t in transcript) + "\n",
                                         encoding="utf-8")

    runs = {d.name: [json.loads(x) for x in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            for d in (project / ".baton" / "runs").iterdir()}
    framing = [evs for evs in runs.values() if evs[0]["data"].get("kind") == "framing"]
    assert framing, "no framing run"
    sel = [e for e in framing[0] if e["type"] == "framing_selected"]
    assert sel and sel[0]["data"]["runs"], "the owner's selection was not applied"
    dec = next(e for e in framing[0] if e["type"] == "human_decision" and e["data"].get("kind") == "frame")
    assert dec["data"]["note"].strip(), "the selection was recorded without the owner's words"
    answers = [e for evs in runs.values() for e in evs if e["type"] == "human_decision" and e["data"].get("kind") == "answers"]
    assert answers, "no confirmed answers were recorded"
    for a in answers:
        assert all(x["owner_words"].strip() for x in a["data"]["answers"])
    for evs in runs.values():
        for e in evs:
            if e["type"] == "result_submitted":
                assert e["actor"].startswith("worker:"), e
