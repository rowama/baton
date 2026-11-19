---
id: 2026-11-builder-context-and-locks
title: "Recipe builder takes reference documents, an approved set of files stays as approved, and a recipe can be retired"
status: in-progress
level: standard
decisions: ["0173", "0172", "0142", "0037", "0149"]
touches: [design/recipes.md, design/gates-and-reviews.md, design/runtime.md, design/adoption-and-framing.md, design/director-interface.md]
manual: [recipe-sources/recipe-builder.md, recipes/recipe-builder.md, anchors.yaml, admin/recipes-and-vendoring.md, user/answer-questions-and-decide.md, reference/commands.md]
---

# Recipe builder takes reference documents, an approved set of files stays as approved, and a recipe can be retired

## Request

### Problem

Writing [2026-11-software-recipe](2026-11-software-recipe.md) found three things Baton lacks (checked against `36352e7`). Each is small and general, so they are a change of their own, which `2026-11-software-recipe` waits on:

- **recipe-builder cannot take reference documents.** Its run inputs are a title, the idea in words, an optional fit-check profile and a base recipe; its only project role is `examples`. An owner who has an existing process written down (a procedures manual, a checklist, an earlier kit) cannot give it to the builder except by pasting it into the idea. `quick-run` already has a `context` role for this.
- **Approved files are not protected after approval.** §9.4 compares protected files only between one attempt's dispatch and its intake; recording the set when the owner approves it, so later steps must preserve it, is listed as deferred. An acceptance spec the owner approved with a plan could change before or during implementation without anything noticing.
- **A recipe cannot be retired.** Decision [0149](../decisions/0149-one-software-recipe.md) retires `software-feature` once one software recipe replaces it, keeping pinned copies working. Nothing in the recipe format, the catalog or the recipes that propose others can say a recipe is retired.

### Acceptance criteria

1. **recipe-builder takes reference documents.** A new version adds an optional project role, `context` (many). Its profile, research and design steps receive the bound documents, and the profile prompt says how to use them: as evidence of how the owner works, not as a specification unless the owner says so. Projects pinned to the earlier version keep it.
2. **A human gate can lock a set of files.** A `human` gate may declare `locks: [globs]`. When the owner approves it, Baton records each matching file with its hash. At every later dispatch in the run, and at its intake, a changed, added or deleted file in the set is caught and handled as that step's `protect` setting says: it waits on the owner (`warn`, the default) or fails (`fail`). The owner's approval of the gate again records a new set.
3. **Locks are visible.** `status`, the step record and `explain` show which sets are locked, by which approval, and any difference found.
4. **A recipe can be retired.** `recipe.yaml` may declare `retired: {replaced_by: <id>}`. Catalog listings and `catalog.summaries` show it; fit-check, framing and project review propose the replacement instead; `vendor` warns before vendoring a retired recipe. Vendored and pinned copies keep working.
5. **Nothing changes for recipes that use none of this.**
6. **Manual and design are current.**

### Open questions

All answered by the owner, 2026-11-18, accepting the suggested answers (Decision [0173](../decisions/0173-builder-context-and-locks-details.md)):

1. **What does a lock compare?** The sha256 of every file matching the globs at approval; an edited, added or deleted matching file is a difference. Paths outside the project, `.git` and `.baton` are never matched.
2. **Which steps does a lock bind?** Every step of the run dispatched after the approval, including later group instances; an intended change to a locked file needs the owner's approval.
3. **What happens to a lock when the gate's step is revised?** It is released with the approval it came from (also when the step goes stale); the next approval locks again.
4. **Which version does recipe-builder become?** The next in landing order: `recipe-builder@7` today.
5. **Does a retired recipe still appear in `recipes()`?** Yes, marked retired with its replacement.

## Design

For the owner's approval, with the Request. Refined against `36352e7` and Decision [0173](../decisions/0173-builder-context-and-locks-details.md).

### Shape

