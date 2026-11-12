---
id: admin.directors
title: Setting up an AI assistant (the Director)
audience: admin
order: 70
summary: Connect an assistant to Baton, wake it when work finishes, and read Baton's exit codes.
related: [admin.troubleshooting, user.when-something-is-wrong, user.long-running-work]
---

## Here, now {#here-now}

The **Director** is the AI assistant the owner talks to. Any assistant that can run `baton` in a shell on this machine, or reach `baton mcp`, can act as one, given the `baton-director` skill that `baton init` copies into `.agents/skills/`. Three things to set up: how it reaches Baton, how it is woken, and its identity.

## How it reaches Baton {#reach}

- **A shell on the machine.** The assistant runs `baton ...` with `--json` for machine-readable output.
- **MCP.** `baton mcp` serves the same calls as tools over stdio. Prefer it even when a shell exists, because an assistant that sandboxes its shell usually runs MCP tools outside the sandbox. `baton mcp --http` serves HTTP on loopback only and needs the bearer token from `~/.baton/mcp.yaml`.

## Codex {#codex}

Codex sandboxes the commands it runs: in its default mode they can change only the project folder and usually cannot reach the internet. Baton keeps files in `~/.baton` and its helpers need the internet, so connect Baton as an MCP tool:

```sh
codex mcp add baton -- baton mcp
```

Codex asks before every MCP call unless told otherwise, and `codex mcp add` has no option for that. Add one line under the `[mcp_servers.baton]` section it wrote, in `~/.codex/config.toml`, then restart Codex:

```toml
default_tools_approval_mode = "approve"
```

Without this, `baton detect` from a sandboxed shell stops with `director_sandboxed` and this fix.

## Identity and environment {#environment}

| Variable | Meaning |
|---|---|
| `BATON_DIRECTOR` | A stable identity for the assistant (default `<user>@<host>`), so its hold on a piece of work survives between turns |
| `BATON_HARNESS` | Which assistant it runs in (for example `cloud-chat`; default `cli`, meaning a terminal that stays attached) |
| `BATON_OWNER_EXIT` | `0` makes the "owner is needed" case exit 0 instead of 4 |

The rest are in the [environment reference](reference.environment#here-now).

## Waking an assistant that ended its turn {#wake}

An assistant in a terminal can wait until work is recorded. One that ends its turn while work runs (a cloud chat agent with a shell on this machine) is brought back only by a **completion hook**, or by its own harness if that really wakes it. Without one, nobody notices when the work finishes. Before it starts work, the assistant checks whether a hook would wake it; with none, it stays attached, or first tells the owner it might not notice. `baton dispatch`, `baton ask-sme` and `baton doctor` warn when no hook would wake it.

Hooks go in `.baton/project.yaml` (committed, no secrets) or `~/.baton/hooks.yaml` (this machine; `secret:` values allowed). Each hook gets `BATON_RUN_ID`, `BATON_STEP_PATH` and `BATON_OUTCOME` (`passed`, `needs_human`, `failed`, and so on). `on_needs_human` falls back to `on_complete`; `on_platform_failure` alone wakes nobody for owner decisions.

A webhook that wakes a remote agent, in `~/.baton/hooks.yaml`:

```yaml
hooks:
  on_complete: "curl -fsS -m 20 -X POST -d run=$BATON_RUN_ID -d step=$BATON_STEP_PATH -d outcome=$BATON_OUTCOME secret:director_wake_url"
```

A local inbox file, in `.baton/project.yaml`:

```yaml
hooks:
  on_complete: "printf '%s %s %s\\n' \"$BATON_RUN_ID\" \"$BATON_STEP_PATH\" \"$BATON_OUTCOME\" >> .baton/cache/inbox.log"
```

## Exit codes {#exit-codes}

| Exit | Meaning |
|---|---|
| 0 | Done; nothing needs the owner |
| 1 | A problem: the call was refused or the work failed |
| 2 | Usage: bad arguments, or a `BATON_OWNER_EXIT` other than `0` or `4` |
| 3 | The piece of work's hold is with another assistant |
| 4 | **Finished, and the owner is needed now.** Not a failure: a decision, approval or question waits on the owner |

Some harnesses show any non-zero exit as failed. For those, set `BATON_OWNER_EXIT=0`: the owner-needed case then exits 0 and `needs_owner: true` in the JSON is the signal. MCP tools have no exit codes and always return `needs_owner`.
