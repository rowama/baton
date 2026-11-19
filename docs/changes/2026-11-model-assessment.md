---
id: 2026-11-model-assessment
title: "Baton learns what each model can do from checks run once, published evaluations and safe use, so cheaper models can take real work"
status: accepted
level: major
decisions: ["0175", "0176", "0110", "0081", "0084", "0088", "0111", "0076", "0114"]
touches: [design/workers.md, design/runtime.md, design/director-interface.md, design/recipes.md, design/platform-and-security.md]
manual: []
---

# Baton learns what each model can do from checks run once, published evaluations and safe use, so cheaper models can take real work

## Request

### Problem

On the owner's first real run (`2026-11-first-use-feedback`, F-6), routing for recipe-builder's profile step could choose only among a few expensive models. The causes, checked against Baton at `6209125`:

- **Tiers come from vendor positioning.** The shipped known-workers data judges 29 models. Its tiers are a research worker's judgment: "Tier assignments for new entries are judgment from vendor positioning (flagship → strong, mid → standard, small/lite → basic), not from benchmarks" (worker-research report, 2026-11-06); one was recorded as "a guess" (report, 2026-11-08). The data also goes stale: `claude-fable-5-1` is judged `strong`, while `claude-fable-5-2` on OpenRouter is unjudged and so `basic`.
- **Everything else is `basic`.** An unjudged listed model gets tier `basic` and only its catalog capabilities (Decision [0110](../decisions/0110-unjudged-model-default-tier.md)). Of 374 models OpenRouter listed for the owner, only a few reached `strong`.
- **Checks prove reachability, not ability.** A live check (Decision [0081](../decisions/0081-live-verification-on-request.md)) is one minimal round trip. A capability becomes `verified` only when a tool call is observed in a real step (Decisions [0084](../decisions/0084-capability-states.md), 0085).
- **Evidence needs use, and use needs trust.** No owner wants an unproven model on an important step, so unproven models stay unused and unproven.

The owner's direction (Decision [0175](../decisions/0175-model-assessment.md)): capability checks run once from the setup page; tiers from published evaluations (amending 0110); shadow attempts for strong steps; trial routing with a fallback for the rest; replay of past work later.

### Acceptance criteria

