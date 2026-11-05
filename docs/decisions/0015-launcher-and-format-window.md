---
id: "0015"
title: "The launcher installs with uv; runtimes read the current and previous format"
status: accepted
date: 2026-11-03
source: "§18 #15"
sections: ["§14.1", "§14.2"]
---

# 0015. The launcher installs with uv; runtimes read the current and previous format

## Context

Launcher installation mechanism and how many older format versions a runtime must read.

Suggested: uv-managed; current and previous.

## Decision

as suggested. The launcher installs a missing version with uv into `~/.baton/versions/<v>/` from a `source` template in `~/.baton/launcher.yaml` (default the runtime's git repo at tag `v<version>`); without uv it refuses with the install hint. A runtime reads the current and previous version of each stored format; older ones are refused naming `baton migrate` (§14.1, §14.2).
