---
id: "0041"
title: "Crosswalk format baton-crosswalk/1"
status: accepted
date: 2026-11-02
source: "inline note, §11.3"
sections: ["§11.3"]
---

# 0041. Crosswalk format baton-crosswalk/1

## Context

Projects run under a known prior process need a declared mapping so research confirms matches instead of interpreting.

## Decision

`baton-crosswalk/1` maps globs (with captures) to qualified step ids and an artifact, output or gate, with `work_item` and `item` templates. It lives in a recipe's `crosswalks/` or anywhere in the project; unknown targets are errors.
