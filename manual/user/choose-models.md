---
id: user.choose-models
title: Choose which models Baton may use
audience: owner
order: 30
summary: Filter the models table, turn models off, prefer cheaper or more proven ones, and check that one works.
related: [user.connect-an-account, user.connect-a-subscription]
---

## Here, now {#here-now}

**Models** lists every model Baton can use through the accounts and subscriptions you connected. Use the filters above the table to narrow it: **free only**, a **maximum price**, a **capability**, a **tier** or a **provider**.

- The **Use** box at the start of a row turns that model on or off for Baton's choices. Unticked means Baton will not pick it. Tick **turned off** in the filters to list the ones you switched off.
- **Check it works** makes one real, small request to that model and records the result.
- **cheapest first** makes Baton pick the lowest-priced capable model; without it Baton picks the most proven one first.

## Reading the table {#reading-the-table}

| Column | Meaning |
|---|---|
| Model | The provider's name for it, and Baton's short name for it underneath |
| Provider | Which provider, or subscription, reaches it |
| Price | What the provider lists, per million tokens in and out (a token is roughly a short word). **free** and **subscription** are shown as such. **unknown** means the provider did not say |
| Context | How much text it can take at once |
| Tier | How capable Baton believes it to be: a rough guide, not a promise |
| Capabilities | What it can do, each marked **likely**, **verified** or **absent** |
| Checked | When a real request last confirmed it works, or **not yet** |

## Likely, verified, absent {#likely-verified-absent}

A capability starts as **likely**: it should be there, and Baton uses it. When real work shows it, it becomes **verified**. If it fails to work, it becomes **absent** and Baton stops choosing that model for steps that need it. You never have to set these by hand; **Check it works** is only a way to confirm one early.

## Prefer a model for one kind of work {#prefer-a-model}

Above the table, **Prefer a model for…** lets you pick a capability, pick a model and choose **Save**. Baton tries that model first for steps that need that capability, and falls back to others if it cannot be used. These choices are kept for this computer.
