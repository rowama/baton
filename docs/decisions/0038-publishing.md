---
id: "0038"
title: "Publishing: when, where and conflicts"
status: accepted
date: 2026-11-03
source: "inline note, §10.4"
sections: ["§10.4"]
---

# 0038. Publishing: when, where and conflicts

## Context

Artifacts with `publish.to` are written to project paths; the start check, timing and conflict handling were open.

## Decision

An unmapped `paths.*` key refuses `start`. Publishing follows every `step_passed` of a step with publish artifacts, before its checkpoint; imports are never published; `publish` inside a group is a load error. Writing is silent only for an absent target, identical bytes, or this run and step's own untouched file; anything else is a pending owner decision (`overwrite`, `keep`, `alternate`) that keeps the step passed and holds run completion.
