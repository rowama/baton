---
id: user.getting-started
title: Getting started
audience: owner
order: 2
summary: Install Baton, set up a project, connect your accounts and ask your assistant for what you want.
related: [user.what-is-baton, user.connect-an-account, user.when-something-is-wrong]
---

## Here, now {#here-now}

1. Install Baton (once per computer).
2. Set up your project (once per project).
3. Connect the accounts and subscriptions Baton may use (once per computer).
4. Open your AI assistant in the project and tell it what you want.

Each step is below.

## Install {#install}

Baton needs Python 3.11 or newer, git and [uv](https://docs.astral.sh/uv/). Then, in a terminal:

```sh
uv tool install "baton[mcp,api] @ git+https://github.com/rowama/baton"
baton --version
```

If the second command prints a version, Baton is installed. For installation options and what is put where, see the admin guide: [install, versions and upgrades](admin.install-and-versions#here-now).

## Set up a project {#set-up-a-project}

In the project's folder:

```baton
baton init
```

This creates a `.baton` folder with the project's settings, copies in the instructions your assistant needs, and adds a starter process. It leaves your existing files alone, except that it creates or extends `AGENTS.md` (the file assistants read) and `.gitignore`. Commit what it added so the project carries it.

At the end it may tell you that this computer's helpers are not set up yet. That is the next step.

## Connect your accounts and subscriptions {#connect}

Open the setup page:

```baton
baton ui
```

It lists the coding assistants it found on this computer and gives you a card for each provider you can connect with an API key. Work through [connecting a subscription](user.connect-a-subscription#here-now) and [connecting an account](user.connect-an-account#here-now). You can also ask your assistant to walk you through it; it will give you the link, and it never takes a key in conversation.

## Ask for what you want {#ask}

Open your assistant in the project and describe what you want, in your own words: "I want to start a pure-water vending business", or "add sign-in to the app". The assistant will either propose how to break a bigger goal into pieces for you to choose from ([starting with a goal](user.start-with-a-goal#here-now)) or begin a piece of work directly. If the project already exists and has its own history, start with [bringing in an existing project](user.bring-an-existing-project#here-now).

## Check that all is well {#check}

```baton
baton doctor
```

It prints one line when everything is healthy, and says what is wrong, and how to fix it, when not. See [when something is wrong](user.when-something-is-wrong#here-now).
