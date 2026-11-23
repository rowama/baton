---
id: 2026-11-process-stats
title: "Process statistics also count what work costs, how much of the owner it takes, and how often the owner accepts it first time"
status: accepted
level: standard
decisions: ["0187", "0185", "0184", "0177", "0181", "0031"]
touches: [design/experts.md, design/runtime.md]   # §12.4 (the stats reference), §8.2 (worker_selected records included)
manual: "none: the stats reference is read by the process SME and by Directors, not by the owner; nothing an owner sees or configures changes"
---

# Process statistics also count what work costs, how much of the owner it takes, and how often the owner accepts it first time

## Request

### Problem

The process statistics (`stats`, §12.4; `sme.stats()`) count, per qualified step, attempts, passes, rejections, gate failures, timeouts, escalations, failure classes, time per attempt, iterations per group and review findings. They leave out three things Baton's purpose depends on:

1. **Cost.** The runner writes `usage.json` for every API attempt (Decision [0177](../decisions/0177-capability-check-details.md), item 2) and the track record already reads it (`assessment.py`), but `stats` adds up none of it. In the first real use, the most expensive model kept being chosen (2026-11-first-use-feedback-batch-a, F-6) and a retry loop spent about 30 minutes of subscription per attempt (2026-11-disposition-evidence); only the owner noticed.
2. **Owner burden.** How often a step stops for the owner, how many questions it asks, how often it asks again what was already answered (F-7), and how long work waits on the owner. Baton exists to take work off the owner, and none of this is measured.
3. **Outcome.** How often the owner accepts a step's result at a human gate first time, rejects it, or edits what it published afterwards.

This is the measuring half of the "how work goes" track of [2026-11-self-improvement](2026-11-self-improvement.md), taken ahead of the rest of it, which stays on hold (Decision [0185](../decisions/0185-self-improvement-direction.md), item 2). It also gives the owner's own runs the numbers from which the first baselines are derived (0185, item 3).

### Acceptance criteria

1. **Cost per step.** Every step in `stats` carries `cost {usd, tokens_in, tokens_out, attempts_priced, attempts_included, attempts_unknown}`: `usd` and tokens summed from each attempt's `usage.json`; an attempt on a route the owner already pays for (`routing.included` at dispatch) counted as included; an attempt with neither a cost nor an included route counted as unknown. Nothing is estimated.
2. **Owner burden per step.** Every step carries `owner {stops, questions, open, reasked, decisions, wait_s_total, wait_s_max}`:
   - `stops`: human gates opened, blocked results, and escalations needing the owner (open questions on a completed result do not wait for the owner, Decision [0184](../decisions/0184-answers-outside-a-blocked-step.md), item 4, so they are not stops);
   - `questions`: questions for the owner recorded on results (`result_submitted.questions`, blocked or completed; Decisions [0031](../decisions/0031-structured-questions.md), 0184), and `open` of them still unanswered at the end of the run;
   - `reasked`: questions whose id was already answered for the same step in the same run, in an earlier attempt or iteration (Decision [0181](../decisions/0181-first-use-feedback-routing-and-answers.md), item 2, makes those answers available, so this should be zero);
   - `decisions`: the owner's `human_decision` events on the step;
   - `wait_s_*`: time from each stop to the owner's decision that ends it.
3. **Outcome per step.** Every step carries `outcome {gate_first_try, gate_rejections, owner_edits}`: steps whose human gates passed on the first owner decision, human-gate rejections, and the owner's edits to the step's published artifacts afterwards (`human_revision_ingested {source: drift}`).
4. **Per recipe.** `stats` gains `recipes {<recipe>@<v>: {runs, completed, abandoned, cost_usd, owner_stops, owner_wait_s}}`, the last three each `{total, mean}` over the runs, so a whole run can be compared with a baseline.
5. **Included recorded at dispatch.** Every `worker_selected` carries `included: true|false` (Decision 0187, item 5); an attempt without it is unknown unless its `usage.json` has a cost.
6. Existing keys are unchanged; the process SME's instructions name the new ones.
7. Tests cover each count from a recorded event log, including an included route, an unpriced one and a re-asked question.

