---
id: "0032"
title: "A stale step is never readied automatically"
status: accepted
date: 2026-11-02
source: "inline note, §8.1"
sections: ["§8.1", "§8.9"]
---

# 0032. A stale step is never readied automatically

## Context

After `revise`, accepted dependents become `stale`. Rerunning them automatically could waste work when the upstream change does not affect them.

## Decision

Once its dependencies are satisfied a stale step is runnable: dispatching it reruns it, or the owner confirms it unchanged (`decide <step> confirm`). It is not a pending owner decision.
