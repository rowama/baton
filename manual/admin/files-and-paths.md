---
id: admin.files-and-paths
title: Files, folders and what to commit
audience: admin
order: 10
summary: Everything Baton writes, where, and whether it belongs in the repository.
related: [admin.secrets, admin.install-and-versions]
---

## Here, now {#here-now}

Commit what the process **is** and what it has **produced**; never commit who runs it or how they pay. A project's `.baton/` folder is committed (except its cache and local overrides); a machine's `~/.baton/` never is, and holds profiles, keys and logs.

## In the project {#project}

| Path | What | Commit? |
|---|---|---|
| `.baton/baton.lock` | Pinned runtime, format versions, recipe hashes | yes |
| `.baton/project.yaml` | Paths, project variables, permissions, hooks, limits, contacts. Never secrets: `secret:` references are refused here | yes |
| `.baton/communication.md` | How the owner likes to be told things | yes |
| `.baton/preferences.yaml` | Optional routing preferences | yes |
| `.baton/recipes/<id>@<version>/` | Vendored, pinned recipes | yes |
| `.baton/runs/<run>/` | Each run's event log, stored artifacts, step records | yes (redacted) |
| `.baton/project/`, `.baton/platform/`, `.baton/process/` | Project events, platform facts, process lessons | yes |
| `.baton/adoption/<run>/baseline.yaml` | An adoption's baseline proposal | yes |
| `.baton/.gitattributes` | `* -text`: git never converts line endings in hashed files | yes |
| `.baton/workers.local.yaml` | Project-specific profile overrides | **no** (gitignored) |
| `.baton/cache/` | SQLite cache, running markers, locks | **no** (gitignored) |
| `.agents/skills/baton-director/`, `.agents/skills/baton-worker/` | The assistants' instructions, vendored by `init` and `upgrade` | yes |
| `AGENTS.md` | A one-line pointer to the Director skill | yes |
| Published deliverables | Documents, drawings and photos at the project's own paths | yes |

## On the machine {#machine}

| Path | What |
|---|---|
| `~/.baton/workers.yaml` | The profiles you write; Baton never writes it |
| `~/.baton/workers/` | Generated profiles, one file each, written only by `baton workers setup` |
| `~/.baton/resources.yaml` | Declared accounts and setup state |
| `~/.baton/preferences.yaml` | Machine-level routing preferences (a project's override them) |
| `~/.baton/capability-states.yaml` | Each profile's capability states: likely, verified, absent |
| `~/.baton/listings/` | Cached provider model lists |
| `~/.baton/quota.yaml` | Routes whose quota is used up, and until when |
| `~/.baton/known-workers.local.yaml` | Your assessed models, merged over Baton's shipped data |
| `~/.baton/secrets/` | The file-based secret store (directory 0700, files 0600) |
| `~/.baton/hooks.yaml` | Machine-level completion hooks; may reference secrets |
| `~/.baton/mcp.yaml` | `token: secret:<name>`: the bearer token for `baton mcp --http` |
| `~/.baton/launcher.yaml` | Where the launcher installs versions from |
| `~/.baton/diag.yaml`, `~/.baton/diag/` | Diagnostics limits, and the diagnostics themselves (redacted) |
| `~/.baton/versions/` | Installed runtime versions |
| `~/.baton/logs/` | Unredacted raw worker output |
| `~/.baton/ui.json` | The running `baton ui`: URL, pid, start time (0600; removed on exit) |

`BATON_HOME` moves `~/.baton`. The full list of settings is in the [project settings reference](reference.project-settings#here-now).

## What stays out of the repository {#never-committed}

Worker profiles, secrets, machine-level hooks, raw logs, the cache and the running markers. Everything that is committed passes redaction first, and tests prove this with sentinel secrets across the working tree and git history. `baton check` verifies the hash chains, the stored blobs, the lockfile, the recipes and that no secret is present.
