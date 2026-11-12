---
id: recipes.baton-adopt
title: Bring in an existing project (the built-in reader)
audience: owner
order: 50
summary: The part of Baton that reads an existing project to find out what is already done.
related:
- user.bring-an-existing-project
generated: true
---

## Here, now {#here-now}

This is the built-in process behind [bringing in an existing project](user.bring-an-existing-project#here-now). You do not choose or start it yourself: ask your assistant to bring the project in, and it runs. A helper reads the project, read-only, and works out which of a process's results already exist, where, and in what state. You are then asked one question.

## What you will be asked {#what-you-are-asked}

Nothing during the reading. Afterwards, once, whether the summary of your existing work is accurate: **That's an accurate picture**. If it is not, say what is wrong.

## What it produces {#what-it-produces}

A proposed starting point, written into your project's `.baton` folder: how it is set up, the size of each piece of work in progress, the work counted as already done and anything proposed to be set aside. It takes effect only when you accept it.

## What it needs {#what-it-needs}

One helper that can read your project's files. It changes none of them.

## The parts {#parts}

| Part | When | You are asked |
|---|---|---|
| Research the existing project | always | nothing |

## If it goes wrong {#if-it-goes-wrong}

- **It missed something that exists:** say so when you are asked about the summary. You can limit the reading to one folder if the project is large.
- No helper is ready: see [no helper is ready](user.when-something-is-wrong#no-helper-ready).
