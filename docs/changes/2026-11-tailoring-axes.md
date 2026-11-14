---
id: 2026-11-tailoring-axes
title: "A recipe rates complexity on a few axes of its own, so each concern changes only the parts of the process it affects"
status: in-progress
level: major
decisions: ["0144", "0147", "0008", "0027", "0028"]
touches: [principles.md, design/recipes.md, design/runtime.md, design/gates-and-reviews.md, design/packets.md, design/adoption-and-framing.md, design/director-interface.md]
manual: [recipes/software-feature.md, user/answer-questions-and-decide.md, user/check-on-your-work.md, admin/recipes-and-vendoring.md, admin/director-commands.md, reference/commands.md]
---

# A recipe rates complexity on a few axes of its own, so each concern changes only the parts of the process it affects

## Request

### Problem

A run is tailored today by one ordered level on the recipe's scale (§5.5): triage picks it, and each step and gate is kept or skipped by `applies_to`. One scale cannot hold concerns that vary independently. A one-line change to tenant authorization needs strong security verification and almost no discovery. A large, low-risk personal project needs real planning but light release control. A small utility that deletes files needs recovery evidence because its data loss can't be undone, whatever its size. On one scale, each of these either takes on ceremony it doesn't need or loses a safeguard it does.

The owner wants one software recipe, eng-process, tailored deeply enough to serve every scale while staying familiar. The many concerns (consequence, uncertainty, data and security, reversibility, reach, scope, longevity, delivery obligations, existing evidence) should map onto three or four axes, and only the axes that matter for a case should change anything (2026-11-13, `docs/catchall/project-process-linkage.md` §4). Decision [0144](../decisions/0144-tailoring-axes.md) settles the shape. This change builds the runtime and recipe-format support. eng-process (`2026-11-eng-process-recipe`) will be its first multi-axis recipe; project policy floors (0143) build on it in their own change.

### Acceptance criteria

- **Recipes declare axes.** A recipe may declare `complexity.axes`, a map from axis name to an ordered scale (optionally with `confirm_lowest: true`), instead of `complexity.levels`; declaring both is a load error. A recipe with `levels` is a one-axis recipe: it loads, runs, hashes its packets and records its events exactly as before (goldens unchanged for every shipped recipe).
- **Steps and gates apply by axis.** `applies_to` may be a map from axis to the values at which the step or gate applies. It applies when any listed axis's rating is among its values (OR); a step with no `applies_to` always runs. The loader refuses an unknown axis, an undeclared value, a list-form `applies_to` in a multi-axis recipe and a map-form one in a one-axis recipe. For every combination of ratings, every included step must be reachable.
- **`baton plan` shows the tailoring.** For a multi-axis recipe it prints the steps and gates that always run, then, per axis and value, what that rating adds. It also prints the full table for any combination given (`--rating axis=value …`).
- **Triage rates every axis with a reason.** A multi-axis triage step outputs `ratings {axis: {value, reason}}`. The loader requires the schema to constrain every axis to its scale and to require a non-empty reason for each. A missing axis or reason fails the schema gate.
- **Approval follows today's rule, per run.** All axes at their lowest applies at once (`complexity_set {ratings, approval: auto}`), unless an axis marked `confirm_lowest` is among them. Otherwise, one implicit `triage` gate asks the owner to approve the whole set of ratings, showing each axis's value and reason in plain words. Approving records `complexity_set {ratings}` and the skips. Rejecting retries triage with the note, as today (Decision 0027).
- **Re-triage works per axis.** `retriage(run, reason, axes?)` reruns triage behind the owner gate, with the previous ratings in its packet. On approval, `retriage_applied` lists the old and new rating of each axis; steps not yet started are skipped or unskipped; started and passed steps never change and are listed in `pre_retriage` and flagged, as today (Decision 0028).
- **A worker can signal that a rating may be wrong.** Any step's result may carry `rating_signal {axis, suggested, reason}`. Intake records it (`rating_signal_recorded`) and opens a pending owner decision `rating:<axis>` (options `retriage` or `dismiss`, with the worker's reason). It blocks no step and does not hold completion; choosing `retriage` starts a re-triage of that axis.
- **Surfaces show ratings.** `status`, `board`, step records and the run summary show a multi-axis run's ratings. `catalog.summaries`, framing's run inputs and adoption's recipe summary show a recipe's axes. The adoption baseline (§11.5) carries `ratings` for a multi-axis recipe's work items, and the owner can edit them like a level.
- **Packets carry the ratings.** A step's packet includes the run's ratings, so a worker can size its work to them without new steps (for example, documentation depth on a coordination axis).
- **Manual and design are current.** §5.5, §9.1 and the surfaces above are documented. The generated recipe tables in the manual show axes for a multi-axis recipe. The owner's guide explains what they are asked and why.

