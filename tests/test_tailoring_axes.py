"""Tailoring by axes (§5.5; Decisions 0144, 0147): the format, the loader, the plan, the runtime."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from baton.recipe import RecipeError, build_plan, load_recipe, render_plan

SCHEMA = "https://json-schema.org/draft/2020-12/schema"
AXES = {"discovery": ["low", "medium", "high"], "assurance": {"scale": ["low", "medium", "high"], "confirm_lowest": True}}
OBJ = {"type": "object"}


def ratings_schema(axes: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "object", "required": ["ratings"],
        "properties": {"ratings": {
            "type": "object", "required": list(axes), "additionalProperties": False,
            "properties": {a: {"type": "object", "required": ["value", "reason"], "properties": {
                "value": {"enum": scale}, "reason": {"type": "string", "minLength": 1}}} for a, scale in axes.items()},
        }},
    }


def scales_of(axes: dict[str, Any]) -> dict[str, list[str]]:
    return {a: (s if isinstance(s, list) else s["scale"]) for a, s in axes.items()}


def axes_steps() -> list[dict]:
    """triage; explore at discovery medium/high; build always (its review gate at assurance high);
    verify at assurance medium/high; checks (a group) at assurance high with a step inside at the same."""
    return [
        {"id": "triage", "output_schema": "schemas/triage.json", "gates": [{"type": "schema"}]},
        {"id": "explore", "depends_on": ["triage"], "applies_to": {"discovery": ["medium", "high"]}},
        {"id": "build", "depends_on": ["triage", "explore"],
         "gates": [{"type": "schema"}, {"type": "human", "applies_to": {"assurance": ["high"]}, "prompt": "Accept the build?"}]},
        {"id": "verify", "depends_on": ["build"], "applies_to": {"assurance": ["medium", "high"]}},
        {"id": "checks", "depends_on": ["build"], "applies_to": {"assurance": ["high"]},
         "steps": [{"id": "probe"}, {"id": "recover", "depends_on": ["probe"], "applies_to": {"assurance": ["high"]}}]},
    ]


def write_recipe(root: Path, steps: list[dict] | None = None, complexity: dict | None = None, triage_schema: dict | None = None) -> Path:
    steps = copy.deepcopy(steps if steps is not None else axes_steps())
    complexity = complexity if complexity is not None else {"axes": AXES, "triage_step": "triage"}
    root.mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "schemas").mkdir(exist_ok=True)
    tri = triage_schema if triage_schema is not None else ratings_schema(scales_of(complexity.get("axes") or {}))
    for name, schema in {"triage.json": tri, "obj.json": OBJ}.items():
        (root / "schemas" / name).write_text(json.dumps({"$schema": SCHEMA, **schema}), encoding="utf-8")

    def fill(nodes: list[dict]) -> None:
        for s in nodes:
            if "steps" in s:
                fill(s["steps"])
                continue
            s.setdefault("requires", {"capabilities": ["structured_output"]})
            s.setdefault("prompt", f"prompts/{s['id']}.md")
            s.setdefault("output_schema", "schemas/obj.json")
            (root / s["prompt"]).write_text(f"Do the {s['id']} step.\n", encoding="utf-8")

    fill(steps)
    doc = {"id": "axes", "version": 1, "format": "baton-recipe/1", "capabilities_vocab": "baton-capabilities/1",
           "complexity": complexity, "steps": steps}
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


def codes(root: Path) -> list[str]:
    with pytest.raises(RecipeError) as e:
        load_recipe(root)
    return [i.code for i in e.value.issues if i.severity == "error"]


# -- the format and the loader (Slice 1) -----------------------------------


def test_a_recipe_with_axes_loads(tmp_path):
    loaded = load_recipe(write_recipe(tmp_path / "r"))
    cx = loaded.recipe.complexity
    assert cx.levels is None and set(cx.axes) == {"discovery", "assurance"}
    assert cx.axes["assurance"].confirm_lowest is True
    assert not [w for w in loaded.warnings if w.code.startswith("complexity.")]


def test_levels_and_axes_together_are_refused(tmp_path):
    root = write_recipe(tmp_path / "r", complexity={"levels": ["a", "b"], "axes": AXES, "triage_step": "triage"})
    assert codes(root) == ["complexity.levels_and_axes"]


def test_a_complexity_block_without_a_scale_is_refused(tmp_path):
    root = write_recipe(tmp_path / "r", complexity={"triage_step": "triage"})
    assert codes(root) == ["complexity.no_scale"]


def test_an_unknown_axis_and_an_undeclared_value_are_refused(tmp_path):
    steps = axes_steps()
    steps[1]["applies_to"] = {"discovry": ["high"]}
    steps[3]["applies_to"] = {"assurance": ["extreme"]}
    assert sorted(codes(write_recipe(tmp_path / "r", steps))) == ["complexity.unknown_axis", "complexity.unknown_level"]


def test_a_list_applies_to_in_a_recipe_with_axes_is_refused(tmp_path):
    steps = axes_steps()
    steps[1]["applies_to"] = ["high"]
    assert codes(write_recipe(tmp_path / "r", steps)) == ["complexity.applies_to_list"]


def test_a_map_applies_to_in_a_recipe_with_levels_is_refused(tmp_path):
    steps = [
        {"id": "triage", "output_schema": "schemas/triage.json"},
        {"id": "spec", "depends_on": ["triage"], "applies_to": {"level": ["major"]}},
    ]
    tri = {"type": "object", "required": ["level"], "properties": {"level": {"enum": ["minor", "major"]}}}
    root = write_recipe(tmp_path / "r", steps, {"levels": ["minor", "major"], "triage_step": "triage"}, tri)
    assert codes(root) == ["complexity.applies_to_by_axis"]


def test_level_is_a_reserved_axis_name(tmp_path):
    axes = {"level": ["low", "high"], "assurance": ["low", "high"]}
    steps = [{"id": "triage", "output_schema": "schemas/triage.json"},
             {"id": "verify", "depends_on": ["triage"], "applies_to": {"assurance": ["high"], "level": ["high"]}}]
    assert codes(write_recipe(tmp_path / "r", steps, {"axes": axes, "triage_step": "triage"})) == ["complexity.reserved_axis"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["required"].clear(),  # ratings not required
        lambda s: s["properties"]["ratings"]["required"].remove("assurance"),  # an axis not required
        lambda s: s["properties"]["ratings"].pop("additionalProperties"),  # other axes allowed
        lambda s: s["properties"]["ratings"]["properties"]["discovery"]["required"].remove("reason"),  # no reason required
        lambda s: s["properties"]["ratings"]["properties"]["discovery"]["properties"]["reason"].pop("minLength"),  # empty reason
        lambda s: s["properties"]["ratings"]["properties"]["assurance"]["properties"]["value"].update(enum=["low", "high"]),  # wrong scale
    ],
    ids=["ratings", "every-axis", "closed", "reason-required", "reason-non-empty", "scale"],
)
def test_the_triage_schema_must_constrain_every_axis_and_require_a_reason(tmp_path, mutate):
    tri = ratings_schema(scales_of(AXES))
    mutate(tri)
    assert codes(write_recipe(tmp_path / "r", triage_schema=tri)) == ["complexity.ratings_schema_mismatch"]


def test_a_nested_step_must_be_reachable_at_every_combination(tmp_path):
    steps = axes_steps()
    steps[4]["steps"][1]["applies_to"] = {"discovery": ["high"]}  # the group runs only at assurance high
    issues = codes(write_recipe(tmp_path / "r", steps))
    assert issues == ["complexity.unreachable"]


def test_a_nested_step_reachable_by_a_wider_condition_loads(tmp_path):
    steps = axes_steps()
    steps[4]["applies_to"] = {"assurance": ["high"], "discovery": ["high"]}
    steps[4]["steps"][1]["applies_to"] = {"discovery": ["high"]}  # implies the group's OR
    load_recipe(write_recipe(tmp_path / "r", steps))


def test_an_axis_nothing_applies_by_is_a_warning(tmp_path):
    axes = {**AXES, "reach": ["one", "many"]}
    loaded = load_recipe(write_recipe(tmp_path / "r", complexity={"axes": axes, "triage_step": "triage"}))
    assert [w.code for w in loaded.warnings if w.code.startswith("complexity.")] == ["complexity.axis_unused"]


def test_a_foreach_source_skippable_at_some_ratings_needs_a_policy(tmp_path):
    steps = axes_steps()
    steps.append({"id": "each", "depends_on": ["explore"], "foreach": "steps.explore.output.items", "steps": [{"id": "do"}]})
    root = write_recipe(tmp_path / "r", steps)
    (root / "schemas" / "list.json").write_text(json.dumps({"$schema": SCHEMA, "type": "object", "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}}}}), encoding="utf-8")
    doc = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
    doc["steps"][1]["output_schema"] = "schemas/list.json"
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    assert "group.foreach_source_skippable" in codes(root)


# -- the plan (Slice 1) ----------------------------------------------------


def test_the_plan_shows_what_always_runs_and_what_each_rating_adds(tmp_path):
    plan = build_plan(load_recipe(write_recipe(tmp_path / "r")))
    (always,) = plan.levels
    assert always.level is None and always.ratings is None
    assert {r.path: r.included for r in always.steps} == {
        "triage": True, "explore": False, "build": True, "verify": False, "checks": False, "checks/probe": False, "checks/recover": False,
    }
    axes = {a.name: {v.value: v.adds for v in a.values} for a in plan.axes}
    assert axes["discovery"] == {"low": [], "medium": ["step explore"], "high": ["step explore"]}
    assert axes["assurance"] == {
        "low": [], "medium": ["step verify"],
        "high": ["human gate on build", "step verify", "group checks", "step checks/recover"],
    }
    assert [a.confirm_lowest for a in plan.axes] == [False, True]
    text = render_plan(plan)
    assert "Axis assurance (low, medium, high; its lowest also asks the owner):" in text
    assert "  high: adds human gate on build; step verify; group checks; step checks/recover" in text
    assert "  low: adds nothing" in text


def test_the_plan_for_a_combination_is_the_full_table(tmp_path):
    loaded = load_recipe(write_recipe(tmp_path / "r"))
    plan = build_plan(loaded, ratings={"discovery": "low", "assurance": "high"})
    assert plan.axes is None
    (combo,) = plan.levels
    assert combo.ratings == {"discovery": "low", "assurance": "high"}
    rows = {r.path: r for r in combo.steps}
    assert {p: r.included for p, r in rows.items()} == {
        "triage": True, "explore": False, "build": True, "verify": True, "checks": True, "checks/probe": True, "checks/recover": True,
    }
    assert rows["explore"].reason == "applies to discovery: medium, high"
    assert [g.included for g in rows["build"].gates] == [True, True]
    assert any(g.implicit and g.note == "approve the ratings" for g in rows["triage"].gates)
    assert "Ratings: discovery low, assurance high" in render_plan(plan)


def test_the_lowest_combination_asks_the_owner_only_when_an_axis_guards_it(tmp_path):
    lowest = {"discovery": "low", "assurance": "low"}
    guarded = build_plan(load_recipe(write_recipe(tmp_path / "a")), ratings=lowest)
    assert any(g.implicit for g in guarded.levels[0].steps[0].gates)
    plain = {"discovery": ["low", "medium", "high"], "assurance": ["low", "medium", "high"]}
    open_ = build_plan(load_recipe(write_recipe(tmp_path / "b", complexity={"axes": plain, "triage_step": "triage"})), ratings=lowest)
    assert not any(g.implicit for g in open_.levels[0].steps[0].gates)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"ratings": {"discovery": "low"}}, "missing: assurance"),
        ({"ratings": {"discovery": "low", "assurance": "extreme"}}, "unknown rating"),
        ({"level": "low"}, "declares axes"),
    ],
)
def test_the_plan_refuses_an_incomplete_or_unknown_combination(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        build_plan(load_recipe(write_recipe(tmp_path / "r")), **kwargs)


def test_ratings_are_refused_for_a_recipe_with_levels(tmp_path):
    from baton.data import path as data_path

    loaded = load_recipe(data_path("examples") / "recipes" / "software-feature")
    with pytest.raises(ValueError, match="declares levels"):
        build_plan(loaded, ratings={"level": "minor"})


def test_baton_plan_takes_ratings(tmp_path):
    from typer.testing import CliRunner

    from baton.cli import app

    root = write_recipe(tmp_path / "r")
    res = CliRunner().invoke(app, ["plan", str(root), "--rating", "discovery=high", "--rating", "assurance=low", "--json"])
    assert res.exit_code == 0, res.output
    plan = json.loads(res.output)["plan"]
    assert plan["levels"][0]["ratings"] == {"discovery": "high", "assurance": "low"}
    res = CliRunner().invoke(app, ["plan", str(root), "--rating", "discovery"])
    assert res.exit_code != 0 and "axis=value" in res.output
