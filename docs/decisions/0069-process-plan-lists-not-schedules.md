---
id: "0069"
title: "Framing's breakdown is a process plan: it lists process starts, never orders or schedules them"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§11.6", "§1.3", "§10.4"]
---

# 0069. Framing's breakdown is a process plan: it lists process starts, never orders or schedules them

## Context

The owner first described framing's breakdown (0064) as a mechanism for sequencing and scheduling process starts. Ordering starts, or starting one after another automatically, would make Baton a scheduler, which §1.3 rules out.

## Decision

- The breakdown is a **process plan**, not a project plan: for each part of the goal it shows which process choosing it starts (a fit check or a recipe), whether it has started and as which run, and what is still waiting. It holds no project content; the work's own plans live in the deliverables each started process publishes.
- It lists; it never orders or schedules. When a part starts is the owner's choice, through the Director. Ordering would be a separate change that revisits §1.3.
- It is published to `paths.process_plans` (default `docs`), one file per framing run: `<goal-slug>-process-plan.md`. The notes file is `paths.notes` (default `docs`), `notes.md`. Both keys fall back to these defaults when `project.yaml` does not map them, and `init` writes them.
