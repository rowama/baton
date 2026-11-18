"""Interaction requests (``baton-interaction/1``; Decisions 0169, 0170), Slice 1.

- Every pending decision is a request with an id that ``status`` and ``board`` give; ``interactions`` lists them
  and ``interaction`` returns one, valid against the published format.
- ``answer`` records a choice as ``decide`` would, stamped with ``request_id`` and ``via``; the owner's words are the
  note, or a fixed phrase naming a renderer other than conversation.
- A blocked step's questions are the fields of its ``retry`` choice; framing's ``select`` takes its parts.
- A request's id changes whenever what it asks changes; an answer to an old id is refused as stale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from baton import engine, interactions
from baton.data import path as data_path

from projectkit import FIT_INPUTS, GOOD_PROFILE, Cli
from test_conversation import QUESTIONS, fresh, frame_output, manual, status, _frame
from runkit import write_result
from test_tailoring_axes import WRITER, ctx, rated, signal, store  # noqa: F401 (fixtures)

pytestmark = pytest.mark.slow

SCHEMA = json.loads((data_path("formats") / "baton-interaction-1.schema.json").read_text(encoding="utf-8"))


def valid(req: dict) -> dict:
    errors = [e.message for e in Draft202012Validator(SCHEMA).iter_errors({k: v for k, v in req.items() if k != "ok"})]
    assert not errors, errors
    return req


def events(project: Path, run: str) -> list[dict]:
    lines = (project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _gate(cli: Cli, project: Path) -> str:
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", GOOD_PROFILE)
    out = manual(cli, project, run, "assess", {"verdict": "fits", "assessed_work": "Reviewing vendor contracts",
                                               "reasons": [{"row": "recurrence", "leans": "baton", "basis": "stated", "reason": "few"}],
                                               "next_step": "Author a recipe."})
    assert out["needs_owner"]
    return run


def test_published_format_is_a_valid_schema():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["title"] == interactions.FORMAT == "baton-interaction/1"


def test_a_gate_is_a_request_listed_read_and_answered(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)
    (pd,) = status(cli, run)["pending_decisions"]
    rid = pd["request_id"]
    assert rid.startswith("ir_")
    board = cli("board", expect=None).payload
    assert [p["request_id"] for r in board["runs"] for p in r["pending_decisions"]] == [rid]

    listed = cli("interactions", expect=4).payload
    assert [(r["id"], r["run"], r["ref"], r["kind"]) for r in listed["requests"]] == [(rid, run, "assess", "gate")]
    assert cli("interactions", "--run", run, expect=4).payload["requests"] == listed["requests"]

    req = valid(cli.run("interaction", rid))
    assert req["format"] == "baton-interaction/1" and req["id"] == rid and req["message"] == pd["prompt"]
    assert [(c["decision"], c["label"]) for c in req["choices"]] == [(o["decision"], o["label"]) for o in pd["options"]]
    assert req["needs_confirmation"] is True and req["hints"] == {} and req["extensions"] == {}

    out = cli.run("answer", rid, "--choice", "approve", "--note", "That verdict is right. Yes.")
    assert out["request_id"] == rid and out["via"] == "conversation" and out["outcome"] == "passed"
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["decision"] == "approve" and dec["data"]["note"] == "That verdict is right. Yes."
    assert dec["data"]["request_id"] == rid and dec["data"]["via"] == "conversation"

    again = cli.run("answer", rid, "--choice", "approve", "--note", "yes", expect=1)
    assert again["error"] == "interaction.stale"
    assert cli.run("interaction", rid, expect=1)["error"] == "interaction.stale"


def test_decide_still_works_and_is_not_stamped(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)
    cli.run("decide", run, "assess", "approve", "--note", "yes")
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert "request_id" not in dec["data"] and "via" not in dec["data"]


def test_conversation_needs_the_owners_words_and_another_renderer_may_record_a_fixed_phrase(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    assert cli.run("answer", rid, "--choice", "approve", expect=1)["error"] == "answer.note_required"
    assert cli.run("answer", rid, "--choice", "maybe", "--note", "x", expect=1)["error"] == "answer.invalid"
    assert not [e for e in events(project, run) if e["type"] == "human_decision"]  # nothing recorded
    out = cli.run("answer", rid, "--choice", "reject", "--via", "local page")
    assert out["via"] == "local page"
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["note"] == "confirmed in local page" and dec["data"]["via"] == "local page"


def test_a_blocked_steps_questions_are_the_fields_of_its_retry(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    (pd,) = status(cli, run)["pending_decisions"]
    req = valid(cli.run("interaction", pd["request_id"]))
    assert req["kind"] == "blocked" and req["title"] == interactions.TITLES["blocked"]
    retry, abandon = req["choices"]
    assert "answer" not in abandon
    spec = retry["answer"]
    assert spec["renderable"] and list(spec["schema"]["properties"]) == ["site", "permits", "hours"]
    assert spec["schema"]["required"] == ["site", "permits"]
    site = spec["schema"]["properties"]["site"]
    assert site["title"] == QUESTIONS[0]["ask"] and site["description"] == QUESTIONS[0]["why"]
    assert site["examples"] == ["One machine", "Several"]  # suggestions: the answer may differ
    assert spec["prefill"] == {"site": "One machine per site at first"}

    bad = tmp_path / "bad.yaml"
    bad.write_text("choice: retry\nvalues:\n  site: One each\n", encoding="utf-8")
    out = cli.run("answer", pd["request_id"], "--file", str(bad), "--note", "x", expect=1)
    assert out["error"] == "answer.invalid" and "permits" in out["message"]

    good = tmp_path / "answer.yaml"
    good.write_text("choice: retry\nvalues:\n  site: Two at the big site\n  permits: I do them myself\n"
                    "words:\n  site: \"Two at the big one, actually. Yes.\"\n", encoding="utf-8")
    out = cli.run("answer", pd["request_id"], "--file", str(good), "--note", "Yes, go ahead with those.")
    assert out["outcome"] == "retry"
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["kind"] == "answers" and dec["data"]["request_id"] == pd["request_id"]
    assert dec["data"]["answers"] == [
        {"id": "site", "answer": "Two at the big site", "owner_words": "Two at the big one, actually. Yes."},
        {"id": "permits", "answer": "I do them myself", "owner_words": "Yes, go ahead with those."},
    ]


def test_a_partial_answer_must_say_so(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"choice": "retry", "values": {"site": "One"}, "partial": True}), encoding="utf-8")
    cli.run("answer", rid, "--file", str(f), "--note", "Only that for now. Yes.")
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["partial"] is True and [a["id"] for a in dec["data"]["answers"]] == ["site"]


def test_framing_select_takes_its_parts_from_the_answer(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    (pd,) = status(cli, fr)["pending_decisions"]
    req = valid(cli.run("interaction", pd["request_id"]))
    assert req["kind"] == "frame"
    sel = req["choices"][0]
    assert sel["decision"] == "select" and sel["next"]  # what choosing it triggers, as status gives it
    parts = sel["answer"]["schema"]["properties"]["items"]["items"]["oneOf"]
    assert [p["const"] for p in parts] == ["setup", "kiosk", "signage", "running"]
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"choice": "select", "values": {"items": ["setup", "nope"]}}), encoding="utf-8")
    assert cli.run("answer", pd["request_id"], "--file", str(f), "--note", "x", expect=1)["error"] == "answer.invalid"
    f.write_text(json.dumps({"choice": "select", "values": {"items": ["setup"]}}), encoding="utf-8")
    out = cli.run("answer", pd["request_id"], "--file", str(f), "--note", "Just the setup for now. Yes.")
    assert out["selected"] == ["setup"] and out["request_id"] == pd["request_id"]
    dec = next(e for e in events(project, fr) if e["type"] == "human_decision")
    assert dec["data"]["kind"] == "frame" and dec["data"]["request_id"] == pd["request_id"]


# -- ids change with what is asked (Decision 0170, item 10) ---------------------


def test_a_signal_joining_a_pending_rating_decision_changes_its_id(ctx):
    rated(ctx, discovery="low", assurance="medium")
    signal(ctx, "build", "assurance", "high", "the change reaches the tenant boundary")
    (first,) = [p for p in engine.pending_decisions(ctx) if p["kind"] == "rating_signal"]
    rid = interactions.request_id(ctx, first)
    assert rid == interactions.request_id(ctx, dict(first))  # stable while nothing changes
    p = engine.begin_attempt(ctx, "verify", "owner", WRITER)  # a failed attempt: the run stays active
    write_result(p, {}, status="failed", rating_signal={"axis": "assurance", "suggested": "high", "reason": "and it changes the audit log"})
    assert engine.submit(ctx, "verify").outcome == "retry"
    (second,) = [p for p in engine.pending_decisions(ctx) if p["kind"] == "rating_signal"]
    assert second["ref"] == first["ref"] and interactions.request_id(ctx, second) != rid


def test_what_is_computed_elsewhere_does_not_change_the_id(ctx):
    rated(ctx, discovery="low", assurance="medium")
    signal(ctx, "build", "assurance", "high", "why")
    (p,) = [p for p in engine.pending_decisions(ctx) if p["kind"] == "rating_signal"]
    rid = interactions.request_id(ctx, p)
    annotated = {**p, "web_advice": {"x": 1}, "options": [{**o, "next": "something"} for o in p["options"]]}
    assert interactions.request_id(ctx, annotated) == rid
    changed = {**p, "prompt": p["prompt"] + " (reworded)"}
    assert interactions.request_id(ctx, changed) != rid


def test_a_step_blocked_again_is_a_new_request(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    old = status(cli, run)["pending_decisions"][0]["request_id"]
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"choice": "retry", "values": {"site": "One", "permits": "Me"}}), encoding="utf-8")
    cli.run("answer", old, "--file", str(f), "--note", "Yes.")
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    new = status(cli, run)["pending_decisions"][0]["request_id"]
    assert new != old
    out = cli.run("answer", old, "--file", str(f), "--note", "Yes.", expect=1)
    assert out["error"] == "interaction.stale" and new in out["message"]  # the open one is named
