---
id: user.start-with-a-goal
title: Start with a goal
audience: owner
order: 40
summary: Tell your assistant what you want to achieve and choose which pieces to start on.
related: [user.answer-questions-and-decide, user.bring-an-existing-project]
---

## Here, now {#here-now}

When what you have is a goal rather than a task, say it in your own words: "I want to start a pure-water vending business." Your assistant offers to break it into pieces of work. You will see the pieces and choose which to start on now. The rest stay in a plan for later.

## What happens {#what-happens}

1. Your assistant confirms the goal with you, in your words.
2. A helper breaks the goal into pieces of work. For each piece it suggests a process to follow (one of the processes that ship with Baton, or a quick check of whether the idea suits Baton at all).
3. You choose which pieces to include. Choosing **That's not quite it** has the breakdown redone with what you said.
4. Each chosen piece begins. The pieces you left out remain in your plan.

A piece that cannot start yet, because its details do not fit the process or it would write to a place the project has not set up, is reported to you as a gap. It is never started anyway.

## What you keep {#what-you-keep}

The breakdown is kept in the project as a plan you can read, in the folder your project's settings name for plans. It is a document like any other: edit it, commit it, share it.

## From the command line {#command-line}

Your assistant does this for you. If you want to do it yourself:

```baton
baton frame --note "I want to start a pure-water vending business"
```
