---
id: "0182"
title: "Model assessment: shadows graded by their own gates with shared failures forgiven; put back means one tier lower until promoted, announced and listed, cleared by a new identity or rating; $0 budget means free models only; shipped recipes declare effects where clear"
status: accepted
date: 2026-11-20
source: 'Owner, 2026-11-20: chose the suggested answer to each of four questions while slices 3 and 4 of 2026-11-model-assessment were refined ("Own gates; forgive shared failure", "One tier lower", "$0 = free models only", "Declare where clear")'
sections: ["§5.1", "§6.4", "§8.4", "§8.7", "§13.3", "§13.9"]
---

# 0182. Model assessment: shadow grading, put back, the default budget and shipped effect declarations

## Context

Decisions [0176](0176-model-assessment-details.md) and [0179](0179-trial-and-shadow-routing-details.md) left four points to settle when slices 3 and 4 of `2026-11-model-assessment` were refined against the code: how a shadow's grade depends on the primary worker's outcome (0176, item 4), what "put back" (0176, item 5) changes in routing, the default daily limit (0176, item 6), and whether any shipped recipe declares the step effects that trials need (0179, item 2). The owner asked what "proven" and "put back" mean for eligibility; the answer: neither changes a model's rating, and evidence is kept per tier of the step. A model is a candidate only at tiers its rating already allows.

## Decision

1. **Shadow grading.** A shadow attempt passes when its own schema and script gates pass. When it fails and the primary attempt it shadowed also failed its gates, the failure is not held against the candidate (the task may be at fault). The grade is written once both have ended, so their order cannot change it; a primary that ends without a gate verdict (timed out, orphaned, cancelled) leaves the shadow's own gates to decide.
2. **Put back.** A model with 2 failures in its last 5 trials or shadows at a tier is treated as one tier below that tier for routing until the owner promotes it (a model put back at `standard` does `basic` steps only). It is never a candidate at that tier meanwhile. The Director tells the owner in plain words when it happens; the setup page marks put-back models with a **Promote** action and a filter; `workers status` lists them with the tier, the date and the failures. Evidence resets, and so a put back clears, when the model, endpoint or harness version changes (0179, item 5) or a new published rating for the model is recorded. Put back does not expire by time.
3. **Proven.** Proven at a tier (5 passes, no failure in the last 5) never changes eligibility: the model stays eligible wherever its rating allows and is no longer tried as a candidate at that tier.
4. **Budget.** The daily limit is in US dollars and limits reservations (0179, item 4). Its default is $0: turned on, trials and shadows try free models only (subscription routes count as $0) until the owner sets a higher limit.
5. **Shipped recipes.** This change declares `effect`, and where safe the repeated-evaluation declaration that shadows need, on shipped recipe steps whose effect is clear from what they do. Steps that may touch outside services stay undeclared, so they are never tried.
