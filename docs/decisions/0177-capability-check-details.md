---
id: "0177"
title: "Capability checks: no vision check until a step needs image input; each call's tokens, cost and response time are recorded"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"A.\" (vision checks wait); \"B. as suggested but also record response time.\""
sections: ["§6.3", "§6.4"]
---

# 0177. Capability checks: no vision check until a step needs image input; each call's tokens, cost and response time are recorded

## Context

Refining slice 1 of `2026-11-model-assessment` against the code showed two gaps. Baton's API runner sends text only, so it cannot give a model an image to check `vision`. And the runner records no token usage or cost, so a check could show only an estimate from list prices, while criterion 9 asks for the cost of every check, shadow attempt and trial.

## Decision

1. **Vision waits.** The first check set covers `structured_output`, `tool_use`, `workspace_read`, `long_form_writing` and `technical_reasoning`. Checks for `vision` come with image input in the runner, when a step first needs it.
2. **Usage, cost and time are recorded.** The API runner records, for each attempt, the model calls it made, their input and output tokens, LiteLLM's cost figure where it has one, and the time the calls took. A check shows its estimate first and the actual cost and response time afterwards. A route on a subscription reports no per-call cost and shows "included in the subscription"; its response time is measured all the same. Later slices reuse the same record for shadow attempts, trials and real steps.
