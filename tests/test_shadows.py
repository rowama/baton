"""Shadow attempts on strong steps (§8.7; Decisions 0176 items 4 and 6, 0179 items 4-6, 0182 item 1; change 2026-11-model-assessment, slice 4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import assessment, engine, prefs, supervisor
from baton.engine import Api, scratch_copy
from baton.models import AssessmentSettings, Step
from baton.packet import task_digest
from baton.project import init
from baton.supervisor import ChildResult

from projectkit import git, make_git_project, make_home
from runkit import Clock, make_recipe
from test_trials import CHEAP, DEAR, MID, api_profile

ON = AssessmentSettings(shadows=True)


def step(**kw) -> Step:
    base = {"id": "think", "requires": {"capabilities": ["structured_output"], "tier": "strong"}, "prompt": "p.md",
            "output_schema": "schemas/out.json", "effect": "none", "repeatable": True, "gates": [{"type": "schema"}]}
    return Step.model_validate({**base, **kw})


STRONG = {n: p.model_copy(update={"tier": "strong"}) for n, p in (("cheap", CHEAP), ("dear", DEAR), ("mid", MID))}


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def test_only_repeatable_strong_steps_that_do_not_write_are_shadowed():
    assert assessment.shadow_problems(step(), "think") == []
    assert assessment.shadow_problems(step(workspace="read"), "think") == []
    assert "it writes to the workspace" in assessment.shadow_problems(step(workspace="write", repeatable=False, effect="reversible"), "think")
    assert any("repeatable" in r for r in assessment.shadow_problems(step(repeatable=False), "think"))
    assert any("strong" in r for r in assessment.shadow_problems(step(requires={"capabilities": ["structured_output"], "tier": "standard"}), "think"))
    assert any("schema" in r for r in assessment.shadow_problems(step(gates=[]), "think"))
    assert "a review" in assessment.shadow_problems(step(), "think~review")


def choose(primary="dear", *, settings=ON, models=None, available=0.0, already=False, profiles=None):
    profiles = profiles or STRONG
    return assessment.shadow_candidate(step(), "think", primary, sorted(profiles), profiles, settings, models or {},
                                       available_usd=available, already=already)


def test_one_candidate_free_first_within_the_budget_and_off_by_default(tmp_path):
    assert choose()[0] == "cheap"
    assert choose(settings=AssessmentSettings())[0] is None
    assert choose(already=True)[0] is None
    assert choose("cheap")[0] is None  # $0: only free models, and the primary is the only free one
    assert choose("cheap", available=10.0)[0] == "mid"
    assert choose(profiles={"dear": STRONG["dear"], "alias": api_profile(None, tier="strong")})[0] is None
    win = AssessmentSettings(shadows=True)
    for i in range(5):
        assessment.record_outcome(tmp_path, "cheap", STRONG["cheap"], {"id": f"r:s:{i}:shadow", "kind": "shadow", "tier": "strong", "passed": True},
                                  settings=win)
    assert choose(models=assessment.load_models(tmp_path), available=10.0)[0] == "mid"  # proven at strong: no longer shadows


@pytest.mark.parametrize("primary_failed", [False, True])
def test_the_grade_is_the_shadows_own_with_a_shared_failure_forgiven(primary_failed):
    assert assessment.shadow_outcome({"passed": True}, primary_failed) == (True, True)
    assert assessment.shadow_outcome({"passed": False}, primary_failed) == (False, not primary_failed)
    assert assessment.shadow_outcome({"passed": False, "counted": False}, primary_failed) == (False, False)


def test_a_scratch_copy_leaves_out_git_and_baton_runs(tmp_path):
    root = tmp_path / "p"
    (root / ".git").mkdir(parents=True)
    (root / ".baton" / "runs").mkdir(parents=True)
    (root / ".baton" / "project").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "a.txt").write_text("a")
    scratch_copy(root, tmp_path / "copy")
    assert (tmp_path / "copy" / "src" / "a.txt").read_text() == "a"
    assert not (tmp_path / "copy" / ".git").exists() and not (tmp_path / "copy" / ".baton" / "runs").exists()
    assert (tmp_path / "copy" / ".baton" / "project").is_dir()


# ---------------------------------------------------------------------------
# The engine (the supervisor's process is not started; its end is played)
# ---------------------------------------------------------------------------


PROFILES = """\
cheap:
  adapter: litellm_api
  creator: acme
  model_id: acme/cheap
  provider: openrouter
  model: openrouter/acme/cheap
  capabilities: [structured_output]
  tier: strong
  context_tokens: 100000
  price: {free: true}
  auth: {mode: api_key, env: {OPENROUTER_API_KEY: "secret:or"}}
