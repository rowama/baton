---
id: "0074"
title: "Worker research, machine resource management and project setup are separate"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§4.1", "§4.4", "§6", "§11.6", "§13.4"]
---

# 0074. Worker research, machine resource management and project setup are separate

## Context

Before any work can run, the owner writes `~/.baton/workers.yaml` by hand. Much of what goes into it is shared knowledge about models and harnesses; the rest describes what one machine or account can use. Neither belongs to a project.

## Decision

1. **Repository research** is a maintainer-only utility in `tools/worker-research/`. It proposes reviewable changes to `defaults/known-workers.yaml` and is excluded from ordinary installations, with any research-only dependencies. This is a packaging boundary, not access control.
2. **The worker resource manager** is part of the installed runtime. It combines the shipped known-workers data (read-only), local discovery and the owner's persistent declarations, and maintains the machine's generated profiles. The Director is a conversational interface to it.
3. **Owner declarations are kept apart from generated profiles**: generated profiles are output, never the only record of the owner's intent.
4. **Onboarding is offered** by the first Director to find machine setup missing or incomplete; the answers, including "nothing else", persist machine-wide.
5. **`init` and `doctor` confirm readiness** and explain missing setup. Neither starts research or writes profiles.
6. **Refreshes are bounded**: untouched generated profiles may get metadata refreshes; new models are added only by an explicit manager run. Installing a Baton update does not expand the worker pool.
7. **Resources are machine-wide.** Per-project exceptions, worker cost data and price-based routing are deferred; project budgeting is unchanged.
