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
STAGES_V3 = [
    {"id": "survey", "title": "Survey the site", "done_by": "person", "needs": ["the bed's location"], "hands_on": ["site notes"],
     "owner_decision": None, "on_failure": "escalate", "failure_note": "Ask the owner where the bed goes."},
    {"id": "plant", "title": "Plant the bed", "done_by": "person", "needs": ["site notes"], "hands_on": ["a planted bed"],
     "owner_decision": "Is the bed planted as wanted?", "on_failure": "revise"},
]
PHYSICAL = {"rules": "partial", "input": "open", "repeatable": "not_required", "result": "certain", "check": "judgment"}
#: recipe-builder@4: every stage says what its work is like, what its check establishes, and whether delegating it is risky.
STAGES = [
    {**STAGES_V3[0], "traits": {**PHYSICAL, "effect": "none", "basis": "A person looks at the ground; nothing changes yet."},
     "acceptance": {"kind": "judgment", "what": "The notes say where the bed goes and what the light is."},
     "delegation": {"risky": False, "reason": "Only notes are taken."}},
    {**STAGES_V3[1], "traits": {**PHYSICAL, "effect": "reversible", "basis": "Plants can be moved, with some loss."},
     "acceptance": {"kind": "judgment", "what": "The owner sees the bed planted as the notes say."},
     "delegation": {"risky": False, "reason": "A planting can be redone."}},
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


def profile(level: str, ledger: list[dict], software: str = "none") -> dict:
    """A profile result: ``level`` is the approach (recipe-builder@4 and later rate two axes)."""
    return {"output": {
        "ratings": {"approach": {"value": level, "reason": "how much process it needs"},
                    "software": {"value": software, "reason": "no rule-like work" if software == "none" else "it adds up amounts"}},
        "reasons": ["one kind of worker, nothing irreversible" if level == "simple" else "several kinds of worker"],
        "goal": {"statement": "Plant a flower bed", "trigger": "The owner wants a bed", "end_state": "A planted bed", "success_measure": "Plants are in and watered"},
        "existing_recipe": None,
        "rung": {"label": "Just flower beds", "covers": ["a flower bed"], "next_rung": "any garden bed"},
        "related_parts": [], "build_now": None, "discovery": [NONE_NEEDED], "ledger": ledger}}


def design(ledger: list[dict], summary: str = "Survey then plant") -> dict:
    return {"output": {"summary": summary, "stages": STAGES, "excluded": [], "discovery": [NONE_NEEDED], "ledger": ledger},
            "artifacts": {"design_doc": "# Planting a flower bed\n\nSurvey the site, then plant.\n"}}


def route(step_path: str) -> str:
    step = step_path.rsplit("/", 1)[-1]
    if step in ("accept", "example_plan"):
        return "owner"
    return "checker" if step in ("audit", "generate~review", "implement") else "builder"


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
    assert st["ratings"] == {"approach": "simple", "software": "none"} and st["steps"]["research"]["state"] == "skipped"
    assert [s.rsplit("/", 1)[-1] for s, _ in d.dispatches] == ["profile", "design", "audit", "generate", "accept"]
    # The owner confirms the goal and approves the finished process: nothing else at the lowest level.
    assert [r.rsplit("/", 1)[-1] for r, _ in d.owner_decisions] == ["profile", "accept"]
    # The audit was a different vendor from the design.
    assert dict((s.rsplit("/", 1)[-1], w) for s, w in d.dispatches)["audit"] == "checker"
    assert_package_is_ready(cli, project)
    evs = run_events(project, run)
    scripts = [e for e in evs if e["type"] == "gate_passed" and e["step_path"] == "generate" and e["data"].get("type") == "script"]
    assert [e["data"]["command"].split(" ")[:2] for e in scripts] == [["baton", "plan"], ["baton", "recipe"], ["baton", "programs"]]
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
    assert st["ratings"]["approach"] == "standard" and st["steps"]["research"]["state"] == "passed"
    # Owner touchpoints: the level, the goal, the design (twice: the first is sent back), the finished process.
    import re

    refs = [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in d.owner_decisions]  # the group's instance id is random
    assert refs == ["profile", "shape/i1/audit", "shape/i2/audit", "accept"], refs  # profile: the goal and the ratings, one question (@5)
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
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("process", "recipe-builder@6")]
    assert sel["gaps"] == [] and sel["vendored"] == ["recipe-builder@6"]
    started = cli.run("status", sel["runs"][0]["run"])
    assert started["recipe"] == "recipe-builder@6"


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
    assert st["ratings"]["approach"] == "standard" and st["steps"]["research"]["state"] == "passed"
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
    assert refs[0] == "profile" and refs.count("profile") == 1 and refs[-1] == "accept"  # the goal and the ratings are one question (@5)


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

DEFERRED = {"id": "D2", "question": "Which program will each job's plan be made in?", "target_status": "none", "timing": "in_generated_recipe",
            "timing_reason": "Every program fits the same process: research, owner choice, then the work that uses it",
            "graph_effect": "One shape serves every program; the program is a value each job supplies", "status": "deferred",
            "generated": {"research_step": "research_options", "decision_step": "decide", "consumers": ["build_plan"]}}
SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
DEFERRED_PACKAGE = {
    "recipe.yaml": (
        "id: flower-bed\nversion: 1\nformat: baton-recipe/1\ncapabilities_vocab: baton-capabilities/1\n"
        "description: Plan a flower bed in the program the job calls for.\nscope:\n  covers: [flower bed plans]\n  not_for: []\n  varies_by: [the program]\nparent: null\n"
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
    open_work = {"rules": "none", "input": "open", "repeatable": "not_required", "effect": "none", "result": "uncertain", "check": "judgment"}
    stages = [*STAGES,
              {"id": "research_options", "title": "Compare the ways", "done_by": "ai", "needs": ["the goal"], "hands_on": ["options"], "on_failure": "retry",
               "traits": {**open_work, "check": "source", "basis": "Reading current sources about programs."},
               "acceptance": {"kind": "source", "what": "Each option cites a source read on a date."}},
              {"id": "decide", "title": "The owner chooses", "done_by": "person", "needs": ["options"], "hands_on": ["a choice"],
               "owner_decision": "Use this way?", "on_failure": "revise",
               "traits": {**open_work, "result": "certain", "basis": "The owner's choice."},
               "acceptance": {"kind": "judgment", "what": "The owner's words name one way."},
               "delegation": {"risky": False, "reason": "The choice can be revisited before work starts."}},
              {"id": "build_plan", "title": "Make the plan", "done_by": "ai", "needs": ["a choice"], "hands_on": ["a plan"], "on_failure": "retry",
               "traits": {**open_work, "basis": "Writing a plan for the chosen way."},
               "acceptance": {"kind": "judgment", "what": "The plan uses the chosen way."}}]
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
    p.pop("ratings")
    p["level"] = "simple"  # v2 rated one scale
    d = design(ledger)["output"]
    d.pop("discovery")
    d["stages"] = STAGES_V3
    gen = generated(ledger)
    gen["commit_files"][f"recipes/drafts/{SLUG}.ledger.json"] = json.dumps(ledger)  # v2 wrote the ledger as a list
    gen["artifacts"]["ledger"] = json.dumps(ledger)
    cli, project, _ = project_with({"profile": {"output": p}, "design": {"output": d, "artifacts": design(ledger)["artifacts"]}, "audit": CLEAN, "generate": gen})
    run = cli.run("start", "recipe-builder@2", "--inputs", json.dumps(INPUTS))["run_id"]
    st = Director(cli, project, run, route=route).drive()
    assert st["recipe"] == "recipe-builder@2" and st["state"] == "completed"
    assert recipe_check.check(project / "recipes" / "drafts" / SLUG, project / "recipes" / "drafts" / f"{SLUG}.ledger.json") == []


@pytest.mark.slow
def test_a_pinned_builder_v3_still_runs_on_its_one_scale(project_with, monkeypatch):
    """A project that pinned recipe-builder@3 keeps it (2026-11-builder-step-design criterion 1)."""
    import sys as _sys

    monkeypatch.setattr(_sys.modules[__name__], "BUILDER", ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v3")
    ledger = [GOAL, BED]
    p = profile("simple", ledger)["output"]
    p.pop("ratings")
    p["level"] = "simple"
    v3_design = design(ledger)
    v3_design["output"]["stages"] = STAGES_V3
    cli, project, _ = project_with({"profile": {"output": p}, "design": v3_design, "audit": CLEAN, "generate": generated(ledger)})
    run = cli.run("start", "recipe-builder@3", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route)
    st = d.drive()
    assert st["recipe"] == "recipe-builder@3" and st["state"] == "completed" and st["level"] == "simple"
    assert [r.rsplit("/", 1)[-1] for r, _ in d.owner_decisions] == ["profile", "accept"]


@pytest.mark.slow
def test_software_simple_waits_on_the_owner_and_adds_the_design_approval_and_the_package_review(project_with):
    """At software: simple the owner approves the ratings and sees the design, and the package is reviewed, even at a simple approach."""
    ledger = [GOAL, BED]
    cli, project, _ = project_with({
        "profile": profile("simple", ledger, software="simple"), "design": design(ledger), "audit": CLEAN, "generate": generated(ledger),
        "generate~review": CLEAN})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route)
    st = d.drive()
    assert st["ratings"] == {"approach": "simple", "software": "simple"} and st["steps"]["research"]["state"] == "skipped"
    import re

    refs = [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in d.owner_decisions]
    assert refs == ["profile", "shape/i1/audit", "accept"], refs  # the goal and the ratings (one question), the design, the result
    evs = run_events(project, run)
    assert any(e["type"] == "gate_passed" and e["step_path"] == "generate" and e["data"].get("type") == "review" for e in evs)


# -- step design (change 2026-11-builder-step-design, Slice 3) ---------------------------------------------

RULES = {"rules": "complete", "input": "structured", "repeatable": "required", "effect": "none", "result": "certain", "check": "mechanical",
         "basis": "Seed counts are the bed's area times the spacing rule."}
COUNT_BY_AI = {"id": "count", "title": "Work out how many plants", "done_by": "ai", "needs": ["site notes"], "hands_on": ["a plant count"],
               "owner_decision": None, "on_failure": "retry", "traits": RULES,
               "acceptance": {"kind": "rule", "what": "The count matches the area and spacing."}}
CEILING = {"could_be": "a small program that multiplies the area by the spacing", "reason": "ceiling",
           "gives_up": "the same count every time, at no cost per run and with no AI service",
           "would_cost": "writing and checking a small program, and keeping it up to date"}


def design_with(stages: list[dict], ledger: list[dict]) -> dict:
    d = design(ledger)
    return {**d, "output": {**d["output"], "stages": stages}}


@pytest.mark.slow
def test_an_ai_stage_with_no_record_and_a_format_only_check_on_an_effect_are_sent_back_to_design(project_with):
    ledger = [GOAL, BED]
    no_record = design_with([STAGES[0], COUNT_BY_AI, STAGES[1]], ledger)
    format_only = design_with([STAGES[0], {**COUNT_BY_AI, "executor_choice": CEILING},
                               {**STAGES[1], "acceptance": {"kind": "format", "what": "A photo was attached."}}], ledger)
    good = design_with([STAGES[0], {**COUNT_BY_AI, "executor_choice": CEILING}, STAGES[1]], ledger)
    cli, project, _ = project_with({"profile": profile("simple", ledger), "design": [no_record, format_only, good],
                                    "audit": CLEAN, "generate": generated(ledger)})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    st = Director(cli, project, run, route=route).drive()
    assert st["state"] == "completed"
    failed = [e for e in run_events(project, run) if e["type"] == "result_rejected" and e["step_path"].endswith("/design")]
    assert [e["attempt"] for e in failed] == [1, 2]
    assert "executor_choice" in json.dumps(failed[0]["data"])  # the AI stage software could do had no record
    assert "format" in json.dumps(failed[1]["data"])  # a stage with an effect was checked for format only


@pytest.mark.slow
def test_a_stage_that_must_be_split_is_found_by_the_audit_and_redesigned(project_with):
    ledger = [GOAL, BED]
    both = design_with([{**STAGES[0], "id": "survey_and_count", "title": "Survey the site and work out the plants"}, STAGES[1]], ledger)
    split = design_with([STAGES[0], {**COUNT_BY_AI, "executor_choice": CEILING}, STAGES[1]], ledger)
    finding = {"id": "F1", "severity": "high", "title": "Two kinds of work in one stage (check 21)", "location": "survey_and_count",
               "detail": "Reading the site is judgment; counting plants is a rule.", "suggested_fix": "Interpret, then enforce: split it."}
    cli, project, _ = project_with({"profile": profile("simple", ledger), "design": [both, split],
                                    "audit": [{"output": {"findings": [finding], "coverage": {"complete": True, "notes": ""}}}, CLEAN],
                                    "generate": generated(ledger)})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    st = Director(cli, project, run, route=route).drive()
    assert st["state"] == "completed"
    inst = st["groups"]["shape"]["instances"][0]["id"]
    i2 = packet_dir(project, run, f"shape/{inst}/i2/design", 1)
    assert "check 21" in (i2 / "inputs" / "open_findings.json").read_text(encoding="utf-8")


@pytest.mark.slow
def test_at_a_ceiling_of_none_the_owner_is_told_once_that_software_could_do_part_of_it(project_with):
    ledger = [GOAL, BED]
    signal = {"axis": "software", "suggested": "simple", "reason": "A small program could work out how many plants each bed needs."}
    designed = {**design_with([STAGES[0], {**COUNT_BY_AI, "executor_choice": CEILING}, STAGES[1]], ledger), "rating_signal": signal}
    cli, project, _ = project_with({"profile": profile("simple", ledger), "design": designed, "audit": CLEAN, "generate": generated(ledger)})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route, decisions={"rating:software": [("dismiss", "Keep it without programs.")]})
    st = d.drive()
    assert st["state"] == "completed" and st["ratings"]["software"] == "none"
    assert [r for r, _ in d.owner_decisions if r.startswith("rating:")] == ["rating:software"]
    recorded = [e for e in run_events(project, run) if e["type"] == "rating_signal_recorded"]
    assert [(e["data"]["axis"], e["data"]["suggested"], e["data"]["rating"]) for e in recorded] == [("software", "simple", "none")]


# -- the builder writes simple programs (change 2026-11-builder-step-design, Slice 4) -------------------------

COUNT_PY = """import json
import sys
from pathlib import Path

bed = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["bed"]
if bed["spacing_m"] <= 0:
    print("count_plants: the spacing must be more than zero", file=sys.stderr)
    sys.exit(1)
plants = int(bed["length_m"] // bed["spacing_m"]) * int(bed["width_m"] // bed["spacing_m"])
(Path(sys.argv[2]) / "output.json").write_text(json.dumps({"plants": plants}), encoding="utf-8")
"""
PROGRAM_YAML = ("id: count_plants\ndescription: Works out how many plants fit in a bed from its size and the spacing.\n"
             "runtime: { kind: python, version: \">=3.10\" }\nentry: [\"python\", \"{program}/count_plants.py\", \"{input}\", \"{output}\"]\n"
             "dependencies: { lock: requirements.lock }\nreach: { workspace: none, network: false, secrets: [] }\n")
PROGRAM_PACKAGE = {
    "recipe.yaml": (
        "id: flower-bed\nversion: 1\nformat: baton-recipe/1\ncapabilities_vocab: baton-capabilities/1\n"
        "description: Plant a flower bed.\nscope:\n  covers: [a flower bed]\n  not_for: []\n  varies_by: [size]\nparent: null\n"
        "run_inputs:\n  schema: schemas/run_inputs.json\nsteps:\n"
        "  - id: count\n    title: Work out how many plants\n    program: count_plants\n    workspace: none\n"
        "    inputs:\n      - { name: bed, from: run.inputs.bed, required: true }\n"
        "    output_schema: schemas/count_out.json\n    gates: [ { type: schema } ]\n"
        "  - id: plant\n    title: Plant the bed\n    depends_on: [count]\n    requires: { capabilities: [human_judgment] }\n"
        "    prompt: prompts/plant.md\n    inputs:\n      - { name: count, from: steps.count.output, required: true }\n"
        "    output_schema: schemas/plant_out.json\n    gates: [ { type: schema } ]\n"
    ),
    "prompts/plant.md": "# Plant the bed\n\nPlant the number of plants worked out, and report what you did.\n",
    "schemas/run_inputs.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
                                           "properties": {"bed": {"type": "object"}}}),
    "schemas/count_out.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
                                          "required": ["plants"], "properties": {"plants": {"type": "integer"}}}),
    "schemas/plant_out.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
    "programs/count_plants/count_plants.py": COUNT_PY,
    "programs/count_plants/program.yaml": PROGRAM_YAML,
    "programs/count_plants/requirements.lock": "",
    "programs/count_plants/examples/three-by-one/input.json": json.dumps({"bed": {"length_m": 3, "width_m": 1, "spacing_m": 0.5}}),
    "programs/count_plants/examples/three-by-one/expected.json": json.dumps({"plants": 12}),
}
COUNT_PROGRAM_STAGE = {**COUNT_BY_AI, "done_by": "program",
                    "program": {"id": "count_plants", "does": "Works out how many plants fit in a bed from its size and the spacing.",
                             "input": "the bed's length, width and spacing", "output": "the number of plants",
                             "reach": {"workspace": "none", "network": False, "secrets": []},
                             "examples": [{"name": "three-by-one", "input": {"bed": {"length_m": 3, "width_m": 1, "spacing_m": 0.5}},
                                           "expected": {"plants": 12}, "says": "A 3 m by 1 m bed at 50 cm spacing takes 12 plants."}]}}


