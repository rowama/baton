---
id: "0175"
title: "Models are assessed by capability checks run once, tiers from published evaluations, and evidence from use: shadow attempts on strong steps, gated trial routing on the rest, replay later"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"I do want the capability verification checks.\"; \"these verification checks should only need to run once. Maybe triggered from the setup UI.\"; \"it doesn't make sense not to start with publically available benchmark results\"; \"Concur checks once from setup and amending 0110. The ideas I had are your 1 and 2. I also like your 3. While I'm building the history for #1, I want to start with 2 for the high stakes (i.e, strong) steps and 3 for the low stakes steps.\""
sections: ["§6.1", "§6.4", "§8.4", "§13.9"]
---

# 0175. Models are assessed by capability checks run once, tiers from published evaluations, and evidence from use: shadow attempts on strong steps, gated trial routing on the rest, replay later

## Context

On the owner's first real run, routing could choose only among a few expensive models (`2026-11-first-use-feedback-batch-a`, F-6). The shipped known-workers data judges 29 models, and its tiers are a research worker's judgment from vendor positioning ("flagship → strong, mid → standard, small/lite → basic, not from benchmarks", worker-research report of 2026-11-06). Every other listed model is tier `basic` with only catalog capabilities (Decision [0110](0110-unjudged-model-default-tier.md)), and a live check (Decision [0081](0081-live-verification-on-request.md)) proves only that a route answers. Evidence from use needs models to be used, and no owner wants to try an unproven model on an important step.

## Decision

1. **Capability checks, run once.** Baton ships a small set of cheap, automatically graded checks per capability. They run on the owner's request, from the setup page or the CLI, once per model and route; they run again only for an alias route, a new version of the check set, or the owner asking. A pass records the capability `verified` with the check as evidence.
2. **Tiers from published evaluations.** A model's tier may rest on published evaluation results, cited with the evaluation and its date. Decision 0110 is amended: an unjudged model with no evidence stays `basic`, but tiers are no longer limited to vendor positioning and may be derived from published evaluations.
3. **Shadow attempts for strong steps.** On a step requiring `strong`, a candidate model may be given the same packet alongside the chosen worker. Its result is graded and recorded, never used.
4. **Trial routing for the other steps.** A step below `strong` may go to a candidate model when its gates can catch a bad result; a failure is retried on a proven model.
5. **Replay comes later.** Re-running past accepted packets on candidate models is the long-term evidence source, built once the owner has history to replay.
6. Built as `2026-11-model-assessment`.
