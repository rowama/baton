---
id: 2026-11-first-use-feedback-batch-a
title: "Fixes and tweaks from the owner's first real use of Baton; the first batch"
status: done
level: standard
decisions: ["0161", "0045", "0042", "0174", "0110", "0124", "0114", "0115", "0181"]
touches: [design/workers.md, design/director-interface.md, design/runtime.md, design/recipes.md, design/packets.md]
manual: [user/answer-questions-and-decide.md, admin/project-settings.md, admin/director-commands.md, admin/troubleshooting.md, reference/project-settings.md, reference/commands.md, reference-notes.yaml, anchors.yaml, user/choose-models.md, admin/accounts-and-costs.md, admin/machine-settings.md]
---

# Fixes and tweaks from the owner's first real use of Baton; the first batch

## Request

### Problem

The owner has started using Baton for real, beginning with a recipe-builder run in `D:\rob\projects\baton-recipes` (run `r_20261119_8c96`, 2026-11-18, with Codex and then Grok Bot as Director). This change is the first batch of what that use shows needs fixing or adjusting: items F-1 to F-8, one per finding. Each item records what happened, the evidence, and the proposed fix. Later feedback goes into a later batch; when an item grows large enough to need its own design, it moves to its own change and this doc links to it.

### Feedback items

**F-1. The Director reused the owner's opening instruction as the owner's words.** The owner's first message was "Become the baton director. Vendor the recipe-builder, then run it using the files in reference directory as inputs". The Director recorded that sentence verbatim as the owner's note on eight decisions (vendoring recipe-builder@7, attesting six files, binding them to `context`) without confirming back, and used it as the run's `idea` input, which recipe-builder treats as the owner's description of the process. Evidence: the project log and the run's `run_started` inputs in `baton-recipes`. The runtime requires words but, by design, leaves it to the skill that they are a real confirmation (§13.8).

**F-2. Person steps have no worker unless the owner writes a profile by hand.** `doctor` warned that no healthy profile can do recipe-builder's `example_plan` and `accept`. Both require only `human_judgment`, which only a `manual` profile for a person has. `workers setup` generates profiles for model routes only, so a person's profile must be written in `~/.baton/workers.yaml`, which the owner has ruled out ("hand-writing worker profiles is never an option"). Without one, a run escalates at its first person step (`no_eligible_worker`). The Director (Grok Bot) told the owner the warning was misleading and that nothing was missing "by design".

**F-3. The Director should ask who does the person steps, with the owner as the default.** The owner's words: "director needs to ask if the user it's talking to is the one who [will] be doing the human steps with yes/owner being the default since the user running the process is by previous decision the owner of the process." By Decision [0161](../decisions/0161-ai-delegates.md), item 6, the person who starts a run is its owner; this is the natural default for who does its person steps, and the question lets the owner name someone else.

**F-4. A Director dismissed a real warning as intended behaviour.** Related to F-2, but about the Director: it characterised a Baton check as wrong without checking what the check tests. The owner: "Director doesn't need to raise concerns that are not real, but especially not by design." A Director should neither invent concerns nor explain real ones away.

**F-5. Nothing tells a Director to vendor a shipped recipe the owner names.** `baton init` vendors only `fit-check` (Decision 0043); other shipped recipes are vendored when chosen. The Director skill says how to vendor `quick-run` by name, and covers recipe-builder only inside adoption, but has no general line: when the owner names a shipped recipe that is not vendored, confirm, `vendor <id> --note "<owner's words>"`, then start it.

**F-6. Routing kept choosing the most expensive model.** For recipe-builder's profile step (run `r_20261119_ee96` in `baton-recipes`), the Director dispatched `openrouter-main-claude-fable-5-1`, which failed for lack of OpenRouter credit, and offered Fable again as the retry; Opus 5.5 through the owner's Claude Code subscription, at no extra cost, came second. The run's `worker_selected` record shows why the choice was so narrow and why Fable led it:
- Every AI step of recipe-builder@7 requires `tier: strong`. 386 of the machine's profiles were excluded for the profile step, among them Sonnet 5.5 and Codex `gpt-6-1-sol` and `gpt-6-1-terra` ("needs tier strong; profile is standard").
- Almost every OpenRouter model, including GPT-5.x, Gemini 3.x and 4 and Grok 4.x, was excluded as unjudged: tier `basic` and only catalog capabilities (Decision [0110](../decisions/0110-unjudged-model-default-tier.md)). Of 374 listed models only a few judged ones reach `strong`.
- With no preferences, eligible profiles are ordered by verified capabilities, then by name (§8.4); `cheapest_first` is off by default. "fable" sorts before "opus". An API profile counts the runner's `workspace_read` as verified, which probably ranked it above the Claude Code profile (inferred: the record keeps the exclusions, not the order of the eligible).
- The Director took the first eligible worker and did not say what each option would cost.

