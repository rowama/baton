from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOFTWARE_FEATURE = ROOT / "tests" / "fixtures" / "recipes" / "software-feature"
FIT_CHECK = ROOT / "examples" / "recipes" / "fit-check"


def step(recipe: dict, path: str) -> dict:
    """Find a step dict by 'id' or 'group/id'."""
    nodes = recipe["steps"]
    found: dict = {}
    for part in path.split("/"):
        found = next(n for n in nodes if n["id"] == part)
        nodes = found.get("steps", [])
    return found


@pytest.fixture
def make_recipe(tmp_path: Path) -> Callable[..., Path]:
    """Copy a fixture recipe into tmp_path and apply edits to its YAML and files."""

    def make(edit: Callable[[dict, Path], None] | None = None, *, source: Path = SOFTWARE_FEATURE, text: Callable[[str], str] | None = None) -> Path:
        dest = tmp_path / source.name
        shutil.copytree(source, dest)
        rf = dest / "recipe.yaml"
        if text is not None:
            rf.write_text(text(rf.read_text(encoding="utf-8")), encoding="utf-8")
        if edit is not None:
            data = yaml.safe_load(rf.read_text(encoding="utf-8"))
            edit(data, dest)
            rf.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return dest

    return make
