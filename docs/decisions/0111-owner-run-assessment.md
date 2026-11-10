---
id: "0111"
title: "Research can run on the owner's machine for chosen models, into a machine-local overlay"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4"]
---

# 0111. Research can run on the owner's machine for chosen models, into a machine-local overlay

## Context

Research is maintainer-only today (0083).

## Decision

An owner may assess selected models: a research dispatch scoped to them, through the owner's own workers, writing `~/.baton/known-workers.local.yaml`. The overlay passes the same validator, can never set `verified`, and may be offered upstream as a candidate change to the shipped data.
