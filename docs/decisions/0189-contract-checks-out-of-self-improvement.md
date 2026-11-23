---
id: "0189"
title: "Self-improvement: contract checks before runs leave the change; it handles problems that got past every check"
status: accepted
date: 2026-11-23
source: 'Owner, 2026-11-23: "Proceed as you have suggested" (to taking the contract checks out of 2026-11-self-improvement)'
sections: ["§12.4", "§5.1"]
---

# 0189. Self-improvement: contract checks before runs leave the change; it handles problems that got past every check

## Context

Decision [0188](0188-self-improvement-open-questions.md), item 0, put four slices in [2026-11-self-improvement](../changes/2026-11-self-improvement.md), the third being contract checks before runs: simulated runs of every shipped recipe, a schema satisfiability check in `recipe check`, and a contract-consistency check in recipe-builder's audit. On starting it, two things showed: schema-generated outputs fail most shipped recipes' script gates, so the simulated runs would mostly stop at the circuit breaker and say nothing about contradictions; and the recipe-builder@7 contradiction it was meant to catch was between prompt and schema, which a schema check can't see. The owner then asked whether the slice was in the lane of self-improvement at all: testing is another lane, and self-improvement deals with the problems that escape detection in design, implementation and testing, by fixing them and adding them to the regression.

## Decision

1. **Self-improvement is about problems that got past every check:** noticing them (cases, from the Director or a detector), capturing them (the repro bundle), and fixing them upstream with a regression test. Checking recipes before they ship is recipe authoring, not self-improvement.
2. **Slice 3 leaves the change.** 2026-11-self-improvement delivers three slices: cases with the repro bundle, the circuit breaker, and baselines with detectors. This amends 0188, item 0.
3. **The two recipe-authoring checks are kept as a proposed change of their own**, [2026-11-recipe-contract-checks](../changes/2026-11-recipe-contract-checks.md): a contract-consistency check in recipe-builder's audit, and a schema satisfiability warning in `recipe check` and `vendor`. Not urgent.
