---
id: "0084"
title: "Capabilities carry a state, likely, verified or absent, kept machine-wide outside profiles"
status: accepted
date: 2026-11-08
source: "change 2026-11-capability-confidence (owner, 2026-11-08)"
sections: ["§6.1", "§8.4"]
---

# 0084. Capabilities carry a state, likely, verified or absent, kept machine-wide outside profiles

## Context

A profile's capabilities were a flat list taken as true. Research may list a capability only with documented evidence, and owners should not have to edit YAML, so capabilities that matter to routing (`web_access`, `structured_output`) were missing from generated profiles even where they work. A capability that should be there ought to be usable, and the work itself should check it.

## Decision

- Each capability a profile claims has a state: `likely` (from data or a declaration, not yet observed), `verified` (observed working, with date and evidence) or `absent` (observed failing, or declared absent by the owner). A claimed capability with no recorded state is `likely`.
- States are kept machine-wide in `~/.baton/capability-states.yaml`, keyed by profile name, never in a profile file, so recording one never changes a profile's content hash (0079) or its `worker_profile_sha256`.
- A state qualifies only a capability the profile claims; it never adds one.
- Routing treats `likely` and `verified` as eligible and `absent` as not eligible. Preferences still come first; among the rest, a profile with more of the step's required capabilities `verified` comes before one with fewer, then by name.
- A `verified` state does not expire. It stands until a failure is observed, or until the harness's version changes, when it goes back to `likely` (Open question 2, owner, 2026-11-08).
- The owner sees the states in `baton workers status`, and resets one to `likely` or declares it `absent` with `baton workers declare --profile <name> --likely|--absent <capability>` (an engine call and an MCP tool). The Director changes states only that way, on the owner's instruction.