**F-7. The owner's answers do not reach the next round of a design-and-review loop.** In recipe-builder's `shape` group, the owner answered three design questions; the design's second attempt received them (`i1/design` attempt 2: `prior_feedback.answers`, 3 entries). The independent review then failed the design and a second round began. Its design step (`i2/design` attempt 1) received the review's findings (`open_findings.json`) but none of the owner's answers, so it asked again, with new option sets that no longer contained the owner's earlier choices (run `r_20261119_ee96`, 2026-11-20). Answers are given only to the next attempt of the step that asked (§13.8), and a new round's step is a new step.

**F-8. Accepting a worker's suggestions keeps the word "accept", not the suggestions.** Recipe-builder's research step (attempt 4) suggested adopt, adapt or reject for every row of the sources-and-lessons ledger, in its own output (`comparison.recommendation`), and asked the owner to accept them. The owner chose "Accept all as suggested"; the recorded answer is `q1_rows: accept`. The retry (attempt 5) received the answers and the question's text but not attempt 4's output, so the row-by-row suggestions never reached it or the design, which rebuilt them from a summary and labelled them confirmed (review findings F17 and F20). A blocked attempt's output is not given to the attempt that follows its answers.

### Acceptance criteria

1. **F-1.** Before `start`, `vendor`, `attest` or `bind`, the Director restates what it will record in the owner's terms and records only the owner's confirming words. It never reuses an instruction to the Director as the owner's confirmation, and never puts an instruction to the Director in a run input; a run's `idea` is the process in the owner's words, confirmed back.
2. **F-2.** Every machine has a profile for the owner as a person, without the owner writing one: `manual` adapter, identity `human/owner`, `human_judgment` and the capabilities a person brings. An owner's own profile of that name replaces it. `doctor` no longer reports person steps as uncovered while it exists, and if no person's profile exists says so plainly with the fix.
3. **F-3.** When a run reaches its first person's step, or at `start` if the recipe has any, the Director asks, once, whether the person it is talking to will do them, with yes as the default. If yes, the owner's profile does them. If someone else will, the Director records who, and their steps are routed to a person's profile for them, created without the owner writing it. The answer is kept so the question is not repeated.
4. **F-4.** The Director skill says: report a `doctor`, `check` or `status` warning as Baton states it; if it seems wrong, read what the check tests (`help`, the manual) before saying so, and never call a warning intended behaviour without that.
5. **F-5.** The Director skill says how to vendor a shipped recipe the owner names, with their confirming words.
6. **F-6.**
   - Routing is cost-aware by default: a route the owner already pays for (a subscription CLI with quota left) comes before a pay-per-token route, and among the rest the cheaper first; price, not the profile's name, breaks ties.
   - recipe-builder asks for `strong` only on steps that need it; steps that assemble or transcribe take `standard`.
   - Unjudged models can be lifted without the owner writing anything: the common ones judged in the shipped data, or a cheap check on request (see open question 5). *Handed over to `2026-11-model-assessment` (0175); the owner, 2026-11-20: "I'll finish the model-assessments later incl criterion 6."*
   - When the Director offers a choice of worker, it says what each costs (included in a subscription, or roughly how much credit), and never offers a pay-per-token route ahead of a paid-for one without saying why.
7. **F-7.** Answers the owner gives to any step of a group's iteration reach the same step in every later iteration, and the reviews of that step, until the owner changes them (0181). A worker may ask again only about something the earlier answers do not cover, and must say what changed.
8. **F-8.** When a step is retried after the owner answers its questions, the retry receives the blocked attempt's output as well as the answers. An answer that accepts something the worker proposed records what was accepted (the proposal, or a reference to it by content hash), so the decision stands on its own in the record.
9. **Manual and design are current.**

