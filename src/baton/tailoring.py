"""Complexity ratings on a recipe's axes (§5.5; Decisions 0144, 0147).

A recipe declares either ``complexity.levels`` (one scale) or
``complexity.axes`` (several). Internally both are axes: a recipe with
``levels`` has one axis named ``level``, so one code path applies either.
A run's *ratings* map each axis to its value; ``applies_to`` on a step or
gate is a list of levels (one-axis form) or a map from axis to values, and
it applies when **any** listed axis's rating is among its values (OR).

The one-axis form keeps its event and output shapes (``level``) so its
records, packets and hashes are unchanged; the axes form records
``ratings``.
"""

from __future__ import annotations

import itertools
from typing import Any, Iterator, Mapping

LEVEL_AXIS = "level"


def scales(cx: Any) -> dict[str, list[str]]:
    """Each axis with its ordered scale; ``{}`` without a complexity block."""
    if cx is None:
        return {}
    if cx.axes is None:
        return {LEVEL_AXIS: list(cx.levels or [])}
    return {name: list(spec if isinstance(spec, list) else spec.scale) for name, spec in cx.axes.items()}


def is_multi(cx: Any) -> bool:
    """True for the axes form (``complexity.axes``), whatever its number of axes."""
    return cx is not None and cx.axes is not None


def confirm_lowest(cx: Any, axis: str) -> bool:
    if not is_multi(cx):
        return False
    spec = cx.axes.get(axis)
    return bool(getattr(spec, "confirm_lowest", False))


def lowest(cx: Any) -> dict[str, str]:
    return {a: s[0] for a, s in scales(cx).items() if s}


def conditions(applies_to: Any) -> dict[str, list[str]] | None:
    """``applies_to`` as a map from axis to values (a list is the ``level`` axis)."""
    if applies_to is None:
        return None
    if isinstance(applies_to, Mapping):
        return {a: list(v) for a, v in applies_to.items()}
    return {LEVEL_AXIS: list(applies_to)}


def applies(applies_to: Any, ratings: Mapping[str, str] | None) -> bool:
    """Whether a node or gate applies at these ratings (OR across and within axes).

    Before the ratings are set (``None``), everything applies.
    """
    cond = conditions(applies_to)
    if cond is None or ratings is None:
        return True
    return any(ratings.get(axis) in values for axis, values in cond.items())


def combinations(cx: Any) -> Iterator[dict[str, str]]:
    """Every combination of ratings the recipe can be given."""
    sc = scales(cx)
    names = list(sc)
    for values in itertools.product(*(sc[n] for n in names)):
        yield dict(zip(names, values))


def auto_approves(cx: Any, ratings: Mapping[str, str]) -> bool:
    """All axes at their lowest, and none of them asks to confirm its lowest (0147 #2)."""
    sc = scales(cx)
    return all(ratings.get(a) == s[0] and not confirm_lowest(cx, a) for a, s in sc.items())


def from_event(data: Mapping[str, Any]) -> dict[str, str] | None:
    """The ratings an event records: ``ratings`` (axes form) or ``level`` (one axis)."""
    if isinstance(data.get("ratings"), Mapping):
        return dict(data["ratings"])
    if "level" in data and data["level"] is not None:
        return {LEVEL_AXIS: data["level"]}
    return None


def as_data(cx: Any, ratings: Mapping[str, str]) -> dict[str, Any]:
    """The event fields for ratings: ``level`` in the one-axis form, else ``ratings``."""
    if is_multi(cx):
        return {"ratings": dict(ratings)}
    return {"level": ratings.get(LEVEL_AXIS)}


def from_output(cx: Any, out: Mapping[str, Any]) -> tuple[dict[str, str], Any]:
    """``(ratings, reasons)`` from a triage output.

    One axis: ``level`` and the optional ``reasons`` list. Axes form:
    ``ratings {axis: {value, reason}}``; reasons by axis.
    """
    if not is_multi(cx):
        return {LEVEL_AXIS: out.get("level")}, out.get("reasons")
    raw = out.get("ratings") or {}
    ratings = {a: (raw.get(a) or {}).get("value") for a in scales(cx)}
    reasons = {a: (raw.get(a) or {}).get("reason") for a in scales(cx)}
    return ratings, reasons


def describe(ratings: Mapping[str, str] | None) -> str:
    """``discovery low, assurance high`` (or the bare level for one axis)."""
    if not ratings:
        return ""
    if list(ratings) == [LEVEL_AXIS]:
        return str(ratings[LEVEL_AXIS])
    return ", ".join(f"{a} {v}" for a, v in ratings.items())


def describe_conditions(applies_to: Any) -> str:
    """``assurance: high; discovery: medium, high`` (or ``standard, major`` for one axis)."""
    cond = conditions(applies_to) or {}
    if list(cond) == [LEVEL_AXIS]:
        return ", ".join(cond[LEVEL_AXIS])
    return "; ".join(f"{a}: {', '.join(v)}" for a, v in cond.items())


# Ratings no axis takes: only what has no ``applies_to`` applies (the plan's "always" view).
NEVER: dict[str, str] = {"\0": "\0"}
