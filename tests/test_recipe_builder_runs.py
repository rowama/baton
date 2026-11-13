"""recipe-builder end to end (change 2026-11-recipe-builder, slice 5): scripted workers, a scripted Director, the real gates.

A simple run and a standard run each produce a package that ``baton plan`` accepts at every level and that
``baton recipe check`` passes, behind exactly the owner touchpoints the recipe defines.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from baton import recipe_check
from baton.recipe import load_recipe

from conftest import ROOT
from projectkit import Cli, OWNER_PROFILE, git, make_git_project, make_home, packet_dir
from realkit import ALL_CAPS, WORKER, Director, cmdline, configure, owner_does, run_events

BUILDER = ROOT / "examples" / "recipes" / "recipe-builder"
CLEAN = {"output": {"findings": [], "coverage": {"complete": True, "notes": ""}}}
INPUTS = {"title": "Flower bed", "idea": "I want to plant a flower bed properly"}
SLUG = "flower-bed"

GOAL = {"id": "G1", "statement": "A repeatable way to plant a flower bed", "kind": "goal", "scope": "class", "status": "confirmed",
        "basis": "the owner's words", "owner_words": "I want to plant a flower bed properly"}
BED = {"id": "I1", "statement": "The bed is 3 m by 1 m, in full sun", "kind": "requirement", "scope": "instance", "status": "confirmed",
       "basis": "the owner's words", "owner_words": "it is about three by one metres", "value": "3 m by 1 m, full sun"}
SOIL = {"id": "R1", "statement": "Every bed needs a soil check before planting", "kind": "requirement", "scope": "class",
        "status": "researched", "basis": "common gardening guidance", "source": "a gardening handbook"}
NONE_NEEDED = {"id": "D1", "question": "Is there an implementation choice that matters?", "target_status": "none", "timing": "not_needed",
               "timing_reason": "Planting a bed has one usual way of being done; nothing to choose between.", "status": "closed"}
STAGES = [
    {"id": "survey", "title": "Survey the site", "done_by": "person", "needs": ["the bed's location"], "hands_on": ["site notes"],
     "owner_decision": None, "on_failure": "escalate", "failure_note": "Ask the owner where the bed goes."},
    {"id": "plant", "title": "Plant the bed", "done_by": "person", "needs": ["site notes"], "hands_on": ["a planted bed"],
     "owner_decision": "Is the bed planted as wanted?", "on_failure": "revise"},
]

PACKAGE = {
    "recipe.yaml": (
        "id: flower-bed\nversion: 1\nformat: baton-recipe/1\ncapabilities_vocab: baton-capabilities/1\n"
        "description: Plant a flower bed.\nscope:\n  covers: [a flower bed]\n  not_for: []\n  varies_by: [size]\nparent: null\n"
        "run_inputs:\n  schema: schemas/run_inputs.json\nsteps:\n  - id: plant\n    title: Plant the bed\n"
        "    requires: { capabilities: [human_judgment] }\n    prompt: prompts/plant.md\n    output_schema: schemas/plant_out.json\n"
        "    gates: [ { type: schema } ]\n"
    ),
    "prompts/plant.md": "# Plant the bed\n\nPlant the bed as surveyed and report what you did.\n",
    "schemas/run_inputs.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
    "schemas/plant_out.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
}


def generated(ledger: list[dict], discovery: list[dict] | None = None) -> dict:
    files = {f"recipes/drafts/{SLUG}/{k}": v for k, v in PACKAGE.items()}
    ledger_file = json.dumps({"ledger": ledger, "discovery": discovery or [NONE_NEEDED]})
    files[f"recipes/drafts/{SLUG}.ledger.json"] = ledger_file
    return {
        "commit_files": files,
        "output": {"package_path": f"recipes/drafts/{SLUG}", "ledger_path": f"recipes/drafts/{SLUG}.ledger.json", "summary": "A flower-bed process"},
        "artifacts": {"walkthrough": "# Planting a flower bed\n\nYou survey the site, then plant it.\n", "ledger": ledger_file},
    }


def profile(level: str, ledger: list[dict]) -> dict:
    return {"output": {
        "level": level, "reasons": ["one kind of worker, nothing irreversible" if level == "simple" else "several kinds of worker"],
        "goal": {"statement": "Plant a flower bed", "trigger": "The owner wants a bed", "end_state": "A planted bed", "success_measure": "Plants are in and watered"},
        "existing_recipe": None,
        "rung": {"label": "Just flower beds", "covers": ["a flower bed"], "next_rung": "any garden bed"},
        "related_parts": [], "build_now": None, "discovery": [NONE_NEEDED], "ledger": ledger}}


def design(ledger: list[dict], summary: str = "Survey then plant") -> dict:
    return {"output": {"summary": summary, "stages": STAGES, "excluded": [], "discovery": [NONE_NEEDED], "ledger": ledger},
            "artifacts": {"design_doc": "# Planting a flower bed\n\nSurvey the site, then plant.\n"}}


def route(step_path: str) -> str:
    step = step_path.rsplit("/", 1)[-1]
    if step == "accept":
        return "owner"
    return "checker" if step in ("audit", "generate~review") else "builder"


@pytest.fixture
def project_with(tmp_path, monkeypatch):
    """A committed git project with recipe-builder vendored and scripted builder/checker workers."""
    def make(script: dict) -> tuple[Cli, Path, Path]:
        shim = tmp_path / "shim"
        shim.mkdir()
        if os.name == "nt":
            (shim / "baton.cmd").write_text(f'@"{sys.executable}" -m baton %*\n', encoding="utf-8")
        else:
            (shim / "baton").write_text(f'#!/bin/sh\nexec "{sys.executable}" -m baton "$@"\n', encoding="utf-8")
            (shim / "baton").chmod(0o755)
        # Gates run `baton plan` and `baton recipe check`: make `baton` this checkout's runtime, not whatever is installed.
        monkeypatch.setenv("PATH", str(shim) + os.pathsep + os.environ.get("PATH", ""))
        work = tmp_path / "work"
        work.mkdir()
        script_file = work / "script.json"
        script_file.write_text(json.dumps(script), encoding="utf-8")
        line = cmdline([sys.executable, str(WORKER), "{packet}", "{result}", str(script_file), "{workspace}"])
        git_dir = str(Path(shutil.which("git")).parent)
        text = OWNER_PROFILE + "".join(
            f"{name}:\n  adapter: command\n  vendor: {vendor}\n  command: {json.dumps(line)}\n"
            f"  capabilities: {json.dumps([*ALL_CAPS, 'web_access'])}\n  tier: strong\n  context_tokens: 128000\n"
            f"  path: {json.dumps({'prepend': [git_dir]})}\n"
            for name, vendor in (("builder", "acme"), ("checker", "globex")))
        project = make_git_project(tmp_path / "proj")
        (project / "README.md").write_text("# Home\n", encoding="utf-8")
        cli = Cli(project, make_home(tmp_path / "home", text))
        cli.run("init", str(project))
        cli.run("vendor", str(BUILDER))
        git(project, "add", "-A")
        git(project, "commit", "-q", "-m", "Toy project with Baton")
        return cli, project, script_file

    return make


def assert_package_is_ready(cli: Cli, project: Path) -> None:
    pkg = project / "recipes" / "drafts" / SLUG
    from baton.recipe import build_plan

    loaded = load_recipe(pkg)
    assert loaded.recipe.provenance == "scratch" and loaded.warnings == []
    assert recipe_check.check(pkg, project / "recipes" / "drafts" / f"{SLUG}.ledger.json", require_discovery=True) == []
    assert [lv.level for lv in build_plan(loaded).levels] == [None]  # the generated recipe has no scale: one plan, every step reachable
    assert not git(project, "status", "--porcelain").strip(), "the draft is committed"


@pytest.mark.slow
def test_a_simple_run_builds_a_package_behind_two_owner_touchpoints(project_with):
    ledger = [GOAL, BED]
    cli, project, script = project_with({
        "profile": profile("simple", ledger), "design": design(ledger), "audit": CLEAN, "generate": generated(ledger)})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route)
    st = d.drive()
    assert st["level"] == "simple" and st["steps"]["research"]["state"] == "skipped"
    assert [s.rsplit("/", 1)[-1] for s, _ in d.dispatches] == ["profile", "design", "audit", "generate", "accept"]
    # The owner confirms the goal and approves the finished process: nothing else at the lowest level.
    assert [r.rsplit("/", 1)[-1] for r, _ in d.owner_decisions] == ["profile", "accept"]
    # The audit was a different vendor from the design.
    assert dict((s.rsplit("/", 1)[-1], w) for s, w in d.dispatches)["audit"] == "checker"
    assert_package_is_ready(cli, project)
    evs = run_events(project, run)
    scripts = [e for e in evs if e["type"] == "gate_passed" and e["step_path"] == "generate" and e["data"].get("type") == "script"]
    assert [e["data"]["command"].split(" ")[:2] for e in scripts] == [["baton", "plan"], ["baton", "recipe"]]
    assert all(e["data"]["exit_code"] == 0 for e in scripts)
    assert not (project / "recipes" / "plans").exists()  # one process: no process plan was written
    from test_real_use import assert_clean_record

    assert_clean_record(cli, project, run)


@pytest.mark.slow
def test_a_standard_run_researches_loops_on_the_owners_note_and_fails_a_bad_ledger(project_with):
    ledger = [GOAL, BED, SOIL]
    open_entry = {"id": "Q1", "statement": "Whether the bed needs a permit", "kind": "assumption", "scope": "class", "status": "open",
                  "basis": "nobody has said"}
    script = {
        "profile": profile("standard", [GOAL, BED]),
        "research": {"output": {"discovery": [NONE_NEEDED], "ledger": ledger, "sources": [{"title": "A gardening handbook", "url": None, "what_it_supports": "R1"}]}},
        "design": [design(ledger, "Survey then plant"), design(ledger, "Survey, test the soil, then plant")],
        "audit": CLEAN,
        # attempt 1 ships a ledger with an open entry: the deterministic gate refuses it, and attempt 2 is clean.
        "generate": [generated([*ledger, open_entry]), generated(ledger)],
    }
    cli, project, _ = project_with(script)
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route, decisions={"audit": [("reject", "Add a soil test before planting."), ("approve", "That is it.")]})
    st = d.drive()
    assert st["level"] == "standard" and st["steps"]["research"]["state"] == "passed"
    # Owner touchpoints: the level, the goal, the design (twice: the first is sent back), the finished process.
    import re

    refs = [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in d.owner_decisions]  # the group's instance id is random
    assert refs == ["profile", "profile", "shape/i1/audit", "shape/i2/audit", "accept"], refs  # profile: the goal, then the level
    evs = run_events(project, run)
    # The owner's rejection started iteration 2 at design, carrying their words.
    inst = st["groups"]["shape"]["instances"][0]["id"]
    assert any(e["type"] == "iteration_started" and e["step_path"] == f"shape/{inst}" and e["data"]["iteration"] == 2 for e in evs)
    from projectkit import packet_dir

    i2 = packet_dir(project, run, f"shape/{inst}/i2/design", 1)
    assert "Add a soil test before planting." in (i2 / "inputs" / "open_findings.json").read_text(encoding="utf-8")
    # The open ledger entry stopped generate on attempt 1 and was fed back; attempt 2 passed.
    failed = [e for e in evs if e["type"] == "gate_failed" and e["step_path"] == "generate"]
    assert len(failed) == 1 and failed[0]["attempt"] == 1
    assert any("is still open" in r for r in failed[0]["data"].get("reasons", [])) or "is still open" in json.dumps(failed[0]["data"])
    assert [e["attempt"] for e in evs if e["type"] == "dispatched" and e["step_path"] == "generate"] == [1, 2]
    assert_package_is_ready(cli, project)
    from test_real_use import assert_clean_record

    assert_clean_record(cli, project, run)


# -- the three entry paths reach the same run --------------------------------------


@pytest.mark.slow
def test_framing_can_propose_the_builder_and_starts_it_vendored_on_selection(tmp_path):
    from test_conversation import _frame, fresh, manual

    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    part = {"id": "process", "label": "A process for planting beds", "description": "A repeatable way to plant a flower bed.",
            "kind": "project", "reasons": ["No listed process covers it"],
            "proposal": {"recipe": "recipe-builder", "inputs": dict(INPUTS)}}
    out = manual(cli, project, fr, "frame", {"goal": "Plant flower beds properly.", "parts": [part], "assumptions": []})
    assert out["outcome"] == "needs_human"
    sel = cli.run("decide", fr, "frame", "select", "--items", "process", "--note", "Yes, build that process.")
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("process", "recipe-builder@3")]
    assert sel["gaps"] == [] and sel["vendored"] == ["recipe-builder@3"]
    started = cli.run("status", sel["runs"][0]["run"])
    assert started["recipe"] == "recipe-builder@3"


@pytest.mark.slow
def test_a_fit_check_profile_and_a_base_recipe_reach_the_first_step(project_with):
    ledger = [GOAL]
    cli, project, script = project_with({"profile": {"output": {**profile("simple", ledger)["output"]}}})
    inputs = {**INPUTS, "profile": {"assumptions": [{"field": "occurrences", "value": "rare", "basis": "the owner said once a year"}]},
              "base_recipe": "backyard-project@1"}
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(inputs))["run_id"]
    cli("dispatch", run, "profile", "--worker", "builder", "--wait", expect=None)  # exit 4: the owner is next
    from realkit import calls

    first = calls(script)[0]
    assert first["step"] == "profile" and {"idea", "profile", "base_recipe", "recipes"} <= set(first["inputs"])
    # The catalog listing is what lets the first step check existing recipes before authoring anything.
    from projectkit import packet_dir

    listing = json.loads((packet_dir(project, run, "profile", 1) / "inputs" / "recipes.json").read_text(encoding="utf-8"))
    assert {"backyard-project", "recipe-builder", "fit-check"} <= {r["id"] for r in listing}
    assert next(r for r in listing if r["id"] == "recipe-builder")["scope"]["covers"]


# -- implementation discovery: a choice that shapes the process (Decision 0141) ----------------------------


PRINTED = {"id": "E9", "statement": "The planting plan is delivered as a printed guide", "kind": "decision", "scope": "class",
           "status": "confirmed", "basis": "the owner's answer to the comparison", "owner_words": "A printed guide, please. Yes, that is right."}
BEFORE = {"id": "D1", "question": "Should the planting plan be a printed guide or an app?", "signals": ["the owner mentioned an app"],
          "target_status": "example", "named_targets": ["a garden app"], "timing": "before_design",
          "timing_reason": "A guide and an app need different deliverables and checks", "status": "to_research"}
CHOSEN = {**BEFORE, "status": "decided", "decision": {"ledger_id": "E9"},
          "comparison": {"criteria": ["the owner has no one to maintain software"], "uncertainty": "App pricing changes often",
                         "recommendation": "A printed guide",
                         "options": [{"name": "A printed guide", "kind": "manual_procedure", "requires_of_development": "layout and a proof check",
                                      "tradeoffs": "no reminders", "sources": [{"title": "A gardening handbook", "read_on": "2026-11-13"}]},
                                     {"name": "A mobile app", "kind": "existing_product", "requires_of_development": "build, test and a release stage",
                                      "tradeoffs": "reminders, but upkeep", "sources": [{"title": "An app vendor's page", "url": "https://example.test/app", "read_on": "2026-11-13"}]}]}}
QUESTION = {"id": "q1", "ask": "Should the plan be a printed guide or an app?", "why": "They need different things made", "best_guess": "A printed guide",
            "options": [{"id": "guide", "label": "A printed guide"}, {"id": "app", "label": "An app"}], "priority": "needed"}
ANSWER = [{"id": "q1", "answer": "A printed guide", "owner_words": "A printed guide, please. Yes, that is right."}]


class DiscoveryDirector(Director):
    """The scripted Director, plus the owner answering a `blocked` step's questions with confirmed answers."""

    def __init__(self, *a, answers_file: Path, **kw):
        super().__init__(*a, **kw)
        self.answers_file = answers_file
        self.answered: list[str] = []

    def decide(self, p: dict) -> None:
        if p.get("kind") == "escalation" and p.get("reason") == "blocked":
            self.answered.append(p["ref"])
            self.answers_file.write_text(json.dumps(ANSWER), encoding="utf-8")
            self.cli("decide", self.run, p["ref"], "retry", "--answers", str(self.answers_file), "--note", "A printed guide, please. Yes, that is right.")
            return
        super().decide(p)


