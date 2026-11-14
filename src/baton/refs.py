"""The closed grammar of input references (§5.2).

Parsing is purely syntactic. Whether a reference is legal *where it appears*
(ancestry, group scope, declared artifacts) is checked by ``recipe.py``; what it
resolves to at run time is the packet builder's business.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEG = r"[A-Za-z0-9_-]+"
_PATH = rf"(?:\.({_SEG}(?:\.{_SEG})*))?"
_ID = r"[a-z][a-z0-9_]*"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("run_input", re.compile(rf"^run\.inputs\.({_SEG})$")),
    ("step_output", re.compile(rf"^steps\.({_ID})\.output{_PATH}$")),
    ("step_artifact", re.compile(rf"^steps\.({_ID})\.artifacts\.({_SEG})$")),
    ("group_outputs", re.compile(rf"^steps\.({_ID})\.outputs$")),
    ("item", re.compile(rf"^item{_PATH}$")),
    ("sibling_output", re.compile(rf"^group\.steps\.({_ID})\.output{_PATH}$")),
    ("sibling_artifact", re.compile(rf"^group\.steps\.({_ID})\.artifacts\.({_SEG})$")),
    ("previous_findings", re.compile(r"^group\.previous_iteration\.findings$")),
    ("static", re.compile(r"^static\.(.+)$")),
    ("human", re.compile(rf"^human\.({_SEG})$")),
    ("human_revision", re.compile(rf"^human_revision\.({_ID})\.({_SEG})$")),
    ("research", re.compile(r"^research\.findings$")),
    ("platform", re.compile(r"^platform\.facts$")),
    ("catalog", re.compile(r"^catalog\.summaries$")),
    ("project", re.compile(rf"^project\.({_ID})$")),
]

# Kinds that may only appear inside a group.
GROUP_ONLY = {"item", "sibling_output", "sibling_artifact", "previous_findings"}


@dataclass(frozen=True)
class Ref:
    kind: str
    raw: str
    step: str | None = None  # step id for steps.* / group.steps.* / human_revision.*
    name: str | None = None  # artifact name, run input key, decision id, static path
    path: tuple[str, ...] = field(default_factory=tuple)  # JSON path into an output or item


class RefSyntaxError(ValueError):
    pass


def parse(raw: str) -> Ref:
    for kind, pattern in _PATTERNS:
        m = pattern.match(raw)
        if not m:
            continue
        g = m.groups()
        if kind == "run_input":
            return Ref(kind, raw, name=g[0])
        if kind in ("step_output", "sibling_output"):
            return Ref(kind, raw, step=g[0], path=_split(g[1]))
        if kind in ("step_artifact", "sibling_artifact", "human_revision"):
            return Ref(kind, raw, step=g[0], name=g[1])
        if kind == "group_outputs":
            return Ref(kind, raw, step=g[0])
        if kind == "item":
            return Ref(kind, raw, path=_split(g[0]))
        if kind in ("static", "human", "project"):
            return Ref(kind, raw, name=g[0])
        return Ref(kind, raw)
    raise RefSyntaxError(f"{raw!r} is not a valid reference (see §5.2 for the grammar)")


def _split(path: str | None) -> tuple[str, ...]:
    return tuple(path.split(".")) if path else ()


# repeat_until: one or more "group.steps.<id>.gates.passed" joined by " and ".
_COND = re.compile(rf"^group\.steps\.({_ID})\.gates\.passed$")


def parse_condition(raw: str) -> list[str]:
    """Return the step ids a ``repeat_until`` condition depends on."""
    ids = []
    for part in raw.split(" and "):
        m = _COND.match(part.strip())
        if not m:
            raise RefSyntaxError(
                f"{raw!r} is not a valid repeat_until condition; expected "
                "'group.steps.<id>.gates.passed' (optionally joined with ' and ')"
            )
        ids.append(m.group(1))
    return ids
