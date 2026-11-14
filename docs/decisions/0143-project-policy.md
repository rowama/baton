---
id: "0143"
title: "A small project policy in project.yaml is enforced on every run"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: Concur with section recommendations for A, B, C, E1-4 (no new concept at E5). Write A and C change proposals."
sections: ["§2", "§5.5", "§13.7"]
---

# 0143. A small project policy in project.yaml is enforced on every run

## Context

Some project-level decisions should constrain every run, not just inform it: how much assurance software work needs, who may push or deploy, which recipe governs a kind of work. The exploration is `docs/catchall/project-process-linkage.md` (§5 B).

## Decision

1. Three policies to start: floors on tailoring axes (per recipe or for all), release authority (who may push, merge or deploy; default ask), and the governing recipe for a kind of work. More only from real need.
2. Policy lives in a `policy:` block in `project.yaml` and changes only through a recorded owner decision.
3. Policy is pinned at run start, like the recipe version. A run started under older policy is reported; the owner may re-triage it.
4. The governing recipe is advisory: the Director proposes it and says so when the owner picks another; the runtime does not refuse. Axis floors and release authority are enforced.
5. *Project policy* is one new concept in §2.

To be designed in its own change (`2026-11-project-policy`), after 2026-11-project-documents and 2026-11-tailoring-axes.
