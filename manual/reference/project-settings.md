---
id: reference.project-settings
title: Project settings reference
audience: admin
summary: Every setting in .baton/project.yaml, its type and default.
order: 20
generated: true
---

## Here, now {#here-now}

These are the keys of `.baton/project.yaml`, which is committed and never holds secrets. For the ones most projects change first, see [project settings](admin.project-settings#here-now).

| Key | Type | Default | What it does |
|---|---|---|---|
| `paths` | mapping | none | Logical folder names a recipe publishes to (`{{ paths.specs }}`), mapped to folders in the project. A name a recipe uses and the project has not mapped is reported as a gap. `init` maps `process_plans` and `notes` to `docs`. |
| `project` | mapping | none | Your own variables, available to recipes as `{{ project.<name> }}`. `test_command` is what a recipe's check runs; `preflight` is the quick command `baton doctor` uses to confirm an assistant's permissions let the tests run. |
| `run_slug` | text | `{{ run.inputs.title \| slugify }}` | How a piece of work's short name is made from its inputs, used in file names (a template; the default slugifies the title). |
| `leases.minutes` | whole number | `60` | How long an assistant holds a piece of work without activity. The hold is renewed on activity. |
| `checkpoints.commit` | yes/no | `true` | Commit the record of the work at checkpoints, to the current branch. |
| `lfs.threshold_mb` | number | `5` | Stored files larger than this go to git-lfs, when it is installed; otherwise they are committed directly. |
| `contacts` | mapping | none | Maps roles (`owner`, `platform`) to the people or assistants that fill them. |
| `effort.bands` | mapping | none | The time a helper gets for a piece of work of effort S, M or L, as durations such as `90s`, `45m`, `2h`. |
| `effort.extend_once` | yes/no | `true` | Give overdue work one extra band before it is stopped. |
| `effort.default` | S, M or L | `M` | The effort used by a part that declares none. |
| `hooks.on_complete` | text | empty | A shell command run when work finishes. Committed, so it holds no secrets; put one that needs a secret in `~/.baton/hooks.yaml`. |
| `hooks.on_needs_human` | text | empty | A shell command run when work is waiting on the owner. Falls back to `on_complete`. |
| `hooks.on_platform_failure` | text | empty | A shell command run when work fails because of the platform. Falls back to `on_complete`; on its own it wakes nobody for owner decisions. |
| `limits.active_runs` | whole number (optional) | none | The most pieces of work that may be active at once; `start` refuses beyond it. Unset means no limit. |
| `sme` | mapping | none | Per subject (`project`, `platform`, `process`), the profiles tried first when an expert is consulted: `preferred_profiles: [...]`. |
| `permissions.push.docs_only` | allow, ask or deny | `allow` | Pushing commits that change only documents (see `docs_only_globs`): `allow`, `ask` or `deny`. |
| `permissions.push.after_verified` | allow, ask or deny | `allow` | Pushing commits that are Baton checkpoints, or that a passed step's own checks vouched for. |
| `permissions.push.other` | allow, ask or deny | `ask` | Pushing anything else. |
| `permissions.tag` | allow, ask or deny | `ask` | Tagging a release. |
| `permissions.force_push` | allow, ask or deny | `deny` | Force-pushing. The default never does. |
| `permissions.merge` | allow, ask or deny | `deny` | Merging. The default never does. |
| `permissions.deploy` | allow, ask or deny | `deny` | Deploying. The default never does. |
| `docs_only_globs` | list | `["docs/**", "**/*.md", ".baton/runs/**", ".baton/project/**", ".baton/platform/**", ".baton/process/**"]` | Paths that count as documents only for `permissions.push.docs_only`. |
