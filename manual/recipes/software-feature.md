---
id: recipes.software-feature
title: Software feature
audience: owner
order: 20
summary: Take a feature, fix or change from a request to accepted, tested work, in slices you approve.
related:
- recipes.fit-check
- user.answer-questions-and-decide
generated: true
---

## Here, now {#here-now}

Use **software feature** to take a change to code from a request to finished, tested work. Tell your assistant what you want: "Let users sign in and out." Baton sizes the change, writes down what it will do, plans it as slices, builds and reviews each slice, and asks you to accept each one before the next.

A small change gets a light process; a large one gets more. You never choose the size: it is worked out and you confirm it.

## What you will be asked {#what-you-are-asked}

The request itself: a short title, whether it is a feature or a fix, and what you want, in your own words. Above **minor**, you also confirm the size it chose. Then, depending on the size:

| Size | What the process adds | You are asked |
|---|---|---|
| **minor** (a fix, a small increment, a copy or settings change) | One build and an independent review | To accept it |
| **standard** (several files or modules, worth splitting into slices) | Written requirements, and a reviewed plan | To approve the plan and its slices, then to accept each slice |
| **major** (a new subsystem, a public interface or stored format others depend on, a migration, security- or money-sensitive, hard to undo) | Requirements you approve, then a technical design, then the plan | To approve the requirements, the plan and its slices, then to accept each slice |

If you accept a slice, the work moves on. If you do not, say what to change: it goes back to be built again with your note.

## What it produces {#what-it-produces}

- **Requirements** and, for a major change, a **design**, written to the folders your project's settings name for them (`paths:` with `specs` and `designs`, in `.baton/project.yaml`). Set them before starting a standard or major change: a piece of work that would write somewhere the project has not set up is reported as a gap, not started.
- **The change itself**, built a slice at a time, with the project's own tests run on each slice (`project: test_command`, in the same file).
- **A record** of what each part did and who approved what.

## What it needs {#what-it-needs}

- Helpers that can write and reason well, and, for building, a **coding assistant** that can edit files and run commands in your project (Claude Code or Codex, on your subscription, or a model through an account with the right tools).
- Plans are reviewed by a **different company's** model than the one that wrote them, so a helper does not mark its own work. That needs models from at least two makers; with only one, nobody is eligible to review and you are asked how to proceed.
- Your project's test command, so each slice is checked.

## The parts {#parts}

| Part | When | You are asked |
|---|---|---|
| Assess complexity | always | Is the size right? (at standard, major) |
| Clarify requirements | at standard, major | Approve requirements before design? |
| Technical design | at major | nothing |
| Plan vertical slices | at standard, major | Approve the plan and its slices? |
| Deliver each slice | always | nothing |
| ↳ Build the slice | always | nothing |
| ↳ Independent code review | always | nothing |
| ↳ You accept the slice | always | Accept this slice as done? Rejecting sends it back to implement with your note. |

The size of the work is **minor**, **standard**, **major**. The first part works out which one fits, and you confirm it above the smallest.

## Example {#example}

> **Note:** You say: "Let users sign in and out." It is sized **standard**. You are shown the requirements it wrote and the plan: three slices (sign-in, sign-out, session timeout). You approve the plan. For each slice you see what was built and what the tests and the review found, and choose **Looks right** or say what to change.

## If it goes wrong {#if-it-goes-wrong}

- **A slice keeps failing its checks:** it is tried again up to three rounds, then you are asked whether to give it another round or stop.
- **The size is wrong:** say so when you are asked to confirm it, and it is sized again.
- **The plan is too big or too small:** do not approve it; say what to change.
- Questions you do not understand: see [if a question confuses you](user.answer-questions-and-decide#confusing).
