from __future__ import annotations

import textwrap

import pytest

from baton.profiles import ProfileError, load_profiles

GUIDE_PROFILES = textwrap.dedent(
    """
    openai-api-strong:
      adapter: litellm_api
      vendor: openai
      model: "openai/some-model"
      capabilities: [structured_output, long_form_writing, technical_reasoning, tool_use]
      tier: strong
      context_tokens: 200000
      auth: { mode: api_key, env: { OPENAI_API_KEY: "secret:openai_main" } }
    codex-sub:
      adapter: codex
      vendor: openai
      capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read]
      tier: strong
      auth: { mode: cli_login }
      env_deny: [OPENAI_API_KEY, CODEX_API_KEY]
      executable: codex
      path: { search: [nvm] }
      args: { write: ["--sandbox", "workspace-write"], read: ["--sandbox", "read-only"] }
    owner:
      adapter: manual
      vendor: human
      person: owner
      capabilities: [human_judgment, long_form_writing, vision, file_write]
      tier: strong
    """
)


def test_guide_profiles_load(tmp_path):
    p = tmp_path / "workers.yaml"
    p.write_text(GUIDE_PROFILES, encoding="utf-8")
    profiles = load_profiles(p)
    assert set(profiles) == {"openai-api-strong", "codex-sub", "owner"}
    assert profiles["codex-sub"].auth.mode == "cli_login"


def test_unknown_capability_rejected(tmp_path):
    p = tmp_path / "workers.yaml"
    p.write_text(GUIDE_PROFILES.replace("vision, file_write", "vision, telepathy"), encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profiles(p)
    assert exc.value.codes() == {"vocab.unknown_capability"}
    assert "owner" in str(exc.value)


def test_unknown_tier_and_field_rejected(tmp_path):
    p = tmp_path / "workers.yaml"
    p.write_text(GUIDE_PROFILES.replace("tier: strong\n  auth: { mode: cli_login }", "tier: mythic\n  auth: { mode: cli_login }").replace("person: owner", "persona: owner"), encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profiles(p)
    assert exc.value.codes() == {"vocab.unknown_tier", "profile.invalid"}
