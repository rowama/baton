---
id: "0179"
title: "Trial and shadow routing: candidate selection, effects, reviews, budgets and evidence identity"
status: proposed
date: null
source: "Implementation review of 2026-11-model-assessment, 2026-11-19; six questions put to the owner, answers pending"
sections: ["§6.4", "§8.4", "§8.7", "§8.10", "§13.9", "§15.2"]
---

# 0179. Trial and shadow routing: candidate selection, effects, reviews, budgets and evidence identity

## Context

Decisions [0175](0175-model-assessment.md) and [0176](0176-model-assessment-details.md) authorize capability checks, evaluation tiers, trials and shadow attempts. The first two slices are committed. Reviewing the remaining slices against the code exposes six questions that the approved outline does not settle.

Routing currently has no separate proven status: claimed capabilities, capability states, tier and independence determine eligibility (`routing.requirement_gaps`, `routing.eligible_workers`). The recipe's `Step` has no effect declaration; the recipe-builder's design output records effects but does not put them into executable steps. A review gate opens a separate dispatch and resolves later (`engine._open_review`, `engine._review_finished`). Usage is measured after calls, not reserved before them. The initial track record is keyed by profile name and retains the last check. Script gates run commands, regardless of the worker's workspace mode.

## Decision

**Open.** These are suggestions submitted together to the owner, not accepted rules. Existing accepted decisions remain in force.

1. **Candidates and fallbacks.** Suggested: retain all capability, tier and independence requirements. The worker selected by the Director for ordinary use is the fallback; another eligible model without five passes at the required tier may be the candidate. Existing eligibility stays usable without demanding five prior trial passes from every worker. Alternative: permit trials one tier above the candidate's rating, up to standard. The owner must settle whether this change can override a tier requirement and how the initial fallback earns trust; an evaluation tier and a record of successful work are distinct evidence.
2. **Reversible effects.** Suggested: add a step `effect` declaration (`none`, `reversible`, `irreversible`); omission prevents a trial. Workspace mode alone cannot establish reversibility, since workers may call external services. Alternative: initially restrict trials to Baton's API runner with read-only tools. The first option changes the recipe format and authoring guidance; it needs corresponding design and manual edits in its implementation slice.
3. **Review-gated trials.** Suggested: include blocking reviews from the outset, as criterion 7 allows. Keep the trial pending until its blocking review passes; rejection readies the producer for its fallback without charging the producer's attempt budget. Advisory reviews do not qualify. Alternative: initially support only schema plus blocking script gates, explicitly narrowing the first delivery. A passing schema alone must not promote a candidate whose review is pending or rejected.
4. **Daily budget enforcement.** Suggested: reserve a conservative estimate under a machine-wide lock before dispatch, reconcile actual usage afterwards and decline paid assessments when price or a usable estimate is missing. The page explains that provider charges can exceed estimates. Alternative: require hard spending controls before paid trials or shadows. Post-call usage alone cannot guarantee the approved budget ceiling; the owner must approve the intended meaning before implementation. Concurrent dispatches must not each claim the same available budget.
5. **Evidence identity.** Suggested: scope evidence to canonical model and route configuration, rather than profile name alone. A changed model, endpoint or harness version starts fresh; aliases can be checked but cannot earn lasting promotion. Alternative: let an alias retain promotion until the harness version changes. Reusing a profile name must not silently attach an old model's evidence to a new model. Existing last-check records need a compatible migration or an explicit distinction from promotion evidence.
6. **Shadow gate effects.** Suggested: require an explicit declaration that a step is safe for repeated evaluation, and run its gates in a separate scratch copy. Alternative: initially grade by schema alone, which would amend the approved schema-and-script grading rule. A read-only worker does not make a gate command read-only; a scratch copy protects project files but cannot itself prevent external effects.

The implementation plan also needs to resolve packet provenance without weakening identity checks: `packet.build` includes the worker profile name, profile hash and route-dependent tools in the packet hash. The approved phrase “same packet” therefore needs a precise definition for a separately identified shadow worker. This is an implementation constraint to address when refining slice 4, not permission to record the primary worker's identity for the candidate.
