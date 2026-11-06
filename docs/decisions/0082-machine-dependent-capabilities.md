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
- A machine-dependent capability (the vocabulary marks which; `loopback_network` to start with) is added to a generated profile only when the owner declares it for that resource, recorded as declared, or when a probe on this machine passes, recorded as probed.
