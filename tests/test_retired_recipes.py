"""Retiring a recipe (§5.3; change 2026-11-builder-context-and-locks, Slice 3; Decisions 0149, 0173).

``recipe.yaml`` may declare ``retired: {replaced_by: <id>}``. Listings and
``catalog.summaries`` show it; a proposal (framing, project review) naming a
retired recipe is refused with its replacement; ``vendor`` and ``start`` warn;
pinned and vendored copies keep working.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baton import frame
from baton import project as project_mod
from baton.engine import Api
from baton.project import catalog, init, retirement, retirement_problems
from baton.recipe import RecipeError, load_recipe

from projectkit import make_home
from runkit import Clock, make_recipe

OBJ = {"type": "object"}
INPUTS = {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}}
PROFILES = """\
alice:
  adapter: manual
  vendor: acme
  capabilities: [structured_output]
  tier: strong
"""


def _pkg(root: Path, rid: str, version: int = 1, **top) -> Path:
    return make_recipe(root, [{"id": "work", "output_schema": "schemas/out.json"}], schemas={"out.json": OBJ}, run_inputs=INPUTS,
                       **{**top, "id": rid, "version": version, "description": f"The {rid} process"})


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    """A shipped catalog of two recipes: `old`, retired in favour of `new`."""
    cat = tmp_path / "catalog"
    _pkg(cat / "old", "old", 2, retired={"replaced_by": "new"})
    _pkg(cat / "new", "new")
    monkeypatch.setattr(project_mod, "catalog_dir", lambda: cat)
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    api = Api.open(root, director_id="alice@host1", home=make_home(tmp_path / "home", PROFILES), clock=Clock())
    return api, cat, tmp_path


def test_retired_loads_and_cannot_name_itself(tmp_path):
    ok = load_recipe(_pkg(tmp_path / "a", "old", retired={"replaced_by": "new"}))
    assert ok.recipe.retired is not None and ok.recipe.retired.replaced_by == "new" and not ok.warnings
    with pytest.raises(RecipeError) as e:
        load_recipe(_pkg(tmp_path / "b", "old", retired={"replaced_by": "old"}))
    assert any(i.code == "recipe.retired_by_itself" for i in e.value.issues)
    with pytest.raises(RecipeError):
        load_recipe(_pkg(tmp_path / "c", "old", retired={"replaced_by": "Not An Id"}))
    assert load_recipe(_pkg(tmp_path / "d", "plain")).recipe.retired is None  # nothing changes for a recipe without it


@pytest.mark.slow  # loads the whole shipped catalog
def test_a_replacement_must_be_a_known_recipe_that_is_not_retired_itself(tmp_path):
    old = load_recipe(_pkg(tmp_path / "a", "old", retired={"replaced_by": "new"}))
    new = load_recipe(_pkg(tmp_path / "b", "new"))
    new_retired = load_recipe(_pkg(tmp_path / "c", "new", retired={"replaced_by": "old"}))
    assert retirement_problems({"old": old, "new": new}) == []
    assert retirement_problems({"old": old}) == ["old is retired in favour of new, which is not a known recipe"]
    assert "which is retired itself" in retirement_problems({"old": old, "new": new_retired})[0]
    assert retirement_problems(catalog()) == []  # the shipped catalog


def test_listings_and_catalog_summaries_show_a_retired_recipe_and_its_replacement(shelf):
    api, cat, _ = shelf
    out = api.vendor(cat / "old")
    assert out["changed"] and out["retired"] == {"replaced_by": "new"}
    assert out["warnings"] == ["old is retired: new replaces it, and new work should use that"]
    (row,) = [r for r in api.recipes()["recipes"] if r["recipe"] == "old@2"]
    assert row["retired"] == {"replaced_by": "new"}
    summaries = {r["id"]: r for r in frame.recipe_listing(api.project, with_scope=True, retired="mark")}  # catalog.summaries
    assert summaries["old"]["retired"] == {"replaced_by": "new", "note": "Retired: propose new instead."}
    assert "retired" not in summaries["new"]
    for v2 in (False, True):  # framing's listing (baton-frame@1 and @2): left out, so never proposed; the published schemas are unchanged
        assert [r["id"] for r in frame.recipe_listing(api.project, with_scope=v2, with_axes=v2, retired="omit")] == ["new"]


def test_a_project_that_vendored_an_earlier_version_sees_it_retired_by_the_catalog(shelf):
    api, cat, tmp_path = shelf
    api.vendor(_pkg(tmp_path / "old-v1", "old", 1))
    assert retirement(api.project, "old") == {"replaced_by": "new"}
    summaries = {r["id"]: r for r in frame.recipe_listing(api.project, with_scope=True, retired="mark")}
    assert summaries["old"]["version"] == 1 and summaries["old"]["vendored"] and summaries["old"]["retired"]["replaced_by"] == "new"
    (row,) = api.recipes()["recipes"]
    assert row["recipe"] == "old@1" and row["retired"] == {"replaced_by": "new"}


def test_a_pinned_retired_recipe_still_starts_with_a_warning(shelf):
    api, cat, _ = shelf
    api.vendor(cat / "old")
    out = api.start("old", {"title": "Still mine"})
    assert out["recipe"] == "old@2" and out["state"] == "active" and out["ready"] == ["work"]
    assert out["retired"] == {"replaced_by": "new"} and "old is retired: new replaces it" in out["warnings"][-1]
    api.vendor(cat / "new")
    plain = api.start("new", {"title": "New work"})  # nothing changes for a recipe that is not retired
    assert "retired" not in plain and not any("retired" in w for w in plain.get("warnings") or [])


def test_a_proposal_naming_a_retired_recipe_is_refused_with_its_replacement(shelf):
    api, cat, _ = shelf
    plan, why = frame._plan_part(api, {"id": "p1", "label": "Old work", "proposal": {"recipe": "old", "inputs": {"title": "x"}}}, 0)
    assert plan is None and why == "old is retired: new replaces it, and new work should use that: propose new for this part"
    plan, why = frame._plan_part(api, {"id": "p2", "label": "New work", "proposal": {"recipe": "new", "inputs": {"title": "x"}}}, 0)
    assert why is None and plan["recipe"].recipe.ref == "new@1"


def test_vendoring_a_recipe_whose_replacement_is_unknown_warns_about_that_too(shelf, tmp_path):
    api, _, _ = shelf
    out = api.vendor(_pkg(tmp_path / "orphan", "orphan", retired={"replaced_by": "nowhere"}))
    assert out["changed"] and out["warnings"][-1] == "nowhere is neither vendored here nor shipped with Baton"
