---
id: 2026-11-model-assessment
title: "Baton learns what each model can do from checks run once, published evaluations and safe use, so cheaper models can take real work"
status: in-progress
level: major
decisions: ["0175", "0176", "0177", "0178", "0179", "0182", "0110", "0081", "0084", "0088", "0111", "0076", "0114"]
touches: [design/workers.md, design/runtime.md, design/director-interface.md, design/recipes.md, design/platform-and-security.md, design/layouts.md]
manual: [user/choose-models.md, admin/accounts-and-costs.md, admin/files-and-paths.md, admin/machine-settings.md, context.yaml, reference/commands.md, reference/diagnostics.md, reference-notes.yaml, anchors.yaml]
---

# Baton learns what each model can do from checks run once, published evaluations and safe use, so cheaper models can take real work

## Request

### Problem

On the owner's first real run (`2026-11-first-use-feedback-batch-a`, F-6), routing for recipe-builder's profile step could choose only among a few expensive models. The causes, checked against Baton at `6209125`:

- **Tiers come from vendor positioning.** The shipped known-workers data judges 29 models. Its tiers are a research worker's judgment: "Tier assignments for new entries are judgment from vendor positioning (flagship → strong, mid → standard, small/lite → basic), not from benchmarks" (worker-research report, 2026-11-06); one was recorded as "a guess" (report, 2026-11-08). The data also goes stale: `claude-fable-5-1` is judged `strong`, while `claude-fable-5-2` on OpenRouter is unjudged and so `basic`.
- **Everything else is `basic`.** An unjudged listed model gets tier `basic` and only its catalog capabilities (Decision [0110](../decisions/0110-unjudged-model-default-tier.md)). Of 374 models OpenRouter listed for the owner, only a few reached `strong`.
- **Checks prove reachability, not ability.** A live check (Decision [0081](../decisions/0081-live-verification-on-request.md)) is one minimal round trip. A capability becomes `verified` only when a tool call is observed in a real step (Decisions [0084](../decisions/0084-capability-states.md), 0085).
- **Evidence needs use, and use needs trust.** No owner wants an unproven model on an important step, so unproven models stay unused and unproven.

The owner's direction (Decision [0175](../decisions/0175-model-assessment.md)): capability checks run once from the setup page; tiers from published evaluations (amending 0110); shadow attempts for strong steps; trial routing with a fallback for the rest; replay of past work later.

### Acceptance criteria