### Open questions

None open. Questions 6 to 8, and the tiers of recipe-builder's steps, were answered by the owner on 2026-11-20 as suggested, and are recorded in Decision [0181](../decisions/0181-first-use-feedback-routing-and-answers.md). The four questions on F-2 and F-3 were answered by the owner on 2026-11-18 as suggested, and are recorded in Decision [0174](../decisions/0174-first-use-feedback-people.md):

1. Who does the person steps is asked at `start` when the recipe has person steps, and kept for the project in project policy (`policy.people: {person_steps: owner | <name>}`); the owner can change it with their words.
2. A person the owner names does person steps only; the run's owner keeps every owner decision.
3. The owner's profile: `human_judgment`, `long_form_writing`, `vision`, `file_write`, tier `strong`.
4. It is built in, present on every machine and shown by `workers status`, replaced by an owner's own profile of that name.

5. **F-6: how are unjudged models lifted?** *Answered (2026-11-18, Decision [0175](../decisions/0175-model-assessment.md)):* moved to its own change. *Suggested at the time:* both: the shipped data judges the models most used through OpenRouter, and the owner may ask for an assessment of chosen models (Decision 0111) or a small set of capability checks: now [2026-11-model-assessment](2026-11-model-assessment.md) (Decision 0175). *Rationale:* shipped judgments help every owner at no cost; checks cover the long tail when an owner wants a particular cheap model.
6. **F-6: how is a subscription route priced?** *Answered (0181):* cost-aware ordering is the default. *Suggested:* as "included" while its quota lasts, ranking before any priced route under cost-aware ordering; exhausted quota already re-routes (Decision 0114). Checked against the code (2026-11-20): harness routes (`claude_code`, `codex`) carry no `price` in the shipped data, and `routing.price_rank` ranks an unpriced route after every priced one, so turning on `cheapest_first` today would push work off a subscription.
7. **F-7: where do carried answers go?** *Answered (0181):* as suggested, and the reviews of that step receive them too; no recipe declaration (`prior_feedback.answers_earlier`). *Suggested:* the runtime keeps a run's confirmed answers, keyed by the step that asked and its question ids, and gives every later attempt of that step, in any iteration, all of them (`prior_feedback.answers` gains `earlier: [...]` with the iteration each came from). *Rationale:* the owner's word should not depend on which round a step is in; keying by question id lets a worker see what is settled.
8. **F-8: whole output, or only what was accepted?** *Answered (0181):* as suggested. *Suggested:* the retry receives the blocked attempt's whole output (`prior_output`), and an answer's record carries the content hash of the output it accepted. *Rationale:* the worker often needs its own earlier work, not just the accepted part; the hash makes the decision verifiable without copying the content into the event.

9. **F-6: which of recipe-builder's steps need `strong`?** *Answered (0181):* `guide`, `generate`, `examples` and the programs' `implement` take `standard`; `profile`, `research`, `design`, `audit` and the programs' `review` stay `strong`.

## Design

### Doc edits

- `design/workers.md` §6.1: the built-in owner profile and profiles for other people (F-2, F-3); §6.4: what `workers status` shows.
- `design/director-interface.md` §13.3: the skill lines for F-1, F-3, F-4 and F-5; §13.4: `doctor` on person steps; §13.7: `policy.people` (F-3).
- `design/runtime.md` §8.4: routing person steps to the recorded person (F-3); cost-aware ordering by default (F-6).
- `design/workers.md` §6.4: lifting unjudged models (F-6): moved to `2026-11-model-assessment` (Decision 0175); not edited here.
- `design/recipes.md` §5.7: recipe-builder's tiers per step (F-6).
- `design/packets.md` §7.1, §7.2 and `design/director-interface.md` §13.8: answers that last and the blocked output (F-7, F-8).

### Manual edits

