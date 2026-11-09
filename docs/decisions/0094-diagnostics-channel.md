---
id: "0094"
title: "Diagnostics are a separate, machine-local, bounded channel"
status: accepted
date: 2026-11-09
source: "change 2026-11-diagnostics (owner, 2026-11-09)"
sections: ["§2", "§4.4", "§8.3", "§8.4", "§13.4"]
---

# 0094. Diagnostics are a separate, machine-local, bounded channel

## Context

The runtime's own fallbacks (swallowed exceptions, cache replays, skipped checks) leave no trace: the event log records only legal transitions, and `src/` has no logging. While Baton is young, these silent paths are where suboptimal conditions hide. Recording them must not touch the state machine, the repo, or owner attention (§1.1), and storage must stay bounded without a daemon (§0 rule 3).

## Decision

Diagnostics are written by `diag.note`, which never raises, to per-process files under `$BATON_HOME/diag/`, never to the project or its event logs. They are redacted on write, and never read by the state machine or used to decide anything. They are machinery (§2), not a concept.

Retention is counted in **usage days** (UTC days with at least one record on the machine), not calendar days. Raw records are kept 14 usage days and at most 64 MiB, pruned on write with no daemon. Before deletion they are rolled up into daily counts kept 180 usage days, so `doctor` can flag unusual codes against a baseline. Owners never see diagnostics unless `doctor` finds something unusual.

Routing exclusions are not diagnostics: they are recorded in the `worker_selected` event as an additive field, with no format version change (as for 0075). Raw worker logs under `~/.baton/logs/` are reported (size, oldest age), not pruned, for now.
