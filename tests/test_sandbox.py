"""A sandboxed Director (change 2026-11-codex-director-sandbox, slice 1; decisions 0053, 0054).

`detect` and `doctor` never crash when the Director's own tool sandboxes them (an unwritable
Baton home, or network refused): each reports exactly one blocking problem, `director_sandboxed`,
with a plain-language owner message and informational options, and exits non-zero. A machine
that is merely offline, or a home write refused for another reason, is an ordinary warning or
problem. The healthy path still prints one line.
"""

from __future__ import annotations

import errno
import os
import socket
import stat

import pytest
from typer.testing import CliRunner

from baton import doctor as doc
from baton import labels
from baton.cli import app

from projectkit import Cli, make_git_project, make_home, setup_fit_check

posix_user = pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")


@pytest.fixture(autouse=True)
def _no_codex_hint(monkeypatch):
    monkeypatch.delenv(doc.CODEX_HINT, raising=False)


@pytest.fixture
def read_only_home(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    cli.home.chmod(stat.S_IRUSR | stat.S_IXUSR)
    yield cli, project
    cli.home.chmod(stat.S_IRWXU)


def _deny_network(monkeypatch, err=errno.EPERM):
    class Refused(socket.socket):
        def connect(self, address):
            raise OSError(err, os.strerror(err))

    monkeypatch.setattr(doc.socket, "socket", Refused)


def _assert_blocked(res, line_prefix):
    assert res.exit_code == 1, res.stdout
    out = res.payload
    assert out["ok"] is False and out["blocking"]["code"] == "director_sandboxed"
    assert out["problems"] == [f"director_sandboxed: {out['blocking']['title']} (fix: {out['blocking']['fix']})"]
    assert out["line"] == f"{line_prefix}: Baton can't run from inside this AI tool's sandbox"
    assert [o["decision"] for o in out["blocking"]["options"]] == ["connect_tool", "approve_when_asked", "turn_off_sandbox"]
    return out["blocking"]


@posix_user
@pytest.mark.slow
def test_unwritable_home_blocks_doctor_and_detect_without_a_traceback(read_only_home):
    cli, _ = read_only_home
    b = _assert_blocked(cli("doctor", expect=None), "doctor")
    assert b["cause"]["home"] and b["harness"] is None
    assert "this AI tool's sandbox" in b["message"] and "`baton mcp`" in b["message"] and "codex" not in b["message"].lower()
    assert b["options"][0]["label"] == "Connect Baton as a tool (recommended)"
    out = cli("detect", expect=None)
    _assert_blocked(out, "baton")
    assert out.payload["runs"] == [] and out.payload["machine"] is None


@posix_user
def test_detect_outside_a_project_still_reports_the_sandbox(tmp_path):
    home = make_home(tmp_path / "home")
    bare = make_git_project(tmp_path / "bare")
    home.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        res = Cli(bare, home)("detect", expect=None)
    finally:
        home.chmod(stat.S_IRWXU)
    _assert_blocked(res, "baton")
    assert res.payload["project"]["situation"] == "no_baton"


@pytest.mark.parametrize("err", [errno.EROFS, errno.EACCES, errno.EPERM])
@pytest.mark.slow
def test_each_sandbox_errno_on_the_home_is_the_sandbox(tmp_path, monkeypatch, err):
    cli, _ = setup_fit_check(tmp_path)

    def refused(*a, **k):
        raise OSError(err, os.strerror(err))

    monkeypatch.setattr(doc.tempfile, "mkstemp", refused)
    b = _assert_blocked(cli("doctor", expect=None), "doctor")
    assert b["cause"]["home"] == os.strerror(err)


@pytest.mark.slow
def test_denied_network_is_the_sandbox_and_codex_gets_its_own_message(tmp_path, monkeypatch):
    cli, _ = setup_fit_check(tmp_path)
    _deny_network(monkeypatch)
    b = _assert_blocked(cli("doctor", expect=None), "doctor")
    assert b["cause"] == {"home": None, "network": "denied"} and b["config"] is None
    monkeypatch.setenv(doc.CODEX_HINT, "1")
    b = _assert_blocked(cli("doctor", expect=None), "doctor")
    assert b["harness"] == "codex" and b["fix"] == "codex mcp add baton -- baton mcp"
    assert b["config"] == {"file": "~/.codex/config.toml", "section": "[mcp_servers.baton]", "line": 'default_tools_approval_mode = "approve"'}
    assert '`default_tools_approval_mode = "approve"`' in b["message"] and "`[mcp_servers.baton]`" in b["message"]
    assert "`codex mcp add baton -- baton mcp`" in b["message"] and "Codex runs connected tools outside its sandbox" in b["message"]
    assert b["options"][0]["label"] == "Connect Baton to Codex (recommended)"


def test_socket_creation_refused_is_denied(monkeypatch):
    def refused(*a, **k):
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(doc.socket, "socket", refused)
    assert doc.network_state() == "denied"


@pytest.mark.slow
def test_an_offline_machine_is_a_warning_not_the_sandbox(tmp_path, monkeypatch):
    cli, _ = setup_fit_check(tmp_path)
    _deny_network(monkeypatch, errno.ENETUNREACH)
    out = cli.run("doctor", "--no-run")
    assert out["ok"] is True and "blocking" not in out
    assert "this machine has no network route; workers that use the internet will fail" in out["warnings"]
    out = cli.run("detect")
    assert out["ok"] is True and "blocking" not in out


@pytest.mark.slow
def test_a_refused_log_write_mid_doctor_is_reported_never_raised(tmp_path, monkeypatch):
    cli, _ = setup_fit_check(tmp_path)
    log = cli.home / "logs" / "doctor" / "x.log"

    def refuse(err):
        def run(*a, **k):
            raise doc.HomeWriteError(log, OSError(err, os.strerror(err)))
        return run

    monkeypatch.setattr(doc, "_doctor", refuse(errno.EROFS))
    _assert_blocked(cli("doctor", expect=None), "doctor")
    monkeypatch.setattr(doc, "_doctor", refuse(errno.ENOSPC))  # not a sandbox: an ordinary problem
    res = cli("doctor", expect=1)
    assert "blocking" not in res.payload and res.payload["problems"] == [f"cannot write {log}: {os.strerror(errno.ENOSPC)}"]


@posix_user
def test_every_doctor_log_write_goes_through_the_helper(tmp_path):
    logs = tmp_path / "home" / "logs"
    logs.mkdir(parents=True)
    logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(doc.HomeWriteError) as e:
            doc._run(["true"], type("Env", (), {"resolved": None, "env": {}})(), tmp_path, logs / "doctor" / "p.log", 5)
    finally:
        logs.chmod(stat.S_IRWXU)
    assert e.value.error.errno in doc.SANDBOX_ERRNOS


@posix_user
@pytest.mark.slow
def test_text_output_carries_the_owner_message(read_only_home):
    cli, project = read_only_home
    res = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_PROJECT": str(project)}).invoke(app, ["doctor"])
    assert res.exit_code == 1
    assert res.stdout.splitlines()[0].startswith("PROBLEM director_sandboxed: ")
    assert "**Baton can't run from inside this AI tool's sandbox.**" in res.stdout and "Options: " in res.stdout


@pytest.mark.slow
def test_healthy_path_is_unchanged(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    out = cli.run("doctor", "--no-run")
    assert out["ok"] is True and "blocking" not in out
    text = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_PROJECT": str(project)}).invoke(app, ["detect"]).stdout
    assert [ln for ln in text.splitlines() if not ln.startswith("WARNING")] == ["baton: healthy; 0 active runs"]


def test_sandbox_labels_are_in_the_owners_terms():
    entries = labels.defaults()["director_sandboxed"]
    assert set(entries) == {"connect_tool", "approve_when_asked", "turn_off_sandbox"}
    for name, entry in entries.items():
        assert entry["label"] and entry["effect"], name
        for word in ("run", "step", "attempt", "dispatch", "escalat", "gate", "worker", "packet"):
            assert word not in f" {entry['label'].lower()} ", (name, word)
