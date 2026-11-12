---
id: "0129"
title: "`baton ui` serves the whole manual, not only the context panel"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§13.9", "§13.9"]
---

# 0129. `baton ui` serves the whole manual, not only the context panel

## Context

Open question 4 concerned the web site. The owner (2026-11-11) added: `baton ui` should serve the manual fully. This extends the scope set in [0122](0122-ui-scope-and-packaging.md) (providers, models and preferences) with a read-only manual.

## Decision

- `baton ui` has two parts: Setup and Manual. The Manual is a full reader (navigation by part and topic, search, an on-this-page outline, previous and next, links by anchor) over every topic in the shipped manual, working offline. The context panel on Setup opens the same topics in the same renderer.
- Read-only and stateless: the routes only read shipped files; the safety checks of §13.9 apply unchanged. `baton help <topic> --open` opens that topic in the reader.
- 0122's "project, run and recipe views are later work" is unchanged: the manual reader is documentation, not a view of project state.
