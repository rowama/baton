---
id: "0181"
title: "First-use feedback: cost-aware routing by default with subscriptions first; answers carried across rounds; the blocked output reaches its retry; recipe-builder's tiers per step"
status: accepted
date: 2026-11-20
source: "Owner, 2026-11-20: chose the suggested answer to each of four questions (routing order, carried answers, accepted proposals, recipe-builder tiers)"
sections: ["§5.7", "§7.1", "§8.4", "§13.3", "§13.8"]
---

# 0181. First-use feedback: cost-aware routing by default with subscriptions first; answers carried across rounds; the blocked output reaches its retry; recipe-builder's tiers per step

## Context

The owner's first real runs (`2026-11-first-use-feedback-batch-a`, items F-6 to F-8) showed three problems. Routing chose the most expensive model: eligible workers are ordered by verified capabilities, then by name, and `cheapest_first` (Decision [0115](0115-price-is-not-a-concept.md)) is off by default. Turning it on would make things worse, because harness routes (`claude_code`, `codex`) carry no `price` and `routing.price_rank` ranks an unpriced route after every priced one. Every AI step of recipe-builder@7 requires tier `strong`. The owner's answers reach only the next attempt of the step that asked (`packet.prior_feedback`), so the next round of a design-and-review loop asked again. And a retry after answers does not receive the blocked attempt's output, so "accept all as suggested" kept only the word "accept". Four questions were put to the owner with suggested answers; the owner chose each suggestion.

## Decision

1. **Cost-aware ordering is the default.** Among eligible workers that no preference names, the order is:
   - a subscription route with quota left, counted as *included*;
   - then a free route;
   - then a priced route, cheapest first (input plus output per million tokens);
   - then an unpriced route.
   
   Within each class, more verified capabilities first, then by name. The order never makes an ineligible worker eligible. `cheapest_first: false` (`--verified-first`) keeps the old order as an opt-out. When the Director offers a choice of worker, it says what each costs (included in a subscription, free, or the price), and never offers a pay-per-token route ahead of an included one without saying why. A subscription whose quota is exhausted is already excluded until it resets (Decision [0114](0114-quota-exhausted-reroutes.md)).
2. **Answers carry across rounds.** The runtime keeps every confirmed answer in the run, by the step that asked and the question id. Every later attempt of the same step, in any iteration, receives the answers from earlier iterations in `prior_feedback.answers_earlier`, each with the iteration and attempt it came from. A review of that step receives them as well, so it does not fail a design for following the owner's choices. No recipe declaration is added: other steps do not receive them.
3. **The blocked output reaches its retry.** When a step is retried after the owner answers its questions, the retry's `prior_feedback.prior_output` holds the blocked attempt's whole output. The `human_decision` that records the answers carries that output's content hash (`output_sha256`), so it shows exactly what an answer accepted.
4. **recipe-builder's tiers per step.** `guide`, `generate`, `examples` and the programs' `implement` take tier `standard`, since they transcribe or follow a design the owner approved and a review checks. `profile`, `research`, `design`, `audit` and the programs' `review` stay `strong`.
