"""Project policy (change 2026-11-project-policy; Decisions 0143, 0151, 0153; §13.7): recorded changes,
hand edits noticed and held until confirmed, a project with no record keeps its file in force."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from baton import policy
from baton.mcp_server import build_server
from baton.models import ProjectConfig
from baton.packet import EngineError
from projectkit import Cli, git, make_git_project, make_home
from test_tailoring_axes import write_recipe

NOTE = "Yes, set it that way."


def _events(project: Path, etype: str | None = None) -> list[dict]:
    f = project / ".baton" / "project" / "events.jsonl"
    evs = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []
    return [e for e in evs if etype is None or e["type"] == etype]


def _yaml(project: Path) -> dict:
    return yaml.safe_load((project / ".baton" / "project.yaml").read_text(encoding="utf-8"))


def _hand_edit(project: Path, edit) -> None:
    py = project / ".baton" / "project.yaml"
    cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
    edit(cfg)
    py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _project(tmp_path: Path, *, axes: bool = True, yaml_text: str | None = None) -> tuple[Cli, Path]:
    """A committed project; with ``axes``, a vendored recipe ``axes`` rated on discovery and assurance.
    ``yaml_text`` writes project.yaml before ``init`` (a project from before policy: nothing recorded)."""
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    if yaml_text is not None:
        (project / ".baton").mkdir()
        (project / ".baton" / "project.yaml").write_text(yaml_text, encoding="utf-8")
    cli.run("init", str(project), "--bare")
    if axes:
        cli.run("vendor", str(write_recipe(tmp_path / "axes")))
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Adopt Baton")
    return cli, project


def _rule(out: dict, key: str) -> dict:
    return next(r for r in out["rules"] if r["key"] == key)


# -- the policy value (no processes) -------------------------------------------


@pytest.mark.not_slow("pure functions")
def test_the_policy_value_is_independent_of_formatting_and_lists_every_rule():
    a = ProjectConfig.model_validate({"policy": {"floors": {"axes": {"assurance": "medium"}}}})
    b = ProjectConfig.model_validate({"policy": {"floors": {"axes": {"assurance": "medium"}}, "governing": []},
                                      "permissions": {"tag": "ask"}, "paths": {"x": "y"}})
    assert policy.sha256(policy.value_of(a)) == policy.sha256(policy.value_of(b))
    flat = policy.flatten(policy.value_of(a))
    assert flat["floors.axes.assurance"] == "medium" and flat["permissions.push.other"] == "ask" and flat["permissions.deploy"] == "deny"


@pytest.mark.not_slow("pure functions")
def test_changes_add_replace_and_remove_rules():
    base = policy.value_of(ProjectConfig())
    v = policy.apply(base, floors={"axes": {"assurance": "medium"}, "*": {"release": "low"}},
                     governing={"Software  development": "eng-process"}, permissions={"push.other": "allow", "tag": "allow"})
    assert v["floors"] == {"*": {"release": "low"}, "axes": {"assurance": "medium"}}
    assert v["governing"] == [{"work": "Software development", "recipe": "eng-process"}]
    assert v["permissions"]["push"]["other"] == "allow" and v["permissions"]["tag"] == "allow"
    v2 = policy.apply(v, floors={"*": {"release": None}}, governing={"software development": None})
    assert v2["floors"] == {"axes": {"assurance": "medium"}} and v2["governing"] == []
    assert [d["key"] for d in policy.differences(v, v2)] == ["floors.*.release", "governing.Software development"]
    for bad, code in [({"permissions": {"launch": "allow"}}, "policy.unknown_permission"),
                      ({"permissions": {"tag": "maybe"}}, "policy.bad_rule"),
                      ({"floors": {"axes": {"assurance": None}}}, "policy.no_such_floor"),
                      ({"governing": {"gardening": None}}, "policy.no_such_governing"),
                      ({"floors": {"Not A Recipe": {"assurance": "low"}}}, "policy.invalid")]:
        with pytest.raises(EngineError) as e:
            policy.apply(base, **bad)
        assert e.value.code == code


@pytest.mark.not_slow("pure functions")
def test_floor_problems_name_what_the_recipe_does_not_declare():
    scales = {"axes": {"discovery": ["low", "high"], "assurance": ["low", "medium", "high"]}, "plain": {"level": ["minor", "major"]}, "bare": {}}

    def of(rid):
        return scales if rid is None else scales.get(rid)

    value = {"floors": {"axes": {"assurance": "medium"}, "plain": {"level": "major"}, "*": {"assurance": "high", "release": "low"}}}
    assert policy.floor_problems(value, of) == ([], ["the floor release low for every recipe matches no vendored recipe (none declares release with low)"])
    refusals, _ = policy.floor_problems({"floors": {"axes": {"speed": "low", "assurance": "extreme"}, "bare": {"level": "x"},
                                                    "gone": {"level": "x"}}}, of)
    assert any("no axis 'speed'" in r for r in refusals) and any("no value 'extreme'" in r for r in refusals)
    assert any("bare has no ratings" in r for r in refusals) and any("no recipe gone" in r for r in refusals)
    assert policy.floor_problems({"floors": {"gone": {"level": "x"}}}, of, unknown_ok=True) == ([], [])


@pytest.mark.not_slow("pure functions")
def test_writing_replaces_only_the_policy_and_permissions_blocks(tmp_path):
    py = tmp_path / "project.yaml"
    py.write_text("# top comment\npaths: { docs: docs }   # where docs go\npermissions:   # release authority\n"
                  "  push: { docs_only: allow, after_verified: allow, other: ask }\n  tag: ask\nhooks: { on_complete: \"\" }\n", encoding="utf-8")
    value = policy.apply(policy.value_of(ProjectConfig()), permissions={"tag": "allow"}, floors={"axes": {"assurance": "medium"}})
    policy.write(py, value)
    text = py.read_text(encoding="utf-8")
    assert text.startswith("# top comment\npaths: { docs: docs }   # where docs go\npermissions:   # release authority\n")
    assert "hooks: { on_complete: \"\" }" in text
    cfg = ProjectConfig.model_validate(yaml.safe_load(text))
    assert policy.value_of(cfg) == value


# -- recorded changes ---------------------------------------------------------------------


@pytest.mark.slow
def test_init_records_its_defaults_and_policy_lists_them(tmp_path):
    cli, project = _project(tmp_path, axes=False)
    assert "policy:" in (project / ".baton" / "project.yaml").read_text(encoding="utf-8")
    [ev] = _events(project, "policy_changed")
    assert ev["actor"] == "runtime:init" and ev["data"]["before"] is None and ev["data"]["decision_id"] is None
    out = cli.run("policy")
    assert out["state"] == "recorded" and "unconfirmed" not in out and out["sha256"] == ev["data"]["sha256"]
    assert _rule(out, "permissions.deploy") == {"key": "permissions.deploy", "value": "deny", "decision_id": None,
                                                "actor": "runtime:init", "at": ev["ts"]}
    assert not [i for i in cli("check", expect=None).payload["issues"] if i["code"].startswith("policy.")]
    assert (project / ".baton" / "project" / "cas").is_dir()  # the recorded value is a project blob


@pytest.mark.slow
def test_policy_set_records_the_decision_writes_the_file_and_commits(tmp_path):
    cli, project = _project(tmp_path)
    out = cli.run("policy", "set", "--floor", "axes.assurance=medium", "--governing", "software development=axes",
                  "--permission", "tag=allow", "--permission", "push.other=deny", "--note", NOTE)
    did = out["decision_id"]
    assert {c["key"] for c in out["changes"]} == {"floors.axes.assurance", "governing.software development",
                                                  "permissions.tag", "permissions.push.other"}
    assert _rule(out, "permissions.tag")["decision_id"] == did and _rule(out, "permissions.deploy")["decision_id"] is None
    [decision] = [e for e in _events(project, "human_decision") if e["data"].get("kind") == "policy"]
    assert decision["actor"] == "human" and decision["data"]["note"] == NOTE and decision["data"]["decision"] == "set"
    changed = _events(project, "policy_changed")[-1]
    assert changed["data"]["decision_id"] == did and changed["data"]["before"]["permissions"]["tag"] == "ask"
    assert changed["data"]["after"]["floors"] == {"axes": {"assurance": "medium"}}
    cfg = _yaml(project)
    assert cfg["policy"] == {"floors": {"axes": {"assurance": "medium"}}, "governing": [{"work": "software development", "recipe": "axes"}]}
    assert cfg["permissions"]["tag"] == "allow" and cfg["permissions"]["push"]["other"] == "deny"
    assert out["checkpoint"]["committed"] and git(project, "status", "--porcelain").strip() == ""
    assert ".baton/project.yaml" in git(project, "show", "--name-only", "--format=", "HEAD")
    assert cli.run("policy")["state"] == "recorded"
    # The new permission is the one enforced.
    assert cli.run("permission", "tag", "--detail", "tag v1")["permission"] == "allow"
    # Removing.
    out = cli.run("policy", "set", "--remove-floor", "axes.assurance", "--remove-governing", "Software Development", "--note", NOTE)
    assert _yaml(project)["policy"] == {"floors": {}, "governing": []}
    assert not [r for r in out["rules"] if r["key"].startswith(("floors.", "governing."))]


@pytest.mark.slow
def test_policy_set_refusals(tmp_path):
    cli, project = _project(tmp_path)
    assert cli("policy", "set", "--permission", "tag=allow", "--note", " ", expect=1).payload["error"] == "policy.note"
    assert cli("policy", "set", "--note", NOTE, expect=2).payload["error"] == "usage.policy"
    assert cli("policy", "set", "--floor", "assurance=high", "--note", NOTE, expect=2).payload["error"] == "usage.policy"
    res = cli("policy", "set", "--floor", "axes.speed=high", "--note", NOTE, expect=1).payload
    assert res["error"] == "policy.invalid" and "no axis 'speed'" in res["message"]
    res = cli("policy", "set", "--floor", "axes.assurance=extreme", "--note", NOTE, expect=1).payload
    assert res["error"] == "policy.invalid" and "no value 'extreme'" in res["message"]
    res = cli("policy", "set", "--floor", "nowhere.level=major", "--note", NOTE, expect=1).payload
    assert res["error"] == "policy.invalid" and "no recipe nowhere" in res["message"]
    res = cli("policy", "set", "--governing", "gardening=nowhere", "--note", NOTE, expect=1).payload
    assert res["error"] == "policy.invalid" and "no recipe nowhere" in res["message"]
    assert cli("policy", "set", "--permission", "tag=ask", "--note", NOTE, expect=1).payload["error"] == "policy.unchanged"
    assert cli("policy", "set", "--permission", "launch=allow", "--note", NOTE, expect=1).payload["error"] == "policy.unknown_permission"
    assert len(_events(project, "policy_changed")) == 1  # only init's


@pytest.mark.slow
def test_floors_on_a_catalog_recipe_a_one_axis_recipe_and_every_recipe(tmp_path):
    cli, project = _project(tmp_path)
    # software-feature is in the catalog, not vendored: one axis, `level`.
    cli.run("policy", "set", "--floor", "software-feature.level=standard", "--note", NOTE)
    assert cli("policy", "set", "--floor", "software-feature.assurance=high", "--note", NOTE, expect=1).payload["error"] == "policy.invalid"
    out = cli.run("policy", "set", "--floor", "*.assurance=medium", "--note", NOTE)
    assert "warnings" not in out
    out = cli.run("policy", "set", "--floor", "*.release=low", "--note", NOTE)
    assert out["warnings"] == ["the floor release low for every recipe matches no vendored recipe (none declares release with low)"]
    [issue] = [i for i in cli("check", expect=None).payload["issues"] if i["code"].startswith("policy.")]
    assert issue["code"] == "policy.floor" and issue["severity"] == "warning" and "release low" in issue["message"]


# -- hand edits -------------------------------------------------------------------------


@pytest.mark.slow
def test_a_hand_edit_is_noticed_and_not_enforced_until_confirmed(tmp_path):
    cli, project = _project(tmp_path)
    _hand_edit(project, lambda c: c["permissions"].update(tag="allow"))
    out = cli.run("policy")
    assert out["state"] == "edited" and out["policy"]["permissions"]["tag"] == "ask"
    assert out["unconfirmed"]["differences"] == [{"key": "permissions.tag", "before": "ask", "after": "allow"}]
    issues = cli("check", expect=0).payload["issues"]
    assert [(i["code"], i["severity"]) for i in issues if i["code"].startswith("policy.")] == [("policy.unconfirmed", "warning")]
    strict = cli("check", "--strict", expect=1).payload["issues"]
    assert [(i["code"], i["severity"]) for i in strict if i["code"].startswith("policy.")] == [("policy.unconfirmed", "error")]
    board = cli.run("board")
    assert board["policy"]["state"] == "edited" and "policy confirm" in board["policy"]["next"]
    run = cli.run("start", "axes", "--title", "Fix", "--inputs", json.dumps({"title": "Fix"}))["run_id"]
    assert cli.run("status", run)["policy"]["state"] == "edited"
    # The recorded rule (ask) is enforced, not the file's (allow).
    assert cli.run("permission", "tag", "--detail", "tag v1", expect=4)["permission"] == "ask"
    # No change on top of an unconfirmed edit.
    assert cli("policy", "set", "--permission", "merge=ask", "--note", NOTE, expect=1).payload["error"] == "policy.unconfirmed_edit"
    out = cli.run("policy", "confirm", "--note", "Yes, tagging without asking is fine.")
    assert out["state"] == "recorded" and _rule(out, "permissions.tag")["decision_id"] == out["decision_id"]
    changed = _events(project, "policy_changed")[-1]["data"]
    assert changed["before"]["permissions"]["tag"] == "ask" and changed["after"]["permissions"]["tag"] == "allow"
    assert out["checkpoint"]["committed"] and git(project, "status", "--porcelain", ".baton/project.yaml", ".baton/project").strip() == ""
    assert "policy" not in cli.run("board") and "policy" not in cli.run("status", run)
    assert cli.run("permission", "tag", "--detail", "tag v1")["permission"] == "allow"
    assert cli("policy", "confirm", "--note", NOTE, expect=1).payload["error"] == "policy.nothing_to_confirm"


@pytest.mark.slow
def test_confirming_a_hand_edit_checks_its_floors(tmp_path):
    cli, project = _project(tmp_path)
    _hand_edit(project, lambda c: c["policy"]["floors"].update(axes={"speed": "high"}))
    res = cli("policy", "confirm", "--note", NOTE, expect=1).payload
    assert res["error"] == "policy.invalid" and "no axis 'speed'" in res["message"]
    # check judges the floors in force (the recorded ones); the edit itself is reported as unconfirmed.
    assert [i["code"] for i in cli("check", expect=None).payload["issues"] if i["code"].startswith("policy.")] == ["policy.unconfirmed"]
    assert len(_events(project, "policy_changed")) == 1


# -- a project with no record (0153) ---------------------------------------------------------

OLD_YAML = """\
paths: { process_plans: docs, notes: docs }
permissions:
  push: { docs_only: allow, after_verified: allow, other: ask }
  tag: ask
  merge: allow
