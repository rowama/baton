---
id: "0093"
title: "An undocumented test-only time-scale environment variable is allowed"
status: accepted
date: 2026-11-08
source: "change 2026-11-fast-tests (owner, 2026-11-08)"
sections: ["§17"]
---

# 0093. An undocumented test-only time-scale environment variable is allowed

## Context

Some `slow` tests wait out real deadlines (overdue extend-then-terminate, hook timing). Scaling those intervals would cut them sharply, at the cost of a code path that exists only for tests (§0 rule 3, §2).

## Decision

`BATON_TEST_TIME_SCALE` may be read by the supervisor to scale such intervals. It defaults to 1, is not documented for owners, adds no concept, and `doctor` ignores it. It is used only where the slice-5 measurement shows a saving.
