---
id: "0009"
title: "Effort bands are 45 min / 2 h / 4 h, extended once"
status: accepted
date: 2026-11-02
source: "§18 #9"
sections: ["§8.7"]
---

# 0009. Effort bands are 45 min / 2 h / 4 h, extended once

## Context

Effort bands and `extend_once`.

Suggested: 45 min / 2 h / 4 h; extend once.

## Decision

as suggested; steps that declare no effort get the M band (`effort.default`); manual workers are never timed out; an extension is recorded as `deadline_extended` (§8.7). The effort scale stays the runtime's fixed `S`/`M`/`L` for now. A possible later change (not built): recipes declare their own ordered effort scale (default `[S, M, L]`), `project.yaml` maps the names to durations, and an unmapped name falls back by position. Effort stays independent of triage complexity levels: levels choose steps and gates, effort budgets one step's time.
