---
id: "0028"
title: "Re-triage reruns triage behind a human gate"
status: accepted
date: 2026-11-02
source: "inline note, §5.5"
sections: ["§5.5", "§8.1"]
---

# 0028. Re-triage reruns triage behind a human gate

## Context

Scope can change after triage; the Director may not add or skip steps itself, so the level must be changeable through the record.

## Decision

`retriage(run, reason)` reruns triage; the new result always waits on the owner. Approving skips or unskips only steps that have not started; started, passed and imported steps never change and are flagged `pre_retriage` where the new level would differ. Rejecting keeps the old level. Refused while attempts are in flight, another re-triage is pending, or before a level is set.
