"""The shipped recipe-builder recipe (change 2026-11-recipe-builder): it loads, plans at every level and is wired as designed."""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from baton.project import catalog
from baton.recipe import build_plan, load_recipe

from conftest import ROOT

BUILDER = ROOT / "examples" / "recipes" / "recipe-builder"


def steps(plan_level):
    return {s.path: s for s in plan_level.steps}


@pytest.fixture(scope="module")
def loaded():
    return load_recipe(BUILDER)


def test_it_loads_cleanly_and_is_a_root_recipe_with_a_scope(loaded):
    r = loaded.recipe
    assert r.ref == "recipe-builder@1" and r.provenance == "scratch"
    assert r.scope is not None and r.scope.covers and r.scope.not_for
    assert not loaded.warnings


def test_it_ships_in_the_catalog():
    assert catalog()["recipe-builder"].recipe.complexity.levels == ["simple", "standard", "complex"]


def test_the_plan_at_each_level(loaded):

    by_level = {lv.level: steps(lv) for lv in build_plan(loaded).levels}
    assert not by_level["simple"]["research"].included
    assert by_level["standard"]["research"].included and by_level["complex"]["research"].included

    def gate(level, path, type_):
        return [g for g in by_level[level][path].gates if g.type == type_]

    assert not gate("simple", "shape/audit", "human")[0].included  # the design is approved only above simple
    assert gate("standard", "shape/audit", "human")[0].included
    assert not gate("standard", "generate", "review")[0].included  # a package review only at complex
    assert gate("complex", "generate", "review")[0].included
    for lv in by_level.values():
        assert [g.type for g in lv["generate"].gates if g.type == "script"] == ["script", "script"]


def test_the_loop_is_bounded_and_audited_by_another_vendor(loaded):
    shape = next(s for s in loaded.recipe.steps if s.id == "shape")
    assert shape.max_iterations == 3 and shape.repeat_from == "design"
    audit = next(s for s in shape.steps if s.id == "audit")
    assert audit.independence.from_step == "design" and audit.independence.level == "different_vendor"
    assert {i.name: i.from_ for i in audit.inputs}["patterns"] == "static.patterns.md"
    design = next(s for s in shape.steps if s.id == "design")
    assert {i.name: i.from_ for i in design.inputs}["patterns"] == "static.patterns.md"


def test_generate_runs_the_deterministic_checks_on_its_own_draft(loaded):
    gen = next(s for s in loaded.recipe.steps if s.id == "generate")
    cmds = [g.run for g in gen.gates if g.type == "script"]
    assert cmds[0] == "baton plan recipes/drafts/{{ run.slug }}"
    assert cmds[1].startswith("baton recipe check recipes/drafts/{{ run.slug }} --ledger recipes/drafts/{{ run.slug }}.ledger.json")
    assert {a.name for a in gen.artifacts} == {"walkthrough", "ledger"}


def test_profile_reads_the_catalog_the_plan_directory_and_publishes_the_process_plan(loaded):
    profile = next(s for s in loaded.recipe.steps if s.id == "profile")
    assert {i.name: i.from_ for i in profile.inputs}["recipes"] == "catalog.summaries"
    assert profile.workspace == "read"
    plan = next(a for a in profile.artifacts if a.name == "process_plan")
    assert plan.publish.to == "recipes/plans/{{ run.slug }}.md" and not plan.required


def test_the_profile_prompt_holds_the_generality_rules():
    text = (BUILDER / "prompts" / "profile.md").read_text(encoding="utf-8")
    assert "narrowest rung" in text and "next wider rung" in text  # Decision 0099
    assert "recipes/plans/" in text  # Decision 0102
    assert "existing_recipe" in text and "base_recipe" in text
    assert "Never\nrecommend a wider rung unless" in text or "recommend a wider rung unless" in text.replace("\n", " ")


def test_every_ledger_in_the_schemas_is_the_ledger_schema():
    entry = json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))["items"]
    for name, path in (("profile_out", ("ledger",)), ("research_out", ("ledger",)), ("design_out", ("ledger",))):
        schema = json.loads((BUILDER / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
        assert schema["properties"][path[0]]["items"] == entry, name


def test_the_ledger_schema_and_the_checker_agree_on_the_vocabulary():
    from baton import recipe_check

    entry = json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))["items"]["properties"]
    assert tuple(entry["status"]["enum"]) == recipe_check.STATUSES
    assert tuple(entry["scope"]["enum"]) == recipe_check.SCOPES


def test_an_example_ledger_is_valid_and_passes_the_check(tmp_path):
    from baton import recipe_check

    ledger = [
        {"id": "G1", "statement": "A plan for planting a flower bed", "kind": "goal", "scope": "class", "status": "confirmed",
         "basis": "the owner's words", "owner_words": "I want to plant a flower bed properly"},
        {"id": "I1", "statement": "The shed is 2 m by 3 m and painted green", "kind": "requirement", "scope": "instance",
         "status": "confirmed", "basis": "the owner's words", "owner_words": "two by three metres, green", "value": "2 m by 3 m, green"},
    ]
    schema = json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))
    assert Draft202012Validator(schema).is_valid(ledger)
    f = tmp_path / "ledger.json"
    f.write_text(json.dumps(ledger), encoding="utf-8")
    assert recipe_check.check(BUILDER, f) == []  # the builder's own prompts hold no instance fact


def test_run_inputs_take_an_idea_and_an_optional_base_recipe():
    v = Draft202012Validator(json.loads((BUILDER / "schemas" / "run_inputs.json").read_text(encoding="utf-8")))
    assert v.is_valid({"title": "Flower bed", "idea": "plant a flower bed"})
    assert v.is_valid({"title": "t", "idea": "i", "base_recipe": "backyard-project@1", "profile": {"a": 1}})
    assert not v.is_valid({"title": "t", "idea": "i", "base_recipe": "backyard-project"})
    assert not v.is_valid({"title": "t"})


def test_the_triage_schema_may_carry_more_than_the_level():
    schema = json.loads((BUILDER / "schemas" / "profile_out.json").read_text(encoding="utf-8"))
    assert schema["properties"]["level"]["enum"] == ["simple", "standard", "complex"]
    assert {"goal", "rung", "ledger", "existing_recipe", "related_parts", "build_now"} <= set(schema["properties"])


def test_no_prompt_names_a_vendor(loaded):
    assert not [w for w in loaded.warnings if w.code.startswith("neutrality")]
