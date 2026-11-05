---
id: "0059"
title: "The Director tells the owner before a dispatch it might not be woken for"
status: accepted
date: 2026-11-04
source: "change 2026-11-director-wake (owner requirement)"
sections: ["§13.1", "§13.3"]
---

# 0059. The Director tells the owner before a dispatch it might not be woken for

## Context

In the bug eval, a detached Director ended its turn after dispatching; nothing woke it when the worker finished, and the owner waited about 47 minutes before asking. The owner: "I don't need detached directors failing to notice when a worker finishes. ... As a fallback, I do need the director to let me know when it might not wake. It needs to issue that warning before it dispatches, so I will know to check back."

## Decision

Before a dispatch it will not stay attached for, a Director with no wake path tells the owner, in plain terms, that it might not notice when the work finishes and when to check back. The runtime supplies what is needed deterministically, before dispatch: whether a hook would wake the Director for this outcome, and how long the work may take. The Director relays it; the warning is never skipped for a Director that will detach without a wake path.
