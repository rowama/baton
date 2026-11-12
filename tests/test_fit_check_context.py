"""fit-check version 4: an optional project `context` input, text only (Decision 0134)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import engine
from baton.recipe import load_recipe
from baton.store import Store

from conftest import FIT_CHECK
from runkit import FIT_INPUTS, WRITER, Clock, start


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def test_version_four_declares_an_optional_context_input():
    loaded = load_recipe(FIT_CHECK)
    assert loaded.recipe.version == 4
    props = json.loads((FIT_CHECK / "schemas" / "run_inputs.json").read_text())
    assert "context" in props["properties"] and "context" not in props["required"]


def test_a_run_with_context_hands_it_to_describe_and_assess(store):
    ctx = start(store, FIT_CHECK, {**FIT_INPUTS, "context": "A half-built web app with docs/ and tests/."})
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    got = [f for f in (p.dir / "inputs").iterdir() if f.name.startswith("context")]
    assert len(got) == 1 and "web app" in got[0].read_text()


def test_a_run_without_context_behaves_as_before(store):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    assert not [f for f in (p.dir / "inputs").iterdir() if f.name.startswith("context")]


def test_context_must_be_text(store):
    with pytest.raises(Exception):
        start(store, FIT_CHECK, {**FIT_INPUTS, "context": {"files": ["a"]}})
