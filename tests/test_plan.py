from __future__ import annotations

import pytest

from baton import engine
from baton.recipe import render_plan

from conftest import FIT_CHECK, SOFTWARE_FEATURE


def _included(plan, level):
    lv = next(l for l in plan.levels if l.level == level)
    return [r.path for r in lv.steps if r.included]


def test_levels_include_the_right_steps():
    plan = engine.plan(SOFTWARE_FEATURE)
    assert [l.level for l in plan.levels] == ["minor", "standard", "major"]
    assert _included(plan, "minor") == ["triage", "slices", "slices/implement", "slices/code_review", "slices/accept"]
    assert _included(plan, "standard") == [
        "triage", "requirements", "plan", "slices", "slices/implement", "slices/code_review", "slices/accept",
    ]
    assert "design" in _included(plan, "major")


def test_gates_follow_levels():
    plan = engine.plan(SOFTWARE_FEATURE)
    for level, expect in [("standard", False), ("major", True)]:
        req = next(r for r in next(l for l in plan.levels if l.level == level).steps if r.path == "requirements")
        human = next(g for g in req.gates if g.type == "human")
        assert human.included is expect


def test_implicit_triage_approval_above_lowest_level():
    # §18 #8: auto-accept at the lowest level; owner approval above it.
    plan = engine.plan(SOFTWARE_FEATURE)
    for lv in plan.levels:
        triage = next(r for r in lv.steps if r.path == "triage")
        implicit = [g for g in triage.gates if g.implicit and g.type == "human"]
        assert bool(implicit) is (lv.level != "minor")


def test_foreach_source_skipped_noted():
    plan = engine.plan(SOFTWARE_FEATURE, level="minor")
    slices = next(r for r in plan.levels[0].steps if r.path == "slices")
    assert slices.group["source_skipped"] == "once"
    assert slices.group["max_iterations"] == 3


def test_single_level_recipe():
    plan = engine.plan(FIT_CHECK)
    assert [l.level for l in plan.levels] == [None]
    text = render_plan(plan)
    assert "describe" in text and "human: Accept this verdict" in text


def test_unknown_level_is_an_error():
    with pytest.raises(ValueError):
        engine.plan(SOFTWARE_FEATURE, level="huge")
    with pytest.raises(ValueError):
        engine.plan(FIT_CHECK, level="minor")


def test_render_marks_skips_and_implicit_gates():
    text = render_plan(engine.plan(SOFTWARE_FEATURE))
    assert "design         skip  (applies to major)" in text
    assert "* implicit gate" in text