def generated_with_program(ledger: list[dict], script: str = COUNT_PY) -> dict:
    gen = generated(ledger)
    files = {f"recipes/drafts/{SLUG}/{k}": (script if k.endswith("count_plants.py") else v) for k, v in PROGRAM_PACKAGE.items()}
    gen["commit_files"] = {**files, f"recipes/drafts/{SLUG}.ledger.json": gen["commit_files"][f"recipes/drafts/{SLUG}.ledger.json"]}
    gen["artifacts"]["walkthrough"] = ("# Planting a flower bed\n\nYou survey the site; a small program works out how many plants fit; you plant them.\n\n"
                                       "**Small programs in this process:** working out how many plants fit (needs Python, nothing else; "
                                       "does not open your files and does not use the internet).\n")
    return gen


@pytest.mark.slow
def test_a_described_process_with_rule_like_work_yields_an_accepted_package_whose_program_passes_its_examples(project_with):
    ledger = [GOAL, BED]
    wrong = COUNT_PY.replace("int(bed[\"width_m\"] // bed[\"spacing_m\"])", "int(bed[\"width_m\"] / bed[\"spacing_m\"] + 1)")
    cli, project, _ = project_with({
        "profile": profile("simple", ledger, software="simple"),
        "design": design_with([STAGES[0], COUNT_PROGRAM_STAGE, STAGES[1]], ledger), "audit": CLEAN,
        # attempt 1's program gets 18 for the example: the `programs test` gate sends it back; attempt 2 is right.
        "generate": [generated_with_program(ledger, wrong), generated_with_program(ledger)], "generate~review": CLEAN})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route)
    st = d.drive()
    assert st["state"] == "completed" and st["ratings"] == {"approach": "simple", "software": "simple"}
    import re

    refs = [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in d.owner_decisions]
    assert refs == ["profile", "shape/i1/audit", "accept"], refs  # the owner saw the design (with the program) before it was built
    evs = run_events(project, run)
    failed = [e for e in evs if e["type"] == "gate_failed" and e["step_path"] == "generate"]
    assert len(failed) == 1 and failed[0]["attempt"] == 1
    assert "FAILED count_plants / three-by-one: output.plants: expected 12, the program gave 18" in json.dumps(failed[0]["data"])
    passed = [e["data"]["command"] for e in evs if e["type"] == "gate_passed" and e["step_path"] == "generate" and e["data"].get("type") == "script"]
    assert passed[-1] == f"baton programs test recipes/drafts/{SLUG} --require-examples --allow-unbuilt"
    assert any(e["type"] == "gate_passed" and e["step_path"] == "generate" and e["data"].get("type") == "review" for e in evs)
    # The accepted draft is a recipe with a program step: vendoring it asks the owner about the program, in their terms.
    flags = cli("vendor", str(project / "recipes" / "drafts" / SLUG), expect=4).payload
    program_flags = [f for f in flags.get("flags", []) if f["code"] == "program"]
    assert [f["program"] for f in program_flags] == ["count_plants"] and "does not use the internet" in program_flags[0]["touches"]


