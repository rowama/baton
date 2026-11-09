---
id: "0103"
title: "A generated recipe records parent: {id, version}, or parent: null when built from scratch"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1", "§14.1"]
---

# 0103. A generated recipe records parent: {id, version}, or parent: null when built from scratch

## Context

Provenance cannot be recovered later and is the only one-way door of the recipe tree (hold decision 2026-11-08).

## Decision

`generate` writes `parent: {id, version}` when the recipe was built from `base_recipe`, and `parent: null` when built from scratch. An absent field marks a legacy recipe; both are roots. The field has no runtime effect, and the recipe runs without knowledge of its parent.
