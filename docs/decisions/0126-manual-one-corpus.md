---
id: "0126"
title: "One manual, written once, read three ways, lives in a top-level `manual/`"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§13.9", "§4.1"]
---

# 0126. One manual, written once, read three ways, lives in a top-level `manual/`

## Context

Open question 1 (and the shape in Design): where the documentation lives and whether the three layers the owner asked for (context, user, admin) are three documents or one.

## Decision

- One corpus, `manual/`, separate from `docs/` (the builders' design record) and shipped as data (`baton/_data/manual`) like `ui/` and `defaults/`. Context help, the user guide and the admin guide are three views of it, not three documents.
- Topics carry permanent ids and every heading an explicit stable anchor; a published anchor never stops resolving (a rename leaves an alias).
