"""The one state machine (§8.1).

Pure and deterministic: no I/O, no clock. ``RunState.apply`` folds one event
into the state of a run or raises ``IllegalTransition`` and leaves the state
unchanged. The store applies every event here before writing it, so a log can
only ever hold legal sequences; replaying a log through the same function
rebuilds the state exactly (§8.3).

Rules encoded here:

* Each state transition is exactly one event (``TRANSITIONS``). Some step
  events record facts without moving the step but are only legal in certain
  states (``RECORDS``). Events in neither table are not state-bound.
* A step with no events is ``blocked_on_deps``; a new run needs no per-step
  events.
* Attempt numbers are ordinal (§5.8). ``worker_selected``, ``packet_built``
  and ``dispatched`` carry the *next* attempt (current + 1); events about the
  attempt in flight carry the *current* one.
* A retry (back to ``ready`` from ``verifying``, ``timed_out`` or
  ``orphaned``) is refused once the step has used ``max_attempts`` attempts
  since it last became ready by another route (first readiness, an owner
  decision after escalation, re-run of a stale step, revision). The limit
  comes from ``run_started.data.max_attempts``; absent means unbounded.
* Run-level: ``run_started`` opens the log exactly once and must be first;
  ``run_completed`` / ``run_abandoned`` end it, after which no step event is
  accepted. Bookkeeping events (leases, checkpoints, records) remain legal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

STEP_STATES: tuple[str, ...] = (
    "blocked_on_deps",
    "ready",
    "dispatched",
    "running",
    "submitted",
    "verifying",
    "awaiting_human",
    "passed",
    "timed_out",
    "orphaned",
    "escalated",
    "abandoned",
    "skipped",
    "imported",
    "superseded",
    "stale",
)
INITIAL_STEP_STATE = "blocked_on_deps"

#: States that satisfy ``depends_on`` (§8.1). ``stale`` and ``superseded`` do not.
SATISFIES_DEPS = frozenset({"passed", "skipped", "imported"})

#: States in which an attempt is in flight or just ended; attempt-scoped events
#: arriving here must carry the current attempt number.
ATTEMPT_STATES = frozenset(
    {"dispatched", "running", "submitted", "verifying", "awaiting_human", "timed_out", "orphaned"}
)

RUN_STATES: tuple[str, ...] = ("active", "completed", "abandoned")

# ---------------------------------------------------------------------------
# Transition tables
# ---------------------------------------------------------------------------

_RETRY_FROM = frozenset({"verifying", "timed_out", "orphaned"})

#: event type -> {from state: to state}
TRANSITIONS: Mapping[str, Mapping[str, str]] = {
    "step_ready": {
        "blocked_on_deps": "ready",
        "verifying": "ready",  # retry after a failed gate or rejected result
        "timed_out": "ready",  # retry after classification
        "orphaned": "ready",
        "escalated": "ready",  # after an owner decision
        "stale": "ready",  # re-run
        "superseded": "ready",  # after step_revised: the new attempt
    },
    "dispatched": {"ready": "dispatched"},
    "step_running": {"dispatched": "running"},
    "result_submitted": {"running": "submitted"},
    "verification_started": {"submitted": "verifying", "escalated": "verifying"},  # escalated: a waiver of the failed gate (§9.3)
    "human_gate_opened": {"verifying": "awaiting_human"},
    "gate_passed": {"awaiting_human": "verifying"},  # the human gate's outcome
    "gate_failed": {"awaiting_human": "verifying"},
    "step_passed": {"verifying": "passed", "stale": "passed"},  # stale: confirmed by decision
    "step_timed_out": {"running": "timed_out"},
    "attempt_orphaned": {"dispatched": "orphaned", "running": "orphaned"},
    "step_escalated": {
        "ready": "escalated",  # no eligible worker (§8.4)
        "verifying": "escalated",
        "timed_out": "escalated",
        "orphaned": "escalated",
    },
    "step_abandoned": {"escalated": "abandoned"},
    "step_skipped": {"blocked_on_deps": "skipped"},
    "step_unskipped": {"skipped": "blocked_on_deps"},  # approved re-triage
    "step_imported": {"blocked_on_deps": "imported"},
    "step_revised": {"passed": "superseded", "imported": "superseded"},
    "step_stale": {"passed": "stale", "imported": "stale"},
}

#: event type -> states in which it is recorded without moving the step.
RECORDS: Mapping[str, frozenset[str]] = {
    "worker_selected": frozenset({"ready"}),
    "packet_built": frozenset({"ready"}),
    "result_rejected": frozenset({"verifying"}),
    "gate_passed": frozenset({"verifying"}),
    "gate_failed": frozenset({"verifying"}),
    "findings_recorded": frozenset({"verifying"}),
    "protected_path_modified": frozenset({"verifying"}),
    "failure_classified": frozenset({"verifying", "timed_out", "orphaned", "escalated"}),
    "deadline_extended": frozenset({"running"}),  # an overdue worker got one more band (§8.7)
}

#: Events that carry the next attempt number (current + 1).
ATTEMPT_NEXT = frozenset({"worker_selected", "packet_built", "dispatched"})
#: Events that, in an attempt state, must carry the current attempt number.
ATTEMPT_CURRENT = frozenset(
    {
        "step_running",
        "result_submitted",
        "verification_started",
        "human_gate_opened",
        "result_rejected",
        "gate_passed",
        "gate_failed",
        "findings_recorded",
        "protected_path_modified",
        "step_passed",
        "step_timed_out",
        "attempt_orphaned",
        "failure_classified",
        "step_escalated",
        "deadline_extended",
    }
)

#: Step events that require a ``step_path``.
STEP_BOUND = frozenset(TRANSITIONS) | frozenset(RECORDS)

RUN_TRANSITIONS: Mapping[str, Mapping[str | None, str]] = {
    "run_started": {None: "active"},
    "run_completed": {"active": "completed"},
    "run_abandoned": {"active": "abandoned"},
}

_STEP_PATH = re.compile(r"^[a-z][a-z0-9_]*(?:/[A-Za-z0-9_-]+)*(?:~review(?:\.[0-9]+)?)?$")


class IllegalTransition(ValueError):
    """An event that the state machine does not allow from the current state."""

    def __init__(self, message: str, *, code: str = "state.illegal_transition"):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepState:
    state: str = INITIAL_STEP_STATE
    attempt: int = 0  # attempts dispatched so far; the current attempt when one is in flight
    budget_base: int = 0  # attempt count when the current retry budget started
    last_seq: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "attempt": self.attempt, "budget_base": self.budget_base, "last_seq": self.last_seq}


@dataclass
class RunState:
    run_id: str
    state: str | None = None  # None until run_started
    max_attempts: int | None = None
    last_seq: int = 0
    last_sha256: str | None = None
    steps: dict[str, StepState] = field(default_factory=dict)

    def step(self, path: str) -> StepState:
        return self.steps.get(path, StepState())

    def apply(self, event: Mapping[str, Any]) -> None:
        """Fold one event (a mapping with the §8.2 envelope fields) or raise.

        On error nothing changes.
        """
        etype = event["type"]
        path = event.get("step_path")
        attempt = event.get("attempt")
        seq = event.get("seq", self.last_seq + 1)

        if etype in RUN_TRANSITIONS:
            table = RUN_TRANSITIONS[etype]
            if self.state not in table:
                raise IllegalTransition(f"{etype} not allowed when run is {self.state or 'not started'}")
            new_run_state = table[self.state]
        else:
            if self.state is None:
                raise IllegalTransition(f"{etype} before run_started", code="state.not_started")
            new_run_state = self.state

        new_step: StepState | None = None
        if etype in STEP_BOUND:
            if not path:
                raise IllegalTransition(f"{etype} needs a step_path", code="state.missing_step_path")
            if self.state != "active":
                raise IllegalTransition(f"{etype} on {path}: run is {self.state}", code="state.run_closed")
            new_step = next_step_state(self.step(path), etype, attempt, self.max_attempts)
        if path is not None and not _STEP_PATH.match(path):
            raise IllegalTransition(f"malformed step_path {path!r}", code="state.bad_step_path")

        # Commit.
        if etype == "run_started":
            max_attempts = (event.get("data") or {}).get("max_attempts")
            if max_attempts is not None and (not isinstance(max_attempts, int) or max_attempts < 1):
                raise IllegalTransition(f"run_started.data.max_attempts must be a positive integer, got {max_attempts!r}")
            self.max_attempts = max_attempts
        self.state = new_run_state
        if new_step is not None:
            self.steps[path] = replace(new_step, last_seq=seq)
        self.last_seq = seq
        self.last_sha256 = event.get("sha256")


def next_step_state(current: StepState, etype: str, attempt: int | None, max_attempts: int | None) -> StepState:
    """The step state after ``etype``, or raise ``IllegalTransition``."""
    frm = current.state
    to: str | None = TRANSITIONS.get(etype, {}).get(frm)
    if to is None:
        if frm in RECORDS.get(etype, ()):
            to = frm
        else:
            raise IllegalTransition(f"{etype} not allowed from {frm}")

    # Attempt numbering.
    n = current.attempt
    if etype == "verification_started" and frm == "escalated" and (n == 0 or attempt != n):
        # A waiver resumes the verification of the attempt the step holds (§9.3).
        raise IllegalTransition(f"verification_started from escalated must carry the held attempt {n}" if n else "verification_started from escalated needs an attempt", code="state.bad_attempt")
    if etype in ATTEMPT_NEXT:
        if attempt != n + 1:
            raise IllegalTransition(f"{etype} must carry attempt {n + 1}, got {attempt}", code="state.bad_attempt")
    elif etype in ATTEMPT_CURRENT and frm in ATTEMPT_STATES:
        if attempt != n:
            raise IllegalTransition(f"{etype} must carry attempt {n}, got {attempt}", code="state.bad_attempt")
    elif attempt is not None and attempt != n:
        raise IllegalTransition(f"{etype} carries attempt {attempt}, but the step is at {n}", code="state.bad_attempt")

    new = replace(current, state=to)
    if etype == "dispatched":
        new = replace(new, attempt=n + 1)
    elif etype == "step_ready":
        if frm in _RETRY_FROM:
            if max_attempts is not None and n - current.budget_base >= max_attempts:
                raise IllegalTransition(
                    f"retry refused: {n - current.budget_base} of {max_attempts} attempts used",
                    code="state.attempts_exhausted",
                )
        else:
            new = replace(new, budget_base=n)
    return new


def allowed_events(current: StepState) -> list[str]:
    """Step event types legal from this state (ignoring the attempt budget)."""
    return sorted(
        t for t in STEP_BOUND if current.state in TRANSITIONS.get(t, {}) or current.state in RECORDS.get(t, ())
    )


def attempt_for(current: StepState, etype: str) -> int | None:
    """The attempt number an event of ``etype`` must carry from ``current``."""
    if etype in ATTEMPT_NEXT:
        return current.attempt + 1
    if etype in ATTEMPT_CURRENT and current.state in ATTEMPT_STATES:
        return current.attempt
    if etype == "verification_started" and current.state == "escalated":
        return current.attempt  # a waiver resumes the held attempt (§9.3)
    return None
