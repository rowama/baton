---
id: "0060"
title: "No wake notice or warning when the work is a person's"
status: accepted
date: 2026-11-04
source: "change 2026-11-director-wake (owner, while building slice 1)"
sections: ["§8.7", "§13.1"]
---

# 0060. No wake notice or warning when the work is a person's

## Context

The change's criterion 1 says "manual steps get no notice", but a step is not manual: its worker is (adapter `manual`, a person who writes the result and is handed in with `submit`). `eligible` reports on a step before a worker is chosen, and its eligible set may hold a manual profile and a process profile together.

## Decision

The rule follows the worker. `eligible` always reports `wake {configured, hook?}`, and leaves out `notice` and `expected` only when every eligible worker is manual; a mixed set gets them, since the Director may choose the process worker. `dispatch` to a manual worker (including a queued one) never gives the wake warning: the Director hands that result in itself, so nothing ends unseen.
