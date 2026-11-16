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

## Scripts a process runs {#tools}

Some processes do part of their work with a small program instead of an AI, for example to compare two spreadsheets the same way every time. Your assistant asks you before a process like that is added to your project, and tells you for each program:
- what it does;
- what it needs installed on your computer;
- what it may touch: your project's files, the internet, any passwords or keys.

It runs only after you say yes. If the process later brings a changed program, you are asked again. A program never gets a password or key it did not name, and it cannot change files it was not allowed to change. Whether it uses the internet is shown to you but not checked by Baton.

## What "asks you" looks like {#asks-you}

Your assistant tells you what it wants to do and why, and waits. If you approve, it goes ahead and records your approval in your own words. If you do not, nothing happens. Approval never lifts a "never".

## Changing it {#changing}

These settings are part of your project's rules, which every piece of work follows. Tell your assistant what you want changed, in your own words. It confirms the change with you, then records it with your words, so you can always see who decided what and when. The rules are kept in `.baton/project.yaml`, under `permissions`, and travel with the project.

If someone edits that file by hand, nothing changes yet. Your assistant shows you what was edited and asks; the edit takes effect only when you confirm it. A project set up before these rules were recorded keeps working as it is: your assistant asks you once to confirm them.

## From the command line {#command-line}

```baton
baton push
baton permission tag --detail "tag v1.2"
baton policy
baton policy set --permission tag=allow --note "Tagging is fine without asking."
```

`baton policy` lists every rule with the decision behind it.

Pushing is always explicit: nothing pushes automatically.
