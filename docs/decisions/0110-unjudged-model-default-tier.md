---
id: "0110"
title: "A listed model with no researched entry is tier basic with no judgment capabilities"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4", "§8.4"]
---

# 0110. A listed model with no researched entry is tier basic with no judgment capabilities

## Context

A listing gives price, context and catalog-basis capabilities but not tier or judgment.

## Decision

An unjudged listed model gets tier `basic` and only its catalog-basis capabilities. A step needing `technical_reasoning` or a higher tier never goes to it. Assessment (0111) lifts it. Tiers are not derived from listing `benchmarks`.
