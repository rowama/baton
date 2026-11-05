---
id: "0010"
title: "Concurrent write steps share one workspace lock; worktree isolation deferred"
status: accepted
date: 2026-11-02
source: "§18 #10"
sections: ["§8.9"]
---

# 0010. Concurrent write steps share one workspace lock; worktree isolation deferred

## Context

Worktree isolation for concurrent write-mode steps.

Suggested: lock only at first.

## Decision

lock only; worktree isolation is deferred (it needs a merge strategy). A write step dispatched while the tree is held is queued, first in first out, and started by the process that releases the lock (§8.9).
