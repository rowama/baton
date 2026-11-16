---
id: "0155"
title: "Recipe builder builds software within a budget: one recipe, an owner-set ceiling, software preferred to an AI worker, 0149 narrowed"
status: accepted
date: 2026-11-15
source: "Owner, 2026-11-15: \"We'll stay with one recipe.\"; \"I like your proposal for the scoping rule.\"; \"I want the user to realize they're settling for less when choosing to go with an AI worker instead.\"; \"Decision 0149 should only apply to intentional software projects\"."
sections: ["§5.7", "§15.3"]
---

# 0155. Recipe builder builds software within a budget: one recipe, an owner-set ceiling, software preferred to an AI worker, 0149 narrowed

## Context

Decision [0154](0154-tool-steps.md) lets a step be run by a tool. The owner wants `recipe-builder` to be a process engineer that also builds the software its process needs, when necessary: more than one-shot code, with a test and verification loop, for possibly many steps, while recognizing that it cannot do large-scale software engineering. The owner sees recipe building as owner-intensive and mostly a digital agency's tool for business customers. A separate `process-engineering` recipe for the engineered case was considered.

## Decision

1. **One recipe.** `recipe-builder` stays one recipe; there is no separate process-engineering recipe. Most of its work is shared by every audience, and whether a step needs engineered software is often found only at design, mid-run.
2. **A ceiling the owner sets at the start** says how much software the builder may build: none (AI workers and people only), simple (one-shot scripts and adapting everyday software), or engineered (tests from the owner's examples and a bounded build loop). Within the ceiling the owner chooses per step at design. The steps of the build loop exist only at the highest setting. How the builder's present size scale becomes ratings is settled in the change that builds this.
3. **Software is preferred to an AI worker.** Where a step could be done by software, the builder proposes software first. An owner who chooses an AI worker for such a step is told plainly what they give up (the same result every time, no cost per run, no dependence on a harness) and what the software would cost them (building it, and the attention a software project needs). The choice is the owner's and is recorded with their words.
4. **A tool budget bounds what the builder builds.** A tool has one entry command with inputs in and outputs out, keeps no service running, holds no state beyond what it declares, fits one effort band, and can be tested from fixture examples. The audit checks it. Anything over the budget is a separate software project.
5. **Examples come from the owner.** The tests of an engineered tool are written from examples and expected results the owner supplies, before the code and by a different worker, and are then protected. Passing tests the builder invented proves nothing about the owner's intent.
6. **Decision [0149](0149-one-software-recipe.md) is narrowed** (amending it): eng-process is the one recipe for intentional software projects, whose result has no specific connection to Baton, as software written in an IDE has none to the IDE. Software built as part of a recipe, within the budget, is outside 0149. Over-budget software goes to eng-process.
7. **The work is three changes after `2026-11-tool-steps`**, not yet written: the builder characterizes each step and chooses its executor; the builder writes and verifies tools; and a more capable way for a person to answer a step, deferred ([2026-11-person-step-forms](../changes/2026-11-person-step-forms.md), on hold).
