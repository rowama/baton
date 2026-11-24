"""An output schema with no instance is warned about by the loader (§5.3; change 2026-11-recipe-contract-checks, Slice 1; Decision 0190).

``schema_instance.find_instance`` builds candidates and keeps one only if the validator accepts it, so an
instance it returns is always valid; finding none is a warning (``schema.no_instance``), never a refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from baton import versions
from baton.cli import app
from baton.engine import Api
from baton.project import init
from baton.recipe import load_recipe, validate_recipe
from baton.schema_instance import find_instance

from conftest import ROOT
from projectkit import make_home
from runkit import Clock, make_recipe

SHIPPED = sorted((ROOT / "examples" / "recipes").glob("*/recipe.yaml"))

#: Contradictions a recipe could carry; each has no instance.
CONTRADICTIONS = {
    "enum clash in allOf": {"type": "object", "required": ["a"],
                            "properties": {"a": {"allOf": [{"enum": ["x", "y"]}, {"enum": ["z"]}]}}},
    "open choice must have no decision, but one is required": {
        "type": "object", "required": ["status", "decision"],
        "properties": {"status": {"enum": ["open", "decided"]}, "decision": {"type": "string"}},
        "allOf": [{"properties": {"status": {"const": "open"}}}],
        "if": {"properties": {"status": {"const": "open"}}}, "then": {"not": {"required": ["decision"]}}},
    "required but not allowed": {"type": "object", "required": ["a"], "additionalProperties": False},
    "too few and too many items": {"type": "array", "minItems": 3, "maxItems": 2},
    "type clash": {"allOf": [{"type": "string"}, {"type": "integer"}]},
}

SATISFIABLE = {
    "if/then on a required const": {"type": "object", "required": ["s"], "properties": {"s": {"enum": ["a", "b"]}},
                                    "if": {"properties": {"s": {"const": "a"}}},
                                    "then": {"required": ["t"], "properties": {"t": {"type": "integer", "minimum": 3}}}},
    "recursive $ref": {"$defs": {"n": {"type": "object", "properties": {"k": {"$ref": "#/$defs/n"}}}}, "$ref": "#/$defs/n"},
    "pattern and minLength": {"type": "string", "pattern": "^[0-9a-f]{7,40}$", "minLength": 7},
    "contains and minItems": {"type": "array", "minItems": 2, "contains": {"const": 5}, "items": {"type": "integer"}},
    "anyOf with a branch that fits": {"anyOf": [{"type": "string", "maxLength": 0, "minLength": 1}, {"type": "boolean"}]},
}


def _valid(schema, value) -> bool:
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).is_valid(value)


def _output_schemas(recipe_yaml: Path):
    loaded = load_recipe(recipe_yaml.parent)
    return [(f"{loaded.recipe.id}:{rel}", schema) for rel, schema in loaded.schemas.items()]


@pytest.mark.parametrize("recipe_yaml", SHIPPED, ids=lambda p: p.parent.name)
def test_every_shipped_recipes_schemas_yield_a_valid_instance(recipe_yaml):
    loaded = load_recipe(recipe_yaml.parent)
    assert not [w for w in loaded.warnings if w.code == "schema.no_instance"]
    for rel, schema in loaded.schemas.items():
        found, instance = find_instance(schema)
        assert found, f"{recipe_yaml.parent.name}: {rel}"
        assert _valid(schema, instance), f"{recipe_yaml.parent.name}: {rel}"


@pytest.mark.parametrize("ref", sorted(versions.RUNTIME_SCHEMAS))
def test_the_runtime_output_schemas_yield_a_valid_instance(ref):
    schema = versions.runtime_schema(ref)
    found, instance = find_instance(schema)
    assert found and _valid(schema, instance)


@pytest.mark.parametrize("name", sorted(CONTRADICTIONS))
def test_a_contradictory_schema_has_no_instance(name):
    assert find_instance(CONTRADICTIONS[name]) == (False, None)


@pytest.mark.parametrize("name", sorted(SATISFIABLE))
def test_a_satisfiable_schema_yields_a_valid_instance(name):
    found, instance = find_instance(SATISFIABLE[name])
    assert found and _valid(SATISFIABLE[name], instance)


def test_the_recipe_builder_7_schema_alone_yields_an_instance():
    """The @7 contradiction was between prompt and schema: the schema check cannot see it (Decision 0189)."""
    schema = json.loads((ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v7" / "schemas" / "research_out.json").read_text(encoding="utf-8"))
    found, instance = find_instance(schema)
    assert found and _valid(schema, instance)


def _contradictory_pkg(root: Path) -> Path:
    return make_recipe(root, [{"id": "work", "output_schema": "schemas/out.json"}],
                       schemas={"out.json": CONTRADICTIONS["open choice must have no decision, but one is required"]},
                       run_inputs={"type": "object"}, id="clash", version=1, description="A recipe whose schema has no instance")


def test_the_loader_warns_by_step_and_file_and_still_loads(tmp_path):
    loaded, issues = validate_recipe(_contradictory_pkg(tmp_path / "clash"))
    assert loaded is not None
    [w] = [i for i in issues if i.code == "schema.no_instance"]
    assert w.severity == "warning" and w.where == "work.output_schema" and "schemas/out.json" in w.message


def test_plan_prints_the_warning_and_exits_0(tmp_path):
    result = CliRunner().invoke(app, ["plan", str(_contradictory_pkg(tmp_path / "clash"))])
    assert result.exit_code == 0
    assert "schema.no_instance" in result.output and "schemas/out.json" in result.output


@pytest.mark.slow  # opens a project (git checkpoints): over 1 s
def test_vendor_warns_and_still_vendors(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    api = Api.open(root, director_id="alice@host1", home=make_home(tmp_path / "home", ""), clock=Clock())
    out = api.vendor(_contradictory_pkg(tmp_path / "clash"))
    assert out["changed"]
    assert any("schema.no_instance" in w and "schemas/out.json" in w for w in out["warnings"])
