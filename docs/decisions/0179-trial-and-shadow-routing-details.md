---
id: "0179"
title: "Trial and shadow routing: candidate selection, effects, reviews, budgets and evidence identity"
status: accepted
date: 2026-11-19
source: 'Owner, 2026-11-19: "for now, agree with all" (the six suggested answers for trial and shadow routing)'
sections: ["§6.4", "§8.4", "§8.7", "§8.10", "§13.9", "§15.2"]
---

# 0179. Trial and shadow routing: candidate selection, effects, reviews, budgets and evidence identity

## Context

Decisions [0175](0175-model-assessment.md) and [0176](0176-model-assessment-details.md) authorize capability checks, evaluation tiers, trials and shadow attempts. The first two slices are committed. Reviewing the remaining slices against the code exposes six questions that the approved outline does not settle.

Routing currently has no separate proven status: claimed capabilities, capability states, tier and independence determine eligibility (`routing.requirement_gaps`, `routing.eligible_workers`). The recipe's `Step` has no effect declaration; the recipe-builder's design output records effects but does not put them into executable steps. A review gate opens a separate dispatch and resolves later (`engine._open_review`, `engine._review_finished`). Usage is measured after calls, not reserved before them. The initial track record is keyed by profile name and retains the last check. Script gates run commands, regardless of the worker's workspace mode.

## Decision

The owner accepted all six suggested answers for now on 2026-11-19. These refine the remaining slices of `2026-11-model-assessment`; they do not claim those slices are implemented.

1. **Candidates and fallbacks.** Retain all capability, tier and independence requirements. The worker selected by the Director for ordinary use is the fallback; another eligible model without five passes at the required tier may be the candidate. Existing eligibility stays usable without demanding five prior trial passes from every worker. Trials do not allow a model rated one tier lower to bypass the step's tier requirement.
2. **Reversible effects.** Add a step `effect` declaration (`none`, `reversible`, `irreversible`); omission prevents a trial. Workspace mode alone cannot establish reversibility, since workers may call external services. The recipe format and authoring guidance gain this declaration in the implementation slice, with corresponding manual edits.
3. **Review-gated trials.** Include blocking reviews from the outset, as criterion 7 allows. Keep the trial pending until its blocking review passes; rejection readies the producer for its fallback without charging the producer's attempt budget. Advisory reviews do not qualify. A passing schema alone must not promote a candidate whose review is pending or rejected.
4. **Daily budget enforcement.** Reserve a conservative estimate under a machine-wide lock before dispatch and reconcile actual usage afterwards. Decline paid trials and shadows when price or a usable estimate is missing. The page explains that provider charges can exceed estimates: the limit controls reservations and subsequent dispatch, not a guaranteed ceiling on provider charges. Concurrent dispatches must not each claim the same available budget. This refines the budget wording of Decision 0176 and criterion 9 of the change.
5. **Evidence identity.** Scope evidence to canonical model and route configuration, rather than profile name alone. A changed model, endpoint or harness version starts fresh; aliases can be checked but cannot earn lasting promotion. Reusing a profile name must not silently attach an old model's evidence to a new model. Existing last-check records need a compatible migration or an explicit distinction from promotion evidence.
6. **Shadow gate effects.** Require an explicit declaration that a step is safe for repeated evaluation, and run its gates in a separate scratch copy. Retain the approved schema-and-script grading rule. A read-only worker does not make a gate command read-only; a scratch copy protects project files but cannot itself prevent external effects.

The implementation plan also needs to resolve packet provenance without weakening identity checks: `packet.build` includes the worker profile name, profile hash and route-dependent tools in the packet hash. The approved phrase “same packet” therefore needs a precise definition for a separately identified shadow worker. This is an implementation constraint to address when refining slice 4, not permission to record the primary worker's identity for the candidate.
