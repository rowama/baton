---
id: admin.project-settings
title: Project settings
audience: admin
order: 40
summary: The settings in .baton/project.yaml, with the ones most projects change first.
related: [reference.project-settings, admin.files-and-paths, user.what-baton-may-do]
---

## Here, now {#here-now}

`.baton/project.yaml` holds the project's own, non-secret settings, and is committed. `baton init` writes it with safe defaults; most projects change only `paths`, `project.test_command` and, later, `permissions` and `hooks`. Every setting is listed in the [project settings reference](reference.project-settings#here-now).

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

`permissions` says what Baton and the assistant may do to the repository: `allow`, `ask` or `deny` for each of `push` (split by `docs_only`, `after_verified`, `other`), `tag`, `force_push`, `merge` and `deploy`. See [what Baton may do](user.what-baton-may-do#here-now). `docs_only_globs` defines which paths count as documents only.

## Hooks {#hooks}

`hooks.on_complete`, `hooks.on_needs_human` and `hooks.on_platform_failure` are shell commands Baton runs when work finishes, needs the owner, or fails on the platform. They exist to wake an assistant that has ended its turn. They are committed, so they must hold no secrets; put a hook that needs a secret in `~/.baton/hooks.yaml`. See [waking an assistant](admin.directors#wake).

## Time, concurrency and commits {#limits}

- `effort.bands` is the time a helper gets for a piece of work of effort S, M or L (default 45 minutes, 2 hours, 4 hours); overdue work gets one extension when `extend_once` is true.
- `leases.minutes` is how long an assistant holds a piece of work without activity (60); it is renewed on activity.
- `limits.active_runs` caps how many pieces of work may be active at once.
- `checkpoints.commit` (on by default) commits the record of the work at checkpoints, to the current branch.
- `lfs.threshold_mb` is the size above which stored files go to git-lfs, when it is installed.
