"""Environment construction, PATH resolution and secrets (§6.1, §6.2)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from baton import redact
from baton.models import WorkerProfile
from baton.profiles import (
    BATON_VARS,
    SetupError,
    build_env,
    effective_env_mode,
    resolve_executable,
    resolve_secret,
    secret_env_name,
    system_path,
    validate_profiles,
)
from baton.vocab import load as load_vocab

PARENT = {
    "PATH": "/parent/bin:/usr/bin",
    "HOME": "/home/me",
    "LANG": "C.UTF-8",
    "TERM": "xterm",
    "FOO": "bar",
    "OPENAI_API_KEY": "parent-key-value",
    "OTHER_API_KEY": "other-value",
    "EDITOR": "vi",
}


def prof(**kw) -> WorkerProfile:
    body = {"adapter": "litellm_api", "vendor": "v", "model": "m"}
    body.update(kw)
    return WorkerProfile.model_validate(body)


def names(built) -> set[str]:
    return set(built.names())


def dirs(tmp: Path) -> dict:
    return {"packet_dir": tmp / "p", "result_dir": tmp / "r"}


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def test_default_modes_follow_auth():
    assert effective_env_mode(prof(auth={"mode": "api_key"})) == "clean"
    assert effective_env_mode(prof(auth={"mode": "cli_login"})) == "allowlist"
    assert effective_env_mode(prof(auth={"mode": "none"})) == "allowlist"
    assert effective_env_mode(prof(auth={"mode": "api_key"}, env_mode="inherit")) == "inherit"


def test_clean_has_only_path_baton_vars_and_injected_secret(tmp_path):
    p = prof(auth={"mode": "api_key", "env": {"MODEL_KEY": "secret:main"}})
    built = build_env(p, home=tmp_path, environ={**PARENT, secret_env_name("main"): "the-secret-value"}, **dirs(tmp_path))
    assert names(built) == {"PATH", "MODEL_KEY", "BATON_PACKET_DIR", "BATON_RESULT_DIR"}
    assert built.env["MODEL_KEY"] == "the-secret-value"
    assert built.env["PATH"].split(os.pathsep) == system_path(PARENT)  # minimal system PATH, not the parent's
    assert built.secrets == ["MODEL_KEY"]


def test_allowlist_passes_base_list_and_env_allow(tmp_path):
    p = prof(auth={"mode": "cli_login"}, env_allow=["EDITOR"])
    built = build_env(p, home=tmp_path, environ=PARENT, **dirs(tmp_path))
    assert names(built) == {"PATH", "HOME", "LANG", "TERM", "EDITOR", "BATON_PACKET_DIR", "BATON_RESULT_DIR"}
    assert "FOO" not in built.env and "OPENAI_API_KEY" not in built.env


def test_inherit_passes_everything_and_keeps_parent_path(tmp_path):
    p = prof(auth={"mode": "cli_login"}, env_mode="inherit", path={"prepend": ["/first"]})
    built = build_env(p, home=tmp_path, environ=PARENT, **dirs(tmp_path))
    assert set(PARENT) <= names(built)
    assert built.env["PATH"].split(os.pathsep)[:3] == ["/first", "/parent/bin", "/usr/bin"]


def test_workspace_var_only_for_workspace_steps(tmp_path):
    p = prof(auth={"mode": "none"})
    assert "BATON_WORKSPACE" not in build_env(p, home=tmp_path, environ=PARENT, **dirs(tmp_path)).env
    built = build_env(p, home=tmp_path, environ=PARENT, workspace=tmp_path, **dirs(tmp_path))
    assert set(BATON_VARS) <= names(built)


# ---------------------------------------------------------------------------
# env_deny always wins
# ---------------------------------------------------------------------------


def test_env_deny_wins_over_inherit(tmp_path):
    p = prof(auth={"mode": "cli_login"}, env_mode="inherit", env_deny=["OPENAI_API_KEY"])
    built = build_env(p, home=tmp_path, environ=PARENT)
    assert "OPENAI_API_KEY" not in built.env and "OTHER_API_KEY" in built.env
    assert built.denied == ["OPENAI_API_KEY"]


def test_env_deny_wins_over_env_allow_and_patterns(tmp_path):
    p = prof(auth={"mode": "cli_login"}, env_allow=["OPENAI_API_KEY", "OTHER_API_KEY", "FOO"], env_deny=["*_API_KEY"])
    built = build_env(p, home=tmp_path, environ=PARENT)
    assert "FOO" in built.env
    assert not any(n.endswith("_API_KEY") for n in built.env)
    assert sorted(built.denied) == ["OPENAI_API_KEY", "OTHER_API_KEY"]


def test_env_deny_wins_over_injected_secrets(tmp_path):
    p = prof(auth={"mode": "api_key", "env": {"OPENAI_API_KEY": "secret:k"}}, env_deny=["OPENAI_API_KEY"])
    built = build_env(p, home=tmp_path, environ={secret_env_name("k"): "x" * 20})
    assert "OPENAI_API_KEY" not in built.env
    assert built.secrets == []


def test_describe_reports_names_never_values(tmp_path):
    p = prof(auth={"mode": "api_key", "env": {"MODEL_KEY": "secret:main"}}, env_deny=["FOO"], env_mode="inherit")
    built = build_env(p, home=tmp_path, environ={**PARENT, secret_env_name("main"): "the-secret-value"})
    text = repr(built.describe())
    assert "MODEL_KEY" in text and "FOO" in text
    for value in ("the-secret-value", "parent-key-value", "/home/me", "bar"):
        assert value not in text


# ---------------------------------------------------------------------------
# PATH resolution
# ---------------------------------------------------------------------------


def make_exe(d: Path, name: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def nvm(tmp_path) -> Path:
    root = tmp_path / "nvm"
    for v in ("v18.20.1", "v22.3.0", "v9.11.2"):
        (root / "versions" / "node" / v / "bin").mkdir(parents=True)
    return root


@pytest.mark.skipif(os.name != "posix", reason="POSIX executables")
def test_cli_found_only_under_nvm_resolves(tmp_path, nvm):
    exe = make_exe(nvm / "versions" / "node" / "v18.20.1" / "bin", "fakecli")
    p = prof(adapter="codex", auth={"mode": "cli_login"}, executable="fakecli", path={"search": ["nvm"]})
    built = build_env(p, home=tmp_path / "home", environ={"NVM_DIR": str(nvm), "HOME": str(tmp_path / "home")})
    assert built.resolved.executable == str(exe)
    assert built.resolved.how == "search:nvm"
    assert built.env["PATH"].split(os.pathsep)[0] == str(exe.parent)  # its directory goes first
    assert built.describe()["executable"] == str(exe)


@pytest.mark.skipif(os.name != "posix", reason="POSIX executables")
def test_nvm_newest_version_wins(tmp_path, nvm):
    make_exe(nvm / "versions" / "node" / "v9.11.2" / "bin", "fakecli")
    newest = make_exe(nvm / "versions" / "node" / "v22.3.0" / "bin", "fakecli")
    p = prof(adapter="codex", executable="fakecli", path={"search": ["nvm"]})
    r = resolve_executable(p, [], home=tmp_path, environ={"NVM_DIR": str(nvm)})
    assert r.executable == str(newest)  # numeric order: v22 > v18 > v9


@pytest.mark.skipif(os.name != "posix", reason="POSIX executables")
def test_home_nvm_and_explicit_dirs(tmp_path):
    home = tmp_path / "home"
    exe = make_exe(home / ".nvm" / "versions" / "node" / "v20.0.0" / "bin", "fromhome")
    p = prof(adapter="codex", executable="fromhome", path={"search": ["nvm"]})
    assert resolve_executable(p, [], home=home, environ={}).executable == str(exe)
    tool = make_exe(home / "tools" / "bin", "explicit")
    p = prof(adapter="codex", executable="explicit", path={"search": ["~/tools/bin"]})
    assert resolve_executable(p, [], home=home, environ={}).executable == str(tool)


@pytest.mark.skipif(os.name != "posix", reason="POSIX executables")
def test_base_path_and_absolute(tmp_path):
    exe = make_exe(tmp_path / "pre", "onpath")
    p = prof(adapter="codex", executable="onpath", path={"prepend": [str(tmp_path / "pre")]})
    built = build_env(p, home=tmp_path, environ={})
    assert built.resolved.how == "base_path" and built.resolved.executable == str(exe)
    p = prof(adapter="codex", executable=str(exe))
    assert resolve_executable(p, [], home=tmp_path, environ={}).how == "absolute"


def test_missing_cli_is_platform_failure_listing_every_path(tmp_path, nvm):
    p = prof(adapter="codex", executable="nowhere-cli", path={"search": ["nvm", "pyenv"], "prepend": ["/opt/pre"]})
    with pytest.raises(SetupError) as e:
        build_env(p, home=tmp_path / "home", environ={"NVM_DIR": str(nvm)})
    err = e.value
    assert err.code == "platform.executable_not_found" and err.failure_class == "platform"
    searched = err.detail["searched"]
    expected = ["/opt/pre", *system_path({})]
    expected += [str(nvm / "versions" / "node" / v / "bin") for v in ("v22.3.0", "v18.20.1", "v9.11.2")]
    expected += [str(tmp_path / "home" / ".nvm" / "versions" / "node" / "*" / "bin")]
    expected += [str(tmp_path / "home" / ".pyenv" / "versions" / "*" / "bin")]
    assert searched == expected
    for d in expected:
        assert d in str(err)


def test_unknown_search_source_rejected():
    raw = {"x": {"adapter": "codex", "vendor": "v", "executable": "c", "path": {"search": ["homebrew"]}}}
    _, issues = validate_profiles(raw, load_vocab("baton-capabilities/1"))
    assert [i.code for i in issues] == ["profile.unknown_search"]


def test_secret_only_in_auth_env():
    raw = {"x": {"adapter": "litellm_api", "vendor": "v", "model": "m", "options": {"api_key": "secret:k"}}}
    _, issues = validate_profiles(raw, load_vocab("baton-capabilities/1"))
    assert [i.code for i in issues] == ["profile.secret_outside_auth"]


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_secret_from_env_then_file(tmp_path):
    assert resolve_secret("my-key", tmp_path, {"BATON_SECRET_MY_KEY": "from-env-value"}) == "from-env-value"
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "my-key").write_text("from-file-value\n", encoding="utf-8")
    assert resolve_secret("my-key", tmp_path, {}) == "from-file-value"
    assert redact.redact_text("x from-file-value y") == "x [REDACTED] y"  # registered for redaction


def test_missing_secret_is_configuration_with_exact_fix(tmp_path):
    p = prof(auth={"mode": "api_key", "env": {"K": "secret:absent"}})
    with pytest.raises(SetupError) as e:
        build_env(p, home=tmp_path, environ={})
    assert e.value.failure_class == "configuration" and e.value.code == "configuration.missing_secret"
    assert "BATON_SECRET_ABSENT" in str(e.value) and str(tmp_path / "secrets" / "absent") in str(e.value)


def test_config_home_needs_adapter_variable(tmp_path):
    p = prof(auth={"mode": "cli_login", "config_home": "~/.baton/homes/x"})
    with pytest.raises(SetupError) as e:
        build_env(p, home=tmp_path, environ={})
    assert e.value.code == "configuration.config_home_unsupported"
    built = build_env(p, home=tmp_path, environ={}, config_home_var="TOOL_HOME")
    assert built.env["TOOL_HOME"].endswith(".baton/homes/x")
