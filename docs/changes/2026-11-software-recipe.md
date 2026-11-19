---
id: 2026-11-software-recipe
title: "Baton's one software recipe, software, is designed fresh by recipe-builder, with the owner's eng-process as evidence"
status: proposed
level: major
decisions: ["0172", "0149", "0155", "0144", "0147", "0142", "0169"]
touches: [design/recipes.md]
manual: []
---

# Baton's one software recipe, software, is designed fresh by recipe-builder, with the owner's eng-process as evidence

## Request

### Problem

Baton ships `software-feature`, a light software recipe, and Decision [0149](../decisions/0149-one-software-recipe.md) calls for one software recipe that serves a personal utility and a commercial system with the same familiar process. `2026-11-eng-process-recipe` (now abandoned) proposed porting the owner's eng-process kit with a parity table. Most of that kit's machinery is now Baton's own, and the owner wants the recipe designed from scratch on current practice, with eng-process's lessons carrying weight (Decision [0172](../decisions/0172-software-recipe.md)).

The owner also wants recipe-builder exercised on a demanding real process. So the recipe's content comes from a recipe-builder run, and this change covers what that run needs, what Baton itself must add, and shipping the result.

It waits on [2026-11-builder-context-and-locks](2026-11-builder-context-and-locks.md), which fixes three gaps found while writing this: recipe-builder cannot take reference documents, files the owner approved are not protected later in the run, and a recipe cannot be retired.

### Acceptance criteria

1. **The run's material is prepared and attested.** Before the run, three kinds of document exist in the project where it runs, each attested by the owner and bound to recipe-builder's `context` role:
   - the **brief** below, as the owner's requirements for the recipe;
   - eng-process's `PROCESS.md`, `LESSONS.md` and `SOURCES.md`, frozen at the commit used;
   - a **sources-and-lessons ledger**: each eng-process lesson and each practice from the sources, with where it came from, when it was read, and whether it was checked against the source.
2. **A recipe-builder run produces `software@1`.** The owner drives it to an accepted package, with the builder's provenance and design record. The ledger is completed in the run: every entry adopted, adapted or rejected, with a reason. The recipe may lock its approved specs with `locks` on a human gate.
3. **`software` ships and `software-feature` is retired.** The accepted package is in the shipped catalog, with scenario tests covering: every axis at its lowest; each axis raised alone; the six examples of `project-process-linkage.md` §4; and a commercial example (every axis high, a product brief bound from a business process). `software-feature` declares `retired: {replaced_by: software}`.
4. **Findings about recipe-builder are kept, not patched mid-run.** Anything the run shows wrong or missing in the builder is recorded as process feedback in the run project and, where it warrants one, becomes a change proposal in the Baton repository.
5. **Manual and design are current.**

### The brief for the builder run

What the owner asks of the `software` recipe. Items marked *(owner decides in the run)* are design questions for the run, not settled here.

