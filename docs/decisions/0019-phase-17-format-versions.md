---
id: "0019"
title: "Phase 17 additions need no format version bump"
status: accepted
date: 2026-11-04
source: "§18 #19"
sections: ["§18"]
---

# 0019. Phase 17 additions need no format version bump

## Context

Format versions for Phase 17's additions (structured questions, `answers`, human-gate `labels`, framing events).

Suggested: Additive within the current `baton-packet/1`, `baton-recipe/1` and `baton-events/1`, no version bump: every addition is optional or a new event type, and the lockfile already pins the runtime that reads them..

## Decision

as suggested: bare-string questions still validate; `prior_feedback.answers`, gate `labels` and `framing_selected` are additive.
