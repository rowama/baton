---
id: "0003"
title: "Independent top-level steps of one run may run in parallel"
status: accepted
date: 2026-11-02
source: "§18 #3"
sections: ["§18"]
---

# 0003. Independent top-level steps of one run may run in parallel

## Context

Dispatching independent top-level steps of one run in parallel (beyond groups and concurrent runs)?

Suggested: allowed, subject to the workspace lock.

## Decision

allowed, as suggested; write-mode steps are serialized once the workspace lock exists (Phase 10).
