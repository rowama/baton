---
id: "0105"
title: "scope and parent are optional fields in baton-recipe/1; no format bump"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1", "§14.1", "§14.2"]
---

# 0105. scope and parent are optional fields in baton-recipe/1; no format bump

## Context

The loader rejects unknown recipe keys (`recipe.unknown_key`), so new fields need a loader change. Decisions 0019 and 0075 set the precedent: optional additions need no version bump, because the lockfile pins the runtime that reads them.

## Decision

The optional `scope` block (`covers`, `not_for`, `varies_by`) and the optional `parent` field are added to `baton-recipe/1`. No new format version. A recipe without them loads as before. If the loader or schema proves unable to take them additively, the change returns to the owner before any bump.
