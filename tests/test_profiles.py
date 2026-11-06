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


# ---------------------------------------------------------------------------
# Identity and route (0075)
# ---------------------------------------------------------------------------


def _one(tmp_path, body: str):
    p = tmp_path / "workers.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_profiles(p)


def test_vendor_is_read_as_creator_and_model_identity_is_unknown(tmp_path):
    profiles = load_profiles_text(tmp_path, GUIDE_PROFILES)
    api = profiles["openai-api-strong"]
    assert api.creator == "openai" and api.vendor == "openai"
    # Nothing is inferred from the invocation string.
    assert api.model == "openai/some-model" and api.model_id is None and api.canonical_model() is None
    # A person's identity is the person.
    assert profiles["owner"].canonical_model() == "human/owner"


def load_profiles_text(tmp_path, text):
    p = tmp_path / "workers.yaml"
    p.write_text(text, encoding="utf-8")
    return load_profiles(p)


def test_identity_and_route_fields(tmp_path):
    profiles = _one(tmp_path, """
        direct:
          adapter: litellm_api
          creator: anthropic
          model_id: anthropic/claude-opus-5-5
          provider: anthropic
          model: anthropic/claude-opus-5-5
        routed:
          adapter: litellm_api
          creator: anthropic
          model_id: anthropic/claude-opus-5-5
          provider: openrouter
          resource: openrouter-main
          model: openrouter/anthropic/claude-opus-5.5
    """)
    d, r = profiles["direct"], profiles["routed"]
    assert d.canonical_model() == r.canonical_model() == "anthropic/claude-opus-5-5"
    assert (d.provider, d.model) != (r.provider, r.model) and r.resource == "openrouter-main"


@pytest.mark.parametrize(
    "fields, needle",
    [
        ("vendor: openai\n  creator: anthropic", "vendor is the old name for creator"),
        ("creator: openai\n  model_id: anthropic/claude", "must start with its creator"),
        ("creator: openai\n  model_id: GPT", "model_id"),
    ],
)
def test_identity_errors(tmp_path, fields, needle):
    with pytest.raises(ProfileError) as exc:
        load_profiles_text(tmp_path, f"x:\n  adapter: manual\n  {fields}\n")
    assert needle in str(exc.value)


def test_profile_hash_unchanged_by_the_creator_rename(tmp_path):
    from baton.packet import profile_sha256

    old = load_profiles_text(tmp_path, "w:\n  adapter: codex\n  vendor: openai\n  auth: { mode: cli_login }\n")["w"]
    new = load_profiles_text(tmp_path, "w:\n  adapter: codex\n  creator: openai\n  auth: { mode: cli_login }\n")["w"]
    assert profile_sha256(old) == profile_sha256(new)
    # The hash the runtime computed for this profile before 0075.
    assert profile_sha256(old) == "e157bee36af0325863fe4e5f3c0c1dea1c75d5ca9b9683c597aacf31b104dac9"
