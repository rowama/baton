---
id: "0135"
title: "The Director writes fit-check's project context from detect and a shallow look"
status: accepted
date: 2026-11-12
source: "owner discussion, 2026-11-12"
sections: ["§5.7", "§11.1", "§13.8"]
---

# 0135. The Director writes fit-check's project context from detect and a shallow look

## Context

Decision 0134 needs someone to produce the `context` text. The Director has `detect` and the repo; a helper step inside fit-check would need file access.

## Decision

Accepted by the owner, 2026-11-12: the Director writes it from the `detect` result plus a top-level look (layout, docs folders, filenames), tells the owner what it assumed, and passes it as `context`. The alternative is a new helper step inside fit-check.
