"""Groups (L3, §5.4, §8.5): expansion, instances, iterations, judges, limits, re-expansion, revise.

Phase 8 acceptance: a three-slice plan expands to three instances run one at a
time; a code review with an open high finding starts iteration 2 whose
implement packet contains it; ``max_iterations`` escalates; revising the plan
(one slice changed, one added) re-expands correctly; instance ids are
runtime-assigned, and a revision echoing an unknown or duplicated id is
rejected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from baton import engine, groups
from baton.models import EffortConfig
from baton.packet import EngineError, view_of
from baton.recipe import RecipeError, load_recipe
from baton.state import IllegalTransition
from baton.store import Store

from runkit import WRITER, Clock, write_result

SCHEMA = "https://json-schema.org/draft/2020-12/schema"
SLICES = {
    "type": "object",
    "required": ["slices"],
    "properties": {
        "slices": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title"],
                "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "effort": {"enum": ["S", "M", "L"]}},
            },
        }
    },
}
OBJ = {"type": "object"}
CLEAN = {"findings": [], "coverage": {"complete": True}}
HIGH = {
    "findings": [
        {"id": "F1", "severity": "high", "location": "src/auth.py:42", "title": "token never expires"},
        {"id": "F2", "severity": "low", "title": "naming"},
    ],
    "coverage": {"complete": True},
}


def write_recipe(root: Path, steps: list[dict], schemas: dict[str, dict] | None = None) -> Path:
    """A recipe package with every step's prompt (groups included) and the given schemas."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "schemas").mkdir(exist_ok=True)
    for name, schema in {"slices.json": SLICES, "obj.json": OBJ, **(schemas or {})}.items():
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
    doc = {"id": "loop", "version": 1, "format": "baton-recipe/1", "capabilities_vocab": "baton-capabilities/1", "steps": steps}
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


def slice_recipe(root: Path, *, max_iterations: int = 2, concurrency: int = 1, accept: dict | None = None, extra_top: list[dict] | None = None) -> Path:
    """plan -> slices (foreach, repeat_until review) -> wrap (consumes steps.slices.outputs)."""
    steps = [
        {"id": "plan", "output_schema": "schemas/slices.json", "gates": [{"type": "schema"}]},
        {
            "id": "slices",
            "title": "Deliver each slice",
            "depends_on": ["plan"],
            "foreach": "steps.plan.output.slices",
            "concurrency": concurrency,
            "repeat_until": "group.steps.review.gates.passed",
            "repeat_from": "implement",
            "max_iterations": max_iterations,
            "steps": [
                {
                    "id": "implement",
                    "effort_from": "item.effort",
                    "inputs": [
                        {"name": "slice", "from": "item", "required": True},
                        {"name": "open_findings", "from": "group.previous_iteration.findings", "required": False},
                    ],
                },
                {
                    "id": "review",
                    "depends_on": ["implement"],
                    "output_schema": "baton:findings",
                    "inputs": [
                        {"name": "slice", "from": "item", "required": True},
                        {"name": "change", "from": "group.steps.implement.output", "required": True},
                    ],
                    "gates": [{"type": "findings", "block_on": ["critical", "high"]}],
                },
                {"id": "accept", "depends_on": ["review"], **(accept or {})},
            ],
        },
        {"id": "wrap", "depends_on": ["slices"], "inputs": [{"name": "delivered", "from": "steps.slices.outputs", "required": True}]},
        *(extra_top or []),
    ]
    return write_recipe(root, steps)


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def begin(ctx, path: str):
    return engine.begin_attempt(ctx, path, "owner", WRITER)


def run_step(ctx, path: str, output: Any, **kw):
    p = begin(ctx, path)
    write_result(p, output, **kw)
    return p, engine.submit(ctx, path)


def expansions(ctx, group: str = "slices") -> list[dict]:
    return [e.data for e in ctx.log.events() if e.type == "group_expanded" and e.step_path == group]


def ids(ctx, group: str = "slices") -> list[str]:
    return [i["id"] for i in expansions(ctx, group)[-1]["items"]]


def ready(ctx) -> list[str]:
    view = view_of(ctx)
    return sorted(p for p, s in ctx.log.state().steps.items() if s.state == "ready" and view.live_reason(p) is None)


def state(ctx, path: str) -> str:
    return view_of(ctx).state(path)


def inputs_of(packet) -> dict[str, Any]:
    out = {}
    for i in packet.manifest["inputs"]:
        raw = (packet.dir / i["path"]).read_bytes()
        out[i["name"]] = json.loads(raw) if i["kind"] == "json" else raw
    return out


