"""Harness tool maps, least privilege and verification by use (§6.3, §8.8; 0085, 0086)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import capability_states as cs
from baton import resources
from baton.engine import Api
from baton.project import init

from harnesskit import calls, harness_profile, install_fake, set_outputs
from projectkit import git, make_git_project, make_home
from runkit import Clock, make_recipe

WEB_CAPS = ["structured_output", "web_access", "tool_use"]
USED = [
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {"query": "x"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "results", "is_error": False}]}},
]
DENIED = [{"type": "result", "subtype": "success", "permission_denials": [{"tool_name": "WebSearch", "tool_use_id": "t1"}]}]


@pytest.fixture
def web(tmp_path):
    """A git project with a one-step recipe needing web_access, and two fake Claude Code profiles."""
    recipe = make_recipe(
        tmp_path / "toy",
        [{"id": "search", "requires": {"capabilities": ["structured_output", "web_access"]}, "output_schema": "schemas/out.json"}],
        schemas={"out.json": {"type": "object"}},
    )
    root = make_git_project(tmp_path / "proj")
    init(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    bins = {n: install_fake(tmp_path / f"bin-{n}", "claude", {"search": {"output": {}}}) for n in ("a", "b")}
    home = make_home(tmp_path / "home", "".join(
        harness_profile(f"claude-{n}", "claude_code", "acme", executable=str(exe), capabilities=WEB_CAPS) for n, exe in bins.items()
    ))
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "vendor")
    run = api.start("toy", {"title": "Web"})["run_id"]
    return api, home, {n: e.parent for n, e in bins.items()}, run


def observed(api):
    return [e.data for e in api.project.store.project_log().events() if e.type == "capability_observed"]


@pytest.mark.slow
def test_a_web_step_turns_on_web_tools_and_a_used_tool_is_verified(web):
    api, home, bins, run = web
    set_outputs(bins["a"], {"search": {"output": {}, "events": USED}})
    out = api.dispatch(run, "search", "claude-a", wait=True)
    assert out["outcome"] == "passed", out
    (call,) = calls(bins["a"])
    assert call["argv"][call["argv"].index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert "--disallowedTools" not in call["argv"] and "stream-json" in call["argv"]
    disp = next(e.data for e in api._ctx(run).log.events() if e.type == "dispatched")
    assert disp["tools"] == {"on": ["web_access"], "off": [], "args": ["--allowedTools", "WebSearch,WebFetch"]}
    assert disp["harness_version"] == "9.9.0"
    state = cs.load(home)["claude-a"]["web_access"]
    assert (state.state, state.by, state.harness_version, state.attempt) == ("verified", "observed", "9.9.0", 1)
    (ev,) = observed(api)
    assert ev["state"] == "verified" and ev["run"] == run and ev["step_path"] == "search" and ev["attempt"] == 1


@pytest.mark.slow
def test_a_step_that_passed_without_the_tool_records_nothing(web):
    api, home, bins, run = web
    assert api.dispatch(run, "search", "claude-a", wait=True)["outcome"] == "passed"
    assert cs.load(home) == {} and observed(api) == []


@pytest.mark.slow
def test_a_denied_tool_reroutes_without_spending_an_attempt(web):
    api, home, bins, run = web
    set_outputs(bins["a"], {"search": {"output": {}, "events": DENIED}})
    out = api.dispatch(run, "search", "claude-a", wait=True)
    assert out["outcome"] == "retry", out
    assert cs.load(home)["claude-a"]["web_access"].state == "absent"
    ev = api._ctx(run).log.events()
    cls = [e.data for e in ev if e.type == "failure_classified"][-1]
    assert (cls["class"], cls["code"], cls["capabilities"]) == ("platform", "capability_absent", ["web_access"])
    assert [e.data for e in ev if e.type == "step_ready"][-1]["not_counted"] is True
    assert not [e for e in api.project.store.project_log().events() if e.type == "platform_incident_opened"]
    st = api._ctx(run).log.state().step("search")
    assert st.attempt - st.budget_base == 0  # the denied attempt is not counted
    assert [e["profile"] for e in api.eligible(run, "search")["eligible"]] == ["claude-b"]
    set_outputs(bins["b"], {"search": {"output": {}, "events": USED}})
    assert api.dispatch(run, "search", "claude-b", wait=True)["outcome"] == "passed"


@pytest.mark.slow
def test_absent_on_every_profile_escalates_at_once(web):
    api, home, bins, run = web
    cs.record(home, "claude-b", "web_access", "absent", by="owner", evidence="declared by the owner")
    set_outputs(bins["a"], {"search": {"output": {}, "events": DENIED}})
    out = api.dispatch(run, "search", "claude-a", wait=True)
    assert out["outcome"] == "escalated", out
    esc = [e.data for e in api._ctx(run).log.events() if e.type == "step_escalated"][-1]
    assert esc["reason"] == "no_eligible_worker"


@pytest.mark.slow
def test_a_rejected_flag_opens_an_incident_and_marks_the_tool_absent(web):
    api, home, bins, run = web
    set_outputs(bins["a"], {"reject_flag": "--allowedTools", "search": {"output": {}}})
    out = api.dispatch(run, "search", "claude-a", wait=True)
    assert out["outcome"] == "escalated", out
    cls = [e.data for e in api._ctx(run).log.events() if e.type == "failure_classified"][-1]
    assert (cls["class"], cls["code"]) == ("platform", "harness_flag_rejected")
    (inc,) = [e.data for e in api.project.store.project_log().events() if e.type == "platform_incident_opened"]
    assert inc["code"] == "harness_flag_rejected"
    assert cs.load(home)["claude-a"]["web_access"].state == "absent"


@pytest.mark.slow
def test_a_new_harness_version_returns_observed_states_to_likely(web):
    api, home, bins, run = web
    cs.record(home, "claude-a", "web_access", "absent", by="observed", evidence="denied", harness_version="9.9.0")
    cs.record(home, "claude-b", "web_access", "absent", by="owner", evidence="declared by the owner")
    assert [e["profile"] for e in api.eligible(run, "search")["eligible"]] == []
    (bins["a"] / "version.txt").write_text("9.10.0\n", encoding="utf-8")
    (bins["a"] / "claude").touch()  # an upgrade changes the executable
    import os
    import time

    t = time.time() + 5
    os.utime(bins["a"] / "claude", (t, t))
    out = api.eligible(run, "search")
    assert [e["profile"] for e in out["eligible"]] == ["claude-a"]
    assert "claude-a" not in cs.load(home)  # forgotten, so likely again
    assert cs.load(home)["claude-b"]["web_access"].state == "absent"  # the owner's declaration stays


@pytest.mark.not_slow("measured under 1 s")
def test_setup_offers_a_tool_only_when_the_cli_shows_its_flag(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    install_fake(bin_dir, "claude")
    install_fake(bin_dir, "codex")
    (bin_dir / "help.txt").write_text("  --allowedTools <tools...>\n  --json\n", encoding="utf-8")  # no --search
    monkeypatch.setattr(resources, "DISCOVERY_SEARCH", [str(bin_dir)])
    monkeypatch.setenv("HOME", str(tmp_path))
    out = resources.setup(home)
    det = {d["provider"]: d for d in out["detected"]}
    assert det["claude_code"]["tools"] == {"web_access": True} and det["codex"]["tools"] == {"web_access": False}
    claude = resources.read_generated_dir(home)["claude-code"][1]
    codex = resources.read_generated_dir(home)["codex"][1]
    assert "web_access" in claude["capabilities"] and "web_access" not in codex["capabilities"]
