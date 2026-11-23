"""The circuit breaker (change 2026-11-self-improvement, slice 2; D3; §8.8; Decision 0188, item 2)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from baton import engine, sme
from baton.store import Store
from conftest import FIT_CHECK
from runkit import PROFILE_OUT, VERDICT_OUT, WRITER, Clock, make_recipe, start, write_result

PY = shlex.quote(sys.executable) if os.name == "posix" else subprocess.list2cmdline([sys.executable])
X_SCHEMA = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def attempt(ctx, step: str, output, **kw):
    p = engine.begin_attempt(ctx, step, "owner", WRITER)
    write_result(p, output, **kw)
    return p, engine.submit(ctx, step)


def toy(root: Path, attempts: int = 3, gates: list | None = None) -> Path:
    return make_recipe(root, [{"id": "work", "output_schema": "schemas/out.json", "gates": gates or [{"type": "schema"}]}],
                       schemas={"out.json": X_SCHEMA}, defaults={"max_attempts": attempts})


def escalation(ctx, step: str = "work") -> dict:
    return ctx.record().last("step_escalated", step).data


def cases(store: Store) -> list[dict]:
    return [e.data for e in store.project_log().events() if e.type == "process_feedback"]


@pytest.mark.not_slow("measured under 1 s")
def test_reasons_differing_only_in_attempt_sha_or_number_match() -> None:
    # The two attempts of issues/2026-11-20-design-evidence-and-lost-answers.md, as the runtime worded them.
    a = ("dispositions[0] (fixed F01): .baton/runs/r_20261119_ee96/steps/shape/x5b12127/i2/design/attempt-2/result/"
         "artifacts/design_doc.md:271 does not exist at commit 13b48b35a3ad")
    b = ("dispositions[0] (fixed F01): .baton/runs/r_20261119_ee96/steps/shape/x5b12127/i2/design/attempt-3/result/"
         "artifacts/design_doc.md:280 does not exist at commit 9f0c2d41be77")
    assert engine._normalized_reason(a) == engine._normalized_reason(b)
    assert engine._normalized_reason("  Missing   X ") == "missing x"
    assert engine._normalized_reason("'x' is a required property") != engine._normalized_reason("1 is not of type 'string'")


@pytest.mark.not_slow("measured under 1 s")
def test_the_same_rejection_twice_escalates_with_the_spend_and_a_case(store, tmp_path) -> None:
    ctx = start(store, toy(tmp_path / "r", attempts=5), {})
    assert attempt(ctx, "work", {})[1].outcome == "retry"
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "escalated" and ctx.log.state().step("work").state == "escalated"
    esc = escalation(ctx)
    assert esc["reason"] == "repeated_failure" and esc["attempts"] == [1, 2]
    assert esc["failure"] == {"event": "result_rejected", "gate": None}
    assert esc["spend"] == {"usd": 0.0, "attempts_priced": 0, "attempts_included": 0, "attempts_unknown": 2}
    assert "the same failure on attempts 1 and 2" in out.reasons[0] and any("'x' is a required property" in r for r in out.reasons)
    [case] = cases(store)
    assert case["kind"] == "repeated_failure" and case["source"] == "detector:repeated_failure"
    assert case["run"] == ctx.run_id and case["step_path"] == "work" and case["attempt"] == 2 and case["qualified"] == "toy@1/work"
    assert len(case["evidence"]) == 2
    stats = sme.stats(store)
    assert stats["steps"]["toy@1/work"]["owner"]["stops"] == 1
    assert stats["steps"]["toy@1/work"]["escalations"] == {"repeated_failure": 1}
    assert stats["cases"]["toy@1/work"]["kinds"] == {"repeated_failure": 1}


@pytest.mark.not_slow("measured under 1 s")
def test_the_spend_counts_priced_and_included_attempts(store, tmp_path) -> None:
    ctx = start(store, toy(tmp_path / "r"), {})
    for n, usage in ((1, {"cost_usd": 0.25, "input_tokens": 10}), (2, None)):
        p = engine.begin_attempt(ctx, "work", "owner", WRITER)
        if usage:
            (p.dir.parent / "usage.json").write_text(json.dumps(usage), encoding="utf-8")
        write_result(p, {})
        engine.submit(ctx, "work")
    assert escalation(ctx)["spend"] == {"usd": 0.25, "attempts_priced": 1, "attempts_included": 0, "attempts_unknown": 1}


@pytest.mark.not_slow("measured under 1 s")
def test_different_reasons_keep_retrying_until_the_budget_is_used(store, tmp_path) -> None:
    ctx = start(store, toy(tmp_path / "r"), {})
    assert attempt(ctx, "work", {})[1].outcome == "retry"
    assert attempt(ctx, "work", {"x": 1})[1].outcome == "retry"
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "escalated" and escalation(ctx)["reason"] == "attempts_exhausted"
    assert cases(store) == []


@pytest.mark.not_slow("measured under 1 s")
def test_with_two_attempts_the_reason_is_repeated_failure(store, tmp_path) -> None:
    ctx = start(store, toy(tmp_path / "r", attempts=2), {})
    attempt(ctx, "work", {})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "escalated" and escalation(ctx)["reason"] == "repeated_failure"


@pytest.mark.not_slow("measured under 1 s")
def test_a_gate_failing_the_same_way_with_a_new_sha_each_time_stops(store, tmp_path) -> None:
    # The class of the 2026-11-20 loop: a check whose message names something new each attempt, failing the same way.
    run = f"{PY} -c \"import secrets, sys; print('design_doc.md does not exist at commit', secrets.token_hex(6)); sys.exit(1)\""
    ctx = start(store, toy(tmp_path / "r", gates=[{"type": "schema"}, {"type": "script", "run": run}]), {})
    assert attempt(ctx, "work", {"x": "a"})[1].outcome == "retry"
    _, out = attempt(ctx, "work", {"x": "a"})
    assert out.outcome == "escalated"
    esc = escalation(ctx)
    assert esc["reason"] == "repeated_failure" and esc["failure"] == {"event": "gate_failed", "gate": 1}


@pytest.mark.not_slow("measured under 1 s")
def test_a_different_gate_failing_is_a_different_failure(store, tmp_path) -> None:
    fail = f"{PY} -c \"import sys; print('no'); sys.exit(1)\""
    flag = tmp_path / "second"
    once = f"{PY} -c \"import os, sys; p = {str(flag)!r}; sys.exit(0 if os.path.exists(p) else (open(p, 'w').close() or 1))\""
    ctx = start(store, toy(tmp_path / "r", gates=[{"type": "schema"}, {"type": "script", "run": once}, {"type": "script", "run": fail}]), {})
    _, first = attempt(ctx, "work", {"x": "a"})   # gate 1 fails
    assert first.outcome == "retry"
    _, second = attempt(ctx, "work", {"x": "a"})  # gate 1 passes now, gate 2 fails
    assert second.outcome == "retry"
    _, third = attempt(ctx, "work", {"x": "a"})   # gate 2 again: repeated
    assert third.outcome == "escalated" and escalation(ctx)["reason"] == "repeated_failure" and escalation(ctx)["failure"]["gate"] == 2


@pytest.mark.not_slow("measured under 1 s")
def test_a_decision_readies_the_step_with_a_fresh_budget(store, tmp_path) -> None:
    ctx = start(store, toy(tmp_path / "r"), {})
    attempt(ctx, "work", {})
    attempt(ctx, "work", {})
    assert escalation(ctx)["reason"] == "repeated_failure"
    engine.decide(ctx, "work", "retry", note="the schema wants x")
    assert ctx.log.state().step("work").state == "ready"
    assert attempt(ctx, "work", {})[1].outcome == "retry"  # the window restarted: attempt 3 has no predecessor in it
    _, out = attempt(ctx, "work", {"x": "done"})
    assert out.outcome == "passed"


@pytest.mark.slow  # loads and hashes the shipped fit-check recipe several times: over 1 s
def test_an_owner_rejection_at_a_human_gate_is_not_a_loop(store) -> None:
    ctx = start(store, FIT_CHECK)
    attempt(ctx, "describe", PROFILE_OUT)
    for _ in range(2):
        _, out = attempt(ctx, "assess", VERDICT_OUT)
        assert out.outcome == "needs_human"
        out = engine.decide(ctx, "assess", "reject", "not yet")
        assert out.outcome == "retry"
    assert ctx.log.state().step("assess").state == "ready"


@pytest.mark.not_slow("measured under 1 s")
def test_the_held_gate_can_be_waived_after_a_repeated_failure(store, tmp_path) -> None:
    fail = f"{PY} -c \"import sys; print('no'); sys.exit(1)\""
    ctx = start(store, toy(tmp_path / "r", gates=[{"type": "schema"}, {"type": "script", "run": fail}]), {})
    attempt(ctx, "work", {"x": "a"})
    attempt(ctx, "work", {"x": "a"})
    assert escalation(ctx)["reason"] == "repeated_failure"
    out = engine.waive(ctx, "work", "1", "The check is wrong here; let it through.")
    assert out.outcome == "passed" and ctx.log.state().step("work").state == "passed"


@pytest.mark.not_slow("reads a file")
def test_the_director_skill_offers_one_choice_with_the_spend() -> None:
    from conftest import ROOT

    text = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    assert "reason `repeated_failure` failed the same way twice" in text and "(`spend`" in text and "waive it" in text