dear:
  adapter: manual
  creator: human
  person: expert
  capabilities: [structured_output]
  tier: strong
"""


@pytest.fixture
def shadowed(tmp_path, monkeypatch):
    """A strong, repeatable step with a script gate; the primary a person (submits by hand), the candidate a free API model."""
    recipe = make_recipe(
        tmp_path / "toy",
        [{"id": "think", "requires": {"capabilities": ["structured_output"], "tier": "strong"}, "output_schema": "schemas/out.json",
          "effect": "none", "repeatable": True,
          "gates": [{"type": "schema"}, {"type": "script", "run": "touch gate-ran && test -f gate-pass"}]}],
        schemas={"out.json": {"type": "object", "required": ["answer"]}}, defaults={"max_attempts": 3},
    )
    root = make_git_project(tmp_path / "proj")
    init(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    home = make_home(tmp_path / "home", PROFILES)
    (home / "secrets").mkdir(exist_ok=True)
    monkeypatch.setenv("OR", "test-key")
    prefs.update_assessment(home, shadows=True)
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "vendor")
    run = api.start("toy", {"title": "Shadow"})["run_id"]
    spawned: list[dict] = []
    monkeypatch.setattr(supervisor, "spawn", lambda spec, log: spawned.append(spec) or object())
    monkeypatch.setattr(supervisor, "await_start", lambda baton, did, proc: {"supervisor_pid": 1})
    monkeypatch.setattr("baton.profiles.build_env", _fake_env)
    return api, run, spawned


class _Env:
    resolved = None
    env: dict = {}
    secrets: list = []

    def describe(self):
        return {}


def _fake_env(*_a, **_k):
    return _Env()


def primary_attempt(api: Api, run: str):
    out = api.dispatch(run, "think", "dear")
    return out


def finish_shadow(api: Api, spec: dict, output, *, timed_out=False):
    sdir = Path(spec["shadow"]["dir"])
    if output is not None and not timed_out:
        packet = json.loads((sdir / "packet" / "manifest.json").read_text())
        (sdir / "result" / "result.json").write_text(json.dumps({
            "protocol": "baton-packet/1", "packet_sha256": packet["packet_sha256"], "status": "completed", "output": output,
            "artifacts": [], "notes": "", "questions_for_human": [], "process_feedback": []}))
    return api.shadow_complete(spec, ChildResult(0, 1.0, timed_out, sdir / "log", b""))


def submit_primary(api: Api, run: str, output, *, gate: bool):
    root = api.project.root
    (root / "gate-pass").unlink(missing_ok=True)
    if gate:
        (root / "gate-pass").write_text("ok")
    ctx = api._ctx(run)
    n = ctx.log.state().step("think").attempt
    pdir = ctx.attempt_dir("think", n) / "packet"
    manifest = json.loads((pdir / "manifest.json").read_text())
    (pdir.parent / "result" / "result.json").write_text(json.dumps({
        "protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": output,
        "artifacts": [], "notes": "", "questions_for_human": [], "process_feedback": []}))
    return api.submit(run, "think")


def shadow_record(api: Api) -> list[dict]:
    rec = assessment.load_models(api.project.home).get(assessment.route_key(api._current_profiles()["cheap"]))
    return [o for o in (rec or {}).get("outcomes", []) if o["kind"] == "shadow"]


@pytest.mark.slow
def test_a_shadow_gets_the_same_task_under_its_own_identity_and_is_never_the_steps_result(shadowed):
    api, run, spawned = shadowed
    out = primary_attempt(api, run)
    assert out["shadow"]["candidate"] == "cheap" and len(spawned) == 1
    spec = spawned[0]
    assert spec["worker"] == "cheap" and spec["dispatch_id"].startswith("s_") and spec["attempt"] == 1
    ctx = api._ctx(run)
    disp = next(e.data for e in ctx.log.events() if e.type == "shadow_dispatched")
    assert disp["profile"] == "cheap" and disp["model_id"] == "acme/cheap"  # its own identity (0075)
    assert disp["task_sha256"] == disp["primary_task_sha256"]  # the same task
    primary = next(e.data for e in ctx.log.events() if e.type == "packet_built")
    assert disp["packet_sha256"] != primary["packet_sha256"]  # a packet of its own
    (api.project.root / "gate-pass").write_text("ok")
    finish_shadow(api, spec, {"answer": 42})
    ctx = api._ctx(run)
    assert ctx.log.state().step("think").state == "running"  # the shadow's result changed nothing about the step
    assert not any(e.type in ("result_submitted", "step_passed") for e in ctx.log.events())
    assert not Path(spec["shadow"]["dir"]).exists()  # its scratch folder is gone
    assert shadow_record(api) == []  # not graded until the primary ends
    res = submit_primary(api, run, {"answer": 1}, gate=True)
    assert res["outcome"] == "passed"
    (o,) = shadow_record(api)
    assert o["passed"] is True and o["counted"] is True and o["tier"] == "strong"


@pytest.mark.slow
@pytest.mark.parametrize("shadow_first", [True, False], ids=["shadow-first", "primary-first"])
def test_the_order_of_ending_does_not_change_the_grade_and_a_shared_failure_is_forgiven(shadowed, shadow_first):
    api, run, spawned = shadowed
    primary_attempt(api, run)
    if shadow_first:
        finish_shadow(api, spawned[0], {"wrong": True})
        submit_primary(api, run, {"answer": 1}, gate=False)  # the primary fails its script gate
    else:
        submit_primary(api, run, {"answer": 1}, gate=False)
        finish_shadow(api, spawned[0], {"wrong": True})
    (o,) = shadow_record(api)
    assert o["passed"] is False and o["counted"] is False


@pytest.mark.slow
def test_a_shadow_that_fails_where_the_primary_passed_counts_against_it(shadowed):
    api, run, spawned = shadowed
    primary_attempt(api, run)
    (api.project.root / "gate-pass").write_text("ok")
    data = finish_shadow(api, spawned[0], {"wrong": True})
    assert data["gates"] == [{"gate": "schema", "passed": False}]  # graded by the schema first
    submit_primary(api, run, {"answer": 1}, gate=True)
    (o,) = shadow_record(api)
    assert o["passed"] is False and o["counted"] is True


@pytest.mark.slow
def test_gates_run_in_a_scratch_copy_and_a_timeout_is_no_evidence(shadowed):
    api, run, spawned = shadowed
    root = api.project.root
    (root / "gate-pass").write_text("ok")
    primary_attempt(api, run)
    data = finish_shadow(api, spawned[0], {"answer": 3})
    assert data["passed"] is True and [g["gate"] for g in data["gates"]] == ["schema", 1]
    assert not (root / "gate-ran").exists()  # the gate's command touched only the scratch copy
    assert api.shadow_complete(spawned[0], ChildResult(0, 1.0, False, Path("log"), b"")) is None  # recorded once


@pytest.mark.slow
def test_a_shadow_that_runs_out_of_time_leaves_the_primary_intact(shadowed):
    api, run, spawned = shadowed
    primary_attempt(api, run)
    data = finish_shadow(api, spawned[0], None, timed_out=True)
    assert data["counted"] is False and data["passed"] is False
    res = submit_primary(api, run, {"answer": 1}, gate=True)
    assert res["outcome"] == "passed"
    (o,) = shadow_record(api)
    assert o["counted"] is False
    assert api._ctx(run).log.state().step("think").state == "passed"


@pytest.mark.slow
def test_a_step_is_shadowed_once_in_a_run_and_never_with_shadows_off(shadowed):
    api, run, spawned = shadowed
    primary_attempt(api, run)
    submit_primary(api, run, {"answer": 1}, gate=False)  # retry
    out = primary_attempt(api, run)
    assert "shadow" not in out and len(spawned) == 1


@pytest.mark.slow
def test_with_shadows_off_nothing_is_dispatched_beside_the_primary(shadowed):
    api, run, spawned = shadowed
    prefs.update_assessment(api.project.home, shadows=False)
    out = primary_attempt(api, run)
    assert "shadow" not in out and spawned == []
    assert not any(e.type.startswith("shadow") for e in api._ctx(run).log.events())


def test_the_task_digest_ignores_who_does_it():
    a = {"run_id": "r", "step_path": "s", "attempt": 1, "inputs": [{"name": "x", "sha256": "1", "path": "inputs/x"}],
         "worker_profile": "a", "worker_profile_sha256": "aa", "tools": ["read_file"]}
    b = {**a, "worker_profile": "b", "worker_profile_sha256": "bb", "tools": []}
    assert task_digest(a) == task_digest(b)
    assert task_digest(a) != task_digest({**a, "attempt": 2})
