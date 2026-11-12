---
id: "0134"
title: "fit-check takes optional project context as text; it never reads the project"
status: accepted
date: 2026-11-12
source: "owner, 2026-11-12 (chose option B)"
sections: ["§5.7", "§11.1"]
---

# 0134. fit-check takes optional project context as text; it never reads the project

## Context

Adopting an existing project needs a recipe, and `adopt` requires one up front (§11.1). fit-check already picks an existing recipe or returns `recipe: null` (§5.7), but sees only the owner's idea. Options considered: leave it alone (the Director paraphrases evidence into `idea`), add an optional text input, or let the worker read the project. Reading the project would break fit-check's "minutes, no coding assistant" design and duplicate adoption research.

## Decision

fit-check version 4 adds one optional run input, `context`: a short project summary written by the Director. The worker reads no files. The rubric, verdicts, human gate and worker requirements are unchanged, and there is no new verdict. A `fits` verdict with a recipe means adopt under it; with `recipe: null` it means run `recipe-builder`, given the same context; the other verdicts mean stop. Which outputs already exist stays with adoption research, after a recipe is chosen.
