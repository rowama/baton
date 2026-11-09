---
id: "0102"
title: "A process plan is a published file at recipes/plans/<plan id>.md"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§11.6"]
---

# 0102. A process plan is a published file at recipes/plans/<plan id>.md

## Context

A later build must find an earlier split without the owner describing the business again.

## Decision

The plan is a published artifact at `recipes/plans/<plan id>.md`, read by `profile` with `workspace: read`. Not a Director-supplied run input. Stitching one large recipe also needs the full text of existing recipes: vendored ones are readable in the project, and catalog ones ship in the runtime package, which the catalog summaries input (0106) must cover.
