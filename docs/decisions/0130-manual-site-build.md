---
id: "0130"
title: "A static site is built from the same files; hosting is the owner's separate step"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§13.9", "§4.1"]
---

# 0130. A static site is built from the same files; hosting is the owner's separate step

## Context

Open question 4. The owner (2026-11-11) concurred with the suggestion.

## Decision

- `tools/build_site.py` (maintainers only, never shipped) builds a static site from `manual/` with the same URLs and anchors, one copy per released minor version. Choosing a host and publishing are outside the change.
