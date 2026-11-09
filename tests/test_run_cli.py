"""Phase 4 acceptance (§16): fit-check completes by hand through the CLI with the manual adapter,
including a forced failure and retry; a fresh clone resumes it; ``check`` passes clean."""

from __future__ import annotations

import pytest

import json
import subprocess
from pathlib import Path

from projectkit import BAD_PROFILE, FIT_INPUTS, GOOD_PROFILE, VERDICT, git, packet_dir, setup_fit_check, write_result, Cli


def _start(cli: Cli) -> str:
    out = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))
    assert out["ready"] == ["describe"]
    assert out["lease"]["yours"] and out["lease"]["director_id"] == "alice@host1"
    return out["run_id"]


def _describe_with_retry(cli: Cli, project: Path, run: str) -> None:
    d = cli.run("dispatch", run, "describe", "--worker", "owner")
    assert d["attempt"] == 1 and d["adapter"] == "manual"
    assert Path(d["packet"], "INSTRUCTIONS.md").is_file()

    # Forced failure: the result does not match the output schema.
    write_result(packet_dir(project, run, "describe", 1), BAD_PROFILE)
    out = cli.run("submit", run, "describe", expect=1)
    assert out["outcome"] == "retry"
    assert any("occurrence" in r for r in out["reasons"])

    r = cli.run("retry", run, "describe", "--guidance", "Fill in every occurrence field.")
    assert r["attempt"] == 2 and r["worker"] == "owner"
    manifest = json.loads((packet_dir(project, run, "describe", 2) / "manifest.json").read_text())
    assert manifest["prior_feedback"]["guidance"] == "Fill in every occurrence field."
    assert any("occurrence" in x for x in manifest["prior_feedback"]["reasons"])

    write_result(packet_dir(project, run, "describe", 2), GOOD_PROFILE)
    out = cli.run("submit", run, "describe")
    assert out["outcome"] == "passed" and out["ready"] == ["assess"]
    assert out["checkpoint"]["committed"], out["checkpoint"]


def _assess_and_approve(cli: Cli, project: Path, run: str) -> dict:
    cli.run("dispatch", run, "assess", "--worker", "owner")
    write_result(packet_dir(project, run, "assess", 1), VERDICT)
    out = cli.run("submit", run, "assess", expect=4)  # waiting for the owner
    assert out["outcome"] == "needs_human"
    assert out["pending_decisions"][0]["ref"] == "assess"
    assert cli.run("status", run, expect=4)["needs_owner"]
    out = cli.run("decide", run, "assess", "approve", "--note", "Agreed; author the recipe.")
    assert out["outcome"] == "passed" and out["run_completed"]
    return out


@pytest.mark.slow
def test_fit_check_end_to_end_by_hand(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    _describe_with_retry(cli, project, run)
    out = _assess_and_approve(cli, project, run)
    assert out["checkpoint"]["committed"]

    status = cli.run("status", run)
    assert status["state"] == "completed"
    assert status["lease"] is None  # released when the run completed
    assert {s["state"] for s in status["steps"].values()} == {"passed"}

    # Checkpoint commits: one per trigger call, only the run's files, working tree clean.
    log = git(project, "log", "--format=%s").splitlines()
    assert log[0] == f"baton({run}): assess decision approve [attempt 1]; assess passed [attempt 1, owner]; run completed"
    assert log[1] == f"baton({run}): describe passed [attempt 2, owner]"
    assert status["last_checkpoint"] == git(project, "rev-parse", "HEAD").strip()
    for sha in git(project, "log", "-2", "--format=%H").split():
        files = git(project, "show", "--name-only", "--format=", sha).split()
        assert files and all(f.startswith(f".baton/runs/{run}/") for f in files)
    assert git(project, "status", "--porcelain") == ""

    # Records.
    docs = project / ".baton" / "runs" / run / "docs"
    assert {p.name for p in docs.iterdir()} == {"SUMMARY.md", "describe.md", "assess.md"}
    rec = cli.run("record", run, "describe")["record"]
    assert "## Attempt 1" in rec and "## Attempt 2" in rec and "Retry guidance" in rec
    assert "Agreed; author the recipe." in cli.run("summary", run)["summary"]
    assert any("run_completed" in line for line in cli.run("trace", run)["events"])

    # check passes clean.
    assert cli.run("check")["ok"]


@pytest.mark.slow
def test_fresh_clone_resumes_by_takeover(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    _describe_with_retry(cli, project, run)  # checkpoint commit after describe passed

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(project), str(clone)], check=True)
    assert not (clone / ".baton" / "cache").exists()
    bob = Cli(clone, cli.home, director="bob@host2")

    # Alice's lease came along through git and has not expired.
    res = bob("resume", run, expect=3)
    assert res.payload["lease"]["director_id"] == "alice@host1"
    assert res.payload["status"]["ready"] == ["assess"]
    bob("dispatch", run, "assess", "--worker", "owner", expect=3)

    bob.run("lease", run, "take-over", "--reason", "Owner approved: alice's session ended.")
    out = bob.run("resume", run)
    assert out["lease"]["yours"] and out["steps"]["describe"]["state"] == "passed"

    bob.run("dispatch", run, "assess", "--worker", "owner")
    write_result(packet_dir(clone, run, "assess", 1), VERDICT)
    bob.run("submit", run, "assess", expect=4)
    out = bob.run("decide", run, "assess", "approve")
    assert out["run_completed"] and out["checkpoint"]["committed"]
    assert bob.run("check")["ok"]
    assert "taken over by bob@host2" in bob.run("summary", run)["summary"]


