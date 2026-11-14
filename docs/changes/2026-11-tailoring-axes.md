---
id: 2026-11-tailoring-axes
title: "A recipe rates complexity on a few axes of its own, so each concern changes only the parts of the process it affects"
status: proposed
level: major
decisions: ["0144", "0008", "0027", "0028"]
touches: [principles.md, design/recipes.md, design/runtime.md, design/gates-and-reviews.md, design/packets.md, design/adoption-and-framing.md, design/director-interface.md]
manual: [recipes/software-feature.md, user/answer-questions-and-decide.md, user/check-on-your-work.md, admin/recipes-and-vendoring.md, admin/director-commands.md, reference/commands.md]
---

# A recipe rates complexity on a few axes of its own, so each concern changes only the parts of the process it affects

## Request

### Problem

A run is tailored today by one ordered level on the recipe's scale (§5.5): triage picks it, and each step and gate is kept or skipped by `applies_to`. One scale cannot hold concerns that vary independently. A one-line change to tenant authorization needs strong security verification and almost no discovery. A large, low-risk personal project needs real planning but light release control. A small utility that deletes files needs recovery evidence because its data loss can't be undone, whatever its size. On one scale, each of these either takes on ceremony it doesn't need or loses a safeguard it does.

The owner wants one software recipe, eng-process, tailored deeply enough to serve every scale while staying familiar. The many concerns (consequence, uncertainty, data and security, reversibility, reach, scope, longevity, delivery obligations, existing evidence) should map onto three or four axes, and only the axes that matter for a case should change anything (2026-11-13, `docs/catchall/project-process-linkage.md` §4). Decision [0144](../decisions/0144-tailoring-axes.md) settles the shape. This change builds the runtime and recipe-format support. eng-process (`2026-11-eng-process-recipe`) will be its first multi-axis recipe; project policy floors (0143) build on it in their own change.

### Acceptance criteria

- **Recipes declare axes.** A recipe may declare `complexity.axes`, a map from axis name to an ordered scale, instead of `complexity.levels`. A recipe with `levels` is a one-axis recipe: it loads, runs, hashes its packets and records its events exactly as before (goldens unchanged for every shipped recipe).
- **Steps and gates apply by axis.** `applies_to` may be a map from axis to the values at which the step or gate applies. It applies when any listed axis's rating is among its values (OR); a step with no `applies_to` always runs. The loader refuses an unknown axis, an undeclared value, a list-form `applies_to` in a multi-axis recipe and a map-form one in a one-axis recipe. For every combination of ratings, every included step must be reachable.
- **`baton plan` shows the tailoring.** For a multi-axis recipe it prints the steps and gates that always run, then, per axis and value, what that rating adds. It also prints the full table for any combination given (`--rating axis=value …`).
- **Triage rates every axis with a reason.** A multi-axis triage step outputs `ratings {axis: {value, reason}}`. The loader requires the schema to constrain every axis to its scale and to require a non-empty reason for each. A missing axis or reason fails the schema gate.
- **Approval follows today's rule, per run.** All axes at their lowest applies at once (`complexity_set {ratings, approval: auto}`). Otherwise, one implicit `triage` gate asks the owner to approve the whole set of ratings, showing each axis's value and reason in plain words. Approving records `complexity_set {ratings}` and the skips. Rejecting retries triage with the note, as today (Decision 0027).
- **Re-triage works per axis.** `retriage(run, reason, axes?)` reruns triage behind the owner gate, with the previous ratings in its packet. On approval, `retriage_applied` lists the old and new rating of each axis; steps not yet started are skipped or unskipped; started and passed steps never change and are listed in `pre_retriage` and flagged, as today (Decision 0028).
- **A worker can signal that a rating may be wrong.** Any step's result may carry `rating_signal {axis, suggested, reason}`. Intake records it (`rating_signal_recorded`), and the Director is told. It changes nothing by itself. `status` shows it until the owner decides to re-triage or to dismiss it.
- **Surfaces show ratings.** `status`, `board`, step records and the run summary show a multi-axis run's ratings. `catalog.summaries`, framing's run inputs and adoption's recipe summary show a recipe's axes. The adoption baseline (§11.5) carries `ratings` for a multi-axis recipe's work items, and the owner can edit them like a level.
- **Packets carry the ratings.** A step's packet includes the run's ratings, so a worker can size its work to them without new steps (for example, documentation depth on a coordination axis).
- **Manual and design are current.** §5.5, §9.1 and the surfaces above are documented. The generated recipe tables in the manual show axes for a multi-axis recipe. The owner's guide explains what they are asked and why.

### Open questions

New questions this change raises. Each has a suggested answer; they go to the owner in one batch before Design.

