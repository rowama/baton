---
id: "0037"
title: "A protected-path change in warn mode waits on the owner"
status: accepted
date: 2026-11-02
source: "inline note, §9.4"
sections: ["§9.4"]
---

# 0037. A protected-path change in warn mode waits on the owner

## Context

What `warn` means for a protected-path change was open.

## Decision

The step waits on the owner like a human gate: `approve` keeps the change, `reject` fails the gate. In `fail` mode the gate fails.
