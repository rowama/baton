---
id: user.connect-a-subscription
title: Use a subscription you already have
audience: owner
order: 20
summary: Let Baton use a coding assistant you are already logged in to, such as Claude Code or Codex.
related: [user.connect-an-account, user.choose-models]
---

## Here, now {#here-now}

**Subscriptions on this computer** lists the coding assistants Baton found. Each shows one of three states:

- **connected**: installed and logged in. Nothing to do.
- **not logged in**: installed, but you have not signed in. The card shows the exact command to run. Choose **Copy**, run it in a terminal, sign in, then return to this page; it checks again by itself, or choose **Check again**.
- **not installed**: the card shows the install step for your computer.

Baton does not start a login for you, because signing in is between you and the provider.

## What a subscription is for {#what-for}

A subscription lets Baton hand a step to the assistant on your own plan instead of paying per use through an API key. Its models appear in **Models** marked **subscription**.

> **Note:** Baton keeps the subscription's login separate from any API key, so a key you set elsewhere cannot silently change what a step costs.

## If it still says not ready {#not-ready}

- Open a new terminal after installing, so the command is found.
- Run the assistant once by itself and finish its sign-in.
- Choose **Check again**.
