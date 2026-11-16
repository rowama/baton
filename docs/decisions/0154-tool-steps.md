---
id: "0154"
title: "A step may be run by a tool: pinned, with declared dependencies, in three forms, built in three changes"
status: accepted
date: 2026-11-15
source: "Owner, 2026-11-15: \"I just want to be able to design a process with more than AI capabilities as the variant.\"; \"Three docs\"; \"wait as state: concur\"."
sections: ["§2", "§5.1", "§6.3", "§8.7"]
---

# 0154. A step may be run by a tool: pinned, with declared dependencies, in three forms, built in three changes

## Context

The owner wants `recipe-builder` to design processes that use AI only where rules or existing software cannot do the work. A recipe can say only what kind of AI worker or person a step needs (`requires`); code runs as a gate, or through a hand-written machine-local `command` profile that a recipe cannot ship, pin or name. The owner does not want every step tied to an agentic harness: formal tool use must be separable from the harness and visible to the recipe designer at the same level as AI capabilities.

## Decision

1. **A tool is a third kind of executor of a step**, beside an AI worker and a person. Baton runs it itself, with the same packet, result, gates and provenance as any step.
2. **Tools are more locked down than AI capabilities.** A recipe names the tool; the Director cannot substitute another. The command is fixed, inputs are typed, what the tool may touch is declared, and a tool enters a project only with the owner's approval.
3. **Three forms**, sharing one model (a requirement stated at design time, a resolution at install time, a record per run):
   - a script built at design time, with its runtime needs;
   - a specific piece of external software that must be available;
   - a specified interface, with the owner pointing to an instance at install time and an adapter between. The design step drafts the specification; the owner approves it.
4. **A tool run is a step** when its output is handed on, when it needs its own check or record, when it must not depend on the harness in use, or when it spends money or changes something outside the project. Otherwise it stays inside a worker.
5. **Waiting is held as state**, like a person's step, with no Baton process kept alive. An optional helper run from a scheduler may check waiting steps and wake the process. Baton never requires it.
6. **Three changes**, in this order: tool steps (design-built scripts, dependencies, checks, records: `2026-11-tool-steps`); external software and binding; waits and the helper. A change to `recipe-builder` (decomposition, traits of each step, choice of executor, audit checks) follows the first.
