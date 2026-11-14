---
id: "0151"
title: "Project policy: permissions are the release authority, hand edits wait for confirmation, re-triage takes current policy"
status: accepted
date: 2026-11-14
source: "Owner, 2026-11-14: Accept all for B and D."
sections: ["§5.2", "§5.5", "§13.7"]
---

# 0151. Project policy: permissions are the release authority, hand edits wait for confirmation, re-triage takes current policy

## Context

Writing `2026-11-project-policy` from Decision 0143 raised six questions. The suggested answers were put to the owner in one batch.

## Decision

1. **Release authority is the existing action permissions** (§13.7, 0050). They keep their key, values and enforcement and come under the recorded-change rule. There is no second release block.
2. **Hand edits are detected, never refused.** Runs keep the last recorded policy until the owner confirms the edit (`policy confirm`).
3. **A floor for all recipes** (`"*"`) applies to every recipe that declares that axis with that value in its scale, and to no other. `check` warns when it matches nothing.
4. **Re-triage applies the policy current at the time** and records its hash.
5. **Governing recipes** are shown in `catalog.summaries`, `recipes()` and the Director skill now, and in framing's and the project review's proposals with `2026-11-project-review`.
6. **Workers see the policy** only through an explicitly declared `project.policy` input.
