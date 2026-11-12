---
id: 2026-11-adopt-recipe-selection
title: "Adopting an existing project finds or builds its recipe first, using fit-check with project context"
status: in-progress
level: standard
decisions: ["0134", "0135", "0136", "0137", "0040", "0044", "0029"]
touches: [design/recipes.md, design/adoption-and-framing.md]
manual: [user/bring-an-existing-project.md, recipes/fit-check.md]
---

# Adopting an existing project finds or builds its recipe first, using fit-check with project context

## Request

### Problem

`baton adopt` requires a recipe, but an owner (through the Director) bringing in an existing project has no way to find the right one or to get one made. fit-check already chooses an existing recipe or returns `recipe: null` (leading to `recipe-builder`), but it sees only the owner's idea, not the project. The manual's `baton adopt fit-check` example is also misleading. Requested by Rob, 2026-11-12.

### Acceptance criteria

- fit-check v4 accepts an optional `context` run input; its worker still reads no files, and the verdicts, rubric and gate are unchanged. Runs without `context` behave as in v3.
- Given project context, a `fits` verdict names a recipe that covers the existing work, or `null`.
- The Director is told how to go from a verdict to `adopt <recipe>`, to `recipe-builder`, or to stopping (per 0135 and 0136 once decided).
- The manual's adopt example uses a recipe with work products and describes the procedure.

## Design

### Doc edits

- `design/recipes.md` §5.7: fit-check version 4 with the optional `context` input (version note, as for versions 2 and 3).
- `design/adoption-and-framing.md` §11.1: the find-or-build procedure before `adopt`; §11.6 mature-projects note points here (decision 0044's deferred work, narrowed to the adopt side).

### Manual edits

- `manual/user/bring-an-existing-project.md`: the procedure, and a corrected command example.
- `manual/recipes/fit-check.md` (via `manual/recipe-sources/fit-check.md` and `tools/build_manual.py`): the optional project context.

### Decisions

- 0134 (accepted): option B, optional text context, no file reading.
- 0135 (accepted): the Director writes the context from `detect` and a shallow look.
- 0136 (accepted): `adopt` with no recipe returns a recipe-needed status naming the procedure.
- 0137 (accepted): the manual example uses a recipe with work products (`software-feature`).

## Plan

### fit-check v4: optional project context

- **Outcome:** fit-check accepts `context`; given it, `describe` and `assess` use it, and `fits` names a recipe for the existing work or `null`.
- **Criteria:**
  - A v4 run with `context` validates and reaches a verdict; a run without it behaves as v3 (test).
  - The recipe's `run_inputs` schema accepts `context` as optional text and rejects non-text (test).
  - The vendored copy of v3 is untouched; v4 is a new version (§5.8) and `init` vendors it (test).
  - Design §5.7, the fit-check manual page and the generated manual are updated, and the docs and manual tests pass.
- **Effort:** M

### adopt with no recipe returns "recipe needed"; the manual explains the procedure

- **Outcome:** `baton adopt` with no recipe starts nothing and says what to do; the Director's guidance and the manual describe find-or-build-or-stop.
- **Criteria:**
  - `adopt` with no recipe starts no run and returns a `recipe_needed` status naming fit-check with `context`, `recipe-builder` and stopping (test); `--json` carries it.
  - The status is explained in the Director's guidance and passes the question check (§13.8).
  - `manual/user/bring-an-existing-project.md` uses a recipe with work products in its example and describes the procedure; the command reference is regenerated (`tools/build_manual.py`, `tools/manual_anchors.py`).
  - Design §11.1 and the §11.6 mature-projects note are updated.
- **Effort:** M

## Log

### fit-check v4: optional project context

- **Commit:** 2026-11-adopt-recipe-selection: Slice 1, fit-check v4 takes optional project context
- **Summary:** `examples/recipes/fit-check` is version 4: optional `context` run input (text), passed to `describe` and `assess`, whose prompts say to use it as given and that the worker reads no files. Design §5.7 version note; the fit-check manual page ("What you will be asked") and generated manual; `fit-check@3` references in tests and goldens moved to `@4`; the assess instructions golden regenerated. New `tests/test_fit_check_context.py` covers the schema (optional, text only), a run with context (both inputs reach the packet) and a run without (no context input).
- **Review:** clean
- **Accepted:** pending the owner.
- **Repair:** the full run on the change's docs commit `2e79c36` was red from an environment fault (a running `baton ui` held the page's fixed port); fixed in `70913fa`, logged under 2026-11-user-help. The full run on slice 1's commit `1ee8a28` was then red: `test_continuity.py::test_records_golden` pins fit-check's content hash, and only the packet golden had been regenerated. Fixed in the commit `repair Slice 1, goldens carry the new recipe hash`.

### adopt with no recipe returns "recipe needed"; the manual explains the procedure

- **Commit:** 2026-11-adopt-recipe-selection: Slice 2, adopt with no recipe returns recipe-needed
- **Summary:** `Api.adopt`, `baton adopt` and the MCP `adopt` tool take an optional recipe. With none and no adoption run active, nothing starts: the result is `state: recipe_needed`, the project situation, the steps (`adopt.RECIPE_NEEDED_STEPS`) and `next`. An active adoption still returns its status. The Director skill and its copy in the design (§13.3) gain the procedure (fit-check with `context`, then `adopt`, `recipe-builder` or stop). Design §11.1, §11.6 note and the director-interface table; the manual's "bring in an existing project" page (new section, corrected example), and the regenerated command reference.
- **Tests:** `tests/test_adopt_recipe_needed.py` (nothing started and `.baton` unchanged; the text form; the skill and its design copy name the procedure).
- **Review:** clean
- **Accepted:** pending the owner.
