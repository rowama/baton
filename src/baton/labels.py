"""Plain-language labels for the owner's decision options (§13.8).

Every pending decision in ``status`` and ``board`` lists its ``options`` as
``[{decision, label, effect}]`` (plus ``command`` where the decision is made by
another command, and ``next`` where the record decides what the option triggers,
added by the API: framing's options, §11.6). Labels come from ``defaults/labels.yaml``; a recipe may give
its own for a human gate (``labels: {approve: "...", reject: "..."}``). The
runtime never shows the owner anything itself: labels are material for the
Director's conversation.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from . import data

FORMAT = "baton-labels/1"


@lru_cache(maxsize=1)
def defaults() -> dict[str, dict[str, dict[str, str]]]:
    raw = data.load_yaml(data.path("defaults") / "labels.yaml")
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ValueError(f"defaults/labels.yaml must declare format {FORMAT}")
    return {k: v for k, v in raw.items() if k != "format"}


def option(kind: str, decision: str, *, label: str | None = None, command: str | None = None) -> dict[str, Any]:
    """One option: the decision name, its label and effect (a recipe's ``label`` overrides the default)."""
    entry = defaults().get(kind, {}).get(decision) or {}
    out: dict[str, Any] = {
        "decision": decision,
        "label": label or entry.get("label") or decision,
        "effect": entry.get("effect", ""),
    }
    if command:
        out["command"] = command
    return out


def options(kind: str, decisions: list[str] | tuple[str, ...], overrides: dict[str, str] | None = None) -> list[dict[str, Any]]:
    over = overrides or {}
    return [option(kind, d, label=over.get(d)) for d in decisions]


def decision_names(opts: list[Any]) -> list[str]:
    """The decision names of an options list (either form)."""
    return [o["decision"] if isinstance(o, dict) else str(o) for o in opts]
