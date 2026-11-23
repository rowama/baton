---
id: "0190"
title: "Recipe contract checks: the prompt-against-schema check is a row of the package review as scoped; the no-instance warning is the loader's; vendor runs no model"
status: accepted
date: 2026-11-23
source: 'Owner, 2026-11-23, answering the change''s open questions: "Package review, as scoped"; "Loader warning"; vendor review "No"; Request "Approve, design next"'
sections: ["§5.3", "§5.7"]
---

# 0190. Recipe contract checks: the prompt-against-schema check is a row of the package review as scoped; the no-instance warning is the loader's; vendor runs no model

## Context

[2026-11-recipe-contract-checks](../changes/2026-11-recipe-contract-checks.md) (Decision [0189](0189-contract-checks-out-of-self-improvement.md)) asked for a check in recipe-builder's `audit` that a built recipe's instructions and output schemas don't contradict each other, and a warning in `baton recipe check` and `vendor` for an output schema with no valid instance. Reading the builder showed two misfits. `audit` judges the design (its stages, ledger and discovery records) before `generate` writes any prompt or schema, so it cannot see the contradiction; `generate`'s package review sees the package, but runs only at approach `complex` or when software is built. And `recipe check` needs the builder's requirements ledger, so a recipe that comes from elsewhere never meets it; the loader's warnings are what `vendor` and `plan` already print.

## Decision

1. **The prompt-against-schema check is a row of recipe-builder's package review rubric**, not of `audit`. The review keeps its scope (approach `complex`, or software `simple` or `engineered`); simple and standard builds without software are not checked by it.
2. **The no-instance warning is a loader warning**, so `vendor`, `plan` and the builder's `baton plan` gate show it. It never refuses a recipe and changes no exit code, so the gates of a pinned recipe keep their behavior. `recipe check` is unchanged.
3. **`vendor` runs no model.** A recipe vendored from elsewhere gets the deterministic warning only; the prompt-against-schema judgment happens when a recipe is built.