- **recipe-builder@7.** A new version beside `@6` (projects pinned to `@6` keep it, §14): an optional project role `context` (many), bound as `quick-run` binds its own, and given to the profile, research and design steps as a `context` input. The profile prompt says to read the documents as evidence of how the owner works (their steps, roles, checks and lessons), and as a specification only when the owner says so in the idea or at the profile gate.
- **Declaring a lock.** A `human` gate may declare `locks: [globs]` (on violation: `warn`) or `locks: {paths: [globs], on_violation: warn | fail}`, the shape `protect` has. The mode belongs to the lock, not to the steps it binds: most of those steps declare no `protect`, and only `workspace: write` steps may.
- **Recording a lock.** When the owner approves the gate, Baton records `files_locked {gate, paths: [{path, sha256}], decision_seq}` on the gate's step, after its `gate_passed`. A waived gate locks nothing. When the step is revised or goes stale, the lock is released; the release is read from `step_revised` / `step_stale`, so it has no event of its own (refined in Slice 2).
- **Changes during a step (at its intake).** Every later step's dispatch records the live locks' current hashes, and its intake compares them, as the implicit `protected` gate does (§9.4): a difference records `locked_path_modified {lock, changed, mode}`. `warn`: the step waits on the owner, and approving keeps the change and records the set again (`files_locked` with the approving decision); `reject` fails the gate. `fail`: the gate fails. A pending `protected` waiver does not cover a lock: an approved set is changed only by the owner's decision.
- **Changes between steps (at dispatch).** A difference found when the next step is dispatched (the files were changed outside any step, by the owner or the Director) cannot be blamed on an attempt, so it never fails one: dispatch is refused with `dispatch.locked_files_changed`, and `pending_decisions` shows a `locked_change` decision on the gate's step. The owner either has the files restored (dispatch then goes on) or accepts the change (`decide <ref> accept`), which records the set again.
- **Publishing into a locked set.** A deliverable whose publish target is a locked file is held as a publish conflict (§10.4), which the owner decides as today; overwriting it records the set again.
- **Visibility.** `status` lists the run's live locks (gate, file count, approving decision) and any pending difference; the step record shows `files_locked` and differences; `explain` names the lock when a dispatch is refused or a gate waits on one.
- **Retiring a recipe.** `recipe.yaml` may declare `retired: {replaced_by: <id>}`; the load check requires the replacement to be a recipe of the catalog, and not itself retired. `recipes()` and `catalog.summaries` carry `retired`. Fit-check, framing and project review are told to propose the replacement; deterministically, a proposal that names a retired recipe is refused with a message naming the replacement. `vendor` of a retired recipe warns and goes on. A pinned or vendored copy runs as before.

### Doc edits

- `design/recipes.md` §5.3: load rules for `locks` on a human gate and for `retired`; §5.7: recipe-builder's `context` role and the retired recipes.
- `design/gates-and-reviews.md` §9.4: approved file sets, replacing the deferral.
- `design/runtime.md` §8.2: `files_locked {gate, paths: [{path, sha256}], decision_id}` and the difference found at dispatch or intake.
- `design/adoption-and-framing.md`: framing and project review propose a retired recipe's replacement.
- `design/director-interface.md` §13.1: `recipes()` and `vendor` with retirement; `status` with locks.

### Manual edits

- `recipe-sources/recipe-builder.md` (and the generated `recipes/recipe-builder.md`): a new section, *What you already have written down* (`#your-documents`), and a line under *What you will be asked* pointing to it. Slice 1.
- `anchors.yaml`: the new anchor. Slice 1.
- `admin/recipes-and-vendoring.md`: a new section, *Files an approval locks* (`#approved-files`): declaring `locks`, what happens to a change, release, visibility. Slice 2.
- `user/answer-questions-and-decide.md`: the **Keep the change** choice, and a section *Files you approved stay as you approved them* (`#approved-files`). Slice 2.
- `reference/commands.md` (generated): `decide`'s `ref` names `lock:<step>#<gate>`. Slice 2.
- Still to come: retirement in `admin/recipes-and-vendoring.md` and the commands (Slice 3).

### Decisions

- [0172](../decisions/0172-software-recipe.md) (accepted): the software recipe, which needs all three.
- [0142](../decisions/0142-project-documents-bound-by-role.md) (accepted): project documents bound by role.
- [0037](../decisions/0037-protected-warn-waits-on-owner.md) (accepted): a protected change waits on the owner in `warn` mode.
- [0149](../decisions/0149-one-software-recipe.md) (accepted): `software-feature` is retired once replaced.
- The five open questions above become one record when the owner answers them.

## Plan

### Slice 1: recipe-builder takes reference documents

- **Outcome:** an owner binds documents to a builder run, and its profile, research and design use them.
- **Criteria:**
  - the `context` role in a new recipe-builder version, read by the three steps;
  - the profile prompt's guidance on using them;
  - a scenario where a bound document shapes the design;
  - the pinned earlier version unchanged.
- **Effort:** S

### Slice 2: approved file sets

- **Outcome:** a file set the owner approved cannot change later in the run without the owner deciding.
- **Criteria:**
  - `locks` loaded and checked;
  - the set recorded on approval;
  - an edited, an added and a deleted file each caught at a later dispatch and at intake, under `warn` and `fail`;
  - re-approval records a new set; revision releases it;
  - `status`, the step record and `explain` show locks.
- **Effort:** M

### Slice 3: retiring a recipe

- **Outcome:** a recipe can say it is retired and by what, and Baton steers new work to the replacement.
- **Criteria:**
  - `retired` loaded and checked (the replacement must be a known recipe id);
  - listings and `catalog.summaries`;
  - fit-check, framing and project review propose the replacement;
  - `vendor` warns;
  - a pinned retired recipe still runs;
  - the manual.
- **Effort:** S

## Log

### Proposal drafted

- **Summary:** Broken out of `2026-11-software-recipe` so the three gaps it found are reviewed and built on their own, before the builder run that needs them. No code changed.
- **Owner decision:** 2026-11-18, "Yes. break out the gap fix proposal".
- **Accepted:** No; proposal only. Five open questions await the owner.