- Slice 2: `user/answer-questions-and-decide.md` gains **Parts of the work for a person** (`#person-steps`): the question asked once, yes by default, someone else named instead, the answer kept, decisions staying the owner's; its *Confirming before anything is recorded* says a request to the assistant is not a confirmation (F-1). `admin/project-settings.md` documents `policy.people.person_steps`, the built-in `owner` profile and `person-<name>`. `admin/director-commands.md`: `policy set --person-steps`. `admin/troubleshooting.md`: the new `doctor` warning for a person's step. `reference/project-settings.md` (generated; optional blocks such as `policy.people` are now listed key by key, its note in `reference-notes.yaml`) and `reference/commands.md` regenerated. `anchors.yaml` updated.
- Slice 3: `user/choose-models.md` says routing is by cost unless turned off (subscriptions first, then free, then cheapest), and that the assistant says what each choice costs; `admin/accounts-and-costs.md` and `admin/machine-settings.md` give the default order and `--verified-first`.
- Slice 4: `user/answer-questions-and-decide.md` (*Confirming before anything is recorded*) says an answer stays answered for the rest of the work, reaches a part done again and its check, and that accepted suggestions are kept with the answer.

### Decisions

- [0161](../decisions/0161-ai-delegates.md) (accepted), item 6: the person who starts a run is its owner.
- [0045](../decisions/0045-sme-never-a-person.md) (accepted): an expert consulted by subject is never a person; unchanged.
- [0042](../decisions/0042-vendoring-on-selection.md) (accepted): shipped recipes are vendored when chosen.
- [0174](../decisions/0174-first-use-feedback-people.md) (accepted): who does person steps, and the built-in owner profile (F-2, F-3).
- [0110](../decisions/0110-unjudged-model-default-tier.md) (accepted): unjudged models default to tier `basic` (F-6).
- [0124](../decisions/0124-machine-level-preferences.md) (accepted): routing preferences (F-6).
- [0114](../decisions/0114-quota-exhausted-reroutes.md) (accepted): an exhausted quota excludes a route until it resets (F-6).
- [0115](../decisions/0115-price-is-not-a-concept.md) (accepted): price is a fact on a profile; `cheapest_first` (F-6).
- [0181](../decisions/0181-first-use-feedback-routing-and-answers.md) (accepted): cost-aware ordering by default, answers across rounds, the blocked output to its retry, recipe-builder's tiers (F-6 to F-8).

## Plan

Slices as proposed; each item may become its own slice, and items that grow move to their own change.

### Slice 1: the Director skill (F-1, F-4, F-5)

- **Outcome:** a Director confirms back before recording, writes run inputs in the owner's words, reports warnings as stated, and vendors a named shipped recipe properly.
- **Criteria:** the skill lines; the Director's live test (§17) checks a transcript for each.
- **Effort:** S

### Slice 2: who does the person steps (F-2, F-3)

- **Outcome:** a run's person steps go to the owner by default, or to the person the owner names, with no profile written by hand.
- **Criteria:**
  - the built-in owner profile, replaceable by the owner's own;
  - a person's profile for someone the owner names, created from the answer;
  - `doctor` on person steps with and without a person's profile;
  - the question asked once, kept, and changeable;
  - routing to the recorded person;
  - the manual.
- **Effort:** M

### Slice 3: cost-aware routing (F-6)

- **Outcome:** a step goes to a route the owner already pays for before a pay-per-token one, the Director says what each choice costs, and recipe-builder asks for the top tier only where it matters.
- **Criteria:** default ordering with included, priced and unpriced routes; price as tie-breaker; recipe-builder's tiers per step with its scenario tests passing; the Director skill; a scenario reproducing the run of 2026-11-18 that picks the Claude Code route.
- **Effort:** M

### Slice 4: answers that last (F-7, F-8)

- **Outcome:** the owner never answers the same question twice in a run, and an accepted proposal is kept with the decision.
- **Criteria:** answers reach every later iteration of the step that asked; a blocked attempt's output reaches its retry; the accepted output's hash in the answer's record; a scenario reproducing the recipe-builder run of 2026-11-20 in which round two asks nothing already answered.
- **Effort:** M

## Log

### Started

- **Summary:** Opened to collect the owner's feedback from first real use, with five items from the recipe-builder run in `baton-recipes` on 2026-11-18. F-1 and F-2 were checked against that project's records and Baton at `6209125`. No code changed.
- **Owner decision:** 2026-11-18, "can you start a change proposal that catches all of my initial use feedback."
- **Accepted:** No; proposal only.

### Open questions answered

