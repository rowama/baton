---
id: "0115"
title: "Price is a profile field and a routing preference, not an owner concept"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§2", "§6.1", "§8.4"]
---

# 0115. Price is a profile field and a routing preference, not an owner concept

## Context

Does price add to the concept budget?

## Decision

No. Price is a profile field (per million input and output tokens, `free`, or `subscription`) with its source and date, and a cheapest-first ordering preference. It never makes an ineligible profile eligible. It is noted in §2's worker-setup note, with no new concept.
