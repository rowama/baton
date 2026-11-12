---
id: recipes.fit-check
title: Fit check
audience: owner
order: 10
summary: Find out in a few minutes whether an idea suits Baton, before you invest in it.
related: [user.start-with-a-goal, recipes.software-feature]
---

## Here, now {#here-now}

Use **fit check** when you are not sure Baton is the right tool for an idea. It asks a few things about the idea, scores it against a simple rule of thumb, and tells you whether it fits, and what to do next. It takes minutes, and it is already in every project that has run `baton init`.

To use it, tell your assistant the idea: "Is this a good fit for Baton: ...". You will be asked one thing at the end: whether you agree with the verdict.

## What you will be asked {#what-you-are-asked}

- At the start: the idea, in your own words, and a short title.
- At the end: **That verdict sounds right** or **I don't think that's right**. If it is not right, say why and it is redone.

It works out what it can from your description and says what it assumed, so you confirm rather than answer a list of questions.

## What it produces {#what-it-produces}

A short profile of the idea, a verdict with its reasons, and a suggested next step. Nothing is written into your project's documents.

## How it decides {#how-it-decides}

It weighs how often the work happens, how much judgment it needs, how long each occurrence takes, and whether a written record in the project is a benefit.

| The work looks like | It fits |
|---|---|
| A few occurrences, at most daily; judgment-heavy, with several kinds of helpers and people signing off; minutes to days each; a record is a benefit | **Baton** |
| Very many occurrences (per order, ticket, event); mostly automated and predictable; seconds each, speed matters; needs live systems and uptime | **A system built to run all day**, not Baton |

The verdict is one of three:

- **fits**: run it with a process that already exists, or have one made for it.
- **fits per occurrence**: each occurrence fits, but they recur. Use a process, with something else to start one each time.
- **operations engine**: the idea is a system to build, not a process to run. Start a software feature whose result is that system.

## What it needs {#what-it-needs}

Any two ordinary helpers: one to write up the profile, one to score it. No coding assistant, no web access.

## The parts {#parts}

%parts%

## Example {#example}

> **Note:** You say: "Is this a good fit for Baton: a way for our volunteers to approve the weekly food-bank order?" The assistant restates the idea, notes it assumed about one order a week and a few people signing off, and the verdict comes back **fits**, with a suggestion to use an existing process. You choose **That verdict sounds right**.

## If it goes wrong {#if-it-goes-wrong}

- No helper is ready: see [no helper is ready](user.when-something-is-wrong#no-helper-ready).
- You disagree with the verdict: choose **I don't think that's right** and say why. It is scored again with your reasons.
