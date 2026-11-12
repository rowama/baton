---
id: user.choose-models
title: Choose which models Baton may use
audience: owner
summary: Filter the models table, turn models off, prefer cheaper or more proven ones, and check that one works.
related: [user.connect-an-account, user.connect-a-subscription]
---

## Here, now {#here-now}

**Models** lists every model Baton can use through the accounts and subscriptions you connected. Use the filters above the table to narrow it: **free only**, a **maximum price**, a **capability**, a **tier** or a **provider**.

- The switch at the start of a row turns that model **on or off** for Baton's choices. Off means Baton will not pick it.
- **Check it works** makes one real, small request to that model and records the result.
- **cheapest first** makes Baton pick the lowest-priced capable model; without it Baton picks the most proven one first.

## Reading the table {#reading-the-table}

| Column | Meaning |
|---|---|
| Model | The provider's name for it, and which of your accounts reaches it |
| Price | What the provider lists, per million words in and out. **free** and **subscription** are shown as such. **unknown** means the provider did not say |
| Tier | How capable Baton believes it to be: a rough guide, not a promise |
| Abilities | What it can do, each marked **likely**, **verified** or **absent** |
| Last checked | When a real request last confirmed it works, or **not yet** |

## Likely, verified, absent {#likely-verified-absent}

An ability starts as **likely**: it should be there, and Baton uses it. When real work shows it, it becomes **verified**. If it fails to work, it becomes **absent** and Baton stops choosing that model for steps that need it. You never have to set these by hand; **Check it works** is only a way to confirm one early.

## Prefer a model for one kind of work {#prefer-a-model}

Under the filters you can name a preferred model for a particular ability. Baton tries it first for steps that need that ability, and falls back to others if it cannot be used. These choices are kept for this computer.
