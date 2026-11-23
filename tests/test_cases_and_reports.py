"""Cases and repro bundles (change 2026-11-self-improvement, slice 1; D1, D2; §12.4, §13.1, §13.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import sme
from baton.redact import SENTINEL_PREFIX
from conftest import ROOT
from projectkit import FIT_INPUTS, Cli, packet_dir, setup_fit_check, write_result

SECRET = SENTINEL_PREFIX + "cases0042"


def _project_events(project: Path) -> list[dict]:
    path = project / ".baton" / "project" / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _feedback(project: Path) -> list[dict]:
    return [e for e in _project_events(project) if e["type"] == "process_feedback"]


def _rejected_run(cli: Cli, project: Path) -> str:
    """A fit-check run whose first describe attempt was rejected by its schema (with a secret in the worker's notes)."""
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    cli.run("dispatch", run, "describe", "--worker", "owner")
    write_result(packet_dir(project, run, "describe", 1), {"summary": "x"}, notes=f"token {SECRET} at {project}/notes.txt")
    cli.run("submit", run, "describe", expect=None)
    return run


@pytest.mark.slow
def test_a_case_with_every_field_round_trips_and_stats_counts_it(tmp_path: Path) -> None:
    cli, project = setup_fit_check(tmp_path)
    run = _rejected_run(cli, project)
    out = cli.run("feedback", "baton_problem", "The schema and the instructions disagree.", "--run", run, "--step", "describe",
                  "--fix-in", "upstream", "--evidence", "12", "--evidence", "steps/describe/attempt-1",
                  "--owner-words", f"hold it, my key is {SECRET}", "--director-harness", "claude-code", "--director-model", "m-1",
                  "--report", ".baton/reports/x")
    cli.run("feedback", "confusing", "The parts question was unclear.", "--run", run, "--step", "describe",
            "--clarified-before", "Which parts to start on?", "--clarified-after", "Which parts to include at all?",
            "--owner-reply", "yes, clearer")
    cli.run("feedback", "friction", "An old-style report.")
    fb = _feedback(project)
    case = next(e for e in fb if e["seq"] == out["seq"])["data"]
    assert case["kind"] == "baton_problem" and case["source"] == "director" and case["fix_in"] == "upstream"
    assert case["evidence"] == ["12", "steps/describe/attempt-1"]
    assert SECRET not in case["owner_words"] and case["owner_words"].startswith("hold it")
    assert case["director"] == {"harness": "claude-code", "model": "m-1"} and case["report"] == ".baton/reports/x"
    assert fb[-2]["data"]["clarified"] == {"before": "Which parts to start on?", "after": "Which parts to include at all?", "owner_reply": "yes, clearer"}
    assert "fix_in" not in fb[-1]["data"] and "clarified" not in fb[-1]["data"]
    stats = sme.stats(_store(project))
    c = stats["cases"]["fit-check@5/describe"]
    assert c["total"] == 2 and c["kinds"] == {"baton_problem": 1, "confusing": 1}
    assert c["fix_in"] == {"upstream": 1, "unclassified": 1}
    assert stats["cases"]["-"] == {"total": 1, "kinds": {"friction": 1}, "fix_in": {"unclassified": 1}}


def _store(project: Path):
    from baton.project import Project

    return Project.open(project).store


@pytest.mark.slow
def test_feedback_refuses_what_a_case_cannot_be(tmp_path: Path) -> None:
    cli, _ = setup_fit_check(tmp_path)
    for args, code in (
        (["repeated_failure", "x"], "feedback.bad_kind"),     # detectors only
        (["friction", "x", "--fix-in", "somewhere"], "feedback.bad_fix_in"),
        (["friction", "x", "--clarified-before", "a", "--clarified-after", "b"], "feedback.clarified"),
        (["confusing", "x", "--clarified-after", "b"], "feedback.clarified"),
    ):
        res = cli("feedback", *args, expect=None)
        assert res.exit_code != 0 and code in res.stdout, (args, res.stdout)


@pytest.mark.slow
def test_a_worker_cannot_report_a_director_or_detector_kind(tmp_path: Path) -> None:
    cli, project = setup_fit_check(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    cli.run("dispatch", run, "describe", "--worker", "owner")
    write_result(packet_dir(project, run, "describe", 1), {"summary": "x"},
                 process_feedback=[{"kind": "baton_problem", "text": "a"}, {"kind": "repeated_failure", "text": "b"}, {"kind": "waste", "text": "c"}])
    cli.run("submit", run, "describe", expect=None)
    assert [(e["data"]["kind"], e["data"]["source"]) for e in _feedback(project)] == [("friction", "worker"), ("friction", "worker"), ("waste", "worker")]


@pytest.mark.slow
def test_report_writes_a_redacted_bundle_and_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli, project = setup_fit_check(tmp_path)
    run = _rejected_run(cli, project)
    log = cli.home / "logs" / run / "describe" / "attempt-1.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(("x" * 70000) + f"\nworker said {SECRET} in {Path.home()}/scratch\n", encoding="utf-8")
    monkeypatch.setenv("BATON_HOME", str(cli.home))
    case = cli.run("feedback", "baton_problem", "Loops on the schema.", "--run", run, "--step", "describe",
                   "--owner-words", "write it up")["seq"]
    before_run = (project / ".baton" / "runs" / run / "events.jsonl").read_bytes()
    before_project = (project / ".baton" / "project" / "events.jsonl").read_bytes()
    out = cli.run("report", run, "describe", "--case", str(case), "--title", "Describe loops")
    assert (project / ".baton" / "runs" / run / "events.jsonl").read_bytes() == before_run
    assert (project / ".baton" / "project" / "events.jsonl").read_bytes() == before_project
    root = project / out["path"]
    assert out["path"].startswith(".baton/reports/") and out["path"].endswith("-describe-loops")
    text = (root / "report.md").read_text(encoding="utf-8")
    assert "recipe `fit-check@5`" in text and f"`{run}`, step `describe`" in text and f"Case: seq {case}, kind `baton_problem`" in text
    assert "The owner's words: write it up" in text and "| 1 | owner | manual |" in text and "result_rejected" in text
    for section in ("## What happened", "## Root cause", "## Expected", "## Suggested fixes", "## Evidence"):
        assert section in text
    files = set(out["files"])
    assert {"events.jsonl", "summary.md", "step-record.md", "attempt-1/result.json", "attempt-1/worker.log", "recipe.yaml",
            "attempt-1/packet/INSTRUCTIONS.md", "attempt-1/packet/manifest.json"} <= files
    assert any(f.startswith("attempt-1/packet/") and f.endswith(".json") and "manifest" not in f for f in files)  # the schemas
    for f in files:
        body = (root / "bundle" / f).read_bytes()
        assert SECRET.encode() not in body, f
        assert str(project.resolve()).encode() not in body, f
    wlog = (root / "bundle" / "attempt-1" / "worker.log").read_text(encoding="utf-8")
    assert len(wlog) <= 64 * 1024 + 100 and "in ~/scratch" in wlog
    assert "<project>/notes.txt" in (root / "bundle" / "attempt-1" / "result.json").read_text(encoding="utf-8")
    assert (project / ".baton" / "reports" / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"
    again = cli.run("report", run, "describe", "--title", "Describe loops")
    assert again["path"] == out["path"] + "-2"
    whole = cli.run("report", run)
    assert "step-record.md" not in whole["files"] and "events.jsonl" in whole["files"]
    res = cli("report", run, "nosuch", expect=None)
    assert res.exit_code != 0 and "report.unknown_step" in res.stdout
    res = cli("report", run, "--case", "99999", expect=None)
    assert res.exit_code != 0 and "report.unknown_case" in res.stdout


@pytest.mark.not_slow("reads a file")
def test_the_director_skill_holds_the_rules_for_baton_problems() -> None:
    text = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    sec = text[text.index("## When Baton itself goes wrong"):text.index("## Before you ask the owner anything")]
    assert "`feedback baton_problem`" in sec and "--fix-in upstream" in sec and "--evidence" in sec and "--owner-words" in sec
    assert "don't wait to be asked" in sec and "`report <run> <step> --case <seq>`" in sec and "--report <path>" in sec
    assert '"This looks like a Baton problem, not yours. I\'ve written it up. I can hold this, or try X. Which?"' in sec
    assert "--director-harness" in sec and "fixed upstream, never edited in the project" in sec
    assert '"Is that clearer?"' in sec and "--clarified-before" in sec and "--owner-reply" in sec
