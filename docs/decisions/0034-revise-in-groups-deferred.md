---
id: "0034"
title: "revise inside groups is deferred"
status: accepted
date: 2026-11-02
source: "inline note, §8.9"
sections: ["§8.9"]
---

# 0034. revise inside groups is deferred

## Context

`revise` was built for top-level steps; in-group revision interacts with instances and iterations.

## Decision

Revising a step inside a group is refused. In-group work is corrected by revising the group's source (which re-expands it) or through the iteration loop.
