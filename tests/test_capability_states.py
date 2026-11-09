"""Capability states: likely, verified, absent; kept machine-wide; routing and the owner's controls (§6.1, §8.4; 0084)."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pytest
import yaml

from baton import capability_states as cs
from baton import resources
from baton.engine import Api, observe_capability
from baton.packet import EngineError, profile_sha256
from baton.project import init

from projectkit import Cli, make_home
from runkit import Clock, make_recipe
from test_resources import found, gen, run_setup

TODAY = dt.date(2026, 11, 8)

PROFILES = """\
alice:
  adapter: manual
  vendor: acme
  capabilities: [structured_output, web_access]
  tier: strong
carol:
  adapter: manual
  vendor: zenith
  capabilities: [structured_output, web_access]
  tier: strong
"""


@pytest.fixture
def routed(tmp_path):
    recipe = make_recipe(
        tmp_path / "toy",
        [{"id": "search", "requires": {"capabilities": ["structured_output", "web_access"]}, "output_schema": "schemas/out.json"}],
        schemas={"out.json": {"type": "object"}},
    )
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    home = make_home(tmp_path / "home", PROFILES)
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    run = api.start("toy", {"title": "States"})["run_id"]
    return api, root, home, run


def names(out):
    return [e["profile"] for e in out["eligible"]]


@pytest.mark.slow
def test_claimed_capabilities_start_likely_and_are_eligible(routed):
    api, _root, _home, run = routed
    out = api.eligible(run, "search")
    assert names(out) == ["alice", "carol"]
    assert out["eligible"][0]["capabilities"] == {"structured_output": "likely", "web_access": "likely"}


@pytest.mark.slow
def test_absent_is_not_eligible_and_says_how_to_reset(routed):
    api, _root, home, run = routed
    cs.record(home, "alice", "web_access", "absent", by="observed", evidence="WebSearch denied", today=TODAY)
    out = api.eligible(run, "search")
    assert names(out) == ["carol"]
    (reason,) = [e for e in out["excluded"] if e["profile"] == "alice"][0]["reasons"]
    assert "web_access is absent here (absent 2026-11-08 (observed, WebSearch denied))" in reason
    assert "--likely web_access" in reason
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "search", "alice")
    assert e.value.code == "routing.ineligible"


@pytest.mark.slow
def test_verified_is_preferred_over_likely_but_preferences_come_first(routed):
    api, root, home, run = routed
    cs.record(home, "carol", "web_access", "verified", by="observed", evidence="web_search call", today=TODAY)
    out = api.eligible(run, "search")
    assert names(out) == ["carol", "alice"]
    assert "verified here: web_access" in out["eligible"][0]["reasons"]
    (root / ".baton" / "preferences.yaml").write_text("prefer:\n  by_step: { search: [alice] }\n", encoding="utf-8")
    assert names(api.eligible(run, "search")) == ["alice", "carol"]


def test_states_live_outside_profiles_and_change_no_hash(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    run_setup(home, found("codex"))
    path = home / "workers" / "codex.yaml"
    before = path.read_bytes()
    body = gen(home, "codex")
    claimed = body["capabilities"]
    cap = claimed[0]
    cs.record(home, "codex", cap, "absent", by="observed", evidence="denied", today=TODAY)
    assert path.read_bytes() == before
    assert resources.ownership(yaml.safe_load(before)) == "untouched"
    st = resources.status(home, discover_fn=found("codex"))
    assert st["generated"]["codex"]["capabilities"][cap] == "absent"
    assert st["capability_states"]["codex"][cap]["state"] == "absent"
    # The profile's dispatch hash is the same with and without a state attached.
    from baton.models import WorkerProfile

    p = WorkerProfile.model_validate({k: v for k, v in body.items() if k != "generated"})
    assert profile_sha256(p) == profile_sha256(p.with_capability_states(cs.load(home)["codex"]))


def test_a_state_never_adds_a_capability(routed):
    api, _root, home, run = routed
    with pytest.raises(EngineError) as e:
        api.workers_declare(profile="alice", likely=["vision"])
    assert "does not claim vision" in str(e.value)
    assert not cs.path(home).exists()


@pytest.mark.slow
def test_the_owner_resets_and_declares_through_the_engine(routed):
    api, _root, home, run = routed
    out = api.workers_declare(profile="alice", absent=["web_access"])
    assert out["capability_states"] == [{"profile": "alice", "capability": "web_access", "from": "likely", "to": "absent", "changed": True}]
    assert names(api.eligible(run, "search")) == ["carol"]
    out = api.workers_declare(profile="alice", likely=["web_access"])
    assert out["capability_states"][0]["to"] == "likely"
    assert cs.load(home) == {}  # a reset forgets the observation
    assert names(api.eligible(run, "search")) == ["alice", "carol"]
    with pytest.raises(EngineError) as e:
        api.workers_declare("openrouter-main", profile="alice", absent=["web_access"])
    assert e.value.code == "usage.declare"


@pytest.mark.slow
def test_the_owner_resets_and_declares_from_the_cli(tmp_path):
    home = make_home(tmp_path / "home", PROFILES)
    root = tmp_path / "proj"
    root.mkdir()
    cli = Cli(root, home)
    out = cli.run("workers", "declare", "--profile", "carol", "--absent", "web_access")
    assert out["capability_states"][0]["to"] == "absent"
    status = cli.run("workers", "status")
    assert status["capability_states"]["carol"]["web_access"]["by"] == "owner"
    assert "no profile named 'nobody'" in cli("workers", "declare", "--profile", "nobody", "--likely", "web_access", expect=1).payload["message"]
    assert cli("workers", "declare", "--likely", "web_access", expect=None).payload["error"] == "usage.declare"


@pytest.mark.slow
def test_an_observation_is_recorded_once_with_its_attempt(routed):
    api, _root, home, run = routed
    project = api.project
    data = observe_capability(project, "alice", "web_access", "verified", "web_search call", run_id=run, step_path="search", attempt=1,
                              harness_version="1.0")
    assert data["previous"] == "likely" and data["attempt"] == 1
    assert observe_capability(project, "alice", "web_access", "verified", "another call", run_id=run, step_path="search", attempt=2,
                              harness_version="1.0") is None
    events = [e for e in project.store.project_log().events() if e.type == "capability_observed"]
    assert [(e.data["profile"], e.data["state"], e.data["run"], e.data["step_path"], e.data["attempt"]) for e in events] == [
        ("alice", "verified", run, "search", 1)
    ]
    assert cs.load(home)["alice"]["web_access"].state == "verified"


@pytest.mark.slow
def test_a_broken_state_file_is_a_configuration_problem(routed):
    api, _root, home, run = routed
    cs.path(home).write_text("format: baton-capability-states/1\nprofiles: { alice: { web_access: { state: maybe } } }\n", encoding="utf-8")
    with pytest.raises(EngineError) as e:
        api.eligible(run, "search")
    assert e.value.code == "configuration.capability_states"


# ---------------------------------------------------------------------------
# structured_output by schema-gate evidence (0087)
# ---------------------------------------------------------------------------


@pytest.fixture
def schema_run(tmp_path):
    recipe = make_recipe(
        tmp_path / "toy",
        [{"id": "draft", "requires": {"capabilities": ["structured_output"]}, "output_schema": "schemas/out.json"}],
        schemas={"out.json": {"type": "object", "required": ["title"]}},
        defaults={"max_attempts": 9},
    )
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    home = make_home(tmp_path / "home", PROFILES)
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    run = api.start("toy", {"title": "Schema"})["run_id"]
    return api, root, home, run


def attempt(api, root, run, worker, output):
    from projectkit import packet_dir, write_result

    d = api.dispatch(run, "draft", worker)
    write_result(packet_dir(root, run, "draft", d["attempt"]), output)
    return api.submit(run, "draft")["outcome"]


@pytest.mark.slow
def test_three_schema_failures_in_a_row_make_structured_output_absent(schema_run):
    api, root, home, run = schema_run
    for _ in range(2):
        assert attempt(api, root, run, "alice", {"wrong": 1}) == "retry"
    st = cs.load(home)["alice"]["structured_output"]
    assert (st.state, st.failures) == ("likely", 2)  # one or two failures change nothing
    assert "alice" in names(api.eligible(run, "draft"))
    assert attempt(api, root, run, "alice", {"wrong": 1}) == "retry"
    st = cs.load(home)["alice"]["structured_output"]
    assert (st.state, st.evidence) == ("absent", "3 schema-gate failures in a row")
    assert names(api.eligible(run, "draft")) == ["carol"]
    (ev,) = [e.data for e in api.project.store.project_log().events() if e.type == "capability_observed"]
    assert (ev["profile"], ev["capability"], ev["state"], ev["attempt"]) == ("alice", "structured_output", "absent", 3)


@pytest.mark.slow
def test_a_pass_resets_the_count(schema_run):
    api, root, home, run = schema_run
    assert attempt(api, root, run, "alice", {"wrong": 1}) == "retry"
    assert attempt(api, root, run, "alice", {"wrong": 1}) == "retry"
    assert attempt(api, root, run, "alice", {"title": "ok"}) == "passed"
    assert "alice" not in cs.load(home)


@pytest.mark.slow
def test_failures_are_counted_per_profile(schema_run):
    api, root, home, run = schema_run
    for worker in ("alice", "carol", "alice", "carol"):
        assert attempt(api, root, run, worker, {"wrong": 1}) == "retry"
    assert {p: s["structured_output"].failures for p, s in cs.load(home).items()} == {"alice": 2, "carol": 2}


def test_model_quality_capabilities_are_never_changed_automatically():
    """Only tool-map capabilities (tooling) are observed from streams, and a tool map may not name a model-quality one."""
    from baton import known_workers, vocab

    raw = yaml.safe_load(known_workers.default_path().read_text(encoding="utf-8"))
    raw["providers"]["claude_code"]["tools"]["technical_reasoning"] = dict(raw["providers"]["claude_code"]["tools"]["web_access"])
    voc = vocab.load(vocab.DEFAULT)
    _kw, issues = known_workers.validate(raw, voc, {"claude_code", "codex", "litellm_api", "manual", "command"})
    assert [i.code for i in issues] == ["known_workers.not_tooling"]
