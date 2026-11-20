"""The owner's answers last (change 2026-11-first-use-feedback-batch-a, Slice 4: F-7, F-8; Decision 0181, items 2 and 3).

F-7: answers given in one round of a group's iteration reach the same step in every later round, and the
review of that step. F-8: a retry after answers receives the blocked attempt's output, and the answers'
record carries that output's hash. Reproduces the recipe-builder run of 2026-11-20 in miniature: a
design asks, the owner answers, the review fails the design, and round two's design asks nothing new.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from baton import engine
from baton.store import canonical_json

from test_groups import HIGH, begin, ids, run_step, slice_recipe, start_run, store  # noqa: F401 (store is a fixture)

pytestmark = pytest.mark.not_slow("in-process engine calls, under 1 s each")

QUESTIONS = [{"id": "venue", "ask": "Indoors or outdoors?", "why": "Sets the venue list"},
             {"id": "rows", "ask": "Accept the row-by-row suggestions?", "why": "They shape the design"}]
PROPOSAL = {"rows": [{"row": "venue", "suggest": "adopt"}, {"row": "catering", "suggest": "adapt"}]}
ANSWERS = [{"id": "venue", "answer": "outdoors", "owner_words": "Outdoors, weather permitting."},
           {"id": "rows", "answer": "accept", "owner_words": "Accept all as suggested."}]


def _manifest(p) -> dict:
    return json.loads((p.dir / "manifest.json").read_text(encoding="utf-8"))


def _asked_and_answered(ctx, path: str) -> None:
    p = begin(ctx, path)
    from runkit import write_result

    write_result(p, PROPOSAL, status="blocked", questions_for_human=QUESTIONS)
    assert engine.submit(ctx, path).outcome == "escalated"
    engine.decide(ctx, path, "retry", "Outdoors; accept all as suggested.", answers=ANSWERS)


def test_a_retry_after_answers_gets_the_blocked_output_and_the_record_keeps_its_hash(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    base = f"slices/{ids(ctx)[0]}"
    _asked_and_answered(ctx, f"{base}/i1/implement")
    dec = [e for e in ctx.log.events() if e.type == "human_decision" and e.data.get("kind") == "answers"][-1]
    sha = dec.data["output_sha256"]
    assert sha == hashlib.sha256(canonical_json(PROPOSAL).encode("utf-8")).hexdigest() or ctx.log.cas.has(sha)
    assert json.loads(ctx.log.cas.read(sha)) == PROPOSAL  # what "accept" accepted stands in the record (F-8)

    p = begin(ctx, f"{base}/i1/implement")
    pf = _manifest(p)["prior_feedback"]
    assert pf["answers"] == ANSWERS
    assert pf["prior_output"] == {"attempt": 1, "output": "blocked/output.json", "sha256": sha}
    assert json.loads((p.dir / "blocked" / "output.json").read_text(encoding="utf-8")) == PROPOSAL
    text = (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "## Your previous output" in text and "accepts that output" in text


def test_answers_reach_the_same_step_in_the_next_round_and_its_review(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    base = f"slices/{ids(ctx)[0]}"
    _asked_and_answered(ctx, f"{base}/i1/implement")
    run_step(ctx, f"{base}/i1/implement", {"commit_sha": "c1"})

    # The review sees what the owner settled, so it does not fail the design for following it (0181, item 2).
    review = begin(ctx, f"{base}/i1/review")
    earlier = _manifest(review)["prior_feedback"]["answers_earlier"]
    assert [(e["step"], e["iteration"], e["attempt"]) for e in earlier] == [(f"{base}/i1/implement", 1, 1)]
    assert earlier[0]["answers"] == ANSWERS
    from runkit import write_result

    write_result(review, HIGH)
    assert engine.submit(ctx, f"{base}/i1/review").outcome == "next_iteration"

    # Round two's first attempt: a new step path, still given the owner's answers, and asked not to ask again.
    p = begin(ctx, f"{base}/i2/implement")
    pf = _manifest(p)["prior_feedback"]
    assert pf["attempt"] == 0 and "answers" not in pf and "prior_output" not in pf
    assert [(e["step"], e["iteration"]) for e in pf["answers_earlier"]] == [(f"{base}/i1/implement", 1)]
    text = (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "## The owner's earlier answers" in text and "Do not ask about them again" in text
    assert "Outdoors, weather permitting." in text and "Attempt 0 was not accepted" not in text


def test_a_step_with_no_answers_has_no_earlier_answers(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    base = f"slices/{ids(ctx)[0]}"
    p = begin(ctx, f"{base}/i1/implement")
    assert _manifest(p)["prior_feedback"] is None


def test_the_worker_skill_says_earlier_answers_stand_and_to_build_on_the_blocked_output():
    from conftest import ROOT

    text = (ROOT / "skills" / "baton-worker" / "SKILL.md").read_text(encoding="utf-8")
    assert "`prior_feedback.answers_earlier`" in text and "Do not ask about them again" in text
    assert "`prior_feedback.prior_output`" in text and "Build on it." in text
