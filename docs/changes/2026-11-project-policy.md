---
id: 2026-11-project-policy
title: "A project sets a few rules every run follows: minimum ratings, who may release, and which recipe governs a kind of work"
status: proposed
level: major
decisions: ["0143", "0151", "0050", "0144", "0147"]
touches: [principles.md, design/recipes.md, design/runtime.md, design/director-interface.md, design/layouts.md]
manual: [admin/project-settings.md, admin/director-commands.md, user/what-baton-may-do.md, user/answer-questions-and-decide.md, reference/project-settings.md, reference/commands.md]
---

# A project sets a few rules every run follows: minimum ratings, who may release, and which recipe governs a kind of work

## Request

### Problem

Project documents (`2026-11-project-documents`) let a run *see* what the project has settled. Some project-level decisions should also *constrain* every run: software work in this project is never rated below medium assurance; nothing is pushed or deployed without asking; software work here goes through eng-process. Today each run starts from scratch. Triage can under-rate a run however consequential the project, and a Director can start any recipe for any work. Only the action permissions in `project.yaml` (§13.7, Decision 0050) apply across runs, and nothing records who changed them or when.

The owner agreed the shape on 2026-11-13 (Decision [0143](../decisions/0143-project-policy.md), from `docs/catchall/project-process-linkage.md` §5 B):
- three policies to start: floors on tailoring axes, release authority, and the governing recipe for a kind of work;
- policy lives in `project.yaml` and changes only through a recorded owner decision;
- it is pinned at run start;
- the governing recipe is advisory, while floors and release authority are enforced;
- *project policy* is one new concept.

Tailoring axes (`2026-11-tailoring-axes`, done) supply the ratings that floors act on.

### Acceptance criteria

- **Policy is declared and listed.** `project.yaml` has a `policy:` block with `floors` and `governing`. `policy()` (CLI `baton policy`, MCP, API) shows the policy in force, release authority included, with the decision that last changed each part.
- **Changes are recorded.** `policy set …` (CLI, MCP, API) records `human_decision {kind: policy}` with the owner's words and `policy_changed {before, after, decision_id}` in the project log. It writes `project.yaml` and commits both as a project checkpoint. A change without words is refused.
- **Hand edits are noticed, not trusted silently.** If the policy in `project.yaml` differs from the last recorded one, `check` warns (an error under `--strict`), `status` says so, and the Director asks the owner. `policy confirm --note` records the edit as the owner's decision. Until it is confirmed, runs keep using the last recorded policy.
- **Floors raise ratings.** When triage or re-triage rates an axis below a floor that applies to the run, the rating is raised to the floor. `complexity_set` (or `retriage_applied`) records `floors_applied [{axis, rated, floor, decision_id}]`, and the owner's triage prompt says which ratings project policy raised and why. A raised rating is never applied without the owner, because it is above the lowest.
- **Floors are checked.** A floor naming an axis or value that the named recipe does not declare is refused when set. A floor for all recipes applies only to recipes that declare that axis with that value, and `check` warns when it matches no vendored recipe. A floor on a one-axis recipe uses the axis `level`.
- **Policy is pinned per run.** `run_started` records the policy's hash. Triage applies the floors pinned at start. When the policy changes later, `status` and `board` report the runs still under the older policy. Re-triage applies the policy current at the time and records the new hash.
- **Release authority is enforced as today, with a record.** The action permissions (§13.7) are the release-authority part of policy: `push`, `tag`, `merge`, `deploy` and `force_push` keep their meaning and enforcement. Changing them now goes through `policy set` and is recorded like any other policy change.
- **The governing recipe is advice the Director gives.** `governing` maps a plain description of a kind of work to a recipe. `catalog.summaries` and `recipes()` mark each governing recipe with the kinds of work it governs. The Director skill proposes the governing recipe for such work and says so when the owner picks another. The runtime never refuses a start because of it.
- **Recipes may read the policy.** A step may declare the input `project.policy`, the policy pinned at its run's start, for example a release step that must state its authority. Without the declaration, no packet changes.
- **Manual and design are current.** §2 lists the concept; §5.5, §8.2, §13.1–§13.3 and §13.7 describe it; the manual tells administrators how to set it and owners what it means for them.

### Open questions

None open. The six questions this change raised were answered by the owner on 2026-11-14 ("Accept all for B and D.") as suggested, and are recorded in Decision [0151](../decisions/0151-project-policy-details.md):

1. Release authority is the existing action permissions (§13.7), brought under the recorded-change rule; no second block.
2. A hand edit to the policy is detected, never refused; runs keep the last recorded policy until the owner confirms it.
3. A `"*"` floor applies only to recipes that declare that axis with that value; `check` warns when it matches nothing.
4. Re-triage applies the policy current at the time and records its hash.
5. Governing recipes show in `catalog.summaries`, `recipes()` and the Director skill now; in proposals with `2026-11-project-review`.
6. Workers see the policy only through a declared `project.policy` input.

