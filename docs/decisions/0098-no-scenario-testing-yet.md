---
id: "0098"
title: "The builder ships without scenario testing; it is added as a gate when baton simulate exists"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§15.3"]
---

# 0098. The builder ships without scenario testing; it is added as a gate when baton simulate exists

## Context

A dry run through every branch, loop and level would be the strongest check, but `baton simulate` is only planned.

## Decision

Ship without it. When `baton simulate` exists, add it as a `generate` gate in a later change.
