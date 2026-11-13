"""fit-check version 5: the assessed work, and a general `not_recommended` verdict (Decision 0140)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from baton.recipe import load_recipe

from conftest import FIT_CHECK
from projectkit import GOOD_PROFILE, VERDICT

V4 = Path(__file__).parent / "fixtures" / "recipes" / "fit-check-v4"
BUILDER = FIT_CHECK.parent / "recipe-builder"


def schema(root: Path, name: str) -> dict:
    return json.loads((root / "schemas" / f"{name}.json").read_text(encoding="utf-8"))


def ok(doc: dict, name: str = "verdict") -> bool:
    return jsonschema.Draft202012Validator(schema(FIT_CHECK, name)).is_valid(doc)


NEG = {**VERDICT, "verdict": "not_recommended", "alternative": "Ask an assistant directly.",
       "next_step": "Do it in one conversation."}
NEG.pop("recipe", None)


def test_version_five_and_pinned_version_four_both_load():
    assert load_recipe(FIT_CHECK).recipe.version == 5
    assert load_recipe(V4).recipe.version == 4


def test_verdict_values_are_exactly_the_three():
    assert set(schema(FIT_CHECK, "verdict")["properties"]["verdict"]["enum"]) == {"fits", "fits_per_occurrence", "not_recommended"}
    assert ok(VERDICT) and ok({**VERDICT, "verdict": "fits_per_occurrence"}) and ok(NEG)
    assert not ok({**VERDICT, "verdict": "operations_engine"})


def test_version_four_records_remain_valid_under_their_own_schema():
    old = {"verdict": "operations_engine", "reasons": [{"row": "occurrences", "leans": "operations_engine", "reason": "per order"}],
           "next_step": "Start a software-feature run."}
    assert jsonschema.Draft202012Validator(schema(V4, "verdict")).is_valid(old)
    assert not ok(old)


def test_a_verdict_names_its_assessed_work_and_row_basis():
    assert not ok({k: v for k, v in VERDICT.items() if k != "assessed_work"})
    bad = copy.deepcopy(VERDICT)
    del bad["reasons"][0]["basis"]
    assert not ok(bad)


def test_not_recommended_needs_an_alternative_and_names_no_recipe():
    assert not ok({k: v for k, v in NEG.items() if k != "alternative"})
    assert not ok({**NEG, "recipe": None})
    assert ok({**NEG, "development_offer": "Build a workflow that does this, as a separate project."})


def test_alternative_and_offer_belong_only_to_a_negative_verdict():
    assert not ok({**VERDICT, "alternative": "A script."})
    assert not ok({**VERDICT, "development_offer": "Build it."})


def test_fits_can_name_a_recipe_or_none_and_per_occurrence_too():
    assert ok({**VERDICT, "recipe": None})
    assert ok({**VERDICT, "verdict": "fits_per_occurrence", "recipe": {"id": "recipe-builder", "version": 2}})


@pytest.mark.parametrize("kind", ["developing_a_process", "executing_a_process", "other_work"])
def test_profile_states_the_scope(kind):
    doc = copy.deepcopy(GOOD_PROFILE)
    doc["scope"]["kind"] = kind
    doc["scope"]["target"] = "an n8n workflow"
    assert ok(doc, "profile")


def test_profile_needs_scope_and_work_and_rejects_the_old_occurrence_shape():
    assert not ok({"summary": "x", "occurrence": {}}, "profile")
    assert not ok({k: v for k, v in GOOD_PROFILE.items() if k != "scope"}, "profile")
    assert not ok({**GOOD_PROFILE, "scope": {"kind": "run_it", "statement": "x"}}, "profile")


def test_a_target_workload_is_never_a_profile_field():
    work = schema(FIT_CHECK, "profile")["properties"]["work"]
    assert work["additionalProperties"] is False
    assert not {"target_volume", "target_frequency"} & set(work["properties"])


def test_rubric_and_prompts_keep_development_separate_from_execution():
    rubric = (FIT_CHECK / "static" / "rubric.md").read_text(encoding="utf-8")
    assert "operations_engine" not in rubric and "not_recommended" in rubric
    assert "however the" in rubric and "finished process will run" in rubric
    describe = (FIT_CHECK / "prompts" / "describe.md").read_text(encoding="utf-8")
    assert "developing_a_process" in describe and "executing_a_process" in describe
    assert "**not** the work you profile" in describe
    assess = (FIT_CHECK / "prompts" / "assess.md").read_text(encoding="utf-8")
    assert "**separate** project" in assess and "Do not reject development work" in " ".join(assess.split())


def test_describe_and_assess_keep_inputs_and_the_human_gate():
    r = load_recipe(FIT_CHECK).recipe
    describe, assess = r.steps[0], r.steps[1]
    assert [i.name for i in describe.inputs] == ["idea", "context"]
    assert {"context", "profile", "rubric", "recipes"} == {i.name for i in assess.inputs}
    assert [g.type for g in assess.gates] == ["schema", "human"]


def test_other_guidance_does_not_turn_execution_into_development():
    frame = (FIT_CHECK.parents[2] / "builtin" / "baton-frame" / "prompts" / "frame.md").read_text(encoding="utf-8")
    frame = " ".join(frame.split())
    assert "operations engine" not in frame and "without saying so" in frame
    assert load_recipe(BUILDER).recipe.version == 3
    prof = (BUILDER / "prompts" / "profile.md").read_text(encoding="utf-8")
    assert "turned into building something else" in " ".join(prof.split())
    assert "Baton does not run day-to-day" not in prof
