from __future__ import annotations

import json

import pytest
import yaml
from jsonschema import Draft202012Validator

from baton import versions
from baton.data import path as data_path
from baton.models import Group, Step
from baton.recipe import load_recipe, package_sha256, validate_recipe

from conftest import FIT_CHECK, SOFTWARE_FEATURE


@pytest.mark.parametrize("root", [SOFTWARE_FEATURE, FIT_CHECK], ids=["software-feature", "fit-check"])
def test_valid_recipe_loads(root):
    loaded = load_recipe(root)
    assert loaded.recipe.format == "baton-recipe/1"
    assert loaded.vocab.id == "baton-capabilities/1"
    assert len(loaded.sha256) == 64
    assert not [w for w in loaded.warnings if w.code.startswith("neutrality")]


def test_software_feature_structure():
    r = load_recipe(SOFTWARE_FEATURE).recipe
    slices = next(s for s in r.steps if s.id == "slices")
    assert isinstance(slices, Group)
    assert [s.id for s in slices.steps] == ["implement", "code_review", "accept"]
    implement = slices.steps[0]
    assert isinstance(implement, Step)
    assert implement.protect_paths() == ["tests/acceptance/specs/**"]
    assert implement.inputs[0].from_ == "item"


def test_package_hash_is_deterministic_and_content_sensitive(make_recipe):
    a = package_sha256(SOFTWARE_FEATURE)
    assert a == package_sha256(SOFTWARE_FEATURE)
    copy = make_recipe()
    assert package_sha256(copy) == a
    (copy / "prompts" / "plan.md").write_text("changed", encoding="utf-8")
    assert package_sha256(copy) != a


def test_vendor_mention_in_prompt_is_only_a_warning(make_recipe):
    def edit(r, d):
        (d / "prompts" / "plan.md").write_text("Unlike gemini, be precise.", encoding="utf-8")

    loaded, issues = validate_recipe(make_recipe(edit))
    assert loaded is not None
    assert [i.code for i in issues] == ["neutrality.vendor_mention"]
    assert issues[0].severity == "warning"


def test_bom_tolerated(make_recipe):
    root = make_recipe(text=lambda t: "﻿" + t)
    load_recipe(root)


def test_published_formats_are_current():
    for name, schema in versions.published_schemas().items():
        on_disk = (data_path("formats") / name).read_text(encoding="utf-8")
        assert on_disk == versions.dump(schema), f"{name} is stale: run python -m baton.versions"


@pytest.mark.parametrize("root", [SOFTWARE_FEATURE, FIT_CHECK], ids=["software-feature", "fit-check"])
def test_recipe_conforms_to_published_schema(root):
    schema = json.loads((data_path("formats") / "baton-recipe-1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    raw = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(raw))
    assert not errors, [e.message for e in errors]


def test_published_schema_rejects_forbidden_key():
    schema = json.loads((data_path("formats") / "baton-recipe-1.schema.json").read_text(encoding="utf-8"))
    raw = yaml.safe_load((SOFTWARE_FEATURE / "recipe.yaml").read_text(encoding="utf-8"))
    raw["steps"][0]["model"] = "x"
    assert list(Draft202012Validator(schema).iter_errors(raw))
