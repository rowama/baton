---
id: user.check-on-your-work
title: Check on your work
audience: owner
order: 60
summary: See where each piece of work stands and what is waiting for you.
related: [user.long-running-work, user.answer-questions-and-decide]
---

## Here, now {#here-now}

Ask your assistant "where are we?" Its answer comes from Baton's record of the work, not from memory, so it is accurate. If the record does not say, the assistant says so.

To look yourself, in the project's folder:

```baton
baton board
```

It lists every piece of work that is not finished: where it stands, what is running, what is waiting for you, and who is working on it now. `No active runs.` means nothing is in progress.

## One piece of work {#one-piece}

```baton
baton status <run>
baton summary <run>
```

`status` shows where one piece of work is, what is ready, what is running and what is waiting for you. `summary` shows the finished work in order. Both need the piece of work named (your assistant knows it; `baton board` lists them).

## What "waiting on you" means {#waiting-on-you}

A piece of work waits on you when it reached a point that is yours to decide or answer. Nothing else moves it forward. See [answering questions and deciding](user.answer-questions-and-decide#here-now).

## The record of what happened {#the-record}

For each piece of work, Baton keeps a readable record in the project: what each part did, what was checked and by what, and who decided what. Ask your assistant to explain how something came about; it reads the record to answer.
