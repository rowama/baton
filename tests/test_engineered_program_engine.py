"""2026-11-builder-engineered-tools Slice 3: the engine support the build loop needs (§5.3, §9; Decision 0164).

A step in a group may be independent of a top-level step its group depends on (the worker that placed
the examples never builds the program), and a script gate inside a `foreach` instance may name the
instance's item (`--program {{ item.program }}`), only with text a shell cannot read as syntax.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest

from baton.intake import _safe_item, render_command
from baton.recipe import validate_recipe

from conftest import ROOT

BUILDER = ROOT / "examples" / "recipes" / "recipe-builder"


def _copy(tmp_path: Path, old: str, new: str) -> Path:
    root = tmp_path / "rb"
    shutil.copytree(BUILDER, root, ignore=shutil.ignore_patterns("__pycache__"))
    y = root / "recipe.yaml"
    text = y.read_text(encoding="utf-8")
    assert old in text
    y.write_text(text.replace(old, new), encoding="utf-8")
    return root


@pytest.mark.not_slow("loads a recipe")
def test_a_group_step_may_be_independent_of_a_top_level_step_its_group_depends_on(tmp_path):
    loaded, issues = validate_recipe(BUILDER)
    assert loaded is not None and not [i for i in issues if i.severity == "error"]
    implement = next(s for s in next(g for g in loaded.recipe.steps if g.id == "build_programs").steps if s.id == "implement")
    assert implement.independence.from_step == "examples"
    # `guide` is a top-level step, but not one the group depends on.
    root = _copy(tmp_path, "independence: { from_step: examples, level: different_vendor }",
                 "independence: { from_step: guide, level: different_vendor }")
    _loaded, issues = validate_recipe(root)
    assert [(i.code, i.where) for i in issues if i.severity == "error"] == [("independence.bad_from_step", "build_programs/implement.independence")]
    assert "or a top-level ancestor of its group" in next(i.message for i in issues if i.code == "independence.bad_from_step")


def _ctx(item=None):
    view = SimpleNamespace(item_value=lambda loc: item)
    record = SimpleNamespace(started={"slug": "flower-bed"})
    return SimpleNamespace(project={"paths": {}}, run_id="r_1", record=lambda: record, recipe=None), view


@pytest.mark.not_slow("renders a template")
def test_a_gate_command_names_the_instances_item(monkeypatch):
    from baton import groups, packet

    ctx, view = _ctx({"program": "count_plants", "title": "Count the plants"})
    monkeypatch.setattr(groups, "locate", lambda recipe, path: SimpleNamespace(frame=object()))
    monkeypatch.setattr(packet, "view_of", lambda c: view)
    cmd = "baton programs test recipes/drafts/{{ run.slug }} --program {{ item.program }} --repeat 2"
    assert render_command(ctx, cmd, "build_programs/x1/i1/implement") == "baton programs test recipes/drafts/flower-bed --program count_plants --repeat 2"
    with pytest.raises(jinja2.TemplateError, match="not safe in a command"):
        render_command(ctx, "echo {{ item.title }}", "build_programs/x1/i1/implement")  # a space
    # Outside a group, `item` is undefined, as before.
    monkeypatch.setattr(groups, "locate", lambda recipe, path: SimpleNamespace(frame=None))
    with pytest.raises(jinja2.UndefinedError):
        render_command(ctx, cmd, "generate")


@pytest.mark.not_slow("pure function")
def test_only_text_a_shell_cannot_read_as_syntax_is_rendered():
    safe = _safe_item({"a": "count_plants", "b": ["x-1.2", "a/b@c:d+e"], "n": 3, "c": "x; rm -rf /", "d": "$(id)", "e": "a b"})
    assert safe["a"] == "count_plants" and safe["b"] == ["x-1.2", "a/b@c:d+e"] and safe["n"] == 3
    for k in ("c", "d", "e"):
        with pytest.raises(jinja2.TemplateError):
            str(safe[k])
