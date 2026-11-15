---
id: 2026-11-project-policy
title: "A project sets a few rules every run follows: minimum ratings, who may release, and which recipe governs a kind of work"
status: done
level: major
decisions: ["0143", "0151", "0153", "0050", "0144", "0147"]
touches: [principles.md, design/recipes.md, design/runtime.md, design/director-interface.md, design/layouts.md, design/adoption-and-framing.md]
manual: [admin/project-settings.md, admin/director-commands.md, admin/recipes-and-vendoring.md, user/what-baton-may-do.md, user/answer-questions-and-decide.md, user/bring-an-existing-project.md, reference/project-settings.md, reference/commands.md]
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
- **Hand edits are noticed, not trusted silently.** If the policy in `project.yaml` differs from the last recorded one, `check` warns (an error under `--strict`), `status` says so, and the Director asks the owner. `policy confirm --note` records the edit as the owner's decision. Until it is confirmed, runs keep using the last recorded policy. A project with no record yet (one that predates policy) keeps `project.yaml` in force; `check` warns that the policy is not recorded and the Director asks the owner once.
- **Floors raise ratings.** When triage or re-triage rates an axis below a floor that applies to the run, the rating is raised to the floor. `complexity_set` (or `retriage_applied`) records `floors_applied [{axis, rated, floor, decision_id}]`, and the owner's triage prompt says which ratings project policy raised and why. A raised rating is never applied without the owner, because it is above the lowest.
- **Floors reach adopted runs.** An adoption baseline proposal (§11.5) carries ratings already raised to the floors, saying which were raised, and the run's `complexity_set` records `floors_applied`.
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

Checking the Design against the code raised two more, answered by the owner on 2026-11-14 as suggested and recorded in Decision [0153](../decisions/0153-policy-upgrade-and-baseline-floors.md):

7. Until a project's first policy record, `project.yaml` is in force, as before; `check` warns and the Director asks once.
8. Floors raise an adoption baseline's ratings when its proposal is built, so the owner approves the raised rating.

## Design

Approved by the owner with the Request on 2026-11-14, with the answers in Decision 0153.

### Shape

- **Format.**
  ```yaml
  policy:
    floors: { eng-process: { assurance: medium }, "*": { release: medium } }
    governing: [ { work: "software development", recipe: eng-process } ]
  permissions: { … }                 # release authority, unchanged (§13.7)
  ```
  The recorded policy is the canonical JSON of `policy` plus `permissions`, hashed. The project log's latest `policy_changed` holds the recorded value.
- **Enforcement.** Floors are applied where triage results are read in `engine.py` (`_triage_gate`, `_apply_triage`, `_apply_retriage`), after the worker's ratings are schema-checked and before the owner gate; the arithmetic (raise each rating to its floor on the axis's scale) is a helper in `tailoring.py`. The adoption baseline proposal applies the same helper (§11.5). Pinning is `run_started.policy_sha256`, with the policy blob in the project CAS.
- **Unrecorded edits.** `ProjectConfig` loading compares the file's policy hash with the recorded one. The result feeds `check`, `status` and `doctor`. Enforcement reads the recorded policy, never the file, until it is confirmed.
- **Permissions.** The runtime's own pushes and `permission()` read the recorded permissions. An `init`-written default counts as recorded, by `init`'s own `policy_changed {actor: init}`. A project with no `policy_changed` at all keeps the file in force until its first record (0153), and the Director asks for that confirmation once.

### Doc edits

