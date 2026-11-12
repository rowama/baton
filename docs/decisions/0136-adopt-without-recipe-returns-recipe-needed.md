---
id: "0136"
title: "adopt with no recipe returns a recipe-needed status that points at fit-check"
status: accepted
date: 2026-11-12
source: "owner discussion, 2026-11-12"
sections: ["§11.1", "§13.8"]
---

# 0136. adopt with no recipe returns a recipe-needed status that points at fit-check

## Context

`adopt` requires a recipe, and nothing tells the Director how to find or build one for an existing project.

## Decision

Accepted by the owner, 2026-11-12: `baton adopt` with no recipe starts nothing and returns a "recipe needed" status naming the procedure: fit-check with project context (0134), then `adopt` with the chosen recipe, `recipe-builder` when none fits, or stop. The alternative is Director guidance only, with `adopt` still refusing a missing recipe.
