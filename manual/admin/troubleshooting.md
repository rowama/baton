---
id: admin.troubleshooting
title: Troubleshooting and diagnostics
audience: admin
order: 80
summary: Use doctor, check and the diagnostics channel to find out what is wrong on a machine or a repository.
related: [user.when-something-is-wrong, admin.directors, reference.diagnostics]
---

## Here, now {#here-now}

Three commands, in this order:

```baton
baton doctor
baton check
baton diag
```

- `doctor` checks **this machine**: each helper's environment, executable, login mode and a no-op round trip, and whether a coding assistant's permissions let the project's test command run. One line when healthy.
- `check` checks **the repository**, for a pre-commit hook or CI: hash chains, stored blobs, the lockfile, recipe lint and that no secret is present. Exit 0 when clean; `--strict` treats drift of published deliverables as an error.
- `diag` reports the **conditions Baton worked around**, which no one else sees.

## doctor {#doctor}

`baton doctor --no-run` skips the no-op round trips, so it makes no model calls. `--profile <name>` checks one helper. Findings are **PROBLEM** (nothing will work until fixed) or **WARNING** (it works, but know this). Common ones:

| Finding | Meaning and fix |
|---|---|
| no worker on this machine is ready yet | No helper is usable. Connect a subscription or account: `baton workers setup`, or the setup page |
| no healthy profile can do `<recipe>/<step>` | Nothing here has the capabilities that part needs. Connect more helpers, or check `baton workers status` for what is missing |
| no completion hook would wake a Director | The assistant may end its turn and never notice finished work. See [waking an assistant](admin.directors#wake) |
| `director_sandboxed` | The assistant's own sandbox blocks Baton. See [setting up Codex](admin.directors#codex) |
| a login profile would bill an API key | A key in the environment would override a subscription login. It is removed by `env_deny`; check the profile |
| open platform incident | A failure classified as the platform's, not the work's. Ask the platform expert, or see `baton diag` |

## check {#check}

Run it in CI and as a pre-commit hook. It fails on a broken hash chain, a stored blob that does not match its hash, a missing `.baton/.gitattributes` rule, a vendored recipe that no longer matches its pinned hash, or a secret in a committed file.

## Diagnostics {#diagnostics}

When Baton works around something (an unreadable file, a failed provider read, a keyring problem) it records a diagnostic in `~/.baton/diag/` instead of failing or staying silent. Records are redacted, bounded and kept only on this machine.

```baton
baton diag
baton diag --since 7 --code listings
baton diag --records --limit 20
```

`--since` takes a number of days or a date; `--code` filters by a code prefix; `--run` by a piece of work. Limits are set in `~/.baton/diag.yaml`. `baton doctor` says so when diagnostics become unusual. Every code is described in the [diagnostics reference](reference.diagnostics#here-now).

## Exit codes {#exit-codes}

See [exit codes](admin.directors#exit-codes).

## Reports and logs {#logs}

Raw worker output is in `~/.baton/logs/` (unredacted, local only). A run's own record is under `.baton/runs/<run>/`, and `baton explain` and `baton trace` read it back.
