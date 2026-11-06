"""Routing: eligibility, independence, preferences, escalation (§8.4; §18 #2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from baton.engine import Api
from baton.packet import EngineError
from baton.project import init

from projectkit import make_home, packet_dir, write_result
from runkit import Clock, make_recipe

PROFILES = """\
alice:
  adapter: manual
  vendor: acme
  capabilities: [structured_output]
  tier: strong
bob:
  adapter: manual
  vendor: ACME
  capabilities: [structured_output]
  tier: basic
carol:
  adapter: manual
  vendor: zenith
  capabilities: [structured_output]
  tier: standard
weak:
  adapter: manual
  vendor: other
  capabilities: []
  tier: strong
"""


@pytest.fixture
def routed(tmp_path):
    recipe = make_recipe(
        tmp_path / "toy",
        [
            {"id": "draft", "requires": {"capabilities": ["structured_output"], "tier": "standard"}, "output_schema": "schemas/out.json"},
            {
                "id": "review",
                "depends_on": ["draft"],
                "requires": {"capabilities": ["structured_output"]},
                "independence": {"from_step": "draft", "level": "different_vendor"},
                "output_schema": "schemas/out.json",
            },
            {"id": "look", "depends_on": ["review"], "requires": {"capabilities": ["vision"]}, "output_schema": "schemas/out.json"},
        ],
        schemas={"out.json": {"type": "object"}},
    )
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    home = make_home(tmp_path / "home", PROFILES)
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    run = api.start("toy", {"title": "Routing"})["run_id"]
    return api, root, run


def names(out: dict) -> list[str]:
    return [e["profile"] for e in out["eligible"]]


def excluded(out: dict) -> dict[str, list[str]]:
    return {e["profile"]: e["reasons"] for e in out["excluded"]}


def pass_step(api: Api, root: Path, run: str, step: str, worker: str) -> None:
    d = api.dispatch(run, step, worker)
    write_result(packet_dir(root, run, step, d["attempt"]), {})
    assert api.submit(run, step)["outcome"] == "passed"


def test_requirements_filter_with_reasons(routed):
    api, root, run = routed
    out = api.eligible(run, "draft")
    assert names(out) == ["alice", "carol"]
    ex = excluded(out)
    assert ex["bob"] == ["needs tier standard; profile is basic"]
    assert ex["weak"] == ["missing capabilities: structured_output"]
    assert out["escalated"] is False


def test_preferences_reorder_and_exclude_but_never_add(routed):
    api, root, run = routed
    (root / ".baton" / "preferences.yaml").write_text("prefer:\n  by_step: { draft: [weak, carol] }\n", encoding="utf-8")
    out = api.eligible(run, "draft")
    assert names(out) == ["carol", "alice"]  # weak is preferred but ineligible: never added
    assert "preferred for step draft" in out["eligible"][0]["reasons"]
    (root / ".baton" / "preferences.yaml").write_text(
        "prefer:\n  by_capability: { structured_output: [carol] }\nexclude: [alice]\n", encoding="utf-8"
    )
    out = api.eligible(run, "draft")
    assert names(out) == ["carol"]
    assert "excluded by preferences.yaml" in excluded(out)["alice"]
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "draft", "alice")
    assert e.value.code == "routing.ineligible" and "preferences" in str(e.value)


def test_bad_preferences_are_configuration(routed):
    api, root, run = routed
    (root / ".baton" / "preferences.yaml").write_text("prefer: { by_model: {} }\n", encoding="utf-8")
    with pytest.raises(EngineError) as e:
        api.eligible(run, "draft")
    assert e.value.code == "configuration.preferences"


def test_independence_uses_the_recorded_worker(routed):
    api, root, run = routed
    pass_step(api, root, run, "draft", "alice")
    out = api.eligible(run, "review")
    assert names(out) == ["carol"]  # weak lacks structured_output
    ex = excluded(out)
    assert any("independence: different_vendor from draft (done by alice, vendor acme)" in r for r in ex["alice"])
    assert any("independence" in r for r in ex["bob"])  # vendor match is case-insensitive
    # The record, not this machine's profiles, says who did draft.
    (Path(api.project.home) / "workers.yaml").write_text(PROFILES.replace("vendor: acme", "vendor: renamed"), encoding="utf-8")
    assert "alice" not in names(api.eligible(run, "review"))
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "review", "bob")
    assert e.value.code == "routing.ineligible"


def test_no_eligible_worker_escalates_and_never_fails_the_run(routed):
    api, root, run = routed
    pass_step(api, root, run, "draft", "alice")
    pass_step(api, root, run, "review", "carol")
    out = api.eligible(run, "look")
    assert out["eligible"] == [] and out["escalated"] is True
    assert out["needs_owner"] is True
    st = api.status(run)
    assert st["state"] == "active"
    assert st["steps"]["look"]["state"] == "escalated"
    pending = st["pending_decisions"][0]
    assert pending["reason"] == "no_eligible_worker"
    assert any(r.startswith("alice: missing capabilities: vision") for r in pending["reasons"])
    # Asking again does not escalate twice.
    assert api.eligible(run, "look")["escalated"] is False
    # Once the owner says retry, the step is ready again (e.g. after a vision-capable profile is added).
    api.decide(run, "look", "retry", note="added a vision profile")
    assert api.status(run)["steps"]["look"]["state"] == "ready"


def test_worker_selected_records_vendor_and_model(routed):
    api, root, run = routed
    api.dispatch(run, "draft", "carol")
    ev = [e for e in api.project.store.run(run).events() if e.type == "worker_selected"][-1]
    # Identity and route as at dispatch (0075); vendor is still written, equal to creator.
    assert ev.data == {"profile": "carol", "vendor": "zenith", "creator": "zenith", "adapter": "manual"}



def test_worker_selected_records_identity_and_route(tmp_path):
    from baton.models import WorkerProfile
    from baton.routing import identity_from_record, identity_record

    p = WorkerProfile.model_validate({"adapter": "litellm_api", "creator": "anthropic", "model_id": "anthropic/claude-opus-5-5",
                                      "provider": "openrouter", "model": "openrouter/anthropic/claude-opus-5.5"})
    rec = identity_record("routed", p)
    assert rec == {"profile": "routed", "vendor": "anthropic", "creator": "anthropic", "model_id": "anthropic/claude-opus-5-5",
                   "provider": "openrouter", "model": "openrouter/anthropic/claude-opus-5.5", "adapter": "litellm_api"}
    assert identity_from_record(rec).model_id == "anthropic/claude-opus-5-5"


def test_an_event_from_before_0075_has_unknown_model_identity():
    from baton.routing import identity_from_record

    old = identity_from_record({"profile": "api", "vendor": "openai", "model": "openai/some-model"})
    # creator is the recorded vendor; the model string is a route, never an identity.
    assert old.creator == "openai" and old.model_id is None and old.model == "openai/some-model"
