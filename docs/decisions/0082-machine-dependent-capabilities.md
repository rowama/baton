---
id: "0082"
title: "Machine-dependent capabilities need an owner declaration or a passing probe"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§5.6", "§6.1"]
---

# 0082. Machine-dependent capabilities need an owner declaration or a passing probe

## Context

A capability must be true on this machine (§6.1). Some, such as `loopback_network`, depend on the machine's sandbox, not on the model or harness.

## Decision

- Known-workers data lists only model- and harness-intrinsic capabilities.
- A machine-dependent capability (the known-workers data lists which, under `machine_dependent`; `loopback_network` to start with) is added to a generated profile only when the owner declares it for that resource, recorded as declared, or when a probe on this machine passes, recorded as probed.

Amended 2026-11-06 while building it: the list lives in the known-workers data, not the capability vocabulary, because a published vocabulary version is never edited (§5.6) and a new one would make every recipe re-pin.