- **Scale.** One process from a personal utility to commercial software, tailored on four axes, `discovery`, `coordination`, `assurance` (its lowest confirmed by the owner) and `release`, each `low`, `medium` or `high`. At its lowest it is as light as `software-feature` at its lowest: one triage, then each slice built, checked and accepted, with no plan or architecture written for show.
- **Product discovery, not marketing.** Discovery covers who uses the software, the problem, how success is measured and what is in and out of scope, including challenging the framing and choosing a scope mode (expand, selectively expand, hold, reduce). Market and commercial work is not part of it; when a business process has produced a product brief or similar, the run binds it.
- **Builds on the project.** Optional roles for the settled architecture, the conventions, the project's decisions (many) and business inputs such as a product brief; an inception run publishes architecture and conventions for later runs to bind.
- **Questions before plans.** A worker first produces open questions and an outline; the owner resolves them before any plan is written. The owner's main review is a short design discussion and, for each slice, its diff summary and a demonstration, not a long plan. An independent worker reviews the plan.
- **Factual research.** Research describes the code as it is, with file and line references and the revision read; recommendations belong to design.
- **Small, always releasable steps.** Vertical slices, one at a time; the first a walking skeleton when the work spans components; what is not being done stated; the pipeline green as part of done.
- **Tests before code, by someone else.** Acceptance examples and tests are written before the code by a worker other than the implementer, and then protected. Executable specifications in the problem's language from `assurance` medium; four layers (specs, a domain language, protocol drivers, the system) where there is a public interface or at `assurance` high *(owner decides in the run)*.
- **Verification is re-execution.** A report is a claim until a separate worker re-runs the criteria and the definition of done against identified code. A rejected review finding needs evidence. The least independent checking at the lowest assurance *(owner decides in the run)*.
- **Risk has a price tag.** A mitigation the agent would add is put to the owner with its cost and a narrower alternative, never absorbed silently.
- **Release under authority.** Release actions go through the project's action permissions; `release` high adds staged rollout and recovery evidence; trunk-and-tag releases are first-class.
- **Learning with evidence.** Decisions carry predictions with a check date; reflection scores those due, records friction and proposes lessons for the owner to approve. When reflection is a full step *(owner decides in the run)*.
- **Software over AI.** Deterministic work (running the suite, lint, coverage, spec-drift checks, changelog and version) is a program or a script gate, per recipe-builder's own rules.
- **Short prompts.** Each step's prompt stays brief; patterns and checklists live in files the steps read.
- **Asks are interaction requests,** and every person's stage carries its delegation mark.
- **The eng-process lessons** L-002, L-003, L-008, L-009, L-010, L-011 and L-013 are engineering lessons for the recipe; L-001, L-004, L-005, L-006 and L-012 concern the kit's mechanics and are recorded in the ledger as now Baton's concern.

### Open questions

Each has a suggested answer, assumed until the owner decides.

1. **Where does the run happen?** *Suggested:* in a separate Baton project made for it (for example `D:\rob\projects\baton-recipes`), not in the Baton repository. The accepted package is then copied into the shipped catalog by slice 3, and this change's Log names the run project, its run id and the commit the package came from. *Rationale:* the builder writes drafts, run records and checkpoint commits into its project; the Baton repository should receive only the result. It is also how an agency would use the builder, with Baton installed rather than from a source checkout. The run project needs the installed Baton updated after `2026-11-builder-context-and-locks` lands.
2. **At what ratings does the builder run?** *Suggested:* `approach: complex`, and `software: simple`, raised to `engineered` only if the design calls for a program that needs packages. *Rationale:* the recipe's programs (spec-drift checks, changelog assembly) are likely small; engineered programs need the owner's own examples.
3. **Who prepares the ledger?** *Suggested:* it is drafted in slice 1 from the eng-process files and a fresh read of the sources, each entry marked checked or not, and the run completes the adopt, adapt or reject column. *Rationale:* the builder's research step is general; it should start from material whose provenance is known.

### Out of scope

- **Market, commercial and business-operations processes** (Decision 0172, item 4).
- **Porting eng-process's machinery** (sessions, handoffs, `PROJECT_STATE`, the approval log, `eng-check`, run markers, runners): Baton's own machinery replaces it.
- **Improving recipe-builder during the run** (criterion 4).
- **The core gaps:** [2026-11-builder-context-and-locks](2026-11-builder-context-and-locks.md).
- **Migrating projects that use the eng-process kit** to `software`: an adoption crosswalk, later.

## Design

For the owner's approval, with the Request. The recipe's own design is the builder run's output.

### Shape

- **No core changes.** Everything Baton needs comes from `2026-11-builder-context-and-locks`.
- **Shipping.** The accepted package from the run project is copied to `examples/recipes/software/` unchanged; any fix found while writing scenario tests goes back through a builder run or is recorded as a reviewed edit in this change's Log, never silently.
- **Scenario tests** live in Baton's suite and use fixture projects, never the run project.

### Doc edits

- `design/recipes.md` §5.7: `software` (purpose, axes, what each rating adds) and `software-feature` retired in its favour.

