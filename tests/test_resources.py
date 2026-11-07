"""The worker resource manager: resources.yaml, discovery inputs, profile generation, verification (§6.4; 0077–0082)."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from baton import resources
from baton.project import Project, init
from baton.resources import Detection, ResourcesError

TODAY = dt.date(2026, 11, 6)


def found(*providers: str, logged_in: bool = True):
    def fn(home, data):
        out = {}
        for p in ("claude_code", "codex"):
            if p in providers:
                out[p] = Detection(p, p, True, f"/usr/bin/{p}", "cli_login" if logged_in else "none",
                                   problem=None if logged_in else "installed but not logged in")
            else:
                out[p] = Detection(p, p, False, problem="not installed here")
        return out
    return fn


def never(home, name, profile):  # pragma: no cover - must not be called
    raise AssertionError("no live check was asked for")


def run_setup(home, discover=found(), verify=None, verifier=never):
    return resources.setup(home, verify=verify, today=TODAY, discover_fn=discover, verifier=verifier)


def gen(home: Path, name: str) -> dict:
    return yaml.safe_load((home / "workers" / f"{name}.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def test_detected_harnesses_become_profiles_and_missing_ones_say_why(home):
    out = run_setup(home, found("codex"))
    assert out["written"] == ["codex"]
    reasons = {s["route"]: s["reason"] for s in out["skipped"]}
    assert reasons["claude_code (default model)"] == "not installed here"
    body = gen(home, "codex")
    # A harness default is a mutable alias: creator, no model identity (0075).
    assert body["creator"] == "openai" and "model_id" not in body and body["auth"] == {"mode": "cli_login"}
    assert body["env_deny"] == ["OPENAI_API_KEY", "CODEX_API_KEY"]
    assert body["generated"]["availability"] == "detected" and "verified" not in body["generated"]
    assert resources.ownership(body) == "untouched"



def test_a_harness_can_be_pinned_to_a_model(home):
    out = run_setup(home, found("claude_code"))
    assert sorted(out["written"]) == ["claude-code", "claude-code-claude-opus-5-5", "claude-code-claude-sonnet-5-5"]
    opus = gen(home, "claude-code-claude-opus-5-5")
    # The identity is the model's; the route is the harness, with the model passed as --model.
    assert opus["adapter"] == "claude_code" and opus["provider"] == "claude_code"
    assert opus["model_id"] == "anthropic/claude-opus-5-5" and opus["model"] == "claude-opus-5-5"
    assert opus["creator"] == "anthropic" and opus["auth"] == {"mode": "cli_login"}
    assert opus["env_deny"] == ["ANTHROPIC_API_KEY"]
    assert {"shell", "file_write", "repo_workspace", "technical_reasoning"} <= set(opus["capabilities"])
    assert opus["tier"] == "strong" and gen(home, "claude-code-claude-sonnet-5-5")["tier"] == "standard"
    # The default-model profile stays an alias, with no model identity.
    default = gen(home, "claude-code")
    assert "model" not in default and "model_id" not in default


def test_a_pinned_harness_profile_runs_its_model(home, tmp_path):
    from baton.adapters import ADAPTERS
    from baton.models import WorkerProfile

    run_setup(home, found("claude_code"))
    body = gen(home, "claude-code-claude-sonnet-5-5")
    profile = WorkerProfile.model_validate({k: v for k, v in body.items()})
    argv = ADAPTERS["claude_code"].argv("claude", "do it", [], profile)
    assert argv[-2:] == ["--model", "claude-sonnet-5-5"]


def test_not_logged_in_is_not_a_profile(home):
    out = run_setup(home, found("claude_code", logged_in=False))
    assert out["written"] == [] and any("not logged in" in s["reason"] for s in out["skipped"])


def test_direct_and_intermediary_share_identity_not_credentials(home):
    resources.declare(home, "anthropic-key", provider="anthropic", credential="secret:anthropic_main")
    resources.declare(home, "openrouter-main", provider="openrouter", credential="secret:openrouter_main")
    out = run_setup(home)
    assert {"anthropic-key-claude-opus-5-5", "anthropic-key-claude-sonnet-5-5", "openrouter-main-claude-opus-5-5"} <= set(out["written"])
    direct, routed = gen(home, "anthropic-key-claude-opus-5-5"), gen(home, "openrouter-main-claude-opus-5-5")
    assert direct["model_id"] == routed["model_id"] == "anthropic/claude-opus-5-5"
    assert direct["model"] != routed["model"] and direct["provider"] != routed["provider"]
    assert direct["auth"]["env"] == {"ANTHROPIC_API_KEY": "secret:anthropic_main"}
    assert routed["auth"]["env"] == {"OPENROUTER_API_KEY": "secret:openrouter_main"} and routed["resource"] == "openrouter-main"
    assert routed["generated"]["availability"] == "declared"
    # Credentials appear only as references, in profiles and in resources.yaml.
    for p in [*(home / "workers").glob("*.yaml"), home / "resources.yaml"]:
        text = p.read_text(encoding="utf-8")
        assert "sk-" not in text


def test_a_model_allowlist_limits_what_an_account_gets(home):
    resources.declare(home, "anthropic-key", provider="anthropic", credential="secret:k", models=["anthropic/claude-sonnet-5-5"])
    out = run_setup(home)
    assert "anthropic-key-claude-sonnet-5-5" in out["written"] and "anthropic-key-claude-opus-5-5" not in out["written"]


@pytest.mark.parametrize(
    "body, code",
    [
        ({"provider": "openrouter", "credential": "sk-or-123"}, "resources.literal_credential"),
        ({"provider": "openrouter", "capabilities": ["vision"]}, "resources.capability"),
    ],
)
def test_declarations_are_checked(home, body, code):
    with pytest.raises(ResourcesError) as e:
        resources.declare(home, "x", **{k: v for k, v in body.items()})
    assert code in {i.code for i in e.value.issues}
    assert not (home / "resources.yaml").exists()


def test_the_file_names_each_resource_kind(home):
    (home / "resources.yaml").write_text("format: baton-resources/1\nresources:\n  a: {provider: openrouter}\n  b: {kind: storage, provider: s3}\n", encoding="utf-8")
    with pytest.raises(ResourcesError) as e:
        resources.status(home, discover_fn=found())
    assert {i.code for i in e.value.issues} == {"resources.no_kind", "resources.unknown_kind"}
    assert "worker" in str(e.value)


def test_a_declared_machine_dependent_capability_is_added(home):
    resources.declare(home, "claude-here", provider="claude_code", capabilities=["loopback_network"])
    run_setup(home, found("claude_code"))
    assert "loopback_network" in gen(home, "claude-code")["capabilities"]
    run_setup(home, found("codex"))
    assert "loopback_network" not in gen(home, "codex")["capabilities"]  # declared for claude_code only


def test_owner_profiles_are_never_touched(home):
    (home / "workers.yaml").write_text("codex:\n  adapter: codex\n  creator: openai\n  auth: { mode: cli_login }\n", encoding="utf-8")
    (home / "workers").mkdir()
    mine = "adapter: claude_code\ncreator: anthropic\nauth: { mode: cli_login }\n"
    (home / "workers" / "claude-code.yaml").write_text(mine, encoding="utf-8")
    out = run_setup(home, found("codex", "claude_code"))
    # Only the pinned-model profiles, which no owner file claims, are written.
    assert sorted(out["written"]) == ["claude-code-claude-opus-5-5", "claude-code-claude-sonnet-5-5"]
    assert {c["profile"] for c in out["collisions"]} == {"codex", "claude-code"}
    assert (home / "workers" / "claude-code.yaml").read_text(encoding="utf-8") == mine
    assert not (home / "workers" / "codex.yaml").exists()


def test_verification_only_when_asked(home):
    calls = []

    def ok(h, name, profile):
        calls.append(name)
        return True, "ok"

    def bad(h, name, profile):
        return False, "platform (auth_failed): not logged in"

    run_setup(home, found("codex"))  # no verify: never calls the verifier
    out = run_setup(home, found("codex", "claude_code"), verify=["claude-code"], verifier=bad)
    assert out["failed"] == [{"profile": "claude-code", "reason": "platform (auth_failed): not logged in"}]
    assert not (home / "workers" / "claude-code.yaml").exists()  # a failed new profile is not written
    out = run_setup(home, found("codex"), verify=[], verifier=ok)
    assert calls == ["codex"] and out["verified"] == ["codex"]
    marker = gen(home, "codex")["generated"]
    assert marker["verified"]["date"] == "2026-11-06" and resources.ownership(gen(home, "codex")) == "untouched"


def test_generated_profiles_load_are_eligible_unverified_and_yield_to_the_owner(home, tmp_path):
    run_setup(home, found("codex", "claude_code"))
    root = tmp_path / "proj"
    root.mkdir()
    init(root, bare=True)
    profiles = Project.open(root, home=home).profiles()
    assert {"codex", "claude-code"} <= set(profiles)  # unverified, still usable (0081)
    from baton.packet import profile_sha256

    h = profile_sha256(profiles["codex"])
    (home / "workers.yaml").write_text("codex:\n  adapter: codex\n  creator: openai\n  tier: basic\n  auth: { mode: cli_login }\n", encoding="utf-8")
    assert Project.open(root, home=home).profiles()["codex"].tier == "basic"  # workers.yaml wins by name
    # The marker is not part of the profile's hash.
    body = gen(home, "codex")
    body.pop("generated")
    from baton.models import WorkerProfile

    assert profile_sha256(WorkerProfile.model_validate(body)) == h


def test_setup_state_is_machine_wide(home):
    st = resources.status(home, discover_fn=found("codex"))
    assert st["setup_complete"] is False and st["available_not_generated"] == ["codex"]
    run_setup(home, found("codex"))
    resources.declare(home, nothing_more=True)
    st = resources.status(home, discover_fn=found("codex"))
    assert st["setup_complete"] is True and st["setup"]["nothing_more"] is True and st["unverified"] == ["codex"]


def test_cli_declare_needs_no_project(home, tmp_path):
    env = {**os.environ, "BATON_HOME": str(home)}
    r = subprocess.run([sys.executable, "-m", "baton", "workers", "declare", "openrouter-main", "--provider", "openrouter",
                        "--credential", "secret:openrouter_main", "--json"], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["declared"] == "openrouter-main"
    r = subprocess.run([sys.executable, "-m", "baton", "workers", "declare", "x", "--provider", "openrouter", "--credential", "sk-1", "--json"],
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode != 0 and "secret:<name>" in r.stdout
