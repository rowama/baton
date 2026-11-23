"""Process statistics: cost, owner burden and outcome per step, and run totals per recipe (§12.4; Decision 0187).

Each count is checked from a recorded event log: a store double holding the events of two runs and the attempts'
``usage.json`` files, read by ``sme.stats`` as it reads a project's runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from baton import sme


class _Run:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def events(self) -> list[Any]:
        return self._events


class _Store:
    def __init__(self, root: Path, runs: dict[str, list[Any]]) -> None:
        self.root, self.runs = root, runs

    def run_ids(self) -> list[str]:
        return sorted(self.runs)

    def run(self, rid: str) -> _Run:
        return _Run(self.runs[rid])

    def run_dir(self, rid: str) -> Path:
        return self.root / rid

    def project_log(self) -> _Run:
        return _Run([])  # no process feedback: stats' cases are covered in test_cases_and_reports.py


class _Log:
    """Builds a run's events, one minute apart unless a time is given."""

    def __init__(self, recipe: str) -> None:
        self.events: list[Any] = []
        self.minute = 0
        self.add("run_started", data={"recipe": recipe})

    def add(self, type_: str, step: str | None = None, attempt: int | None = None, at: int | None = None, **data: Any) -> None:
        self.minute = self.minute + 1 if at is None else at
        h, m = divmod(self.minute, 60)
        ts = f"2026-11-22T{h:02d}:{m:02d}:00Z"
        self.events.append(SimpleNamespace(type=type_, step_path=step, attempt=attempt, ts=ts, seq=len(self.events) + 1,
                                           data=data.get("data", data)))


def _usage(root: Path, rid: str, step: str, attempt: int, **u: Any) -> None:
    d = root / rid / "steps" / step / f"attempt-{attempt}"
    d.mkdir(parents=True)
    (d / "usage.json").write_text(json.dumps({"calls": 1, "seconds": 1.0, **u}), encoding="utf-8")


def _record(tmp_path: Path) -> dict[str, Any]:
    a = _Log("r@1")
    # draft, attempt 1: a priced API route; asks two questions on a completed result; the owner answers one of them
    # without the step waiting (an open answer ends no stop), then rejects it at its human gate after 30 minutes.
    a.add("worker_selected", "draft", 1, profile="api", included=False)
    a.add("dispatched", "draft", 1, profile="api")
    a.add("result_submitted", "draft", 1, status="completed", questions=[{"id": "q1"}, {"id": "q2"}])
    a.add("human_gate_opened", "draft", 1, at=100, gate=0)
    a.add("human_decision", "draft", 1, data={"ref": "draft", "kind": "answers", "decision": "answer", "open": True,
                                              "answers": [{"id": "q1", "answer": "yes"}]})
    a.add("human_decision", "draft", 1, at=130, data={"ref": "draft", "kind": "gate", "gate": 0, "decision": "reject"})
    # draft, attempt 2: an included subscription route that measured nothing; asks q1 again (re-asked) and q3 (left open);
    # approved after 10 minutes; the owner later edits its published file.
    a.add("worker_selected", "draft", 2, profile="sub", included=True)
    a.add("dispatched", "draft", 2, profile="sub")
    a.add("result_submitted", "draft", 2, status="completed", questions=[{"id": "q1"}, {"id": "q3"}])
    a.add("human_gate_opened", "draft", 2, at=200, gate=0)
    a.add("human_decision", "draft", 2, at=210, data={"ref": "draft", "kind": "gate", "gate": 0, "decision": "approve"})
    a.add("step_passed", "draft", 2)
    a.add("human_revision_ingested", "draft", source="drift", artifact="doc")
    a.add("human_revision_ingested", "draft", source="director", artifact="doc")  # not the owner's edit of a published file
    # review: recorded before the included flag; attempt 1 has tokens but no cost (unknown), blocked with a question
    # answered after an hour; attempt 2 wrote no usage record (unknown); approved at its first gate decision.
    a.add("worker_selected", "review", 1, profile="old")
    a.add("dispatched", "review", 1, profile="old")
    a.add("result_submitted", "review", 1, status="blocked")
    a.add("step_escalated", "review", 1, at=300, reason="blocked", questions=[{"id": "b1"}])
    a.add("human_decision", "review", 1, at=360, data={"ref": "review", "kind": "answers", "decision": "retry", "answers": [{"id": "b1"}]})
    a.add("worker_selected", "review", 2, profile="old")
    a.add("dispatched", "review", 2, profile="old")
    a.add("result_submitted", "review", 2, status="completed")
    a.add("human_gate_opened", "review", 2, at=400, gate=0)
    a.add("human_decision", "review", 2, at=405, data={"ref": "review", "kind": "gate", "gate": 0, "decision": "approve"})
    a.add("step_passed", "review", 2)
    # a loop at its iteration limit is one stop of the group, ended by the owner's decision on it
    a.add("iteration_started", "loop/x1a2b3c4", iteration=3)
    a.add("iteration_limit_reached", "loop/x1a2b3c4", at=500, iteration=3, max_iterations=3)
    a.add("human_decision", "loop/x1a2b3c4", at=520, data={"ref": "loop/x1a2b3c4", "kind": "iteration_limit", "decision": "abandon"})
    a.add("run_completed")
    _usage(tmp_path, "r1", "draft", 1, input_tokens=1000, output_tokens=200, cost_usd=0.25)
    _usage(tmp_path, "r1", "review", 1, input_tokens=50, output_tokens=5, cost_usd=None)

    b = _Log("r@1")
    b.add("worker_selected", "draft", 1, profile="api", included=False)
    b.add("dispatched", "draft", 1, profile="api")
    b.add("result_submitted", "draft", 1, status="completed")
    b.add("human_gate_opened", "draft", 1, gate=0)  # never decided: a stop with no wait
    b.add("run_abandoned")
    _usage(tmp_path, "r2", "draft", 1, input_tokens=10, output_tokens=10, cost_usd=0.5)
    return sme.stats(_Store(tmp_path, {"r1": a.events, "r2": b.events}))


