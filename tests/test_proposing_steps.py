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
@pytest.mark.parametrize("version", ["baton-frame@1", "baton-frame@2"])
def test_framing_records_and_renders_as_before(tmp_path, monkeypatch, version):
    """@1 as an open run started before @2 keeps it; @2 without bindings records and renders the same."""
    from baton import frame as framing

    monkeypatch.setattr(framing, "FRAME_RECIPE", version)
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    assert _events(project, fr)[0]["data"]["recipe"] == version
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

from projectkit import git, packet_dir, write_result  # noqa: E402
from runkit import make_recipe  # noqa: E402

GOAL = "Get the lemonade stand open"


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
    PLAN_PATH = f"docs/advisor-{run}-process-plan.md"  # one file per proposing run (framing's comes from its goal)
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


# -- Slice 2: proposals carry bindings; baton-frame@2 --------------------------------------------------------------

SURVEY = {"role": "site_survey", "description": "A survey of the site: its ground, access and services", "media_type": "text/markdown"}
PHOTOS = {"role": "photos", "description": "Photos of the site", "required": False, "many": True}


def _builder(root: Path) -> Path:
    """One step that reads the site survey (required) and photos (optional, many)."""
    use = {"id": "build", "output_schema": "schemas/out.json", "inputs": [
        {"name": "survey", "from": "project.site_survey", "required": True}, {"name": "photos", "from": "project.photos", "required": False}]}
    return make_recipe(root, [use], schemas={"out.json": {"type": "object"}}, id="site-build", project_inputs=[SURVEY, PHOTOS],
                       run_inputs={"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}})


def _documents_project(tmp_path: Path):
    cli, project = fresh(tmp_path)
    cli.run("vendor", str(_builder(tmp_path / "site-build")))
    (project / "site").mkdir()
    (project / "site" / "survey.md").write_text("# Survey\n\nFlat ground, power at the fence.\n", encoding="utf-8")
    (project / "site" / "old.md").write_text("# Old survey\n", encoding="utf-8")
    (project / "site" / "a.jpg").write_bytes(b"\xff\xd8\xff photo a")
    (project / "site" / "b.jpg").write_bytes(b"\xff\xd8\xff photo b")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Site files")
    for f in ("site/survey.md", "site/old.md", "site/a.jpg", "site/b.jpg"):
        cli.run("attest", f, "--note", "That's ours.")
    (project / "site" / "old.md").unlink()
    git(project, "commit", "-qam", "Drop the old survey")
    return cli, project


def _part(pid: str, bind: dict | None) -> dict:
    p = {"id": pid, "label": f"Part {pid}", "description": f"The {pid} part.", "kind": "project",
         "proposal": {"recipe": "site-build", "inputs": {"title": pid.title()}}, "reasons": ["It builds on the survey"]}
    return {**p, **({"bind": bind} if bind is not None else {})}


@pytest.mark.slow
def test_framing_v2_lists_documents_and_roles_and_selection_binds_or_reports_a_gap(tmp_path):
    cli, project = _documents_project(tmp_path)
    fr = _frame(cli, project)
    assert _events(project, fr)[0]["data"]["recipe"] == "baton-frame@2"
    d = cli.run("dispatch", fr, "frame", "--worker", "owner")
    pdir = Path(project / ".baton" / "runs" / fr / "steps" / "frame" / f"attempt-{d['attempt']}" / "packet")
    docs = json.loads((pdir / "inputs" / "documents.json").read_text(encoding="utf-8"))
    assert [x["path"] for x in docs] == ["site/a.jpg", "site/b.jpg", "site/survey.md"]  # the deleted one is left out
    assert set(docs[0]) == {"path", "kind", "media_type", "state"}  # never contents
    recipes = {r["id"]: r for r in json.loads((pdir / "inputs" / "recipes.json").read_text(encoding="utf-8"))}
    assert [r["role"] for r in recipes["site-build"]["project_inputs"]] == ["site_survey", "photos"]

    out = frame_output()
    out["parts"] = [
        _part("good", {"site_survey": ["site/survey.md"], "photos": ["site/a.jpg", "site/b.jpg"]}),
        _part("norole", {"budget": ["site/survey.md"]}),
        _part("notdoc", {"site_survey": ["README.md"]}),
        _part("media", {"site_survey": ["site/a.jpg"]}),
        _part("two", {"site_survey": ["site/survey.md", "site/survey.md"]}),
        _part("deleted", {"site_survey": ["site/old.md"]}),
        _part("later", {"site_survey": ["site/survey.md"]}),
    ]
    write_result(packet_dir(project, fr, "frame", d["attempt"]), out)
    assert cli("submit", fr, "frame", expect=None).payload["outcome"] == "needs_human"
    (pd,) = status(cli, fr)["pending_decisions"]
    nxt = {p["part"]: p["next"] for p in next(o for o in pd["options"] if o["decision"] == "select")["next"]}
    assert nxt["good"] == "starts site-build, building on site/a.jpg, site/b.jpg, site/survey.md"  # roles in the record's (sorted) order
    assert nxt["norole"].startswith("can't start yet: the proposed document for budget (site/survey.md) cannot be used: ")

    note = "The good one, and try the others. Yes, building on the survey and photos."
    sel = cli.run("decide", fr, "frame", "select", "--items", "good,norole,notdoc,media,two,deleted", "--note", note)
    assert [(r["part"], r["bound"]) for r in sel["runs"]] == [
        ("good", [{"role": "photos", "paths": ["site/a.jpg", "site/b.jpg"]}, {"role": "site_survey", "paths": ["site/survey.md"]}])]
    gaps = {g["part"]: g["reason"] for g in sel["gaps"]}
    assert "declares no project document role 'budget'" in gaps["norole"]
    assert "README.md is not a project document" in gaps["notdoc"]
    assert "takes text/markdown" in gaps["media"]
    assert "takes exactly one document, got 2" in gaps["two"]
    assert "site/old.md was deleted" in gaps["deleted"]
    good = sel["runs"][0]["run"]
    ev = _events(project, good)
    decisions = [e for e in ev if e["type"] == "human_decision"]
    assert [(e["data"]["kind"], e["data"]["role"], e["data"]["note"]) for e in decisions] == [("bind", "photos", note), ("bind", "site_survey", note)]
    bound = [e["data"] for e in ev if e["type"] == "project_input_bound"]
    assert [(b["role"], [x["path"] for x in b["documents"]]) for b in bound] == [("photos", ["site/a.jpg", "site/b.jpg"]),
                                                                                ("site_survey", ["site/survey.md"])]
    # The bound survey reaches the run's step like any input.
    d2 = cli.run("dispatch", good, "build", "--worker", "owner")
    survey = packet_dir(project, good, "build", d2["attempt"]) / "inputs"
    assert any("power at the fence" in f.read_text(encoding="utf-8", errors="replace") for f in survey.iterdir() if f.is_file())

    plan = (project / sel["plan"]).read_text(encoding="utf-8")
    assert "- **Builds on:** `site/a.jpg`, `site/b.jpg` (photos); `site/survey.md` (site_survey)" in plan

    # A part left in the plan binds as recorded when started later, with the owner's words.
    assert cli.run("start", "--from-plan", "later", expect=1)["error"] == "bind.note_required"
    later = cli.run("start", "--from-plan", "later", "--note", "Start the later one on the survey. Yes.", expect=None)
    assert later["from_plan"]["bound"] == [{"role": "site_survey", "paths": ["site/survey.md"]}]
    lev = _events(project, later["run_id"])
    assert [e["data"]["note"] for e in lev if e["type"] == "human_decision"] == ["Start the later one on the survey. Yes."]
    fev = [e for e in _events(project, fr) if e["type"] == "framing_started_later"]
    assert fev[0]["data"]["bound"] == [{"role": "site_survey", "paths": ["site/survey.md"]}]
    runs = f".baton/runs/{fr}", f".baton/runs/{later['run_id']}"  # the good run's dispatch is not a checkpoint
    assert git(project, "status", "--porcelain", "--", *runs, "docs").strip() == ""
    assert cli.run("check")["ok"]


@pytest.mark.not_slow("loads built-in recipes in process")
def test_framing_v1_stays_loadable_and_v2_proposes_runs_with_bindings():
    from baton.frame import FRAME_RECIPE, proposing_step
    from baton.project import builtin_recipe

    v1, v2 = builtin_recipe("baton-frame@1"), builtin_recipe("baton-frame@2")
    assert FRAME_RECIPE == "baton-frame@2" and not v1.recipe.steps[0].proposes_runs and v2.recipe.steps[0].proposes_runs
    assert proposing_step(v1) == proposing_step(v2) == "frame"
    assert "bind" in v2.schemas["schemas/frame.json"]["properties"]["parts"]["items"]["properties"]
    assert "bind" not in v1.schemas["schemas/frame.json"]["properties"]["parts"]["items"]["properties"]


# -- Slice 3: project.summary -----------------------------------------------------------------------------------------


def _reviewer(root: Path) -> Path:
    look = {"id": "look", "output_schema": "schemas/out.json", "inputs": [{"name": "state", "from": "project.summary", "required": True}]}
    return make_recipe(root, [look], schemas={"out.json": {"type": "object"}}, id="reviewer",
                       run_inputs={"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}})


@pytest.mark.slow
def test_project_summary_reports_the_projects_state_from_the_records_without_contents(tmp_path):
    from baton import summary

    cli, project = _documents_project(tmp_path)
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"] = [_part("good", {"site_survey": ["site/survey.md"]}), _part("later", None), _part("bad", {"budget": ["site/survey.md"]})]
    manual(cli, project, fr, "frame", out)
    sel = cli.run("decide", fr, "frame", "select", "--items", "good,bad", "--note", "Good and bad. Yes.")
    good = sel["runs"][0]["run"]
    (project / "site" / "survey.md").write_text("# Survey\n\nFlat ground, power moved to the gate.\n", encoding="utf-8")
    git(project, "commit", "-qam", "Survey revised")
    cli.run("vendor", str(_reviewer(tmp_path / "reviewer")))
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Vendor reviewer")
    rv = cli.run("start", "reviewer", "--inputs", json.dumps({"title": "Where are we?"}), expect=None)["run_id"]
    d = cli.run("dispatch", rv, "look", "--worker", "owner")
    blob = (packet_dir(project, rv, "look", d["attempt"]) / "inputs" / "state.json").read_bytes()
    s = json.loads(blob)

    assert set(s) == {"runs", "documents", "bindings", "upstream_changes", "process_plans", "policy"}
    runs = {r["run"]: r for r in s["runs"]}
    assert rv not in runs and set(runs) == {fr, good}
    assert runs[fr]["recipe"] == "baton-frame@2" and runs[fr]["state"] == "completed" and "steps" not in runs[fr]
    g = runs[good]
    assert (g["recipe"], g["title"], g["state"]) == ("site-build@1", "Good", "active")
    assert g["proposed_by"] == {"run": fr, "part": "good"} and g["steps"] == {"build": "ready"} and g["waiting_on_owner"] == []
    assert [x["path"] for x in s["documents"]] == [sel["plan"], "site/a.jpg", "site/b.jpg", "site/old.md", "site/survey.md"]
    by = {x["path"]: x for x in s["documents"]}
    assert by[sel["plan"]]["kind"] == "deliverable" and by[sel["plan"]]["source"]["run"] == fr  # the plan is a deliverable
    assert by["site/old.md"]["state"] == "deleted" and by["site/survey.md"]["state"] == "edited" and by["site/a.jpg"]["kind"] == "attested"
    assert "note" not in json.dumps(s["documents"])  # the owner's words stay in the record
    assert s["bindings"] == [{"run": good, "role": "site_survey", "documents": [{"path": "site/survey.md", "version": 1}]}]
    assert [(c["run"], c["path"], c["change"]) for c in s["upstream_changes"]] == [(good, "site/survey.md", "edited")]
    (plan,) = s["process_plans"]
    assert plan["run"] == fr and plan["path"] == sel["plan"]
    assert [(p["id"], p["status"]) for p in plan["parts"]] == [("good", "started"), ("later", "later"), ("bad", "gap")]
    assert plan["parts"][0]["run"] == good and "budget" in plan["parts"][2]["reason"]
    started = _events(project, rv)[0]["data"]
    assert s["policy"]["sha256"] == started["policy_sha256"] and set(s["policy"]) >= {"floors", "governing", "permissions"}
    for text in ("Flat ground", "power moved", "Old survey", "photo a"):  # metadata only: no document's contents
        assert text.encode() not in blob

    # Deterministic: the same records give the same blob.
    from baton.packet import _json_bytes
    from baton.store import Store

    again = summary.build(Store(project), exclude_run=rv, policy_sha256=started["policy_sha256"])
    assert _json_bytes(again) == blob


@pytest.mark.not_slow("loads a recipe in process")
def test_summary_is_a_reserved_role_name_and_a_reference_steps_may_take(tmp_path):
    from baton.recipe import load_recipe

    assert load_recipe(_reviewer(tmp_path / "ok")).recipe.steps[0].inputs[0].from_ == "project.summary"
    role = {"role": "summary", "description": "A summary of something"}
    use = {"id": "look", "output_schema": "schemas/out.json"}
    root = make_recipe(tmp_path / "bad", [use], schemas={"out.json": {"type": "object"}}, project_inputs=[role])
    assert _codes(root) == {"project_inputs.reserved_role"}


# -- Slice 4: the project-review recipe -------------------------------------------------------------------------------

DOC_TARGET = "{{ paths.docs }}/{{ run.slug }}-survey.md"


def _surveyor(root: Path) -> Path:
    """One step that publishes a survey (a project document once accepted)."""
    draft = {"id": "survey", "output_schema": "schemas/out.json",
             "artifacts": [{"name": "report", "required": True, "media_type": "text/markdown", "publish": {"to": DOC_TARGET}}]}
    return make_recipe(root, [draft], schemas={"out.json": {"type": "object"}}, id="site-survey",
                       run_inputs={"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}})


def _review_project(tmp_path: Path):
    cli, project = fresh(tmp_path)
    for r in (_surveyor(tmp_path / "site-survey"), _builder(tmp_path / "site-build")):
        cli.run("vendor", str(r))
    py = project / ".baton" / "project.yaml"
    cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
    cfg.setdefault("paths", {})["docs"] = "docs/out"
    py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Recipes")
    return cli, project


@pytest.mark.slow
def test_a_review_after_framing_recommends_the_next_two_with_a_binding_and_an_order(tmp_path):
    cli, project = _review_project(tmp_path)
    # Framing: three parts; the owner starts the survey only.
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"] = [
        {"id": "survey", "label": "Surveying the site", "description": "What the ground and services are like.", "kind": "project",
         "proposal": {"recipe": "site-survey", "inputs": {"title": "Survey"}}, "reasons": ["Everything else depends on the site"]},
        _part("build", None),
        {"id": "signs", "label": "Signs", "description": "Signs for the stand.", "kind": "project",
         "proposal": {"fit_check": {"idea": "Signs for a lemonade stand."}}, "reasons": ["Unclear"]},
    ]
    manual(cli, project, fr, "frame", out)
    sel = cli.run("decide", fr, "frame", "select", "--items", "survey", "--note", "Just the survey for now. Yes.")
    sv = sel["runs"][0]["run"]
    framing_plan = (project / sel["plan"]).read_text(encoding="utf-8")
    # The survey is done: its report is published and becomes a project document.
    d = cli.run("dispatch", sv, "survey", "--worker", "owner")
    pdir = packet_dir(project, sv, "survey", d["attempt"])
    (pdir.parent / "result" / "artifacts").mkdir(parents=True, exist_ok=True)
    (pdir.parent / "result" / "artifacts" / "report.md").write_text("# Survey\n\nFlat ground.\n", encoding="utf-8")
    write_result(pdir, {}, artifacts=[{"name": "report", "path": "artifacts/report.md"}])
    cli("submit", sv, "survey", expect=None)
    assert status(cli, sv)["state"] == "completed"
    (doc,) = [x["path"] for x in cli.run("documents")["documents"] if x["path"].endswith("-survey.md")]

    # The owner asks what's next; the Director offers a review and, on yes, vendors it by name and starts it.
    assert cli.run("vendor", "project-review", expect=1)["error"] == "vendor.note"
    words = "What should we do next? Yes, look it over."
    v = cli.run("vendor", "project-review", "--note", words)
    assert v["recipe"] == "project-review@1" and v["changed"] and v["decision_id"]
    plog = [json.loads(x) for x in (project / ".baton" / "project" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["type"] == "human_decision" and e["data"].get("kind") == "vendor" and e["data"]["note"] == words for e in plog)
    assert git(project, "status", "--porcelain", "--", ".baton/recipes", ".baton/baton.lock").strip() == ""
    rv = cli.run("start", "project-review", "--inputs", json.dumps({"title": "Project review", "words": words}), expect=None)["run_id"]
    d = cli.run("dispatch", rv, "recommend", "--worker", "owner")
    inputs = packet_dir(project, rv, "recommend", d["attempt"]) / "inputs"
    state = json.loads((inputs / "state.json").read_text(encoding="utf-8"))
    (plan,) = state["process_plans"]
    assert [(p["id"], p["status"]) for p in plan["parts"]] == [("survey", "started"), ("build", "later"), ("signs", "later")]
    assert {r["run"]: r["state"] for r in state["runs"]}[sv] == "completed" and doc in [x["path"] for x in state["documents"]]
    assert json.loads((inputs / "words.json").read_text(encoding="utf-8")) == words
    assert "site-build" in [r["id"] for r in json.loads((inputs / "recipes.json").read_text(encoding="utf-8"))]

    recs = {"goal": "The site is surveyed; building comes next, then signs.", "parts": [
        {**_part("build", {"site_survey": [doc]}), "label": "Building the stand", "position": {"rank": 1, "reason": "The survey is done"},
         "reasons": ["The survey is settled", "It builds on the survey"]},
        {"id": "signs", "label": "Signs", "description": "Signs for the stand.", "proposal": {"fit_check": {"idea": "Signs for a lemonade stand."}},
         "reasons": ["Customers need to find it"], "position": {"rank": 2, "reason": "Signs go on the stand"},
         "waits_on": [{"on": "build", "reason": "the stand must exist first"}]},
    ]}
    write_result(packet_dir(project, rv, "recommend", d["attempt"]), recs)
    assert cli("submit", rv, "recommend", expect=None).payload["outcome"] == "needs_human"
    (pd,) = status(cli, rv)["pending_decisions"]
    nxt = {p["part"]: p["next"] for p in next(o for o in pd["options"] if o["decision"] == "select")["next"]}
    assert nxt["build"] == f"starts site-build, building on {doc}"
    rsel = cli.run("decide", rv, "recommend", "select", "--items", "build", "--note", "Build the stand on the survey. Yes.")
    assert [(r["part"], r["recipe"], r["bound"]) for r in rsel["runs"]] == [("build", "site-build@1", [{"role": "site_survey", "paths": [doc]}])]
    assert rsel["state"] == "completed" and rsel["plan"] == f"docs/project-review-{rv}-process-plan.md"
    text = (project / rsel["plan"]).read_text(encoding="utf-8")
    assert "The order suggested is advice, with its reasons." in text
    build = text[text.index("## Building the stand"):text.index("## Signs")]
    assert "- **Why:** The survey is settled. It builds on the survey." in build and "- **Suggested order:** 1: The survey is done" in build
    assert f"started (site-build, run {rsel['runs'][0]['run']})" in build and f"`{doc}` (site_survey)" in build
    signs = text[text.index("## Signs"):]
    assert "- **Waits on:** Building the stand: the stand must exist first" in signs and "**Status:** for later" in signs
    # Framing's plan never shows an order or reasons (Decision 0069).
    assert "Suggested order" not in framing_plan and "Waits on" not in framing_plan and "**Why:**" not in framing_plan
    assert git(project, "status", "--porcelain", "--", f".baton/runs/{rv}", "docs").strip() == ""
    assert cli.run("check")["ok"]


@pytest.mark.not_slow("loads shipped recipes in process")
def test_project_review_ships_in_the_catalog_with_optional_roles():
    from baton.frame import proposing_step
    from baton.project import catalog

    rv = catalog()["project-review"]
    assert proposing_step(rv) == "recommend" and rv.recipe.steps[0].output_schema == "baton:proposals"
    roles = {r.role: r for r in rv.recipe.project_inputs}
    assert set(roles) == {"project_plan", "decisions"} and not roles["project_plan"].required
    assert roles["decisions"].many and not roles["decisions"].required
    assert {i.from_ for i in rv.recipe.steps[0].inputs} >= {"project.summary", "catalog.summaries", "run.inputs.words"}