- **Summary:** The four questions on F-2 and F-3 were answered as suggested and recorded as Decision 0174. No code changed.
- **Owner decision:** 2026-11-18, "Concur with your suggested answers." (0174).
- **Accepted:** No; proposal only.

### F-6 added

- **Summary:** Added F-6 (routing kept choosing the most expensive model), from the run record of `r_20261119_ee96`, with criteria, two open questions and slice 3. No code changed.
- **Owner decision:** 2026-11-18, "Yes, add F-6."
- **Accepted:** No; proposal only. Open questions 5 and 6 await the owner.

### F-7 and F-8 added

- **Summary:** Added F-7 (answers do not reach the next round of a design-and-review loop) and F-8 (accepting a worker's suggestions keeps only "accept"), both checked against the packets and records of `r_20261119_ee96` in `baton-recipes`. Criteria, two open questions and a slice added. No code changed.
- **Owner decision:** 2026-11-19, "Add both".
- **Accepted:** No; proposal only. Open questions 5 to 8 await the owner.

### Open questions on F-6 to F-8 answered

- **Summary:** The owner renamed the change to the first batch (F-1 to F-8); the doc, the register and the references in other docs were made consistent. Q6's `[VERIFY]` was checked against the code: harness routes carry no price and rank last under `cheapest_first`. Questions 6 to 8 and recipe-builder's tiers per step were put to the owner with suggested answers and recorded as Decision 0181. Status set to in-progress. No code changed.
- **Owner decision:** 2026-11-20, "Work on this first batch of issues"; chose each suggested answer (0181).
- **Accepted:** Request accepted for work; slices follow.

### Slice 1: the Director skill (F-1, F-4, F-5)

- **Commit:** `2026-11-first-use-feedback-batch-a: Slice 1, the Director skill`
- **Summary:** `skills/baton-director/SKILL.md` and its copy in §13.3 gain three lines: a hard rule that an instruction to the Director is not the owner's confirmation and never a run input (F-1); session item 4a, vendoring a shipped recipe the owner names after confirming back (F-5); and under *Questions*, reporting a `doctor`, `check` or `status` warning as stated and reading what the check tests before calling it wrong (F-4). `tests/test_director_surface.py` checks the lines. The live Director scenario is `tests/test_live_director_confirms.py` (opt-in, `BATON_LIVE=1`, about four Claude Code turns on the owner's subscription): the owner opens with an instruction to the Director, and the record must show recipe-builder vendored after the first turn with a note that is not the instruction, and a run `idea` that is the owner's description (F-1, F-5). F-4 is left to the owner's reading of the saved transcript and to the skill test. The live test has not been run yet.
- **Manual:** none: the skill is the Director's, not the owner's.
- **Accepted:** Yes, 2026-11-20 ("I accept these 4 slices."); the live scenario was not run.

### Slice 2: who does the person steps (F-2, F-3)

