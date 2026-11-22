"""Open questions: what a worker asked the owner to confirm without stopping (§7.2, §13.8; Decision 0184).

A ``completed`` result may carry ``questions_for_human``: choices it made on a guess. Intake records them on
``result_submitted`` as ``questions``. A step's open questions are those of its latest accepted completed result,
every iteration of its group counting as one step, less those the owner answered for that step anywhere in the run.
Nothing waits for them: they are listed, offered and answered, never a pending decision.
"""

from __future__ import annotations

from typing import Any

from . import groups
from .models import recorded_questions


def step_key(recipe: Any, step_path: str) -> str:
    """``step_path`` with the iteration of each enclosing group replaced by ``i*``: the same step in any round."""
    from .packet import _iteration_free

    loc = groups.locate(recipe, step_path)
    depth = len(loc.frames) if loc is not None else 0
    return _iteration_free(step_path, depth)[0]


def answered_ids(recipe: Any, events: list[Any]) -> dict[str, set[str]]:
    """Per step key, the ids of every question the owner answered for that step (any iteration, any attempt)."""
    out: dict[str, set[str]] = {}
    for ev in events:
        if ev.type == "human_decision" and ev.data.get("kind") == "answers" and ev.step_path:
            ids = {a.get("id") for a in ev.data.get("answers") or [] if isinstance(a, dict)}
            out.setdefault(step_key(recipe, ev.step_path), set()).update(i for i in ids if isinstance(i, str))
    return out


def open_questions(recipe: Any, events: list[Any]) -> list[dict[str, Any]]:
    """``[{step_path, attempt, seq, questions}]``: each step's open questions, oldest asking step first.

    ``step_path`` and ``attempt`` are the asking result's (the latest accepted completed result of the step, in any
    iteration); ``seq`` is its ``result_submitted``. A result that intake rejected asks nothing.
    """
    rejected = {(ev.step_path, ev.attempt) for ev in events if ev.type == "result_rejected"}
    latest: dict[str, tuple[str, int, int, list[dict[str, Any]]]] = {}
    for ev in events:
        if ev.type != "result_submitted" or ev.data.get("status") != "completed" or not ev.step_path:
            continue
        if (ev.step_path, ev.attempt) in rejected:
            continue
        latest[step_key(recipe, ev.step_path)] = (ev.step_path, ev.attempt, ev.seq, recorded_questions(ev.data.get("questions") or []))
    answered = answered_ids(recipe, events)
    out = []
    for key, (path, attempt, seq, qs) in latest.items():
        left = [q for q in qs if q["id"] not in answered.get(key, set())]
        if left:
            out.append({"step_path": path, "attempt": attempt, "seq": seq, "questions": left})
    return sorted(out, key=lambda o: o["seq"])
