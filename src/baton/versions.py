"""Format versions, the lockfile and the published format schemas (§14.1, §15.3).

Regenerate the files under ``formats/`` with ``python -m baton.versions``;
a test fails if they drift from the models.

**Lockfile** (``.baton/baton.lock``, JSON): the runtime version, the format
and vocabulary versions in use, and for every vendored recipe version its
package hash and per-step signatures (§5.8). Entries for older recipe
versions are kept, so later vendoring can compare against every version the
project has used (Phase 15).
"""

from __future__ import annotations

import json
import sys
from functools import cache
from typing import Any

from . import data

RECIPE_FORMATS: tuple[str, ...] = ("baton-recipe/1",)
LOCK_FORMAT = "baton-lock/1"
FINDINGS_FORMAT = "baton-findings/1"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


def _with_header(schema: dict[str, Any], title: str) -> dict[str, Any]:
    return {"$schema": DRAFT_2020_12, "title": title, **{k: v for k, v in schema.items() if k != "title"}}


def recipe_json_schema() -> dict[str, Any]:
    from .models import Recipe

    return _with_header(Recipe.model_json_schema(by_alias=True), RECIPE_FORMATS[-1])


@cache
def findings_json_schema() -> dict[str, Any]:
    """The runtime-owned ``baton:findings`` schema (§9.2)."""
    from .models import Findings

    return _with_header(Findings.model_json_schema(by_alias=True), FINDINGS_FORMAT)


def published_schemas() -> dict[str, dict[str, Any]]:
    """File name under ``formats/`` -> schema."""
    return {
        "baton-recipe-1.schema.json": recipe_json_schema(),
        "baton-findings-1.schema.json": findings_json_schema(),
    }


def dump(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_published() -> None:
    out = data.path("formats")
    out.mkdir(exist_ok=True)
    for name, schema in published_schemas().items():
        (out / name).write_text(dump(schema), encoding="utf-8", newline="\n")
        print(out / name, file=sys.stderr)


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------


def new_lock() -> dict[str, Any]:
    from . import __version__
    from .models import EVENTS_FORMATS
    from .packet import PROTOCOL
    from .vocab import DEFAULT

    return {
        "format": LOCK_FORMAT,
        "runtime": __version__,
        "formats": {"events": EVENTS_FORMATS[-1], "packet": PROTOCOL, "recipe": RECIPE_FORMATS[-1]},
        "vocab": [DEFAULT],
        "recipes": {},
    }


def dump_lock(lock: dict[str, Any]) -> str:
    return json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def step_signatures(loaded: Any) -> dict[str, dict[str, Any]]:
    """Per step id: kind, enclosing group, output schema hash, required capabilities (§5.8)."""
    import hashlib

    from .models import Group

    out: dict[str, dict[str, Any]] = {}

    def schema_hash(ref: str | None) -> str | None:
        if ref is None:
            return None
        if ref.startswith("baton:"):
            return ref
        return hashlib.sha256((loaded.root / ref).read_bytes()).hexdigest()

    def visit(nodes: list, group: str | None) -> None:
        for n in nodes:
            if isinstance(n, Group):
                out[n.id] = {"kind": "group", "group": group, "output_schema_sha256": None, "capabilities": []}
                visit(n.steps, n.id)
            else:
                out[n.id] = {
                    "kind": "step",
                    "group": group,
                    "output_schema_sha256": schema_hash(n.output_schema),
                    "capabilities": sorted(n.requires.capabilities),
                }

    visit(loaded.recipe.steps, None)
    return out


if __name__ == "__main__":
    write_published()