- `principles.md` §2: **Project policy**.
- `design/recipes.md` §5.2 (`project.policy`; `catalog.summaries` marks governing recipes), §5.3 (`policy` is a reserved role), §5.5 (floors at triage and re-triage).
- `design/runtime.md` §8.2: `policy_changed`, `run_started.policy_sha256`, `floors_applied`.
- `design/director-interface.md` §13.1–§13.3 (`policy`, `policy set`, `policy confirm`; the skill's governing-recipe advice and confirm-back), §13.7 (permissions as release-authority policy, recorded changes).
- `design/layouts.md`: the `policy:` block in `project.yaml`.
- `design/adoption-and-framing.md` §11.5: baseline ratings raised to the floors.
- `docs/README.md`: new records.

### Manual edits

- `manual/admin/project-settings.md` and the generated `manual/reference/project-settings.md`: the `policy:` block; permissions now recorded.
- `manual/admin/director-commands.md` and the generated `manual/reference/commands.md`: `policy`, `policy set`, `policy confirm`.
- `manual/admin/recipes-and-vendoring.md`: the `project.policy` input and the reserved role name.
- `manual/user/what-baton-may-do.md`: release authority as project policy, and how to change it.
- `manual/user/answer-questions-and-decide.md`: a rating raised by project policy; confirming a hand edit.
- `manual/user/bring-an-existing-project.md`: a baseline size raised by the project's rules.

### Decisions

- [0143](../decisions/0143-project-policy.md) (accepted): the three policies, where they live, pinning, advisory governing recipe, the concept.
- [0050](../decisions/0050-action-permissions.md) (accepted): action permissions, kept and brought under policy.
- [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md) (accepted): the axes floors act on.
- [0151](../decisions/0151-project-policy-details.md) (accepted): permissions as release authority, hand edits, `"*"` floors, re-triage's policy, where governing recipes show, `project.policy`.
- [0153](../decisions/0153-policy-upgrade-and-baseline-floors.md) (accepted): the file is in force until the first record; floors raise baseline ratings.

## Plan

Request and Design approved 2026-11-14. Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: recorded policy

- **Outcome:** policy, permissions included, is listed, changed with a record, and hand edits are noticed.
- **Criteria:** `policy`, `policy set` and `policy confirm` through API, CLI and MCP; refusals (no words, bad floor); hand edit detected by `check` (warning, `--strict` error) and `status`; enforcement keeps the recorded policy until confirmed; `init` records its defaults; a project with no record keeps the file in force and is asked once.
- **Effort:** M

### Slice 2: floors and pinning

- **Outcome:** floors raise ratings at triage and re-triage; runs are pinned and report newer policy.
- **Criteria:** a rating below a floor is raised and recorded; the owner's prompt names it; a baseline proposal's ratings are raised and its `complexity_set` records it; all-lowest with a floor waits on the owner; `*` floors match by axis and value only; a one-axis floor; `run_started` hash; runs under older policy reported; re-triage takes the current policy.
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

### Request and Design approved

- **Summary:** Checked the Design against the code. Two gaps answered (0153): a project with no policy record keeps `project.yaml` in force until its first record, and floors raise adoption baseline ratings in the proposal. Corrected where floors are applied (`engine.py`, with a `tailoring.py` helper). Added `design/adoption-and-framing.md` to `touches:`. No code changed.
- **Owner decision:** 2026-11-14: approved the Request and Design with the suggested answers (0153).
- **Accepted:** Yes; status in-progress.

### Slice 1: recorded policy

- **Summary:** `project.yaml` has a `policy:` block (`floors`, `governing`; `models.PolicyConfig`), and with `permissions` it is the project policy. New `policy.py` holds its value (canonical JSON, hashed), the three states (`recorded`, `edited`, `unrecorded`), the rules with the decision that last set each, changes, floor checks and the rewrite of the two blocks. Api `policy`, `policy_set`, `policy_confirm`, CLI `baton policy [set|confirm]` and MCP tools. Both change calls record `human_decision {kind: policy}` and `policy_changed` (the value also in the project CAS), write `project.yaml` if needed and commit a project checkpoint. `init` records its defaults (`runtime:init`). `push` and `permission` enforce the recorded permissions (`Project.permissions_in_force`; `permissions.rule_for` now takes the permissions). `check` reports `policy.unconfirmed`/`policy.unrecorded` (errors under `--strict`) and `policy.floor`; `status`, `board` and `doctor` carry the notice. Added during the slice: `policy set` is refused while a hand edit is unconfirmed (`policy.unconfirmed_edit`), so the edit is never overwritten unseen; `check` judges the floors in force, not those of an unconfirmed edit. The Director skill and its §13.3 copy have a *Project policy* section.
- **Design docs:** `principles.md` §2 (Project policy); `design/director-interface.md` §13.1 (`policy` calls), §13.3 (skill), §13.5 (`check`), §13.7 (release authority is project policy; recorded policy in force); `design/runtime.md` §8.2 (`policy_changed`, `human_decision {kind: policy}`); `design/layouts.md`.
- **Manual:** `admin/project-settings.md` (permissions, new *Project policy* section), `admin/director-commands.md` (new *Project policy* section), `user/what-baton-may-do.md` (changing the rules; hand edits), `user/answer-questions-and-decide.md` (new *Confirming a change to the rules*), `context.yaml` (`policy` command), `reference-notes.yaml` (`policy.floors`, `policy.governing`), regenerated `reference/commands.md` and `reference/project-settings.md`, `anchors.yaml`.
- **Tests:** `tests/test_project_policy.py` (value and formatting, changes, floor problems, the rewrite; init's record; set with record, file, commit and enforcement; refusals; catalog, one-axis and `"*"` floors; a hand edit noticed by `check`/`--strict`/`status`/`board`, not enforced until confirmed; confirm checks floors; a project with no record keeps its file in force and is asked once; first change records; MCP). `test_director_surface.py` changes permissions with `policy set` instead of a hand edit, and lists the new calls; `test_versioning.py` counts the project log's lines (init now writes one event).

### Slice 2: floors and pinning

- **Summary:** `start_run` pins the policy in force (`run_started.policy_sha256`, its value in the project CAS; `policy.pin`). Floors are applied in `engine.py`'s triage path. `_triage_gate` and `_apply_triage` raise the worker's ratings to the floors (`policy.floored`; `floors_for` picks a recipe's own and matching `"*"` floors, the higher winning; `decision_for` names the decision that set each). This happens before the auto-approval rule, so a raised rating always waits on the owner. The gate's prompt says what policy raised (`policy.floor_note`). The gate, `complexity_set` and `retriage_applied` record `policy_sha256` and `floors_applied`. The first triage uses the pinned policy, a re-triage the current one; approval reuses the policy the gate was opened under. `status` carries `policy_outdated {pinned, current, message}` and `board` `policy_outdated: true` for a run under an earlier policy (`policy.pinned`: the latest re-triage's hash, else the start's). Adoption (0153): `adopt.propose` raises each work item's ratings (`baseline_floors`) and lists `floors_applied`. `check_baseline` refuses an owner edit below a floor. `apply_baseline`'s `complexity_set` records `policy_sha256` and the floors that raised the triage's ratings and that the baseline keeps. Added during the slice: refusing a baseline rating below a floor (the Design only said the proposal is raised), and `manual/user/bring-an-existing-project.md` (added to `manual:`).
- **Design docs:** `design/recipes.md` §5.5 (Floors); `design/runtime.md` §8.2 (`run_started.policy_sha256`, `complexity_set`/`retriage_applied`/triage gate `policy_sha256`, `floors_applied`), §8.9 (`run_started` fields); `design/adoption-and-framing.md` §11.5; `design/director-interface.md` §13.1 (`status`, `board`), §13.7 (Pinned per run).
- **Manual:** `user/answer-questions-and-decide.md` (a rating raised by your rules), `user/bring-an-existing-project.md`, `admin/project-settings.md` (pinning, baselines).
- **Tests:** `tests/test_project_policy.py`: a rating below a floor raised, recorded and named in the prompt; all-lowest with a floor waits; a run keeps its pinned policy, is reported under an earlier one, and a floor never lowers; re-triage applies the current policy and records its hash; a one-axis floor on `level`; a `"*"` floor only where the axis and value exist; a baseline proposal raised, an edit below the floor refused, and `complexity_set` recording it.

### Slice 3: governing recipes, `project.policy` and the manual

- **Summary:** `recipes()` marks each vendored recipe the policy names with `governs`, and lists under `governing` the kinds of work whose recipe is only in the catalog. The `catalog.summaries` input (`frame.recipe_listing(governing=…)`) marks `governs` from the policy pinned at the run's start. The Director skill (and its §13.3 copy) proposes the governing recipe, says the rules name it, and starts the owner's choice if they pick another; nothing is refused. `project.policy` is its own reference kind (`refs.py`, `policy`, matched before `project.<role>`), and resolves to the pinned policy (`{sha256, floors, governing, permissions}`); a run started before pinning cannot resolve it. A recipe may not name a role `policy` (`project_inputs.reserved_role`). Corrected during the slice: the Design named §5.7 for the summaries, but `catalog.summaries` is in §5.2; the reserved role name was added because `project.policy` shares its grammar with `project.<role>`.
- **Design docs:** `design/recipes.md` §5.2 (`project.policy`; `governs` in `catalog.summaries`), §5.3 (reserved role); `design/director-interface.md` §13.1 (`recipes()`), §13.3 (skill), §13.7 (the governing recipe is advice).
- **Manual:** `admin/project-settings.md` (governing is advice), `admin/recipes-and-vendoring.md` (`project.policy`, reserved role; added to `manual:`), `user/answer-questions-and-decide.md` (the three rules, and how to change one).
- **Tests:** `tests/test_project_policy.py`: `recipes` marks `governs` and lists catalog-only governing recipes; `catalog.summaries` in a packet marks them; `project.policy` gives the pinned policy with its hash; a step without the declaration gets no policy; `project.policy` parses as its own kind and `policy` is refused as a role name. `test_catalog_summaries.py` and `test_packet.py` stub `recipe_listing` with its new `governing` argument; the full suite on 9f71581 found a third stub (`test_continuity.py::test_records_golden`), fixed in the repair commit that follows.

### Done

- **Summary:** Every acceptance criterion is shown by `tests/test_project_policy.py`: policy listed and recorded (Slice 1); hand edits and projects with no record (Slice 1, 0153); floors at triage, re-triage and adoption, checked and pinned (Slice 2); release authority as recorded permissions (Slice 1); governing recipes as advice and `project.policy` (Slice 3); the manual and design docs (all slices). Left for `2026-11-project-review`: governing recipes in framing's and the project review's proposals (0151 #5).
- **Owner decision:** 2026-11-14: Request and Design approved (0153).
- **Accepted:** Yes; status done.
