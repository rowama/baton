"""The ``catalog.summaries`` input (§5.2; Decision 0106): vendored and shipped recipe summaries for any step."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import engine
from baton.project import catalog
from baton.recipe import load_recipe, validate_recipe
from baton.store import Store

from conftest import FIT_CHECK
from projectkit import make_home
from runkit import PROFILE_OUT, WRITER, Clock, start, write_result


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def assess_packet(store):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    write_result(p, PROFILE_OUT)
    assert engine.submit(ctx, "describe").outcome == "passed"
    return json.loads(
        (engine.begin_attempt(ctx, "assess", "owner", WRITER).dir / "inputs" / "recipes.json").read_text(encoding="utf-8")
    )


def test_a_step_receives_every_shipped_recipe_with_its_scope_slot(store):
    got = assess_packet(store)
    assert [r["id"] for r in got] == sorted(catalog())
    fit = next(r for r in got if r["id"] == "fit-check")
    assert fit["vendored"] is False and fit["levels"] == [] and fit["scope"] is None
    assert fit["version"] == catalog()["fit-check"].recipe.version
    assert next(r for r in got if r["id"] == "software-feature")["levels"] == ["minor", "standard", "major"]


def test_summaries_carry_a_recipes_scope(make_recipe):
    # the summary function reads the loaded recipe's scope block (§5.1)
    from baton.frame import _summary

    scope = {"covers": ["a flower bed"], "not_for": [{"job": "a remodel", "use": "home-renovation"}]}
    loaded = load_recipe(make_recipe(lambda d, _: d.update(scope=scope)))
    s = _summary(loaded, False, with_scope=True)
    assert s["scope"] == {"covers": ["a flower bed"], "not_for": [{"job": "a remodel", "use": "home-renovation"}], "varies_by": []}
    assert "scope" not in _summary(loaded, False)  # framing's own run inputs are unchanged


def test_a_vendored_recipe_is_listed_as_vendored_and_wins_over_the_shipped_one(tmp_path, make_recipe):
    from baton.engine import Api
    from baton.frame import recipe_listing
    from baton.project import init

    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    newer = make_recipe(lambda d, _: d.update(version=9), source=FIT_CHECK)
    api = Api.open(root, director_id="alice@host1", home=make_home(tmp_path / "home"), clock=Clock())
    api.vendor(newer)
    got = {r["id"]: r for r in recipe_listing(api.project, with_scope=True)}
    assert got["fit-check"]["vendored"] is True and got["fit-check"]["version"] == 9
    assert got["backyard-project"]["vendored"] is False


def test_a_misspelt_source_is_a_reference_error(make_recipe):
    from conftest import FIT_CHECK as src

    def edit(d, _):
        d["steps"][1]["inputs"][2]["from"] = "catalog.summary"

    _, issues = validate_recipe(make_recipe(edit, source=src))
    assert "ref.invalid" in {i.code for i in issues}


def test_fit_check_verdict_can_name_an_existing_recipe():
    from jsonschema import Draft202012Validator

    schema = json.loads((FIT_CHECK / "schemas" / "verdict.json").read_text(encoding="utf-8"))
    base = {"verdict": "fits", "assessed_work": "Reviewing vendor contracts", "reasons": [{"row": "coordination", "leans": "baton", "basis": "stated", "reason": "r"}], "next_step": "n"}
    ok = Draft202012Validator(schema)
    assert ok.is_valid(base)  # optional
    assert ok.is_valid({**base, "recipe": {"id": "backyard-project", "version": 1}})
    assert ok.is_valid({**base, "recipe": None})
    assert not ok.is_valid({**base, "recipe": {"id": "backyard-project"}})
    assert not ok.is_valid({**base, "recipe": {"id": "x", "version": 1, "extra": 1}})


def test_an_unreadable_recipe_leaves_the_optional_input_out_and_notes_it(store, monkeypatch):
    from baton import diag
    from baton.packet import EngineError

    def broken(project, with_scope=False):
        raise EngineError("recipe.invalid", "shipped recipe x is invalid")

    seen = []
    monkeypatch.setattr("baton.frame.recipe_listing", broken)
    monkeypatch.setattr(diag, "note", lambda code, where, **data: seen.append(code))
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    write_result(p, PROFILE_OUT)
    assert engine.submit(ctx, "describe").outcome == "passed"
    packet = engine.begin_attempt(ctx, "assess", "owner", WRITER)
    assert not (packet.dir / "inputs" / "recipes.json").exists()
    assert "catalog.summaries_unavailable" in seen
