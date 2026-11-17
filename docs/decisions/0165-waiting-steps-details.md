---
id: "0165"
title: "Waiting steps: a waiting state, a check that reports met, three failed checks escalate, submit may deliver, advisory intervals, a 30-day ceiling, install on request, Task Scheduler on WSL, tool steps only, skip where the recipe allows"
status: accepted
date: 2026-11-17
source: "Owner, 2026-11-17: \"All as suggested.\""
sections: ["§1", "§5.3", "§5.9", "§8.1", "§8.2", "§8.7", "§8.8", "§13.1", "§14"]
---

# 0165. Waiting steps: a waiting state, a check that reports met, three failed checks escalate, submit may deliver, advisory intervals, a 30-day ceiling, install on request, Task Scheduler on WSL, tool steps only, skip where the recipe allows

## Context

`2026-11-waiting-steps` carries Decision [0154](0154-tool-steps.md) item 5 into the runtime: a step that waits for a condition is held as state, with no Baton process kept alive, and an optional helper run from a scheduler checks on it. The change doc raised nine open questions, each with a suggested answer. Checked against the design before asking: an escalated step's decisions today are `retry` and `abandon` only (§8.1), and `skipped` is reached only through tailoring, so answer 9 adds one edge. The owner accepted every suggested answer.

## Decision

1. **A new state, `waiting`.** `dispatched → waiting → submitted`, and `waiting → escalated` at the deadline. `running` keeps its meaning (a supervisor and a work deadline), and reconciliation never judges a waiting step orphaned or timed out.
2. **A check reports in `output.json`** with `met: true|false`. When met, the rest of the output is the step's output and is checked against its schema. A check that fails (the tool crashed, exited non-zero, or wrote no valid report) is not "not met": it is counted, and after three failed checks in a row the step escalates to the owner. A successful check resets the count.
3. **`submit` works on a waiting step**, as it does on a person's step, so a program outside Baton (a webhook receiver, another tool) can hand in the result.
4. **The interval is advice.** A step may give `every: <duration>`. `baton waits schedule` uses the shortest `every` among waiting steps, never under five minutes. Baton does not enforce an interval.
5. **A longest wait.** `project.yaml` `waits: { max: <duration> }`, default `30d`. A recipe's `until` longer than it is cut to it, and `start` tells the owner.
6. **Install only when asked.** `baton waits schedule` prints the entry and what it does; `--install` installs it after showing it; `--remove` removes it.
7. **WSL.** `doctor` detects WSL and recommends a Windows Task Scheduler entry that runs the check inside WSL, since cron in WSL runs only while WSL is running. `waits schedule --install` on WSL installs that entry.
8. **Only tool steps wait** in this change. A check must be cheap and repeatable.
9. **Going on without it.** A waiting step declares `on_expire: escalate` (default) or `skip`. At expiry the step escalates (`wait_expired`); the owner's `decide <step> retry` starts another period, `abandon` abandons it, and, only for a step declaring `on_expire: skip`, `decide <step> skip` marks it `skipped`, which satisfies what depends on it. This adds the edge `escalated → skipped`, legal only for an expired wait that declares `skip`.
