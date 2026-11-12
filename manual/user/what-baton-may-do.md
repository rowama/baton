---
id: user.what-baton-may-do
title: What Baton may do to your repository
audience: owner
order: 90
summary: Which repository actions are allowed, which need your approval and which are never done.
related: [user.answer-questions-and-decide]
---

## Here, now {#here-now}

Baton never pushes, tags, merges or deploys on its own authority. Your project's settings say which of these are **allowed**, which you must **approve** each time, and which are **never** done. A new project starts careful:

| Action | Starts as |
|---|---|
| Push changes that are only documents | allowed |
| Push changes that Baton's own checks vouched for | allowed |
| Push anything else | asks you |
| Tag a release | asks you |
| Force-push, merge or deploy | never |

## What "asks you" looks like {#asks-you}

Your assistant tells you what it wants to do and why, and waits. If you approve, it goes ahead and records your approval in your own words. If you do not, nothing happens. Approval never lifts a "never".

## Changing it {#changing}

The settings are in `.baton/project.yaml`, under `permissions`, in your project. Each is `allow`, `ask` or `deny`. Edit and commit it: the setting travels with the project.

## From the command line {#command-line}

```baton
baton push
baton permission tag --detail "tag v1.2"
```

Pushing is always explicit: nothing pushes automatically.