- **Commit:** `2026-11-first-use-feedback-batch-a: Slice 2, who does the person steps`
- **Summary:** Built-in profiles for people (`Project.people_profiles`): `owner` on every machine, and `person-<slug>` for a person the project policy names, both under every other profile source so a profile of the same name replaces one (`WorkerProfile.builtin_person`). They take only steps for a person (`routing.is_person_step`: requires `human_judgment`) and are not listed for any other step. Project policy gains `people.person_steps` (`PeopleConfig`), absent until set so older policies keep their hash; `policy set --person-steps` (CLI, MCP, API; `yes`/`me` record `owner`). Routing sends a person's step only to the named person, reading the policy in force at routing time. `start` (and `start --from-plan`) returns `people {steps, default, ask, next}` while unanswered. `doctor` no longer counts a person's profile as an AI helper, and says plainly when a replaced `owner` profile cannot do a person's step. `workers status` shows `people.owner {builtin}`. The Director skill asks once, yes by default. The settings reference generator now lists the keys of an optional block.
- **Tests:** `tests/test_person_steps.py` (the built-in profile and its replacement; person steps only; doctor coverage, the plain message and no setup offer suppressed; the question at start asked once and kept; a named person's profile and routing, and changing back; the policy value, file and hash; refusal of an empty name; the CLI option; `workers status`; the skill line). Existing routing and onboarding tests pass unchanged: a built-in profile is not listed for AI steps.
- **Design:** §6.1 (built-in profiles for people), §8.4 (person steps routed to the named person), §13.1 (`start`'s `people`, `policy_set`'s `person_steps`), §13.3 (skill), §13.4 (doctor), §13.7 (`policy.people`).
- **Review:** clean.
- **Accepted:** Yes, 2026-11-20 ("I accept these 4 slices.").

### Slice 3: cost-aware routing (F-6)

- **Commit:** `2026-11-first-use-feedback-batch-a: Slice 3, cost-aware routing`
- **Summary:** `Preferences.cheapest_first` now defaults to true, and `routing.price_rank` ranks an included route first (`routing.included`: a harness CLI on `cli_login`; an exhausted quota is already excluded), then free, then priced cheapest first, then unpriced, verified-first and name breaking ties; `cheapest_first: false` (`--verified-first`) keeps the old order, and only that opt-out is written to a preferences file. Every eligible entry carries `cost` (`routing.cost_label`) and a reason line with it. The Director skill says what each choice costs and never offers a per-use route ahead of an included one without saying why. `recipe-builder@8`: `guide`, `generate`, `examples` and `build_programs/implement` take `standard`; `@7` is frozen in `tests/fixtures/recipes/recipe-builder-v7`. The setup page's toggle reads "by cost". `2026-11-ai-delegates` now plans `recipe-builder@9`, by landing order (Decision 0173).
- **Tests:** `tests/test_listings.py` (default and opt-out orders; an included subscription first with each `cost`; an exhausted one left out; the run of 2026-11-18 reproduced with the old order choosing Fable over OpenRouter and the new one choosing Opus through Claude Code; the skill line). `tests/test_recipe_builder.py` (the tiers per step, generate's package review still strong, the frozen `@7`). Builder run and page tests updated for `@8` and the new default.
- **Design:** §5.7 (recipe-builder's tiers), §8.4 (cost-aware default, `cost`), §13.3 (skill).
- **Full suite:** the first run on the slice's SHA was red on `tests/test_harness_tools.py::test_a_web_step_turns_on_web_tools_and_a_used_tool_is_verified` (outcome `retry`, not `passed`). It passes alone, and it failed the same way on three earlier, unrelated commits (`f1c96e8`, `e558d53`, `632abdb`): a known flake under load, not this slice. A rerun on the same SHA was green; no code changed.
- **Review:** clean.
- **Accepted:** Yes, 2026-11-20 ("I accept these 4 slices.").

### Slice 4: answers that last (F-7, F-8)

- **Commit:** `2026-11-first-use-feedback-batch-a: Slice 4, answers that last`
- **Summary:** `packet.answers_earlier` gives a step the owner's answers from earlier iterations of its group and from attempts before the previous one, and a review of a step (its `~review`, a findings step independent of it, or one reading its output) every answer given to that step, as `prior_feedback.answers_earlier`; `INSTRUCTIONS.md` lists them under *The owner's earlier answers* and says not to ask again. Intake now keeps a blocked result's partial output in the CAS (`result_submitted.blocked_output_sha256`, never `output_sha256`, so nothing consumes it). A retry after answers receives it as `blocked/output.json` with `prior_feedback.prior_output {attempt, output, sha256}`, and the answers' `human_decision` carries its `output_sha256`. The worker skill says both.
- **Tests:** `tests/test_lasting_answers.py`: the run of 2026-11-20 in miniature (a step blocked with a proposal, answered with "accept all as suggested", its retry receiving the proposal, the answers' record holding its hash; the review receiving the answers; round two's first attempt receiving them and told not to ask again); no earlier answers without answers; the worker skill.
- **Design:** §7.1, §7.2, §13.8.
- **Review:** clean.
- **Accepted:** Yes, 2026-11-20 ("I accept these 4 slices.").

### Finished

- **Commit:** `2026-11-first-use-feedback-batch-a: done`
- **Summary:** The owner accepted the four slices (2026-11-20, "I accept these 4 slices."). Criteria 1 to 5, 7 to 9 and three of criterion 6's four parts are shown by the tests listed under each slice. Criterion 6's third part, lifting unjudged models, is handed over to `2026-11-model-assessment` (Decision 0175), which the owner will finish later. The opt-in live Director scenario (`tests/test_live_director_confirms.py`) was not run; it stays available.
- **Accepted:** Yes.
