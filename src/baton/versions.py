"""Format versions and the published format schemas (§14.1, §15.3).

Regenerate the files under ``formats/`` with ``python -m baton.versions``;
a test fails if they drift from the models.
"""

from __future__ import annotations

import json
import sys
from functools import cache
from typing import Any

from . import data

RECIPE_FORMATS: tuple[str, ...] = ("baton-recipe/1",)
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


if __name__ == "__main__":
    write_published()