### Open questions answered, Design refined

- **Summary:** Recorded Decision 0173 (the five suggested answers). Refined the Design against `36352e7`: the violation mode belongs to the lock (most bound steps have no `protect`, and only write steps may); a difference found at dispatch was made outside any step, so it refuses the dispatch and asks the owner rather than failing an attempt; a publish into a locked file is a publish conflict; a `protected` waiver does not cover a lock. No code changed.
- **Owner decision:** 2026-11-18, "accept all".
- **Accepted:** No; the Request and Design await the owner's approval.

### Request and Design approved

- **Owner decision:** 2026-11-18, "Approve" (the Request, and the Design with its four refinements).
- **Accepted:** Yes; status `in-progress`.

### Slice 1: recipe-builder takes reference documents

- **Summary:** `recipe-builder@7` declares a second project role, `context` (many, optional), and gives it to `profile`, `research` and `design` as an optional `project.context` input. The profile prompt has a new section 2a: the documents are evidence of how the owner works, a specification only when the owner says so, and the idea wins where they disagree (an `open` entry). Research compares usual practice with them; the design keeps what works and says what it kept and changed, in its summary and design document. `@6` is frozen as `tests/fixtures/recipes/recipe-builder-v6`.
- **Modules:** none changed (the recipe and its prompts only).
- **Design docs:** `design/recipes.md` §5.7 (version 7, the owner's documents).
- **Manual:** `recipe-sources/recipe-builder.md` *What you already have written down*; `anchors.yaml`.
- **Other docs:** `2026-11-ai-delegates` now plans `recipe-builder@8` (Decision 0173, item 4).
- **Tests:** `tests/test_recipe_builder.py` (the role and the three inputs, nothing else takes it; the prompts' guidance; v6 a frozen copy); `tests/test_recipe_builder_runs.py` (an attested procedures document bound at start reaches the profile, research and design packets byte for byte, and not audit or generate; a pinned `@6` still runs to completion); the `@6` references moved to `@7`.

### Slice 2: approved file sets

- **Summary:** A `human` gate may declare `locks` (`[globs]` or `{paths, on_violation}`). The owner's approval records `files_locked` with every matching file's sha256. Every later dispatch in the run lists the live locks and is refused (`dispatch.locked_files_changed`) when a set differs, with a `locked_change` pending decision (`lock:<step>#<gate>`, `accept`). At intake, the implicit `locked` gate (after `protected`) records `locked_path_modified`: `warn` waits on the owner (approve records the set again), `fail` fails the gate. A lock is released when its step is revised or goes stale. The lock's own deliverable, and a publish the owner decided, join the set; a publish over a locked file by another step is a publish conflict. No waiver covers a lock. `status`, `explain`, the step record and `plan` show locks. Refinement from the Design: the release has no `files_unlocked` event; it is read from `step_revised` / `step_stale`. Also: a lock's own step publishing its deliverable after approval would have conflicted with its own lock, so its deliverable joins the set instead.
- **Modules:** `file_locks.py` (new); `models.py` (`HumanGate.locks`, the two events, the implicit gate type); `state.py` (`locked_path_modified`); `recipe.py` (`gate.lock_path`, the plan note); `engine.py` (dispatch check, the `locked` gate, recording on approval, `lock:` decisions, pending decisions, status, explain); `publish.py` (the conflict); `reviews.py` (`waive.not_waivable`); `interactions.py`, `defaults/labels.yaml` (`locked`, `locked_change`); `docs.py` (the step record); `cli.py`, `mcp_server.py` (status line, `decide` help); `formats/baton-recipe-1.schema.json` regenerated (an additive key: the format stays `baton-recipe/1`).
- **Design docs:** `design/gates-and-reviews.md` §9.1, §9.4 (approved file sets, replacing the deferral); `design/runtime.md` §8.2 (the two events); `design/recipes.md` §5.3 (`gate.lock_path`); `design/director-interface.md` §13.1 (`decide lock:`, `status` and `explain`).
- **Manual:** `admin/recipes-and-vendoring.md` *Files an approval locks*; `user/answer-questions-and-decide.md` *Files you approved stay as you approved them*; `reference/commands.md` regenerated; `anchors.yaml`.
- **Tests:** `tests/test_file_locks.py`: the set recorded with hashes on approval and listed on the next dispatch; an edited, an added and a deleted file each caught at intake under `warn` (approve records the set again) and under `fail` (the gate fails); rejecting fails the attempt and the retry waits until the files are restored; an edited, added and deleted file each caught at the next dispatch, refused with nothing written, decided by `accept`; accepting keeps only the changed files; revision releases and re-approval records a fresh set; `status`, its text, `explain` and the step record (through the Api); no waiver; a publish over a locked file is a conflict and an owner's overwrite joins the set; the glob checks and the plan note; a recipe without locks records nothing new.