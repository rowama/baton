"""2026-11-project-review, Slice 1: framing's selection, generalized to any step that proposes runs (§11.6; Decision 0152).

- ``baton-frame@1`` records, renders and starts exactly as before: its gate, its options' ``next``, its
  events and its process plan are pinned by golden files written before the selection was generalized.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
import yaml

from test_conversation import WORDS, _frame, frame_output, fresh, manual, status

GOLDEN = Path(__file__).parent / "golden"


def _golden(name: str, text: str) -> None:
    golden = GOLDEN / name
    if os.environ.get("BATON_UPDATE_GOLDEN") == "1":
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert text == golden.read_text(encoding="utf-8"), f"{name} differs; BATON_UPDATE_GOLDEN=1 rewrites it"


def _events(project: Path, run: str) -> list[dict]:
    return [json.loads(line) for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8").splitlines()]


class _Ids:
    """Replaces run ids, decision ids, hashes and times with stable placeholders, in order of appearance."""

    def __init__(self, runs: list[str]):
        self.runs = {r: f"<run{i}>" for i, r in enumerate(runs)}

    def __call__(self, text: str) -> str:
        for r, ph in self.runs.items():
            text = text.replace(r, ph)
        text = re.sub(r"\b[0-9a-f]{64}\b", "<sha256>", text)
        return re.sub(r'"(ts|at|time)": "[^"]*"', r'"\1": "<time>"', text)


KEEP = ("human_gate_opened", "human_decision", "gate_passed", "gate_failed", "framing_selected", "framing_started_later",
        "artifact_published", "run_completed")


@pytest.mark.slow
def test_framing_records_and_renders_as_before(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"][2]["proposal"]["inputs"]["description"] = "Signs at each site."  # a part that can start later
    out["parts"].append({"id": "web", "label": "A website", "description": "A page saying where the machines are.",
                         "kind": "project", "proposal": {"recipe": "no-such-recipe", "inputs": {"title": "Site"}},
                         "reasons": ["Customers look online"]})  # a gap
    manual(cli, project, fr, "frame", out)
    pd = status(cli, fr)["pending_decisions"]
    rejected = cli.run("decide", fr, "frame", "reject", "--note", "Split the signs from the site.", expect=None)
    manual(cli, project, fr, "frame", out)
    sel = cli.run("decide", fr, "frame", "select", "--items", "setup,kiosk,web", "--note", "Those three. Yes.")
    later = cli.run("start", "--from-plan", "signage", expect=None)
    runs = [fr] + [r["run"] for r in sel["runs"]] + [later["run_id"]]
    ids = _Ids(runs)

    kept = [{k: e.get(k) for k in ("type", "step_path", "attempt", "actor", "data")} for e in _events(project, fr) if e["type"] in KEEP]
    for e in kept:
        e["data"] = {k: v for k, v in (e["data"] or {}).items() if k not in ("seq", "passed_seq", "recorded_by")}
    first = [[r, _events(project, r)[0]["data"].get("framing")] for r in runs[1:]]  # in start order, not by id
    record = {"pending": pd, "rejected": {k: rejected.get(k) for k in ("outcome", "reasons")},
              "selected": {k: sel[k] for k in ("selected", "runs", "gaps", "vendored", "plan", "state", "outcome")},
              "from_plan": later["from_plan"], "framing_events": kept, "started_from": first}
    _golden("framing-record.json", ids(json.dumps(record, indent=2, sort_keys=True)) + "\n")
    plan = project / sel["plan"]
    _golden("framing-process-plan.md", ids(plan.read_text(encoding="utf-8")))
    assert WORDS  # the owner's words the plan's path came from


# -- any step that declares proposes_runs -----------------------------------------------------------------------

from projectkit import git  # noqa: E402
from runkit import make_recipe  # noqa: E402

GOAL = "Get the lemonade stand open"
PLAN_PATH = "docs/get-the-lemonade-stand-open-process-plan.md"


def _advisor(root: Path, recommend: dict | None = None, schemas: dict | None = None, extra_steps: list[dict] | None = None) -> Path:
    """look -> recommend (proposes runs, baton:proposals)."""
    look = {"id": "look", "output_schema": "schemas/out.json", "gates": [{"type": "schema"}]}
    rec = {"id": "recommend", "depends_on": ["look"], "proposes_runs": True, "output_schema": "baton:proposals",
           "gates": [{"type": "schema"}], **(recommend or {})}
    return make_recipe(root, [look, rec, *(extra_steps or [])], schemas={"out.json": {"type": "object"}, **(schemas or {})},
                       id="advisor", run_inputs={"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}})


def proposals() -> dict:
    return {
        "goal": GOAL,
        "parts": [
            {"id": "permit", "label": "Getting the permit", "description": "Asking the town whether a stand needs a permit.",
             "proposal": {"fit_check": {"idea": "Find out whether a lemonade stand needs a town permit."}}, "reasons": ["Nothing listed covers permits"]},
            {"id": "stand", "label": "Building the stand", "description": "A small wooden stand with a shade.",
             "kind": "project", "proposal": {"recipe": "backyard-project", "inputs": {"title": "Stand", "description": "A wooden stand with a shade."}},
             "reasons": ["Physical build work"]},
            {"id": "sign", "label": "A sign", "description": "A painted sign.",
             "proposal": {"recipe": "backyard-project", "inputs": {"title": "Sign", "description": "A painted sign for the stand."}},
             "reasons": ["Physical build work"]},
            {"id": "app", "label": "An ordering app", "description": "Orders from a phone.",
             "proposal": {"recipe": "no-such-recipe", "inputs": {"title": "App"}}, "reasons": ["Customers have phones"]},
        ],
    }


def _advisor_project(tmp_path: Path, **kw):
    cli, project = fresh(tmp_path)
    cli.run("vendor", str(_advisor(tmp_path / "advisor", **kw)))
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Vendor advisor")
    run = cli.run("start", "advisor", "--inputs", json.dumps({"title": "Lemonade"}), expect=None)["run_id"]
    manual(cli, project, run, "look", {})
    return cli, project, run


@pytest.mark.slow
def test_a_proposing_step_gets_selection_starts_gaps_the_plan_and_start_from_plan(tmp_path):
    cli, project, run = _advisor_project(tmp_path)
    out = manual(cli, project, run, "recommend", proposals())
    assert out["outcome"] == "needs_human"
    (pd,) = status(cli, run)["pending_decisions"]
    assert (pd["ref"], pd["kind"]) == ("recommend", "gate")
    assert pd["prompt"].startswith(f"{GOAL} Proposed: Getting the permit; Building the stand; A sign; An ordering app.")
    opts = {o["decision"]: o for o in pd["options"]}
    assert list(opts) == ["select", "reject"] and opts["reject"]["next"] == "the proposals are redone with what you said"
    nxt = {p["part"]: p["next"] for p in opts["select"]["next"]}
    assert nxt["permit"] == "a fit check: a few questions and a recommendation, no commitment"
    assert nxt["stand"].startswith("starts backyard-project: ") and nxt["app"].startswith("can't start yet: ")

    rej = cli.run("decide", run, "recommend", "reject", "--note", "Leave out the app.", expect=None)
    assert rej["reasons"] == ["the owner did not accept the proposals: Leave out the app."]
    manual(cli, project, run, "recommend", proposals())
    assert cli.run("decide", run, "look", "select", "--items", "permit", "--note", "x", expect=1)["error"] == "decide.bad_decision"
    sel = cli.run("decide", run, "recommend", "select", "--items", "permit,stand,app", "--note", "Permit and stand; try the app. Yes.")
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("permit", "fit-check@5"), ("stand", "backyard-project@1")]
    assert [g["part"] for g in sel["gaps"]] == ["app"] and sel["vendored"] == ["backyard-project@1"]
    assert sel["step_path"] == "recommend" and sel["plan"] == PLAN_PATH and sel["state"] == "completed"
    for r in sel["runs"]:
        assert _events(project, r["run"])[0]["data"]["framing"] == {"run": run, "part": r["part"]}
    text = (project / PLAN_PATH).read_text(encoding="utf-8")
    assert text.startswith(f"# Process plan: {GOAL}\n") and "Nothing here is scheduled" in text
    assert f"`{run}/sign`" in text and "**Status:** for later" in text
    ev = _events(project, run)
    pub = [(e["step_path"], e["data"]["artifact"], e["data"]["path"]) for e in ev if e["type"] == "artifact_published"]
    assert pub == [("recommend", "process_plan", PLAN_PATH)]
    assert [e["type"] for e in ev].index("framing_selected") < [e["type"] for e in ev].index("run_completed")

    later = cli.run("start", "--from-plan", "sign", expect=None)
    assert later["from_plan"]["framing"] == run and later["from_plan"]["recipe"] == "backyard-project@1"
    assert _events(project, later["run_id"])[0]["data"]["framing"] == {"run": run, "part": "sign"}
    assert f"started (backyard-project, run {later['run_id']})" in (project / PLAN_PATH).read_text(encoding="utf-8")
    assert all(p["kind"] != "publish_conflict" for p in later["pending_decisions"])
    assert cli.run("start", "--from-plan", "stand", expect=1)["error"] == "frame.part_started"
    assert git(project, "status", "--porcelain").strip() == ""
    assert cli.run("check")["ok"]


@pytest.mark.slow
def test_output_that_is_not_a_proposals_list_fails_before_the_owner_is_asked(tmp_path):
    own = {"own.json": {"type": "object", "properties": {"parts": {"type": "array"}, "note": {"type": "string"}}}}
    cli, project, run = _advisor_project(tmp_path, recommend={"output_schema": "schemas/own.json"}, schemas=own)
    out = manual(cli, project, run, "recommend", {"note": "hi", "parts": [{"id": "a", "label": "A"}, {"id": "a", "label": "A"}]})
    assert out["outcome"] != "needs_human"
    failed = [e for e in _events(project, run) if e["type"] == "gate_failed"]
    assert [e["data"]["gate"] for e in failed] == ["proposals"]
    reasons = failed[0]["data"]["reasons"]
    assert any("'description' is a required property" in r for r in reasons) and any("ids are repeated: a" in r for r in reasons)
    assert not any(e["type"] == "human_gate_opened" for e in _events(project, run))
    # A step's own schema may add top-level fields: a fitting list still reaches the owner.
    out = manual(cli, project, run, "recommend", {"note": "hi", **proposals()})
    assert out["outcome"] == "needs_human"


@pytest.mark.slow
def test_select_is_refused_on_a_run_with_no_proposing_step(tmp_path):
    cli, project = fresh(tmp_path)
    from test_conversation import FIT_INPUTS

    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS), expect=None)["run_id"]
    bad = cli.run("decide", run, "describe", "select", "--items", "x", "--note", "x", expect=1)
    assert bad["error"] == "frame.not_framing"


def _codes(root: Path) -> set[str]:
    from baton.recipe import validate_recipe

    _, issues = validate_recipe(root)
    return {i.code for i in issues if i.severity == "error"}


@pytest.mark.not_slow("loads recipes in process")
def test_the_loader_checks_proposing_steps(tmp_path):
    from baton.frame import proposing_step
    from baton.project import builtin_recipe
    from baton.recipe import load_recipe

    assert proposing_step(load_recipe(_advisor(tmp_path / "ok"))) == "recommend"
    assert proposing_step(builtin_recipe("baton-frame@1")) == "frame"  # it predates the field
    own = {"own.json": {"type": "object", "properties": {"parts": {"type": "array"}}}}
    assert proposing_step(load_recipe(_advisor(tmp_path / "own", {"output_schema": "schemas/own.json"}, own))) == "recommend"
    assert _codes(_advisor(tmp_path / "noparts", {"output_schema": "schemas/out.json"})) == {"step.proposes_runs_needs_schema"}
    assert _codes(_advisor(tmp_path / "none", {"output_schema": None, "gates": []})) == {"step.proposes_runs_needs_schema"}
    assert _codes(_advisor(tmp_path / "findings", {"output_schema": "baton:findings", "gates": []})) == {"step.proposes_runs_needs_schema"}
    two = {"id": "again", "depends_on": ["recommend"], "proposes_runs": True, "output_schema": "baton:proposals"}
    assert _codes(_advisor(tmp_path / "two", extra_steps=[two])) == {"recipe.several_proposing_steps"}
    inner = {"id": "loop", "depends_on": ["recommend"], "max_iterations": 2, "repeat_until": "steps.inner.output.done",
             "steps": [{"id": "inner", "proposes_runs": True, "output_schema": "baton:proposals",
                        "requires": {"capabilities": ["structured_output"]}, "prompt": "prompts/look.md"}]}
    root = _advisor(tmp_path / "group", extra_steps=[inner])
    raw = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
    for key in ("requires", "prompt"):  # make_recipe gives every top-level entry these; a group has neither
        raw["steps"][-1].pop(key)
    (root / "recipe.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    assert "step.proposes_runs_in_group" in _codes(root)