### Open questions

None open. The six questions this change raised were answered by the owner on 2026-11-13 ("Accept all.") as suggested, and are recorded in Decision [0147](../decisions/0147-tailoring-axes-details.md):

1. The format is additive within `baton-recipe/1`: `levels` and `axes` are mutually exclusive, told apart by key.
2. A recipe may mark an axis `confirm_lowest: true`, so its lowest rating also asks the owner; eng-process marks assurance.
3. A worker's rating signal is a pending owner decision (`retriage` or `dismiss`) that blocks nothing.
4. `applies_to` is OR across and within axes; no AND until a real recipe needs it.
5. Recipe builder keeps generating one-axis recipes; generating axes is a follow-up after eng-process.
6. Only `applies_to` is rating-driven, plus the ratings in every packet.

## Design

For the owner's approval, with the Request (a major change: Request and Design are approved before the Plan is final).

### Shape

- **Format.** `complexity: { axes: { discovery: [low, medium, high], assurance: { scale: [low, medium, high], confirm_lowest: true }, … }, triage_step: triage }` (an axis is a list, or a map with `scale` and `confirm_lowest`). `applies_to: { assurance: [high] }` on steps and gates. Internally, a one-axis recipe is treated as a recipe with a single axis named `level`, so one code path handles both. Its events and outputs keep today's `level` field for compatibility.
- **Application.** `complexity_set` and `retriage_applied` carry `ratings`. Skipping evaluates each `applies_to` against the ratings (OR). The skip and unskip rules of §5.5 are unchanged.
- **Gates by axis.** Two gate entries with different `applies_to` express, for example, a same-vendor verifier at low assurance and a different-vendor one at high (§8.4 independence levels unchanged).
- **Signals.** `rating_signal` is an optional result field (§7.2), schema-checked at intake (§8.10) and recorded as an event; it opens the pending decision `rating:<axis>` (0147). In a one-axis recipe its axis is `level`. A second signal on the same axis while one is pending is added to it, not opened again.
- **Plan table.** The per-axis view prints in linear size. The full table is printed only for a given combination.

### Doc edits

