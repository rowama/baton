---
id: "0026"
title: "A judge's failed blocking gate ends the iteration and keeps its result"
status: accepted
date: 2026-11-02
source: "inline note, §5.4"
sections: ["§5.4", "§8.5"]
---

# 0026. A judge's failed blocking gate ends the iteration and keeps its result

## Context

In a `repeat_until` group, a judge whose blocking gate fails could either retry as an attempt or end the iteration.

## Decision

A judge whose declared blocking gate (findings, review, human or script) fails did its work: its result is kept (`step_passed` with `condition.gates_passed: false`), later steps in that iteration never start, and the next iteration starts at `repeat_from` with the open findings and gate reasons. Rejected results, schema failures, failed workers and timeouts still retry the judge as attempts.
