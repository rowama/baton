---
id: "0106"
title: "Steps can take the vendored and catalog recipe summaries as an input source"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.2", "§5.7", "§11.6"]
---

# 0106. Steps can take the vendored and catalog recipe summaries as an input source

## Context

Framing receives these summaries because the runtime builds its run inputs; an ordinary recipe has no such source, so the builder cannot check existing recipes first and fit-check's `fits` verdict cannot name one.

## Decision

Add one closed-grammar input source, `catalog.summaries`, giving a step the summaries framing already receives. The builder's `profile` and `fit-check` use it. It adds no concept (§2).