- `principles.md` §1.2 *Tailored formality*: ratings on the recipe's axes; §2.1 L6: complexity ratings.
- `design/recipes.md` §5.1 (format example), §5.3 (validation and reachability), §5.5 (axes, ratings, OR, approval, `confirm_lowest`, re-triage per axis, signals), §5.7 (summaries carry axes; recipe builder still generates one axis, 0147).
- `design/gates-and-reviews.md` §9.1: gate `applies_to` by axis.
- `design/runtime.md` §8.2 (events carry `ratings`; `rating_signal_recorded`), §8.10 (intake of the signal).
- `design/packets.md` §7.1 (the manifest's ratings), §7.2 (`rating_signal` in results).
- `design/adoption-and-framing.md` §11.5 (baseline `ratings`), §11.6 (summaries).
- `design/director-interface.md` §13.1–§13.3: `retriage(run, reason, axes?)`, `plan --rating`, the skill's wording for ratings and signals.
- `docs/README.md`: decision 0144 and the new records.

### Manual edits

- `manual/user/answer-questions-and-decide.md`: approving ratings, a suggested rating change, re-triage.
- `manual/user/check-on-your-work.md`: seeing a run's ratings and why.
- `manual/admin/recipes-and-vendoring.md`: declaring axes and `applies_to` by axis.
- `manual/admin/director-commands.md` and the generated `manual/reference/commands.md`: `retriage --axis`, `plan --rating`.
- `manual/recipes/software-feature.md`: regenerated table, unchanged in content (shows the one-axis form still works). Other recipe topics are regenerated if the table format changes.

### Decisions

- [0144](../decisions/0144-tailoring-axes.md) (accepted): axes, OR, approval, re-triage per axis, signals.
- [0147](../decisions/0147-tailoring-axes-details.md) (accepted): additive format, `confirm_lowest`, signals as pending decisions, no AND, recipe builder unchanged, nothing else rating-driven.
- [0008](../decisions/0008-triage-approval.md) and [0028](../decisions/0028-retriage.md) (accepted): today's approval and re-triage rules, generalized here, not changed.

## Plan

Slices as proposed; the Request and Design were approved on 2026-11-14 (see the Log). Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: axes in the recipe format and `baton plan`

- **Outcome:** recipes can declare axes and `applies_to` by axis; `baton plan` shows the tailoring.
- **Criteria:** loader acceptance and every refusal; reachability across combinations; one-axis recipes unchanged (hashes, goldens, plan output); per-axis and `--rating` plan output.
- **Effort:** M

### Slice 2: triage ratings, approval and skipping

- **Outcome:** a multi-axis run is rated, approved and tailored.
- **Criteria:** schema requirements (every axis, a reason each); auto-apply at lowest everywhere; `confirm_lowest`; one owner gate for the set; reject retries; OR skipping of steps and gates; packets carry ratings; status, board and records show them.
- **Effort:** M

### Slice 3: re-triage per axis and rating signals

- **Outcome:** ratings can change mid-run, by owner request or prompted by a worker's signal.
- **Criteria:** `retriage --axis`; old and new rating per axis in `retriage_applied`; skip and unskip of unstarted steps; started and passed steps flagged, never changed; signal recorded at intake, shown as a pending decision that blocks nothing, dismissed or turned into re-triage, a repeated signal joining the pending one; signal in a one-axis run.
- **Effort:** M

### Slice 4: summaries, adoption and the manual

- **Outcome:** everything that describes or seeds a recipe understands axes.
- **Criteria:** `catalog.summaries`, framing and adoption summaries show axes; baseline `ratings` validated and editable; a multi-axis example recipe in tests runs end to end; manual topics and generated tables updated.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Change doc written from decision 0144 and `docs/catchall/project-process-linkage.md` (§4, §5 C). No code changed.
- **Owner decision:** 2026-11-13, "Concur with section recommendations for A, B, C, E1-4 (no new concept at E5). Write A and C change proposals." (0144). The Request is not yet accepted; the open questions above are unanswered.
- **Accepted:** No; proposal only.

### Open questions answered

- **Summary:** The six questions the proposal raised were answered as suggested and recorded as Decision 0147. The Request has no open questions; the acceptance criteria and Design now carry `confirm_lowest`, signals as pending decisions, and the format's mutual exclusion. No code changed.
- **Owner decision:** 2026-11-13, "Accept all." (0147).
- **Accepted:** Request and Design await the owner's approval.

### Request and Design approved

- **Summary:** The owner asked for the change to be implemented, approving the Request and Design as written. Status `in-progress`.
- **Owner decision:** 2026-11-14, "implement tailoring-axes".
- **Accepted:** Yes.

### Slice 1: axes in the recipe format and `baton plan`

- **Summary:** `complexity.axes` (an axis is a scale list, or `{scale, confirm_lowest}`) alongside `complexity.levels`, mutually exclusive; `applies_to` on steps, groups and gates may be a map from axis to values. A new module, `tailoring.py`, treats a one-axis recipe as the single axis `level`, so the loader and the plan share one path; OR applies across and within axes. The loader refuses both or neither scale, an unknown axis or value, a list `applies_to` with axes and a map one with levels, the reserved axis name `level`, a triage schema that does not require `ratings` with every axis's `value` (its exact scale) and a non-empty `reason`, and a nested step that applies at a combination where its group does not (checked over every combination); an axis nothing applies by is a warning. A foreach source skippable at some combination needs its policy, as with levels. `baton plan` for a recipe with axes prints what always runs and, per axis and value, what that rating adds; `--rating axis=value` (every axis) prints the table for one combination, including whether the owner is asked to approve it (`confirm_lowest`). The plan API and MCP tool take `ratings`.
- **Modules:** `tailoring.py` (new), `models.py` (`Axis`, `Complexity.axes`, `AppliesTo`, `PlanAxis`, `PlanLevel.ratings`), `recipe.py`, `cli.py`, `engine.py`, `mcp_server.py`; `formats/baton-recipe-1.schema.json` regenerated.
- **Design docs:** `recipes.md` §5.1 (axes example), §5.3 (validation), §5.5 (axes, OR); `gates-and-reviews.md` §9.1; `director-interface.md` §13.1 (`plan`).
- **Manual:** `admin/recipes-and-vendoring.md` (*Rating work on several axes*); `reference/commands.md` regenerated (`plan --rating`); anchors updated.
- **Tests:** `tests/test_tailoring_axes.py`: loading, every refusal, the triage schema's requirements, reachability across combinations, the foreach-source policy, the per-axis and per-combination plan, `confirm_lowest` in the plan, refusals of bad combinations, `baton plan --rating`. One-axis recipes: the existing plan, tailoring, recipe and manual-table tests pass unchanged.

### Slice 2: triage ratings, approval and skipping

- **Summary:** A run of a recipe with axes is rated, approved and tailored. Triage outputs `ratings {axis: {value, reason}}`; the schema the loader requires makes a missing axis or reason a failed result (retried). Every axis at its lowest applies at once unless an axis is `confirm_lowest`; otherwise one implicit `triage` gate asks for the whole set, its prompt giving each axis's value and reason; approving records `complexity_set {ratings, reasons, approval: owner, decision_seq}`, rejecting retries triage with the note. Steps, groups and gates are kept or skipped by OR over the ratings (`step_skipped {ratings, cause}`). The run record, the group view, gate evaluation, packets, adoption seeding and re-triage all read ratings (`RunRecord.ratings()`; a one-axis run is `{level: …}`), so one path serves both forms; one-axis events, packets and hashes are unchanged. Packets of a recipe with axes carry `ratings` and a *Ratings* section in `INSTRUCTIONS.md`. `status` and `board` carry `ratings`; `explain` says the ratings, what is skipped at them and what changing one axis would add or drop; step records and the run summary show each rating and its reason. Ratings are shown in the recipe's axis order (events store keys sorted). Re-triage already carries ratings (`previous_ratings`; per-axis old and new in `retriage_applied`); its `axes` option and signals are Slice 3.
- **Modules:** `tailoring.py` (`ordered`), `packet.py` (`RunRecord.ratings`, `gate_included`, manifest, instructions), `groups.py` (`View.ratings`), `engine.py` (refresh, triage gate and application, re-triage, gates, status, board, explain), `adopt.py` (internal ratings), `docs.py` (records, summary, timeline).
- **Design docs:** `principles.md` §1.2, §2.1; `recipes.md` §5.5 (ratings, approval, `confirm_lowest`); `runtime.md` §8.2 (events); `packets.md` §7.1 (`ratings`).
- **Manual:** `user/answer-questions-and-decide.md` (*Sizing the work*), `user/check-on-your-work.md` (the summary shows the ratings).
- **Tests:** `tests/test_tailoring_axes.py`: a missing axis, a missing or empty reason fail the result; all-lowest applies at once without a guard and asks with `confirm_lowest`; one owner gate approves the set; rejecting retries with the note; OR skipping of steps and gates; packets and instructions carry ratings, one-axis packets have no such field; records and the summary; `status`, `board` and `explain` through the CLI (slow). One-axis tailoring, adoption, director-surface and goldens unchanged.
