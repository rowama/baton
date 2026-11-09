---
id: "0094"
title: "Diagnostics are a separate, machine-local, bounded channel"
status: proposed
date: 2026-11-09
source: "change 2026-11-diagnostics (proposed)"
sections: ["§4.4", "§8.3", "§13.4"]
---

# 0094. Diagnostics are a separate, machine-local, bounded channel

## Context

The runtime's own fallbacks (swallowed exceptions, cache replays, skipped checks) leave no trace: the event log records only legal transitions, and `src/` has no logging. While Baton is young, these silent paths are where suboptimal conditions hide. Recording them must not touch the state machine, the repo, or owner attention (§1.1), and storage must stay bounded without a daemon (§0 rule 3).

## Decision

Open. Proposed: diagnostics are written by `diag.note`, which never raises, to per-process files under `$BATON_HOME/diag/`, never to the project or its event logs; they are redacted on write and never read by the state machine or used to decide anything. Raw records are kept a short window and pruned by age and size on write; before deletion they are rolled up into daily counts kept longer, so `doctor` can flag unusual codes against a baseline. Owners never see them unless `doctor` finds something unusual.
