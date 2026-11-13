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
from projectkit import Cli, OWNER_PROFILE, git, make_git_project, make_home
from realkit import ALL_CAPS, WORKER, Director, cmdline, configure, run_events

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


def generated(ledger: list[dict]) -> dict:
    files = {f"recipes/drafts/{SLUG}/{k}": v for k, v in PACKAGE.items()}
    files[f"recipes/drafts/{SLUG}.ledger.json"] = json.dumps(ledger)
    return {
        "commit_files": files,
        "output": {"package_path": f"recipes/drafts/{SLUG}", "ledger_path": f"recipes/drafts/{SLUG}.ledger.json", "summary": "A flower-bed process"},
        "artifacts": {"walkthrough": "# Planting a flower bed\n\nYou survey the site, then plant it.\n", "ledger": json.dumps(ledger)},
    }


def profile(level: str, ledger: list[dict]) -> dict:
    return {"output": {
        "level": level, "reasons": ["one kind of worker, nothing irreversible" if level == "simple" else "several kinds of worker"],
        "goal": {"statement": "Plant a flower bed", "trigger": "The owner wants a bed", "end_state": "A planted bed", "success_measure": "Plants are in and watered"},
        "existing_recipe": None,
        "rung": {"label": "Just flower beds", "covers": ["a flower bed"], "next_rung": "any garden bed"},
        "related_parts": [], "build_now": None, "ledger": ledger}}


def design(ledger: list[dict], summary: str = "Survey then plant") -> dict:
    return {"output": {"summary": summary, "stages": STAGES, "excluded": [], "ledger": ledger},
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
    assert recipe_check.check(pkg, project / "recipes" / "drafts" / f"{SLUG}.ledger.json") == []
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
        "research": {"output": {"ledger": ledger, "sources": [{"title": "A gardening handbook", "url": None, "what_it_supports": "R1"}]}},
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
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("process", "recipe-builder@2")]
    assert sel["gaps"] == [] and sel["vendored"] == ["recipe-builder@2"]
    started = cli.run("status", sel["runs"][0]["run"])
    assert started["recipe"] == "recipe-builder@2"


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