### Manual edits

To be listed when the change is accepted. Expected: `recipes/software.md` and its recipe source, `recipes/recipe-builder.md`, `recipes/software-feature.md` (retired), `admin/recipes-and-vendoring.md`, `reference/commands.md`.

### Decisions

- [0172](../decisions/0172-software-recipe.md) (accepted): the name, the fresh design by recipe-builder, commercial scope.
- [0149](../decisions/0149-one-software-recipe.md) (accepted, amended by 0172): one software recipe.
- [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): recipe-builder's software rules.
- [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md) (accepted): the axes.
- [0142](../decisions/0142-project-documents-bound-by-role.md) (accepted): project documents bound by role.
- [0169](../decisions/0169-interaction-requests.md) (accepted): asks as interaction requests.
- The three open questions above become one record when the owner answers them.

## Plan

Slices as proposed; refined once the Request and Design are approved. It starts after `2026-11-builder-context-and-locks` is done. Slice 2 is a Baton run the owner drives, not code.

### Slice 1: the material is ready

- **Outcome:** the run project exists, and the brief, the frozen eng-process files and the ledger are attested in it.
- **Criteria:** the run project initialised with the updated Baton; the eng-process commit recorded; the ledger with provenance per entry; the documents attested.
- **Effort:** S

### Slice 2: the builder run

- **Outcome:** the owner accepts `software@1` from a recipe-builder run.
- **Criteria:** the run's record and provenance; the completed ledger; the owner's decisions on the brief's open items; builder findings recorded per criterion 4.
- **Effort:** L

### Slice 3: ship `software`, retire `software-feature`

- **Outcome:** `software` is in the shipped catalog with its scenario tests, and `software-feature` is retired.
- **Criteria:** the package copied in and `baton recipe check` clean; the scenarios of criterion 3; `software-feature` declares `retired`; pinned `software-feature` runs unaffected; the manual.
- **Effort:** L

## Log

### Written to replace eng-process-recipe

- **Summary:** Written from the owner's direction of 2026-11-18 (Decision 0172). Replaces `2026-11-eng-process-recipe`, which ported the eng-process kit with a parity table. Checked against `36352e7`: recipe-builder@6 has no reference-document role, and §9.4 still defers approval-time protected sets. No code changed.
- **Owner decision:** 2026-11-18, "Change name and use recipe-builder. I'll go with your recommendation for the commercial sw question."
- **Accepted:** No; proposal only. Six open questions await the owner.

### Gap fixes broken out

- **Summary:** The `context` role, approved file sets and recipe retirement moved to `2026-11-builder-context-and-locks`, which this change now waits on. Criteria, open questions, Design and Plan trimmed to preparing the material, the builder run and shipping. No code changed.
- **Owner decision:** 2026-11-18, "Yes. break out the gap fix proposal".
- **Accepted:** No; proposal only. Three open questions await the owner.

### Slice 1 material prepared

- **Summary:** At the owner's instruction, ahead of approving the Request and Design, the reference documents were put in the run project `D:\rob\projects\baton-recipes`, under `reference\`: `software-brief.md` (this change's brief), `eng-process\` (`PROCESS.md`, `LESSONS.md` and `SOURCES.md` from https://github.com/rowama/eng-process at `cd615b4`, with a README giving their hashes) and `sources-and-lessons-ledger.md` (73 rows: 13 lessons, 36 eng-process practices, 12 sources as eng-process recorded them, 12 current practices read 2026-11-18, each marked primary, secondary or as recorded; Decision and Reason left for the run). This follows open questions 1 and 3 as suggested. Not done here, by the owner's choice: attesting the documents, vendoring recipe-builder and starting the run, which the owner does in another session. Nothing was committed in the run project.
- **Owner decision:** 2026-11-18, "implement the software-recipe proposal until the point of putting the reference files in d:\rob\projects\baton-recipes ... Don't vendor the recipe-builder".
- **Accepted:** No; proposal only. Open question 2 (the builder's ratings) is decided in the run.
