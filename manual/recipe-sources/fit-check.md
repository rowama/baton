---
id: recipes.fit-check
title: Fit check
audience: owner
order: 10
summary: Find out in a few minutes whether the work you want done suits Baton, before you invest in it.
related: [user.start-with-a-goal, recipes.software-feature]
---

## Here, now {#here-now}

Use **fit check** when you are not sure Baton is the right tool for what you want done. It works out what you are asking for, scores that work against a simple rule of thumb, and tells you whether it fits, and what to do next. It takes minutes, and it is already in every project that has run `baton init`.

To use it, tell your assistant the idea: "Is this a good fit for Baton: ...". You will be asked one thing at the end: whether you agree with the verdict.

## What you will be asked {#what-you-are-asked}

- At the start: the idea, in your own words, and a short title. For an idea about a project that already exists, your assistant also gives a short summary of what is already there, so the suggested process fits it. It reads nothing in your project itself.
- At the end: **That verdict sounds right** or **I don't think that's right**. If it is not right, say why and it is redone.

It works out what it can from your description and says what it assumed, so you confirm rather than answer a list of questions.

## What it produces {#what-it-produces}

A short profile of the work, a verdict that says which work it assessed, its reasons, and a suggested next step. Nothing is written into your project's documents.

## How it decides {#how-it-decides}

First it works out **what you are asking for**: making, testing or improving a process (a workflow in a tool such as n8n, Temporal or LangGraph, a BPMN or CMMN diagram, or a set of procedures, templates and software), running a process for real, or something else. If your request is clear, you are not asked. If it holds both, such as building a process and also running it, it asks which parts you want and looks at each separately; it never picks for you.

Making a process is work Baton can coordinate however the finished process will run. How busy the finished process will be, how fast, or where it runs is not held against the project that makes it. The work is judged on its own facts: how many helpers and people it involves, how much later work depends on earlier thinking, how long it takes, whether a written record helps, and whether it recurs.

| The work looks like | It fits |
|---|---|
| Several helpers or people, handoffs and sign-offs, later steps that depend on earlier thinking, minutes to days of effort, a record that helps | **Baton** |
| One short step, nothing to pass on, or work so frequent and small, or so speed- and uptime-bound, that running Baton each time costs more than it returns | **Something simpler**, not Baton |

The verdict is one of three:

- **fits**: run it with a process that already exists and covers all of it, or have one made for it. Having no ready-made process is not a reason against.
- **fits per occurrence**: each occurrence is worth its own run, but they recur. Use a process, with something else to start one each time. Adding a timer does not make unsuitable work fit.
- **not recommended**: Baton would cost more than it returns. It suggests what suits the work better: a script, asking an assistant directly, a tool you already have, a written procedure, or a system built to run all day. If you asked for work to be run and it does not fit, it may offer making a suitable process or system as a **separate** project. Agreeing with the verdict does not start that project; you are asked whether you want it.

Its reasons say whether each point rests on something you told it or on something it assumed.

## What it needs {#what-it-needs}

Any two ordinary helpers: one to write up the profile, one to score it. No coding assistant, no web access.

## The parts {#parts}

%parts%

## Example {#example}

> **Note:** You say: "Is this a good fit for Baton: a way for our volunteers to approve the weekly food-bank order?" The assistant restates the idea, notes it assumed about one order a week and a few people signing off, and the verdict comes back **fits**, with a suggestion to use an existing process. You choose **That verdict sounds right**.

> **Note:** You say: "Is this a good fit for Baton: an n8n workflow that handles our 2,000 daily refund requests?" The assistant sees that you want the workflow designed, built and tested, not the refunds processed by Baton, so it judges that effort. It does not hold the 2,000 daily requests against you, and the verdict can come back **fits**. Had you asked Baton to process each refund itself, the verdict would be **not recommended**, with an offer to build the workflow as a separate project you can choose.

## If it goes wrong {#if-it-goes-wrong}

- No helper is ready: see [no helper is ready](user.when-something-is-wrong#no-helper-ready).
- You disagree with the verdict: choose **I don't think that's right** and say why. It is scored again with your reasons.
