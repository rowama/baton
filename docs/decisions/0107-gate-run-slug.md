---
id: "0107"
title: "A script gate's command can use run.slug"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.3", "§9.1"]
---

# 0107. A script gate's command can use run.slug

## Context

Script gate commands render only `project.*`, `paths.*` and `run.id`, while `publish.to` also has `run.slug`. The builder's `generate` step must run `baton plan` on a draft directory named by the run slug (0095), and no deterministic gate could name it.

## Decision

`run.slug` is added to the variables a script gate command renders, with the same value `publish.to` uses. Additive; no recipe or format change.
