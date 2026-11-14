---
id: "0152"
title: "Project review: framing's selection generalized, a catalog recipe, metadata-only summary, bindings in proposals"
status: accepted
date: 2026-11-14
source: "Owner, 2026-11-14: Accept all for B and D."
sections: ["§5.1", "§5.2", "§5.7", "§11.6"]
---

# 0152. Project review: framing's selection generalized, a catalog recipe, metadata-only summary, bindings in proposals

## Context

Writing `2026-11-project-review` from Decision 0150 raised six questions. The suggested answers were put to the owner in one batch.

## Decision

1. **Selection is generalized.** A step may declare `proposes_runs: true`. The runtime then supplies framing's selection gate, starts, gaps, plan rendering and `start --from-plan` for it. Framing is its first user and is unchanged.
2. **The review is a catalog recipe**, `project-review@1`, vendored on first use and specializable with recipe builder.
3. **`project.summary` is metadata only.** Document contents reach a review only through its declared roles.
4. **Framing gains bindings now**, as `baton-frame@2`. Open `@1` runs keep `@1`.
5. **Adoption is not a startable proposal** in this change. A review may say in its reasons that existing work could be adopted, and the Director follows the `adopt` flow (§11.1).
6. **Suggested order** is `position` and `waits_on` (each with a reason) on a proposal. It is shown, never enforced.
