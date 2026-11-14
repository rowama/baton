"""Tailoring by axes (§5.5; Decisions 0144, 0147): the format, the loader, the plan, the runtime."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from baton.recipe import RecipeError, build_plan, load_recipe, render_plan

SCHEMA = "https://json-schema.org/draft/2020-12/schema"
AXES = {"discovery": ["low", "medium", "high"], "assurance": {"scale": ["low", "medium", "high"], "confirm_lowest": True}}
OBJ = {"type": "object"}


def ratings_schema(axes: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "object", "required": ["ratings"],
        "properties": {"ratings": {
            "type": "object", "required": list(axes), "additionalProperties": False,
            "properties": {a: {"type": "object", "required": ["value", "reason"], "properties": {
                "value": {"enum": scale}, "reason": {"type": "string", "minLength": 1}}} for a, scale in axes.items()},
        }},
    }


def scales_of(axes: dict[str, Any]) -> dict[str, list[str]]:
    return {a: (s if isinstance(s, list) else s["scale"]) for a, s in axes.items()}


def axes_steps() -> list[dict]:
    """triage; explore at discovery medium/high; build always (its review gate at assurance high);
    verify at assurance medium/high; checks (a group) at assurance high with a step inside at the same."""
    return [
        {"id": "triage", "output_schema": "schemas/triage.json", "gates": [{"type": "schema"}]},
        {"id": "explore", "depends_on": ["triage"], "applies_to": {"discovery": ["medium", "high"]}},
        {"id": "build", "depends_on": ["triage", "explore"],
         "gates": [{"type": "schema"}, {"type": "human", "applies_to": {"assurance": ["high"]}, "prompt": "Accept the build?"}]},
        {"id": "verify", "depends_on": ["build"], "applies_to": {"assurance": ["medium", "high"]}},
        {"id": "checks", "depends_on": ["build"], "applies_to": {"assurance": ["high"]},
         "steps": [{"id": "probe"}, {"id": "recover", "depends_on": ["probe"], "applies_to": {"assurance": ["high"]}}]},
    ]


def write_recipe(root: Path, steps: list[dict] | None = None, complexity: dict | None = None, triage_schema: dict | None = None) -> Path:
    steps = copy.deepcopy(steps if steps is not None else axes_steps())
    complexity = complexity if complexity is not None else {"axes": AXES, "triage_step": "triage"}
    root.mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "schemas").mkdir(exist_ok=True)
    tri = triage_schema if triage_schema is not None else ratings_schema(scales_of(complexity.get("axes") or {}))
    for name, schema in {"triage.json": tri, "obj.json": OBJ}.items():
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
    doc = {"id": "axes", "version": 1, "format": "baton-recipe/1", "capabilities_vocab": "baton-capabilities/1",
           "complexity": complexity, "steps": steps}
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


def codes(root: Path) -> list[str]:
    with pytest.raises(RecipeError) as e:
        load_recipe(root)
    return [i.code for i in e.value.issues if i.severity == "error"]


# -- the format and the loader (Slice 1) -----------------------------------


def test_a_recipe_with_axes_loads(tmp_path):
    loaded = load_recipe(write_recipe(tmp_path / "r"))
    cx = loaded.recipe.complexity
    assert cx.levels is None and set(cx.axes) == {"discovery", "assurance"}
    assert cx.axes["assurance"].confirm_lowest is True
    assert not [w for w in loaded.warnings if w.code.startswith("complexity.")]


def test_levels_and_axes_together_are_refused(tmp_path):
    root = write_recipe(tmp_path / "r", complexity={"levels": ["a", "b"], "axes": AXES, "triage_step": "triage"})
    assert codes(root) == ["complexity.levels_and_axes"]


def test_a_complexity_block_without_a_scale_is_refused(tmp_path):
    root = write_recipe(tmp_path / "r", complexity={"triage_step": "triage"})
    assert codes(root) == ["complexity.no_scale"]


def test_an_unknown_axis_and_an_undeclared_value_are_refused(tmp_path):
    steps = axes_steps()
    steps[1]["applies_to"] = {"discovry": ["high"]}
    steps[3]["applies_to"] = {"assurance": ["extreme"]}
    assert sorted(codes(write_recipe(tmp_path / "r", steps))) == ["complexity.unknown_axis", "complexity.unknown_level"]


def test_a_list_applies_to_in_a_recipe_with_axes_is_refused(tmp_path):
    steps = axes_steps()
    steps[1]["applies_to"] = ["high"]
    assert codes(write_recipe(tmp_path / "r", steps)) == ["complexity.applies_to_list"]


def test_a_map_applies_to_in_a_recipe_with_levels_is_refused(tmp_path):
    steps = [
        {"id": "triage", "output_schema": "schemas/triage.json"},
        {"id": "spec", "depends_on": ["triage"], "applies_to": {"level": ["major"]}},
    ]
    tri = {"type": "object", "required": ["level"], "properties": {"level": {"enum": ["minor", "major"]}}}
    root = write_recipe(tmp_path / "r", steps, {"levels": ["minor", "major"], "triage_step": "triage"}, tri)
    assert codes(root) == ["complexity.applies_to_by_axis"]


def test_level_is_a_reserved_axis_name(tmp_path):
    axes = {"level": ["low", "high"], "assurance": ["low", "high"]}
    steps = [{"id": "triage", "output_schema": "schemas/triage.json"},
             {"id": "verify", "depends_on": ["triage"], "applies_to": {"assurance": ["high"], "level": ["high"]}}]
    assert codes(write_recipe(tmp_path / "r", steps, {"axes": axes, "triage_step": "triage"})) == ["complexity.reserved_axis"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["required"].clear(),  # ratings not required
        lambda s: s["properties"]["ratings"]["required"].remove("assurance"),  # an axis not required
        lambda s: s["properties"]["ratings"].pop("additionalProperties"),  # other axes allowed
        lambda s: s["properties"]["ratings"]["properties"]["discovery"]["required"].remove("reason"),  # no reason required
        lambda s: s["properties"]["ratings"]["properties"]["discovery"]["properties"]["reason"].pop("minLength"),  # empty reason
        lambda s: s["properties"]["ratings"]["properties"]["assurance"]["properties"]["value"].update(enum=["low", "high"]),  # wrong scale
    ],
    ids=["ratings", "every-axis", "closed", "reason-required", "reason-non-empty", "scale"],
)
def test_the_triage_schema_must_constrain_every_axis_and_require_a_reason(tmp_path, mutate):
    tri = ratings_schema(scales_of(AXES))
    mutate(tri)
    assert codes(write_recipe(tmp_path / "r", triage_schema=tri)) == ["complexity.ratings_schema_mismatch"]


def test_a_nested_step_must_be_reachable_at_every_combination(tmp_path):
    steps = axes_steps()
    steps[4]["steps"][1]["applies_to"] = {"discovery": ["high"]}  # the group runs only at assurance high
    issues = codes(write_recipe(tmp_path / "r", steps))
    assert issues == ["complexity.unreachable"]


def test_a_nested_step_reachable_by_a_wider_condition_loads(tmp_path):
    steps = axes_steps()
    steps[4]["applies_to"] = {"assurance": ["high"], "discovery": ["high"]}
    steps[4]["steps"][1]["applies_to"] = {"discovery": ["high"]}  # implies the group's OR
    load_recipe(write_recipe(tmp_path / "r", steps))


def test_an_axis_nothing_applies_by_is_a_warning(tmp_path):
    axes = {**AXES, "reach": ["one", "many"]}
    loaded = load_recipe(write_recipe(tmp_path / "r", complexity={"axes": axes, "triage_step": "triage"}))
    assert [w.code for w in loaded.warnings if w.code.startswith("complexity.")] == ["complexity.axis_unused"]


def test_a_foreach_source_skippable_at_some_ratings_needs_a_policy(tmp_path):
    steps = axes_steps()
    steps.append({"id": "each", "depends_on": ["explore"], "foreach": "steps.explore.output.items", "steps": [{"id": "do"}]})
    root = write_recipe(tmp_path / "r", steps)
    (root / "schemas" / "list.json").write_text(json.dumps({"$schema": SCHEMA, "type": "object", "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}}}}), encoding="utf-8")
    doc = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
    doc["steps"][1]["output_schema"] = "schemas/list.json"
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    assert "group.foreach_source_skippable" in codes(root)


# -- the plan (Slice 1) ----------------------------------------------------


def test_the_plan_shows_what_always_runs_and_what_each_rating_adds(tmp_path):
    plan = build_plan(load_recipe(write_recipe(tmp_path / "r")))
    (always,) = plan.levels
    assert always.level is None and always.ratings is None
    assert {r.path: r.included for r in always.steps} == {
        "triage": True, "explore": False, "build": True, "verify": False, "checks": False, "checks/probe": False, "checks/recover": False,
    }
    axes = {a.name: {v.value: v.adds for v in a.values} for a in plan.axes}
    assert axes["discovery"] == {"low": [], "medium": ["step explore"], "high": ["step explore"]}
    assert axes["assurance"] == {
        "low": [], "medium": ["step verify"],
        "high": ["human gate on build", "step verify", "group checks", "step checks/recover"],
    }
    assert [a.confirm_lowest for a in plan.axes] == [False, True]
    text = render_plan(plan)
    assert "Axis assurance (low, medium, high; its lowest also asks the owner):" in text
    assert "  high: adds human gate on build; step verify; group checks; step checks/recover" in text
    assert "  low: adds nothing" in text


def test_the_plan_for_a_combination_is_the_full_table(tmp_path):
    loaded = load_recipe(write_recipe(tmp_path / "r"))
    plan = build_plan(loaded, ratings={"discovery": "low", "assurance": "high"})
    assert plan.axes is None
    (combo,) = plan.levels
    assert combo.ratings == {"discovery": "low", "assurance": "high"}
    rows = {r.path: r for r in combo.steps}
    assert {p: r.included for p, r in rows.items()} == {
        "triage": True, "explore": False, "build": True, "verify": True, "checks": True, "checks/probe": True, "checks/recover": True,
    }
    assert rows["explore"].reason == "applies to discovery: medium, high"
    assert [g.included for g in rows["build"].gates] == [True, True]
    assert any(g.implicit and g.note == "approve the ratings" for g in rows["triage"].gates)
    assert "Ratings: discovery low, assurance high" in render_plan(plan)


def test_the_lowest_combination_asks_the_owner_only_when_an_axis_guards_it(tmp_path):
    lowest = {"discovery": "low", "assurance": "low"}
    guarded = build_plan(load_recipe(write_recipe(tmp_path / "a")), ratings=lowest)
    assert any(g.implicit for g in guarded.levels[0].steps[0].gates)
    plain = {"discovery": ["low", "medium", "high"], "assurance": ["low", "medium", "high"]}
    open_ = build_plan(load_recipe(write_recipe(tmp_path / "b", complexity={"axes": plain, "triage_step": "triage"})), ratings=lowest)
    assert not any(g.implicit for g in open_.levels[0].steps[0].gates)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"ratings": {"discovery": "low"}}, "missing: assurance"),
        ({"ratings": {"discovery": "low", "assurance": "extreme"}}, "unknown rating"),
        ({"level": "low"}, "declares axes"),
    ],
)
def test_the_plan_refuses_an_incomplete_or_unknown_combination(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        build_plan(load_recipe(write_recipe(tmp_path / "r")), **kwargs)


def test_ratings_are_refused_for_a_recipe_with_levels(tmp_path):
    from baton.data import path as data_path

    loaded = load_recipe(data_path("examples") / "recipes" / "software-feature")
    with pytest.raises(ValueError, match="declares levels"):
        build_plan(loaded, ratings={"level": "minor"})


def test_baton_plan_takes_ratings(tmp_path):
    from typer.testing import CliRunner

    from baton.cli import app

    root = write_recipe(tmp_path / "r")
    res = CliRunner().invoke(app, ["plan", str(root), "--rating", "discovery=high", "--rating", "assurance=low", "--json"])
    assert res.exit_code == 0, res.output
    plan = json.loads(res.output)["plan"]
    assert plan["levels"][0]["ratings"] == {"discovery": "high", "assurance": "low"}
    res = CliRunner().invoke(app, ["plan", str(root), "--rating", "discovery"])
    assert res.exit_code != 0 and "axis=value" in res.output


# -- a rated run: triage, approval, skipping, packets, surfaces (Slice 2) ---

from baton import docs, engine  # noqa: E402
from baton.packet import view_of  # noqa: E402
from baton.store import Store  # noqa: E402

from runkit import WRITER, Clock, write_result  # noqa: E402


def rate(**values: str) -> dict:
    return {"ratings": {a: {"value": v, "reason": f"{a} is {v} here"} for a, v in values.items()}}


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def start_run(store, root: Path, run_id: str = "r_20261114_axes"):
    return engine.start(store, load_recipe(root), {"title": "Tenant fix"}, run_id=run_id)


@pytest.fixture
def ctx(store, tmp_path):
    return start_run(store, write_recipe(tmp_path / "recipe"))


@pytest.fixture
def plain_ctx(store, tmp_path):
    """The same recipe with no axis guarding its lowest rating."""
    plain = {"discovery": ["low", "medium", "high"], "assurance": ["low", "medium", "high"]}
    return start_run(store, write_recipe(tmp_path / "plain", complexity={"axes": plain, "triage_step": "triage"}), "r_20261114_plai")


def run_step(ctx, path: str, output: Any, **result: Any):
    p = engine.begin_attempt(ctx, path, "owner", WRITER)
    write_result(p, output, **result)
    return p, engine.submit(ctx, path)


def events(ctx, etype: str) -> list[Any]:
    return [e for e in ctx.log.events() if e.type == etype]


def state(ctx, path: str) -> str:
    return view_of(ctx).state(path)


def ready(ctx) -> list[str]:
    return sorted(p for p, s in ctx.log.state().steps.items() if s.state == "ready")


@pytest.mark.parametrize(
    "output",
    [
        {"ratings": {"discovery": {"value": "low", "reason": "known fix"}}},  # an axis missing
        {"ratings": {"discovery": {"value": "low", "reason": "known fix"}, "assurance": {"value": "high"}}},  # a reason missing
        {"ratings": {"discovery": {"value": "low", "reason": ""}, "assurance": {"value": "high", "reason": "auth"}}},  # an empty reason
    ],
    ids=["axis", "reason", "empty-reason"],
)
def test_a_missing_axis_or_reason_fails_the_schema_gate(ctx, output):
    _, out = run_step(ctx, "triage", output)
    assert out.outcome != "passed"
    assert events(ctx, "complexity_set") == []
    (rejected,) = events(ctx, "result_rejected")
    assert rejected.data["output_schema"] == "failed" and out.outcome == "retry"


def test_all_lowest_applies_at_once_when_no_axis_guards_it(plain_ctx):
    ctx = plain_ctx
    _, out = run_step(ctx, "triage", rate(discovery="low", assurance="low"))
    assert out.outcome == "passed"
    (cs,) = events(ctx, "complexity_set")
    assert cs.data == {"ratings": {"discovery": "low", "assurance": "low"}, "approval": "auto",
                       "reasons": {"discovery": "discovery is low here", "assurance": "assurance is low here"}}
    skipped = {e.step_path: e.data for e in events(ctx, "step_skipped")}
    assert set(skipped) == {"explore", "verify", "checks"}
    assert skipped["verify"] == {"ratings": {"discovery": "low", "assurance": "low"}, "cause": "complexity"}
    assert ctx.record().ratings() == {"discovery": "low", "assurance": "low"} and ctx.record().level() is None
    assert ready(ctx) == ["build"]
    _, out = run_step(ctx, "build", {})
    assert out.outcome == "passed"  # its human gate applies only at assurance high
    assert ctx.log.state().state == "completed"


def test_confirm_lowest_asks_the_owner_even_at_all_lowest(ctx):
    _, out = run_step(ctx, "triage", rate(discovery="low", assurance="low"))
    assert out.outcome == "needs_human"
    assert events(ctx, "complexity_set") == []
    (pending,) = engine.pending_decisions(ctx)
    assert pending["ref"] == "triage" and pending["kind"] == "gate"
    assert "discovery low (discovery is low here); assurance low (assurance is low here)" in pending["prompt"]


def test_one_owner_gate_approves_the_whole_set(ctx):
    _, out = run_step(ctx, "triage", rate(discovery="low", assurance="high"))
    assert out.outcome == "needs_human"
    (opened,) = [e for e in events(ctx, "human_gate_opened") if e.data.get("gate") == "triage"]
    assert opened.data["ratings"] == {"discovery": "low", "assurance": "high"} and "level" not in opened.data
    out = engine.decide(ctx, "triage", "approve", "Yes, it touches tenant access")
    assert out.outcome == "passed"
    (cs,) = events(ctx, "complexity_set")
    assert cs.data["ratings"] == {"discovery": "low", "assurance": "high"} and cs.data["approval"] == "owner"
    assert cs.data["reasons"]["assurance"] == "assurance is high here" and isinstance(cs.data["decision_seq"], int)
    assert {e.step_path for e in events(ctx, "step_skipped")} == {"explore"}  # OR: assurance high adds verify and checks
    assert ready(ctx) == ["build"]
    _, out = run_step(ctx, "build", {})
    assert out.outcome == "needs_human"  # the human gate at assurance high


def test_rejecting_the_ratings_retries_triage_with_the_note(ctx):
    run_step(ctx, "triage", rate(discovery="high", assurance="high"))
    out = engine.decide(ctx, "triage", "reject", "It is a one-line change; discovery is low")
    assert events(ctx, "complexity_set") == []
    (failed,) = [e for e in events(ctx, "gate_failed") if e.data.get("gate") == "triage"]
    assert failed.data["reasons"] == ["the owner did not approve the ratings: It is a one-line change; discovery is low"]
    p = engine.begin_attempt(ctx, "triage", "owner", WRITER)
    assert "discovery is low" in json.dumps(p.manifest["prior_feedback"])


def test_a_gate_applies_when_any_listed_axis_matches(store, tmp_path):
    steps = axes_steps()
    steps[2]["gates"][1]["applies_to"] = {"assurance": ["high"], "discovery": ["high"]}
    ctx = start_run(store, write_recipe(tmp_path / "r", steps))
    run_step(ctx, "triage", rate(discovery="high", assurance="medium"))
    engine.decide(ctx, "triage", "approve", "")
    run_step(ctx, "explore", {})
    _, out = run_step(ctx, "build", {})
    assert out.outcome == "needs_human"  # discovery high matched, though assurance is medium


def test_packets_and_instructions_carry_the_ratings(ctx):
    p, _ = run_step(ctx, "triage", rate(discovery="medium", assurance="high"))
    assert "ratings" in p.manifest and p.manifest["ratings"] is None  # before triage, none are set
    engine.decide(ctx, "triage", "approve", "")
    p = engine.begin_attempt(ctx, "explore", "owner", WRITER)
    assert p.manifest["ratings"] == {"discovery": "medium", "assurance": "high"}
    text = (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "This work was rated discovery medium, assurance high" in text


def test_a_one_axis_packet_has_no_ratings_field(tmp_path, store):
    import test_tailoring

    ctx1 = engine.start(store, load_recipe(test_tailoring.tailor_recipe(tmp_path / "one")), {"title": "Garden"}, run_id="r_20261114_one1")
    p = engine.begin_attempt(ctx1, "triage", "owner", WRITER)
    assert "ratings" not in p.manifest
    assert "## Ratings" not in (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")


def test_records_and_the_summary_show_the_ratings(ctx):
    run_step(ctx, "triage", rate(discovery="low", assurance="high"))
    engine.decide(ctx, "triage", "approve", "")
    assert "skipped at ratings **discovery low, assurance high** (complexity)" in docs.step_record(ctx, "explore")
    summ = docs.summary(ctx)
    assert "- Ratings:\n  - discovery: **low** (discovery is low here)\n  - assurance: **high** (assurance is high here)" in summ
    assert "ratings **discovery low, assurance high**, approved by the owner" in summ


@pytest.mark.slow
def test_status_board_and_explain_show_the_ratings(tmp_path):
    from projectkit import Cli, git, make_git_project, make_home, packet_dir
    from projectkit import write_result as play

    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project))
    cli.run("vendor", str(write_recipe(tmp_path / "axes")))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    run = cli.run("start", "axes", "--title", "Tenant fix", "--inputs", json.dumps({"title": "Tenant fix"}))["run_id"]
    out = cli.run("explain", run)
    assert out["ratings"] is None and "The ratings are not set yet; what remains depends on triage." in out["text"]
    cli.run("dispatch", run, "triage", "--worker", "owner")
    play(packet_dir(project, run, "triage", 1), rate(discovery="low", assurance="medium"))
    cli.run("submit", run, "triage", expect=4)  # waits on the owner
    cli.run("decide", run, "triage", "approve", "--note", "fine")
    st = cli.run("status", run)
    assert st["ratings"] == {"discovery": "low", "assurance": "medium"} and st["level"] is None
    (row,) = cli.run("board")["runs"]
    assert row["ratings"] == {"discovery": "low", "assurance": "medium"}
    out = cli.run("explain", run)
    assert out["ratings"] == {"discovery": "low", "assurance": "medium"}
    assert out["axes"] == {"discovery": ["low", "medium", "high"], "assurance": ["low", "medium", "high"]}
    assert out["text"].startswith(f"{run} (Tenant fix), recipe axes@1 rated discovery low, assurance medium: active.")
    assert "Skipped at these ratings: " in out["text"] and {d["step"] for d in out["done"]["skipped"]} == {"explore", "checks"}
    assert out["other_levels"]["assurance high"]["adds"] == ["checks"]
    assert out["other_levels"]["discovery medium"]["adds"] == ["explore"]
    assert "At assurance low: drops verify." in out["text"]
