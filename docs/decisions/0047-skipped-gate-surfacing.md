---
id: "0047"
title: "A skipped blocking gate is surfaced to the owner immediately"
status: accepted
date: 2026-11-03
source: "inline note, §12.4"
sections: ["§12.4"]
---

# 0047. A skipped blocking gate is surfaced to the owner immediately

## Context

Baton enforces its own gates, so a skipped blocking gate or approval can only happen outside it, and must not wait for a retrospective.

## Decision

`feedback skipped_step … --gate` records `process_feedback` and `step_skip_recorded`; unless the gate is advisory, `on_needs_human` fires at once and an owner notice stays pending until acknowledged (`decide <run> skip:<seq> acknowledge`). The notice blocks nothing.