## Design

For the owner's approval, with the Request (a major change: Request and Design are approved before the Plan is final).

### Shape

- **Format.**
  ```yaml
  policy:
    floors: { eng-process: { assurance: medium }, "*": { release: medium } }
    governing: [ { work: "software development", recipe: eng-process } ]
  permissions: { … }                 # release authority, unchanged (§13.7)
  ```
  The recorded policy is the canonical JSON of `policy` plus `permissions`, hashed. The project log's latest `policy_changed` holds the recorded value.
- **Enforcement.** Floors are applied in the triage application path that `complexity_set` and `retriage_applied` share (`tailoring.py`), after the worker's ratings are schema-checked and before the owner gate. Pinning is `run_started.policy_sha256`, with the policy blob in the project CAS.
- **Unrecorded edits.** `ProjectConfig` loading compares the file's policy hash with the recorded one. The result feeds `check`, `status` and `doctor`. Enforcement reads the recorded policy, never the file, until it is confirmed.
- **Permissions.** The runtime's own pushes and `permission()` read the recorded permissions. An `init`-written default counts as recorded, by `init`'s own `policy_changed {actor: init}`, so existing projects need one confirmation on upgrade, which the Director asks for.

### Doc edits

- `principles.md` §2: **Project policy**.
- `design/recipes.md` §5.2 (`project.policy`), §5.5 (floors at triage and re-triage), §5.7 (summaries mark governing recipes).
- `design/runtime.md` §8.2: `policy_changed`, `run_started.policy_sha256`, `floors_applied`.
- `design/director-interface.md` §13.1–§13.3 (`policy`, `policy set`, `policy confirm`; the skill's governing-recipe advice and confirm-back), §13.7 (permissions as release-authority policy, recorded changes).
- `design/layouts.md`: the `policy:` block in `project.yaml`.
- `docs/README.md`: new records.

### Manual edits

- `manual/admin/project-settings.md` and the generated `manual/reference/project-settings.md`: the `policy:` block; permissions now recorded.
- `manual/admin/director-commands.md` and the generated `manual/reference/commands.md`: `policy`, `policy set`, `policy confirm`.
- `manual/user/what-baton-may-do.md`: release authority as project policy, and how to change it.
- `manual/user/answer-questions-and-decide.md`: a rating raised by project policy; confirming a hand edit.

### Decisions

- [0143](../decisions/0143-project-policy.md) (accepted): the three policies, where they live, pinning, advisory governing recipe, the concept.
- [0050](../decisions/0050-action-permissions.md) (accepted): action permissions, kept and brought under policy.
- [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md) (accepted): the axes floors act on.
- [0151](../decisions/0151-project-policy-details.md) (accepted): permissions as release authority, hand edits, `"*"` floors, re-triage's policy, where governing recipes show, `project.policy`.

## Plan

Slices as proposed; refined, if needed, once the Request and Design are approved. Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: recorded policy

- **Outcome:** policy, permissions included, is listed, changed with a record, and hand edits are noticed.
- **Criteria:** `policy`, `policy set` and `policy confirm` through API, CLI and MCP; refusals (no words, bad floor); hand edit detected by `check` (warning, `--strict` error) and `status`; enforcement keeps the recorded policy until confirmed; `init` records its defaults; an upgraded project is asked once.
- **Effort:** M

### Slice 2: floors and pinning

- **Outcome:** floors raise ratings at triage and re-triage; runs are pinned and report newer policy.
- **Criteria:** a rating below a floor is raised and recorded; the owner's prompt names it; all-lowest with a floor waits on the owner; `*` floors match by axis and value only; a one-axis floor; `run_started` hash; runs under older policy reported; re-triage takes the current policy.
- **Effort:** M

### Slice 3: governing recipes, `project.policy` and the manual

- **Outcome:** the Director advises the governing recipe, recipes can read the policy, and the manual is complete.
- **Criteria:** summaries and `recipes()` mark governing recipes; skill text and its §13.3 copy; `project.policy` resolves to the pinned policy and is absent from packets that don't declare it; manual topics and generated references updated.
- **Effort:** S

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0143 and `docs/catchall/project-process-linkage.md` (§5 B), against what `2026-11-project-documents` and `2026-11-tailoring-axes` built. Found that release authority already exists as action permissions (§13.7), so the proposal brings them under policy instead of adding a second mechanism. No code changed.
- **Owner decision:** 2026-11-14, "Write the B, D, E and F change proposals". The Request is not yet accepted; the open questions above are unanswered.
- **Accepted:** No; proposal only.

### Open questions answered

- **Summary:** The six questions the proposal raised were answered as suggested and recorded as Decision 0151. The Request has no open questions; the Design is ready for approval. No code changed.
- **Owner decision:** 2026-11-14, "Accept all for B and D." (0151).
- **Accepted:** Request and Design await the owner's approval.
