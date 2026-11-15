---
id: admin.project-settings
title: Project settings
audience: admin
order: 40
summary: The settings in .baton/project.yaml, with the ones most projects change first.
related: [reference.project-settings, admin.files-and-paths, user.what-baton-may-do]
---

## Here, now {#here-now}

`.baton/project.yaml` holds the project's own, non-secret settings, and is committed. `baton init` writes it with safe defaults; most projects change only `paths`, `project.test_command` and, later, `policy` (with `permissions`) and `hooks`. Every setting is listed in the [project settings reference](reference.project-settings#here-now).

```yaml
paths: { specs: docs/specs, designs: docs/design, process_plans: docs, notes: docs }
project: { test_command: "pytest -q" }
permissions:
  push: { docs_only: allow, after_verified: allow, other: ask }
  tag: ask
```

> **Warning:** `project.yaml` is committed. Baton refuses a `secret:` reference in it; keep keys in the machine's [secret store](admin.secrets#where-keys-are-kept).

## Where deliverables go {#paths}

`paths` maps logical names to folders. A recipe publishes to a name (`{{ paths.specs }}/...`), never to a literal folder, so recipes stay portable. `init` maps `process_plans` and `notes` to `docs`. A recipe that publishes to a name your project has not mapped is reported as a gap and is never started; add the name.

## The test command {#test-command}

`project.test_command` is what a recipe's check runs, for example `pytest -q`. `project.preflight` is a quick command (such as `pytest -q --collect-only`) that `baton doctor` uses to confirm a coding assistant's permissions let the test command run. Other values under `project:` are available to recipes as `{{ project.<name> }}`.

## Permissions {#permissions}

`permissions` says what Baton and the assistant may do to the repository: `allow`, `ask` or `deny` for each of `push` (split by `docs_only`, `after_verified`, `other`), `tag`, `force_push`, `merge` and `deploy`. They are the release-authority part of the [project policy](#policy), and change the same way. See [what Baton may do](user.what-baton-may-do#here-now). `docs_only_globs` defines which paths count as documents only.

## Project policy {#policy}

The policy is the few rules every run follows: `policy.floors` (the lowest rating a recipe's axis may get), `policy.governing` (which recipe suits a kind of work) and `permissions`.

```yaml
policy:
  floors: { software-feature: { level: standard }, "*": { assurance: medium } }
  governing: [ { work: "software development", recipe: software-feature } ]
```

Policy changes are recorded: `baton policy set ... --note "<the owner's words>"` records the owner's decision, rewrites these blocks and commits them. `baton policy` lists each rule with the decision that last changed it. A floor must name an axis and value its recipe declares (a one-axis recipe's axis is `level`); a floor for `"*"` applies only to recipes that declare that axis with that value, and `baton check` warns when none does.

`policy.governing` is advice: `baton recipes` and the recipe list a part receives mark each governing recipe with the kinds of work it `governs`, and the assistant proposes it for such work, saying so when the owner picks another. Nothing is refused because of it.

Each run records the policy in force when it starts: its first sizing (triage) raises any rating below a floor to it, a re-sizing (`retriage`) applies the policy current at that time, and `baton status` and `board` mark a run still under an earlier policy. An adoption baseline carries ratings already raised (`floors_applied`), and refuses an edit below a floor. The permissions are never pinned: the recorded ones in force always apply.

A hand edit is noticed, not trusted: `baton check` warns (an error with `--strict`), `baton status`, `board` and `doctor` say so, and runs keep the last recorded policy until the owner confirms the edit (`baton policy confirm --note "<words>"`). `baton init` records the defaults it writes. A project from before the policy was recorded keeps `project.yaml` in force until its first record; `baton check` warns until then.

## Hooks {#hooks}

`hooks.on_complete`, `hooks.on_needs_human` and `hooks.on_platform_failure` are shell commands Baton runs when work finishes, needs the owner, or fails on the platform. They exist to wake an assistant that has ended its turn. They are committed, so they must hold no secrets; put a hook that needs a secret in `~/.baton/hooks.yaml`. See [waking an assistant](admin.directors#wake).

## Time, concurrency and commits {#limits}

- `effort.bands` is the time a helper gets for a piece of work of effort S, M or L (default 45 minutes, 2 hours, 4 hours); overdue work gets one extension when `extend_once` is true.
- `leases.minutes` is how long an assistant holds a piece of work without activity (60); it is renewed on activity.
- `limits.active_runs` caps how many pieces of work may be active at once.
- `checkpoints.commit` (on by default) commits the record of the work at checkpoints, to the current branch.
- `lfs.threshold_mb` is the size above which stored files go to git-lfs, when it is installed.
