---
id: 2026-11-recipe-contract-checks
title: "Recipe builder's package review and the recipe loader catch a recipe whose instructions and schemas contradict each other before it ships"
status: done
level: standard
decisions: ["0190", "0189", "0188"]
touches: [design/recipes.md]
manual: [admin/recipes-and-vendoring.md, recipe-sources/recipe-builder.md, recipes/recipe-builder.md]
---

# Recipe builder's package review and the recipe loader catch a recipe whose instructions and schemas contradict each other before it ships

> Split out of [2026-11-self-improvement](2026-11-self-improvement.md) by Decision [0189](../decisions/0189-contract-checks-out-of-self-improvement.md), 2026-11-23: checking recipes before they ship is recipe authoring, not self-improvement. Not urgent. Request approved by the owner, 2026-11-23, with Decision [0190](../decisions/0190-recipe-contract-checks-placement.md).

## Request

### Problem

A recipe whose instructions demand what its output schema forbids (or forbid what it requires) can't be passed by an honest worker: the step fails, retries and, since the circuit breaker (§8.8), stops on its second identical failure. First use met this once: `issues/2026-11-19-research-blocked-vs-schema.md` (recipe-builder@7: the prompt let research report a choice as open while the schema required it decided). It was fixed by hand in recipe-builder, with a regression run in `tests/test_recipe_builder_runs.py`. Nothing checks for the class before a recipe ships.

What doesn't work, from the self-improvement investigation: simulated runs with outputs generated from each schema fail most shipped recipes' script gates (ledger, guess and budget checks) and so test nothing about contradictions; and the recipe-builder@7 schema was satisfiable on its own: the contradiction was between prose and schema.

### Acceptance criteria

- **A built recipe's instructions are checked against its output schemas** (Decision [0190](../decisions/0190-recipe-contract-checks-placement.md), item 1). Recipe-builder's package review rubric has a row for it: a prompt that requires what its step's output schema forbids, or forbids what it requires; and a disposition, answer, evidence or result-status rule a prompt states (a `blocked` result with questions included) that no output valid against the schema can meet. It is `high`, and the finding's location names the prompt and the schema. The review keeps its scope (approach `complex`, or software `simple` or `engineered`). A prompt test shows the row and that the recipe-builder@7 contradiction (`tests/fixtures/recipes/recipe-builder-v7`, `prompts/research.md` against `schemas/research_out.json`) is the case it names; `audit` is unchanged, because it sees the design and not the package.
- **An output schema with no instance is warned about by the loader** (item 2): `schema.no_instance`, naming the step and the schema, shown by `vendor`, `plan` and any other command that prints loader warnings. It never refuses a recipe or changes an exit code. The check builds candidate instances for the JSON Schema shipped recipes use (`type`, `required`, `properties`, `additionalProperties`, `enum`, `const`, `items`, `minItems`, `maxItems`, `contains`, `minLength`, `minimum`, `maximum`, `if`/`then`/`else`, `allOf`, `anyOf`, `oneOf`, `not`, `$ref` and `$defs` within the schema; `pattern` and `format` by fixed candidates) and keeps one only if the JSON Schema validator accepts it, so it never claims an instance that isn't one; finding none is a warning, not a proof. Every output schema of every shipped recipe, and the runtime's `baton:findings` and `baton:proposals`, yield an instance (suite test); a crafted contradictory schema is warned about by step and file.
- **`vendor` runs no model** (item 3): a recipe vendored from elsewhere gets the warning only.

## Design

### Doc edits

- `design/recipes.md` §5.3: a bullet for the no-instance warning (`schema.no_instance`), what it reads, that it is a warning only and why.
- `design/recipes.md` §5.7: recipe-builder version 11, the steps table's package review cell, and a paragraph on the contract row and why it is the package review's and not the audit's.

### Manual edits

