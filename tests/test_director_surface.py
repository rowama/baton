"""Phase 14: the Director surface — action permissions, skills and the communication default, explain, MCP (§13)."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from baton import data
from baton.adopt import AGENTS_POINTER
from baton.mcp_server import build_server, check_loopback, http_token
from baton.packet import EngineError

from conftest import FIT_CHECK, ROOT
from projectkit import (
    FIT_INPUTS, GOOD_PROFILE, OWNER_PROFILE, VERDICT, Cli, git, make_git_project, make_home, packet_dir, setup_fit_check, write_result,
)

GOLDEN = Path(__file__).parent / "golden"
STEP_WORKER = Path(__file__).parent / "fakes" / "step_worker.py"
FIT_CAPS = ["structured_output", "long_form_writing", "technical_reasoning"]


def project_events(project: Path) -> list[dict]:
    f = project / ".baton" / "project" / "events.jsonl"
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def run_events(project: Path, run: str) -> list[dict]:
    f = project / ".baton" / "runs" / run / "events.jsonl"
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]


def set_config(project: Path, **changes: object) -> None:
    py = project / ".baton" / "project.yaml"
    cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            for k, v in value.items():
                if isinstance(v, dict) and isinstance(cfg[key].get(k), dict):
                    cfg[key][k].update(v)
                else:
                    cfg[key][k] = v
        else:
            cfg[key] = value
    py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def commit_file(project: Path, rel: str, text: str = "x\n", message: str | None = None) -> str:
    p = project / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(project, "add", rel)
    git(project, "commit", "-q", "-m", message or f"Change {rel}")
    return git(project, "rev-parse", "HEAD").strip()


def with_remote(tmp_path: Path, project: Path) -> Path:
    """A bare remote ``origin`` holding the project's current commits, with ``main`` tracking it."""
    git(project, "add", "-A")
    if git(project, "status", "--porcelain").strip():
        git(project, "commit", "-q", "-m", "Configure")
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    git(project, "remote", "add", "origin", str(bare))
    git(project, "push", "-q", "-u", "origin", "main")
    return bare


def remote_head(bare: Path, branch: str = "main") -> str:
    return git(bare, "rev-parse", branch).strip()


def head(project: Path) -> str:
    return git(project, "rev-parse", "HEAD").strip()


# ---------------------------------------------------------------------------
# Action permissions (§13.7)
# ---------------------------------------------------------------------------