1. **A capability check set ships.** For each capability a check can establish (`structured_output`, `tool_use`, `workspace_read`, `long_form_writing`, `technical_reasoning`), a few short tasks with answers graded by code. The set has a version. Vision checks wait for image input in the runner (Decision 0177).
2. **Checks run once, on request.** From the setup page (one model, a selection, or every model of a provider or price class) or `baton workers check [<profile>…]`, after showing the estimated cost. A model and route already checked under the current set version is skipped unless the route is an alias, or the owner asks again.
3. **Checks record evidence.** A pass records the capability `verified` with `by: check`, the set version and the date (§6.1). A failure records it `absent` with the task that failed, resettable as today; a failed task is run once more first, and only a second failure counts (Decision 0178, item 4). A check never adds a capability the profile does not claim, except `structured_output`, `tool_use` and `workspace_read`, which a pass may add to an unjudged model's profile (0176, item 3).
4. **Tiers can rest on published evaluations.** A model's tier in the known-workers data or the owner's overlay may cite published evaluation results as its basis (`basis: evaluation`, with the evaluation's name, the score, its source and date). A shipped mapping from evaluation results to tiers makes this mechanical. An owner's assessment (Decision [0111](../decisions/0111-owner-run-assessment.md)), started from the setup page, can tier chosen models this way. A model with no evidence stays `basic`.
5. **Each model has a track record.** Baton keeps, per model and route, what its checks, shadow attempts, trials and real steps showed: steps done, gates passed and failed, by tier and capability. The setup page and `workers status` show it.
6. **Shadow attempts on strong steps.** When enabled, a step requiring `strong` may also be dispatched, with the same packet, to one candidate model: a model rated `strong` by checks or evaluations but without a track record at that tier. The candidate's result is graded by the step's schema and script gates and kept in the record; it is never used, never feeds a later step and never counts as the step's result. Only steps that do not write to the workspace are shadowed. Shadowing has a budget the owner sets.
7. **Trial routing on the other steps.** When enabled, a step below `strong` that a bad result cannot get past unnoticed (it has a schema gate and a script gate or a review, and its effect is not irreversible) may go to a candidate model. A failed gate retries on a proven model, without counting against the step's attempts. The Director tells the owner, in plain words, when a step was a trial.
8. **Promotion.** A candidate that does well enough is treated as proven for that tier, and one that does badly is put back, by thresholds the owner can see: proven after 5 passes at a tier with no failure in the last 5, put back after 2 failures in the last 5 (0176, item 5). The owner can promote, demote or exclude a model by hand.
9. **Cost stays visible and bounded.** Every check, shadow attempt and trial shows its cost in the track record; checks show an estimate first. Shadowing and trials reserve conservative estimated cost under a machine-wide lock and reconcile actual usage afterwards; no paid dispatch without a price and usable estimate, and no new reservation beyond the available budget. Provider charges can exceed estimates, which the page explains (0179). Free models are tried first.
10. **Identity is never blurred.** Every shadow attempt and trial records its model as any dispatch does; nothing switches models silently inside an attempt (Decisions [0075](../decisions/0075-model-identity-separate-from-route.md), [0076](../decisions/0076-unknown-identity-not-independent.md)).
11. **Manual and design are current.**

### Open questions

The original nine questions below were answered as suggested: Decision [0176](../decisions/0176-model-assessment-details.md). Six further questions found while refining slices 3 and 4 were answered as suggested in Decision [0179](../decisions/0179-trial-and-shadow-routing-details.md): candidate and fallback trust, reversible effects, review-gated trials, budget enforcement, evidence identity and shadow gate effects. They were put to the owner together with suggestions and rationale on 2026-11-19. The owner accepted all six suggestions for now on 2026-11-19: "for now, agree with all". No owner question remains from that batch.

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
- **Changing recipe tiers** (F-6 of `2026-11-first-use-feedback-batch-a`).

## Design

Request and Design approved 2026-11-18. Slices 1 and 2 are implemented; the six remaining routing refinements were accepted in Decision 0179 on 2026-11-19. The shape below distinguishes the delivered interfaces from the remaining outline.

### Shape

- **Check set (delivered).** `defaults/capability-checks.yaml`, one `version`, 17 tasks over five capabilities, with code graders. Each task is a tiny packet through the profile's own adapter; no vision check yet (0177). Slice 1's refinement and Log describe the actual format and execution.
- **Command and page (delivered).** `baton workers check [<profile>…] [--free] [--provider <name>] [--all] [--again] [--yes]` and **Check abilities** on the setup page. `POST /api/models/check` returns an estimate before a separately confirmed run; the live verify route remains separate.
- **Check evidence (delivered).** Capability states carry `by: check` and `set_version`. The last check, including completeness, date, outcomes, cost and time, is stored in the track record and used to skip a completed current-version check. A failed task is repeated once before failure counts (0178).
- **Evaluation basis (delivered).** `tier_basis` carries deciding and optional supporting evaluation results (`name`, `version`, `score`, optional `configuration`, `source: {url, retrieved}`); a capability basis may cite one result. `defaults/evaluation-tiers.yaml` maps results to tiers and grants. The same validator checks shipped data, overlays and assessments (0178).
- **Track record (remaining).** Extend `~/.baton/track-record.yaml` beyond its delivered last-check records to counts by tier and capability for checks, shadows, trials and real steps, plus recent outcomes for promotion. Evidence belongs to the canonical model and route configuration, resets when model, endpoint or harness version changes, and cannot confer lasting promotion on aliases (0179). Preserve last-check records separately or migrate them compatibly.
- **Shadow attempts.** At dispatch of an eligible step, the runtime picks one candidate within budget and dispatches it with the same packet under a shadow dispatch id; its intake runs the schema and script gates only and records `shadow_result {profile, model_id, gates, cost}` on the step, never `step_passed`.
- **Trials.** The Director's normally selected worker is the fallback; a free or cheaper eligible candidate may be tried first without relaxing any tier, capability or independence requirement. The step must declare `effect: none` or `effect: reversible` and have qualifying blocking gates. A failed gate records `trial_failed` and readies a separate fallback attempt without charging the recipe's attempt budget; `worker_selected` carries `trial: true`. Blocking reviews participate immediately, with success pending their outcome (0179).

### Doc edits

- `design/workers.md` §6.1 (`by: check`, `checked`), §6.4 (the check set, evaluation basis, track record, assessment from the page).
- `design/runtime.md` §8.2 (`shadow_result`, `trial_failed`, `trial` on `worker_selected`), §8.4 (candidates in routing), §8.7 (shadow dispatch).
- `design/director-interface.md` §13.1 (`workers check`, `workers status` with track records), §13.3 (telling the owner about trials), §13.9 (the page's check, assessment and settings).
- `design/recipes.md` §5.1: explicit step effects and shadow evaluation safety; §5.6: tier basis.
- `design/platform-and-security.md`: budgets and what shadow attempts may touch.

### Manual edits

- Slice 1: `user/choose-models.md` gains **Check abilities** (`#check-abilities`): what the tasks cover, the estimate first, what verified and absent mean afterwards, checking once, and the terminal command; its table's **Checked** column also shows the last capability check. `admin/accounts-and-costs.md` says what checks cost and links there. `admin/files-and-paths.md` lists `~/.baton/track-record.yaml`. `context.yaml` maps the page's `ui.models.check` help to the new section. `reference/commands.md` is regenerated with `baton workers check`.
- Slice 2: `user/choose-models.md` gains **Rate from published evaluations** (`#rate-from-evaluations`): where tiers come from, the thresholds, what an unrated model is, the page's action and the command; the **Tier** column row points there, and **Check abilities** says a failed task gets a second try. `context.yaml` maps `ui.models.rate`. `reference-notes.yaml` explains the diagnostic `capability_check.record_invalid`, and the generated `reference/diagnostics.md` with it.
- Slice 3: `user/choose-models.md` gains **Try cheaper models** (`#try-cheaper-models`): what a trial is, which steps are tried, proven and put back with **Promote** and the filter, the daily limit ($0: free only) and that a provider can charge more than the estimate, and the commands; the **Tier** row mentions the record. `admin/accounts-and-costs.md` says what trials spend; `admin/files-and-paths.md` lists `~/.baton/assessment-spend.yaml` and the track record's new contents; `admin/machine-settings.md` describes `assessment:` in the machine preferences. `context.yaml` maps `ui.models.assessment`. `reference-notes.yaml` explains `assessment.record_invalid`, `assessment.settings_unreadable` and `assessment.spend_invalid`; `reference/commands.md` and `reference/diagnostics.md` are regenerated with `workers assessment` and `workers standing`.
- Slice 4: `user/choose-models.md` (shadow attempts) and `admin/accounts-and-costs.md` (what shadows spend).

### Decisions

- [0175](../decisions/0175-model-assessment.md) (accepted): the approach.
- [0110](../decisions/0110-unjudged-model-default-tier.md) (accepted, amended by 0175): unjudged models stay `basic` only without evidence.
- [0081](../decisions/0081-live-verification-on-request.md), [0084](../decisions/0084-capability-states.md), [0088](../decisions/0088-capability-basis.md) (accepted): live checks, capability states and their basis.
- [0111](../decisions/0111-owner-run-assessment.md) (accepted): owner assessment, now startable from the page.
- [0076](../decisions/0076-unknown-identity-not-independent.md), [0114](../decisions/0114-quota-exhausted-reroutes.md) (accepted): identity and re-routing.
- [0176](../decisions/0176-model-assessment-details.md) (accepted): the nine answers.
- [0177](../decisions/0177-capability-check-details.md) (accepted): no vision check yet; the runner records tokens, cost and response time.
- [0178](../decisions/0178-evaluation-tiers.md) (accepted): the Artificial Analysis index decides tiers (50 and 25), LMArena supports, standard grants `technical_reasoning`, a failed check task runs once more.
- [0179](../decisions/0179-trial-and-shadow-routing-details.md) (accepted): candidates retain every routing requirement; the normally selected worker is the fallback; explicit step effects; blocking reviews participate immediately; estimated budget reservations; evidence resets with identity or route changes; explicit shadow evaluation safety and scratch copies.
- [0182](../decisions/0182-assessment-grading-put-back-budget.md) (accepted): a shadow is graded by its own gates, a failure the primary shared forgiven; put back is one tier lower until promoted, announced, listed and cleared by a new identity or rating; proven changes no eligibility; the $0 default allows free models only; shipped recipes declare effects where clear.

## Plan

Request and Design approved 2026-11-18. Each slice's detail is refined against the code when it starts.

### Slice 1: capability checks, once, from the page

- **Outcome:** the owner checks chosen models once from the setup page, and passed capabilities are verified.
- **Criteria:** the check set and graders; estimate before running; skip when already checked; `by: check` states; added capabilities for unjudged models where 0176 allows; the page action and the CLI command.
- **Refined against the code (2026-11-18):** one check-set file, `defaults/capability-checks.yaml`, with one version (simpler than a file per capability, and the version is the set's); each task runs as a tiny packet through the profile's own adapter, as `live_check` runs its no-op, so API and harness routes share one path; a task with files runs in read mode, so for an API route the runner's tool loop proves `tool_use` (and `finish` is itself a tool call) and `workspace_read` together; no `vision` check (0177); the runner writes `usage.json` per attempt (0177); the track record starts here, holding the last check per profile; checks cover generated profiles, the ones the page lists. The CLI flags are `--free`, `--provider`, `--all`, `--again`, `--yes`.
- **Effort:** M

### Slice 2: tiers from published evaluations

- **Outcome:** models are tiered from cited evaluations, in the shipped data and the owner's overlay, and the shipped data is refreshed with them.
- **Criteria:** `tier_basis` and evaluation basis validated; the evaluation-to-tier mapping; assessment from the page; a refresh covering the models most used through OpenRouter, including current Fable and Opus versions.
- **Effort:** M
- **Refined (2026-11-19, Decision 0178):** the mapping is `defaults/evaluation-tiers.yaml`; a tier with an evaluation basis must equal what its deciding results give (lower median); new models are keyed by their OpenRouter canonical slug, with no routes, so listing profiles take the tier and keep their price.

### Slice 3: track record and trial routing

- **Outcome:** a below-strong step may go to a free or cheaper candidate, a failure falls back to a proven worker, and the candidate's record grows.
- **Criteria:** the track record; eligibility rules; fallback without counting an attempt; promotion and demotion; budgets; the Director's words to the owner; the page's settings.
- **Effort:** L
- **Refined (2026-11-19, Decision 0179):** Items 1–5 settle candidate and fallback trust, how reversibility is declared, whether blocking reviews participate immediately, what the daily budget guarantees and when evidence resets. Preserve current routing with assessment disabled. Count a candidate's pass only once its qualifying blocking gates finish; a schema pass while a review is pending is not success. Do not confuse provider or gate infrastructure failures with evidence of poor model quality.
- **Validation to demonstrate:** assessment off leaves ordinary dispatch unchanged; tier, capability, exclusion and independence checks still apply under the chosen rule; a failed candidate falls back without consuming the recipe's attempt budget, including when its limit is one; no fallback is silently substituted inside an attempt; pending or failed reviews cannot produce a premature promotion; repeated intake does not duplicate evidence; concurrent runs cannot reserve the same budget; promotion, demotion and owner overrides are visible; changed identities cannot inherit trust accidentally.

- **Refined against the code (2026-11-20, Decision 0182):** settings are `assessment:` in the machine's `preferences.yaml` (a project's is ignored); evidence is `models:` in the track record keyed by route (`assessment.route_key`), the last-check `profiles:` section kept as it was (`capability_check.save_section` writes one section and keeps the other); a trial is chosen when the attempt starts, inside `Api._dispatch`, so a queued write dispatch is judged when it starts; one trial per step in a run, so the fallback is simply the Director's next dispatch; the fallback reuses `step_ready {not_counted}` (as `capability_absent` does); evidence is recorded in `Api._after` from the new events, so every path (supervisor, `submit`, `decide`) records once; the estimate needs no packet: the route's context (at most 200,000 tokens) four times at the input price plus 16,000 output tokens. Shipped recipes: `recipe-builder@9` and `software-feature@2`; `2026-11-ai-delegates` now plans `recipe-builder@10`.

### Slice 4: shadow attempts on strong steps

- **Outcome:** a candidate shadows strong steps within budget, graded but never used, and can earn a strong record.
- **Criteria:** candidate choice; shadow dispatch with the same packet; gates only; never used or counted; read and none steps only; budget; the track record and promotion.
- **Effort:** L
- **Refined (2026-11-19, Decision 0179):** Items 4–6 govern budget reservations, evidence identity and gates safe to repeat. Define how the candidate receives the same task inputs while its dispatch retains its own identity: today's packet hash includes the worker profile and route-dependent tools. Specify how shadow grading depends on the primary worker's outcome (0176 item 4), including when either completes first or the primary fails.
- **Validation to demonstrate:** no shadow result becomes `step_passed`, publishes a deliverable, supplies a dependent input or spends a primary attempt; write steps never shadow; candidate and primary completion order cannot alter the grade; gate evaluation cannot change the live project; shadow timeout or crash leaves the primary outcome intact; budget and identity rules hold across concurrent runs and restart.

## Log

### Remaining routing decisions accepted, 2026-11-19

- **Owner decision:** "for now, agree with all" — all six suggested answers accepted as Decision 0179.
- **Summary:** Set 0179 to accepted, record its date and the owner's words, remove rejected alternatives from its rules, and update the proposal and register. Write each approved rule into the relevant design sections, explicitly marked as awaiting slices 3 and 4. The budget is an estimate reservation limit, with possible provider overrun, rather than a guaranteed spending ceiling.
- **Manual:** No runtime, command, configuration parser or page changed; implementation slices must supply the manual and authoring guidance for the new declarations and settings.
- **Validation:** The required quick gate selected the documentation suite: all 258 tests passed. The register was reconciled against every change doc by the documentation checks; `git diff --check` passed.
- **Accepted:** Yes, for now. Slices 3 and 4 remain unimplemented.

### Remaining proposal refined, 2026-11-19

- **Summary:** Reviewed the approved remaining slices against `routing.py`, `models.py`, `engine.py`, `packet.py` and the delivered capability-check record. Recorded six questions, each with a suggestion and rationale, as proposed Decision 0179 and put them to the owner together. Added concrete validation requirements for trials and shadows. Reconciled the Design's descriptions of delivered checks and evaluation evidence with slices 1 and 2 and Decisions 0177 and 0178.
- **Manual:** No user-visible implementation changed in this proposal refinement; the remaining slices retain their manual obligations above.
- **Baseline:** HEAD's recorded full run was lost. A fresh full suite outside the sandbox passed: 2277 passed, 9 skipped. The sandboxed run was stopped after network restrictions and widespread failures; no tests were deselected.
- **Validation:** Documentation checks passed (258 tests); the required quick gate passed (1808 passed, 3 skipped). The ledger now also reports the prior slice's exact SHA green.
- **Accepted:** Pending the owner's answers to 0179. Request and Design approval of 2026-11-18 remains recorded; suggestions in 0179 are not owner decisions.

### Proposal drafted

- **Summary:** Written from the owner's direction of 2026-11-18 (Decision 0175), after F-6 of `2026-11-first-use-feedback-batch-a`. Checked against Baton at `6209125`: the shipped data's 29 judged models and its research reports. No code changed.
- **Owner decision:** 2026-11-18, "Concur checks once from setup and amending 0110. ... I want to start with 2 for the high stakes (i.e, strong) steps and 3 for the low stakes steps."
- **Accepted:** No; proposal only. Eight open questions await the owner.

### Request and Design accepted

- **Summary:** The owner concurred with all nine suggested answers (the ninth, on the concept budget, added this session under §0 rule 8) and approved the Request and Design. Recorded as Decision 0176; criteria 3 and 8 now cite it. No code changed.
- **Owner decision:** 2026-11-18, "Concur on all."
- **Accepted:** Yes.

### Slice 1: capability checks, once, from the page

- **Summary:** The check set (`defaults/capability-checks.yaml`, version 1: 17 tasks over five capabilities, eight graders) and `capability_check.py` (load and validate the set, plan who is due, estimate from list prices, run each task as a packet through the profile's adapter, six at a time, grade by code, record states and the track record). Capability states gain `by: check` with `set_version`, kept fresh on each check and reset with the harness version like observed ones. The API runner wraps its completion in a meter and writes `usage.json` (calls, tokens, LiteLLM's cost, seconds). `workers setup` adds check-proven `structured_output`/`tool_use` to unjudged listing profiles; `workers status` and the page rows show the last check. `baton workers check` shows the estimate and runs on confirmation or `--yes`; the page's **Check abilities** (per row, and for the models shown) asks with the estimate first, through `POST /api/models/check`.
- **Owner decisions:** 2026-11-18, "A." and "B. as suggested but also record response time." (Decision 0177).
- **Modules:** `capability_check.py` (new), `capability_states.py`, `worker_runner.py`, `resources.py`, `cli.py`, `ui.py`, `ui/app.js`; `defaults/capability-checks.yaml` (new).
- **Docs:** `design/workers.md` §6.1 (`by: check`), §6.3 (usage record), §6.4 (capability checks, the track record); `design/director-interface.md` §13.1 (`workers check`, Director guidance, mirrored in `skills/baton-director/SKILL.md`), §13.9 (the route, the state row); `principles.md` §2 (no new concept, 0176 item 9); Decision 0177.
- **Tests:** `tests/test_capability_check.py` (the shipped set is valid, covers five capabilities without vision and each task passes its own right answer; invalid sets refused; every grader; estimate before running and nothing run unasked; pass, fail and could-not-run each recorded correctly, with cost and time; skip when checked, again with `--again`, a new set version or an alias route; an unjudged model gains `tool_use` through setup and a failed one does not; the owner's `absent` is not argued with; filters; status and page rows; the command and the page route; the runner's meter; a check state across a schema pass and a harness upgrade; the packet the adapters read). `tests/test_api_worker.py`: one task through the real runner child against a local OpenAI-compatible server, graded and with its usage recorded.
- **Accepted:** Yes (slice).

### Slice 1, repaired after real use

- **Summary:** The owner asked for checks on a few OpenRouter models (2026-11-18). Six were checked: Nemotron 3.5 Super VL (free) verified `structured_output`, `tool_use`, `workspace_read`; gpt-oss-120b verified `tool_use`, `workspace_read`, `technical_reasoning` ($0.0020, 74 s); DeepSeek V3.2 verified `structured_output` and `tool_use` and failed `wr-function` (it read a path that was not a file and gave up), so `workspace_read` is absent ($0.0052, 124 s); ERNIE 5.5 Flash (free) verified two capabilities. Gemma 4 31B and LFM 3.1 (free) were rate-limited upstream on almost every task, because six tasks of one model ran at once. Fixed: one model's tasks now run one after another (six models at a time), a rate-limited task waits and is tried twice more, and a route still limited stops for this check instead of failing every task. The runner's `read_file` refusal for a path that is not a file now says whether it is a folder or nothing, and to use `list_files`, which helps real steps too.
- **Rerun with the fix:** ERNIE 5.5 Flash completed every task, verifying `structured_output` and `workspace_read`, but failed `tu-find` (it reported `failed`) after passing all tool tasks in the first run, so `tool_use` is now absent: one run is noisy, and the one-failure rule (0176, item 2 and criterion 3) turns a single bad answer into `absent`. Reported to the owner, not changed. Gemma 4 31B and LFM 3.1 stayed rate-limited upstream: the check stopped after its retries, recorded nothing, and they stay due.
- **Modules:** `capability_check.py` (`_run_profile`, `RATE_WAIT_S`, `RATE_RETRIES`), `runner_tools.py`.
- **Docs:** `design/workers.md` §6.4.
- **Tests:** `tests/test_capability_check.py`: a rate-limited route waits, retries and then stops without running its remaining tasks.

### Slice 2: tiers from published evaluations

- **Summary:** Research (2026-11-18) read the Artificial Analysis leaderboard and methodology (Intelligence Index v5.0.1, nine evaluations it runs itself), the LMArena text leaderboard (human preference votes, dated 2026-11-18) and OpenRouter's usage rankings. The owner chose the index to decide tiers at 50 and 25, LMArena as support, `technical_reasoning` granted at standard, and a second try for a failed check task (Decision 0178). The format gains `tier_basis` and the `evaluation` capability basis (still `baton-known-workers/1`); `defaults/evaluation-tiers.yaml` is the mapping, and the one validator enforces it for the shipped data, the overlay and assessments. The shipped data was refreshed: 12 existing models gained an evaluation basis, five of them with a new tier (Sonnet 5.5 and GPT-6.1 Terra up to `strong`, Haiku 5.5 and GPT-6 Luna up to `standard` with `technical_reasoning`, gpt-oss-120b and DeepSeek V4 Pro down to `basic`); Fable 5.1 keeps a judgment basis (no published index result) with LMArena support; 19 models were added, keyed by their OpenRouter canonical slug, among them Fable 5.2 (65, strong), GPT-6.2 Astra and Sol, Gemini 4 Neon, Carbon and Hydrogen (strong), Kimi K3.1 Pro, Qwen4 Max, Grok 4.7, Hy4, GLM 5.3 and 5.3 Flash, MiMo V2.6 Pro and Flash, Step 5 Preview, MiniMax M3.1 Flash (standard), and MiniMax M3, Nemotron 3.5 Super VL and Lightning (basic). The research and assessment recipes get the mapping as `evaluations` and are at version 2. The setup page offers **Rate … from published evaluations** for unrated listed models, through `POST /api/models/assess`. A failed check task now runs once more (0178, item 4).
- **Not done:** Hy4 Flash (the second most used model this week) has no index result, so it stays unrated. Fable 5.2 has no Claude Code subscription route yet: its CLI model id was not researched, so the subscription keeps using Fable 5.1, and Fable 5.2 is reached through OpenRouter. Models whose index entry names a different version from the data (GPT-6 Astra, GPT-6.1 Sol, Kimi K3, GLM 5, Grok 4.20, Qwen 3.8 Max, Command A+) were left as they were rather than matched by guess.
- **Owner decisions:** 2026-11-19, "Concur on the suggestions" (Decision 0178).
- **Also fixed:** `workers status` read the track record once per profile (391 times on the owner's machine); it now reads it once, and an unreadable record is a diagnostic (`capability_check.record_invalid`). The page's state loads the model data once instead of three times, and `known_workers` keeps the parsed file while its size and modification time are unchanged (handing out copies): the refreshed file is larger, and parsing it four times made `/api/state` take 0.35 s, slow enough under a parallel test run to trip a page test's idle timer; it now takes 0.09 s.
- **Modules:** `known_workers.py` (`EvaluationResult`, `TierBasis`, `EvaluationTiers`, the validation), `assess.py`, `capability_check.py`, `ui.py`, `ui/app.js`, `resources.py`; `defaults/evaluation-tiers.yaml` (new), `defaults/known-workers.yaml`, `defaults/capability-checks.yaml` (comment); `tools/worker-research` (both recipes, the research CLI).
- **Docs:** `design/workers.md` §6.4; `design/recipes.md` §5.6; `design/director-interface.md` §13.9; Decision 0178.
- **Tests:** `tests/test_evaluation_tiers.py` (the mapping; thresholds at 50 and 25; the lower median; supporting results never decide; unknown evaluations and versions refused; judgment needs a reason; `technical_reasoning` granted only at standard and never `long_form_writing`; an overlay tiered from results, and refused at another tier; the refreshed shipped data; the page's rating action and its state). `tests/test_capability_check.py`: a failed task runs once more and only a second failure counts. `tests/test_assess.py`: the mapping reaches the assessment packet.
- **Accepted:** Yes (slice).

### Slice 3: track record and trial routing

- **Owner decisions:** 2026-11-20, four questions put while refining slices 3 and 4, after the owner asked what proven and put back mean ("put back still eligible at 'that tier'? ... does user have to be proactive in looking for demoted/excluded models"): "Own gates; forgive shared failure", "One tier lower", "$0 = free models only", "Declare where clear" (Decision 0182).
- **Summary:** `assessment.py` (new): evidence identity (`route_key`: model, adapter, provider, invocation, endpoint; aliases none), the track record's `models:` section (outcomes with ids, totals by tier and kind, the harness version and rating, owner overrides), standing (proven 5/none of last 5 failed; put back 2 of last 5; void under a new rating; reset by a new harness version), the owner's `set_standing`, trial eligibility (`trial_problems`) and candidate choice (`trial_candidate`: eligible, unproven, not put back, not an alias or the same route, free or cheaper, within budget), the conservative estimate and the budget (`reserve`, `reconcile`, `release` under `.assessment-spend.lock`). Routing excludes a put-back model at its tier and above, with the command that promotes it. The engine chooses a trial when an attempt starts (the candidate recorded in `worker_selected` with `trial`, `fallback`, `tier`, `estimate_usd`; the dispatch result's `trial` message), turns a trial's failure (rejected result, failed gate, review rejection, timeout, worker `failed`, orphan) into `trial_failed` and a `step_ready` that does not spend the budget, and records outcomes from new events in `_after`, with `model_standing_changed` and a notice when standing changes. `Step` gains `effect` and `repeatable` (the loader refuses `repeatable` on a write step or without `effect: none`); `Preferences` gains machine-only `assessment`. CLI: `workers assessment`, `workers standing`; `workers status` shows each track record, the settings, today's budget and the models put back. Page: the switches, the daily limit and today's amount, the record under **Tier**, **Promote at …** and a **put back** filter (`PUT /api/assessment`, `POST /api/models/<profile>/standing`). Shipped recipes: `recipe-builder@9` and `software-feature@2` declare effects (and `repeatable` for shadows); `generate`'s prompt asks for them in the recipes it writes; `@8` frozen as a fixture.
- **Modules:** `assessment.py` (new), `engine.py`, `routing.py`, `models.py`, `prefs.py`, `capability_check.py`, `resources.py`, `recipe.py`, `cli.py`, `ui.py`, `ui/app.js`; `formats/baton-recipe-1.schema.json` (regenerated); `examples/recipes/recipe-builder` (@9), `examples/recipes/software-feature` (@2); `skills/baton-director/SKILL.md`.
- **Docs:** `design/workers.md` §6.4 (the track record, standing); `design/runtime.md` §8.2 (assessment events), §8.4 (trials, put back), §8.7 (trial dispatch and its budget), §8.10 (a trial's intake); `design/recipes.md` §5.1 (`effect`, `repeatable`), §5.7 (recipe-builder@9, software-feature@2); `design/director-interface.md` §13.1 (the commands), §13.3 (telling the owner about trials), §13.9 (the page); `design/platform-and-security.md` §15.2; `design/layouts.md` §4.4; Decision 0182; `2026-11-ai-delegates` plans `recipe-builder@10`.
- **Tests:** `tests/test_trials.py`: identity and aliases; proven and put back thresholds per tier; intake seen twice records once; real steps do not decide standing; uncounted outcomes; a new rating or harness version starts afresh; owner promote, put back and clear, and evidence after a promotion; both sections share one file; routing treats put back as one tier lower and proven changes nothing; which steps qualify; candidate rules (off by default, one per step, free or cheaper, $0 free only, a price needed, aliases excluded, proven and put back excluded); concurrent reservations cannot claim the same credit, reconciled once; the estimate; machine-level settings; and through the engine without processes: a failed trial falls back without spending an attempt budget of one, identity recorded as any dispatch, the fallback an ordinary attempt; with assessment off nothing changes; a passed trial counts; a trial waiting on its review is not a pass; a put back is announced and then routed one tier lower; status lists records and put-back models. `tests/test_ui_models.py`: the page's settings, refusals and the commands. `tests/test_recipe_builder.py`: @9's effects and the frozen @8. `tests/test_adoption.py` and `tests/test_recipe_broken.py` follow `software-feature@2`; `tests/test_recipe_builder_runs.py` follows `recipe-builder@9`.
- **Validation:** the quick gate passed (1846 passed, 3 skipped).
- **Repaired:** the full suite on `a7960c1` was red: `workers status` (text) read the last generated profile's record outside its loop and failed when a project profile had capability states (`test_capability_states.py`). Fixed in `cli.py`, which also lists a listing profile that has a track record; `test_ui_models.py` now runs `workers status` with a put-back model.
- **Accepted:** Yes (slice).