- `manual/admin/recipes-and-vendoring.md`: what the `schema.no_instance` warning means when `vendor` or `plan` prints it, and what to do (read the step's prompt and schema; a recipe still loads).
- `manual/recipe-sources/recipe-builder.md`, regenerated into `manual/recipes/recipe-builder.md`: the package review now checks that each step's instructions can be met by an output its schema accepts.

### Decisions

- [0190](../decisions/0190-recipe-contract-checks-placement.md): the check is a package review row, as scoped; the warning is the loader's; `vendor` runs no model.
- [0189](../decisions/0189-contract-checks-out-of-self-improvement.md): this change exists, split from self-improvement.
- [0188](../decisions/0188-self-improvement-open-questions.md), item 0: where the checks were first scoped.

### How the no-instance check works

A new module, `schema_instance.py`, has one function: given a schema, return an instance or `None`. It walks the schema and makes a small list of candidates at each node: the `const` or each `enum` value; for an object, the required properties (and, when an `if` matches, the `then` branch's), each built recursively; for an array, `minItems` copies of an item candidate; for a string, a candidate per `pattern` from a fixed list, else `"x"` padded to `minLength`; numbers at `minimum`. `allOf` merges its branches, `anyOf` and `oneOf` try each, and `not`, `if`, `contains` and anything else are left to the validator, which judges every finished candidate. The search is bounded (a fixed number of candidates per node and in all), so a large schema costs milliseconds. The loader calls it once per distinct output schema after the schema has loaded, and caches the answer by the schema's content hash for the process.

## Plan

### Slice 1: the loader warns about an output schema with no instance

- **Outcome:** `schema.no_instance` from the loader, shown by `vendor` and `plan`; §5.3 and the vendoring manual page describe it.
- **Criteria:**
  - every shipped recipe's output schemas and the runtime schemas yield an instance that validates (suite test);
  - a crafted contradictory schema (a required property whose `enum` is empty after an `allOf`, and the `if`/`then` const clash) is warned about by step and file, and the recipe still loads and plans with exit 0;
  - an instance returned is always valid against the schema (property test over the shipped schemas and small crafted ones).
- **Effort:** M

### Slice 2: recipe-builder@11's package review checks instructions against schemas

- **Outcome:** recipe-builder version 11 with the rubric row; `@10` frozen in `tests/fixtures/recipes/recipe-builder-v10`; §5.7 and the recipe-builder manual page updated.
- **Criteria:**
  - the rubric carries the row, with severity `high` and the result-status case (prompt test);
  - the recipe-builder@7 fixture's research prompt and schema are the contradiction the row names (prompt test: the prompt lets research return `blocked` with the choice open, and the v7 schema requires a `before_design` record to be `decided`), and the v7 schema alone yields an instance, so only the review row can catch it;
  - `@10` keeps its behavior (frozen fixture loads and plans as before).
- **Effort:** S

## Log

### Request approved, Design and Plan written

- **Summary:** The owner answered the open questions and approved the Request (Decision 0190). Criteria rewritten from the answers: the check is a package review row, not the audit's; the warning is a loader warning; `vendor` runs no model. Design and two slices written; title updated (`recipe check` itself is unchanged). Status set to `accepted`; the Design awaits the owner. No code changed.
- **Owner decision:** 2026-11-23, "Package review, as scoped"; "Loader warning"; "No" to a model-run vendor check; "Approve, design next".

### Design approved

- **Summary:** The owner approved the Design and Plan. Status set to `in-progress`.
- **Owner decision:** 2026-11-23, "Approved".

### Slice 1: the loader warns about an output schema with no instance

- **Commit:** `2026-11-recipe-contract-checks: Slice 1, the loader warns about an output schema with no instance`
- **Summary:** New module `schema_instance.py` (`find_instance`): alternatives flattened from `allOf`, `anyOf`/`oneOf` and `if`+`then`/`else`, with combinations whose `const`/`enum` or types plainly clash pruned before the bound (without that, recipe-builder's `design_out.json`, with seven `if` rules on each stage, found nothing); candidates per alternative; every candidate judged by the validator with intake's format checker. The loader (`recipe.py`) warns `schema.no_instance` for each step's own output schema; `plan` prints it; `vendor` (`project.py`) now returns it in `warnings` and still vendors. Only this loader warning was added to `vendor`'s output, to keep the slice narrow; its other loader warnings are unchanged. All 129 schemas under `examples/recipes` and `tests/fixtures/recipes` yield an instance; the shipped catalog takes about 0.15 s in all. Design §5.3; manual `admin/recipes-and-vendoring.md` (#review).
- **Tests:** `tests/test_schema_instance.py`: every shipped recipe's schemas and both runtime schemas yield a valid instance, and no shipped recipe gets the warning; five crafted contradictions have none; five satisfiable shapes (if/then, recursive `$ref`, pattern, `contains`, `anyOf`) yield a valid one; the recipe-builder@7 research schema alone yields an instance; the loader warns by step and file and still loads; `plan` prints it and exits 0; `vendor` returns it and vendors (slow).
- **Review:** none (standard level).

### Slice 2: recipe-builder@11's package review checks instructions against schemas

- **Commit:** `2026-11-recipe-contract-checks: Slice 2, recipe-builder@11's package review checks prompts against schemas`
- **Summary:** recipe-builder version 11. `prompts/package_review_rubric.md` has a `high` row for a step whose prompt and output schema contradict each other (requires what the schema forbids or the reverse; a disposition, answer, evidence or result-status rule, `blocked` with questions included, that no valid output can meet), and a note to read every rule against the schema and the schemas it draws on, name both files in the `location`, and not count an output that validates only by inventing an owner's answer. The review's scope is unchanged (Decision 0190, item 1); `audit` is unchanged. `@10` frozen in `tests/fixtures/recipes/recipe-builder-v10`. Design §5.7 (version 11, the steps table, "Prompts checked against their schemas"); manual `recipe-sources/recipe-builder.md` (#what-it-produces), `recipes/recipe-builder.md` regenerated. Not changed: `2026-11-ai-delegates` (proposed) still plans its marks for `recipe-builder@10`; it will take the next version when it is designed.
- **Tests:** `test_recipe_builder.py`: the row, its severity and the `blocked` case, and the review's scope (prompt test); the recipe-builder@7 research prompt asks for `blocked` with the choice open while its schema requires a `before_design` record `decided`, the case the row names (the schema alone is satisfiable, `test_schema_instance.py`); `@10` frozen without the row. Version references to `@11` in `test_recipe_builder.py` and `test_recipe_builder_runs.py`.
- **Review:** none (standard level).

### Done

- **Summary:** Both acceptance criteria shown by tests: the package review row (Slice 2) and the loader's `schema.no_instance` warning, shown by `plan` and `vendor` (Slice 1). `vendor` runs no model. Status `done`.
