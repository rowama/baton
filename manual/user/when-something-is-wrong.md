---
id: user.when-something-is-wrong
title: When something is wrong
audience: owner
order: 100
summary: What the common messages mean and what to do about each.
related: [user.connect-an-account, user.long-running-work]
---

## Here, now {#here-now}

Run the health check:

```baton
baton doctor
```

It prints a single line when everything is healthy. Otherwise it lists each **PROBLEM** (nothing will work until it is fixed) and **WARNING** (it will work, but you should know), with the fix. The common ones are below.

## No helper on this computer is ready {#no-helper-ready}

> **Note:** `no worker on this machine is ready yet: set them up with baton workers setup`

Baton has no helper it can give work to. Connect a subscription or an account: see [getting started](user.getting-started#connect). Or ask your assistant to walk you through it.

## A key is refused {#key-refused}

See [what a refusal means](user.connect-an-account#key-refused).

## Your assistant is sandboxed {#sandboxed}

Some assistants (Codex, in its default mode) run commands in a sandbox that stops Baton reaching its files or the internet. Baton notices and stops before anything half-works. The best fix is to connect Baton to the assistant as a tool, so it runs outside the sandbox:

```sh
codex mcp add baton -- baton mcp
```

Then add one line under the `[mcp_servers.baton]` section the command wrote, in `~/.codex/config.toml`:

```toml
default_tools_approval_mode = "approve"
```

and restart Codex. The other choices are to approve each Baton command when asked (frequent prompts) or to turn the sandbox off (which lets it change anything on your computer).

## Another assistant has the work {#another-assistant}

Only one assistant changes a piece of work at a time. If another holds it, you are told who and until when. Taking it over needs your approval. See [long-running work](user.long-running-work#one-at-a-time).

## No notice when work finishes {#no-wake}

> **Note:** `no completion hook would wake a Director when work needs the owner`

Your assistant may end its turn while work runs, and nothing would bring it back. It will tell you this before starting work. It is a warning, not a failure: stay in the conversation, or come back and ask where things stand. To set up an automatic wake-up, see the admin guide.

## A problem in Baton, not in your work {#baton-problem}

Sometimes the work stops because of something in Baton itself: a process's instructions that contradict each other, or an answer you gave that didn't reach the next step. Your assistant tells you in one line ("This looks like a Baton problem, not yours. I've written it up. I can hold this, or try something else. Which?"). Either choice is fine. Holding keeps everything as it is until a fix arrives; the other way round is something Baton already offers, such as giving the step to a different helper.

The write-up stays on your computer, in `.baton/reports/`, with the evidence and your secrets taken out. Nothing is sent anywhere.

## Still stuck {#still-stuck}

Ask your assistant: it can read Baton's record of what happened. Or search the manual: [using the manual](user.using-the-manual#here-now).
