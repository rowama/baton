---
id: "0114"
title: "Quota exhaustion is a classified platform condition that re-routes without spending an attempt"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§8.4", "§8.8"]
---

# 0114. Quota exhaustion is a classified platform condition that re-routes without spending an attempt

## Context

A free route has a daily quota; a subscription CLI has its own limits.

## Decision

`quota_exhausted` is a `platform` failure that re-routes the step to the next eligible worker without counting an attempt, like `capability_absent` (0086). It covers free-route quotas and subscription-CLI quota. The failover question left open in 2026-11-step-tool-harness moves to 2026-11-model-listings.
