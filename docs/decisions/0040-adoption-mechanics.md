---
id: "0040"
title: "Adoption is an adoption run plus one baseline decision"
status: accepted
date: 2026-11-02
source: "inline note, §11.1"
sections: ["§11.1", "§11.5"]
---

# 0040. Adoption is an adoption run plus one baseline decision

## Context

Adoption had to fit the concept budget (§2) and end in exactly one owner decision.

## Decision

`adopt` starts a run of the built-in `baton-adopt@1` recipe whose one step is research; when it passes, one work-item run per in-flight item is started and triaged; the runtime then writes `baseline.yaml` and the owner makes one decision, `establish_baseline`.
