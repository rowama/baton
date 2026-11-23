---
id: "0187"
title: "Process statistics: seen through the process SME, raw waits, late defects later, unmeasured subscription routes included, the included flag recorded at dispatch, one stop per held step"
status: accepted
date: 2026-11-22
source: 'Owner, 2026-11-22, change 2026-11-process-stats: "All as suggested" (questions 1 to 6)'
sections: ["§12.4", "§8.2", "§8.4"]
---

# 0187. Process statistics: cost, owner burden and outcome, and how they are counted

## Context

Change 2026-11-process-stats adds cost, owner burden and outcome to the `stats` reference (§12.4), as Decision [0185](0185-self-improvement-direction.md), item 2, set out. Four questions were open in its Request. Two more came from the code: whether a route was *included* (a subscription the owner already pays for, `routing.included`, Decision [0181](0181-first-use-feedback-routing-and-answers.md)) is not recorded at dispatch, since `worker_selected` records the adapter but not the login mode; and a blocked result is itself an escalation (`step_escalated {reason: blocked}`), so "stops" could count it twice.

## Decision

1. **Where the owner sees them.** Through the process SME (`--ref stats`) and the Director, as today. No new command; a page view belongs with the setup page later.
2. **Waits are raw.** Wait time is recorded as it happened, nights included. Later analysis (baselines, detectors) reads medians, not means.
3. **Defects found late are not counted here.** Attributing a later finding to the step that caused it needs design; it moves to 2026-11-self-improvement's detectors.
4. **Unmeasured subscription routes are included.** An included attempt counts as included whether or not it reports tokens; absent tokens are absent, never estimated.
5. **The included flag is recorded at dispatch.** Every `worker_selected` carries `included: true|false`, the route's `routing.included` at dispatch. An attempt from before the flag counts as `unknown` unless its `usage.json` has a cost: guessing from the adapter alone could be wrong (a harness CLI on an API key is priced).
6. **One stop per held step.** A stop is a human gate opened (`human_gate_opened`), an escalation of any reason, `blocked` among them (`step_escalated`), or an iteration limit reached (`iteration_limit_reached`): each holds the step until the owner decides, and each is counted once. Open questions on a completed result hold nothing (Decision [0184](0184-answers-outside-a-blocked-step.md), item 4) and are not stops.
