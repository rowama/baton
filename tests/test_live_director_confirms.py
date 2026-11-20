"""Live test (opt-in, ``BATON_LIVE=1``): a real Director given an instruction, not a confirmation.

Change 2026-11-first-use-feedback-batch-a, Slice 1 (F-1, F-5). The owner's first message is an
instruction to the Director, as on the owner's first real run: "Become the baton director. Vendor
the recipe-builder, then run it." Claude Code (``claude -p``, resumed for each owner turn) directs
through the baton CLI only; recipe-builder is not vendored (``init`` vendors only fit-check).

Checked mechanically from the record:
- recipe-builder was vendored with a note that is not the opening instruction (F-1, F-5);
- it was not vendored in the Director's first turn, before the owner could confirm (F-1);
- the run's ``idea`` is the owner's description of the process, not the instruction (F-1).
The transcript is saved to ``$BATON_LIVE_OUT`` for the owner to judge against §13.8.

Uses the owner's Claude subscription; costs about four Director turns.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from projectkit import Cli, git, make_git_project, make_home
from test_live_conversation import FAKES, _messages, _system, _wrapper

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("BATON_LIVE") != "1", reason="live harness test: set BATON_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed"),
]

INSTRUCTION = "Become the baton director. Vendor the recipe-builder, then run it."
DESCRIPTION = "I want a repeatable process for planning our team's quarterly offsite: picking a venue, setting a budget and writing the agenda."
OWNER_REPLIES = [
    INSTRUCTION,
    DESCRIPTION,
    "Yes, that's right. Go ahead.",
    "Thanks, that's all for today. I'll answer its questions tomorrow.",
]
CAPS = ["structured_output", "long_form_writing", "technical_reasoning", "workspace_read"]
# The first step asks a question, so the run waits on the owner and the scripted conversation can end.
QUESTIONS = [{"id": "size", "ask": "How many people usually come to the offsite?", "why": "Sets the venue and budget"}]


def _setup(base: Path) -> tuple[Path, Path]:
    work = base / "work"
    work.mkdir(parents=True)
    (work / "outputs.json").write_text(json.dumps({"profile": {"blocked": QUESTIONS, "output": {}}}), encoding="utf-8")
    line = shlex.join([sys.executable, str(FAKES / "conversation_worker.py"), "{packet}", "{result}", str(work / "outputs.json")])
    profiles = f"alpha:\n  adapter: command\n  vendor: acme\n  command: {json.dumps(line)}\n  capabilities: {json.dumps(CAPS)}\n  tier: strong\n"
    project = make_git_project(base / "proj")
    home = make_home(base / "home", profiles)
    Cli(project, home).run("init", str(project))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return project, home


def test_director_confirms_back_before_vendoring_and_starting(tmp_path):
    project, home = _setup(tmp_path)
    (tmp_path / "scratch").mkdir()
    wrapper = _wrapper(tmp_path, project, home, "claude-director@live")
    out = Path(os.environ.get("BATON_LIVE_OUT") or tmp_path / "transcripts")
    out.mkdir(parents=True, exist_ok=True)
    project_log = project / ".baton" / "project" / "events.jsonl"
    session, transcript, vendored_at = None, [], None
    for n, reply in enumerate(OWNER_REPLIES):
        cmd = ["claude", "-p", reply, "--output-format", "stream-json", "--verbose", "--tools", "Bash",
               "--allowedTools", f"Bash({wrapper}:*)", "--append-system-prompt", _system(wrapper, tmp_path)]
        if session:
            cmd += ["--resume", session]
        proc = subprocess.run(cmd, cwd=tmp_path / "scratch", capture_output=True, text=True, timeout=1800)
        (out / f"confirm-turn-{n + 1}.jsonl").write_text(proc.stdout, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr[-2000:]
        session, text, commands = _messages(proc.stdout)
        transcript.append({"owner": reply, "director": text, "commands": commands})
        if vendored_at is None and project_log.is_file() and "recipe-builder" in project_log.read_text(encoding="utf-8"):
            vendored_at = n
    (out / "confirm-conversation.md").write_text(
        "\n\n".join(f"**Owner:** {t['owner']}\n\n**Director:** {t['director']}" for t in transcript) + "\n", encoding="utf-8")

    events = [json.loads(x) for x in project_log.read_text(encoding="utf-8").splitlines()]
    vend = [e for e in events if e["type"] == "human_decision" and e["data"].get("kind") == "vendor"
            and e["data"].get("recipe", "").startswith("recipe-builder@")]
    assert vend, "recipe-builder was not vendored"
    assert vendored_at is not None and vendored_at >= 1, "vendored in the first turn, before the owner could confirm"
    note = vend[0]["data"]["note"]
    assert INSTRUCTION not in note and "Vendor the recipe-builder" not in note, note

    started = []
    for d in (project / ".baton" / "runs").iterdir():
        first = json.loads((d / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        if first["data"].get("recipe", "").startswith("recipe-builder@"):
            sha = first["data"]["inputs_sha256"]  # the run's inputs are in its CAS (§8.9)
            started.append(json.loads((d / "cas" / sha[:2] / sha).read_text(encoding="utf-8")))
    assert started, "recipe-builder was not started"
    idea = started[0]["idea"]
    assert "director" not in idea.lower() and "vendor" not in idea.lower(), idea
    assert "offsite" in idea.lower(), idea
