---
id: "0127"
title: "The manual has user, admin and recipe parts; recipe-author documentation is a later change"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§13.9"]
---

# 0127. The manual has user, admin and recipe parts; recipe-author documentation is a later change

## Context

Open question 2. The suggestion was three parts (context, user, admin) with recipe documentation left out. The owner (2026-11-11) concurred and added: write the manual sections for the current recipes.

## Decision

- Parts: `user/` (what an owner can and should do), `admin/` (configuration and operations for IT), `reference/` (generated) and `recipes/`, one topic per shipped recipe: `fit-check`, `software-feature`, `backyard-project`, `recipe-builder` and the built-in `baton-adopt` and `baton-frame`. A recipe topic says what the process is for, what the owner will be asked, what it produces and what it needs (its step and gate table is generated from the recipe). A test fails for a shipped recipe with no topic.
- Writing recipes (an author's guide) stays out until a follow-up change; the manual links to §5 meanwhile.
