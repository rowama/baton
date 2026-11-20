"""Trial routing and the track record (§6.4, §8.4; Decisions 0176, 0179, 0182; change 2026-11-model-assessment, slice 3)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from baton import assessment, engine, prefs
from baton.engine import Api
from baton.models import AssessmentSettings, Step, WorkerProfile
from baton.project import init
from baton.routing import eligible_workers
from baton.vocab import DEFAULT, load

from projectkit import git, make_git_project, make_home
from runkit import Clock, make_recipe, write_result

VOCAB = load(DEFAULT)
ON = AssessmentSettings(trials=True)


def api_profile(model_id: str | None, *, price: dict | None = None, tier: str = "standard", caps: list[str] | None = None) -> WorkerProfile:
    return WorkerProfile(adapter="litellm_api", creator="acme", model_id=model_id, provider="openrouter", model=f"openrouter/{model_id or 'auto'}",
                         capabilities=caps or ["structured_output"], tier=tier, context_tokens=100_000,
                         price={"free": True} if price is None else price, auth={"mode": "api_key", "env": {"KEY": "secret:k"}})


CHEAP = api_profile("acme/cheap")
DEAR = api_profile("acme/dear", price={"input": 5, "output": 20})
MID = api_profile("acme/mid", price={"input": 0.1, "output": 0.4})


def outcome(i: int, passed: bool, tier: str = "standard", kind: str = "trial", **kw) -> dict:
    return {"id": f"r:s:{i}:{kind}", "kind": kind, "tier": tier, "passed": passed, **kw}


def step(**kw) -> Step:
    base = {"id": "draft", "requires": {"capabilities": ["structured_output"], "tier": "standard"}, "prompt": "p.md",
            "output_schema": "schemas/out.json", "effect": "reversible",
            "gates": [{"type": "schema"}, {"type": "script", "run": "true"}]}
    return Step.model_validate({**base, **kw})


# ---------------------------------------------------------------------------
# Identity, standing and the thresholds
# ---------------------------------------------------------------------------


def test_evidence_belongs_to_the_model_and_route_and_an_alias_gets_none():
    assert assessment.route_key(CHEAP) != assessment.route_key(api_profile("acme/cheap", price={"input": 1, "output": 1}).model_copy(
        update={"provider": "other"}))
    assert assessment.route_key(api_profile(None)) is None
    assert assessment.route_key(WorkerProfile(adapter="manual", creator="human", person="owner")) is None


def test_proven_after_five_passes_and_put_back_after_two_failures_in_the_last_five(tmp_path):
    for i in range(4):
        assert assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, True), settings=ON) is None
    change = assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(4, True), settings=ON)
    assert change == {"tier": "standard", "before": "candidate", "after": "proven"}
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert assessment.standing(rec, "basic", ON, "standard")["state"] == "candidate"  # per tier of the step
    assert assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(5, False), settings=ON) == \
        {"tier": "standard", "before": "proven", "after": "candidate"}
    change = assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(6, False), settings=ON)
    assert change == {"tier": "standard", "before": "candidate", "after": "put_back"}


def test_the_same_intake_twice_records_once_and_real_steps_do_not_decide_standing(tmp_path):
    assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(1, False), settings=ON)
    assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(1, False), settings=ON)
    for i in range(3):
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(10 + i, False, kind="step"), settings=ON)
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert rec["totals"]["standard"] == {"trial": {"passed": 0, "failed": 1}, "step": {"passed": 0, "failed": 3}}
    assert assessment.standing(rec, "standard", ON, "standard")["state"] == "candidate"


def test_an_uncounted_outcome_is_kept_but_not_evidence(tmp_path):
    assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(1, False, counted=False), settings=ON)
    assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(2, False, counted=False), settings=ON)
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert len(rec["outcomes"]) == 2 and rec["totals"] == {}
    assert assessment.standing(rec, "standard", ON, "standard")["state"] == "candidate"


def test_a_new_rating_or_harness_version_starts_afresh(tmp_path):
    for i in range(2):
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, False), settings=ON, harness_version="1.0")
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert assessment.standing(rec, "standard", ON, "standard")["state"] == "put_back"
    assert assessment.standing(rec, "standard", ON, "strong")["state"] == "candidate"  # re-rated: void at once (0182, item 2)
    assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(9, True), settings=ON, harness_version="2.0")
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert [o["id"] for o in rec["outcomes"]] == ["r:s:9:trial"] and rec["harness_version"] == "2.0"


def test_the_owner_promotes_puts_back_and_clears(tmp_path):
    for i in range(2):
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, False), settings=ON)
    assessment.set_standing(tmp_path, "cheap", CHEAP, "standard", "proven")
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert assessment.standing(rec, "standard", ON, "standard") | {} == {**assessment.standing(rec, "standard", ON, "standard"),
                                                                        "state": "proven", "by": "owner"}
    for i in range(2, 4):  # evidence after the promotion can still put it back
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, False), settings=ON)
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert assessment.standing(rec, "standard", ON, "standard")["state"] == "put_back"
    assessment.set_standing(tmp_path, "cheap", CHEAP, "basic", "put_back")
    rec = assessment.load_models(tmp_path)[assessment.route_key(CHEAP)]
    assert assessment.standing(rec, "basic", ON, "standard") ["by"] == "owner"
    with pytest.raises(assessment.AssessmentError):
        assessment.set_standing(tmp_path, "alias", api_profile(None), "basic", "proven")


def test_the_last_check_records_and_the_evidence_share_one_file(tmp_path):
    from baton import capability_check as cc

    assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(1, True), settings=ON)
    cc._save_record(tmp_path, {"cheap": {"checks": {"set_version": 1}}})
    assert cc.load_record(tmp_path) == {"cheap": {"checks": {"set_version": 1}}}
    assert assessment.route_key(CHEAP) in assessment.load_models(tmp_path)


# ---------------------------------------------------------------------------
# Routing: put back is one tier lower (0182, item 2)
# ---------------------------------------------------------------------------


def test_a_put_back_model_is_treated_as_one_tier_lower_and_proven_changes_nothing():
    profiles = {"cheap": CHEAP, "dear": DEAR}
    st = step()
    got = eligible_workers(st, "draft", profiles, VOCAB, put_back={"cheap": ["standard"]})
    assert got.names() == ["dear"]
    assert "put back at standard" in got.reasons_for("cheap")[0]
    basic = step(requires={"capabilities": ["structured_output"], "tier": "basic"})
    assert eligible_workers(basic, "draft", profiles, VOCAB, put_back={"cheap": ["standard"]}).names() == ["cheap", "dear"]
    assert eligible_workers(st, "draft", profiles, VOCAB).names() == ["cheap", "dear"]


# ---------------------------------------------------------------------------
# Which steps and which candidates (0179, items 1-3)
# ---------------------------------------------------------------------------


def test_only_declared_reversible_steps_with_blocking_gates_below_strong_are_tried():
    assert assessment.trial_problems(step(), "draft") == []
    assert assessment.trial_problems(step(effect="none", gates=[{"type": "schema"}, {"type": "review", "block_on": ["high"], "reviewer_requires": {"capabilities": ["structured_output"]}, "rubric": "prompts/rubric.md"}]),
                                     "draft") == []
    assert "its effect is not declared" in assessment.trial_problems(step(effect=None), "draft")
    assert "its effect is irreversible" in assessment.trial_problems(step(effect="irreversible"), "draft")
    assert "it has no blocking script gate or review" in assessment.trial_problems(step(gates=[{"type": "schema"}]), "draft")
    assert "it has no blocking script gate or review" in assessment.trial_problems(
        step(gates=[{"type": "schema"}, {"type": "script", "run": "true", "advisory": True}]), "draft")
    assert any("strong" in r for r in assessment.trial_problems(step(requires={"capabilities": ["structured_output"], "tier": "strong"}), "draft"))
    assert "a review" in assessment.trial_problems(step(), "draft~review")


def choose(chosen="dear", profiles=None, *, settings=ON, models=None, available=0.0, already=False, st=None):
    profiles = profiles or {"cheap": CHEAP, "dear": DEAR, "mid": MID}
    return assessment.trial_candidate(st or step(), "draft", chosen, sorted(profiles), profiles, settings, models or {},
                                      available_usd=available, already_tried=already)


def test_the_candidate_is_free_or_cheaper_unproven_and_within_the_budget():
    assert choose()[0] == "cheap"  # free first
    assert choose(settings=AssessmentSettings())[0] is None  # off by default (0176, item 6)
    assert choose(already=True)[0] is None  # one trial per step in a run
    assert choose("cheap")[0] is None  # nothing is cheaper than free
    no_free = {"dear": DEAR, "mid": MID}
    assert choose(profiles=no_free)[0] is None  # $0: free models only (0182, item 4)
    assert choose(profiles=no_free, available=10.0)[0] == "mid"
    unpriced = api_profile("acme/unpriced", price={})
    assert choose(profiles={"dear": DEAR, "x": unpriced}, available=10.0)[0] is None  # a paid route needs a price
    alias = api_profile(None)
    assert choose(profiles={"dear": DEAR, "alias": alias})[0] is None  # an alias earns no standing


def test_a_proven_or_put_back_model_is_not_a_candidate(tmp_path):
    for i in range(5):
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, True), settings=ON)
    models = assessment.load_models(tmp_path)
    assert choose(models=models, available=10.0)[0] == "mid"
    for i in range(5, 7):
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, False), settings=ON)
    assert assessment.standing(assessment.load_models(tmp_path)[assessment.route_key(CHEAP)], "standard", ON, "standard")["state"] == "put_back"
    assert choose(models=assessment.load_models(tmp_path), available=10.0)[0] == "mid"


# ---------------------------------------------------------------------------
# The budget (0179, item 4)
# ---------------------------------------------------------------------------


def test_reservations_are_held_under_a_lock_and_reconciled(tmp_path):
    s = AssessmentSettings(trials=True, daily_limit_usd=1.0)
    results = []
    threads = [threading.Thread(target=lambda i=i: results.append(assessment.reserve(tmp_path, f"d{i}", 0.4, s))) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, False, False, False, True, True]  # concurrent dispatches cannot claim the same credit
    held = [r for r, ok in zip([f"d{i}" for i in range(6)], results) if ok]
    assert assessment.available(tmp_path, s) == pytest.approx(0.2)
    rid = next(iter(assessment._load_spend(tmp_path)["reservations"]))
    assessment.reconcile(tmp_path, rid, 0.05)
    assert assessment.available(tmp_path, s) == pytest.approx(0.55)
    assessment.reconcile(tmp_path, rid, 9.0)  # once only
    assert assessment.available(tmp_path, s) == pytest.approx(0.55)
    assert assessment.reserve(tmp_path, "free", 0.0, AssessmentSettings(trials=True))  # free needs no credit
    assert held


def test_the_estimate_is_conservative_and_unknown_without_a_price():
    assert assessment.estimate_usd(CHEAP) == 0.0
    assert assessment.estimate_usd(api_profile("acme/x", price={})) is None
    est = assessment.estimate_usd(MID)
    assert est == pytest.approx(100_000 * 4 * 0.1 / 1e6 + 16_000 * 0.4 / 1e6)


def test_the_settings_are_machine_level_and_off_by_default(tmp_path):
    home = tmp_path / "home"
    assert prefs.load(home).assessment == AssessmentSettings()
    out = prefs.update_assessment(home, trials=True, daily_limit_usd=0.5)
    assert out["assessment"]["trials"] is True and out["assessment"]["shadows"] is False
    assert yaml.safe_load((home / "preferences.yaml").read_text())["assessment"] == {"trials": True, "daily_limit_usd": 0.5}
    from baton.routing import PreferencesError

    with pytest.raises(PreferencesError):
        prefs.update_assessment(home, daily_limit_usd=-1)


# ---------------------------------------------------------------------------
# The engine: a trial, its fallback and the record (no processes)
# ---------------------------------------------------------------------------


PROFILES = """\
owner:
  adapter: manual
  vendor: human
  person: owner
  capabilities: [human_judgment, structured_output, long_form_writing, technical_reasoning, file_write]
  tier: strong