def start_discovery_run(project_with, script):
    cli, project, script_file = project_with(script)
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    return cli, project, run, DiscoveryDirector(cli, project, run, route=route, answers_file=script_file.parent / "answers.json")


def discovery_script(ledger, **over):
    full = [*ledger, PRINTED]
    base = {
        "profile": {"output": {**profile("standard", ledger)["output"], "discovery": [BEFORE]}},
        "research": [{"status": "blocked", "output": {}, "questions_for_human": [QUESTION]},
                     {"output": {"discovery": [CHOSEN], "ledger": full, "sources": [{"title": "A gardening handbook", "url": None, "what_it_supports": "D1"}]}}],
        "design": {"output": {**design(full)["output"], "discovery": [CHOSEN]}, "artifacts": design(full)["artifacts"]},
        "audit": CLEAN, "generate": generated(full, [CHOSEN]),
    }
    return {**base, **over}


@pytest.mark.slow
def test_a_choice_that_shapes_the_process_is_researched_and_the_owner_decides_before_design(project_with):
    ledger = [GOAL, BED]
    cli, project, run, d = start_discovery_run(project_with, discovery_script(ledger))
    st = d.drive()
    assert st["level"] == "standard" and st["steps"]["research"]["state"] == "passed"
    assert d.answered == ["research"]  # the owner was asked once, about the one choice
    order = [s.rsplit("/", 1)[-1] for s, _ in d.dispatches]
    assert order.index("research") < order.index("design") and order.count("research") == 2
    from projectkit import packet_dir

    # The owner's confirmed words, recorded by the runtime, reach the retried research packet...
    manifest = json.loads((packet_dir(project, run, "research", 2) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prior_feedback"]["answers"] == ANSWER
    # ...and the decision they produced reaches the design packet, with the comparison behind it.
    import re

    inst = st["groups"]["shape"]["instances"][0]["id"]
    seen = json.loads((packet_dir(project, run, f"shape/{inst}/i1/design", 1) / "inputs" / "research.json").read_text(encoding="utf-8"))
    assert seen["discovery"][0]["decision"] == {"ledger_id": "E9"} and seen["discovery"][0]["comparison"]["recommendation"] == "A printed guide"
    assert next(e for e in seen["ledger"] if e["id"] == "E9")["owner_words"] == ANSWER[0]["owner_words"]
    assert_package_is_ready(cli, project)
    data = json.loads((project / "recipes" / "drafts" / f"{SLUG}.ledger.json").read_text(encoding="utf-8"))
    assert data["discovery"][0]["status"] == "decided"
    refs = [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in d.owner_decisions]
    assert refs[:2] == ["profile", "profile"] and refs[-1] == "accept"


@pytest.mark.slow
def test_a_recommendation_cannot_stand_in_for_the_owners_choice(project_with):
    """A worker that returns the comparison as `decided`, without the owner's confirmed decision entry, is stopped by the gates."""
    ledger = [GOAL, BED]
    unconfirmed = {**PRINTED, "status": "researched", "owner_words": None}
    script = discovery_script(ledger)
    script["generate"] = [generated([*ledger, unconfirmed], [CHOSEN]), generated([*ledger, PRINTED], [CHOSEN])]
    cli, project, run, d = start_discovery_run(project_with, script)
    d.drive()
    evs = run_events(project, run)
    failed = [e for e in evs if e["type"] == "gate_failed" and e["step_path"] == "generate"]
    assert len(failed) == 1 and "must be a confirmed `decision` carrying the owner's words" in json.dumps(failed[0]["data"])
    assert_package_is_ready(cli, project)


@pytest.mark.slow
def test_research_cannot_complete_with_an_unanswered_shaping_choice(project_with):
    ledger = [GOAL, BED]
    script = discovery_script(ledger)
    script["research"] = [{"output": {"discovery": [BEFORE], "ledger": ledger, "sources": []}}, *script["research"]]
    cli, project, run, d = start_discovery_run(project_with, script)
    d.drive()
    evs = run_events(project, run)
    kinds = [e["type"] for e in evs if e["step_path"] == "research" and e["type"] in ("result_rejected", "step_passed", "step_escalated")]
    assert kinds == ["result_rejected", "step_escalated", "step_passed"]  # the schema refused it; only the owner's answer let it pass


# -- implementation discovery: a process that makes its own choice (Decision 0141) -------------------------

DEFERRED = {"id": "D2", "question": "Which tool will each job's plan be made in?", "target_status": "none", "timing": "in_generated_recipe",
            "timing_reason": "Every tool fits the same process: research, owner choice, then the work that uses it",
            "graph_effect": "One shape serves every tool; the tool is a value each job supplies", "status": "deferred",
            "generated": {"research_step": "research_options", "decision_step": "decide", "consumers": ["build_plan"]}}
SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
DEFERRED_PACKAGE = {
    "recipe.yaml": (
        "id: flower-bed\nversion: 1\nformat: baton-recipe/1\ncapabilities_vocab: baton-capabilities/1\n"
        "description: Plan a flower bed in the tool the job calls for.\nscope:\n  covers: [flower bed plans]\n  not_for: []\n  varies_by: [the tool]\nparent: null\n"
        "run_inputs:\n  schema: schemas/run_inputs.json\nsteps:\n"
        "  - id: research_options\n    title: Compare the ways to make the plan\n    requires: { capabilities: [structured_output, web_access] }\n"
        "    prompt: prompts/research_options.md\n    inputs:\n      - { name: goal, from: run.inputs.goal, required: true }\n"
        "    output_schema: schemas/findings.json\n    gates: [ { type: schema } ]\n"
        "  - id: decide\n    title: The owner chooses\n    depends_on: [research_options]\n    requires: { capabilities: [human_judgment] }\n"
        "    prompt: prompts/decide.md\n    inputs:\n      - { name: findings, from: steps.research_options.output, required: true }\n"
        "    output_schema: schemas/choice.json\n    gates:\n      - { type: schema }\n      - { type: human, prompt: \"Use this way of making the plan?\" }\n"
        "  - id: build_plan\n    title: Make the plan\n    depends_on: [decide]\n    requires: { capabilities: [structured_output] }\n"
        "    prompt: prompts/build_plan.md\n    inputs:\n      - { name: choice, from: steps.decide.output, required: true }\n"
        "      - { name: findings, from: steps.research_options.output, required: true }\n    output_schema: schemas/plan.json\n    gates: [ { type: schema } ]\n"
    ),
    "prompts/research_options.md": "# Compare the ways\n\nFind the ways to make the plan for this job, with sources and what each needs.\n",
    "prompts/decide.md": "# Choose\n\nRecord which way the owner chose, in their words.\n",
    "prompts/build_plan.md": "# Make the plan\n\nMake the plan in the way the owner chose.\n",
    "schemas/run_inputs.json": json.dumps({**SCHEMA, "required": ["goal"], "properties": {"goal": {"type": "string"}}}),
    "schemas/findings.json": json.dumps({**SCHEMA, "required": ["options"]}),
    "schemas/choice.json": json.dumps({**SCHEMA, "required": ["choice"]}),
    "schemas/plan.json": json.dumps({**SCHEMA, "required": ["summary"]}),
}
FINDINGS = {"options": [{"name": "A spreadsheet", "source": "a vendor page, read 2026-11-13"}, {"name": "A printed guide", "source": "a handbook"}]}


def deferred_script(ledger):
    generate = generated(ledger, [DEFERRED])
    generate["commit_files"] = {**{f"recipes/drafts/{SLUG}/{k}": v for k, v in DEFERRED_PACKAGE.items()},
                                f"recipes/drafts/{SLUG}.ledger.json": json.dumps({"ledger": ledger, "discovery": [DEFERRED]})}
    generate["artifacts"]["ledger"] = generate["commit_files"][f"recipes/drafts/{SLUG}.ledger.json"]
    stages = [*STAGES, {"id": "research_options", "title": "Compare the ways", "done_by": "ai", "needs": ["the goal"], "hands_on": ["options"], "on_failure": "retry"},
              {"id": "decide", "title": "The owner chooses", "done_by": "person", "needs": ["options"], "hands_on": ["a choice"],
               "owner_decision": "Use this way?", "on_failure": "revise"},
              {"id": "build_plan", "title": "Make the plan", "done_by": "ai", "needs": ["a choice"], "hands_on": ["a plan"], "on_failure": "retry"}]
    return {
        "profile": {"output": {**profile("simple", ledger)["output"], "discovery": [NONE_NEEDED, DEFERRED]}},
        "design": {"output": {**design(ledger)["output"], "stages": stages, "discovery": [DEFERRED]}, "artifacts": design(ledger)["artifacts"]},
        "audit": CLEAN, "generate": generate,
        # the generated process, run later
        "research_options": {"output": FINDINGS},
        "build_plan": [{"output": {"summary": "Plan made as chosen"}}],
    }


def build_deferred_draft(project_with):
    cli, project, script_file = project_with(deferred_script([GOAL, BED]))
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route)
    d.drive()
    assert_package_is_ready(cli, project)
    return cli, project, script_file


@pytest.mark.slow
def test_a_process_that_makes_its_own_choice_passes_the_builders_gates_even_at_simple(project_with):
    cli, project, _ = build_deferred_draft(project_with)
    data = json.loads((project / "recipes" / "drafts" / f"{SLUG}.ledger.json").read_text(encoding="utf-8"))
    assert [r["timing"] for r in data["discovery"]] == ["in_generated_recipe"]  # deferred: no comparison in the builder, so `simple` stays
    # It is a settled requirement of the process, not an open entry: nothing was weakened.
    assert not [e for e in data["ledger"] if e["status"] == "open"]


@pytest.mark.slow
def test_findings_and_the_owners_choice_reach_the_dependent_work_and_nothing_advances_without_them(project_with):
    cli, project, script_file = build_deferred_draft(project_with)
    cli.run("vendor", str(project / "recipes" / "drafts" / SLUG))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Vendor the generated process")
    run = cli.run("start", SLUG, "--inputs", json.dumps({"title": "Bed plan", "goal": "Plan the bed"}))["run_id"]

    def gen_route(path):
        return "owner" if path == "decide" else "builder"

    # build_plan cannot start before the owner's choice: its required input has no producer yet.
    st = cli("status", run, expect=None).payload
    assert [s for s in st["ready"]] == ["research_options"]
    d = Director(cli, project, run, route=gen_route, decisions={"decide": [("reject", "Not that one; the printed guide."), ("approve", "Yes, the printed guide.")]},
                 acceptance={"choice": "A spreadsheet"})
    # Drive the research and the first (rejected) decision.
    cli("dispatch", run, "research_options", "--worker", "builder", "--wait", expect=None)
    st = cli("status", run, expect=None).payload
    assert [s for s in st["ready"]] == ["decide"] and st["steps"]["build_plan"]["state"] != "ready"
    owner_does(cli, project, run, "decide", {"choice": "A spreadsheet"})
    pending = cli("status", run, expect=None).payload["pending_decisions"]
    assert pending and pending[0]["ref"].endswith("decide")  # the output alone does not advance: the owner must approve
    assert cli("status", run, expect=None).payload["steps"]["build_plan"]["state"] != "ready"
    cli("decide", run, pending[0]["ref"], "reject", "--note", "Not that one; the printed guide.")
    st = cli("status", run, expect=None).payload
    assert st["ready"] == ["decide"], st  # the owner's rejection sent the choice back
    # The findings are still in the retried packet, with the owner's note.
    d2 = cli.run("dispatch", run, "decide", "--worker", "owner")
    pkt = packet_dir(project, run, "decide", d2["attempt"])
    assert json.loads((pkt / "inputs" / "findings.json").read_text(encoding="utf-8")) == FINDINGS
    assert "Not that one; the printed guide." in (pkt / "INSTRUCTIONS.md").read_text(encoding="utf-8") + (pkt / "manifest.json").read_text(encoding="utf-8")
    from realkit import write_result

    write_result(pkt, {"choice": "A printed guide"})
    cli("submit", run, "decide", expect=None)
    pending = cli("status", run, expect=None).payload["pending_decisions"]
    cli("decide", run, pending[0]["ref"], "approve", "--note", "Yes, the printed guide.")
    cli("dispatch", run, "build_plan", "--worker", "builder", "--wait", expect=None)
    build = packet_dir(project, run, "build_plan", 1) / "inputs"
    assert json.loads((build / "choice.json").read_text(encoding="utf-8")) == {"choice": "A printed guide"}  # the second, approved choice
    assert json.loads((build / "findings.json").read_text(encoding="utf-8")) == FINDINGS
    assert cli("status", run, expect=None).payload["state"] == "completed"


@pytest.mark.slow
def test_a_deferred_choice_nothing_consumes_is_refused_by_the_gate(project_with):
    ledger = [GOAL, BED]
    script = deferred_script(ledger)
    broken = {**DEFERRED, "generated": {**DEFERRED["generated"], "consumers": ["build_plan"]}}
    no_input = dict(DEFERRED_PACKAGE)
    no_input["recipe.yaml"] = DEFERRED_PACKAGE["recipe.yaml"].replace("{ name: choice, from: steps.decide.output, required: true }", "{ name: choice, from: run.inputs.goal, required: true }")
    bad = generated(ledger, [broken])
    bad["commit_files"] = {**{f"recipes/drafts/{SLUG}/{k}": v for k, v in no_input.items()}, f"recipes/drafts/{SLUG}.ledger.json": json.dumps({"ledger": ledger, "discovery": [broken]})}
    bad["artifacts"]["ledger"] = bad["commit_files"][f"recipes/drafts/{SLUG}.ledger.json"]
    script["generate"] = [bad, script["generate"]]
    cli, project, _ = project_with(script)
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    Director(cli, project, run, route=route).drive()
    failed = [e for e in run_events(project, run) if e["type"] == "gate_failed" and e["step_path"] == "generate"]
    assert len(failed) == 1 and "step `build_plan` must take the output of `decide`" in json.dumps(failed[0]["data"])
    assert_package_is_ready(cli, project)


@pytest.mark.slow
def test_a_pinned_builder_v2_still_runs_and_never_asks_for_discovery(project_with, monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys.modules[__name__], "BUILDER", ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v2")
    ledger = [GOAL, BED]
    p = profile("simple", ledger)["output"]
    p.pop("discovery")
    d = design(ledger)["output"]
    d.pop("discovery")
    gen = generated(ledger)
    gen["commit_files"][f"recipes/drafts/{SLUG}.ledger.json"] = json.dumps(ledger)  # v2 wrote the ledger as a list
    gen["artifacts"]["ledger"] = json.dumps(ledger)
    cli, project, _ = project_with({"profile": {"output": p}, "design": {"output": d, "artifacts": design(ledger)["artifacts"]}, "audit": CLEAN, "generate": gen})
    run = cli.run("start", "recipe-builder@2", "--inputs", json.dumps(INPUTS))["run_id"]
    st = Director(cli, project, run, route=route).drive()
    assert st["recipe"] == "recipe-builder@2" and st["state"] == "completed"
    assert recipe_check.check(project / "recipes" / "drafts" / SLUG, project / "recipes" / "drafts" / f"{SLUG}.ledger.json") == []