### Open questions

All six settled by the owner on 2026-11-22 as suggested ("All as suggested"): Decision [0187](../decisions/0187-process-stats-details.md). Questions 5 and 6 came from the code: `worker_selected` does not record the login mode `routing.included` needs, and a blocked result is itself an escalation.

1. **Where does the owner see these?** *Suggested:* through the process SME (`--ref stats`) and the Director, as today; no new command in this change. *Rationale:* the concept budget (§0 rule 8); a page view belongs with the setup page later, and the digest of 2026-11-self-improvement is where the owner normally meets them.
2. **Wait time when the owner is away overnight.** *Suggested:* record raw wait time; later analysis (baselines, detectors) uses medians, not means. *Rationale:* the record should state what happened; how to read it belongs to the analysis.
3. **Defects found late** (a later review finding a problem in an earlier step's artifact). *Suggested:* not in this change; it moves to 2026-11-self-improvement's detectors. *Rationale:* attributing a finding to the step that caused it needs design (which artifact, which line); the counts above don't.
4. **Harness routes report no tokens.** *Suggested:* counted as included with tokens absent, never estimated. *Rationale:* matches the rule that a subscription route is "included", never guessed (§6.4).
5. **Included is not recorded at dispatch.** *Suggested:* every `worker_selected` records `included`; older attempts count as unknown unless priced. *Rationale:* nothing estimated; the adapter alone cannot tell a subscription login from an API key.
6. **What is a stop.** *Suggested:* a human gate opened, an escalation of any reason (`blocked` among them) or an iteration limit reached, each once. *Rationale:* each holds the step until the owner decides; open questions hold nothing (0184).

## Design

### Doc edits

- `design/experts.md` §12.4: the `stats` reference gains `cost`, `owner` and `outcome` per step and `recipes` per recipe version, each defined as in the acceptance criteria; the process SME's inputs say so.
- `design/runtime.md` §8.2: `worker_selected` carries `included`.

### Manual edits

- none: the `stats` reference is read by the process SME and by Directors, not by the owner; no command, setting or page changes.

### Decisions

- [0187](../decisions/0187-process-stats-details.md) (accepted): the six open questions, all as suggested.
- [0185](../decisions/0185-self-improvement-direction.md) (accepted): this change goes ahead now; baselines from the owner's own runs.
- [0177](../decisions/0177-capability-check-details.md) (accepted): `usage.json` per attempt.
- [0181](../decisions/0181-first-use-feedback-routing-and-answers.md) (accepted): answers last across rounds, so re-asking is measurable as a fault.
- [0031](../decisions/0031-structured-questions.md) (accepted): questions for the owner are structured, with ids.
- [0184](../decisions/0184-answers-outside-a-blocked-step.md) (accepted): a completed result may carry questions; open questions wait for nothing.

## Plan

### Slice 1: cost, owner burden and outcome in stats

- **Outcome:** `stats` answers "what does this step cost, how much of the owner does it take, and how often is it accepted first time", per step and per recipe version.
- **Criteria:**
  - `cost` from `usage.json`, with included, priced and unknown attempts (criterion 1);
  - `owner` counts and waits, with a re-asked question detected (criterion 2);
  - `outcome` from human gates and owner edits (criterion 3);
  - `recipes` totals (criterion 4);
  - `included` recorded at dispatch (criterion 5);
  - existing keys unchanged; the process SME's instructions updated (criterion 6);
  - tests from recorded event logs (criterion 7).
- **Effort:** M

## Log

### Proposed

- **Summary:** Opened from the 2026-11-22 discussion of 2026-11-self-improvement, as its measuring half taken first. Checked against `src/baton/sme.py` `stats()` at `a1d25f0`: no cost, owner or outcome counts today. No code changed.
- **Owner decision:** 2026-11-22, "2-yes, now." (Decision 0185, item 2).
- **Accepted:** No; proposal only. Open questions 1 to 4 await the owner.

### Accepted

- **Summary:** The owner answered the six open questions (four from the Request, two found in the code) "All as suggested", 2026-11-22. Decision 0187 recorded.
