---
id: admin.machine-settings
title: Machine settings and profiles
audience: admin
order: 50
summary: The files under ~/.baton that say which helpers a machine has, and how to write a profile by hand.
related: [admin.files-and-paths, user.choose-models, admin.accounts-and-costs]
---

## Here, now {#here-now}

A machine's helpers are described in `~/.baton`, never in a repository. Most owners never edit these files: `baton workers setup`, `baton workers connect` and the setup page write them. Edit by hand to add a helper Baton cannot discover, or to override one.

## Worker profiles {#profiles}

`~/.baton/workers.yaml` holds profiles you write; Baton never writes it. Generated profiles live in `~/.baton/workers/`, one file each. A project may override with the gitignored `.baton/workers.local.yaml`. A profile says how to run one helper and what it can do:

```yaml
claude-code-sub:                       # a coding assistant on its subscription login
  adapter: claude_code
  vendor: anthropic                    # used for reviewer independence
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }
  env_deny: [ANTHROPIC_API_KEY]        # a stray key would switch billing to the API
  path: { search: [nvm] }              # find CLIs installed under nvm

codex-sub:
  adapter: codex
  vendor: openai
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, long_form_writing, technical_reasoning]
  tier: strong
  auth: { mode: cli_login }
  env_deny: [OPENAI_API_KEY, CODEX_API_KEY]
  path: { search: [nvm] }

api-writer:                            # a model API call
  adapter: litellm_api
  vendor: some-vendor
  model: "<provider>/<model>"
  capabilities: [structured_output, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: api_key, env: { PROVIDER_API_KEY: "secret:provider_main" } }

owner:                                 # a person: the manual adapter
  adapter: manual
  vendor: human
  capabilities: [human_judgment, long_form_writing, vision, file_write]
```

| Field | Meaning |
|---|---|
| `adapter` | How it is run: `claude_code`, `codex`, `litellm_api`, `command` or `manual` |
| `vendor` | Who made the model; used to require a reviewer from a different maker |
| `capabilities` | What it can do, from Baton's capability vocabulary |
| `tier` | A rough capability level |
| `auth.mode` | `api_key` (resolved secrets injected), `cli_login` (the program's own stored login) or `none` |
| `env_deny` | Variables always removed, so a stray key cannot switch a login's billing |

A claimed capability is **likely** until work shows it **verified** or **absent** on this machine; `baton workers status` shows each one.

## Preferences {#preferences}

`~/.baton/preferences.yaml` (machine-wide) and `.baton/preferences.yaml` (per project, overriding) set routing preferences: cheapest or most proven first, and preferred models per capability. The setup page edits the machine file. See [choosing models](user.choose-models#here-now).

## Other machine files {#other-files}

- `~/.baton/hooks.yaml`: machine-level completion hooks; may reference secrets.
- `~/.baton/mcp.yaml`: `token: secret:<name>`, the bearer token for `baton mcp --http`.
- `~/.baton/launcher.yaml`: `source`, `extras` and `python` for the launcher.
- `~/.baton/diag.yaml`: diagnostics limits (`raw_days`, `raw_max_bytes`, `count_days`, `burst`).
- `~/.baton/known-workers.local.yaml`: models you have assessed, merged over Baton's shipped data.

The environment variables that also configure Baton are in the [environment reference](reference.environment#here-now).
