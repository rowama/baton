"""Packet builder (§7.1, §8.6): layout, determinism, handoff errors, refusals."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from baton import engine
from baton.models import WorkerProfile
from baton.packet import EngineError, HandoffError, packet_digest, profile_sha256, verify_packet
from baton.recipe import load_recipe
from baton.store import Store

from conftest import FIT_CHECK, SOFTWARE_FEATURE
from runkit import FIT_INPUTS, PROFILE_OUT, WRITER, Clock, artifact_recipe, make_recipe, start, write_result

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def passed_describe(store: Store):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    write_result(p, PROFILE_OUT)
    assert engine.submit(ctx, "describe").outcome == "passed"
    return ctx


# -- layout -------------------------------------------------------------------


def test_packet_layout_and_manifest(store):
    ctx = passed_describe(store)
    p = engine.begin_attempt(ctx, "assess", "owner", WRITER)
    assert p.dir == store.baton / "runs" / ctx.run_id / "steps" / "assess" / "attempt-1" / "packet"
    names = sorted(x.relative_to(p.dir).as_posix() for x in p.dir.rglob("*") if x.is_file())
    assert names == ["INSTRUCTIONS.md", "inputs/profile.json", "inputs/rubric.md", "manifest.json", "output_schema.json"]
    m = json.loads((p.dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["protocol"] == "baton-packet/1"
    assert m["recipe"] == "fit-check@2" and m["recipe_sha256"] == ctx.recipe.sha256
    assert (m["step_path"], m["attempt"], m["worker_profile"]) == ("assess", 1, "owner")
    assert [(i["name"], i["kind"], i["from"]) for i in m["inputs"]] == [
        ("profile", "json", "steps.describe.output"),
        ("rubric", "file", "static.rubric.md"),
    ]
    assert json.loads((p.dir / "inputs" / "profile.json").read_text(encoding="utf-8")) == PROFILE_OUT
    assert (p.dir / "inputs" / "rubric.md").read_bytes() == (FIT_CHECK / "static" / "rubric.md").read_bytes()
    assert m["prior_feedback"] is None and m["not_applicable"] == []
    assert any("the owner is asked" in c for c in m["exit_criteria"])
    assert p.result_dir.is_dir() and (p.result_dir / "artifacts").is_dir()
    assert verify_packet(p.dir) == (p.sha256, [])


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_packet_is_read_only(store):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    with pytest.raises(PermissionError):
        (p.dir / "INSTRUCTIONS.md").write_text("changed")
    with pytest.raises(PermissionError):
        (p.dir / "inputs" / "new.json").write_text("{}")


def test_instructions_golden(store):
    """INSTRUCTIONS.md for fit-check/assess is pinned (§17 golden files). BATON_UPDATE_GOLDEN=1 rewrites it."""
    ctx = passed_describe(store)
    p = engine.begin_attempt(ctx, "assess", "owner", WRITER)
    text = (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    golden = GOLDEN / "fit-check-assess-INSTRUCTIONS.md"
    if os.environ.get("BATON_UPDATE_GOLDEN"):
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert text == golden.read_text(encoding="utf-8")


def test_packet_records_events(store):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    tail = [(e.type, e.attempt) for e in ctx.log.events()][-4:]
    assert tail == [("worker_selected", 1), ("packet_built", 1), ("dispatched", 1), ("step_running", 1)]
    built = ctx.record().last("packet_built", "describe", 1)
    assert built.data["packet_sha256"] == p.sha256
    assert built.data["worker_profile_sha256"] == profile_sha256(WRITER)


# -- determinism --------------------------------------------------------------


def _hash_in_fresh_project(root: Path, inputs: dict, profile: WorkerProfile = WRITER) -> str:
    with Store(root, clock=Clock()) as s:
        ctx = start(s, FIT_CHECK, inputs)
        return engine.begin_attempt(ctx, "describe", "owner", profile).sha256


def test_same_state_and_profile_same_hash(tmp_path):
    assert _hash_in_fresh_project(tmp_path / "a", FIT_INPUTS) == _hash_in_fresh_project(tmp_path / "b", FIT_INPUTS)


def test_hash_covers_inputs_and_profile(tmp_path):
    base = _hash_in_fresh_project(tmp_path / "a", FIT_INPUTS)
    assert _hash_in_fresh_project(tmp_path / "b", {**FIT_INPUTS, "idea": "Something else"}) != base
    other = WRITER.model_copy(update={"tier": "standard"})
    assert _hash_in_fresh_project(tmp_path / "c", FIT_INPUTS, other) != base


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(idea=st.text(min_size=1, max_size=200), title=st.text(min_size=1, max_size=40))
@pytest.mark.slow
def test_packet_determinism_property(tmp_path_factory, idea, title):
    inputs = {"title": title, "idea": idea}
    a = _hash_in_fresh_project(tmp_path_factory.mktemp("a"), inputs)
    b = _hash_in_fresh_project(tmp_path_factory.mktemp("b"), inputs)
    assert a == b


def test_digest_algorithm():
    """The documented algorithm, independently re-derived."""
    import hashlib

    manifest = {"protocol": "baton-packet/1", "b": 1, "a": [1, 2], "packet_sha256": "ignored"}
    files = {"inputs/x.json": "1" * 64, "INSTRUCTIONS.md": "2" * 64}
    expected = hashlib.sha256(
        b"baton-packet/1\n"
        + b'{"a":[1,2],"b":1,"packet_sha256":null,"protocol":"baton-packet/1"}\n'
        + b"INSTRUCTIONS.md\x00" + b"2" * 64 + b"\n"
        + b"inputs/x.json\x00" + b"1" * 64 + b"\n"
    ).hexdigest()
    assert packet_digest(manifest, files) == expected


def test_profile_hash_ignores_secret_values():
    def with_env(env: dict) -> WorkerProfile:
        return WorkerProfile.model_validate({**WRITER.model_dump(), "auth": {"mode": "api_key", "env": env}})

    a, b = with_env({"KEY": "secret:one"}), with_env({"KEY": "secret:two"})
    assert profile_sha256(a) == profile_sha256(b)
    c = with_env({"OTHER": "secret:one"})
    assert profile_sha256(c) != profile_sha256(a)


# -- handoff errors -----------------------------------------------------------

NAMES = ["alpha", "beta", "gamma", "delta"]


def three_input_recipe(root: Path) -> Path:
    return make_recipe(
        root,
        [
            {
                "id": "work",
                "output_schema": "schemas/out.json",
                "inputs": [{"name": n, "from": f"run.inputs.{n}", "required": n != "delta"} for n in NAMES],
            }
        ],
        schemas={"out.json": {"type": "object"}},
        run_inputs={"type": "object", "properties": {n: {"type": "string"} for n in NAMES}},
    )


def test_missing_required_inputs_listed_and_nothing_written(store, tmp_path):
    ctx = start(store, three_input_recipe(tmp_path / "r"), {"beta": "b"})
    before = ctx.log.events()
    with pytest.raises(HandoffError) as ei:
        engine.begin_attempt(ctx, "work", "owner", WRITER)
    assert [m[0] for m in ei.value.missing] == ["alpha", "gamma"]  # all of them; delta is optional
    assert "alpha" in str(ei.value) and "gamma" in str(ei.value)
    assert ctx.log.events() == before
    assert not (ctx.run_dir / "steps").exists()


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(present=st.sets(st.sampled_from(NAMES)))
def test_removing_required_inputs_property(tmp_path_factory, present):
    root = tmp_path_factory.mktemp("p")
    with Store(root / "project", clock=Clock()) as s:
        ctx = start(s, three_input_recipe(root / "r"), {n: n for n in present})
        required_missing = [n for n in NAMES[:3] if n not in present]
        if required_missing:
            with pytest.raises(HandoffError) as ei:
                engine.begin_attempt(ctx, "work", "owner", WRITER)
            assert [m[0] for m in ei.value.missing] == required_missing
        else:
            p = engine.begin_attempt(ctx, "work", "owner", WRITER)
            assert sorted(i["name"] for i in p.manifest["inputs"]) == sorted(present)


def test_skipped_source_not_applicable(tmp_path):
    recipe = make_recipe(
        tmp_path / "r",
        [
            {"id": "first", "output_schema": "schemas/out.json"},
            {"id": "maybe", "depends_on": ["first"], "output_schema": "schemas/out.json"},
            {
                "id": "after",
                "depends_on": ["maybe"],
                "output_schema": "schemas/out.json",
                "inputs": [{"name": "earlier", "from": "steps.maybe.output", "required": True}],
            },
        ],
        schemas={"out.json": {"type": "object"}},
    )
    with Store(tmp_path / "p", clock=Clock()) as s:
        ctx = engine.start(s, load_recipe(recipe), {})
        ctx.log.append("step_skipped", step_path="maybe")  # what applying a complexity level does (Phase 11)
        p = engine.begin_attempt(ctx, "first", "owner", WRITER)
        write_result(p, {})
        assert engine.submit(ctx, "first").ready == ["after"]
        p = engine.begin_attempt(ctx, "after", "owner", WRITER)
        assert p.manifest["inputs"] == []
        assert [na["name"] for na in p.manifest["not_applicable"]] == ["earlier"]
        assert "Not applicable" in (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")


# -- refusals -----------------------------------------------------------------


def test_not_ready_step_refused(store):
    ctx = start(store, FIT_CHECK)
    with pytest.raises(EngineError) as ei:
        engine.begin_attempt(ctx, "assess", "owner", WRITER)
    assert ei.value.code == "packet.not_ready"


def test_ineligible_profile_refused(store):
    ctx = start(store, FIT_CHECK)
    weak = WRITER.model_copy(update={"capabilities": ["file_write"], "tier": "basic"})
    with pytest.raises(EngineError) as ei:
        engine.begin_attempt(ctx, "describe", "weak", weak)
    assert ei.value.code == "packet.ineligible_profile"
    assert "structured_output" in str(ei.value) and "tier standard" in str(ei.value)
    assert not (ctx.run_dir / "steps").exists()


def test_groups_and_non_steps_are_not_dispatched(store):
    """A group is not dispatched itself, and a path that is not a step of the recipe is refused."""
    rec = load_recipe(SOFTWARE_FEATURE)
    ctx = engine.start(store, rec, {"title": "Login", "kind": "feature", "feature_request": "Add login"}, run_id="r_x")
    for path in ("slices", "slices/implement"):
        with pytest.raises(EngineError) as ei:
            engine.begin_attempt(ctx, path, "owner", WRITER)
        assert ei.value.code == "packet.unsupported_step"


def test_run_inputs_validated_at_start(store):
    with pytest.raises(EngineError) as ei:
        start(store, FIT_CHECK, {"title": "x"})
    assert ei.value.code == "run.inputs_invalid" and "idea" in str(ei.value)


def test_open_run_checks_recipe_pin(store, tmp_path, make_recipe):
    ctx = start(store, FIT_CHECK)
    assert engine.open_run(store, ctx.run_id, load_recipe(FIT_CHECK)).run_id == ctx.run_id
    changed = make_recipe(source=FIT_CHECK, text=lambda t: t.replace("Profile the idea", "Profile it"))
    with pytest.raises(EngineError) as ei:
        engine.open_run(store, ctx.run_id, load_recipe(changed))
    assert ei.value.code == "run.recipe_mismatch"


def test_artifact_input_comes_from_cas_not_worker_files(store, tmp_path):
    ctx = start(store, artifact_recipe(tmp_path / "r"), {})
    p = engine.begin_attempt(ctx, "draft", "owner", WRITER)
    write_result(p, {}, artifacts={"doc": ("doc.md", b"# Original\n")})
    assert engine.submit(ctx, "draft").outcome == "passed"
    (p.result_dir / "artifacts" / "doc.md").write_bytes(b"# Tampered later\n")
    p2 = engine.begin_attempt(ctx, "use", "owner", WRITER)
    assert (p2.dir / "inputs" / "doc.md").read_bytes() == b"# Original\n"
    assert p2.manifest["inputs"][0]["media_type"] == "text/markdown"
