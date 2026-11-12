---
id: reference.environment
title: Environment variables
audience: admin
summary: The variables Baton reads, and the ones it sets for hooks and helpers.
order: 30
generated: true
---

## Here, now {#here-now}

Variables **you** may set, then the ones **Baton** sets for the programs it starts.

## Variables you set {#you-set}

| Variable | Meaning |
|---|---|
| `BATON_DIRECTOR` | A stable identity for the assistant, so its hold on a piece of work survives between turns. Default `<user>@<host>`. Same as `--director`. |
| `BATON_HARNESS` | Which assistant the Director runs in, for example `cloud-chat`. Default `cli`, meaning a terminal that stays attached. Shown in leases; `doctor` uses it. |
| `BATON_HOME` | Where the machine's `~/.baton` is (profiles, secrets, diagnostics, installed versions). Default `~/.baton`. |
| `BATON_OWNER_EXIT` | `0` makes the owner-needed case exit 0 instead of 4, for harnesses that treat any non-zero exit as failure; `needs_owner: true` is then the signal. |
| `BATON_PROJECT` | The project's root, instead of the nearest folder with `.baton/project.yaml`. Same as `--project`. |
| `BATON_SECRET_<NAME>` | The key of the account named `<name>` (upper-cased, other characters `_`). Looked up before the keyring and the secret file. |
| `BATON_SUPERVISOR_HEARTBEAT_S` | How often, in seconds, a running piece of work's supervisor writes its heartbeat. Default 30; for tests and unusual hosts. |
| `BATON_UV` | The `uv` executable the launcher uses to install a runtime version, when it is not on the path. |
| `BATON_VERSION` | Run this runtime version for one invocation, instead of the one `baton.lock` pins. |

## Variables Baton sets {#baton-sets}

| Variable | Meaning |
|---|---|
| `BATON_CLASSIFICATION` | To a completion hook: how a failure was classified, when it was. |
| `BATON_DISPATCH_ID` | To a completion hook: which hand-off the outcome came from. |
| `BATON_INCIDENT` | To a completion hook: the platform incident the outcome opened, if any. |
| `BATON_LAUNCHED` | Set by the launcher on the runtime it starts, so a hook or check that runs `baton` again does not loop. |
| `BATON_OUTCOME` | To a completion hook: `passed`, `gate_failed`, `needs_human`, `needs_review`, `timed_out`, `failed`, `overdue`, `not_started` or `answered`. |
| `BATON_PACKET_DIR` | To a helper: the folder holding what it is to work from. |
| `BATON_RECORD` | To a completion hook: the part's readable record, already regenerated. |
| `BATON_REPO` | To a completion hook: the project's root. |
| `BATON_RESULT_DIR` | To a helper: the folder it writes its result to. |
| `BATON_RUN_ID` | To a completion hook: the piece of work the outcome is about. |
| `BATON_STEP_PATH` | To a completion hook: the part of it. |
| `BATON_STEP_STATE` | To a completion hook: the part's state after the outcome. |
| `BATON_WORKSPACE` | To a helper working in the project: the working folder (only for parts that use the project's files). |
