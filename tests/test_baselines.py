"""Baselines and detectors (change 2026-11-self-improvement, slice 4; D5; §5.1, §12.4; Decisions 0185 item 3, 0187 item 2, 0188 item 8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import baselines, engine, sme
from baton.engine import Api
from baton.project import init
from baton.recipe import load_recipe
from baton.store import Store
from projectkit import Cli, git, make_git_project, make_home, packet_dir
from projectkit import write_result as pk_write_result
from baton.models import WorkerProfile
from runkit import WRITER, Clock, make_recipe, start, write_result

REPO_WRITER = WorkerProfile(adapter="manual", vendor="acme", capabilities=["structured_output", "repo_workspace", "file_write", "workspace_read"], tier="strong")
X_SCHEMA = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
OBJ = {"type": "object"}
PROFILES = """\
alice:
  adapter: manual
  vendor: acme
  capabilities: [structured_output]
"""


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def cases(store_or_project, kind: str) -> list[dict]:
    log = store_or_project.project_log()
    return [e.data for e in log.events() if e.type == "process_feedback" and e.data.get("kind") == kind]


def two_steps(root: Path) -> Path:
    return make_recipe(root, [{"id": "a", "output_schema": "schemas/out.json"},
                              {"id": "b", "depends_on": ["a"], "output_schema": "schemas/out.json"}],
                       schemas={"out.json": X_SCHEMA}, defaults={"max_attempts": 5})


def attempt(ctx, step: str, output, **kw):
    p = engine.begin_attempt(ctx, step, "owner", WRITER)
    write_result(p, output, **kw)
    return engine.submit(ctx, step)


# ---------------------------------------------------------------------------
# Measures and baselines.json
# ---------------------------------------------------------------------------


@pytest.mark.not_slow("in-process engine calls, under 1 s")
def test_measures_and_medians_come_from_completed_runs_only(tmp_path) -> None:
    recipe = two_steps(tmp_path / "r")
    runs = []
    for i, extra in enumerate((0, 1, 2, 0)):
        with Store(tmp_path / f"p{i}", clock=Clock()) as s:
            ctx = start(s, recipe, {})
            failures = ({}, {"x": 1})[:extra]
            for bad in failures:
                attempt(ctx, "a", bad)
            attempt(ctx, "a", {"x": "ok"})
            if i < 3:  # the fourth run never completes
                attempt(ctx, "b", {"x": "ok"})
            runs.append((s.run(ctx.run_id).events(), s.run_dir(ctx.run_id)))
    m = baselines.run_measures(*runs[2])
    assert m["a"]["attempts"] == 3 and m["a"]["iterations"] == 1 and m["a"]["owner_stops"] == 0 and "cost_usd" not in m["a"]
    doc = baselines.derive(runs, ["p"], "2026-11-23")
    assert doc["format"] == "baton-baselines/1" and doc["derived"] == {"from": ["p"], "runs": 3, "recipe_versions": [1], "date": "2026-11-23"}
    assert doc["steps"]["a"]["attempts"] == {"median": 2, "samples": 3}
    assert doc["steps"]["b"]["attempts"] == {"median": 1, "samples": 3}
    assert baselines.check(doc) == []
    assert baselines.check({"format": "baton-baselines/1", "steps": {"a": {"speed": {"median": 1, "samples": 1}}}})


@pytest.mark.not_slow("reads and hashes a small recipe")
def test_baselines_json_is_part_of_the_package_and_its_hash(tmp_path) -> None:
    recipe = two_steps(tmp_path / "r")
    before = load_recipe(recipe).sha256
    (recipe / "baselines.json").write_text(json.dumps({"format": "baton-baselines/1", "steps": {}}), encoding="utf-8")
    assert load_recipe(recipe).sha256 != before
    assert baselines.load(recipe) == {"format": "baton-baselines/1", "steps": {}}
    (recipe / "baselines.json").write_text("{}", encoding="utf-8")
    with pytest.raises(baselines.BaselineError):
        baselines.load(recipe)


@pytest.mark.not_slow("the CLI in process, under 1 s")
def test_recipe_baselines_writes_the_medians_from_the_projects_named(tmp_path) -> None:
    recipe = two_steps(tmp_path / "r")
    proj = tmp_path / "proj"
    with Store(proj, clock=Clock()) as s:
        ctx = start(s, recipe, {})
        attempt(ctx, "a", {"x": "ok"})
        attempt(ctx, "b", {"x": "ok"})
    cli = Cli(proj, make_home(tmp_path / "home", PROFILES))
    out = cli.run("recipe", "baselines", str(recipe), "--project", str(proj), "--project", str(proj))
    assert out["runs"] == 2 and out["steps"] == 2 and out["from"] == ["proj", "proj"]
    out = cli.run("recipe", "baselines", str(recipe))  # this project
    assert out["runs"] == 1 and out["from"] == ["proj"]
    doc = json.loads((recipe / "baselines.json").read_text(encoding="utf-8"))
    assert doc["steps"]["a"]["attempts"] == {"median": 1, "samples": 1}


# ---------------------------------------------------------------------------
# Off baseline, at run completion
# ---------------------------------------------------------------------------


def _api(tmp_path: Path, samples: int, prefs: str | None = None) -> tuple[Api, Path, str]:
    recipe = two_steps(tmp_path / "r")
    (recipe / "baselines.json").write_text(json.dumps({"format": "baton-baselines/1", "steps": {
        "a": {"attempts": {"median": 1, "samples": samples}, "owner_stops": {"median": 0, "samples": samples}},
        "b": {"attempts": {"median": 1, "samples": samples}}}}), encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    home = make_home(tmp_path / "home", PROFILES)
    if prefs:
        (home / "preferences.yaml").write_text(prefs, encoding="utf-8")
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    return api, root, api.start("toy", {"title": "Baselines"})["run_id"]


def _do(api: Api, root: Path, run: str, step: str, output) -> dict:
    d = api.dispatch(run, step, "alice")
    pk_write_result(packet_dir(root, run, step, d["attempt"]), output)
    return api.submit(run, step)


@pytest.mark.slow  # a project through the Api, several calls
def test_a_step_well_off_its_baseline_opens_one_case_per_measure_with_its_guards(tmp_path) -> None:
    api, root, run = _api(tmp_path, samples=3)
    for bad in ({}, {"x": 1}):
        assert _do(api, root, run, "a", bad)["outcome"] == "retry"
    _do(api, root, run, "a", {"x": "ok"})
    assert not cases(api.project.store, "off_baseline")  # not before the run completes
    assert _do(api, root, run, "b", {"x": "ok"})["run_completed"]
    [c] = cases(api.project.store, "off_baseline")
    assert c["source"] == "detector:off_baseline" and c["run"] == run and c["step_path"] == "a" and c["qualified"] == "toy@1/a"
    assert (c["measure"], c["value"], c["median"], c["samples"], c["factor"]) == ("attempts", 3, 1.0, 3, 2.0)
    assert c["guards"] == {"first_try": False, "rejections": 2, "owner_rejections": 0, "defects_late": 0}
    assert c["text"] == "attempts 3 against a median of 1 (3 samples, factor 2)"
    assert sme.stats(api.project.store)["cases"]["toy@1/a"]["kinds"] == {"off_baseline": 1}


@pytest.mark.slow  # a project through the Api
def test_too_few_samples_or_within_the_factor_opens_nothing(tmp_path) -> None:
    api, root, run = _api(tmp_path / "few", samples=2)
    for bad in ({}, {"x": 1}):
        _do(api, root, run, "a", bad)
    _do(api, root, run, "a", {"x": "ok"})
    _do(api, root, run, "b", {"x": "ok"})
    assert not cases(api.project.store, "off_baseline")
    # The machine's factor: three attempts are within 4 times a median of 1.
    api, root, run = _api(tmp_path / "factor", samples=3, prefs="self_improvement:\n  factor: 4\n")
    for bad in ({}, {"x": 1}):
        _do(api, root, run, "a", bad)
    _do(api, root, run, "a", {"x": "ok"})
    _do(api, root, run, "b", {"x": "ok"})
    assert not cases(api.project.store, "off_baseline")


# ---------------------------------------------------------------------------
# Re-asked, at intake
# ---------------------------------------------------------------------------

QUESTIONS = [{"id": "venue", "ask": "Indoors or outdoors?", "why": "Sets the venue list"}]


@pytest.mark.not_slow("in-process engine calls, under 1 s")
def test_a_question_asked_again_after_its_answer_opens_a_reasked_case(store, tmp_path) -> None:
    ctx = start(store, make_recipe(tmp_path / "r", [{"id": "work", "output_schema": "schemas/out.json"}],
                                   schemas={"out.json": OBJ}, defaults={"max_attempts": 5}), {})
    assert attempt(ctx, "work", {}, status="blocked", questions_for_human=QUESTIONS).outcome == "escalated"
    assert not cases(store, "reasked")
    engine.decide(ctx, "work", "retry", "Outdoors.", answers=[{"id": "venue", "answer": "outdoors", "owner_words": "Outdoors."}])
    answer = [e for e in ctx.log.events() if e.type == "human_decision"][-1].seq
    attempt(ctx, "work", {}, status="blocked", questions_for_human=[*QUESTIONS, {"id": "date", "ask": "When?", "why": "x"}])
    [c] = cases(store, "reasked")
    asked = ctx.record().last("step_escalated", "work").seq
    assert c["source"] == "detector:reasked" and c["question"] == "venue" and c["attempt"] == 2 and c["qualified"] == "toy@1/work"
    assert c["evidence"] == [str(answer), str(asked)] and "Indoors or outdoors?" in c["text"]
    # A completed result asking to confirm the same guess (0184) is re-asked too.
    engine.decide(ctx, "work", "retry", "Outdoors, as I said.", answers=[{"id": "venue", "answer": "outdoors", "owner_words": "Outdoors, as I said."},
                                                                {"id": "date", "answer": "June", "owner_words": "June."}])
    attempt(ctx, "work", {}, questions_for_human=QUESTIONS)
    assert len(cases(store, "reasked")) == 2


# ---------------------------------------------------------------------------
# Defects found late (Decision 0188, item 8)
# ---------------------------------------------------------------------------

NO_FINDINGS = {"findings": [], "coverage": {"complete": True}}


def _finding(fid: str, location: str) -> dict:
    return {"id": fid, "severity": "low", "location": location, "title": "wrong"}


@pytest.mark.not_slow("in-process engine calls, under 1 s")
def test_a_finding_in_a_reviewed_earlier_steps_file_is_a_late_defect_against_it(store, tmp_path) -> None:
    gate = [{"type": "findings", "block_on": ["high"]}]
    recipe = make_recipe(tmp_path / "r", [
        {"id": "design", "output_schema": "baton:findings", "gates": gate, "artifacts": [{"name": "doc", "required": True}]},
        {"id": "notes", "output_schema": "schemas/out.json", "artifacts": [{"name": "notes", "required": True}]},
        {"id": "check", "depends_on": ["design", "notes"], "output_schema": "baton:findings", "gates": gate},
    ], schemas={"out.json": OBJ})
    ctx = start(store, recipe, {})
    assert attempt(ctx, "design", NO_FINDINGS, artifacts={"doc": ("design.md", b"# Design\n")}).outcome == "passed"
    assert attempt(ctx, "notes", {}, artifacts={"notes": ("notes.md", b"n\n")}).outcome == "passed"
    out = {"findings": [_finding("F1", "design.md:3"), _finding("F2", "notes.md:1"), _finding("F3", "elsewhere.py:9"),
                        _finding("F4", f".baton/runs/{ctx.run_id}/steps/design/attempt-1/result/artifacts/design.md:12")],
           "coverage": {"complete": True}}
    assert attempt(ctx, "check", out).outcome == "passed"
    # F1 and F4 name design's file, which passed its own findings gate; notes has no review; elsewhere.py is nobody's.
    assert baselines.late_defects(ctx.log.events()) == {"design": 2}
    st = sme.stats(store)["steps"]
    assert st["toy@1/design"]["outcome"]["defects_late"] == 2
    assert st["toy@1/notes"]["outcome"]["defects_late"] == 0


@pytest.mark.slow  # runs git
def test_a_write_steps_pass_records_the_files_it_committed(tmp_path) -> None:
    root = make_git_project(tmp_path / "project")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    recipe = make_recipe(tmp_path / "r", [{"id": "implement", "workspace": "write", "output_schema": "schemas/out.json",
                                           "requires": {"capabilities": ["structured_output", "repo_workspace"]}}],
                         schemas={"out.json": OBJ})
    with Store(root, clock=Clock()) as s:
        ctx = start(s, recipe, {})
        p = engine.begin_attempt(ctx, "implement", "w", REPO_WRITER)
        assert ctx.record().last("dispatched", "implement").data["head"]
        (root / "src").mkdir()
        (root / "src" / "auth.py").write_text("def ok(): pass\n", encoding="utf-8")
        git(root, "add", "src/auth.py")
        git(root, "commit", "-q", "-m", "auth")
        write_result(p, {})
        assert engine.submit(ctx, "implement").outcome == "passed"
        assert ctx.record().last("step_passed", "implement").data["changed_files"] == ["src/auth.py"]
