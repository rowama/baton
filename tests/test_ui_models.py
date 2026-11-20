"""Models and preferences on the page and in `baton workers prefs`; the machine level of routing preferences (§8.4, §13.9; 0124)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from baton import cli, prefs, resources, routing, ui
from baton.models import Preferences, Requires, Step

from test_resources import found, run_setup
from test_ui import Page, home  # noqa: F401  (the fixture)


def test_a_turned_off_model_is_excluded_from_routing_with_its_level_named(home, tmp_path):  # noqa: F811
    p = Page(home)
    try:
        r, raw = p.post("/api/models/codex/enabled", {"enabled": False})
        assert r.status == 200 and json.loads(raw)["exclude"] == ["codex"]
        state = json.loads(p.req("GET", "/api/state")[1])
        assert next(m for m in state["models"] if m["profile"] == "codex")["enabled"] is False
    finally:
        p.close()
    assert yaml.safe_load((home / "preferences.yaml").read_text())["exclude"] == ["codex"]
    # Routing reads it: the exclusion reason says it is the machine's.
    project = tmp_path / "proj" / ".baton"
    project.mkdir(parents=True)
    merged = routing.load_preferences(project, home)
    assert "codex" in merged.exclude and merged.excluded_by_machine("codex")


@pytest.mark.not_slow("loopback requests only")
def test_turning_it_back_on_and_unknown_names(home):  # noqa: F811
    p = Page(home)
    try:
        p.post("/api/models/codex/enabled", {"enabled": False})
        assert json.loads(p.post("/api/models/codex/enabled", {"enabled": True})[1])["exclude"] == []
        r, raw = p.post("/api/models/nope/enabled", {"enabled": False})
        assert r.status == 422 and "no worker profile named nope" in json.loads(raw)["message"]
        assert p.post("/api/models/codex/enabled", {"enabled": "yes"})[0].status == 400
    finally:
        p.close()


def pm(**kw) -> Preferences:
    return Preferences.model_validate(kw)


@pytest.mark.not_slow("pure functions")
def test_the_merge_rules_of_decision_0124():
    machine = pm(prefer={"by_step": {"s": ["a"]}, "by_capability": {"c1": ["a"], "c2": ["b"]}}, exclude=["x"], cheapest_first=True)
    project = pm(prefer={"by_capability": {"c1": ["z"]}}, exclude=["y"])
    m = routing.merge_preferences(machine, project)
    assert m.prefer.by_capability == {"c1": ["z"], "c2": ["b"]} and m.prefer.by_step == {"s": ["a"]}   # per key, the project's wins
    assert m.exclude == ["x", "y"]                                                                     # the union
    assert m.cheapest_first is True                                                                    # the project did not set it
    assert routing.merge_preferences(machine, pm(cheapest_first=False)).cheapest_first is False         # the project did
    assert m.excluded_by_machine("x") and not m.excluded_by_machine("y")


@pytest.mark.not_slow("pure functions")
def test_a_project_cannot_lift_a_machine_exclusion(home, tmp_path):  # noqa: F811
    prefs.update(home, exclude=["codex"])
    baton = tmp_path / "p" / ".baton"
    baton.mkdir(parents=True)
    (baton / "preferences.yaml").write_text("exclude: []\n", encoding="utf-8")
    assert "codex" in routing.load_preferences(baton, home).exclude
    (home / "preferences.yaml").write_text("bogus: 1\n", encoding="utf-8")
    with pytest.raises(routing.PreferencesError):
        routing.load_preferences(baton, home)


@pytest.mark.not_slow("pure functions")
def test_eligibility_names_the_level(home):  # noqa: F811
    from baton import vocab
    from baton.models import WorkerProfile

    prefs.update(home, exclude=["codex"])
    profile = WorkerProfile.model_validate(yaml.safe_load((home / "workers" / "codex.yaml").read_text(encoding="utf-8")))
    step = Step.model_validate({"id": "s", "title": "s", "prompt": "p", "requires": {"capabilities": []}})
    out = routing.eligible_workers(step, "s", {"codex": profile}, vocab.load(vocab.DEFAULT), preferences=routing.load_preferences(home / "none", home))
    assert any("turned off for this machine" in r for e in out.excluded for r in e["reasons"])


@pytest.mark.not_slow("loopback requests only")
def test_ordering_and_preferred_models(home):  # noqa: F811
    p = Page(home)
    try:
        out = json.loads(p.req("PUT", "/api/preferences", headers={"X-Baton-UI": "1"}, body={"cheapest_first": True, "prefer_by_capability": {"web_access": ["codex"]}})[1])
        assert out["cheapest_first"] is True and out["prefer_by_capability"] == {"web_access": ["codex"]}
        assert json.loads(p.req("GET", "/api/preferences")[1])["cheapest_first"] is True
        r, raw = p.req("PUT", "/api/preferences", headers={"X-Baton-UI": "1"}, body={"prefer_by_capability": {"web_access": ["nope"]}})
        assert r.status == 422
        out = json.loads(p.req("PUT", "/api/preferences", headers={"X-Baton-UI": "1"}, body={"prefer_by_capability": {"web_access": []}, "cheapest_first": False})[1])
        assert out["prefer_by_capability"] == {} and out["cheapest_first"] is False
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_verifying_one_model_runs_the_one_live_check(home, monkeypatch):  # noqa: F811
    calls = []
    real = resources.setup

    def fake_setup(h, **kw):
        calls.append(kw)
        return real(h, **{**kw, "discover_fn": found("codex"), "verifier": lambda hh, n, pr: (n == "codex", "no reply")})

    monkeypatch.setattr(resources, "setup", fake_setup)
    p = Page(home)
    try:
        out = json.loads(p.post("/api/models/codex/verify")[1])
        assert out["verified"] == ["codex"] and calls == [{"verify": ["codex"]}]
        out = json.loads(p.post("/api/models/openrouter-main-acme-big/verify")[1])
        assert out["verified"] == [] and out["failed"]
    finally:
        p.close()
    assert json.loads(json.dumps(resources.generated_profiles(home)["codex"]["verified"]))["adapter"]


@pytest.mark.not_slow("loopback requests only")
def test_the_cli_and_the_page_write_the_same_preferences_file(home, tmp_path, monkeypatch):  # noqa: F811
    other = tmp_path / "other"
    other.mkdir()
    run_setup(other, found("codex"))
    p = Page(home)
    try:
        p.post("/api/models/codex/enabled", {"enabled": False})
        p.req("PUT", "/api/preferences", headers={"X-Baton-UI": "1"}, body={"cheapest_first": True, "prefer_by_capability": {"web_access": ["codex"]}})
    finally:
        p.close()
    monkeypatch.setenv("BATON_HOME", str(other))
    for args in (["--exclude", "codex"], ["--cheapest-first", "--prefer", "web_access=codex"]):
        res = CliRunner().invoke(cli.app, ["workers", "prefs", *args, "--json"])
        assert res.exit_code == 0, res.output
    assert (home / "preferences.yaml").read_text() == (other / "preferences.yaml").read_text()
    shown = CliRunner().invoke(cli.app, ["workers", "prefs"])
    assert "by cost (your subscriptions" in shown.output and "turned off: codex" in shown.output
    bad = CliRunner().invoke(cli.app, ["workers", "prefs", "--exclude", "nope", "--json"])
    assert bad.exit_code == 1 and "no worker profile named nope" in bad.output
    assert CliRunner().invoke(cli.app, ["workers", "prefs", "--prefer", "oops"]).exit_code == 2


@pytest.mark.not_slow("loopback requests only")
def test_the_state_carries_what_the_models_table_filters_on(home):  # noqa: F811
    p = Page(home)
    try:
        state = json.loads(p.req("GET", "/api/state")[1])
    finally:
        p.close()
    row = state["models"][0]
    for k in ("provider", "price", "context_tokens", "tier", "capabilities", "verified", "enabled", "subscription"):
        assert k in row
    assert {k: v for k, v in state["preferences"].items() if k != "assessment"} == {"cheapest_first": True, "exclude": [], "prefer_by_capability": {}}
    assert state["preferences"]["assessment"]["trials"] is False and state["preferences"]["assessment"]["shadows"] is False


# -- trying cheaper models (change 2026-11-model-assessment, slice 3; Decisions 0176, 0179, 0182) --


@pytest.mark.not_slow("loopback requests only")
def test_the_page_turns_trials_on_with_a_daily_limit_and_shows_the_budget(home):  # noqa: F811
    p = Page(home)
    try:
        state = json.loads(p.req("GET", "/api/state")[1])
        assert state["assessment"]["settings"]["trials"] is False and state["assessment"]["budget"]["limit_usd"] == 0.0
        out = json.loads(p.req("PUT", "/api/assessment", headers={"X-Baton-UI": "1"}, body={"trials": True, "daily_limit_usd": 0.5})[1])
        assert out["assessment"]["trials"] is True and out["assessment"]["shadows"] is False and out["assessment"]["daily_limit_usd"] == 0.5
        assert p.req("PUT", "/api/assessment", headers={"X-Baton-UI": "1"}, body={"daily_limit_usd": -1})[0].status == 400
        assert p.req("PUT", "/api/assessment", headers={"X-Baton-UI": "1"}, body={"trials": "yes"})[0].status == 400
        assert p.post("/api/models/codex/standing", {"tier": "huge", "standing": "proven"})[0].status == 400
        assert p.post("/api/models/nope/standing", {"tier": "basic", "standing": "proven"})[0].status == 404
    finally:
        p.close()
    assert yaml.safe_load((home / "preferences.yaml").read_text())["assessment"] == {"trials": True, "daily_limit_usd": 0.5}


@pytest.mark.not_slow("in-process CLI runner")
def test_the_assessment_and_standing_commands(tmp_path, monkeypatch):
    from baton import assessment

    home = tmp_path / "home"
    (home / "workers").mkdir(parents=True)
    (home / "workers" / "cheap.yaml").write_text(yaml.safe_dump({
        "adapter": "litellm_api", "creator": "acme", "model_id": "acme/cheap", "provider": "openrouter", "model": "openrouter/acme/cheap",
        "capabilities": ["structured_output"], "tier": "standard", "price": {"free": True},
        "auth": {"mode": "api_key", "env": {"KEY": "secret:k"}}}), encoding="utf-8")
    monkeypatch.setenv("BATON_HOME", str(home))
    shown = CliRunner().invoke(cli.app, ["workers", "assessment"])
    assert shown.exit_code == 0 and "trials: off" in shown.output and "free models only" in shown.output
    out = json.loads(CliRunner().invoke(cli.app, ["workers", "assessment", "--trials", "--daily-limit", "2", "--json"]).output)
    assert out["assessment"]["trials"] is True and out["budget"]["available_usd"] == 2.0
    res = CliRunner().invoke(cli.app, ["workers", "standing", "cheap", "--tier", "standard", "--put-back", "--json"])
    assert res.exit_code == 0 and json.loads(res.output)["standing"] == "put_back"
    profile = assessment.machine_profiles(home)["cheap"]
    assert assessment.put_back_tiers(assessment.load_models(home), profile, prefs.load(home).assessment, ["basic", "standard", "strong"]) == ["standard"]
    status = CliRunner().invoke(cli.app, ["workers", "status"])
    assert status.exit_code == 0, status.output
    assert "put back: cheap at standard (by you)" in status.output and "trials: on" in status.output
    assert CliRunner().invoke(cli.app, ["workers", "standing", "cheap", "--tier", "standard"]).exit_code == 2
    assert CliRunner().invoke(cli.app, ["workers", "standing", "nope", "--tier", "basic", "--promote"]).exit_code != 0
    res = CliRunner().invoke(cli.app, ["workers", "standing", "cheap", "--tier", "standard", "--promote"])
    assert res.exit_code == 0 and "promoted" in res.output
