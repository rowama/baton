---
id: "0157"
title: "Project review: it reads the policy and governing recipes, proposes recipes or fit checks only, and starts as an ordinary run"
status: accepted
date: 2026-11-15
source: "Owner, 2026-11-15: \"All approved.\" (the Request and Design of 2026-11-project-review, with refinements A to C as suggested)"
sections: ["§5.2", "§5.7", "§11.6", "§13.1", "§13.3"]
---

# 0157. Project review: it reads the policy and governing recipes, proposes recipes or fit checks only, and starts as an ordinary run

## Context

Checking the Design of `2026-11-project-review` against the code before approval: project policy (`2026-11-project-policy`) is done, so the review need not work around its absence; quick runs (`2026-11-quick-runs`) are deferred, so a review cannot propose one; and the Design did not say how a review is started.

## Decision

1. **The review reads the policy.** `project.summary` always carries the project policy (none recorded is stated as such), and the review step receives the recipe listing (`catalog`) with the policy's governing recipes marked, as framing's does.
2. **A proposal is a recipe or a fit check only.** The proposal format leaves room for a quick run, added by `2026-11-quick-runs` if it is accepted.
3. **No new command.** The Director starts a review as an ordinary run of `project-review` (`baton start`). The owner's yes to the Director's offer is the confirmation to vendor the catalog recipe on first use, recorded with the owner's words.
