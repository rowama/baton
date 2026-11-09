"""``scope`` and ``parent`` are optional fields of baton-recipe/1 (§5.1; Decisions 0103, 0105)."""
from __future__ import annotations

import pytest

from baton.recipe import load_recipe, validate_recipe

SCOPE = {
    "covers": ["a flower bed", "a raised bed"],
    "not_for": [{"job": "a kitchen remodel", "use": "home-renovation"}],
    "varies_by": ["size", "whether a permit is needed"],
}


def test_recipe_without_either_field_is_unrecorded_and_unchanged(make_recipe):
    r = load_recipe(make_recipe()).recipe
    assert r.format == "baton-recipe/1"
    assert r.scope is None and r.parent is None
    assert r.provenance == "unrecorded"


def test_scope_loads(make_recipe):
    r = load_recipe(make_recipe(lambda d, _: d.update(scope=SCOPE))).recipe
    assert r.scope.covers == ["a flower bed", "a raised bed"]
    assert r.scope.not_for[0].use == "home-renovation"
    assert r.scope.varies_by == ["size", "whether a permit is needed"]


def test_parent_names_the_recipe_it_came_from(make_recipe):
    r = load_recipe(make_recipe(lambda d, _: d.update(parent={"id": "backyard-project", "version": 2}))).recipe
    assert (r.parent.id, r.parent.version) == ("backyard-project", 2)
    assert r.provenance == "parent"


def test_explicit_null_parent_means_built_from_scratch(make_recipe):
    r = load_recipe(make_recipe(lambda d, _: d.update(parent=None))).recipe
    assert r.parent is None
    assert r.provenance == "scratch"


@pytest.mark.parametrize(
    "field,value,where",
    [
        ("scope", {"covers": []}, "scope.covers"),
        ("scope", {"covers": ["x"], "bogus": 1}, "scope.bogus"),
        ("scope", {"covers": ["x"], "not_for": [{"job": "y", "use": "Not An Id"}]}, "scope.not_for"),
        ("parent", {"id": "ok", "version": 0}, "parent.version"),
        ("parent", {"id": "Bad Id", "version": 1}, "parent.id"),
        ("parent", {"id": "ok"}, "parent.version"),
        ("parent", {"id": "ok", "version": 1, "extra": True}, "parent.extra"),
    ],
)
def test_malformed_scope_or_parent_is_a_recipe_error(make_recipe, field, value, where):
    loaded, issues = validate_recipe(make_recipe(lambda d, _: d.update({field: value})))
    errors = [i for i in issues if i.severity == "error"]
    assert errors and any(where in i.where for i in errors), [str(i) for i in issues]


def test_published_schema_accepts_scope_and_parent_and_rejects_bad_ones():
    import yaml
    from jsonschema import Draft202012Validator

    from baton.data import path as data_path
    from conftest import SOFTWARE_FEATURE

    schema = __import__("json").loads((data_path("formats") / "baton-recipe-1.schema.json").read_text(encoding="utf-8"))
    raw = yaml.safe_load((SOFTWARE_FEATURE / "recipe.yaml").read_text(encoding="utf-8"))
    for parent in ({"id": "a-b", "version": 1}, None):
        assert not list(Draft202012Validator(schema).iter_errors({**raw, "scope": SCOPE, "parent": parent}))
    assert list(Draft202012Validator(schema).iter_errors({**raw, "parent": {"id": "a", "version": 0}}))
    assert list(Draft202012Validator(schema).iter_errors({**raw, "scope": {"covers": []}}))
