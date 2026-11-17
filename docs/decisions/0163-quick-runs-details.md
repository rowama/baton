---
id: "0163"
title: "Quick runs: the quick rating and the builder's one question, one Markdown result, default paths, a starter set of guides, guides copied by attestation, no workspace"
status: accepted
date: 2026-11-17
source: "Owner, 2026-11-17: \"Agree to all.\" (the suggested answers to the six open questions of 2026-11-quick-runs, with questions 1 and 5 discussed first)."
sections: ["§5.5", "§5.7", "§10.4", "§13.1"]
---

# 0163. Quick runs: the quick rating and the builder's one question, one Markdown result, default paths, a starter set of guides, guides copied by attestation, no workspace

## Context

`2026-11-quick-runs` carries Decision [0145](0145-quick-runs-through-recipe-builder.md) into a design. It raised six open questions. The owner deferred them on 2026-11-14 to discuss questions 1 and 5 first. Decision [0162](0162-builder-step-design-details.md) (item 3) has since settled most of question 1: `quick` is added below `simple` on recipe builder's `approach` axis, with `confirm_lowest`, and the profile schema requires `software: none` with `quick`. What remained was a side effect. Once `quick` is the lowest rating, every set of ratings waits on the owner, so a simple build, which asks one question today (the profile's "Is this what the process should do?") would ask two. Question 5 was put with three options: copy a shipped guide into the project by attestation (suggested), let `quick-run` take a shipped guide's id directly, or offer no path except recipe builder.

## Decision

1. **The builder's quick path, one question.** `recipe-builder@5` rates `approach: [quick, simple, standard, complex]` with `confirm_lowest: true`, and `quick` requires `software: none` (0162). `profile` drops its own human gate. The triage gate, which now always opens, is the profile's one owner question: it confirms what the process should do and the recommended approach, full or quick, together. Rejecting it sends `profile` back with the owner's note, as today. A project with `recipe-builder@4` pinned keeps it.
2. **A quick run produces one Markdown document.** The guide's `produces` names it. Other media come later, if guides need them.
3. **Default paths.** Quick-run results publish to `paths.documents`, which defaults to `docs` when `project.yaml` does not map it, as `paths.process_plans` does (Decision [0069](0069-process-plan-lists-not-schedules.md)). The project's own guides live at `guides/<slug>.md`.
4. **The starter guides:** a lean business plan, a marketing plan, a standard operating procedure, a project charter and a decision record. More are added from real use.
5. **A shipped guide without recipe builder.** `baton guides copy <id> --note "<owner's words>"` copies a shipped guide into the project's `guides/` and records the owner's attestation of the copy, so it is a project document that `quick-run` binds by role. `quick-run` has one way to get its guide: a bound project document. Recipe builder remains the way to choose a guide or write a new one. This adds a command, not a concept (0145 item 5).
6. **No workspace.** The quick run's worker has `workspace: none`. Context reaches it only through the `context` role.
