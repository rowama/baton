---
id: "0036"
title: "Waiver naming, recording and scope"
status: accepted
date: 2026-11-02
source: "inline note, §9.3"
sections: ["§9.3"]
---

# 0036. Waiver naming, recording and scope

## Context

`waive` covers one gate occurrence; how a gate is named, how the waiver is recorded and which occurrence it covers were open.

## Decision

`gate` is a declared gate's index, its type when unique, `independence` or `protected`; human gates are decided, never waived. The runtime requires the reason (`human_decision {kind: waiver}` then `gate_waived`); the director skill requires the owner's approval. A waiver covers the failed occurrence the step still holds (`scope: held`), else the next occurrence (`scope: next`); one pending waiver per step path and gate.
