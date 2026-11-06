---
id: "0077"
title: "The resource manager is baton workers status, setup and declare"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§13.1", "§13.2", "§2"]
---

# 0077. The resource manager is `baton workers status`, `setup` and `declare`

## Context

The manager is a separate responsibility from `doctor` and must be usable directly as well as through the Director.

## Decision

- `baton workers status`: read-only. What is discovered, declared and generated, each profile's verification state, and whether machine setup is complete.
- `baton workers setup [--verify [<profile>…]]`: the explicit manager run. Discovers, applies declarations, generates and refreshes profiles, and records setup completion.
- `baton workers declare`: adds, changes or removes an owner declaration (a resource discovery cannot find, such as an OpenRouter account), or records that there is nothing more to add.
- Each has an engine call (§13.1) and an MCP tool; the code is part of the installed package. The manager is the only writer of generated profiles; an owner-approved call supplies the instruction the Director needs to change profiles.
- The commands add no concept (§2): a declaration is the owner's input for generating worker profiles.
