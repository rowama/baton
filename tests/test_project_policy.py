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
