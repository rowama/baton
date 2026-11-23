---
id: 2026-11-recipe-contract-checks
title: "Recipe builder and recipe check catch a recipe whose instructions and schemas contradict each other before it ships"
status: proposed
level: standard
decisions: ["0189", "0188"]
touches: [design/recipes.md]
manual: []
---

# Recipe builder and recipe check catch a recipe whose instructions and schemas contradict each other before it ships

> Split out of [2026-11-self-improvement](2026-11-self-improvement.md) by Decision [0189](../decisions/0189-contract-checks-out-of-self-improvement.md), 2026-11-23: checking recipes before they ship is recipe authoring, not self-improvement. Not urgent. Request not yet discussed with the owner.

## Request

### Problem

A recipe whose instructions demand what its output schema forbids (or forbid what it requires) can't be passed by an honest worker: the step fails, retries and, since the circuit breaker (§8.8), stops on its second identical failure. First use met this once: `issues/2026-11-19-research-blocked-vs-schema.md` (recipe-builder@7: the prompt let research report a choice as open while the schema required it decided). It was fixed by hand in recipe-builder, with a regression run in `tests/test_recipe_builder_runs.py`. Nothing checks for the class before a recipe ships.

What doesn't work, from the self-improvement investigation: simulated runs with outputs generated from each schema fail most shipped recipes' script gates (ledger, guess and budget checks) and so test nothing about contradictions; and the recipe-builder@7 schema was satisfiable on its own: the contradiction was between prose and schema.

### Acceptance criteria

- Recipe builder's audit step checks a built recipe's instructions against its output schemas: does a prompt require what the schema forbids or forbid what it requires; does each disposition, answer and evidence rule it states have a way to be met. A fixture recipe with the recipe-builder@7 contradiction is reported by the audit prompt's rule (prompt test), and the audit output names the step.
- `baton recipe check` and `vendor` warn (never refuse) when an output schema has no instance the check can build, for the JSON Schema subset shipped recipes use (`type`, `required`, `properties`, `enum`, `const`, `items`, `minItems`, `if`/`then`, `allOf`, `$ref` within the package; patterns by fixed candidates). It is a warning because the generator can't prove a schema unsatisfiable outside that subset. Every shipped recipe's schemas yield an instance (suite test); a crafted contradictory schema is warned about by name.

### Open questions

- Whether the audit check should also cover a recipe being vendored from elsewhere (it needs a model; `vendor` today runs none).

## Design

### Doc edits

- `design/recipes.md` §5.1: the satisfiability warning in `recipe check` and `vendor`; the contract-consistency check in recipe-builder's audit.

### Manual edits

- To be settled with the Design: `manual/reference/commands.md` if `recipe check` output changes.

### Decisions

- [0189](../decisions/0189-contract-checks-out-of-self-improvement.md): this change exists, split from self-improvement.
- [0188](../decisions/0188-self-improvement-open-questions.md), item 0: where the checks were first scoped.

## Plan

### Contract checks in the audit and in recipe check

- **Outcome:** the two checks above.
- **Criteria:**
  - as in the acceptance criteria.
- **Effort:** M

## Log