"""


@pytest.mark.slow
def test_a_project_with_no_record_keeps_its_file_in_force_and_is_asked_once(tmp_path):
    cli, project = _project(tmp_path, axes=False, yaml_text=OLD_YAML)
    assert _events(project, "policy_changed") == []
    out = cli.run("policy")
    assert out["state"] == "unrecorded" and out["unconfirmed"]["state"] == "unrecorded"
    assert _rule(out, "permissions.merge") == {"key": "permissions.merge", "value": "allow", "decision_id": None, "actor": None, "at": None}
    assert cli.run("permission", "merge", "--detail", "merge feature")["permission"] == "allow"  # the file is in force
    issues = cli("check", expect=0).payload["issues"]
    assert [(i["code"], i["severity"]) for i in issues if i["code"].startswith("policy.")] == [("policy.unrecorded", "warning")]
    assert cli.run("board")["policy"]["state"] == "unrecorded"
    out = cli.run("policy", "confirm", "--note", "Those are right.")
    assert out["state"] == "recorded" and _events(project, "policy_changed")[0]["data"]["before"] is None
    assert not [i for i in cli("check", expect=0).payload["issues"] if i["code"].startswith("policy.")]


@pytest.mark.slow
def test_a_first_change_on_a_project_with_no_record_records_it(tmp_path):
    cli, project = _project(tmp_path, axes=False, yaml_text=OLD_YAML)
    out = cli.run("policy", "set", "--permission", "merge=ask", "--note", NOTE)
    assert out["state"] == "recorded" and _yaml(project)["permissions"]["merge"] == "ask"
    [changed] = _events(project, "policy_changed")
    assert changed["data"]["before"]["permissions"]["merge"] == "allow"
    assert _yaml(project)["paths"] == {"process_plans": "docs", "notes": "docs"}


# -- MCP ---------------------------------------------------------------------------------


@pytest.mark.slow
def test_mcp_policy_tools(tmp_path, monkeypatch):
    from mcp import Client

    cli, project = _project(tmp_path)
    monkeypatch.setenv("BATON_HOME", str(cli.home))

    async def main() -> tuple[dict, dict]:
        async with Client(build_server(project)) as c:
            set_ = await c.call_tool("policy_set", {"note": NOTE, "floors": {"axes": {"discovery": "medium"}},
                                                    "permissions": {"push.docs_only": "ask"}})
            listed = await c.call_tool("policy", {})
            return set_.structured_content, listed.structured_content

    set_, listed = asyncio.run(main())
    assert {c["key"] for c in set_["changes"]} == {"floors.axes.discovery", "permissions.push.docs_only"}
    assert listed["policy"]["floors"] == {"axes": {"discovery": "medium"}} and listed["state"] == "recorded"


# -- floors and pinning (Slice 2) -----------------------------------------------------------

from projectkit import packet_dir, write_result  # noqa: E402
from test_tailoring_axes import rate  # noqa: E402


def _run_events(project: Path, run: str, etype: str | None = None) -> list[dict]:
    f = project / ".baton" / "runs" / run / "events.jsonl"
    evs = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    return [e for e in evs if etype is None or e["type"] == etype]


def _triage(cli: Cli, project: Path, run: str, output: dict, expect: int = 4) -> dict:
    d = cli.run("dispatch", run, "triage", "--worker", "owner")
    write_result(packet_dir(project, run, "triage", d["attempt"]), output)
    return cli.run("submit", run, "triage", expect=expect)


def _start(cli: Cli, recipe: str = "axes") -> str:
    return cli.run("start", recipe, "--title", "Fix", "--inputs", json.dumps({"title": "Fix"}))["run_id"]


def _prompt(cli: Cli, run: str) -> str:
    return next(d for d in cli.run("status", run, expect=4)["pending_decisions"] if d["ref"] == "triage")["prompt"]


@pytest.mark.slow
def test_a_rating_below_a_floor_is_raised_recorded_and_named_to_the_owner(tmp_path):
    cli, project = _project(tmp_path)
    did = cli.run("policy", "set", "--floor", "axes.assurance=medium", "--note", NOTE)["decision_id"]
    run = _start(cli)
    started = _run_events(project, run, "run_started")[0]["data"]
    assert started["policy_sha256"] == cli.run("policy")["sha256"]
    _triage(cli, project, run, rate(discovery="medium", assurance="low"))
    prompt = _prompt(cli, run)
    assert "assurance medium (assurance is low here)" in prompt
    assert f"Project policy raised assurance from low to medium (decision {did})." in prompt
    cli.run("decide", run, "triage", "approve", "--note", "fine")
    [cs] = _run_events(project, run, "complexity_set")
    assert cs["data"]["ratings"] == {"discovery": "medium", "assurance": "medium"}
    assert cs["data"]["floors_applied"] == [{"axis": "assurance", "rated": "low", "floor": "medium", "decision_id": did}]
    assert cs["data"]["policy_sha256"] == started["policy_sha256"]
    assert cli.run("status", run)["steps"]["verify"]["state"] != "skipped"  # verify runs at assurance medium


@pytest.mark.slow
def test_all_lowest_with_a_floor_waits_on_the_owner(tmp_path):
    cli, project = _project(tmp_path)
    cli.run("policy", "set", "--floor", "*.discovery=medium", "--note", NOTE)
    run = _start(cli)
    # assurance asks at its lowest anyway (confirm_lowest); the floor is on discovery.
    out = _triage(cli, project, run, rate(discovery="low", assurance="low"))
    assert out["needs_owner"]
    assert "Project policy raised discovery from low to medium" in _prompt(cli, run)


@pytest.mark.slow
def test_floors_never_lower_and_a_run_keeps_the_policy_pinned_at_its_start(tmp_path):
    cli, project = _project(tmp_path)
    run = _start(cli)  # pinned before any floor
    cli.run("policy", "set", "--floor", "axes.assurance=high", "--note", NOTE)
    st = cli.run("status", run)
    assert st["policy_outdated"]["pinned"] != st["policy_outdated"]["current"]
    [row] = cli.run("board")["runs"]
    assert row["policy_outdated"] is True
    _triage(cli, project, run, rate(discovery="low", assurance="medium"))
    assert "Project policy" not in _prompt(cli, run)  # the pinned policy has no floor
    cli.run("decide", run, "triage", "approve", "--note", "fine")
    [cs] = _run_events(project, run, "complexity_set")
    assert cs["data"]["ratings"]["assurance"] == "medium" and "floors_applied" not in cs["data"]
    # A run started now is under the current policy and is not reported.
    run2 = _start(cli)
    assert "policy_outdated" not in cli.run("status", run2)
    _triage(cli, project, run2, rate(discovery="high", assurance="high"))
    assert "Project policy" not in _prompt(cli, run2)  # already at the floor: nothing raised


@pytest.mark.slow
def test_retriage_applies_the_current_policy_and_records_its_hash(tmp_path):
    cli, project = _project(tmp_path)
    run = _start(cli)
    _triage(cli, project, run, rate(discovery="low", assurance="medium"))
    cli.run("decide", run, "triage", "approve", "--note", "fine")
    did = cli.run("policy", "set", "--floor", "axes.discovery=high", "--note", NOTE)["decision_id"]
    current = cli.run("policy")["sha256"]
    cli.run("retriage", run, "--reason", "scope grew", "--axis", "assurance")
    _triage(cli, project, run, rate(discovery="low", assurance="medium"))
    prompt = _prompt(cli, run)
    assert "change discovery from low to high" in prompt and f"Project policy raised discovery from low to high (decision {did})." in prompt
    cli.run("decide", run, "triage", "approve", "--note", "yes")
    [ra] = _run_events(project, run, "retriage_applied")
    assert ra["data"]["ratings"] == {"discovery": "high", "assurance": "medium"}
    assert ra["data"]["policy_sha256"] == current
    assert ra["data"]["floors_applied"] == [{"axis": "discovery", "rated": "low", "floor": "high", "decision_id": did}]
    assert "policy_outdated" not in cli.run("status", run)  # re-triage brought it under the current policy


@pytest.mark.slow
def test_a_floor_on_a_one_axis_recipe_uses_level(tmp_path):
    from test_tailoring import tailor_recipe

    cli, project = _project(tmp_path, axes=False)
    cli.run("vendor", str(tailor_recipe(tmp_path / "toy")))
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Vendor toy")
    assert cli("policy", "set", "--floor", "tailor.assurance=high", "--note", NOTE, expect=1).payload["error"] == "policy.invalid"
    did = cli.run("policy", "set", "--floor", "tailor.level=standard", "--note", NOTE)["decision_id"]
    run = cli.run("start", "tailor", "--title", "Garden", "--inputs", json.dumps({"title": "Garden"}))["run_id"]
    _triage(cli, project, run, {"level": "minor", "reasons": ["small"]})
    prompt = _prompt(cli, run)
    assert prompt.startswith("Triage rated this work 'minor'") and "Approve level 'standard'?" in prompt
    assert f"Project policy raised level from minor to standard (decision {did})." in prompt
    cli.run("decide", run, "triage", "approve", "--note", "ok")
    [cs] = _run_events(project, run, "complexity_set")
    assert cs["data"]["level"] == "standard"
    assert cs["data"]["floors_applied"] == [{"axis": "level", "rated": "minor", "floor": "standard", "decision_id": did}]


@pytest.mark.slow
def test_a_star_floor_applies_only_to_recipes_that_declare_the_axis_and_value(tmp_path):
    from test_tailoring import tailor_recipe

    cli, project = _project(tmp_path)
    cli.run("vendor", str(tailor_recipe(tmp_path / "toy")))
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Vendor toy")
    cli.run("policy", "set", "--floor", "*.assurance=medium", "--note", NOTE)
    toy = cli.run("start", "tailor", "--title", "Garden", "--inputs", json.dumps({"title": "Garden"}))["run_id"]
    out = _triage(cli, project, toy, {"level": "minor", "reasons": ["small"]}, expect=0)
    assert out["outcome"] == "passed"  # toy has no assurance axis: auto-approved as before
    [cs] = _run_events(project, toy, "complexity_set")
    assert cs["data"]["level"] == "minor" and "floors_applied" not in cs["data"]
    axes = _start(cli)
    _triage(cli, project, axes, rate(discovery="low", assurance="low"))
    assert "Project policy raised assurance from low to medium" in _prompt(cli, axes)


@pytest.mark.slow
def test_an_adoption_baseline_carries_ratings_raised_to_the_floors(tmp_path):
    from projectkit import make_home as home

    from test_adoption import PERSON

    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, home(tmp_path / "home", PERSON))
    git(project, "commit", "-q", "--allow-empty", "-m", "Prior work")
    adoption = cli.run("adopt", str(write_recipe(tmp_path / "axes")))["adoption"]
    did = cli.run("policy", "set", "--floor", "axes.assurance=medium", "--note", NOTE)["decision_id"]

    def play(run: str, step: str, output: dict) -> dict:
        d = cli.run("dispatch", run, step, "--worker", "owner")
        write_result(packet_dir(project, run, step, d["attempt"]), output)
        return cli.run("submit", run, step)

    play(adoption, "research", {
        "evidence": [], "proposed_seeds": [], "agent_config": [], "path_candidates": {}, "command_candidates": {}, "gaps": [],
        "work_items": [{"key": "fix", "title": "Tenant fix", "status": "in_flight", "position": "not started", "inputs": {"title": "Tenant fix"}}],
    })
    (run,) = [v["run_id"] for v in cli.run("adopt", "axes")["runs"].values()]
    play(run, "triage", rate(discovery="low", assurance="low"))
    cli.run("adopt", "axes", expect=4)
    bpath = project / ".baton" / "adoption" / adoption / "baseline.yaml"
    text = bpath.read_text(encoding="utf-8")
    assert "was raised by the project's policy" in text
    doc = yaml.safe_load(text)
    (item,) = doc["work_items"]
    assert item["ratings"] == {"discovery": "low", "assurance": "medium"}
    assert item["floors_applied"] == [{"axis": "assurance", "rated": "low", "floor": "medium", "decision_id": did}]
    assert "verify" not in item["plan"]["skip"]
    header = text[: text.index("format:")]
    item["ratings"]["assurance"] = "low"  # the owner cannot edit below the floor
    bpath.write_text(header + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    bad = cli.run("establish-baseline", adoption, "--note", "go", expect=None)
    assert "assurance low is below the project's floor medium" in json.dumps(bad)
    item["ratings"]["assurance"] = "medium"
    bpath.write_text(header + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    cli.run("establish-baseline", adoption, "--note", "fine")
    [cs] = _run_events(project, run, "complexity_set")
    assert cs["data"]["ratings"] == {"discovery": "low", "assurance": "medium"} and cs["data"]["approval"] == "baseline"
    assert cs["data"]["floors_applied"] == [{"axis": "assurance", "rated": "low", "floor": "medium", "decision_id": did}]


# -- governing recipes and project.policy (Slice 3) ---------------------------------------------

from runkit import make_recipe  # noqa: E402

OBJ = {"type": "object"}


def _readers(tmp_path: Path) -> tuple[Path, Path]:
    """``release`` reads the policy and the catalog; ``plain`` declares neither."""
    release = make_recipe(tmp_path / "release", [{"id": "ship", "output_schema": "schemas/out.json", "inputs": [
        {"name": "rules", "from": "project.policy", "required": True}, {"name": "recipes", "from": "catalog.summaries"}]}],
        schemas={"out.json": OBJ}, id="release")
    plain = make_recipe(tmp_path / "plain", [{"id": "work", "output_schema": "schemas/out.json"}], schemas={"out.json": OBJ}, id="plain")
    return release, plain


@pytest.mark.slow
def test_governing_recipes_are_marked_in_recipes_and_catalog_summaries(tmp_path):
    cli, project = _project(tmp_path)
    release, plain = _readers(tmp_path)
    cli.run("vendor", str(release))
    cli.run("vendor", str(plain))
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Vendor")
    cli.run("policy", "set", "--governing", "software development=axes", "--governing", "bug fixes=axes",
            "--governing", "web features=software-feature", "--note", NOTE)
    out = cli.run("recipes")
    rows = {r["recipe"]: r for r in out["recipes"]}
    assert rows["axes@1"]["governs"] == ["software development", "bug fixes"] and "governs" not in rows["plain@1"]
    assert out["governing"] == [{"work": "web features", "recipe": "software-feature"}]  # in the catalog, not vendored
    run = cli.run("start", "release", "--inputs", json.dumps({"title": "v1"}))["run_id"]
    d = cli.run("dispatch", run, "ship", "--worker", "owner")
    pdir = packet_dir(project, run, "ship", d["attempt"])
    listing = {r["id"]: r for r in json.loads((pdir / "inputs" / "recipes.json").read_text(encoding="utf-8"))}
    assert listing["axes"]["governs"] == ["software development", "bug fixes"]
    assert listing["software-feature"]["governs"] == ["web features"] and "governs" not in listing["plain"]
    rules = json.loads((pdir / "inputs" / "rules.json").read_text(encoding="utf-8"))
    pinned = _run_events(project, run, "run_started")[0]["data"]["policy_sha256"]
    assert rules["sha256"] == pinned and rules["permissions"]["deploy"] == "deny"
    assert rules["governing"][0] == {"work": "software development", "recipe": "axes"}
    # A step that does not declare project.policy gets no policy in its packet.
    run2 = cli.run("start", "plain", "--inputs", json.dumps({"title": "x"}))["run_id"]
    d = cli.run("dispatch", run2, "work", "--worker", "owner")
    pdir2 = packet_dir(project, run2, "work", d["attempt"])
    manifest = json.loads((pdir2 / "manifest.json").read_text(encoding="utf-8"))
    assert not (pdir2 / "inputs").exists() or not list((pdir2 / "inputs").iterdir())
    assert "policy" not in json.dumps(manifest.get("inputs") or {})


@pytest.mark.not_slow("loads a recipe")
def test_project_policy_is_its_own_reference_and_policy_is_not_a_role_name(tmp_path):
    from baton import refs
    from baton.recipe import RecipeError, load_recipe

    assert refs.parse("project.policy").kind == "policy" and refs.parse("project.brief").kind == "project"
    root = make_recipe(tmp_path / "r", [{"id": "s", "output_schema": "schemas/out.json"}], schemas={"out.json": OBJ},
                       project_inputs=[{"role": "policy", "description": "the rules"}])
    with pytest.raises(RecipeError) as e:
        load_recipe(root)
    assert "project_inputs.reserved_role" in str(e.value)
