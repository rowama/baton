"""The state machine (§8.1): every legal edge passes, every illegal one raises."""

from __future__ import annotations

from collections import deque

import pytest

from baton import state as sm
from baton.models import EVENT_TYPES
from baton.state import IllegalTransition, RunState, StepState

P = "design"


def started(max_attempts: int | None = None) -> RunState:
    rs = RunState("r_test")
    rs.apply({"type": "run_started", "data": {} if max_attempts is None else {"max_attempts": max_attempts}})
    return rs


def ev(rs: RunState, etype: str, path: str = P) -> dict:
    return {"type": etype, "step_path": path, "attempt": sm.attempt_for(rs.step(path), etype)}


def _paths_to_every_state() -> dict[str, list[str]]:
    """Shortest legal event sequence from a fresh step to each state (BFS)."""
    found: dict[str, list[str]] = {sm.INITIAL_STEP_STATE: []}
    queue = deque([[]])
    while queue:
        seq = queue.popleft()
        rs = drive(seq)
        for etype in sm.allowed_events(rs.step(P)):
            nxt = seq + [etype]
            to = drive(nxt).step(P).state
            if to not in found:
                found[to] = nxt
                queue.append(nxt)
    return found


def drive(seq: list[str], rs: RunState | None = None) -> RunState:
    rs = rs or started()
    for etype in seq:
        rs.apply(ev(rs, etype))
    return rs


PATHS = _paths_to_every_state()


def test_every_state_is_reachable():
    assert set(PATHS) == set(sm.STEP_STATES)


def test_tables_use_known_states_and_event_types():
    for etype, edges in sm.TRANSITIONS.items():
        assert etype in EVENT_TYPES
        assert set(edges) | set(edges.values()) <= set(sm.STEP_STATES)
    for etype, states in sm.RECORDS.items():
        assert etype in EVENT_TYPES
        assert states <= set(sm.STEP_STATES)


LEGAL_EDGES = [(etype, frm, to) for etype, edges in sm.TRANSITIONS.items() for frm, to in edges.items()]


@pytest.mark.parametrize("etype,frm,to", LEGAL_EDGES, ids=[f"{f}-{e}-{t}" for e, f, t in LEGAL_EDGES])
def test_legal_transition(etype, frm, to):
    rs = drive(PATHS[frm])
    assert rs.step(P).state == frm
    rs.apply(ev(rs, etype))
    assert rs.step(P).state == to


LEGAL_RECORDS = [(etype, s) for etype, states in sm.RECORDS.items() for s in sorted(states)]


@pytest.mark.parametrize("etype,frm", LEGAL_RECORDS, ids=[f"{s}-{e}" for e, s in LEGAL_RECORDS])
def test_record_events_keep_state(etype, frm):
    rs = drive(PATHS[frm])
    rs.apply(ev(rs, etype))
    assert rs.step(P).state == frm


ILLEGAL = [
    (etype, s)
    for etype in sorted(sm.STEP_BOUND)
    for s in sm.STEP_STATES
    if s not in sm.TRANSITIONS.get(etype, {}) and s not in sm.RECORDS.get(etype, ())
]


@pytest.mark.parametrize("etype,frm", ILLEGAL, ids=[f"{s}-{e}" for e, s in ILLEGAL])
def test_illegal_transition_raises_and_changes_nothing(etype, frm):
    rs = drive(PATHS[frm])
    before = rs.step(P)
    seq = rs.last_seq
    with pytest.raises(IllegalTransition):
        rs.apply(ev(rs, etype))
    assert rs.step(P) == before and rs.last_seq == seq


def test_happy_path_and_attempt_numbers():
    rs = drive(["step_ready", "worker_selected", "packet_built", "dispatched", "step_running",
                "result_submitted", "verification_started", "gate_passed", "step_passed"])
    assert rs.step(P) == StepState(state="passed", attempt=1, budget_base=0, last_seq=rs.last_seq)


def test_dispatch_must_carry_next_attempt():
    rs = drive(["step_ready"])
    with pytest.raises(IllegalTransition) as e:
        rs.apply({"type": "dispatched", "step_path": P, "attempt": 2})
    assert e.value.code == "state.bad_attempt"
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "dispatched", "step_path": P, "attempt": None})


def test_in_flight_events_must_carry_current_attempt():
    rs = drive(["step_ready", "dispatched"])
    with pytest.raises(IllegalTransition) as e:
        rs.apply({"type": "step_running", "step_path": P, "attempt": 2})
    assert e.value.code == "state.bad_attempt"
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "step_running", "step_path": P})