# -- the quick path (change 2026-11-quick-runs, Slice 3; Decisions 0145, 0163) ------------------------------

@pytest.mark.slow
def test_a_pinned_builder_v4_still_runs_with_its_own_profile_question(project_with, monkeypatch):
    """A project that pinned recipe-builder@4 keeps it: its goal question and its ratings question are separate."""
    import re
    import sys as _sys

    monkeypatch.setattr(_sys.modules[__name__], "BUILDER", ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v4")
    ledger = [GOAL, BED]
    cli, project, _ = project_with({
        "profile": profile("simple", ledger, software="simple"), "design": design(ledger), "audit": CLEAN, "generate": generated(ledger),
        "generate~review": CLEAN})
    run = cli.run("start", "recipe-builder@4", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route)
    st = d.drive()
    assert st["recipe"] == "recipe-builder@4" and st["state"] == "completed"
    assert [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in d.owner_decisions] == ["profile", "profile", "shape/i1/audit", "accept"]


WATER = {"title": "Water stand plan", "idea": "I want a business plan for a water vending stand, just good enough to get started"}
WATER_SLUG = "water-stand-plan"
WATER_GOAL = {"id": "G1", "statement": "A plan good enough to start a water stand", "kind": "goal", "scope": "instance", "status": "inferred",
              "basis": "The owner said 'just good enough to get started'", "value": "a water vending stand"}
NEW_GUIDE = """---
format: baton-guide/1
id: kiosk-plan
version: 1
title: Kiosk business plan
description: A short plan for a small stand or kiosk selling one kind of product.
produces: a kiosk business plan (Markdown, two pages)
---

## Purpose

Decide whether a small stand is worth starting.

## What to produce

The offer, the site, the daily numbers and the first month's steps.

## What good looks like

The daily numbers add up and every figure has its basis.

## What to ask the owner

Where the stand would be and what it would sell.
"""


def quick_profile(choice: dict) -> dict:
    out = profile("simple", [WATER_GOAL])
    out["output"]["ratings"]["approach"] = {"value": "quick", "reason": "One plan to start on is enough; a quick guided run, not a full process"}
    out["output"]["guide_choice"] = choice
    out["output"]["goal"] = {"statement": "A plan to start a water stand", "trigger": "The owner wants to start", "end_state": "A plan",
                             "success_measure": "The owner can act on it"}
    return out


def quick_route(step_path: str) -> str:
    return "builder"


@pytest.mark.slow
def test_the_quick_path_writes_a_guide_the_owner_approves_and_a_bad_guide_is_redone(project_with):
    from baton import guides

    bad = NEW_GUIDE.replace("## What to ask the owner\n\nWhere the stand would be and what it would sell.\n", "")
    cli, project, script = project_with({
        "profile": quick_profile({"action": "write", "base": None, "why": "No listed guide is for a stand or kiosk"}),
        "guide": [{"output": {"id": "kiosk-plan", "action": "written", "base": None, "summary": "A two-page plan for a stand", "changes": []},
                   "artifacts": {"guide": text}} for text in (bad, NEW_GUIDE)]})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(WATER))["run_id"]
    d = Director(cli, project, run, route=quick_route)
    st = d.drive()
    assert st["state"] == "completed" and st["ratings"] == {"approach": "quick", "software": "none"}
    for skipped in ("research", "shape", "generate", "accept"):
        assert st["steps"][skipped]["state"] == "skipped", skipped
    assert [s for s, _ in d.dispatches] == ["profile", "guide", "guide"]
    # One question at profile (the goal and the quick approach together), then the guide.
    assert [r for r, _ in d.owner_decisions] == ["profile", "guide"]
    evs = run_events(project, run)
    triage = next(e for e in evs if e["type"] == "human_gate_opened" and e["data"].get("gate") == "triage")
    assert "quick" in triage["data"]["prompt"] and "a quick guided run" in triage["data"]["prompt"]
    failed = [e for e in evs if e["type"] == "gate_failed" and e["step_path"] == "guide"]
    assert len(failed) == 1 and failed[0]["data"]["command"] == "baton guides check --artifact guide"
    assert "missing the section '## What to ask the owner'" in json.dumps(failed[0]["data"])
    seen = json.loads((packet_dir(project, run, "guide", 2) / "manifest.json").read_text(encoding="utf-8"))["prior_feedback"]
    assert any("What to ask the owner" in r for r in seen["reasons"])
    assert (project / "guides" / f"{WATER_SLUG}.md").read_text(encoding="utf-8") == NEW_GUIDE
    doc = {x["path"]: x for x in cli.run("documents")["documents"]}[f"guides/{WATER_SLUG}.md"]
    assert doc["kind"] == "deliverable" and doc["source"]["run"] == run and doc["source"]["step"] == "guide"
    listed = [g for g in cli.run("guides")["guides"] if g["where"] == "project"]
    assert listed == [{"id": "kiosk-plan", "version": 1, "title": "Kiosk business plan",
                       "description": "A short plan for a small stand or kiosk selling one kind of product.",
                       "produces": "a kiosk business plan (Markdown, two pages)", "where": "project", "path": f"guides/{WATER_SLUG}.md"}]
    assert guides.check_file(project / "guides" / f"{WATER_SLUG}.md").problems == []
    assert not (project / "recipes" / "drafts").exists()  # nothing was designed or built