def test_default_permissions_in_project_yaml(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    cfg = yaml.safe_load((project / ".baton" / "project.yaml").read_text(encoding="utf-8"))
    assert cfg["permissions"] == {"push": {"docs_only": "allow", "after_verified": "allow", "other": "ask"},
                                  "tag": "ask", "force_push": "deny", "merge": "deny", "deploy": "deny"}
    assert ".baton/project/**" in cfg["docs_only_globs"] and "**/*.md" in cfg["docs_only_globs"]


def test_docs_only_push_is_allowed_and_recorded(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    bare = with_remote(tmp_path, project)
    docs = commit_file(project, "docs/notes.md", "# Notes\n")
    out = cli.run("push")
    assert out["granted"] and out["pushed"] and out["permission"] == "allow"
    assert out["category"] == "docs_only" and out["commits"] == [docs]
    assert remote_head(bare) == head(project)  # the permission record was committed first and travelled with the push
    used = [e for e in project_events(project) if e["type"] == "permission_used"]
    assert len(used) == 1 and used[0]["data"]["action"] == "push" and used[0]["data"]["category"] == "docs_only"
    assert used[0]["data"]["commits"] == [docs] and used[0]["actor"] == "director:alice@host1"
    assert git(project, "log", "-1", "--format=%s").strip() == "baton(project): permission used: push (docs-only)"
    assert cli.run("push")["reason"] == "nothing to push"


def test_denied_push_is_refused_and_never_attempted(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    set_config(project, permissions={"push": {"other": "deny"}})
    bare = with_remote(tmp_path, project)
    before = remote_head(bare)
    commit_file(project, "src/app.py", "print('hi')\n")
    res = cli("push", expect=1)
    assert res.payload["error"] == "permission.denied"
    assert remote_head(bare) == before
    assert not [e for e in project_events(project) if e["type"].startswith("permission_")]


def test_ask_push_waits_for_the_owners_words(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    bare = with_remote(tmp_path, project)
    before = remote_head(bare)
    code = commit_file(project, "src/app.py", "print('hi')\n")
    out = cli.run("push", expect=4)
    assert not out["granted"] and out["needs_owner"] and out["category"] == "other" and out["unverified"] == [code]
    assert remote_head(bare) == before
    requested = [e for e in project_events(project) if e["type"] == "permission_requested"]
    assert len(requested) == 1 and requested[0]["data"]["category"] == "other"
    assert cli("push", "--approved", expect=1).payload["error"] == "permission.note"
    out = cli.run("push", "--approved", "--note", "Yes, ship the greeting.")
    assert out["granted"] and out["pushed"] and out["permission"] == "approved"
    assert remote_head(bare) == head(project)
    evs = project_events(project)
    decision = next(e for e in evs if e["type"] == "human_decision")
    assert decision["actor"] == "human" and decision["data"]["kind"] == "permission"
    assert decision["data"]["note"] == "Yes, ship the greeting." and decision["data"]["decision_id"] == out["decision_id"]
    used = [e for e in evs if e["type"] == "permission_used"]
    assert len(used) == 1 and used[0]["data"]["decision_id"] == out["decision_id"] and used[0]["seq"] > decision["seq"]


VERIFY_RECIPE = {
    "id": "change", "version": 1, "format": "baton-recipe/1", "capabilities_vocab": "baton-capabilities/1",
    "run_inputs": {"schema": "schemas/in.json"},
    "steps": [{"id": "implement", "title": "Make the change", "requires": {"capabilities": ["file_write"]}, "prompt": "prompts/p.md",
               "inputs": [{"name": "title", "from": "run.inputs.title", "required": True}],
               "output_schema": "schemas/out.json", "gates": [{"type": "schema"}]}],
}


def _verify_recipe(root: Path) -> Path:
    (root / "schemas").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "recipe.yaml").write_text(yaml.safe_dump(VERIFY_RECIPE, sort_keys=False), encoding="utf-8")
    (root / "prompts" / "p.md").write_text("Make the change and commit it.\n", encoding="utf-8")
    (root / "schemas" / "in.json").write_text(json.dumps({"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}}))
    (root / "schemas" / "out.json").write_text(json.dumps({"type": "object", "required": ["commit_sha"], "properties": {"commit_sha": {"type": "string"}}}))
    return root


def test_after_verified_push_covers_passed_steps_commits_only(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    cli.run("vendor", str(_verify_recipe(tmp_path / "change")))
    set_config(project, permissions={"push": {"other": "deny"}})
    bare = with_remote(tmp_path, project)
    code = commit_file(project, "src/app.py", "print('hi')\n")
    run = cli.run("start", "change", "--inputs", json.dumps({"title": "Greeting"}))["run_id"]
    cli.run("dispatch", run, "implement", "--worker", "owner")
    write_result(packet_dir(project, run, "implement", 1), {"commit_sha": code[:12]})  # a short sha resolves too
    assert cli.run("submit", run, "implement")["outcome"] == "passed"
    out = cli.run("push")
    assert out["category"] == "after_verified" and out["pushed"] and "src/app.py" in out["outside_docs"]
    assert remote_head(bare) == head(project)
    stray = commit_file(project, "src/other.py", "x = 1\n")
    res = cli("push", expect=1)
    assert res.payload["error"] == "permission.denied" and "push (other)" in res.payload["message"]
    assert remote_head(bare) != head(project) and stray


def test_docs_only_globs_are_the_projects(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    set_config(project, docs_only_globs=["notes/**"], permissions={"push": {"other": "deny"}})
    with_remote(tmp_path, project)
    commit_file(project, "docs/guide.md", "# Guide\n")
    assert cli("push", expect=1).payload["error"] == "permission.denied"  # docs/ is not docs-only here
    git(project, "reset", "-q", "--hard", "HEAD~1")
    commit_file(project, "notes/today.txt", "plans\n")
    assert cli.run("push")["category"] == "docs_only"


def test_push_of_a_new_branch_sets_its_upstream(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    bare = with_remote(tmp_path, project)
    git(project, "checkout", "-q", "-b", "notes")
    commit_file(project, "docs/a.md")
    out = cli.run("push")
    assert out["upstream"] is None and out["branch"] == "notes" and out["pushed"]
    assert remote_head(bare, "notes") == head(project)
    assert git(project, "rev-parse", "--abbrev-ref", "notes@{u}").strip() == "origin/notes"
    assert cli.run("push")["reason"] == "nothing to push"


def test_push_without_a_remote_is_a_problem(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    commit_file(project, "docs/a.md")
    assert cli("push", expect=1).payload["error"] == "push.git"


def test_director_actions_outside_the_runtime(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    out = cli.run("permission", "tag", "--detail", "tag v1.0 on main", expect=4)
    assert out["permission"] == "ask" and not out["granted"]
    out = cli.run("permission", "tag", "--detail", "tag v1.0 on main", "--approved", "--note", "Go ahead and tag it.")
    assert out["granted"] and out["permission"] == "approved"
    assert cli("permission", "deploy", expect=1).payload["error"] == "permission.denied"
    assert cli("permission", "force-push", expect=1).payload["error"] == "permission.denied"
    assert cli("permission", "push", expect=1).payload["error"] == "permission.use_push"
    assert cli("permission", "launch", expect=1).payload["error"] == "permission.unknown_action"
    set_config(project, permissions={"merge": "allow"})
    assert cli.run("permission", "merge", "--detail", "merge feature into main")["permission"] == "allow"
    evs = [e for e in project_events(project) if e["type"] in ("permission_requested", "permission_used", "human_decision")]
    assert [(e["type"], e["data"]["action"]) for e in evs] == [
        ("permission_requested", "tag"), ("human_decision", "tag"), ("permission_used", "tag"), ("permission_used", "merge")]
    assert evs[0]["data"]["detail"] == "tag v1.0 on main" and evs[1]["data"]["note"] == "Go ahead and tag it."
    assert cli("check").exit_code == 0


# ---------------------------------------------------------------------------
# Skills, the AGENTS.md pointer and the communication contract (§4.3, §13.3, §13.6)
# ---------------------------------------------------------------------------


def test_init_vendors_skills_pointer_and_communication_default(tmp_path):
    project = make_git_project(tmp_path / "p")
    cli = Cli(project, make_home(tmp_path / "home"))
    out = cli.run("init", str(project))
    for name in ("baton-director", "baton-worker"):
        vendored = project / ".agents" / "skills" / name / "SKILL.md"
        shipped = data.path("skills") / name / "SKILL.md"
        assert vendored.read_bytes() == shipped.read_bytes()
        front = yaml.safe_load(vendored.read_text(encoding="utf-8").split("---")[1])
        assert front["name"] == name and front["description"]
        assert f".agents/skills/{name}/SKILL.md" in out["created"]
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_POINTER + "\n"
    assert (project / ".baton" / "communication.md").read_bytes() == (data.path("defaults") / "communication.md").read_bytes()
    (project / ".agents" / "skills" / "baton-worker" / "SKILL.md").write_text("edited\n", encoding="utf-8")
    again = cli.run("init", str(project))
    assert again["created"] == [] and (project / ".agents" / "skills" / "baton-worker" / "SKILL.md").read_text() == "edited\n"


def test_init_appends_the_pointer_to_an_existing_agents_md_once(tmp_path):
    project = make_git_project(tmp_path / "p")
    (project / "AGENTS.md").write_text("# Agents\nBe kind.", encoding="utf-8")
    cli = Cli(project, make_home(tmp_path / "home"))
    assert "AGENTS.md (pointer appended)" in cli.run("init", str(project))["created"]
    cli.run("init", str(project))
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == f"# Agents\nBe kind.\n{AGENTS_POINTER}\n"


def test_adopt_leaves_agents_md_to_the_baseline(tmp_path):
    project = make_git_project(tmp_path / "p")
    (project / "README.md").write_text("hello\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "start")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli("adopt", str(FIT_CHECK), expect=None)
    assert (project / ".agents" / "skills" / "baton-director" / "SKILL.md").is_file()
    assert not (project / "AGENTS.md").exists()


def test_director_skill_names_every_call_it_relies_on():
    text = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    for call in ("detect", "doctor", "board", "resume", "status", "eligible", "dispatch", "wait", "submit", "decide", "explain",
                 "ask_sme", "sme-handoff", "sme-followup", "feedback", "push", "permission", "revise", "retriage", "summary"):
        assert f"`{call}" in text, call
    assert "Follow `.baton/communication.md` exactly." in text


# ---------------------------------------------------------------------------
# explain (§10.6)
# ---------------------------------------------------------------------------


def _golden(name: str, text: str) -> None:
    golden = GOLDEN / name
    if os.environ.get("BATON_UPDATE_GOLDEN"):
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert text == golden.read_text(encoding="utf-8"), f"{name} differs; BATON_UPDATE_GOLDEN=1 rewrites it"


def test_explain_gives_process_facts_only(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    out = cli.run("explain", run)
    assert out["position"]["ready"] == ["describe"] and [r["step"] for r in out["remaining"]] == ["describe", "assess"]
    cli.run("dispatch", run, "describe", "--worker", "owner")
    write_result(packet_dir(project, run, "describe", 1), GOOD_PROFILE)
    cli.run("submit", run, "describe")
    out = cli.run("explain", run)
    assert out["done"]["passed"] == [{"step": "describe", "title": "Profile the idea"}]
    assert out["branches"] == ["assess: the owner approves or rejects (a rejection sends it back for another attempt)"]
    blob = json.dumps(out)
    assert GOOD_PROFILE["summary"] not in blob and FIT_INPUTS["idea"] not in blob  # no subject matter
    _golden("fit-check-explain.txt", out["text"].replace(run, "<run>") + "\n")


def test_explain_shows_levels(tmp_path):
    from test_backyard import do as yard_do, setup as yard_setup

    cli, project = yard_setup(tmp_path)
    run = cli.run("start", "backyard-project", "--inputs", json.dumps({"title": "Bed", "description": "Plant perennials"}))["run_id"]
    out = cli.run("explain", run)
    assert out["level"] is None and "The level is not set yet; what remains depends on triage." in out["text"]
    yard_do(cli, project, run, "triage", {"level": "minor", "reasons": ["planting only"]})
    out = cli.run("explain", run)
    assert out["level"] == "minor" and out["done"]["skipped"] and out["other_levels"]["major"]["adds"]
    assert "At major: adds " in out["text"]


# ---------------------------------------------------------------------------
# MCP (§13.2)
# ---------------------------------------------------------------------------

API_CALLS = {
    "detect", "board", "recipes", "plan", "start", "status", "explain", "eligible", "dispatch", "cancel", "wait", "submit", "decide",
    "retry", "retriage", "revise", "disposition", "waive", "ingest_revision", "ask_sme", "sme_followup", "sme", "sme_handoff",
    "sme_eligible", "promote_sme", "platform_fact", "platform_incident", "feedback", "adopt", "establish_baseline", "resume", "lease",
    "abandon", "record", "summary", "trace", "doctor", "check", "vendor", "push", "permission", "upgrade", "migrate",
}


def _tool_error(result) -> dict:
    assert result.is_error
    text = result.content[0].text
    return json.loads(text[text.index("{"):])


def test_mcp_exposes_the_director_api(tmp_path):
    from mcp import Client

    async def main() -> set[str]:
        async with Client(build_server(tmp_path)) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert asyncio.run(main()) == API_CALLS


def test_mcp_refusals_carry_cli_exit_codes(tmp_path, monkeypatch):
    from mcp import Client

    cli, project = setup_fit_check(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    monkeypatch.setenv("BATON_HOME", str(cli.home))

    async def main():
        async with Client(build_server(project, "bob@host2")) as c:
            held = await c.call_tool("dispatch", {"run": run, "step": "describe", "worker": "owner"})
            missing = await c.call_tool("status", {"run": "r_nope"})
            ok = await c.call_tool("status", {"run": run})
            return held, missing, ok

    held, missing, ok = asyncio.run(main())
    err = _tool_error(held)
    assert err["exit_code"] == 3 and err["lease"]["director_id"] == "alice@host1"
    assert _tool_error(missing)["exit_code"] == 1
    assert not ok.is_error and ok.structured_content["ok"] and ok.structured_content["ready"] == ["describe"]


def _two_worker_project(tmp_path: Path) -> tuple[Path, Path]:
    outputs = tmp_path / "work" / "outputs.json"
    outputs.parent.mkdir()
    outputs.write_text(json.dumps({"describe": GOOD_PROFILE, "assess": VERDICT}), encoding="utf-8")
    import shlex

    def cmd(argv: list[str]) -> str:
        return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)

    (outputs.parent / "sme.json").write_text(json.dumps({"answer": "Two days is typical."}), encoding="utf-8")
    line = cmd([sys.executable, str(STEP_WORKER), "{packet}", "{result}", str(outputs)])
    sme_line = cmd([sys.executable, str(STEP_WORKER.parent / "fake_sme.py"), "{packet}", "{result}", str(outputs.parent / "sme.json")])
    profiles = OWNER_PROFILE + "".join(
        f"{name}:\n  adapter: command\n  vendor: {vendor}\n  command: {json.dumps(cl)}\n  capabilities: {json.dumps(FIT_CAPS)}\n  tier: strong\n"
        for name, vendor, cl in (("alpha", "acme", line), ("beta", "globex", line), ("sage", "initech", sme_line)))
    project = make_git_project(tmp_path / "proj")
    home = make_home(tmp_path / "home", profiles)
    cli = Cli(project, home)
    cli.run("init", str(project))
    cli.run("vendor", str(FIT_CHECK))
    set_config(project, sme={"project": {"preferred_profiles": ["sage"]}})
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return project, home


def _env(project: Path, home: Path, director: str, harness: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BATON_")}
    env.update(BATON_HOME=str(home), BATON_PROJECT=str(project), BATON_DIRECTOR=director, BATON_HARNESS=harness,
               PYTHONPATH=str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""))
    return env


def _mcp_director(project: Path, home: Path) -> str:
    """A Director that only has MCP: describe → alpha, assess → beta, the owner's decision relayed."""
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=["-m", "baton", "mcp"], cwd=str(project),
                                   env=_env(project, home, "mcp-director@test", "harness-a"))

    async def main() -> str:
        async with Client(params, read_timeout_seconds=120) as c:
            async def call(name: str, **args):
                res = await c.call_tool(name, args)
                assert not res.is_error, res.content
                return res.structured_content
            run = (await call("start", recipe="fit-check", inputs=FIT_INPUTS))["run_id"]
            assert "alpha" in [e["profile"] for e in (await call("eligible", run=run, step="describe"))["eligible"]]
            assert (await call("dispatch", run=run, step="describe", worker="alpha", wait=True))["outcome"] == "passed"
            out = await call("dispatch", run=run, step="assess", worker="beta", wait=True)
            assert out["outcome"] == "needs_human" and out["needs_owner"]
            assert (await call("explain", run=run))["position"]["owner_decisions"] == [{"ref": "assess", "kind": "gate"}]
            done = await call("decide", run=run, ref="assess", decision="approve", note="Agreed: it fits.")
            assert done["run_completed"]
            return run

    return asyncio.run(main())


def _cli_director(project: Path, home: Path) -> str:
    """A Director that only has a shell: describe → beta, assess → alpha."""
    env = _env(project, home, "cli-director@test", "harness-b")

    def baton(*args: str, expect: int = 0) -> dict:
        proc = subprocess.run([sys.executable, "-m", "baton", *args, "--json"], env=env, cwd=project, capture_output=True, text=True, timeout=120)
        assert proc.returncode == expect, proc.stdout + proc.stderr
        return json.loads(proc.stdout)

    run = baton("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    assert baton("dispatch", run, "describe", "--worker", "beta", "--wait")["outcome"] == "passed"
    assert baton("dispatch", run, "assess", "--worker", "alpha", "--wait", expect=4)["outcome"] == "needs_human"
    assert baton("decide", run, "assess", "approve", "--note", "Agreed: it fits.")["run_completed"]
    return run


def test_two_directors_complete_the_same_recipe_through_mcp_and_cli(tmp_path):
    """The Phase 14 criterion, scripted: different interfaces and worker assignments, every output from a worker."""
    project, home = _two_worker_project(tmp_path)
    by_mcp = _mcp_director(project, home)
    by_cli = _cli_director(project, home)
    for run, director, harness, workers in ((by_mcp, "mcp-director@test", "harness-a", ["alpha", "beta"]),
                                            (by_cli, "cli-director@test", "harness-b", ["beta", "alpha"])):
        evs = run_events(project, run)
        assert evs[-1]["type"] in ("run_completed", "lease_released", "checkpoint_committed")
        assert any(e["type"] == "run_completed" for e in evs)
        claimed = next(e for e in evs if e["type"] == "lease_claimed")
        assert claimed["data"]["director_id"] == director and claimed["data"]["harness"] == harness
        # Every result came from a worker process, never from the Director.
        submitted = [(e["step_path"], e["actor"]) for e in evs if e["type"] == "result_submitted"]
        assert submitted == [("describe", f"worker:{workers[0]}"), ("assess", f"worker:{workers[1]}")]
        assert [e["data"]["profile"] for e in evs if e["type"] == "dispatched"] == workers
        decision = next(e for e in evs if e["type"] == "human_decision")
        assert decision["actor"] == "human" and decision["data"]["note"] == "Agreed: it fits."
        director_types = {e["type"] for e in evs if e["actor"].startswith("director")}
        assert not director_types & {"result_submitted", "step_passed", "gate_passed", "findings_recorded", "artifact_published"}
    calls = [json.loads(line) for line in (tmp_path / "work" / "calls.jsonl").read_text().splitlines()]
    assert [(c["step"], c["profile"]) for c in calls] == [("describe", "alpha"), ("assess", "beta"), ("describe", "beta"), ("assess", "alpha")]
    assert Cli(project, home)("check").exit_code == 0


def test_expert_on_a_completed_run_is_not_blamed_for_checkpoints(tmp_path):
    """Found by the live Claude Code Director: consulting about a just-completed run releases its lease again,
    whose checkpoint commit moved HEAD while the expert worked and was blamed on the expert (workspace_modified)."""
    project, home = _two_worker_project(tmp_path)
    run = _cli_director(project, home)
    cli = Cli(project, home, director="cli-director@test")
    out = cli.run("ask-sme", "project", "Is two days typical?", "--run", run, "--wait")
    assert out["state"] == "answered", out
    assert out["turns"][-1]["answer"]["answer"] == "Two days is typical."


def test_checkpoint_commits_are_not_working_tree_changes(tmp_path):
    from baton import gitops

    root = make_git_project(tmp_path / "r")
    commit_file(root, "a.txt")
    before = gitops.tree_snapshot(root)
    commit_file(root, ".baton/runs/r1/events.jsonl", "{}\n", message="baton(r1): describe passed")
    assert gitops.tree_changes(before, gitops.tree_snapshot(root), root) == []
    assert gitops.tree_changes(before, gitops.tree_snapshot(root))[0].startswith("HEAD moved")  # without root: as before
    commit_file(root, "b.txt", message="worker change")
    assert gitops.tree_changes(before, gitops.tree_snapshot(root), root)[0].startswith("HEAD moved")
    git(root, "reset", "-q", "--hard", "HEAD~2")
    commit_file(root, "c.txt", message="baton(r1): rewritten history")  # not a descendant of nothing-but-checkpoints
    git(root, "reset", "-q", "--hard", "HEAD~1")
    git(root, "commit", "-q", "--amend", "-m", "amended")
    assert gitops.tree_changes(before, gitops.tree_snapshot(root), root)[0].startswith("HEAD moved")


def test_snapshot_uses_the_repositorys_own_line_endings(tmp_path):
    """Found on Windows CI (Phase 16): with the owner's ``core.autocrlf=true`` a committed CRLF file is LF in the
    index; a status forced to ``autocrlf=false`` called it modified whenever git re-hashed it, so snapshots flapped."""
    import os as _os

    from baton import gitops

    root = make_git_project(tmp_path / "r")
    git(root, "config", "core.autocrlf", "true")
    f = root / "notes.txt"
    f.write_bytes(b"one\r\ntwo\r\n")
    git(root, "add", "notes.txt")
    git(root, "commit", "-q", "-m", "CRLF file")
    before = gitops.tree_snapshot(root)
    st = f.stat()
    _os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # same bytes; git must re-hash it
    after = gitops.tree_snapshot(root)
    assert before.files == {} and after.files == {}
    assert gitops.tree_changes(before, after, root) == []


# -- HTTP ---------------------------------------------------------------------


def test_http_needs_a_token_and_loopback(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(EngineError) as e:
        http_token(home)
    assert e.value.code == "configuration.mcp_token" and "mcp.yaml" in str(e.value)
    (home / "mcp.yaml").write_text("token: plain-text-token-here\n", encoding="utf-8")
    with pytest.raises(EngineError, match="secret reference"):
        http_token(home)
    (home / "mcp.yaml").write_text("token: secret:mcp_token\n", encoding="utf-8")
    with pytest.raises(EngineError, match="mcp_token"):
        http_token(home)
    (home / "secrets").mkdir()
    (home / "secrets" / "mcp_token").write_text("short\n", encoding="utf-8")
    with pytest.raises(EngineError, match="at least 16"):
        http_token(home)
    (home / "secrets" / "mcp_token").write_text("s3cret-token-0123456789\n", encoding="utf-8")
    assert http_token(home) == "s3cret-token-0123456789"
    for ok in ("127.0.0.1", "::1", "localhost", "127.0.0.2"):
        check_loopback(ok)
    for bad in ("0.0.0.0", "10.0.0.5", "example.com"):
        with pytest.raises(EngineError) as e:
            check_loopback(bad)
        assert e.value.code == "mcp.not_loopback"


def test_http_cli_refuses_without_token_or_off_loopback(tmp_path):
    from typer.testing import CliRunner

    from baton.cli import app

    cli, project = setup_fit_check(tmp_path)
    runner = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_PROJECT": str(project)})
    res = runner.invoke(app, ["mcp", "--http"])
    assert res.exit_code == 1 and "bearer token" in res.stderr
    res = runner.invoke(app, ["mcp", "--http", "--host", "0.0.0.0"])
    assert res.exit_code == 1 and "not a loopback address" in res.stderr


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_http_serves_the_api_to_bearer_holders_only(tmp_path):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    cli, project = setup_fit_check(tmp_path)
    (cli.home / "mcp.yaml").write_text("token: secret:mcp_token\n", encoding="utf-8")
    (cli.home / "secrets").mkdir()
    token = "s3cret-token-0123456789"
    (cli.home / "secrets" / "mcp_token").write_text(token, encoding="utf-8")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "baton", "mcp", "--http", "--port", str(port)],
                            env=_env(project, cli.home, "http-director@test", "harness-c"), cwd=project,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                assert proc.poll() is None and time.monotonic() < deadline, proc.stderr.read().decode() if proc.poll() is not None else "timeout"
                time.sleep(0.1)
        assert httpx2.post(url, json={}).status_code == 401
        assert httpx2.post(url, json={}, headers={"Authorization": "Bearer wrong-token-0123456789"}).status_code == 401

        async def main():
            async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60) as http:
                async with Client(streamable_http_client(url, http_client=http)) as c:
                    res = await c.call_tool("start", {"recipe": "fit-check", "inputs": FIT_INPUTS})
                    assert not res.is_error, res.content
                    return res.structured_content

        out = asyncio.run(main())
        assert out["ok"] and out["ready"] == ["describe"]
        evs = run_events(project, out["run_id"])
        claimed = next(e for e in evs if e["type"] == "lease_claimed")
        assert claimed["data"]["director_id"] == "http-director@test"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
