---
id: "0100"
title: "When several recipes fit, the owner's own come first, then the most specific, then the more general"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1", "§11.6"]
---

# 0100. When several recipes fit, the owner's own come first, then the most specific, then the more general

## Context

More than one recipe can cover a job once scope blocks exist; the choice must be predictable.

## Decision

Prefer the owner's own recipes, then the most specific recipe that covers the whole job (it carries more domain knowledge), then the more general one. Ties go to the owner.