1. **A capability check set ships.** For each capability a check can establish (`structured_output`, `tool_use`, `workspace_read`, `long_form_writing`, `technical_reasoning`, `vision`), a few short tasks with answers graded by code. The set has a version.
2. **Checks run once, on request.** From the setup page (one model, a selection, or every model of a provider or price class) or `baton workers check [<profile>…]`, after showing the estimated cost. A model and route already checked under the current set version is skipped unless the route is an alias, or the owner asks again.
3. **Checks record evidence.** A pass records the capability `verified` with `by: check`, the set version and the date (§6.1). A failure records it `absent` with the task that failed, resettable as today. A check never adds a capability the profile does not claim, except `structured_output`, `tool_use` and `workspace_read`, which a pass may add to an unjudged model's profile (0176, item 3).
4. **Tiers can rest on published evaluations.** A model's tier in the known-workers data or the owner's overlay may cite published evaluation results as its basis (`basis: evaluation`, with the evaluation's name, the score, its source and date). A shipped mapping from evaluation results to tiers makes this mechanical. An owner's assessment (Decision [0111](../decisions/0111-owner-run-assessment.md)), started from the setup page, can tier chosen models this way. A model with no evidence stays `basic`.
5. **Each model has a track record.** Baton keeps, per model and route, what its checks, shadow attempts, trials and real steps showed: steps done, gates passed and failed, by tier and capability. The setup page and `workers status` show it.
6. **Shadow attempts on strong steps.** When enabled, a step requiring `strong` may also be dispatched, with the same packet, to one candidate model: a model rated `strong` by checks or evaluations but without a track record at that tier. The candidate's result is graded by the step's schema and script gates and kept in the record; it is never used, never feeds a later step and never counts as the step's result. Only steps that do not write to the workspace are shadowed. Shadowing has a budget the owner sets.
7. **Trial routing on the other steps.** When enabled, a step below `strong` that a bad result cannot get past unnoticed (it has a schema gate and a script gate or a review, and its effect is not irreversible) may go to a candidate model. A failed gate retries on a proven model, without counting against the step's attempts. The Director tells the owner, in plain words, when a step was a trial.
8. **Promotion.** A candidate that does well enough is treated as proven for that tier, and one that does badly is put back, by thresholds the owner can see: proven after 5 passes at a tier with no failure in the last 5, put back after 2 failures in the last 5 (0176, item 5). The owner can promote, demote or exclude a model by hand.
9. **Cost stays visible and bounded.** Every check, shadow attempt and trial shows its cost in the track record; checks show an estimate first; shadowing and trials stop at their budget. Free models are tried first.
10. **Identity is never blurred.** Every shadow attempt and trial records its model as any dispatch does; nothing switches models silently inside an attempt (Decisions [0075](../decisions/0075-model-identity-separate-from-route.md), [0076](../decisions/0076-unknown-identity-not-independent.md)).
11. **Manual and design are current.**

### Open questions

All nine answered as suggested: Decision [0176](../decisions/0176-model-assessment-details.md).

1. **Which published evaluations count?** *Suggested:* independent leaderboards that publish their method and test models themselves, preferred over figures a vendor reports about its own model; each tier cites at least one, and the shipped mapping names which evaluation informs which capability (coding evaluations for `technical_reasoning`, for example). *Rationale:* vendor-reported scores and leaked test items inflate results; naming the evaluation lets the owner judge it.
2. **What do the checks look like?** *Suggested:* three to five tasks per capability, each a few hundred tokens, with deterministic grading: a reply matching a schema; a correct function call; an answer found only in a supplied file; a set of explicit constraints all followed; small reasoning problems with one right answer. `long_form_writing` is checked only for following length, structure and constraints, not quality. *Rationale:* cheap enough to run across many models once, and graded without another model.
3. **Can a passed check add a capability to an unjudged model?** *Suggested:* yes, for capabilities a check fully establishes (`structured_output`, `tool_use`, `workspace_read`); `technical_reasoning` and the tier come only from evaluations or a track record. *Rationale:* a few puzzles prove a model can follow a schema, not that it reasons at a strong level.
4. **How is a shadow attempt graded?** *Suggested:* by the step's schema and script gates, and by whether the chosen worker's result passed; no model judges the candidate in the first version. *Rationale:* deterministic and free; a judge model adds cost and its own errors.
5. **When is a candidate proven, or put back?** *Suggested:* proven at a tier after 5 passed shadow attempts or trials at that tier with no failures in the last 5; put back after 2 failures in its last 5. *Rationale:* a starting rule, not a measured one, shown to the owner and adjustable.
6. **What are the default budgets?** *Suggested:* both off until the owner turns them on in the setup page; when on, shadowing at most one candidate per step and a daily credit limit the owner sets, and trials limited to free or cheaper-than-the-proven-worker models. *Rationale:* nothing should spend the owner's credit unasked.
7. **Where do the track record and settings live?** *Suggested:* machine-wide, beside the capability states (`~/.baton/`), since models are a machine's resource; settings as machine preferences (Decision [0124](../decisions/0124-machine-level-preferences.md)). *Rationale:* evidence about a model is the same in every project on the machine.
8. **How does this relate to cost-aware routing (F-6)?** *Suggested:* F-6 orders proven workers by cost; this change grows the set of proven workers. Both can land in either order. *Rationale:* they are independent.
9. **Does this add a concept (§2)?** *Suggested:* no. The check set is shipped profile knowledge, like the known-workers data; the track record is evidence behind capability states and tiers; shadow attempts and trials are dispatches. §2 says so, as it does for worker setup. *Rationale:* the owner meets none of these terms; the Director only says a step was tried on a cheaper model.

### Out of scope

- **Replay of past work** (Decision 0175, item 5): a later change, once there is history to replay.
- **Grading by a judge model.**
- **Shadowing steps that write to the workspace.**
- **Changing recipe tiers** (F-6 of `2026-11-first-use-feedback`).

## Design

For the owner's approval, with the Request.

### Shape

- **Check set.** `defaults/capability-checks/` with one file per capability (`format: baton-capability-checks/1`, a set `version`), each task a prompt, inputs and a grader (`json_schema`, `function_call`, `exact`, `contains_all`, `constraints`). Run through the worker runner (API routes) or the adapter (harness routes), one task per call.
- **Command and page.** `baton workers check [<profile>…] [--all-free] [--again]` and a "Check capabilities" action on the setup page's models list, both returning `{estimate, results}`; the page's existing verify route gains the check option.
- **Evidence.** Capability states gain `by: check {set_version, tasks_passed, tasks_failed}`; a pass also records `checked: {set_version, date}` on the model and route, which `workers check` uses to skip.
- **Evaluation basis.** `capability_basis` and a new `tier_basis` accept `evaluation {name, score, source, retrieved}`; `defaults/evaluation-tiers.yaml` maps named evaluations to tiers and capabilities. The researcher and the owner's assessment write it; the validator requires a source.
- **Track record.** `~/.baton/track-record.yaml`, keyed by model and route: counts by tier and capability for checks, shadows, trials and real steps, and recent outcomes for promotion.
- **Shadow attempts.** At dispatch of an eligible step, the runtime picks one candidate within budget and dispatches it with the same packet under a shadow dispatch id; its intake runs the schema and script gates only and records `shadow_result {profile, model_id, gates, cost}` on the step, never `step_passed`.
- **Trials.** Routing places a candidate first for an eligible step; a failed gate records `trial_failed` and retries on the first proven worker with the attempt not counted; `worker_selected` carries `trial: true`.

### Doc edits

- `design/workers.md` §6.1 (`by: check`, `checked`), §6.4 (the check set, evaluation basis, track record, assessment from the page).
- `design/runtime.md` §8.2 (`shadow_result`, `trial_failed`, `trial` on `worker_selected`), §8.4 (candidates in routing), §8.7 (shadow dispatch).
- `design/director-interface.md` §13.1 (`workers check`, `workers status` with track records), §13.3 (telling the owner about trials), §13.9 (the page's check, assessment and settings).
- `design/recipes.md` §5.6: tier basis.
- `design/platform-and-security.md`: budgets and what shadow attempts may touch.

### Manual edits

To be listed when the change is accepted. Expected: an administrator topic on how Baton learns about models, `admin/accounts-and-costs.md`, `admin/machine-settings.md`, `reference/commands.md`.

### Decisions

- [0175](../decisions/0175-model-assessment.md) (accepted): the approach.
- [0110](../decisions/0110-unjudged-model-default-tier.md) (accepted, amended by 0175): unjudged models stay `basic` only without evidence.
- [0081](../decisions/0081-live-verification-on-request.md), [0084](../decisions/0084-capability-states.md), [0088](../decisions/0088-capability-basis.md) (accepted): live checks, capability states and their basis.
- [0111](../decisions/0111-owner-run-assessment.md) (accepted): owner assessment, now startable from the page.
- [0076](../decisions/0076-unknown-identity-not-independent.md), [0114](../decisions/0114-quota-exhausted-reroutes.md) (accepted): identity and re-routing.
- [0176](../decisions/0176-model-assessment-details.md) (accepted): the nine answers.

## Plan

Request and Design approved 2026-11-18. Each slice's detail is refined against the code when it starts.

### Slice 1: capability checks, once, from the page

- **Outcome:** the owner checks chosen models once from the setup page, and passed capabilities are verified.
- **Criteria:** the check set and graders; estimate before running; skip when already checked; `by: check` states; added capabilities for unjudged models where 0176 allows; the page action and the CLI command.
- **Effort:** M

### Slice 2: tiers from published evaluations

- **Outcome:** models are tiered from cited evaluations, in the shipped data and the owner's overlay, and the shipped data is refreshed with them.
- **Criteria:** `tier_basis` and evaluation basis validated; the evaluation-to-tier mapping; assessment from the page; a refresh covering the models most used through OpenRouter, including current Fable and Opus versions.
- **Effort:** M

### Slice 3: track record and trial routing

- **Outcome:** a below-strong step may go to a free or cheaper candidate, a failure falls back to a proven worker, and the candidate's record grows.
- **Criteria:** the track record; eligibility rules; fallback without counting an attempt; promotion and demotion; budgets; the Director's words to the owner; the page's settings.
- **Effort:** L

### Slice 4: shadow attempts on strong steps

- **Outcome:** a candidate shadows strong steps within budget, graded but never used, and can earn a strong record.
- **Criteria:** candidate choice; shadow dispatch with the same packet; gates only; never used or counted; read and none steps only; budget; the track record and promotion.
- **Effort:** L

## Log

### Proposal drafted

- **Summary:** Written from the owner's direction of 2026-11-18 (Decision 0175), after F-6 of `2026-11-first-use-feedback`. Checked against Baton at `6209125`: the shipped data's 29 judged models and its research reports. No code changed.
- **Owner decision:** 2026-11-18, "Concur checks once from setup and amending 0110. ... I want to start with 2 for the high stakes (i.e, strong) steps and 3 for the low stakes steps."
- **Accepted:** No; proposal only. Eight open questions await the owner.

### Request and Design accepted

- **Summary:** The owner concurred with all nine suggested answers (the ninth, on the concept budget, added this session under §0 rule 8) and approved the Request and Design. Recorded as Decision 0176; criteria 3 and 8 now cite it. No code changed.
- **Owner decision:** 2026-11-18, "Concur on all."
- **Accepted:** Yes.
