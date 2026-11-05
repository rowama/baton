---
id: "0058"
title: "A Director with no wake path is warned, never refused"
status: accepted
date: 2026-11-04
source: "change 2026-11-director-wake (bug eval 2026-11-04-director-wake-on-needs-human, B6)"
sections: ["§8.7", "§13.4"]
---

# 0058. A Director with no wake path is warned, never refused

## Context

The bug eval's B6 proposed that `dispatch` refuse, or loudly warn, when a Director declaring itself detached (`BATON_HARNESS` other than `cli`) has no completion hook. Refusing changes behavior, and Baton cannot tell reliably whether a Director is detached or whether its harness wakes it.

## Decision

Warn, never refuse: `dispatch` and `ask_sme` warn whenever no hook would wake a Director (with or without `--wait`), `eligible` reports the wake path before dispatch (decision 0059), and `doctor` warns, raising it to a problem when an active run's lease names a harness other than `cli`. Revisit if Directors keep detaching without a wake path despite the warnings.
