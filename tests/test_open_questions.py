"""Questions without blocking (change 2026-11-answers-between-rounds; Decision 0184).

A completed result may ask the owner to confirm its guesses. The run keeps them as open questions, step by step
(every round of a group counting as one step), until the owner answers them; nothing waits for them. Reproduces
run r_20261119_ee96 in miniature: a design guesses, the review fails it, the owner answers between rounds.
"""

from __future__ import annotations

import json

import pytest

from baton import engine
from baton.questions import open_questions

from test_groups import HIGH, begin, ids, run_step, slice_recipe, start_run, store  # noqa: F401 (store is a fixture)

pytestmark = pytest.mark.not_slow("in-process engine calls, under 1 s each")

GUESSES = [{"id": "A-VER-1", "ask": "May the first version number go up without asking you?", "why": "Sets when a release waits for you",
            "best_guess": "Ask before the first number; the others go up on their own"},
           {"id": "A-GAP-1", "ask": "What may happen to a check nobody ran?", "why": "Sets how unchecked work is handled",
            "best_guess": "You check it, push it to a named later piece, or accept the risk", "priority": "helpful"}]


def _round_one(store, tmp_path, *, questions=GUESSES):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    base = f"slices/{ids(ctx)[0]}"
    _, out = run_step(ctx, f"{base}/i1/implement", {"commit_sha": "c1"}, questions_for_human=questions)
    assert out.outcome == "passed"  # nothing waits for the questions
    return ctx, base


def _open(ctx) -> list[dict]:
    return [{k: o[k] for k in ("step_path", "attempt")} | {"ids": [q["id"] for q in o["questions"]]}
            for o in open_questions(ctx.recipe, ctx.log.events())]


def test_a_completed_result_may_ask_and_its_questions_are_open(store, tmp_path):
    ctx, base = _round_one(store, tmp_path)
    sub = [e for e in ctx.log.events() if e.type == "result_submitted" and e.step_path == f"{base}/i1/implement"][-1]
    assert [q["id"] for q in sub.data["questions"]] == ["A-VER-1", "A-GAP-1"]
    assert sub.data["questions"][0]["best_guess"].startswith("Ask before")
    assert _open(ctx) == [{"step_path": f"{base}/i1/implement", "attempt": 1, "ids": ["A-VER-1", "A-GAP-1"]}]


def test_a_result_with_no_questions_records_none(store, tmp_path):
    ctx, base = _round_one(store, tmp_path, questions=[])
    sub = [e for e in ctx.log.events() if e.type == "result_submitted" and e.step_path == f"{base}/i1/implement"][-1]
    assert "questions" not in sub.data and _open(ctx) == []


def test_a_rejected_result_asks_nothing(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    base = f"slices/{ids(ctx)[0]}"
    _, out = run_step(ctx, f"{base}/i1/implement", {"commit_sha": "c1"}, packet_sha256="0" * 64, questions_for_human=GUESSES)
    assert out.outcome == "retry"
    sub = [e for e in ctx.log.events() if e.type == "result_submitted"][-1]
    assert "questions" not in sub.data and _open(ctx) == []


def test_the_next_round_replaces_the_last_rounds_questions(store, tmp_path):
    ctx, base = _round_one(store, tmp_path)
    run_step(ctx, f"{base}/i1/review", HIGH)  # the review fails the design: round two
    run_step(ctx, f"{base}/i2/implement", {"commit_sha": "c2"}, questions_for_human=[GUESSES[1]])
    assert _open(ctx) == [{"step_path": f"{base}/i2/implement", "attempt": 1, "ids": ["A-GAP-1"]}]
    run_step(ctx, f"{base}/i2/review", HIGH)
    run_step(ctx, f"{base}/i3/implement", {"commit_sha": "c3"})  # asks nothing now: nothing is open
    assert _open(ctx) == []


def test_an_answered_question_is_not_open_in_any_round(store, tmp_path):
    ctx, base = _round_one(store, tmp_path)
    ctx.log.append("human_decision", actor="human", step_path=f"{base}/i1/implement", attempt=1,
                   data={"ref": f"{base}/i1/implement", "kind": "answers", "decision": "answer",
                         "answers": [{"id": "A-VER-1", "answer": "ask first", "owner_words": "Ask me first."}], "note": "Ask me first."})
    assert _open(ctx) == [{"step_path": f"{base}/i1/implement", "attempt": 1, "ids": ["A-GAP-1"]}]
    run_step(ctx, f"{base}/i1/review", HIGH)
    run_step(ctx, f"{base}/i2/implement", {"commit_sha": "c2"}, questions_for_human=GUESSES)  # asked again by mistake
    assert _open(ctx) == [{"step_path": f"{base}/i2/implement", "attempt": 1, "ids": ["A-GAP-1"]}]


def test_the_contracts_say_a_completed_result_may_ask(store, tmp_path):
    from baton import worker_runner

    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    p = begin(ctx, "plan")
    text = (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "A `completed` result may also list `questions_for_human`" in text and "is still `blocked`" in text
    src = json.dumps([v for k, v in vars(worker_runner).items() if isinstance(v, str)])
    assert 'A \\"completed\\" result may also list questions_for_human' in src
