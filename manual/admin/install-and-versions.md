---
id: admin.install-and-versions
title: Install, versions and upgrades
audience: admin
order: 5
summary: How Baton is installed, how a project pins its version, and how to upgrade or try a new one safely.
related: [admin.files-and-paths, admin.troubleshooting]
---

## Here, now {#here-now}

Baton needs Python 3.11 or newer, git and [uv](https://docs.astral.sh/uv/). Install the `baton` command once per machine; it is a **launcher** that runs the exact Baton version each project pins in `.baton/baton.lock`, installing that version under `~/.baton/versions/` on first use. Two projects on two versions work side by side.

```baton
baton --version
```

## Install {#install}

One command with uv, naming the extras you want:

| Extra | Adds |
|---|---|
| `api` | Model-API workers (through LiteLLM) |
| `mcp` | `baton mcp`, for an assistant that connects over MCP |
| `keyring` | The OS keyring as a secret store |

The launcher's default extras include `api` and `keyring`, so an installed runtime can connect API accounts without further steps. Use a different install source or extras with `~/.baton/launcher.yaml` (`source`, `extras`, `python`; `source` may be a URL template with `{version}`).

## How the launcher picks a version {#launcher}

1. It finds the project: `--project`, `BATON_PROJECT`, or the nearest folder with `.baton/project.yaml`.
2. It reads `runtime` from `.baton/baton.lock` and, when that is not the running version, installs it with uv and runs it instead.
3. `BATON_VERSION` overrides the pin for one invocation.

The re-run process is marked (`BATON_LAUNCHED`) so a hook or script gate that starts Baton again does not loop. Outside a project the launcher runs its own version.

## Upgrade {#upgrade}

```baton
baton upgrade --to <version>
```

This pins a runtime version in `baton.lock` and re-vendors the Director's skills. Nothing else changes. Stored files are versioned; a runtime reads the current and previous version of each format, and refuses older ones with a hint to run:

```baton
baton migrate --dry-run
baton migrate
```

## Try a new version on a branch {#try-a-version}

Use a separate worktree so the trial is a branch, not a risk:

```sh
git worktree add ../my-project-trial -b baton-trial
cd ../my-project-trial
baton upgrade --to <version>
```

Run real work there. To keep it, merge the branch; to drop it, delete the branch and the worktree. Each worktree has its own `.baton/cache/`, so two worktrees run two versions at once.

## The manual matches the version {#manual-version}

The manual ships inside the runtime, so `baton help` and `baton ui` show the documentation for the version the project pins, and work offline.
