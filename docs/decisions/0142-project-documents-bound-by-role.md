---
id: "0142"
title: "Runs bind accepted or attested project documents as inputs, by role"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: Concur with section recommendations for A, B, C, E1-4 (no new concept at E5). Write A and C change proposals."
sections: ["§2", "§5.2", "§8.6", "§10.4", "§10.5"]
---

# 0142. Runs bind accepted or attested project documents as inputs, by role

## Context

Baton guarantees reliable handoff only inside a run. A step's declared inputs come from its own run, recorded human decisions, platform facts or the catalog (§5.2). A later process (marketing, say) cannot declare that it needs what an earlier process (business setup) settled, receive the accepted version, be stopped when it is missing, or record which version it used. The exploration is `docs/catchall/project-process-linkage.md` (§5 A).

## Decision

1. A **project document** is an accepted, published deliverable of any run (automatically) or a file in the repo the owner attests (an owner decision recording their words and the file's hash).
2. A recipe declares the project documents it would like in a recipe-level `project_inputs` list (`role`, `description`, `media_type`, `required`), referenced in step inputs as `project.<role>`. Roles never name another recipe or its steps, so recipes stay shareable. A recipe with no `project_inputs` behaves as today.
3. The Director proposes bindings at run start from the project's documents and the role descriptions and confirms them back with the owner (§13.8); framing and a project review may propose them too. A role may stay unbound until the first step that needs it is dispatched; a required unbound role then refuses that dispatch as a missing required input does, and the Director asks.
4. When a bound document changes upstream, nothing happens automatically: status shows that a newer version exists. The owner may rebind, which within that run makes the consuming steps stale as `revise` does; other runs are never touched.
5. The project's documents are listed by the runtime from run records and attestations, never from a hand-kept index.
6. *Project document* is one new concept in §2; roles and binding are its mechanics.