cheap:
  adapter: litellm_api
  creator: acme
  model_id: acme/cheap
  provider: openrouter
  model: openrouter/acme/cheap
  capabilities: [structured_output]
  tier: standard
  context_tokens: 100000
  price: {free: true}
  auth: {mode: api_key, env: {OPENROUTER_API_KEY: "secret:or"}}
dear:
  adapter: litellm_api
  creator: other
  model_id: other/dear
  provider: openrouter
  model: openrouter/other/dear
  capabilities: [structured_output]
  tier: standard
  context_tokens: 100000
  price: {input: 5, output: 20}
  auth: {mode: api_key, env: {OPENROUTER_API_KEY: "secret:or"}}
"""


def project(tmp_path: Path, gates: list[dict], *, trials: bool = True, **stepkw) -> tuple[Api, str]:
    recipe = make_recipe(
        tmp_path / "toy",
        [{"id": "draft", "requires": {"capabilities": ["structured_output"], "tier": "standard"}, "output_schema": "schemas/out.json",
          "effect": "reversible", "gates": gates, **stepkw}],
        schemas={"out.json": {"type": "object"}}, defaults={"max_attempts": 1},
    )
    (recipe / "prompts" / "rubric.md").write_text("Check it.\n", encoding="utf-8")
    root = make_git_project(tmp_path / "proj")
    init(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    home = make_home(tmp_path / "home", PROFILES)
    if trials:
        prefs.update_assessment(home, trials=True)
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "vendor")
    return api, api.start("toy", {"title": "Trial"})["run_id"]


def attempt(api: Api, run: str, chosen: str, *, gate_file: bool, output=None):
    """Dispatch as ``Api._dispatch`` does, without a process: choose a trial, begin the attempt, hand in a result, run intake."""
    ctx = api._ctx(run)
    node = engine.node_for(ctx.recipe, "draft")
    routing, _w = api._routing(ctx, "draft")
    before = ctx.log.state().last_seq
    trial = api._choose_trial(ctx, node, "draft", chosen, routing, f"d_{ctx.log.state().step('draft').attempt + 1}")
    name, prof, extra = chosen, api._current_profiles()[chosen], None
    if trial is not None:
        name, prof = trial["profile"], trial["_profile"]
        extra = {"trial": True, "fallback": chosen, "tier": trial["tier"], "estimate_usd": trial["estimate_usd"]}
    built = engine.begin_attempt(ctx, "draft", name, prof, dispatch_id=f"d_{ctx.log.state().step('draft').attempt + 1}",
                                 dispatch_data={"trial": extra} if extra else None, selected_extra=extra)
    (api.project.root / "gate-pass").unlink(missing_ok=True)
    if gate_file:
        (api.project.root / "gate-pass").write_text("ok")
    write_result(built, {} if output is None else output)
    out = engine.submit(ctx, "draft")
    notices = api._learn(ctx, [e for e in ctx.log.events() if e.seq > before])
    return trial, out, notices


GATES = [{"type": "schema"}, {"type": "script", "run": "test -f gate-pass"}]


@pytest.mark.slow
def test_a_failed_trial_falls_back_without_spending_the_attempt_even_with_a_limit_of_one(tmp_path):
    api, run = project(tmp_path, GATES)
    trial, out, _ = attempt(api, run, "dear", gate_file=False)
    assert trial is not None and trial["profile"] == "cheap" and "cheaper model than dear" in trial["message"]
    assert out.outcome == "retry" and "dispatch dear to do it again" in out.reasons[0]
    ctx = api._ctx(run)
    st = ctx.log.state().step("draft")
    assert st.state == "ready" and st.attempt - st.budget_base == 0
    sel = [e.data for e in ctx.log.events() if e.type == "worker_selected"]
    assert sel[0]["profile"] == "cheap" and sel[0]["trial"] is True and sel[0]["fallback"] == "dear"  # identity as any dispatch (0075)
    assert [e.data["profile"] for e in ctx.log.events() if e.type == "trial_failed"] == ["cheap"]
    # The fallback: the Director's choice, an ordinary attempt (one trial per step in a run).
    trial2, out2, _ = attempt(api, run, "dear", gate_file=True)
    assert trial2 is None and out2.outcome == "passed"
    models = assessment.load_models(api.project.home)
    cheap = models[assessment.route_key(api._current_profiles()["cheap"])]
    dear = models[assessment.route_key(api._current_profiles()["dear"])]
    assert cheap["totals"]["standard"] == {"trial": {"passed": 0, "failed": 1}}
    assert dear["totals"]["standard"] == {"step": {"passed": 1, "failed": 0}}


@pytest.mark.slow
def test_with_assessment_off_dispatch_is_unchanged(tmp_path):
    api, run = project(tmp_path, GATES, trials=False)
    trial, out, _ = attempt(api, run, "dear", gate_file=False)
    assert trial is None
    assert out.outcome == "escalated"  # the attempt budget of one is spent as before
    assert not any(e.type in ("trial_failed",) or e.data.get("trial") for e in api._ctx(run).log.events())


@pytest.mark.slow
def test_a_passed_trial_counts_for_the_candidate(tmp_path):
    api, run = project(tmp_path, GATES)
    trial, out, _ = attempt(api, run, "dear", gate_file=True)
    assert trial["profile"] == "cheap" and out.outcome == "passed"
    rec = assessment.load_models(api.project.home)[assessment.route_key(api._current_profiles()["cheap"])]
    assert rec["totals"]["standard"] == {"trial": {"passed": 1, "failed": 0}}


@pytest.mark.slow
def test_a_trial_waiting_on_its_review_is_not_yet_a_pass(tmp_path):
    gates = [{"type": "schema"}, {"type": "review", "block_on": ["high"], "reviewer_requires": {"capabilities": ["structured_output"]}, "rubric": "prompts/rubric.md"}]
    api, run = project(tmp_path, gates)
    trial, out, _ = attempt(api, run, "dear", gate_file=True)
    assert trial is not None and out.outcome == "needs_review"
    assert assessment.load_models(api.project.home) == {}  # a schema pass while the review is pending is not success (0179, item 3)


@pytest.mark.slow
def test_a_candidate_put_back_is_announced_and_then_routed_one_tier_lower(tmp_path):
    api, run = project(tmp_path, GATES)
    cheap = api._current_profiles()["cheap"]
    assessment.record_outcome(api.project.home, "cheap", cheap, outcome(100, False), settings=ON)
    _trial, _out, notices = attempt(api, run, "dear", gate_file=False)
    assert len(notices) == 1 and "treats it as below standard" in notices[0]
    changed = [e.data for e in api._ctx(run).log.events() if e.type == "model_standing_changed"]
    assert changed[0]["after"] == "put_back" and changed[0]["profile"] == "cheap"
    assert api.eligible(run, "draft")["eligible"][0]["profile"] == "dear"
    assert "cheap" in [x["profile"] for x in api.eligible(run, "draft")["excluded"]]


def test_status_lists_each_track_record_and_the_models_put_back(tmp_path):
    from baton import resources

    for i in range(2):
        assessment.record_outcome(tmp_path, "cheap", CHEAP, outcome(i, False), settings=ON)
    assessment.record_outcome(tmp_path, "dear", DEAR, outcome(5, True, kind="step"), settings=ON)
    gen = {"cheap": {}, "dear": {}}
    bodies = {n: p.model_dump(mode="json", exclude_none=True) for n, p in (("cheap", CHEAP), ("dear", DEAR))}
    out = resources._assessment_summary(tmp_path, bodies, gen)
    assert out["put_back"] == [{"profile": "cheap", "tier": "standard", "by": "evidence", "failures": out["put_back"][0]["failures"]}]
    assert len(out["put_back"][0]["failures"]) == 2
    assert gen["dear"]["track_record"]["by_tier"]["standard"]["step"] == {"passed": 1, "failed": 0}
    assert out["settings"]["trials"] is False and out["budget"]["available_usd"] == 0.0
