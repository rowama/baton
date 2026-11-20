---
id: "0174"
title: "First-use feedback: who does person steps is asked at start and kept in project policy; the owner keeps every decision; a built-in owner profile"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"director needs to ask if the user it's talking to is the one who be doing the human steps with yes/owner being the default\"; \"Concur with your suggested answers.\""
sections: ["§6.1", "§8.4", "§13.3", "§13.7"]
---

# 0174. First-use feedback: who does person steps is asked at start and kept in project policy; the owner keeps every decision; a built-in owner profile

## Context

The owner's first real run (`2026-11-first-use-feedback-batch-a`, items F-2 and F-3) showed that a person's step has no worker unless a person's profile is written by hand, and that the Director should ask who will do the person steps, defaulting to the owner, who started the run (Decision [0161](0161-ai-delegates.md), item 6). Four questions were put to the owner with suggested answers; the owner concurred with each.

## Decision

1. **Asked at start, kept in project policy.** When a recipe has person steps, the Director asks at `start`, once, whether the person it is talking to will do them, with yes as the default. The answer is kept for the project in project policy (`policy.people: {person_steps: owner | <name>}`), so later runs inherit it; the owner can change it at any time with their words.
2. **Another person does steps, not decisions.** A person the owner names does the person steps (work and checks they perform). The run's owner keeps every owner decision: gates, approvals and waivers.
3. **The owner's profile** is `manual`, identity `human/owner`, with `human_judgment`, `long_form_writing`, `vision` and `file_write`, tier `strong`.
4. **Built in.** It is present in memory on every machine, like a program's in-memory profile (§6.3), shown by `workers status`, and replaced by an owner's own profile of the same name. A profile for another person the owner names is created the same way, from the answer, never written by hand.