def plan3(ctx, slices=None):
    slices = slices or [{"title": "Login", "effort": "S"}, {"title": "Logout", "effort": "M"}, {"title": "Reset", "effort": "L"}]
    return run_step(ctx, "plan", {"slices": slices})


def finish_instance(ctx, inst: str, it: int = 1) -> None:
    base = f"slices/{inst}/i{it}"
    run_step(ctx, f"{base}/implement", {"commit_sha": f"c-{inst}-{it}"})
    run_step(ctx, f"{base}/review", CLEAN)
    run_step(ctx, f"{base}/accept", {"accepted": True})


def start_run(store, recipe: Path, inputs: dict | None = None):
    return engine.start(store, load_recipe(recipe), inputs or {"title": "Auth"}, run_id="r_20261101_gr01")


# -- acceptance: expansion, one at a time ----------------------------------------


def test_three_slices_expand_to_three_instances_run_one_at_a_time(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    _, out = plan3(ctx)
    assert out.outcome == "passed"
    exp = expansions(ctx)
    assert len(exp) == 1 and exp[0]["mode"] == "foreach"
    insts = ids(ctx)
    assert len(insts) == 3 and len(set(insts)) == 3
    assert all(re.fullmatch(r"x[0-9a-f]{7}", i) for i in insts)  # opaque runtime tokens (§5.8)
    assert [i["title"] for i in exp[0]["items"]] == ["Login", "Logout", "Reset"]
    # Only the first instance has started (concurrency 1).
    assert ready(ctx) == [f"slices/{insts[0]}/i1/implement"]
    assert out.ready == [f"slices/{insts[0]}/i1/implement"]
    started = [e.step_path for e in ctx.log.events() if e.type == "iteration_started"]
    assert started == [f"slices/{insts[0]}"]

    for n, inst in enumerate(insts):
        p = begin(ctx, f"slices/{inst}/i1/implement")
        assert inputs_of(p)["slice"]["id"] == inst  # the item carries its runtime id
        node = groups.locate(ctx.recipe, p.step_path).node
        assert engine.resolve_effort(ctx, node, EffortConfig(), p.step_path) == (["S", "M", "L"][n], "effort_from")
        assert [na["name"] for na in p.manifest["not_applicable"]] == ["open_findings"]
        write_result(p, {"commit_sha": f"c{n}"})
        engine.submit(ctx, f"slices/{inst}/i1/implement")
        # While this instance runs, no later instance has started.
        started = [e.step_path for e in ctx.log.events() if e.type == "iteration_started"]
        assert started == [f"slices/{i}" for i in insts[: n + 1]]
        p = begin(ctx, f"slices/{inst}/i1/review")
        assert inputs_of(p)["change"] == {"commit_sha": f"c{n}"}
        write_result(p, CLEAN)
        engine.submit(ctx, f"slices/{inst}/i1/review")
        assert ready(ctx) == [f"slices/{inst}/i1/accept"]
        run_step(ctx, f"slices/{inst}/i1/accept", {"accepted": True})
        if n < 2:
            assert ready(ctx) == [f"slices/{insts[n + 1]}/i1/implement"]
    assert state(ctx, "slices") == "passed"
    assert ready(ctx) == ["wrap"]
    p = begin(ctx, "wrap")
    delivered = inputs_of(p)["delivered"]
    assert [d["id"] for d in delivered] == insts
    assert [d["item"]["title"] for d in delivered] == ["Login", "Logout", "Reset"]
    assert delivered[1]["outputs"] == {"implement": {"commit_sha": "c1"}, "review": CLEAN, "accept": {"accepted": True}}
    write_result(p, {})
    out = engine.submit(ctx, "wrap")
    assert out.run_completed


def test_concurrency_two_starts_two_instances(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", concurrency=2))
    plan3(ctx)
    a, b, c = ids(ctx)
    assert ready(ctx) == sorted([f"slices/{a}/i1/implement", f"slices/{b}/i1/implement"])
    finish_instance(ctx, b)
    assert f"slices/{c}/i1/implement" in ready(ctx)


def test_empty_foreach_passes_the_group(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    run_step(ctx, "plan", {"slices": []})
    assert state(ctx, "slices") == "passed" and ready(ctx) == ["wrap"]


# -- acceptance: an open high finding starts iteration 2 ------------------------------


def test_open_high_finding_starts_iteration_two_with_the_finding(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=3))
    plan3(ctx)
    inst = ids(ctx)[0]
    base = f"slices/{inst}"
    run_step(ctx, f"{base}/i1/implement", {"commit_sha": "c1"})
    _, out = run_step(ctx, f"{base}/i1/review", HIGH)
    assert out.outcome == "next_iteration"
    assert out.reasons == ["open high finding F1: token never expires (src/auth.py:42)"]
    rec = [e.data for e in ctx.log.events() if e.type == "findings_recorded"]
    assert rec == [{"gate": 0, "counts": {"high": 1, "low": 1}, "open": ["F1", "F2"], "blocking": ["F1"], "partial": False}]
    # The judge's result is kept; accept never starts in iteration 1; iteration 2 starts at implement.
    assert ctx.log.state().step(f"{base}/i1/review").state == "passed"
    assert ctx.log.state().step(f"{base}/i1/accept").state == "blocked_on_deps"
    assert ready(ctx) == [f"{base}/i2/implement"]
    it = [e.data for e in ctx.log.events() if e.type == "iteration_started" and e.step_path == base]
    assert it[-1] == {"iteration": 2, "from": "implement", "budget_base": 0, "after": f"{base}/i1/review"}

    p = begin(ctx, f"{base}/i2/implement")
    found = inputs_of(p)["open_findings"]
    assert found["iteration"] == 1
    assert [f["id"] for f in found["findings"]] == ["F1", "F2"] and found["findings"][0]["step"] == "review"
    assert found["gate_reasons"] == ["open high finding F1: token never expires (src/auth.py:42)"]
    assert "token never expires" in (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    write_result(p, {"commit_sha": "c2"})
    engine.submit(ctx, f"{base}/i2/implement")
    p = begin(ctx, f"{base}/i2/review")
    assert inputs_of(p)["change"] == {"commit_sha": "c2"}  # the sibling in the same iteration
    write_result(p, CLEAN)
    engine.submit(ctx, f"{base}/i2/review")
    run_step(ctx, f"{base}/i2/accept", {})
    assert view_of(ctx).instance_state(load_recipe(tmp_path / "r").recipe.steps[1], "slices", inst) == "passed"
    assert ready(ctx) == [f"slices/{ids(ctx)[1]}/i1/implement"]
    # The aggregate is described plainly.
    info = groups.describe(view_of(ctx), ctx.recipe.recipe.steps[1], "slices")
    assert groups.summary_line(info, ctx.recipe.recipe.steps[1]).startswith("3 instances: 1 passed, 1 active, 1 not started")


def test_partial_coverage_is_recorded(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    plan3(ctx)
    base = f"slices/{ids(ctx)[0]}/i1"
    run_step(ctx, f"{base}/implement", {})
    run_step(ctx, f"{base}/review", {"findings": [], "coverage": {"complete": False, "notes": "no socket tests"}})
    rec = next(e.data for e in ctx.log.events() if e.type == "findings_recorded")
    assert rec["partial"] is True and rec["coverage_notes"] == "no socket tests"
    gate = next(e.data for e in ctx.log.events() if e.type == "gate_passed" and e.data.get("type") == "findings")
    assert gate["partial"] is True


def test_non_judge_gate_failure_is_still_an_attempt(store, tmp_path):
    """A schema-rejected review retries the review (attempts); only the judge's gates end iterations."""
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    plan3(ctx)
    base = f"slices/{ids(ctx)[0]}/i1"
    run_step(ctx, f"{base}/implement", {})
    _, out = run_step(ctx, f"{base}/review", {"findings": "not a list"})
    assert out.outcome == "retry"
    assert ctx.log.state().step(f"{base}/review").state == "ready"


def test_human_gate_rejection_on_a_judge_ends_the_iteration(store, tmp_path):
    root = write_recipe(
        tmp_path / "r",
        [
            {"id": "plan", "output_schema": "schemas/slices.json"},
            {
                "id": "slices", "depends_on": ["plan"], "foreach": "steps.plan.output.slices",
                "repeat_until": "group.steps.check.gates.passed", "max_iterations": 2,
                "steps": [
                    {"id": "build"},
                    {"id": "check", "depends_on": ["build"], "gates": [{"type": "human", "prompt": "Good enough?"}],
                     "inputs": [{"name": "prev", "from": "group.previous_iteration.findings", "required": False}]},
                ],
            },
        ],
    )
    ctx = start_run(store, root)
    run_step(ctx, "plan", {"slices": [{"title": "only"}]})
    inst = ids(ctx)[0]
    run_step(ctx, f"slices/{inst}/i1/build", {})
    _, out = run_step(ctx, f"slices/{inst}/i1/check", {})
    assert out.outcome == "needs_human"
    out = engine.decide(ctx, f"slices/{inst}/i1/check", "reject", "colours are wrong")
    assert out.outcome == "next_iteration"
    assert ready(ctx) == [f"slices/{inst}/i2/build"]  # no repeat_from: the whole group repeats
    run_step(ctx, f"slices/{inst}/i2/build", {})
    p = begin(ctx, f"slices/{inst}/i2/check")
    assert inputs_of(p)["prev"]["gate_reasons"] == ["the owner did not approve: colours are wrong"]


# -- acceptance: max_iterations escalates -------------------------------------------


def test_max_iterations_escalates_and_owner_decides(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=2))
    plan3(ctx)
    a, b, c = ids(ctx)
    for it in (1, 2):
        run_step(ctx, f"slices/{a}/i{it}/implement", {})
        _, out = run_step(ctx, f"slices/{a}/i{it}/review", HIGH)
    assert out.outcome == "iteration_limit"
    lim = [e for e in ctx.log.events() if e.type == "iteration_limit_reached"]
    assert len(lim) == 1 and lim[0].step_path == f"slices/{a}"
    assert lim[0].data["iteration"] == 2 and lim[0].data["max_iterations"] == 2
    assert ready(ctx) == []  # the escalated instance holds the only slot
    assert state(ctx, "slices") == "active"
    pending = engine.pending_decisions(ctx)
    assert [(p["ref"], p["kind"], p["options"]) for p in pending] == [(f"slices/{a}", "iteration_limit", ["retry", "abandon"])]
    with pytest.raises(EngineError) as e:
        engine.decide(ctx, f"slices/{a}", "approve")
    assert e.value.code == "decide.bad_decision"

    # retry: a fresh budget of max_iterations, starting at repeat_from, with the owner's note.
    out = engine.decide(ctx, f"slices/{a}", "retry", "try a sliding expiry")
    assert out.outcome == "next_iteration" and engine.pending_decisions(ctx) == []
    assert ready(ctx) == [f"slices/{a}/i3/implement"]
    p = begin(ctx, f"slices/{a}/i3/implement")
    assert inputs_of(p)["open_findings"]["owner_note"] == "try a sliding expiry"
    write_result(p, {})
    engine.submit(ctx, f"slices/{a}/i3/implement")
    _, out = run_step(ctx, f"slices/{a}/i3/review", HIGH)
    assert out.outcome == "next_iteration"  # iteration 1 of the new budget of 2
    run_step(ctx, f"slices/{a}/i4/implement", {})
    _, out = run_step(ctx, f"slices/{a}/i4/review", HIGH)
    assert out.outcome == "iteration_limit"

    # abandon: the instance stops, the next one starts, and the group can no longer pass.
    out = engine.decide(ctx, f"slices/{a}", "abandon", "drop it")
    assert out.outcome == "abandoned"
    assert view_of(ctx).instance_state(ctx.recipe.recipe.steps[1], "slices", a) == "abandoned"
    assert ready(ctx) == [f"slices/{b}/i1/implement"]
    finish_instance(ctx, b)
    finish_instance(ctx, c)
    assert state(ctx, "slices") == "active" and ready(ctx) == []
    with pytest.raises(EngineError) as e:
        engine.decide(ctx, f"slices/{a}", "retry")
    assert e.value.code == "decide.nothing_pending"


# -- acceptance: revising the plan re-expands ----------------------------------------


def test_revising_the_plan_reexpands_by_echoed_ids(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    plan3(ctx)
    a, b, c = ids(ctx)
    finish_instance(ctx, a)
    finish_instance(ctx, b)
    assert ready(ctx) == [f"slices/{c}/i1/implement"]

    out = engine.revise(ctx, "plan", "Logout must also revoke refresh tokens; Reset moves to its own work item")
    assert out.outcome == "revised" and out.ready == ["plan"]
    assert ctx.log.state().step("plan").state == "ready"
    # The group fed by the plan is not marked stale: re-expansion judges each instance.
    assert not any(e.type == "step_stale" for e in ctx.log.events())
    assert ready(ctx) == ["plan"]  # instances wait while their source is being revised

    p = begin(ctx, "plan")
    prev = json.loads((p.dir / "previous" / "output.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in prev["slices"]] == [a, b, c]  # previous items with their runtime ids
    rev = p.manifest["prior_feedback"]["revision"]
    assert rev["reason"].startswith("Logout must") and rev["items"] == "output.slices"
    text = (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "## Revision" in text and "Echo the `id`" in text
    write_result(p, {"slices": [
        {"id": a, "title": "Login", "effort": "S"},                       # kept
        {"id": b, "title": "Logout + revoke", "effort": "M"},             # changed
        {"title": "Audit log", "effort": "S"},                            # added
    ]})                                                                   # c dropped
    engine.submit(ctx, "plan")

    exp = expansions(ctx)[-1]
    d = exp["added"][0]
    assert (exp["kept"], exp["changed"], exp["superseded"]) == ([a], [b], [c])
    assert ids(ctx) == [a, b, d] and d not in (a, b, c)
    view = view_of(ctx)
    group = ctx.recipe.recipe.steps[1]
    assert [view.instance_state(group, "slices", i) for i in (a, b, c, d)] == ["passed", "active", "superseded", "not_started"]
    # The kept instance is untouched; the changed one's accepted work is stale and re-runs in order.
    assert ctx.log.state().step(f"slices/{a}/i1/accept").state == "passed"
    stale = sorted(e.step_path for e in ctx.log.events() if e.type == "step_stale")
    assert stale == sorted(f"slices/{b}/i1/{s}" for s in ("implement", "review", "accept"))
    assert ready(ctx) == [f"slices/{b}/i1/implement"]
    p = begin(ctx, f"slices/{b}/i1/implement")
    assert inputs_of(p)["slice"] == {"id": b, "title": "Logout + revoke", "effort": "M"}
    write_result(p, {})
    engine.submit(ctx, f"slices/{b}/i1/implement")
    run_step(ctx, f"slices/{b}/i1/review", CLEAN)
    run_step(ctx, f"slices/{b}/i1/accept", {})
    # The superseded instance never runs; the added one does.
    assert ready(ctx) == [f"slices/{d}/i1/implement"]
    assert "superseded" in (view_of(ctx).live_reason(f"slices/{c}/i1/implement") or "")
    finish_instance(ctx, d)
    assert state(ctx, "slices") == "passed"
    p = begin(ctx, "wrap")
    assert [x["id"] for x in inputs_of(p)["delivered"]] == [a, b, d]


@pytest.mark.parametrize(
    "slices, needle",
    [
        ([{"id": "x0000000", "title": "Login"}], "'x0000000' is not a current item id"),
        (None, "is used by more than one item"),
    ],
)
def test_revision_echoing_unknown_or_duplicated_id_is_rejected(store, tmp_path, slices, needle):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    plan3(ctx)
    a, _b, _c = ids(ctx)
    engine.revise(ctx, "plan", "rework")
    slices = slices or [{"id": a, "title": "Login"}, {"id": a, "title": "Login again"}]
    _, out = run_step(ctx, "plan", {"slices": slices})
    assert out.outcome == "retry"
    rejected = [e.data["reasons"] for e in ctx.log.events() if e.type == "result_rejected"]
    assert any(needle in r for r in rejected[-1])
    assert len(expansions(ctx)) == 1  # nothing re-expanded


def test_first_plan_may_not_invent_ids(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    _, out = plan3(ctx, [{"id": "x1234567", "title": "Login"}])
    assert out.outcome == "retry" and expansions(ctx) == []


def test_unchanged_revision_keeps_every_instance(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    plan3(ctx)
    a, b, c = ids(ctx)
    finish_instance(ctx, a)
    engine.revise(ctx, "plan", "re-check")
    p = begin(ctx, "plan")
    prev = json.loads((p.dir / "previous" / "output.json").read_text(encoding="utf-8"))
    write_result(p, {"slices": [{**s} for s in prev["slices"]]})  # every item echoed unchanged
    engine.submit(ctx, "plan")
    exp = expansions(ctx)
    # Echoed ids are not part of an item's content, so the output differs only by ids: kept.
    assert exp[-1]["kept"] == [a, b, c] and exp[-1]["changed"] == [] and exp[-1]["added"] == []
    assert not any(e.type == "step_stale" for e in ctx.log.events())
    assert ready(ctx) == [f"slices/{b}/i1/implement"]


# -- revise -------------------------------------------------------------------------


def test_revise_marks_only_this_runs_dependents_stale_and_reruns_them(store, tmp_path):
    root = write_recipe(
        tmp_path / "r",
        [
            {"id": "design"},
            {"id": "build", "depends_on": ["design"], "inputs": [{"name": "d", "from": "steps.design.output", "required": True}]},
            {"id": "docs", "depends_on": ["build"]},
            {"id": "other"},
        ],
    )
    ctx = start_run(store, root)
    run_step(ctx, "design", {"v": 1})
    run_step(ctx, "build", {})
    run_step(ctx, "docs", {})
    run_step(ctx, "other", {})
    assert ctx.log.state().state == "completed"

    root2 = engine.start(store, load_recipe(root), {"title": "Second"}, run_id="r_20261101_gr02")
    run_step(root2, "design", {"v": 1})

    ctx = engine.open_run(store, "r_20261101_gr01", load_recipe(root))
    with pytest.raises(IllegalTransition):  # a completed run takes no step events
        engine.revise(ctx, "design", "wrong units")
    # Use a fresh, unfinished run to revise.
    ctx = engine.start(store, load_recipe(root), {"title": "Third"}, run_id="r_20261101_gr03")
    run_step(ctx, "design", {"v": 1})
    run_step(ctx, "build", {})
    run_step(ctx, "docs", {})
    with pytest.raises(EngineError) as e:
        engine.revise(ctx, "design", "  ")
    assert e.value.code == "revise.reason_required"
    out = engine.revise(ctx, "design", "wrong units")
    assert out.ready == ["design"]
    rs = ctx.log.state()
    assert (rs.step("design").state, rs.step("build").state, rs.step("docs").state, rs.step("other").state) == ("ready", "stale", "stale", "ready")
    assert root2.log.state().step("design").state == "passed"  # other runs are never affected
    p, out = run_step(ctx, "design", {"v": 2})
    assert p.manifest["prior_feedback"]["revision"]["reason"] == "wrong units"
    assert json.loads((p.dir / "previous" / "output.json").read_text(encoding="utf-8")) == {"v": 1}
    assert out.ready == ["build"]  # stale dependents re-run once their dependencies pass
    p, _ = run_step(ctx, "build", {})
    assert inputs_of(p)["d"] == {"v": 2}
    assert p.manifest["prior_feedback"] is None
    assert ready(ctx) == ["docs", "other"]


def test_revise_refusals(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    with pytest.raises(EngineError) as e:
        engine.revise(ctx, "plan", "x")
    assert e.value.code == "revise.not_accepted"
    plan3(ctx)
    inst = ids(ctx)[0]
    begin(ctx, f"slices/{inst}/i1/implement")
    with pytest.raises(EngineError) as e:
        engine.revise(ctx, "plan", "x")
    assert e.value.code == "revise.in_flight" and f"slices/{inst}/i1/implement" in str(e.value)
    with pytest.raises(EngineError) as e:
        engine.revise(ctx, f"slices/{inst}/i1/implement", "x")
    assert e.value.code == "revise.inside_group"


def test_steps_of_a_superseded_or_waiting_instance_cannot_be_dispatched(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r"))
    plan3(ctx)
    a, b, _c = ids(ctx)
    with pytest.raises(EngineError) as e:
        begin(ctx, f"slices/{b}/i1/implement")
    assert e.value.code == "packet.not_ready"
    engine.revise(ctx, "plan", "rework")
    with pytest.raises(EngineError) as e:  # the instance's step is ready, but its group waits for the plan
        begin(ctx, f"slices/{a}/i1/implement")
    assert e.value.code == "packet.not_current"


# -- other group shapes ---------------------------------------------------------------


def test_group_without_foreach_and_with_repeat_from_after_a_first_step(store, tmp_path):
    root = write_recipe(
        tmp_path / "r",
        [
            {
                "id": "loop", "repeat_until": "group.steps.review.gates.passed", "repeat_from": "draft", "max_iterations": 3,
                "steps": [
                    {"id": "outline"},
                    {"id": "draft", "depends_on": ["outline"], "inputs": [{"name": "outline", "from": "group.steps.outline.output", "required": True}]},
                    {"id": "review", "depends_on": ["draft"], "output_schema": "baton:findings", "gates": [{"type": "findings", "block_on": ["high"]}]},
                ],
            },
        ],
    )
    ctx = start_run(store, root)
    exp = expansions(ctx, "loop")
    assert exp[0]["mode"] == "single" and len(exp[0]["items"]) == 1
    inst = ids(ctx, "loop")[0]
    run_step(ctx, f"loop/{inst}/i1/outline", {"o": 1})
    run_step(ctx, f"loop/{inst}/i1/draft", {})
    run_step(ctx, f"loop/{inst}/i1/review", HIGH)
    # Iteration 2 reruns draft and review; outline ran once, in i1, and still feeds draft.
    assert ready(ctx) == [f"loop/{inst}/i2/draft"]
    p, _ = run_step(ctx, f"loop/{inst}/i2/draft", {})
    assert inputs_of(p)["outline"] == {"o": 1}
    _, out = run_step(ctx, f"loop/{inst}/i2/review", CLEAN)
    assert out.run_completed


def test_foreach_source_skipped_once_and_skip(store, tmp_path):
    def recipe(policy: str) -> Path:
        return write_recipe(
            tmp_path / policy,
            [
                {"id": "first"},
                {"id": "plan", "depends_on": ["first"], "output_schema": "schemas/slices.json"},
                {"id": "slices", "depends_on": ["plan"], "foreach": "steps.plan.output.slices", "foreach_if_source_skipped": policy,
                 "steps": [{"id": "work", "inputs": [{"name": "item", "from": "item", "required": True}]}]},
            ],
        )

    ctx = engine.start(store, load_recipe(recipe("once")), {"title": "Tiny fix"}, run_id="r_20261101_once")
    ctx.log.append("step_skipped", step_path="plan")  # the complexity layer (Phase 11) records skips
    engine.refresh(ctx)
    exp = expansions(ctx)[-1]
    assert exp["mode"] == "once" and len(exp["items"]) == 1
    inst = exp["items"][0]["id"]
    p, out = run_step(ctx, f"slices/{inst}/i1/work", {})
    assert inputs_of(p)["item"] == {"title": "Tiny fix", "id": inst}  # item = run inputs
    assert state(ctx, "slices") == "passed"
    _, out = run_step(ctx, "first", {})
    assert out.run_completed

    ctx = engine.start(store, load_recipe(recipe("skip")), {"title": "Tiny fix"}, run_id="r_20261101_skip")
    ctx.log.append("step_skipped", step_path="plan")
    engine.refresh(ctx)
    assert expansions(ctx)[-1]["mode"] == "skip"
    assert state(ctx, "slices") == "skipped"
    _, out = run_step(ctx, "first", {})
    assert out.run_completed


def test_nested_groups(store, tmp_path):
    root = write_recipe(
        tmp_path / "r",
        [
            {"id": "plan", "output_schema": "schemas/slices.json"},
            {
                "id": "outer", "depends_on": ["plan"], "foreach": "steps.plan.output.slices",
                "steps": [
                    {"id": "split", "output_schema": "schemas/slices.json"},
                    {"id": "parts", "depends_on": ["split"], "foreach": "group.steps.split.output.slices",
                     "steps": [{"id": "part", "inputs": [{"name": "p", "from": "item", "required": True}]}]},
                    {"id": "join", "depends_on": ["parts"]},
                ],
            },
        ],
    )
    ctx = start_run(store, root)
    run_step(ctx, "plan", {"slices": [{"title": "A"}]})
    o = ids(ctx, "outer")[0]
    run_step(ctx, f"outer/{o}/i1/split", {"slices": [{"title": "A1"}, {"title": "A2"}]})
    inner = f"outer/{o}/i1/parts"
    i1, i2 = ids(ctx, inner)
    assert ready(ctx) == [f"{inner}/{i1}/i1/part"]
    p, _ = run_step(ctx, f"{inner}/{i1}/i1/part", {})
    assert inputs_of(p)["p"]["title"] == "A1"
    run_step(ctx, f"{inner}/{i2}/i1/part", {})
    assert ready(ctx) == [f"outer/{o}/i1/join"]
    _, out = run_step(ctx, f"outer/{o}/i1/join", {})
    assert out.run_completed


def test_independence_is_judged_against_the_sibling_in_the_same_instance(store, tmp_path):
    from baton.models import WorkerProfile
    from baton.routing import eligible_workers

    root = slice_recipe(tmp_path / "r")
    doc = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
    doc["steps"][1]["steps"][1]["independence"] = {"from_step": "implement", "level": "different_vendor"}
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    ctx = start_run(store, root)
    plan3(ctx)
    a = ids(ctx)[0]
    run_step(ctx, f"slices/{a}/i1/implement", {})
    other = WorkerProfile(adapter="manual", vendor="elsewhere", person="r", capabilities=["structured_output"])
    loc = groups.locate(ctx.recipe, f"slices/{a}/i1/review")
    res = eligible_workers(
        loc.node, loc.path, {"owner": WRITER, "other": other}, ctx.recipe.vocab, events=ctx.log.events(),
        source_path=groups.child_path(loc.frame, "implement"),
    )
    assert res.names() == ["other"]
    assert "independence" in res.reasons_for("owner")[0]


# -- state is derived ------------------------------------------------------------------


def test_rebuilt_cache_gives_the_same_group_state(store, tmp_path):
    ctx = start_run(store, slice_recipe(tmp_path / "r", max_iterations=2))
    plan3(ctx)
    a = ids(ctx)[0]
    run_step(ctx, f"slices/{a}/i1/implement", {})
    run_step(ctx, f"slices/{a}/i1/review", HIGH)
    before = groups.describe(view_of(ctx), ctx.recipe.recipe.steps[1], "slices")
    steps_before = {p: s.state for p, s in ctx.log.state().steps.items()}
    store.rebuild_run(ctx.run_id)
    assert groups.describe(view_of(ctx), ctx.recipe.recipe.steps[1], "slices") == before
    assert {p: s.state for p, s in ctx.log.state().steps.items()} == steps_before


# -- loader ------------------------------------------------------------------------------


def _loop_group(**kw: Any) -> dict:
    return {
        "id": "loop", "repeat_until": "group.steps.review.gates.passed", "max_iterations": 2,
        "steps": [{"id": "outline"}, {"id": "draft", "depends_on": ["outline"]}, {"id": "review", "depends_on": ["draft"]}],
        **kw,
    }


def test_judge_before_repeat_from_is_rejected(tmp_path):
    g = _loop_group(repeat_from="draft", repeat_until="group.steps.outline.gates.passed")
    root = write_recipe(tmp_path / "r", [g])
    with pytest.raises(RecipeError) as e:
        load_recipe(root)
    assert "group.judge_not_repeated" in str(e.value)


def test_first_iteration_step_depending_on_a_repeated_step_is_rejected(tmp_path):
    g = _loop_group(repeat_from="review")
    g["steps"] = [{"id": "outline"}, {"id": "draft", "depends_on": ["review"]}, {"id": "review"}]
    root = write_recipe(tmp_path / "r", [g])
    with pytest.raises(RecipeError) as e:
        load_recipe(root)
    assert "group.depends_on_repeated" in str(e.value)


# -- through the CLI: dispatch, status, decide on an instance, revise, records, checkpoints ----


def test_group_run_through_the_cli(tmp_path):
    from projectkit import Cli, git, make_git_project, make_home, packet_dir
    from projectkit import write_result as cli_result

    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project))
    cli.run("vendor", str(slice_recipe(tmp_path / "loop", max_iterations=1)))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    run = cli.run("start", "loop", "--inputs", json.dumps({"title": "Auth"}))["run_id"]

    def step(path: str, output: Any, expect: int = 0) -> dict:
        d = cli.run("dispatch", run, path, "--worker", "owner")
        cli_result(packet_dir(project, run, path, d["attempt"]), output)
        return cli.run("submit", run, path, expect=expect)

    out = step("plan", {"slices": [{"title": "Login"}, {"title": "Logout"}]})
    st = cli.run("status", run)
    a, b = [i["id"] for i in st["groups"]["slices"]["instances"]]
    assert st["steps"]["slices"] == {"state": "active", "group": True}
    assert st["ready"] == [f"slices/{a}/i1/implement"] == out["ready"]
    assert st["groups"]["slices"]["summary"].startswith("2 instances: 1 active, 1 not started")

    step(f"slices/{a}/i1/implement", {})
    out = step(f"slices/{a}/i1/review", HIGH, expect=4)  # max_iterations 1: the owner decides now
    assert out["outcome"] == "iteration_limit"
    assert out["pending_decisions"][0]["ref"] == f"slices/{a}" and out["pending_decisions"][0]["kind"] == "iteration_limit"
    assert "reached 1 iterations" in out["checkpoint"]["subject"]
    # What a completion hook would be told: the owner is needed (on_needs_human).
    api = engine.Api.open(project, home=cli.home)
    try:
        info = api._hook_info(api._ctx(run), f"slices/{a}/i1/review", 1, "d_test", None)
        res = api._attempt_result(api._ctx(run), f"slices/{a}/i1/review", 1)
    finally:
        api.close()
    assert (info["outcome"], info["needs_owner"], info["step_state"]) == ("needs_human", True, "passed")
    assert res["outcome"] == "iteration_limit"
    out = cli.run("decide", run, f"slices/{a}", "retry", "--note", "One more pass.")
    assert out["outcome"] == "next_iteration" and out["ready"] == [f"slices/{a}/i2/implement"]
    step(f"slices/{a}/i2/implement", {})
    step(f"slices/{a}/i2/review", CLEAN)
    step(f"slices/{a}/i2/accept", {})

    out = cli.run("revise", run, "plan", "--reason", "Split logout")
    assert out["outcome"] == "revised" and out["ready"] == ["plan"] and out["stale"] == []
    d = cli.run("dispatch", run, "plan", "--worker", "owner")
    prev = json.loads((Path(d["packet"]) / "previous" / "output.json").read_text(encoding="utf-8"))
    cli_result(Path(d["packet"]), {"slices": [prev["slices"][0], {"id": b, "title": "Logout (all devices)"}, {"title": "Logout (one device)"}]})
    cli.run("submit", run, "plan")
    st = cli.run("status", run)
    insts = st["groups"]["slices"]["instances"]
    assert [i["state"] for i in insts] == ["passed", "active", "not_started"]

    docs = project / ".baton" / "runs" / run / "docs"
    summary = (docs / "SUMMARY.md").read_text(encoding="utf-8")
    assert "## Groups" in summary and "re-expanded (foreach): kept 1, changed 1, added 1, superseded 0" in summary
    assert "iteration limit reached (1); waiting for the owner" in summary
    assert (docs / "slices" / a / "i2" / "review.md").is_file()
    rec = (docs / "slices" / a / "i1" / "review.md").read_text(encoding="utf-8")
    assert "result kept, iteration not done" in rec and "findings: 1 high, 1 low" in rec
    assert not (docs / "slices.md").exists() and not (docs / "slices" / f"{a}.md").exists()
    assert cli.run("check") is not None
