---
id: "0097"
title: "The builder never edits a vendored recipe in place"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.8"]
---

# 0097. The builder never edits a vendored recipe in place

## Context

Runs pin recipe versions, so an in-place edit would change what a pinned run means.

## Decision

Specializing or widening always produces a new recipe id or a new version (§5.8), never an edit of a vendored recipe.
