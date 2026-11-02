"""The Director API (§13.1), shared by the CLI and (later) the MCP server."""

from __future__ import annotations

from pathlib import Path

from .models import Plan
from .recipe import build_plan, load_recipe


def plan(recipe: str | Path, level: str | None = None) -> Plan:
    """Per-level step and gate table for a recipe directory. Raises ``RecipeError``."""
    return build_plan(load_recipe(recipe), level=level)
