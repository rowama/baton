"""Harness adapters (§6.3): claude_code, codex, command; read/write modes; doctor's auth report and gate preflight (§13.4).

Offline: the CLIs are the fake in ``tests/fakes/fake_harness.py`` (see its
docstring for what it models). Opt-in live test against the real CLIs and
their stored subscription logins: ``BATON_LIVE_HARNESS=1`` (``test_live_harnesses``).
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from baton.adapters import ADAPTERS
from baton.adapters.harness import TASK_PROMPT
from baton.engine import classify_exit
from baton.models import WorkerProfile
from baton.supervisor import ChildResult

from harnesskit import calls, harness_profile, install_fake, nvm_dir, same, set_outputs
from projectkit import FIT_INPUTS, GOOD_PROFILE, OWNER_PROFILE, VERDICT, git, setup_fit_check


SENTINEL = "BATON-SENTINEL-harnessKey0003"
#: This interpreter, quoted for the platform shell (script gates run under /bin/sh or cmd.exe).
PY = shlex.quote(sys.executable) if os.name == "posix" else subprocess.list2cmdline([sys.executable])
FIT_CAPS = ["structured_output", "long_form_writing", "technical_reasoning"]
CODER_CAPS = FIT_CAPS + ["tool_use", "file_write", "shell", "code_exec", "repo_workspace", "workspace_read"]


def prof(**kw) -> WorkerProfile:
    base = {"adapter": "claude_code", "vendor": "v", "capabilities": ["structured_output"], "auth": {"mode": "cli_login"}}
    return WorkerProfile.model_validate({**base, **kw})


def events(project: Path, run: str) -> list[dict]:
    return [json.loads(line) for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text().splitlines()]


def set_project(project: Path, **values: object) -> None:
    f = project / ".baton" / "project.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    data.setdefault("project", {}).update(values)
    f.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    git(project, "commit", "-qam", "project vars")


def setup_with_workspace(tmp_path: Path, step: str, mode: str):
    """Like ``setup_fit_check``, but with one fit-check step made a workspace step."""
    from conftest import FIT_CHECK
    from projectkit import Cli, make_git_project, make_home

    src = tmp_path / "fit-check"
    shutil.copytree(FIT_CHECK, src)
    rf = src / "recipe.yaml"
    data = yaml.safe_load(rf.read_text(encoding="utf-8"))
    s = next(x for x in data["steps"] if x["id"] == step)
    s["workspace"] = mode
    s["requires"]["capabilities"].append("repo_workspace" if mode == "write" else "workspace_read")
    rf.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project), "--bare")  # vendors its own edited fit-check
    cli.run("vendor", str(src))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return cli, project


STREAM = ["--output-format", "stream-json", "--verbose"]

# ---------------------------------------------------------------------------
# Command lines per preset and mode
# ---------------------------------------------------------------------------


def test_claude_code_command_per_mode(tmp_path):
    a = ADAPTERS["claude_code"]
    pk, rs = tmp_path / "packet", tmp_path / "result"
    argv = a.command(prof(), pk, rs, None, "none")
    assert argv[:3] == ["claude", "-p", TASK_PROMPT.format(packet=pk.as_posix(), result=rs.as_posix())]
    stream = ["--output-format", "stream-json", "--verbose"]  # the event stream, for tool evidence (0085)
    assert argv[3:] == ["--permission-mode", "acceptEdits", *stream]
    assert a.command(prof(), pk, rs, tmp_path, "write")[3:] == ["--permission-mode", "bypassPermissions", *stream]
    assert a.command(prof(), pk, rs, tmp_path, "read")[3:] == ["--permission-mode", "acceptEdits", *stream]
    # A profile's args replace the default for that mode only; model is passed through.
    p = prof(args={"read": ["--permission-mode", "plan"]}, model="some-model")
    assert a.command(p, pk, rs, tmp_path, "read")[3:] == ["--permission-mode", "plan", *stream, "--model", "some-model"]
    assert a.command(p, pk, rs, tmp_path, "write")[3:5] == ["--permission-mode", "bypassPermissions"]
    assert a.config_home_var == "CLAUDE_CONFIG_DIR"


def test_codex_command_per_mode(tmp_path):
    a = ADAPTERS["codex"]
    p = prof(adapter="codex", executable="/opt/codex", args={"write": ["--sandbox", "danger-full-access"]})
    argv = a.command(p, tmp_path / "packet", tmp_path / "result", tmp_path, "write")
    assert argv[:4] == ["/opt/codex", "exec", "--sandbox", "danger-full-access"]
    assert "--skip-git-repo-check" in argv and argv[-1].startswith("Read ")
    assert a.command(p, tmp_path / "packet", tmp_path / "result", None, "none")[2:4] == ["--sandbox", "workspace-write"]
    assert "--json" in argv
    assert a.config_home_var == "CODEX_HOME"


def test_tool_maps_turn_on_only_what_the_step_requires(tmp_path):
    from baton import known_workers, vocab
    from baton.adapters.harness import plan_tools

    data = known_workers.load(vocab.load(vocab.DEFAULT))
    pk, rs = tmp_path / "packet", tmp_path / "result"
    claude, codex = ADAPTERS["claude_code"], ADAPTERS["codex"]
    claims = ["structured_output", "web_access", "file_write"]
    web = plan_tools(data.tool_map("claude_code"), ["structured_output", "web_access"], claims)
    argv = claude.command(prof(), pk, rs, None, "none", tools=web)
    assert argv[argv.index("--allowedTools") + 1] == "WebSearch,WebFetch" and "--disallowedTools" not in argv
    quiet = plan_tools(data.tool_map("claude_code"), ["structured_output"], claims)
    argv = claude.command(prof(), pk, rs, None, "none", tools=quiet)
    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch" and "--allowedTools" not in argv
    assert quiet.describe() == {"on": [], "off": ["web_access"], "args": ["--disallowedTools", "WebSearch,WebFetch"]}
    # A profile that does not claim the tool never gets it turned on.
    assert plan_tools(data.tool_map("claude_code"), ["web_access"], ["structured_output"]).on == {}
    # Codex's web search is a flag before the subcommand.
    p = prof(adapter="codex", executable="/opt/codex")
    argv = codex.command(p, pk, rs, None, "none", tools=plan_tools(data.tool_map("codex"), ["web_access"], claims))
    assert argv[:3] == ["/opt/codex", "--search", "exec"]
    assert "--search" not in codex.command(p, pk, rs, None, "none", tools=plan_tools(data.tool_map("codex"), [], claims))


def test_harness_versions_are_read_from_their_output():
    c = ADAPTERS["claude_code"]
    assert c.parse_version("2.1.319 (Claude Code)") == "2.1.319"
    assert ADAPTERS["codex"].parse_version("codex-cli 0.166.0\n") == "0.166.0"
    assert c.parse_version("") is None


def test_harness_needs_an_auth_mode():
    from baton.profiles import SetupError

    with pytest.raises(SetupError) as e:
        ADAPTERS["codex"].check_profile(prof(adapter="codex", auth={"mode": "none"}))
    assert e.value.failure_class == "configuration"


def test_command_adapter_placeholders(tmp_path):
    a = ADAPTERS["command"]
    p = prof(adapter="command", command="relay --prompt {prompt_file} --in {packet} --out={result} --ws '{workspace}'")
    argv = a.command(p, tmp_path / "pk", tmp_path / "rs", None, "none")
    t = tmp_path.as_posix()  # placeholders are POSIX paths on every platform (§15.1)
    assert argv == ["relay", "--prompt", f"{t}/pk/INSTRUCTIONS.md", "--in", f"{t}/pk", f"--out={t}/rs", "--ws", ""]
    from baton.profiles import SetupError, executable_for

    assert executable_for(p) == "relay"
    with pytest.raises(SetupError):
        a.check_profile(prof(adapter="command"))


def test_auth_status_parsing():
    c, x = ADAPTERS["claude_code"], ADAPTERS["codex"]
    assert c.parse_auth_status(0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "pro"}))["mode"] == "cli_login"
    assert c.parse_auth_status(0, json.dumps({"loggedIn": True, "authMethod": "api_key"}))["mode"] == "api_key"
    assert c.parse_auth_status(1, json.dumps({"loggedIn": False}))["mode"] == "none"
    assert c.parse_auth_status(1, "garbage")["mode"] == "unknown"
    assert x.parse_auth_status(0, "Logged in using ChatGPT\n")["mode"] == "cli_login"
    assert x.parse_auth_status(0, "Logged in using an API key - sk-***\n")["mode"] == "api_key"
    assert x.parse_auth_status(1, "Not logged in\n")["mode"] == "none"


def test_failure_signals_classify_harness_exits(tmp_path):
    tail = b"starting\nNot logged in \xc2\xb7 Please run /login\n"
    cls = classify_exit(ChildResult(1, 0.1, False, tmp_path / "x", tail), ADAPTERS["claude_code"].failure_signals)
    assert cls["class"] == "platform" and cls["code"] == "auth_failed" and "Please run /login" in cls["message"]
    assert classify_exit(ChildResult(1, 0.1, False, tmp_path / "x", b"boom\n"), ADAPTERS["codex"].failure_signals)["class"] == "unknown"


# ---------------------------------------------------------------------------
# Acceptance: one run, one step through a CLI login, another through an API key
# ---------------------------------------------------------------------------


@pytest.fixture
def litellm_or_skip():
    pytest.importorskip("litellm")


def test_cli_login_and_api_key_steps_in_one_run(tmp_path, monkeypatch, litellm_or_skip):
    from test_api_worker import api_profile, reply

    cli, project = setup_fit_check(tmp_path)
    # A key for the CLI's vendor is in the Director's environment: it must not reach the CLI worker.
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    bin_dir = tmp_path / "bin"
    claude = install_fake(bin_dir, "claude", {"describe": {"output": GOOD_PROFILE}})
    (cli.home / "secrets").mkdir()
    (cli.home / "secrets" / "zenith_key").write_text("zenith-key-value", encoding="utf-8")
    (cli.home / "workers.yaml").write_text(
        harness_profile("claude-sub", "claude_code", "acme", executable=str(claude), capabilities=FIT_CAPS, env_deny=["ANTHROPIC_API_KEY"])
        + api_profile("zenith-api", "zenith", "anthropic/zenith-model", "zenith_key", reply(VERDICT), env_var="ZENITH_KEY"),
        encoding="utf-8",
    )
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    d1 = cli.run("dispatch", run, "describe", "--worker", "claude-sub", "--wait")
    assert d1["outcome"] == "passed", d1
    d2 = cli("dispatch", run, "assess", "--worker", "zenith-api", "--wait", expect=4).payload
    assert d2["outcome"] == "needs_human", d2
    assert cli.run("decide", run, "assess", "approve", "--note", "Agreed.")["run_completed"] is True

    disp = {e["step_path"]: e["data"] for e in events(project, run) if e["type"] == "dispatched"}
    assert disp["describe"]["auth_mode"] == "cli_login" and disp["assess"]["auth_mode"] == "api_key"
    assert disp["describe"]["adapter"] == "claude_code" and disp["describe"]["env"]["env_mode"] == "allowlist"
    assert disp["describe"]["env"]["executable"] == str(claude)
    assert ("HOME" if os.name == "posix" else "USERPROFILE") in disp["describe"]["env"]["names"] and disp["describe"]["env"]["secret_names"] == []
    # It was in the parent environment, so env_deny removed it (allowlist would not have passed it anyway).
    assert "ANTHROPIC_API_KEY" not in disp["describe"]["env"]["names"]
    assert disp["assess"]["env"]["secret_names"] == ["ZENITH_KEY"]

    (call,) = [c for c in calls(bin_dir)]
    assert "ANTHROPIC_API_KEY" not in call["env"] and "BATON_PACKET_DIR" in call["env"]
    assert "BATON_WORKSPACE" not in call["env"]  # a workspace: none step
    assert Path(call["cwd"]).name == "attempt-1"  # cwd is the attempt directory
    assert call["argv"][2:] == ["--permission-mode", "acceptEdits", "--disallowedTools", "WebSearch,WebFetch", *STREAM]
    assert git(project, "status", "--porcelain") == ""
    assert SENTINEL not in subprocess.run(["git", "-C", str(project), "log", "-p", "--all"], capture_output=True, text=True).stdout


def test_codex_found_only_under_nvm_runs_a_step(tmp_path, monkeypatch):
    cli, project = setup_fit_check(tmp_path)
    user_home = tmp_path / "user"
    bin_dir = nvm_dir(user_home)
    codex = install_fake(bin_dir, "codex", {"describe": {"output": GOOD_PROFILE}})
    monkeypatch.delenv("NVM_DIR", raising=False)
    monkeypatch.setenv("HOME", str(user_home))
    (cli.home / "workers.yaml").write_text(
        harness_profile("codex-sub", "codex", "zenith", executable="codex", capabilities=FIT_CAPS, path={"search": ["nvm"]}, env_deny=["OPENAI_API_KEY", "CODEX_API_KEY"]),
        encoding="utf-8",
    )
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    d = cli.run("dispatch", run, "describe", "--worker", "codex-sub", "--wait")
    assert d["outcome"] == "passed", d
    disp = next(e["data"] for e in events(project, run) if e["type"] == "dispatched")
    assert disp["env"]["resolved_by"] == "search:nvm" and same(disp["env"]["executable"], codex)
    (call,) = calls(bin_dir)
    assert call["argv"][:3] == ["exec", "--sandbox", "workspace-write"]


def test_cli_not_logged_in_is_a_platform_failure(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    claude = install_fake(tmp_path / "bin", "claude", {"describe": {"output": GOOD_PROFILE}})
    # clean env: no HOME, so the stored login cannot be found.
    (cli.home / "workers.yaml").write_text(
        harness_profile("claude-sub", "claude_code", "acme", executable=str(claude), capabilities=FIT_CAPS, env_mode="clean"), encoding="utf-8"
    )
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    d = cli("dispatch", run, "describe", "--worker", "claude-sub", "--wait", expect=4).payload
    assert d["outcome"] == "escalated", d
    ev = events(project, run)
    cls = next(e["data"] for e in ev if e["type"] == "failure_classified")
    assert cls["class"] == "platform" and cls["code"] == "auth_failed"
    assert [e["type"] for e in ev if e["step_path"] == "describe"][-3:] == ["attempt_orphaned", "failure_classified", "step_escalated"]


def test_command_adapter_runs_a_step(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    tool = tmp_path / "relay.py"
    tool.write_text(
        "import json, sys, pathlib\n"
        "pk, rs = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])\n"
        "m = json.loads((pk / 'manifest.json').read_text())\n"
        f"out = {GOOD_PROFILE!r}\n"
        "rs.mkdir(parents=True, exist_ok=True)\n"
        "(rs / 'result.json').write_text(json.dumps({'protocol': 'baton-packet/1', 'packet_sha256': m['packet_sha256'], 'status': 'completed', 'output': out}))\n",
        encoding="utf-8",
    )
    (cli.home / "workers.yaml").write_text(
        f"relay:\n  adapter: command\n  vendor: other\n  command: {json.dumps(f'{sys.executable} {tool} {{packet}} {{result}}')}\n"
        f"  capabilities: {json.dumps(FIT_CAPS)}\n  tier: strong\n",
        encoding="utf-8",
    )
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    d = cli.run("dispatch", run, "describe", "--worker", "relay", "--wait")
    assert d["outcome"] == "passed", d


# ---------------------------------------------------------------------------
# Read / write / none modes: the runtime's tree check
# ---------------------------------------------------------------------------


def _ws_setup(tmp_path, mode: str, spec: dict):
    cli, project = setup_fit_check(tmp_path) if mode == "none" else setup_with_workspace(tmp_path, "describe", mode)
    bin_dir = tmp_path / "bin"
    claude = install_fake(bin_dir, "claude", {"describe": {"output": GOOD_PROFILE, **spec}})
    (cli.home / "workers.yaml").write_text(harness_profile("claude-sub", "claude_code", "acme", executable=str(claude), capabilities=CODER_CAPS), encoding="utf-8")
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    return cli, project, bin_dir, run


def test_read_step_that_changes_the_tree_escalates(tmp_path):
    cli, project, bin_dir, run = _ws_setup(tmp_path, "read", {"touch": "notes.txt"})
    d = cli("dispatch", run, "describe", "--worker", "claude-sub", "--wait", expect=4).payload
    assert d["outcome"] == "escalated" and "notes.txt" in d["reasons"][0], d
    ev = events(project, run)
    gate = next(e["data"] for e in ev if e["type"] == "gate_failed")
    assert gate["gate"] == "workspace" and gate["implicit"] is True and gate["changed"] == ["notes.txt"]
    esc = [e for e in ev if e["type"] == "step_escalated"][-1]["data"]
    assert esc["reason"] == "workspace_modified"
    assert (project / "notes.txt").exists()  # never reverted by the runtime
    (call,) = calls(bin_dir)
    assert call["cwd"] == str(project) and "BATON_WORKSPACE" in call["env"]
    assert call["argv"][2:] == ["--permission-mode", "acceptEdits", "--disallowedTools", "WebSearch,WebFetch", *STREAM]


def test_read_step_that_leaves_the_tree_alone_passes(tmp_path):
    cli, project, _, run = _ws_setup(tmp_path, "read", {})
    (project / "scratch.txt").write_text("pre-existing uncommitted work\n")  # already dirty: not the worker's change
    assert cli.run("dispatch", run, "describe", "--worker", "claude-sub", "--wait")["outcome"] == "passed"


def test_none_step_writing_outside_its_attempt_escalates(tmp_path):
    cli, project, _, run = _ws_setup(tmp_path, "none", {})
    set_outputs(tmp_path / "bin", {"describe": {"output": GOOD_PROFILE, "touch": str(project / "README-x.md")}})
    d = cli("dispatch", run, "describe", "--worker", "claude-sub", "--wait", expect=4).payload
    assert d["outcome"] == "escalated" and "README-x.md" in d["reasons"][0]


def test_write_step_may_change_the_tree(tmp_path):
    cli, project, bin_dir, run = _ws_setup(tmp_path, "write", {"touch": "src.txt"})
    assert cli.run("dispatch", run, "describe", "--worker", "claude-sub", "--wait")["outcome"] == "passed"
    (call,) = calls(bin_dir)
    assert call["argv"][2:] == ["--permission-mode", "bypassPermissions", "--disallowedTools", "WebSearch,WebFetch", *STREAM]


def test_tree_snapshot_sees_commits_and_edits(tmp_path):
    from baton import gitops

    from projectkit import make_git_project

    root = make_git_project(tmp_path / "r")
    (root / "a.txt").write_text("1")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a")
    (root / "skip").mkdir()
    before = gitops.tree_snapshot(root, ["skip"])
    (root / "skip" / "x").write_text("ignored by exclude")
    assert gitops.tree_changes(before, gitops.tree_snapshot(root, ["skip"])) == []
    (root / "a.txt").write_text("2")
    assert gitops.tree_changes(before, gitops.tree_snapshot(root, ["skip"])) == ["a.txt"]
    git(root, "commit", "-qam", "b")
    changes = gitops.tree_changes(before, gitops.tree_snapshot(root, ["skip"]))
    assert changes[0].startswith("HEAD moved") and "a.txt" not in changes  # committed: clean again, but HEAD moved
    assert gitops.tree_snapshot(tmp_path / "not-a-repo") is None


# ---------------------------------------------------------------------------
# doctor: effective auth mode and gate preflight
# ---------------------------------------------------------------------------


def _doctor_setup(tmp_path, monkeypatch, profiles: str):
    from test_api_worker import api_profile

    cli, project = setup_fit_check(tmp_path)
    set_project(project, preflight=f"{PY} -c \"print('preflight')\"")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    (cli.home / "secrets").mkdir()
    (cli.home / "secrets" / "k").write_text("key-value", encoding="utf-8")
    (cli.home / "workers.yaml").write_text(OWNER_PROFILE + profiles + api_profile("api", "zenith", "anthropic/m", "k", '{"ok": true}'), encoding="utf-8")
    return cli, project


def test_doctor_reports_effective_auth_and_passes_preflight(tmp_path, monkeypatch, litellm_or_skip):
    user_home = tmp_path / "user"
    install_fake(nvm_dir(user_home), "codex")
    claude = install_fake(tmp_path / "bin", "claude")
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.delenv("NVM_DIR", raising=False)
    cli, project = _doctor_setup(
        tmp_path, monkeypatch,
        harness_profile("claude-sub", "claude_code", "acme", executable=str(claude), capabilities=CODER_CAPS, env_deny=["ANTHROPIC_API_KEY"])
        + harness_profile("codex-sub", "codex", "zenith", executable="codex", capabilities=CODER_CAPS, path={"search": ["nvm"]}),
    )
    res = cli("doctor")
    assert res.exit_code == 0 and res.payload["ok"] is True, res.payload
    p = res.payload["profiles"]
    assert p["claude-sub"]["auth_effective"]["mode"] == "cli_login" and p["claude-sub"]["auth_effective"]["subscription"] == "pro"
    assert p["codex-sub"]["auth_effective"] == {"mode": "cli_login", "detail": "Logged in using ChatGPT"}
    assert p["api"]["auth_effective"]["mode"] == "api_key" and p["owner"]["auth_effective"]["mode"] == "none"
    for name in ("claude-sub", "codex-sub"):
        assert p[name]["noop"]["ok"] is True
        pf = p[name]["preflight"]
        assert pf["ok"] is True and pf["worker_exit"] == 0 == pf["runtime_exit"], pf
    assert "preflight" not in p["api"]  # not write-capable
    assert not list((project / ".baton" / "cache" / "doctor").glob("*.json"))  # markers cleaned up
    assert git(project, "status", "--porcelain") == ""
    # --no-run still reports auth (a local status query), but makes no model calls.
    q = cli.run("doctor", "--no-run")["profiles"]["claude-sub"]
    assert q["auth_effective"]["mode"] == "cli_login" and q["noop"] == {"skipped": "--no-run"} and q["preflight"] == {"skipped": "--no-run"}


def test_preflight_catches_a_permission_mode_that_blocks_the_test_command(tmp_path, monkeypatch):
    claude = install_fake(tmp_path / "bin", "claude")
    cli, project = _doctor_setup(
        tmp_path, monkeypatch,
        harness_profile(
            "claude-plan", "claude_code", "acme", executable=str(claude), capabilities=CODER_CAPS,
            env_deny=["ANTHROPIC_API_KEY"], args={"write": ["--permission-mode", "plan"]},
        ),
    )
    res = cli("doctor", "--profile", "claude-plan", expect=1).payload
    rep = res["profiles"]["claude-plan"]
    assert rep["noop"]["ok"] is True  # the CLI itself works ...
    assert rep["preflight"]["ok"] is False and rep["preflight"]["worker_exit"] is None  # ... but cannot run gate commands
    assert any("could not run under this profile's write-mode args ['--permission-mode', 'plan']" in p for p in res["problems"])
    assert not (project / ".baton" / "runs").exists() or not any((project / ".baton" / "runs").iterdir())  # before any real run


def test_preflight_catches_a_sandbox_that_changes_the_outcome(tmp_path, monkeypatch):
    claude = install_fake(tmp_path / "bin", "claude")
    cli, project = _doctor_setup(
        tmp_path, monkeypatch,
        harness_profile("claude-sub", "claude_code", "acme", executable=str(claude), capabilities=CODER_CAPS, env_deny=["ANTHROPIC_API_KEY"]),
    )
    # LC_ALL reaches a script gate (the runtime's gate env) but not this worker (allowlist):
    # the same command passes for the runtime and fails inside the worker.
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    set_project(project, preflight=f"{PY} -c \"import os, sys; sys.exit(0 if os.environ.get('LC_ALL') else 1)\"")
    rep = cli("doctor", "--profile", "claude-sub", expect=1).payload["profiles"]["claude-sub"]
    assert rep["preflight"]["runtime_exit"] == 0 and rep["preflight"]["worker_exit"] == 1
    assert "changes its outcome" in rep["preflight"]["problem"]


def test_doctor_flags_a_login_profile_that_would_bill_an_api_key(tmp_path, monkeypatch):
    claude = install_fake(tmp_path / "bin", "claude")
    cli, _ = _doctor_setup(
        tmp_path, monkeypatch,
        # inherit and no env_deny: the Director's ANTHROPIC_API_KEY reaches the CLI.
        harness_profile("claude-leaky", "claude_code", "acme", executable=str(claude), capabilities=FIT_CAPS, env_mode="inherit"),
    )
    res = cli("doctor", "--profile", "claude-leaky", expect=1).payload
    rep = res["profiles"]["claude-leaky"]
    assert rep["auth_effective"]["mode"] == "api_key" and rep["failure_class"] == "configuration"
    assert any("billing would switch to the API; add the key's variable to env_deny" in p for p in res["problems"])
    assert SENTINEL not in json.dumps(res)


def test_doctor_flags_a_cli_that_is_not_logged_in(tmp_path, monkeypatch):
    claude = install_fake(tmp_path / "bin", "claude")
    cli, _ = _doctor_setup(
        tmp_path, monkeypatch, harness_profile("claude-sub", "claude_code", "acme", executable=str(claude), capabilities=FIT_CAPS, env_mode="clean")
    )
    res = cli("doctor", "--profile", "claude-sub", expect=1).payload
    assert any("not authenticated; log in on this machine with `claude auth login`" in p for p in res["problems"])


# ---------------------------------------------------------------------------
# Live (opt-in): the real CLIs with their stored subscription logins
# ---------------------------------------------------------------------------


LIVE_ANSWERS = (
    "Answers: a few contracts per month; each takes about two days with one or two rounds of redlines; "
    "a legal-review agent and I are involved and I sign off; it checks legal terms, pricing and data protection "
    "against our playbook; contracts arrive as PDF email attachments and a supplied document is fine; "
    "a turnaround of a day or two is fine; keeping each review as a record in the repo is a benefit. "
    "Do not ask further questions; produce the profile from these answers."
)


@pytest.mark.skipif(not os.environ.get("BATON_LIVE_HARNESS"), reason="live test: set BATON_LIVE_HARNESS=1 (uses the real claude and codex logins)")
def test_live_harnesses(tmp_path):
    """fit-check through the real CLIs: describe by claude, assess by codex; doctor on both, preflight included."""
    real_home = os.environ["HOME"]
    cli, project = setup_fit_check(tmp_path)
    set_project(project, preflight="git status --porcelain")
    (cli.home / "workers.yaml").write_text(
        harness_profile("claude-sub", "claude_code", "anthropic", executable="claude", capabilities=CODER_CAPS,
                        path={"search": [f"{real_home}/.local/bin"]}, env_deny=["ANTHROPIC_API_KEY"])
        + harness_profile("codex-sub", "codex", "openai", executable="codex", capabilities=CODER_CAPS,
                          path={"search": ["nvm"]}, env_deny=["OPENAI_API_KEY", "CODEX_API_KEY"]),
        encoding="utf-8",
    )
    doc = cli("doctor", expect=None).payload
    print(json.dumps(doc, indent=2))
    for name in ("claude-sub", "codex-sub"):
        rep = doc["profiles"][name]
        assert rep["auth_effective"]["mode"] == "cli_login", rep
        assert rep["noop"]["ok"] is True, rep
        assert rep["preflight"]["ok"] is True, rep
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    d1 = cli("dispatch", run, "describe", "--worker", "claude-sub", "--wait", expect=None).payload
    print(json.dumps(d1, indent=2))
    if d1["outcome"] == "escalated":
        # describe interviews the owner: a real worker asks first (a `blocked` result). The owner answers.
        assert d1["pending_decisions"][0]["reason"] == "blocked", d1
        cli("decide", run, "describe", "retry", "--note", LIVE_ANSWERS, expect=None)
        d1 = cli("dispatch", run, "describe", "--worker", "claude-sub", "--wait", expect=None).payload
        print(json.dumps(d1, indent=2))
    assert d1["outcome"] == "passed", d1
    d2 = cli("dispatch", run, "assess", "--worker", "codex-sub", "--wait", expect=None).payload
    print(json.dumps(d2, indent=2))
    assert d2["outcome"] == "needs_human", d2
