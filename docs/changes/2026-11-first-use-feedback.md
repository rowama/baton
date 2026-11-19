---
id: 2026-11-first-use-feedback
title: "Fixes and tweaks from the owner's first real use of Baton"
status: proposed
level: standard
decisions: ["0161", "0045", "0042", "0174", "0110", "0124"]
touches: [design/workers.md, design/director-interface.md, design/runtime.md, design/recipes.md]
manual: []
---

# Fixes and tweaks from the owner's first real use of Baton

## Request

### Problem

The owner has started using Baton for real, beginning with a recipe-builder run in `D:\rob\projects\baton-recipes` (run `r_20261119_8c96`, 2026-11-18, with Codex and then Grok Bot as Director). This change collects what that use shows needs fixing or adjusting, one item per finding, so the owner's feedback is caught in one place as it arrives. Each item records what happened, the evidence, and the proposed fix. Items are added as they come; when one grows large enough to need its own design, it moves to its own change and this doc links to it.

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

### Acceptance criteria

1. **F-1.** Before `start`, `vendor`, `attest` or `bind`, the Director restates what it will record in the owner's terms and records only the owner's confirming words. It never reuses an instruction to the Director as the owner's confirmation, and never puts an instruction to the Director in a run input; a run's `idea` is the process in the owner's words, confirmed back.
2. **F-2.** Every machine has a profile for the owner as a person, without the owner writing one: `manual` adapter, identity `human/owner`, `human_judgment` and the capabilities a person brings. An owner's own profile of that name replaces it. `doctor` no longer reports person steps as uncovered while it exists, and if no person's profile exists says so plainly with the fix.
3. **F-3.** When a run reaches its first person's step, or at `start` if the recipe has any, the Director asks, once, whether the person it is talking to will do them, with yes as the default. If yes, the owner's profile does them. If someone else will, the Director records who, and their steps are routed to a person's profile for them, created without the owner writing it. The answer is kept so the question is not repeated.
4. **F-4.** The Director skill says: report a `doctor`, `check` or `status` warning as Baton states it; if it seems wrong, read what the check tests (`help`, the manual) before saying so, and never call a warning intended behaviour without that.
5. **F-5.** The Director skill says how to vendor a shipped recipe the owner names, with their confirming words.
6. **F-6.**
   - Routing is cost-aware by default: a route the owner already pays for (a subscription CLI with quota left) comes before a pay-per-token route, and among the rest the cheaper first; price, not the profile's name, breaks ties.
   - recipe-builder asks for `strong` only on steps that need it; steps that assemble or transcribe take `standard`.
   - Unjudged models can be lifted without the owner writing anything: the common ones judged in the shipped data, or a cheap check on request (see open question 5).
   - When the Director offers a choice of worker, it says what each costs (included in a subscription, or roughly how much credit), and never offers a pay-per-token route ahead of a paid-for one without saying why.
7. **Each later item** gets its criterion here when it is added.
8. **Manual and design are current.**

### Open questions

None open for F-1 to F-5. The four questions on F-2 and F-3 were answered by the owner on 2026-11-18 as suggested, and are recorded in Decision [0174](../decisions/0174-first-use-feedback-people.md):

1. Who does the person steps is asked at `start` when the recipe has person steps, and kept for the project in project policy (`policy.people: {person_steps: owner | <name>}`); the owner can change it with their words.
2. A person the owner names does person steps only; the run's owner keeps every owner decision.
3. The owner's profile: `human_judgment`, `long_form_writing`, `vision`, `file_write`, tier `strong`.
4. It is built in, present on every machine and shown by `workers status`, replaced by an owner's own profile of that name.

Later items add their own questions here.

5. **F-6: how are unjudged models lifted?** *Suggested:* both: the shipped data judges the models most used through OpenRouter, and the owner may ask for an assessment of chosen models (Decision 0111) or a small set of capability checks: now [2026-11-model-assessment](2026-11-model-assessment.md) (Decision 0175). *Rationale:* shipped judgments help every owner at no cost; checks cover the long tail when an owner wants a particular cheap model.
6. **F-6: how is a subscription route priced?** *Suggested:* as "included" while its quota lasts, ranking before any priced route under cost-aware ordering; exhausted quota already re-routes (Decision 0114). **[VERIFY]** how such routes rank under `cheapest_first` today; as far as known, unpriced profiles rank last, which would push work off a subscription.

## Design

### Doc edits

- `design/workers.md` §6.1: the built-in owner profile and profiles for other people (F-2, F-3); §6.4: what `workers status` shows.
- `design/director-interface.md` §13.3: the skill lines for F-1, F-3, F-4 and F-5; §13.4: `doctor` on person steps; §13.7: `policy.people` (F-3).
- `design/runtime.md` §8.4: routing person steps to the recorded person (F-3); cost-aware ordering by default (F-6).
- `design/workers.md` §6.4: lifting unjudged models (F-6).
- `design/recipes.md` §5.7: recipe-builder's tiers per step (F-6).

### Manual edits

To be listed when the change is in progress. Expected: the owner's topic on what Baton asks you, `admin/director-commands.md`, `admin/machine-settings.md`, `reference/diagnostics.md`.

### Decisions

- [0161](../decisions/0161-ai-delegates.md) (accepted), item 6: the person who starts a run is its owner.
- [0045](../decisions/0045-sme-never-a-person.md) (accepted): an expert consulted by subject is never a person; unchanged.
- [0042](../decisions/0042-vendoring-on-selection.md) (accepted): shipped recipes are vendored when chosen.
- [0174](../decisions/0174-first-use-feedback-people.md) (accepted): who does person steps, and the built-in owner profile (F-2, F-3).
- [0110](../decisions/0110-unjudged-model-default-tier.md) (accepted): unjudged models default to tier `basic` (F-6).
- [0124](../decisions/0124-machine-level-preferences.md) (accepted): routing preferences (F-6).
- Later items add their own records.

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
