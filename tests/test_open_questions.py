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


# -- Slice 2: answering open questions, alone or with a retry -----------------------

CONFIRMED = [{"id": "A-VER-1", "answer": "ask before the first number; the others go up on their own",
              "owner_words": "Ask before bumping the first number, otherwise approved."}]


def _manifest(p) -> dict:
    return json.loads((p.dir / "manifest.json").read_text(encoding="utf-8"))


def test_answering_a_steps_open_questions_records_them_and_they_last(store, tmp_path):
    ctx, base = _round_one(store, tmp_path)
    out = engine.decide(ctx, f"{base}/i1/implement", "answer", "Ask before bumping the first number.", answers=CONFIRMED)
    assert out.outcome == "recorded" and "1 answer(s) recorded" in out.reasons[0]
    dec = [e for e in ctx.log.events() if e.type == "human_decision"][-1]
    assert (dec.step_path, dec.attempt) == (f"{base}/i1/implement", 1)
    assert dec.data["kind"] == "answers" and dec.data["decision"] == "answer" and dec.data["answers"] == CONFIRMED
    assert _open(ctx) == [{"step_path": f"{base}/i1/implement", "attempt": 1, "ids": ["A-GAP-1"]}]  # a partial set is fine

    review = begin(ctx, f"{base}/i1/review")  # the review sees what the owner settled (0181, item 2)
    assert _manifest(review)["prior_feedback"]["answers_earlier"][0]["answers"] == CONFIRMED
    from runkit import write_result

    write_result(review, HIGH)
    assert engine.submit(ctx, f"{base}/i1/review").outcome == "next_iteration"
    p = begin(ctx, f"{base}/i2/implement")  # and so does the next round
    assert [(e["step"], e["iteration"]) for e in _manifest(p)["prior_feedback"]["answers_earlier"]] == [(f"{base}/i1/implement", 1)]
    assert "Ask before bumping the first number" in (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("answers", "note", "code", "says"), [
    (None, "words", "decide.bad_decision", "answer goes with --answers"),
    (CONFIRMED, "", "decide.note_required", "--note"),
    ([{"id": "nope", "answer": "x", "owner_words": "x"}], "words", "answers.invalid", "not one of the open questions here (A-GAP-1, A-VER-1)"),
    ([{"id": "A-VER-1", "answer": "x"}], "words", "answers.invalid", "owner_words is required"),
])
def test_answers_to_open_questions_are_checked(store, tmp_path, answers, note, code, says):
    ctx, base = _round_one(store, tmp_path)
    before = len(ctx.log.events())
    with pytest.raises(engine.EngineError) as e:
        engine.decide(ctx, f"{base}/i1/implement", "answer", note, answers=answers)
    assert e.value.code == code and says in str(e.value)
    assert len(ctx.log.events()) == before


def test_a_step_without_open_questions_says_which_steps_have_them(store, tmp_path):
    ctx, base = _round_one(store, tmp_path)
    with pytest.raises(engine.EngineError) as e:
        engine.decide(ctx, "plan", "answer", "words", answers=CONFIRMED)
    assert e.value.code == "decide.nothing_pending" and f"{base}/i1/implement" in str(e.value)


def _at_the_limit(store, tmp_path, *, review_asks=None):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=1))
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    base = f"slices/{ids(ctx)[0]}"
    run_step(ctx, f"{base}/i1/implement", {"commit_sha": "c1"}, questions_for_human=GUESSES)
    _, out = run_step(ctx, f"{base}/i1/review", HIGH, **({"questions_for_human": review_asks} if review_asks else {}))
    assert out.outcome == "iteration_limit"
    return ctx, base


def test_another_round_with_answers_records_them_against_the_asking_step(store, tmp_path):
    # r_20261119_ee96: "Give it another set of rounds, but ask me the four questions first."
    ctx, base = _at_the_limit(store, tmp_path)
    p = [x for x in engine.pending_decisions(ctx) if x["kind"] == "iteration_limit"][0]
    from baton import interactions

    req = interactions.build(None, ctx, {**p, "request_id": interactions.request_id(ctx, p)})
    retry = next(c for c in req["choices"] if c["decision"] == "retry")
    assert set(retry["answer"]["schema"]["properties"]) == {"A-VER-1", "A-GAP-1"} and retry["answer"]["schema"]["required"] == []
    assert "answer" not in next(c for c in req["choices"] if c["decision"] == "abandon")

    out = engine.decide(ctx, base, "retry", "Another round; ask before bumping the first number.", answers=CONFIRMED)
    assert out.outcome != "escalated" and "1 answer(s) to open questions recorded" in out.reasons[-1]
    types = [e.type for e in ctx.log.events()]
    assert types[-1] == "human_decision" and "iteration_started" in types[-4:]
    dec = ctx.log.events()[-1]
    assert (dec.step_path, dec.data["decision"], dec.data["answers"]) == (f"{base}/i1/implement", "retry", CONFIRMED)
    p2 = begin(ctx, f"{base}/i2/implement")
    assert _manifest(p2)["prior_feedback"]["answers_earlier"][0]["answers"] == CONFIRMED


def test_an_id_two_steps_ask_is_answered_one_step_at_a_time(store, tmp_path):
    ctx, base = _at_the_limit(store, tmp_path, review_asks=[GUESSES[0]])
    before = len(ctx.log.events())
    with pytest.raises(engine.EngineError) as e:
        engine.decide(ctx, base, "retry", "words", answers=CONFIRMED)
    assert e.value.code == "answers.invalid" and "answer it one step at a time" in str(e.value)
    assert len(ctx.log.events()) == before  # neither the answers nor the retry were recorded
    engine.decide(ctx, f"{base}/i1/review", "answer", "words", answers=CONFIRMED)
    assert [o["ids"] for o in _open(ctx)] == [["A-VER-1", "A-GAP-1"]]


def test_answers_go_only_with_a_retry_or_a_reject_and_are_always_partial(store, tmp_path):
    ctx, base = _at_the_limit(store, tmp_path)
    with pytest.raises(engine.EngineError) as e:
        engine.decide(ctx, base, "abandon", "words", answers=CONFIRMED)
    assert e.value.code == "decide.bad_decision" and "retry or reject" in str(e.value)
    with pytest.raises(engine.EngineError) as e:
        engine.decide(ctx, base, "retry", "words", answers=CONFIRMED, partial=True)
    assert e.value.code == "decide.bad_decision" and "may always be partial" in str(e.value)


def test_the_open_questions_request(store, tmp_path):
    from baton import interactions
    from baton.questions import open_questions

    ctx, base = _round_one(store, tmp_path)
    entry = open_questions(ctx.recipe, ctx.log.events())[0]
    req = interactions.build_open_questions(ctx, entry)
    assert req["kind"] == "open_questions" and req["ref"] == f"{base}/i1/implement" and req["attempt"] == 1
    (choice,) = req["choices"]
    assert choice["decision"] == "answer" and choice["label"] == "Confirm or correct these"
    assert choice["answer"]["schema"]["required"] == [] and choice["answer"]["prefill"]["A-VER-1"].startswith("Ask before")
    engine.decide(ctx, f"{base}/i1/implement", "answer", "words", answers=CONFIRMED)
    assert interactions.build_open_questions(ctx, open_questions(ctx.recipe, ctx.log.events())[0])["id"] != req["id"]
