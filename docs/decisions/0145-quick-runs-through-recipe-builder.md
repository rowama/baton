---
id: "0145"
title: "Recipe builder offers a quick guided run as an alternative to a full recipe"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: Concur with section recommendations for A, B, C, E1-4 (no new concept at E5). Write A and C change proposals."
sections: ["§5.7"]
---

# 0145. Recipe builder offers a quick guided run as an alternative to a full recipe

## Context

Not every component of a project deserves a rigorous process. The owner wants to choose, per component, between a full Baton recipe and a quick, inference-driven run that produces something good enough. Framing only lists components and fit-check does not apply; the choice belongs in recipe builder, early. The exploration is `docs/catchall/project-process-linkage.md` (§5 E).

## Decision

1. In recipe builder's `profile` step, after existing recipes are checked, the builder offers "a full process" or "a quick guided run", with what each costs and gives. Choosing quick ends the builder with a guidance document instead of a recipe.
2. A guidance document is harness-neutral Markdown (purpose, what to produce, a checklist of what good looks like, what to ask the owner), never a harness-specific skill.
3. A catalog of guidance documents ships beside the recipe catalog and is listed to recipe builder the same way; the builder uses one that fits or writes one.
4. A shipped one-step recipe dispatches a guidance document to a worker, so the output is an accepted deliverable with provenance and needs no attestation. Work done entirely outside Baton still enters through attestation (Decision 0142).
5. No new concept: a guidance document is a recipe input, and the quick run is a recipe.

To be designed in its own change (`2026-11-quick-runs`), after 2026-11-project-documents.