def test_cost_counts_priced_included_and_unknown_attempts_without_estimating(tmp_path: Path) -> None:
    st = _record(tmp_path)["steps"]
    assert st["r@1/draft"]["cost"] == {"usd": 0.75, "tokens_in": 1010, "tokens_out": 210,
                                       "attempts_priced": 2, "attempts_included": 1, "attempts_unknown": 0}
    # Tokens with no cost are counted, the attempt is unknown; an attempt from before the flag is unknown too (0187, item 5).
    assert st["r@1/review"]["cost"] == {"usd": 0.0, "tokens_in": 50, "tokens_out": 5,
                                        "attempts_priced": 0, "attempts_included": 0, "attempts_unknown": 2}


def test_owner_burden_counts_stops_questions_reasked_decisions_and_waits(tmp_path: Path) -> None:
    st = _record(tmp_path)["steps"]
    # Two gates in r1 and one never decided in r2; three decisions (an open answer and two gate decisions).
    assert st["r@1/draft"]["owner"] == {"stops": 3, "questions": 4, "open": 1, "reasked": 1, "decisions": 3,
                                        "wait_s_total": 2400.0, "wait_s_max": 1800.0}
    # A blocked escalation is one stop (not two), ended by the answers; then the gate.
    assert st["r@1/review"]["owner"] == {"stops": 2, "questions": 1, "open": 0, "reasked": 0, "decisions": 2,
                                         "wait_s_total": 3900.0, "wait_s_max": 3600.0}
    assert st["r@1/loop"]["owner"]["stops"] == 1 and st["r@1/loop"]["owner"]["wait_s_total"] == 1200.0


def test_outcome_counts_first_try_acceptance_rejections_and_owner_edits(tmp_path: Path) -> None:
    st = _record(tmp_path)["steps"]
    assert st["r@1/draft"]["outcome"] == {"gate_first_try": 0, "gate_rejections": 1, "owner_edits": 1, "defects_late": 0}
    assert st["r@1/review"]["outcome"] == {"gate_first_try": 1, "gate_rejections": 0, "owner_edits": 0, "defects_late": 0}


def test_recipe_totals_and_means_per_run(tmp_path: Path) -> None:
    r = _record(tmp_path)["recipes"]["r@1"]
    assert r == {"runs": 2, "completed": 1, "abandoned": 1,
                 "cost_usd": {"total": 0.75, "mean": 0.375},
                 "owner_stops": {"total": 6, "mean": 3.0},
                 "owner_wait_s": {"total": 7500.0, "mean": 3750.0}}


def test_existing_keys_are_unchanged(tmp_path: Path) -> None:
    out = _record(tmp_path)
    assert set(out) == {"steps", "cases", "iterations", "reviews", "recipes"}  # cases: 2026-11-self-improvement
    d = out["steps"]["r@1/draft"]
    assert {k: d[k] for k in ("runs", "attempts", "passed", "rejected", "gate_failures", "timeouts", "escalations", "failure_classes")} == {
        "runs": 2, "attempts": 3, "passed": 1, "rejected": 0, "gate_failures": 0, "timeouts": 0, "escalations": {}, "failure_classes": {}}
    assert d["mean_duration_s"] == 60.0 and d["max_duration_s"] == 60.0
    assert out["iterations"] == {"r@1/loop": {"instances": 1, "mean": 3.0, "max": 3}}