1. **Format: additive or a new version?** (left to Design by 0144.) *Suggested:* additive within `baton-recipe/1`. `levels` and `axes` are mutually exclusive, and the loader tells the forms apart by key. *Rationale:* every pinned recipe keeps loading unchanged and no migration is needed. A version bump would buy nothing the key check doesn't.
2. **Is the lowest-everywhere case really safe to auto-apply?** Under-rating is the main way tailoring fails, and auto-apply means no one looks. *Suggested:* keep auto-apply (decided in 0144), and let a recipe mark an axis `confirm_lowest: true`, so that axis's lowest rating also asks the owner. eng-process would mark assurance this way. *Rationale:* the recipe author knows which axis is dangerous to under-rate. Most runs stay friction-free, and the dangerous case is never silent.
3. **What does a worker's rating signal cost the owner?** *Suggested:* it is a pending owner decision (`rating:<axis>`, options `retriage` or `dismiss`, with the worker's reason). It blocks nothing and does not hold completion. *Rationale:* a changed risk is a real decision (§1.1 #1). Making it pending keeps it from being lost, and not blocking keeps the work moving.
4. **May `applies_to` require two axes together (AND)?** *Suggested:* not in this change. Only OR across axes, and the values within one axis are OR as well. Add AND only if a real recipe needs it. *Rationale:* 0144 chose OR so that no single low rating hides a risk. AND brings back exactly that risk and makes the plan table harder to read.
5. **Does recipe builder generate multi-axis recipes?** *Suggested:* not in this change. Recipe builder keeps generating one-axis recipes, and generating axes is a follow-up once eng-process has shown the pattern. *Rationale:* keeps this change to runtime and format. Choosing axes well needs a worked example first.
6. **Is `effort_from` or anything else rating-driven?** *Suggested:* no; only `applies_to` and the packet's ratings. *Rationale:* keeps the mechanism one thing.

## Design

Provisional, for review with the Request. The design is settled after the open questions are answered.

### Shape

- **Format.** `complexity: { axes: { discovery: [low, medium, high], assurance: [low, medium, high], … }, triage_step: triage }`. `applies_to: { assurance: [high] }` on steps and gates. Internally, a one-axis recipe is treated as a recipe with a single axis named `level`, so one code path handles both. Its events and outputs keep today's `level` field for compatibility.
- **Application.** `complexity_set` and `retriage_applied` carry `ratings`. Skipping evaluates each `applies_to` against the ratings (OR). The skip and unskip rules of §5.5 are unchanged.
- **Gates by axis.** Two gate entries with different `applies_to` express, for example, a same-vendor verifier at low assurance and a different-vendor one at high (§8.4 independence levels unchanged).
- **Signals.** `rating_signal` is an optional result field (§7.2), schema-checked at intake (§8.10), recorded as an event and surfaced as a pending decision.
- **Plan table.** The per-axis view prints in linear size. The full table is printed only for a given combination.

### Doc edits

- `principles.md` §1.2 *Tailored formality*: ratings on the recipe's axes; §2.1 L6: complexity ratings.
- `design/recipes.md` §5.1 (format example), §5.3 (validation and reachability), §5.5 (axes, ratings, OR, approval, `confirm_lowest`, re-triage per axis, signals), §5.7 (summaries carry axes).
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

- [0144](../decisions/0144-tailoring-axes.md) (accepted): axes, OR, approval, re-triage per axis, signals; format left to Design.
- [0008](../decisions/0008-triage-approval.md) and [0028](../decisions/0028-retriage.md) (accepted): today's approval and re-triage rules, generalized here, not changed.
- The open questions above become records when decided.

## Plan

Provisional slices, refined after the Request and Design are approved. Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: axes in the recipe format and `baton plan`

- **Outcome:** recipes can declare axes and `applies_to` by axis; `baton plan` shows the tailoring.
- **Criteria:** loader acceptance and every refusal; reachability across combinations; one-axis recipes unchanged (hashes, goldens, plan output); per-axis and `--rating` plan output.
- **Effort:** M

### Slice 2: triage ratings, approval and skipping

- **Outcome:** a multi-axis run is rated, approved and tailored.
- **Criteria:** schema requirements (every axis, a reason each); auto-apply at lowest everywhere; `confirm_lowest` (if agreed); one owner gate for the set; reject retries; OR skipping of steps and gates; packets carry ratings; status, board and records show them.
- **Effort:** M

### Slice 3: re-triage per axis and rating signals

- **Outcome:** ratings can change mid-run, by owner request or prompted by a worker's signal.
- **Criteria:** `retriage --axis`; old and new rating per axis in `retriage_applied`; skip and unskip of unstarted steps; started and passed steps flagged, never changed; signal recorded at intake, shown as a pending decision, dismissed or turned into re-triage; signal in a one-axis run.
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
