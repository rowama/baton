---
id: "0176"
title: "Model assessment: independent evaluations preferred, short code-graded checks, checks add only what they fully prove, gates grade candidates, 5 passes to prove and 2 failures to demote, off until the owner turns it on, machine-wide evidence, no new concept"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"Concur on all.\" (the nine suggested answers of 2026-11-model-assessment)"
sections: ["§2", "§6.1", "§6.4", "§8.4", "§8.7", "§13.9"]
---

# 0176. Model assessment: independent evaluations preferred, short code-graded checks, checks add only what they fully prove, gates grade candidates, 5 passes to prove and 2 failures to demote, off until the owner turns it on, machine-wide evidence, no new concept

## Context

Decision [0175](0175-model-assessment.md) set the approach for learning what each model can do: checks run once, tiers from published evaluations, shadow attempts on strong steps, trial routing on the rest. Change `2026-11-model-assessment` put nine questions to the owner, each with a suggested answer; the owner concurred with all nine.

## Decision

1. **Evaluations.** Independent leaderboards that publish their method and test the models themselves are preferred over a vendor's figures about its own model; a vendor's figure counts only where no independent one exists. Every tier resting on evaluations cites at least one, and the shipped mapping names which evaluation informs which capability (coding evaluations for `technical_reasoning`, for example).
2. **Checks.** Three to five tasks per capability, each a few hundred tokens, graded by code only: a reply matching a schema, a correct tool call, an answer found only in a supplied file, a set of explicit constraints all followed, small reasoning problems with one right answer. `long_form_writing` is checked for length, structure and constraints, not quality.
3. **What a check may add.** A passed check may add `structured_output`, `tool_use` or `workspace_read` to an unjudged model's capabilities. `technical_reasoning`, `long_form_writing`, `vision` and the tier come only from evaluations or a track record; a check on those only verifies a claim the profile already makes.
4. **Grading a shadow attempt.** By the step's schema and script gates, and by whether the chosen worker's result passed. No model judges a candidate in this version.
5. **Promotion.** A candidate is proven at a tier after 5 passed shadow attempts or trials at that tier with no failure in its last 5; it is put back after 2 failures in its last 5. The thresholds are shown to the owner and adjustable.
6. **Budgets.** Shadowing and trials are both off until the owner turns them on in the setup page. When on: at most one shadow candidate per step, a daily credit limit the owner sets, and trials only on models that are free or cheaper than the proven worker.
7. **Where it lives.** The track record is machine-wide, in `~/.baton/` beside the capability states; the settings are machine preferences (Decision [0124](0124-machine-level-preferences.md)).
8. **Cost-aware routing.** Independent of `2026-11-first-use-feedback-batch-a` F-6: F-6 orders proven workers by cost, this change grows the set of proven workers; either may land first.
9. **No new concept.** The check set is shipped profile knowledge, like the known-workers data; the track record is evidence behind capability states and tiers; shadow attempts and trials are dispatches. §2 says so, as it does for worker setup. The owner meets none of these terms: the Director says a step was tried on a cheaper model.
