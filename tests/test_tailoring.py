"""Tailoring (L6, §5.5): triage application, ``applies_to`` skipping, the triage approval, re-triage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from baton import engine
from baton.packet import EngineError, view_of
from baton.recipe import load_recipe
from baton.store import Store

from runkit import WRITER, Clock, write_result

SCHEMA = "https://json-schema.org/draft/2020-12/schema"
LEVELS = ["minor", "standard", "major"]
TRIAGE = {"type": "object", "required": ["level"], "properties": {"level": {"enum": LEVELS}, "reasons": {"type": "array", "items": {"type": "string"}}}}
OBJ = {"type": "object"}


def write_recipe(root: Path, steps: list[dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "schemas").mkdir(exist_ok=True)
    for name, schema in {"triage.json": TRIAGE, "obj.json": OBJ}.items():
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
    doc = {
        "id": "tailor", "version": 1, "format": "baton-recipe/1", "capabilities_vocab": "baton-capabilities/1",
        "complexity": {"levels": LEVELS, "triage_step": "triage"}, "steps": steps,
    }
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


def tailor_recipe(root: Path) -> Path:
    """triage -> spec [standard, major] -> design [major]; build after all (its human gate only at major);
    extras [major] is a group; polish runs at every level with a [major]-only step inside."""
    return write_recipe(
        root,
        [
            {"id": "triage", "output_schema": "schemas/triage.json", "gates": [{"type": "schema"}]},
            {"id": "spec", "depends_on": ["triage"], "applies_to": ["standard", "major"],
             "gates": [{"type": "schema"}, {"type": "human", "applies_to": ["major"], "prompt": "Approve the spec?"}]},
            {"id": "design", "depends_on": ["spec"], "applies_to": ["major"]},
            {"id": "build", "depends_on": ["triage", "spec", "design"],
             "gates": [{"type": "human", "applies_to": ["major"], "prompt": "Accept the build?"}]},
            {"id": "extras", "depends_on": ["triage"], "applies_to": ["major"], "steps": [{"id": "garnish"}]},
            {"id": "polish", "depends_on": ["build"], "steps": [{"id": "sand"}, {"id": "varnish", "depends_on": ["sand"], "applies_to": ["major"]}]},
        ],
    )


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


@pytest.fixture
def ctx(store, tmp_path):
    return engine.start(store, load_recipe(tailor_recipe(tmp_path / "recipe")), {"title": "Garden"}, run_id="r_20261102_tail")


def run_step(ctx, path: str, output: Any):
    p = engine.begin_attempt(ctx, path, "owner", WRITER)
    write_result(p, output)
    return p, engine.submit(ctx, path)


def events(ctx, etype: str) -> list[Any]:
    return [e for e in ctx.log.events() if e.type == etype]


def state(ctx, path: str) -> str:
    return view_of(ctx).state(path)


def ready(ctx) -> list[str]:
    return sorted(p for p, s in ctx.log.state().steps.items() if s.state == "ready")


def only_instance(ctx, group: str) -> str:
    exp = [e for e in events(ctx, "group_expanded") if e.step_path == group][-1]
    return exp.data["items"][0]["id"]


def test_steps_with_applies_to_wait_for_triage(ctx):
    assert ready(ctx) == ["triage"]
    assert state(ctx, "spec") == "blocked_on_deps" and state(ctx, "extras") == "blocked_on_deps"
    assert ctx.record().level() is None


def test_lowest_level_is_applied_at_once_and_excluded_steps_are_skipped(ctx):
    _, out = run_step(ctx, "triage", {"level": "minor", "reasons": ["one bed of flowers"]})
    assert out.outcome == "passed"
    (cs,) = events(ctx, "complexity_set")
    assert cs.data == {"level": "minor", "approval": "auto", "reasons": ["one bed of flowers"]}
    skipped = {e.step_path: e.data for e in events(ctx, "step_skipped")}
    assert set(skipped) == {"spec", "design", "extras"}  # the group is skipped as one
    assert skipped["extras"] == {"level": "minor", "cause": "complexity"}
    assert state(ctx, "extras") == "skipped"
    assert ready(ctx) == ["build"]  # skipped dependencies count as satisfied
    _, out = run_step(ctx, "build", {})
    assert out.outcome == "passed"  # its human gate applies only at major
    inst = only_instance(ctx, "polish")
    _, out = run_step(ctx, f"polish/{inst}/i1/sand", {})
    assert state(ctx, f"polish/{inst}/i1/varnish") == "skipped"  # in a group: marked when the iteration runs
    assert out.run_completed
    assert engine.pending_decisions(ctx) == []


def test_above_lowest_level_waits_for_the_owner_and_reject_retries(ctx):
    _, out = run_step(ctx, "triage", {"level": "major", "reasons": ["a shed needs a permit"]})
    assert out.outcome == "needs_human"
    assert "'major'" in out.reasons[0] and "a shed needs a permit" in out.reasons[0]
    (pd,) = engine.pending_decisions(ctx)
    assert pd["ref"] == "triage" and pd["kind"] == "gate" and pd["options"] == ["approve", "reject"]
    assert events(ctx, "complexity_set") == []
    assert state(ctx, "spec") == "blocked_on_deps"

    out = engine.decide(ctx, "triage", "reject", "It is only a small shed kit, standard at most")
    assert out.outcome == "retry"
    p, out = run_step(ctx, "triage", {"level": "standard"})
    assert "standard at most" in json.dumps(p.manifest["prior_feedback"])
    assert out.outcome == "needs_human"
    out = engine.decide(ctx, "triage", "approve", "Agreed")
    assert out.outcome == "passed"
    (cs,) = events(ctx, "complexity_set")
    assert cs.data["level"] == "standard" and cs.data["approval"] == "owner" and isinstance(cs.data["decision_seq"], int)
    assert {e.step_path for e in events(ctx, "step_skipped")} == {"design", "extras"}
    assert ready(ctx) == ["spec"]


def _to_standard_with_spec_passed(ctx):
    run_step(ctx, "triage", {"level": "standard"})
    engine.decide(ctx, "triage", "approve", "")
    run_step(ctx, "spec", {})
    assert ready(ctx) == ["build"]


def test_retriage_adds_future_steps_only(ctx):
    _to_standard_with_spec_passed(ctx)
    out = engine.retriage(ctx, "the owner now wants a full shed")
    assert out.outcome == "retriage_requested" and out.ready == ["triage"]
    with pytest.raises(EngineError) as e:
        engine.begin_attempt(ctx, "build", "owner", WRITER)
    assert e.value.code == "packet.deps_unmet"  # nothing after triage starts while it is re-assessed
    p, out = run_step(ctx, "triage", {"level": "major"})
    rev = p.manifest["prior_feedback"]["revision"]
    assert rev["reason"] == "the owner now wants a full shed"
    assert json.loads((p.dir / rev["output"]).read_text()) == {"level": "standard"}
    assert out.outcome == "needs_human" and "instead of 'standard'" in out.reasons[0]
    out = engine.decide(ctx, "triage", "approve", "yes, a shed")
    (ra,) = events(ctx, "retriage_applied")
    assert ra.data["level"] == "major" and ra.data["previous_level"] == "standard"
    assert sorted(ra.data["unskipped"]) == ["design", "extras"]
    assert ra.data["skipped"] == []
    assert ra.data["pre_retriage"] == ["spec"]  # passed without the human gate major would have added
    assert ctx.record().level() == "major"
    assert state(ctx, "spec") == "passed"  # passed steps never change
    assert "design" in ready(ctx) and state(ctx, "build") == "ready"
    assert state(ctx, "extras") != "skipped"
    assert events(ctx, "step_stale") == []  # re-triage makes nothing stale


def test_retriage_down_skips_steps_not_started(ctx):
    run_step(ctx, "triage", {"level": "standard"})
    engine.decide(ctx, "triage", "approve", "")
    assert ready(ctx) == ["spec"]  # ready, never dispatched
    engine.retriage(ctx, "it turned out to be a single flower bed")
    run_step(ctx, "triage", {"level": "minor"})
    out = engine.decide(ctx, "triage", "approve", "fine")
    (ra,) = events(ctx, "retriage_applied")
    assert ra.data["skipped"] == ["spec"] and ra.data["unskipped"] == []
    assert state(ctx, "spec") == "skipped"
    assert ready(ctx) == ["build"]


def test_retriage_reject_keeps_the_level_and_the_earlier_result(ctx):
    _to_standard_with_spec_passed(ctx)
    before = ctx.record().registered("triage")
    engine.retriage(ctx, "maybe bigger")
    run_step(ctx, "triage", {"level": "major"})
    out = engine.decide(ctx, "triage", "reject", "no, keep it standard")
    assert out.outcome == "retriage_rejected"
    assert ctx.record().level() == "standard"
    assert ctx.record().registered("triage")["output_sha256"] == before["output_sha256"]
    passed = ctx.record().last("step_passed", "triage")
    assert passed.data["retriage_rejected"]["previous_seq"] < passed.seq
    assert events(ctx, "retriage_applied") == []
    assert engine.pending_retriage(ctx.log.events()) is None
    assert ready(ctx) == ["build"]


def test_retriage_refusals(ctx):
    with pytest.raises(EngineError) as e:
        engine.retriage(ctx, "too early")
    assert e.value.code == "retriage.no_level"
    run_step(ctx, "triage", {"level": "standard"})
    engine.decide(ctx, "triage", "approve", "")
    with pytest.raises(EngineError) as e:
        engine.retriage(ctx, " ")
    assert e.value.code == "retriage.reason_required"
    engine.begin_attempt(ctx, "spec", "owner", WRITER)
    with pytest.raises(EngineError) as e:
        engine.retriage(ctx, "while spec runs")
    assert e.value.code == "retriage.in_flight"
    with pytest.raises(EngineError) as e:
        engine.revise(ctx, "triage", "use revise")
    assert e.value.code == "revise.triage"


def test_retriage_refused_while_pending(ctx):
    run_step(ctx, "triage", {"level": "minor"})
    engine.retriage(ctx, "bigger")
    with pytest.raises(EngineError) as e:
        engine.retriage(ctx, "again")
    assert e.value.code in ("retriage.pending", "retriage.triage_not_accepted")


def test_ready_to_skipped_only_for_a_step_never_dispatched(ctx):
    from baton.state import IllegalTransition

    run_step(ctx, "triage", {"level": "standard"})
    engine.decide(ctx, "triage", "approve", "")
    p = engine.begin_attempt(ctx, "spec", "owner", WRITER)
    write_result(p, {}, status="failed")
    engine.submit(ctx, "spec")  # back to ready for attempt 2
    assert state(ctx, "spec") == "ready"
    with pytest.raises(IllegalTransition):
        ctx.log.append("step_skipped", step_path="spec")


def test_records_show_level_skips_and_pre_retriage(ctx):
    from baton import docs

    _to_standard_with_spec_passed(ctx)
    engine.retriage(ctx, "the owner now wants a full shed")
    run_step(ctx, "triage", {"level": "major"})
    engine.decide(ctx, "triage", "approve", "yes")
    rec = docs.step_record(ctx, "spec")
    assert "**pre-retriage:** accepted at level standard" in rec
    assert "skipped at level **standard** (complexity)" in docs.step_record(ctx, "design")
    assert "included again at level **major** (retriage)" in docs.step_record(ctx, "design")
    summ = docs.summary(ctx)
    assert "- Complexity level: **major**" in summ
    assert "re-triage applied: level standard → **major**" in summ
    assert "level **standard**, approved by the owner" in summ