@pytest.mark.slow
def test_the_quick_path_adopts_a_fitting_shipped_guide_from_the_listing(project_with):
    from baton import guides

    shipped = guides.shipped()["lean-business-plan"].file.read_text(encoding="utf-8")
    cli, project, script = project_with({
        "profile": quick_profile({"action": "adopt", "base": "lean-business-plan", "why": "It is the plan the owner asked for"}),
        "guide": {"output": {"id": "lean-business-plan", "action": "adopted", "base": "lean-business-plan", "summary": "A lean plan", "changes": []},
                  "artifacts": {"guide": shipped}}})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(WATER))["run_id"]
    st = Director(cli, project, run, route=quick_route).drive()
    assert st["state"] == "completed"
    calls = [json.loads(x) for x in (script.parent / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "guides" in next(c for c in calls if c["step"] == "profile")["inputs"]  # the profile saw the guides
    given = json.loads((packet_dir(project, run, "guide", 1) / "inputs" / "guides.json").read_text(encoding="utf-8"))
    assert next(g for g in given if g["id"] == "lean-business-plan")["text"] == shipped  # the guide step had the text to adopt
    assert (project / "guides" / f"{WATER_SLUG}.md").read_text(encoding="utf-8") == shipped


@pytest.mark.slow
def test_a_quick_rating_with_software_is_refused_by_the_profile_schema(project_with):
    out = quick_profile({"action": "adopt", "base": "lean-business-plan", "why": "w"})
    out["output"]["ratings"]["software"] = {"value": "simple", "reason": "it adds up amounts"}
    cli, project, _ = project_with({"profile": out})
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(WATER))["run_id"]
    res = cli("dispatch", run, "profile", "--worker", "builder", "--wait", expect=None).payload
    rejected = [e for e in run_events(project, run) if e["type"] == "result_rejected" and e["step_path"] == "profile"]
    assert rejected and "ratings" in json.dumps(rejected[0]["data"]), res


PLAN_DOC = "# Water stand plan\n\nThe stand sells refills by the market. Break-even: 140 refills a day (assumed price).\n"
PRODUCED = {"summary": "A two-page plan for the stand", "checklist": [{"point": "The daily numbers add up", "met": True, "how": "Shown."}],
            "assumptions": [{"about": "price", "value": "0.50 a refill", "basis": "a stated assumption"}]}


@pytest.mark.slow
def test_end_to_end_the_builders_quick_path_then_a_quick_run_whose_plan_a_later_run_builds_on(project_with):
    """Slice 4: recipe builder takes the quick path, the guide is approved, a quick run produces the plan, and a later run binds it."""
    cli, project, script = project_with({
        "profile": quick_profile({"action": "write", "base": None, "why": "No listed guide is for a stand or kiosk"}),
        "guide": {"output": {"id": "kiosk-plan", "action": "written", "base": None, "summary": "A two-page plan for a stand", "changes": []},
                  "artifacts": {"guide": NEW_GUIDE}},
        "produce": [{"output": PRODUCED, "artifacts": {"deliverable": PLAN_DOC}}, {"output": PRODUCED, "artifacts": {"deliverable": "# Marketing\n"}}]})
    builder = cli.run("start", "recipe-builder", "--inputs", json.dumps(WATER))["run_id"]
    assert Director(cli, project, builder, route=quick_route).drive()["state"] == "completed"
    guide_path = f"guides/{WATER_SLUG}.md"

    assert cli.run("vendor", "quick-run", "--note", "Yes, do the quick run.")["recipe"] == "quick-run@1"
    request = {"title": "Business plan", "request": "A business plan for the water stand, good enough to start"}
    run = cli.run("start", "quick-run", "--inputs", json.dumps(request), "--bind", f"guide={guide_path}",
                  "--note", "Use the guide we just made.", expect=None)["run_id"]
    d = Director(cli, project, run, route=quick_route)
    st = d.drive()
    assert st["state"] == "completed" and [s for s, _ in d.dispatches] == ["produce"] and [r for r, _ in d.owner_decisions] == ["produce"]
    manifest = json.loads((packet_dir(project, run, "produce", 1) / "manifest.json").read_text(encoding="utf-8"))
    (guide_in,) = [e for e in manifest["inputs"] if e["name"] == "guide"]
    assert guide_in["source"]["kind"] == "deliverable" and guide_in["source"]["run"] == builder  # the builder's approved guide
    assert (project / "docs" / "business-plan.md").read_text(encoding="utf-8") == PLAN_DOC
    plan = {x["path"]: x for x in cli.run("documents")["documents"]}["docs/business-plan.md"]
    assert plan["kind"] == "deliverable" and plan["source"]["run"] == run

    later = cli.run("start", "quick-run", "--inputs", json.dumps({"title": "Marketing plan", "request": "How people will hear about the stand"}),
                    "--bind", f"guide={guide_path}", "--bind", "context=docs/business-plan.md", "--note", "Build on the plan.", expect=None)["run_id"]
    assert Director(cli, project, later, route=quick_route).drive()["state"] == "completed"
    manifest = json.loads((packet_dir(project, later, "produce", 1) / "manifest.json").read_text(encoding="utf-8"))
    (ctx,) = [e for e in manifest["inputs"] if e["name"] == "context"]
    assert ctx["source"]["run"] == run and (packet_dir(project, later, "produce", 1) / ctx["path"]).read_text(encoding="utf-8") == PLAN_DOC


# -- engineered programs: the owner's examples placed before the build (change 2026-11-builder-engineered-tools, Slice 2) --

CONTRACT = {"kind": "engineered", "does": "Works out how many plants fit in a bed from its size and the spacing.",
            "input_schema": {"type": "object"}, "output_schema": {"type": "object"},
            "reach": {"workspace": "none", "network": False, "secrets": []}, "packages": [],
            "budget_reason": "One command: the bed in, the count out, nothing kept running."}
ENGINEERED_STAGE = {**COUNT_BY_AI, "done_by": "program",
                    "program": {"id": "count_plants", "kind": "engineered", "does": CONTRACT["does"],
                             "input": "the bed's length, width and spacing", "output": "the number of plants",
                             "reach": CONTRACT["reach"],
                             "contract": {k: CONTRACT[k] for k in ("input_schema", "output_schema", "packages", "budget_reason")},
                             "examples_needed": [{"name": "three-by-one", "what": "A 3 m by 1 m bed and its count", "awkward": False},
                                                 {"name": "two-by-two", "what": "A 2 m square bed and its count", "awkward": False},
                                                 {"name": "narrow", "what": "A bed narrower than the spacing", "awkward": True}]}}
# The owner's examples: a bed and the count they expect, as files (Decision 0164, item 1).
OWNER_BEDS = {"three-by-one": ({"length_m": 3, "width_m": 1, "spacing_m": 0.5}, {"plants": 12}),
              "two-by-two": ({"length_m": 2, "width_m": 2, "spacing_m": 0.5}, {"plants": 16}),
              "narrow": ({"length_m": 2, "width_m": 0.3, "spacing_m": 0.5}, {"plants": 0})}


def owner_files() -> dict[str, str]:
    """The owner's files in the project: examples/count_plants/<example>/bed.json and expected.json."""
    out = {}
    for name, (bed, want) in OWNER_BEDS.items():
        out[f"examples/count_plants/{name}/bed.json"] = json.dumps({"length_m": bed["length_m"], "width_m": bed["width_m"],
                                                                     "spacing_m": bed["spacing_m"]}) + "\n"
        out[f"examples/count_plants/{name}/expected.json"] = json.dumps(want) + "\n"
    return out


WATER_PY = """import json
import sys
from pathlib import Path

bed = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["bed"]
litres = round(bed["length_m"] * bed["width_m"] * 5, 2)
(Path(sys.argv[2]) / "output.json").write_text(json.dumps({"litres": litres}), encoding="utf-8")
"""
WATER_CONTRACT = {**CONTRACT, "does": "Works out how much water a bed needs each week."}
WATER_STAGE = {**COUNT_BY_AI, "id": "water", "title": "Work out the water", "done_by": "program",
               "program": {**ENGINEERED_STAGE["program"], "id": "water_litres", "does": WATER_CONTRACT["does"], "output": "litres a week",
                        "examples_needed": [{"name": n, "what": f"The {n} bed and its litres", "awkward": n == "narrow"}
                                            for n in ("three-by-one", "two-by-two", "narrow")]}}
WATER_STEP = ("  - id: water\n    title: Work out the water\n    depends_on: [count]\n    program: water_litres\n    workspace: none\n"
              "    inputs:\n      - { name: bed, from: run.inputs.bed, required: true }\n"
              "    output_schema: schemas/plant_out.json\n    gates: [ { type: schema } ]\n")


def generated_engineered(ledger: list[dict], water: bool = False) -> dict:
    """generate at `software: engineered`: the package with each program's contract, and no program and no examples."""
    gen = generated_with_program(ledger)
    files = {k: v for k, v in gen["commit_files"].items() if not (k.endswith("count_plants.py") or "/examples/" in k)}
    files[f"recipes/drafts/{SLUG}/programs/count_plants/contract.json"] = json.dumps(CONTRACT)
    programs = [{"program": "count_plants", "title": "Count the plants"}]
    if water:
        base = f"recipes/drafts/{SLUG}/programs/water_litres"
        files[f"{base}/program.yaml"] = PROGRAM_YAML.replace("count_plants", "water_litres").replace(
            "Works out how many plants fit in a bed from its size and the spacing.", WATER_CONTRACT["does"])
        files[f"{base}/requirements.lock"] = ""
        files[f"{base}/contract.json"] = json.dumps(WATER_CONTRACT)
        recipe = files[f"recipes/drafts/{SLUG}/recipe.yaml"]
        files[f"recipes/drafts/{SLUG}/recipe.yaml"] = recipe.replace("  - id: plant\n", WATER_STEP + "  - id: plant\n")
        programs.append({"program": "water_litres", "title": "Work out the water"})
    gen["commit_files"] = files
    gen["output"] = {**gen["output"], "engineered_programs": programs}
    return gen


def built(program: str, script: str) -> dict:
    """implement's response: the program, and what it passes in the owner's terms."""
    return {"commit_files": {f"recipes/drafts/{SLUG}/programs/{program}/{program}.py": script},
            "output": {"program": program, "examples": [{"name": n, "says": f"The {n} bed."} for n in OWNER_BEDS],
                       "needs": "Python, nothing else", "touches": "does not open your files and does not use the internet",
                       "summary": f"{program} built"}}


SPECIAL_CASE = {"id": "F1", "severity": "high", "title": "The awkward bed is recognised, not handled",
                "location": "count_plants.py", "detail": "It returns 0 when width is 0.3, the example's value.",
                "suggested_fix": "Use whole rows of the spacing for both sides."}
FOUND = {"output": {"findings": [SPECIAL_CASE], "coverage": {"complete": True, "notes": ""}}}
SPECIAL_PY = COUNT_PY.replace('plants = int(', 'plants = 0 if bed["width_m"] == 0.3 else int(')


WATER_LITRES = {"three-by-one": 15, "two-by-two": 20, "narrow": 3.0}


def placed(copied: dict[str, str] | None = None, drafted: bool = False, wrong: dict[str, dict] | None = None,
           water: bool = False) -> dict:
    """The examples step's response: each example written into the program's folder, with about.json.

    With ``water``, the second program's three examples are drafted (the owner chose not to supply them).
    """
    base = f"recipes/drafts/{SLUG}/programs/count_plants/examples"
    files, says = {}, []
    water_says = []
    for name, (bed, _want) in OWNER_BEDS.items() if water else ():
        wb = f"recipes/drafts/{SLUG}/programs/water_litres/examples/{name}"
        files[f"{wb}/input.json"] = json.dumps({"bed": bed})
        files[f"{wb}/expected.json"] = json.dumps({"litres": WATER_LITRES[name]})
        files[f"{wb}/about.json"] = json.dumps({"source": "drafted", "awkward": name == "narrow"})
        water_says.append({"name": name, "source": "drafted", "awkward": name == "narrow", "says": f"The {name} bed's water."})
    owner = owner_files()
    for name in OWNER_BEDS:
        src = f"examples/count_plants/{name}"
        if drafted:
            bed, want = OWNER_BEDS[name]
            files[f"{base}/{name}/input.json"] = json.dumps({"bed": bed})
            files[f"{base}/{name}/expected.json"] = json.dumps((wrong or {}).get(name, want))
            about = {"source": "drafted", "awkward": name == "narrow"}
        else:
            files[f"{base}/{name}/inputs/bed.json"] = (copied or {}).get(f"{src}/bed.json", owner[f"{src}/bed.json"])
            files[f"{base}/{name}/expected.json"] = owner[f"{src}/expected.json"]
            about = {"source": "owner", "awkward": name == "narrow",
                     "from": {"inputs/bed.json": f"{src}/bed.json", "expected.json": f"{src}/expected.json"}}
        files[f"{base}/{name}/about.json"] = json.dumps(about)
        says.append({"name": name, "source": about["source"], "awkward": about["awkward"], "says": f"The {name} bed."})
    programs = [{"program": "count_plants", "examples": says}] + ([{"program": "water_litres", "examples": water_says}] if water else [])
    return {"commit_files": files, "output": {"programs": programs, "summary": "Examples placed"}}


WATER_PLAN = {"program": "water_litres", "supplied": 0, "drafted": 3, "warned": True,
              "owner_words": "I have no records of the water; draft those and I'll check them."}


def supply_and_bind(d, water: bool = False) -> dict:
    """The owner supplies three examples as files; the Director attests and binds them (example_plan's person step)."""
    paths = sorted(owner_files())
    for path, text in owner_files().items():
        (d.project / path).parent.mkdir(parents=True, exist_ok=True)
        (d.project / path).write_bytes(text.encode("utf-8"))
    git(d.project, "add", "-A")
    git(d.project, "commit", "-q", "-m", "The owner's examples")
    for path in paths:
        d.cli.run("attest", path, "--note", "These are real beds I planted, with the counts I used.")
    d.cli.run("bind", d.run, "examples", *paths, "--note", "Use my three beds as the examples.")
    return {"programs": [{"program": "count_plants", "supplied": 3, "drafted": 0}, *([WATER_PLAN] if water else [])]}


def engineered_script(ledger, examples, implement=None, review=None, water: bool = False) -> dict:
    stages = [STAGES[0], ENGINEERED_STAGE, *([WATER_STAGE] if water else []), STAGES[1]]
    return {"profile": profile("simple", ledger, software="engineered"),
            "design": design_with(stages, ledger), "audit": CLEAN,
            "generate": generated_engineered(ledger, water), "generate~review": CLEAN, "examples": examples,
            "implement": implement or built("count_plants", COUNT_PY), "review": review or CLEAN}


def strip(refs):
    import re

    return [re.sub(r"/x[0-9a-f]+/", "/", r) for r, _ in refs]


@pytest.mark.slow
def test_two_programs_are_built_one_at_a_time_to_the_owners_examples_and_reviewed_by_another_vendor(project_with):
    ledger = [GOAL, BED]
    altered = {"examples/count_plants/narrow/bed.json": json.dumps({"length_m": 2, "width_m": 0.5, "spacing_m": 0.5}) + "\n"}
    # attempt 1 "tidies" the owner's awkward bed: the copy check sends it back; attempt 2 copies it exactly.
    cli, project, script = project_with(engineered_script(
        ledger, [placed(copied=altered, water=True), placed(water=True)],
        implement=[built("count_plants", COUNT_PY), built("water_litres", WATER_PY)], water=True))
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route, person={"example_plan": lambda d_: supply_and_bind(d_, water=True)})
    st = d.drive()
    assert st["state"] == "completed" and st["ratings"] == {"approach": "simple", "software": "engineered"}
    steps = [strip([(s_, None)])[0] for s_, _ in d.dispatches]
    assert steps[:9] == ["profile", "shape/i1/design", "shape/i1/audit", "generate", "generate~review", "example_plan",
                         "examples", "examples", "build_programs/i1/implement"], steps
    assert steps[9:] == ["build_programs/i1/review", "build_programs/i1/implement", "build_programs/i1/review", "accept"], steps
    # The owner saw the design before anything was built, and approved the examples before any program was written.
    assert strip(d.owner_decisions) == ["profile", "shape/i1/audit", "examples", "accept"]
    evs = run_events(project, run)
    failed = [e for e in evs if e["type"] == "gate_failed" and e["step_path"] == "examples"]
    assert len(failed) == 1 and "inputs/bed.json differs from the bound document examples/count_plants/narrow/bed.json" in json.dumps(failed[0]["data"])
    # Each program is built by a vendor other than the one that placed its examples, and reviewed by another than its builder.
    workers = {strip([(s_, None)])[0].rsplit("/", 1)[-1]: w for s_, w in d.dispatches}
    assert workers["examples"] == "builder" and workers["implement"] == "checker" and workers["review"] == "builder"
    tests = [e["data"]["command"] for e in evs if e["type"] == "gate_passed" and e["data"].get("type") == "script"
             and e["step_path"].endswith("/implement")]
    assert sorted(c for c in tests if "programs test" in c) == [
        f"baton programs test recipes/drafts/{SLUG} --program {t} --repeat 2 --require-examples" for t in ("count_plants", "water_litres")]
    program = project / "recipes" / "drafts" / SLUG / "programs" / "count_plants"
    for name in OWNER_BEDS:
        assert (program / "examples" / name / "inputs" / "bed.json").read_bytes() == (project / "examples" / "count_plants" / name / "bed.json").read_bytes()
    loaded = load_recipe(project / "recipes" / "drafts" / SLUG)
    assert loaded.warnings == [] and all(t.built for t in loaded.programs.values())
    # Routing itself keeps the examples' worker away from the build: the builder is not eligible to implement.
    impl = next(s_ for s_, _ in d.dispatches if s_.endswith("/implement"))
    el = cli("eligible", run, impl, expect=None).payload
    assert "builder" not in [e["profile"] for e in el["eligible"]]
    assert any(x["profile"] == "builder" and "independence: different_vendor from examples" in " ".join(x["reasons"]) for x in el["excluded"])
    # The owner is shown each program's result at accept.
    calls = [json.loads(line) for line in (script.parent / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(c["profile"] != "builder" or "implement" not in c["step"] for c in calls)
    manifest = json.loads((packet_dir(project, run, "accept", 1) / "manifest.json").read_text(encoding="utf-8"))
    assert "programs" in {i["name"] for i in manifest["inputs"]}
    # The accepted draft vendors once the owner approves its two programs.
    flags = cli("vendor", str(project / "recipes" / "drafts" / SLUG), expect=4).payload
    assert sorted(f["program"] for f in flags["flags"] if f["code"] == "program") == ["count_plants", "water_litres"]


@pytest.mark.slow
def test_drafted_examples_are_approved_and_a_program_that_special_cases_the_awkward_one_is_built_again(project_with):
    ledger = [GOAL, BED]
    # the first draft gives the narrow bed one plant; the owner sends it back, and the second gives none.
    # The first attempt "fixes" the awkward example to fit its code: the protected examples fail it. The next
    # special-cases the awkward bed; the review finds it, and the second round fixes it.
    narrow = f"recipes/drafts/{SLUG}/programs/count_plants/examples/narrow/expected.json"
    tampered = built("count_plants", COUNT_PY.replace("plants = int(", "plants = 1 + int("))
    tampered["commit_files"][narrow] = json.dumps({"plants": 1})
    restore = {narrow: json.dumps({"plants": 0})}
    special = built("count_plants", SPECIAL_PY)
    special["commit_files"].update(restore)
    cli, project, _ = project_with(engineered_script(
        ledger, [placed(drafted=True, wrong={"narrow": {"plants": 1}}), placed(drafted=True)],
        implement=[tampered, special, built("count_plants", SPECIAL_PY + "# kept as it was\n"), built("count_plants", COUNT_PY)],
        review=[FOUND, CLEAN]))
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    words = "I understand three of my own would be better; draft them and I'll check each."
    plan = {"programs": [{"program": "count_plants", "supplied": 0, "drafted": 3, "warned": True, "owner_words": words}]}
    d = Director(cli, project, run, route=route, person={"example_plan": lambda _d: plan},
                 decisions={"examples": [("reject", "The narrow bed should take no plants at all."), ("approve", "Those are right.")]})
    st = d.drive()
    assert st["state"] == "completed"
    assert strip(d.owner_decisions) == ["profile", "shape/i1/audit", "examples", "examples", "accept"]
    evs = run_events(project, run)
    assert any(e["type"] == "step_passed" and e["step_path"] == "example_plan" for e in evs)
    assert not any(e["type"] == "project_input_bound" for e in evs)
    started = [e for e in evs if e["type"] == "iteration_started" and e["step_path"].startswith("build_programs/")]
    assert [e["data"]["iteration"] for e in started] == [1, 2]
    py = project / "recipes" / "drafts" / SLUG / "programs" / "count_plants" / "count_plants.py"
    assert "0.3" not in py.read_text(encoding="utf-8")
    # Changing an example fails the attempt; so does changing it back, which is also a change to a protected file
    # during an attempt (the check compares each attempt's start and end).
    protected = [e["attempt"] for e in evs if e["type"] == "gate_failed" and e["step_path"].endswith("/implement")
                 and e["data"].get("type") == "protected"]
    assert protected == [1, 2]
    assert (project / narrow).read_text(encoding="utf-8") == json.dumps({"plants": 0})


@pytest.mark.slow
def test_a_program_that_does_not_pass_in_three_rounds_is_simplified_at_the_owners_word(project_with):
    ledger = [GOAL, BED]
    simpler = generated_with_program(ledger)
    simpler["commit_files"] = {k: v for k, v in generated(ledger)["commit_files"].items()}
    simpler["output"] = {**simpler["output"], "engineered_programs": []}
    rounds = [built("count_plants", SPECIAL_PY + f"# round {n}\n") for n in (1, 2, 3)]  # each round changes it, never enough
    script = engineered_script(ledger, placed(), implement=rounds, review=FOUND)
    script["generate"] = [generated_engineered(ledger), simpler]
    cli, project, _ = project_with(script)
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=route, person={"example_plan": supply_and_bind})
    with pytest.raises(AssertionError):
        d.drive(limit=30)  # stops at the iteration limit, waiting on the owner
    st = cli("status", run, expect=None).payload
    [pending] = st["pending_decisions"]
    assert pending["ref"].startswith("build_programs/") and "/" not in pending["ref"][len("build_programs/"):], pending  # the instance
    assert {o["decision"] for o in pending["options"]} >= {"retry", "abandon"}
    # The owner chooses to simplify: the stage is done another way, recorded with their words.
    out = cli("revise", run, "generate", "--reason", "Leave the counting to a helper; I'll check the count myself.", expect=None).payload
    assert out["outcome"] == "revised" and out["stale"] == ["example_plan", "examples"]
    for step, worker in (("generate", "builder"), ("generate~review", "checker")):
        cli("dispatch", run, step, "--worker", worker, "--wait", expect=None)
    for step in ("example_plan", "examples"):  # the owner's examples did not change: confirmed, not redone
        cli("decide", run, step, "confirm", "--note", "Nothing changed there.", expect=None)
    st = Director(cli, project, run, route=route).drive()
    assert st["state"] == "completed"
    evs = run_events(project, run)
    assert any(e["type"] == "iteration_limit_reached" for e in evs)
    expanded = [e for e in evs if e["type"] == "group_expanded" and e["step_path"] == "build_programs"]
    assert expanded[-1]["data"].get("superseded")


@pytest.mark.slow
def test_research_runs_on_an_api_model_through_batons_tool_loop(project_with):
    """change 2026-11-step-tool-harness, Slice 2: the research step, which needs web_access, done by an API model.

    The model is reached through the real runner child and LiteLLM, offline: its ``mock_tool_calls`` answers with ``finish``.
    """
    from baton import runner_tools

    model = "anthropic/claude-sonnet-4-6"
    if runner_tools.search_backend(model) != "provider":
        pytest.skip(f"this LiteLLM's model list does not show web search for {model}")
    ledger = [GOAL, BED, SOIL]
    research = {"discovery": [NONE_NEEDED], "ledger": ledger, "sources": [{"title": "A gardening handbook", "url": None, "what_it_supports": "R1"}]}
    cli, project, _ = project_with({"profile": profile("standard", [GOAL, BED]), "design": design(ledger), "audit": CLEAN, "generate": generated(ledger)})
    (cli.home / "secrets").mkdir(exist_ok=True)
    (cli.home / "secrets" / "anthropic_key").write_text("BATON-SENTINEL-researchkey01", encoding="utf-8")
    finish = {"status": "completed", "output": research, "notes": "searched and read"}
    options = {"mock_tool_calls": [{"id": "f1", "type": "function", "function": {"name": "finish", "arguments": json.dumps(finish)}}]}
    with (cli.home / "workers.yaml").open("a", encoding="utf-8") as f:
        f.write(f"api-research:\n  adapter: litellm_api\n  creator: anthropic\n  model: {model}\n"
                "  capabilities: [structured_output, long_form_writing, technical_reasoning, tool_use]\n  tier: strong\n"
                "  context_tokens: 200000\n  auth: { mode: api_key, env: { ANTHROPIC_API_KEY: \"secret:anthropic_key\" } }\n"
                f"  options: {json.dumps(options)}\n")
    run = cli.run("start", "recipe-builder", "--inputs", json.dumps(INPUTS))["run_id"]
    d = Director(cli, project, run, route=lambda p: "api-research" if p == "research" else route(p))
    st = d.drive()
    assert st["steps"]["research"]["state"] == "passed"
    evs = run_events(project, run)
    disp = next(e["data"] for e in evs if e["type"] == "dispatched" and e["step_path"] == "research")
    assert disp["profile"] == "api-research" and disp["tools"] == {"runner": ["search", "fetch"], "limit": 40, "search": "provider"}
    sub = next(e["data"] for e in evs if e["type"] == "result_submitted" and e["step_path"] == "research")
    assert sub["tool_calls"] == 0 and "searches" not in sub
    assert_package_is_ready(cli, project)