def test_attempts_are_never_reused():
    retry = ["dispatched", "step_running", "result_submitted", "verification_started", "gate_failed", "step_ready"]
    rs = drive(["step_ready"] + retry * 2 + ["dispatched"])
    assert rs.step(P).attempt == 3


def _fail_once() -> list[str]:
    return ["dispatched", "step_running", "result_submitted", "verification_started", "gate_failed"]


def test_retry_refused_when_attempts_exhausted():
    rs = drive(["step_ready"] + (_fail_once() + ["step_ready"]) * 2 + _fail_once(), started(max_attempts=3))
    assert rs.step(P).attempt == 3
    with pytest.raises(IllegalTransition) as e:
        rs.apply(ev(rs, "step_ready"))
    assert e.value.code == "state.attempts_exhausted"
    rs.apply(ev(rs, "step_escalated"))  # the legal way out


def test_owner_decision_after_escalation_gives_a_fresh_budget():
    rs = drive(["step_ready"] + _fail_once() + ["step_escalated", "step_ready"] + _fail_once(), started(max_attempts=1))
    with pytest.raises(IllegalTransition):
        rs.apply(ev(rs, "step_ready"))  # 1 attempt since the decision
    assert rs.step(P).attempt == 2


def test_timeouts_and_orphans_count_against_the_budget():
    rs = drive(["step_ready", "dispatched", "step_running", "step_timed_out"], started(max_attempts=1))
    with pytest.raises(IllegalTransition):
        rs.apply(ev(rs, "step_ready"))
    rs = drive(["step_ready", "dispatched", "attempt_orphaned"], started(max_attempts=2))
    rs.apply(ev(rs, "step_ready"))


def test_human_gate_round_trip():
    rs = drive(["step_ready", "dispatched", "step_running", "result_submitted", "verification_started",
                "gate_passed", "human_gate_opened"])
    assert rs.step(P).state == "awaiting_human"
    rs.apply(ev(rs, "gate_passed"))  # the owner's approval recorded as the gate's outcome
    assert rs.step(P).state == "verifying"


def test_revise_goes_through_superseded_to_a_new_attempt():
    rs = drive(["step_ready", "dispatched", "step_running", "result_submitted", "verification_started",
                "step_passed", "step_revised"])
    assert rs.step(P).state == "superseded"
    rs.apply(ev(rs, "step_ready"))
    rs.apply(ev(rs, "dispatched"))
    assert rs.step(P).attempt == 2


def test_deps_satisfied_only_by_passed_skipped_imported():
    assert sm.SATISFIES_DEPS == {"passed", "skipped", "imported"}


def test_steps_are_independent():
    rs = drive(["step_ready", "dispatched"])
    rs.apply({"type": "step_skipped", "step_path": "requirements"})
    assert rs.step(P).state == "dispatched" and rs.step("requirements").state == "skipped"


def test_group_step_paths_accepted():
    rs = started()
    rs.apply({"type": "step_ready", "step_path": "slices/x7f3a9c2/i1/implement"})
    assert rs.step("slices/x7f3a9c2/i1/implement").state == "ready"


@pytest.mark.parametrize("bad", ["", "Design", "a//b", "a/b c", "../x"])
def test_malformed_step_path(bad):
    rs = started()
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "step_ready", "step_path": bad})
    assert rs.steps == {}


# -- run level ----------------------------------------------------------------


def test_run_must_start_first_and_once():
    rs = RunState("r")
    with pytest.raises(IllegalTransition) as e:
        rs.apply({"type": "step_ready", "step_path": P})
    assert e.value.code == "state.not_started"
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "lease_claimed"})
    rs.apply({"type": "run_started"})
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "run_started"})


@pytest.mark.parametrize("end", ["run_completed", "run_abandoned"])
def test_closed_run_refuses_step_events_but_keeps_bookkeeping(end):
    rs = started()
    rs.apply({"type": end})
    with pytest.raises(IllegalTransition) as e:
        rs.apply({"type": "step_ready", "step_path": P})
    assert e.value.code == "state.run_closed"
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "run_completed"})
    rs.apply({"type": "lease_released"})
    rs.apply({"type": "checkpoint_committed"})


def test_step_bound_event_needs_path():
    with pytest.raises(IllegalTransition) as e:
        started().apply({"type": "step_ready"})
    assert e.value.code == "state.missing_step_path"


@pytest.mark.parametrize("bad", [0, -1, "3", 1.5])
def test_max_attempts_must_be_positive_int(bad):
    with pytest.raises(IllegalTransition):
        RunState("r").apply({"type": "run_started", "data": {"max_attempts": bad}})
