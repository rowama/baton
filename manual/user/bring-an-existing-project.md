---
id: user.bring-an-existing-project
title: Bring in an existing project
audience: owner
order: 45
summary: Let Baton read what already exists in a project and agree, in one decision, where things stand.
related: [user.start-with-a-goal, user.answer-questions-and-decide]
---

## Here, now {#here-now}

If your project already has work in it, ask your assistant to bring it into Baton. A helper reads the project, read-only, and works out which of a process's outputs already exist and in what state. You are then asked **one** question: is the summary an accurate picture? When you say yes, the project's existing work is the starting point, and Baton carries on from there.

## What you decide {#what-you-decide}

You are shown a baseline: how the project is set up, the size of each piece of work in progress, the work counted as already done, and anything proposed to be set aside. If it is accurate, choose **That's an accurate picture**. If something is wrong, say what, and it is redone.

Reading changes none of your files. Baton records what it found under `.baton`, and the baseline takes effect only when you say it is accurate.

## From the command line {#command-line}

```baton
baton adopt fit-check
baton establish-baseline --help
```

Replace `fit-check` with the process you want to follow. `--scope docs/` limits the reading to one folder.
