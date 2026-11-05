---
id: "0033"
title: "A busy workspace queues write dispatches"
status: accepted
date: 2026-11-02
source: "inline note, §8.9"
sections: ["§8.9"]
---

# 0033. A busy workspace queues write dispatches

## Context

With the workspace lock only (§18 #10), a write-mode dispatch while the tree is held needed defined behavior.

## Decision

The dispatch joins a first-in-first-out queue and returns `queued`; the step stays `ready`. Whatever releases the lock starts the next entry itself (no daemon), re-checking routing and the lease; an entry that can no longer start is dropped and the hook fires with `not_started`. `cancel` withdraws a queued request.
