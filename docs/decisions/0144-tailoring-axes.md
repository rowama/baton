---
id: "0144"
title: "Complexity is rated on a few recipe-owned axes instead of one scale"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: Concur with section recommendations for A, B, C, E1-4 (no new concept at E5). Write A and C change proposals."
sections: ["§5.5", "§9.1"]
---

# 0144. Complexity is rated on a few recipe-owned axes instead of one scale

## Context

A run's tailoring today is one ordered level (§5.5). eng-process needs to separate concerns that vary independently: a one-line permissions fix needs strong verification and little discovery; a large low-risk project needs planning but light release control. The owner wants the many concerns to project onto three or four axes, with only the axes that matter changing anything. The exploration is `docs/catchall/project-process-linkage.md` (§4, §5 C).

## Decision

1. The recipe defines its axes, as it defines its levels today. A recipe with today's `levels` is a one-axis recipe and is unchanged.
2. Each axis has a recipe-owned ordered scale.
3. A step or gate lists conditions per axis; it applies when **any** listed axis matches (OR). A step with no `applies_to` always runs. Gates that differ by axis are separate gate entries.
4. Triage gives a reason for every axis (schema-checked). All axes at their lowest is applied at once, as today; anything else waits on the owner. A policy floor (Decision 0143) raises a rating automatically and says why.
5. Re-triage works per axis, otherwise by today's rules (Decision 0028). A worker's result may carry a structured signal that a rating should change, which the Director turns into a re-triage request.
6. Whether this is additive within `baton-recipe/1` or a format version is decided in Design.