@pytest.mark.slow
def test_fresh_clone_resumes_after_release(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    cli.run("dispatch", run, "describe", "--worker", "owner")
    out = cli.run("lease", run, "release")
    assert out["lease"] is None and out["checkpoint"]["committed"]  # the release travels through git

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(project), str(clone)], check=True)
    bob = Cli(clone, cli.home, director="bob@host2")
    out = bob.run("resume", run)
    assert out["lease"]["yours"]
    assert out["reconciled"] == [{"step_path": "describe", "attempt": 1, "action": "waiting_for_submit"}]
    # The in-flight manual attempt continues on the new machine.
    write_result(packet_dir(clone, run, "describe", 1), GOOD_PROFILE)
    assert bob.run("submit", run, "describe")["outcome"] == "passed"


@pytest.mark.slow
def test_exit_codes(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    assert cli("start", "fit-check", "--inputs", "{not json", expect=2).exit_code == 2
    cli.run("start", "fit-check", "--inputs", json.dumps({"title": "x"}), expect=1)  # schema: idea missing
    cli.run("start", "nope", expect=1)
    run = _start(cli)
    assert cli.run("dispatch", run, "describe", "--worker", "ghost", expect=1)["error"] == "configuration.unknown_profile"
    assert cli.run("dispatch", run, "assess", "--worker", "owner", expect=1)["error"] == "packet.not_ready"
    assert cli.run("submit", run, "describe", expect=1)["error"] == "engine.not_running"
    assert cli.run("decide", run, "describe", "approve", expect=1)["error"] == "decide.nothing_pending"
    assert cli.run("retry", run, "describe", expect=1)["error"] == "retry.not_retryable"
    bob = Cli(project, cli.home, director="bob@host2")
    assert bob.run("dispatch", run, "describe", "--worker", "owner", expect=3)["error"] == "lease.held"
    assert bob.run("lease", run, "release", expect=3)["error"] == "lease.held"
    assert bob.run("lease", run, "take-over", expect=1)["error"] == "lease.reason_required"


@pytest.mark.slow
def test_escalation_decisions(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    cli.run("dispatch", run, "describe", "--worker", "owner")
    write_result(packet_dir(project, run, "describe", 1), None, status="blocked", questions_for_human=["Which vendors count?"])
    out = cli.run("submit", run, "describe", expect=4)
    assert out["outcome"] == "escalated" and out["checkpoint"]["committed"]
    pending = out["pending_decisions"][0]
    assert pending["kind"] == "escalation" and [q["ask"] for q in pending["questions"]] == ["Which vendors count?"]
    assert cli.run("retry", run, "describe", expect=1)["error"] == "retry.escalated"

    out = cli.run("decide", run, "describe", "retry", "--note", "Only vendors over $10k.")
    assert out["outcome"] == "retry" and not out["needs_owner"]
    cli.run("dispatch", run, "describe", "--worker", "owner")
    pf = json.loads((packet_dir(project, run, "describe", 2) / "manifest.json").read_text())["prior_feedback"]
    assert "the owner answered: Only vendors over $10k." in pf["reasons"]
    assert "you asked the owner (q1): Which vendors count?" in pf["reasons"]


@pytest.mark.slow
def test_abandon(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    out = cli.run("abandon", run, "--reason", "Idea dropped.")
    assert out["checkpoint"]["committed"]
    status = cli.run("status", run)
    assert status["state"] == "abandoned" and status["lease"] is None
    assert cli.run("dispatch", run, "describe", "--worker", "owner", expect=1)["error"] == "run.closed"


@pytest.mark.slow
def test_submit_from_external_result_dir(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    cli.run("dispatch", run, "describe", "--worker", "owner")
    manifest = json.loads((packet_dir(project, run, "describe", 1) / "manifest.json").read_text())
    ext = tmp_path / "handed-in"
    ext.mkdir()
    (ext / "result.json").write_text(
        json.dumps({"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": GOOD_PROFILE})
    )
    assert cli.run("submit", run, "describe", "--result", str(ext))["outcome"] == "passed"


@pytest.mark.slow
def test_text_output_is_brief(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    from typer.testing import CliRunner

    from baton.cli import app

    env = {"BATON_HOME": str(cli.home), "BATON_DIRECTOR": cli.director, "BATON_PROJECT": str(project)}
    res = CliRunner(env=env).invoke(app, ["status", run])
    assert res.exit_code == 0
    assert len(res.stdout.strip().splitlines()) == 1  # healthy: one line
    assert "ready: describe" in res.stdout
