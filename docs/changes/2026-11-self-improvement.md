---
id: 2026-11-self-improvement
title: "Baton learns from what goes wrong and from how work goes, taking as little of the owner's attention as possible"
status: accepted
level: major
decisions: ["0188", "0185", "0187", "0184", "0180", "0179", "0026", "0181", "0183"]
touches: [design/experts.md, design/director-interface.md, design/recipes.md, design/runtime.md, design/platform-and-security.md, design/testing.md]
manual: [manual/user/when-something-is-wrong.md, manual/admin/director-commands.md, manual/admin/machine-settings.md, manual/reference/commands.md]
---

# Baton learns from what goes wrong and from how work goes, taking as little of the owner's attention as possible

> **Hold lifted for four slices (Decision [0188](../decisions/0188-self-improvement-open-questions.md), 2026-11-22):** capture with a repro bundle, the circuit breaker, contract checks before runs, and baselines with detectors. Replay, local lines with the digest, sharing upstream and the analyst stay on hold, each to become a change of its own; they are kept below, under *Later*, so the thinking isn't lost. Request and Design approved 2026-11-23.
>
> History: Widened on 2026-11-22 from wording-level fixes for owner confusion (the first version, 2026-11-05) to two tracks: **A, learning from what goes wrong**, and **B, learning from how work goes**. The owner settled three questions (Decision [0185](../decisions/0185-self-improvement-direction.md)) and asked for every suggestion of that discussion to be written in; apart from 0185, everything below is a position, not a decision. The measuring part of track B goes ahead now as [2026-11-process-stats](2026-11-process-stats.md). Related: [2026-11-recipe-tree](2026-11-recipe-tree.md) (on hold), whose tree is the route for cases upstream; [2026-11-model-assessment](2026-11-model-assessment.md) (done), which already improves routing from evidence.

## Request

### Problem

**The owner is not here to improve Baton.** They are here for their own work. Baton should still get better with use, both where it fails and where it merely works less well than it could, while asking for as little of the owner's attention as possible, and never in the middle of their thinking about the subject.

**What first use showed.** The first real recipe-builder runs (`baton-recipes`, 2026-11-18 to 20; all fixed since by hand) are the evidence for what really comes up:

| Issue | Kind | How it surfaced | Where the fix had to go |
|---|---|---|---|
| Framing "which parts to start on" (pure-water, 2026-11-04) | Wording | The owner was confused | Recipe prompt |
| F-1 instruction reused as the owner's words; F-4 a real warning explained away | Director behaviour | The owner noticed | Director skill |
| F-2, F-3 no profile for person steps | Missing default | `doctor` warned; the Director dismissed it | Runtime and skill |
| F-6 the most expensive model kept chosen | Cost | The owner noticed the cost | Routing default, recipe tiers |
| F-7, F-8 answers lost between rounds | Runtime information flow | The owner was asked again | Runtime |
| `issues/2026-11-19-research-blocked-vs-schema.md` | Recipe contradicts itself | The worker refused, honestly | Shipped recipe schema |
| `issues/2026-11-20-design-evidence-and-lost-answers.md` | Runtime contradicts the packet | A retry loop, about 30 minutes of subscription each | Runtime |

Only one of the seven is wording, the only kind the first version handled, and the only one a local automatic fix could safely address. All the others had to be fixed upstream, in Baton's code, a shipped recipe or the Director skill. One thing worked: on the owner's "write it up as a Baton bug and hold the build", the Director wrote both `issues/` reports, reproducible and with evidence. That is the seed of the low-friction path for track A.

**What exists now (at `a1d25f0`).**
- *Who does each step* already improves from evidence, automatically: the track record, trials and shadow attempts under a daily budget, standing (proven, put back), and cost-aware routing by default (2026-11-model-assessment; Decisions 0175, 0176, 0179, 0181, 0182).
- *How the recipe works* has data but nothing acts on it: `stats` (§12.4) counts attempts, outcomes, failures, time, iterations and review findings; `process_feedback` events (kinds `friction`, `skipped_step`, `waste`, `confusing`); lessons with confirmation counts; process proposals the owner approves. All of it is read only when the process SME is consulted (on demand, at a retrospective step, or on the owner's cadence). `stats` has no cost, owner-burden or outcome counts; 2026-11-process-stats adds them.
- *Circuit breakers:* an explicit worker failure escalates instead of retrying (Decision [0180](../decisions/0180-worker-failures-escalate.md)); rejected results and failed gates still retry automatically (0180, 0183 item 4).
- *Hand-written cases:* `docs/bug-evals/` and `issues/`.

### Scenarios

**Track A, what goes wrong.**
1. **Wording** confuses the owner (the first version's case).
2. **Director behaviour:** the Director misreads, over-records or explains away (F-1, F-4); some of it may depend on which harness or model is the Director.
3. **Contract contradictions:** a recipe's instructions, schema and the runtime's rules disagree (research vs schema, dispositions). The most damaging kind, because an honest worker cannot pass and the step loops.
4. **Runtime defects:** information lost or mishandled (F-7, F-8).
5. **Missing defaults:** something every owner needs but must set up by hand (F-2).
6. **Runaway waste:** the same failure again and again, or spend far beyond what the step should cost.
7. **Drift:** harness versions and flags, retired models, price changes (the platform SME's ground).
8. **Upgrade regressions:** an upstream recipe version undoes a local improvement or breaks a case.

**Track B, how work goes.**
1. **Efficiency:** cost, time, attempts and iterations per step.
2. **Effectiveness:** first-time acceptance by the owner, rework, defects found late.
3. **Owner burden:** stops, questions, re-asked questions, waiting on the owner. Arguably the measure closest to what Baton is for.
4. **Recipe fit:** the owner keeps skipping, overriding or working around a step.
5. **Owner preferences:** not defects; adaptation to one owner (`.baton/communication.md`, §13.6).

### Acceptance criteria

- **Attention.** The owner meets self-improvement at three points only: one short check right after a confusion ("Is that clearer?"); a one-line choice when a Baton problem blocks their work ("this looks like a Baton problem, not yours: hold, or try X?"); and the digest at the end of a run, only when something is worth approving. Plus one opt-in for sharing, chosen once at setup.
- **Cases.** Every scenario produces the same record, a case: what happened, the evidence, where it came from, and where its fix belongs.
- **Track A.** A Baton problem that blocks a run produces a reproducible report without the owner having to ask, and the run is held or worked around, never left looping. A repeated identical failure stops after a set number of attempts and reaches the owner as one choice.
- **Track B.** A step whose measures are well off its baseline, with its quality guard holding, produces a proposal in the digest, with its evidence and its expected saving.
- **Replay.** A candidate change is replayed against the cases it addresses and every earlier case for the same step before it is offered or applied.
- **Autonomy.** Only wording changes apply automatically (replay-gated, new runs only, reported in the digest, with undo); routing keeps its existing behaviour. A change to a step's settings, reviews, design or the recipe's shape is applied only on the owner's yes in the digest (0185, item 1). Nothing changes steps, gates, schemas or the runtime without that yes (§1.4 #10).
- **Undo.** The owner can ask "what has Baton adjusted for me?" and get a plain answer, with undo.
- **Privacy.** Nothing leaves the machine unless the owner opted in and saw the exact text being sent.

### Acceptance criteria for this change (Decision 0188, item 0)

The criteria above are the whole direction. This change delivers these, and the rest (replay, autonomy, undo, privacy, and the digest's proposals) goes to the later changes:

1. **Cases.** A case is a `process_feedback` event with one shape whatever produced it: kind, `source` (`director` or a detector's name), what was shown or measured, the owner's words if any, the evidence (event seqs, attempt paths), the Director's harness and model when it is about the Director, and `fix_in` (where its fix lives). `stats` counts cases per step by kind and `fix_in`.
2. **Report, without being asked.** When a Baton problem blocks a run, the Director writes a repro bundle (`baton report`) and offers the owner one choice: hold, or a named workaround. The bundle is assembled deterministically from the record, machine-local parts redacted.
3. **Circuit breaker.** The same rejection or gate failure on two consecutive attempts escalates with reason `repeated_failure`, the spend so far, and no further automatic retry (0188, item 2).
4. **Contract checks.** Each built-in recipe and every example recipe the project ships passes a simulated run in the suite, through the blocked-and-answered path and a second round of each review loop; recipe-builder's audit checks a recipe's instructions against its schemas and runtime rules.
5. **Baselines and detectors.** A recipe can carry baselines; at the end of a run a step well off its baseline opens a case that records its quality guards (so a later proposal can require them holding); a re-asked question opens a case.
6. **Late defects.** `stats` counts defects found late against the step that produced the file (0188, item 8).

## Design

### This change: four slices (Decision [0188](../decisions/0188-self-improvement-open-questions.md), item 0)

Nothing here changes a step, gate, schema or recipe on its own; everything recorded is an observation (Principle 5). The *Positions* further down are the background for the later changes and are not part of this design.

**D1. Cases (§12.4).** A case is a `process_feedback` event with more fields, not a new store:
- New kinds: `baton_problem` (the Director: the run hit something in Baton, a shipped recipe or the Director skill, not in the owner's work), and three a detector records: `repeated_failure` (D3), `off_baseline` and `reasked` (D5). The existing four kinds stay.
- New fields, all optional: `source` (`director`, `worker`, `owner` or `detector:<name>`; the existing events read as before); `fix_in` (`local_wording`, `local_preference`, `local_settings`, `recipe_shape`, `upstream`, or absent when nobody has classified it); `evidence` (event seqs and attempt paths); `owner_words` (verbatim, when the owner said something); `director` (`{harness, model}`, recorded when the case is about the Director's behaviour, as the Director states it); `clarified` (`{before, after, owner_reply}` for the "Is that clearer?" check); `report` (the repro bundle's path, D2).
- `feedback` (CLI, MCP, engine) gains `--fix-in`, `--evidence`, `--owner-words`, `--about-director` and `--clarified-before/--clarified-after/--owner-reply`. Detectors set `source` and the evidence and leave `fix_in` to the Director or the process SME.
- `stats` adds `cases` per step: counts by kind and by `fix_in` (`unclassified` for absent).

**D2. Report, hold or work around (§13.3, §13.8, a new command in §13.1).** `baton report <run> [<step>] [--case <seq>] [--title <text>]` writes `.baton/reports/<date>-<slug>/`, kept out of git like `.baton/cache/`:
- `report.md`: a header assembled from the record (Baton version, recipe and version, run, step, attempts, harness and model of each, the case), then sections headed *What happened*, *Root cause*, *Expected* and *Suggested fixes* for the Director to fill in, as in the two first-use `issues/` reports.
- `bundle/`: the step's events, each attempt's packet (INSTRUCTIONS.md, the schemas), `result.json`, the gate outputs and the tail of each attempt's log, all redacted (`redact_text`) and with machine-local paths written as `~`.
It records nothing and changes no state; the Director records a `baton_problem` case with `report` set. The Director skill gains rules: when a Baton problem blocks the run, write the report without being asked, then tell the owner in one line, "This looks like a Baton problem, not yours. I've written it up. I can hold this step, or try X. Which?", where X is an existing decision (another worker, a retry with a note pointing out the contradiction). Holding needs no command; the step stays escalated. After clarifying something that confused the owner, ask "Is that clearer?" once and record a `confusing` case with `clarified`. Record cases silently otherwise. The Director skill itself is fixed upstream only (0188, item 3). The temporary local patch (0188, item 1) needs the overlay of local lines and arrives with them.

**D3. The circuit breaker (§8.8; 0188, item 2).** When a counted attempt is rejected (`result_rejected`) or fails a blocking gate (`gate_failed`), and would be retried, the runtime compares its failure with the previous counted attempt's in the same attempt budget (trial attempts and attempts not counted are skipped):
- A failure's signature is its event type, the gate's index (none for a rejection) and the set of its reasons, each normalized: lower case, `attempt-<n>` and runs of digits and hex of 7 or more characters replaced by `#`, whitespace collapsed. So "design_doc.md does not exist at commit 13b48b3" on attempt 2 and the same text with another SHA on attempt 3 match.
- Equal signatures: `step_escalated {reason: repeated_failure, reasons, attempts: [n-1, n], spend: {usd, attempts_priced, attempts_included, attempts_unknown}}` instead of `step_ready`, and a `repeated_failure` case. It is checked before the attempt budget, so with `max_attempts: 2` the reason is `repeated_failure`, not `attempts_exhausted`.
- Different signatures: retry as today. `repeated_failure` joins the escalation reasons (§8.1) and is a stop (§12.4). The Director offers the owner one choice, with the spend so far. A decision readies the step and restarts the budget, as for any escalation.

**D4. Contract checks before runs (§5.1, §15.3, §17).**
- *Runtime against the packet.* For every rule the packet's INSTRUCTIONS state about results (a blocked or failed result is exempt from the output schema; `fixed` evidence in the attempt's own result; answers carried across rounds; dispositions in a second review round), the suite has a scenario that follows the rule as written and passes. That is the class of `issues/2026-11-20`. The scenarios use `tests/runkit.py` and the fake adapter.
- *Shipped recipes, simulated.* A small generator in `recipe_check.py` builds a minimal instance of an output schema for the JSON Schema subset recipes use (`type`, `required`, `properties`, `enum`, `const`, `items`, `minItems`, `if`/`then`, `allOf`, `$ref` within the package). Each built-in recipe and each example recipe is simulated in the suite (`slow`): every step returns its generated output; a step whose prompt allows `blocked` (or which asks questions) returns blocked first, then completes on the answers; every review loop runs a second round with `fixed` dispositions citing the new artifact. A schema the generator can't satisfy is a problem reported by name.
- *Recipe instructions against their schemas.* Prose can't be checked by code, so recipe-builder's audit step gains a contract-consistency check: do its instructions require what the output schema forbids, or forbid what it requires; does each disposition, answer and evidence rule have a way to be met. `baton recipe check` (and `vendor`) runs the generator's satisfiability check on every output schema.

**D5. Baselines and detectors (§5.1, §12.4; 0185 item 3, 0187 item 2, 0188 item 8).**
- *Baselines.* An optional `baselines.json` in a recipe package: per step id, the medians of `cost_usd`, `duration_s`, `attempts`, `iterations`, `owner_stops` and `owner_questions`, with `samples`, plus `derived {from, runs, recipe_versions, date}`. It is part of the package and its hash, so it changes with a recipe version. `baton recipe baselines <recipe> [--project <dir>]...` writes it from the completed runs in the projects named (the owner's own, as reference owner), medians only.
- *Off baseline.* When a run completes, for each step with a baseline of at least `min_samples` (a machine setting, `~/.baton/preferences.yaml` `self_improvement`, default 3), a measure above `factor` × its median (default 2) opens one `off_baseline` case per step and measure, recording the value, the median and the guards (first-try gate pass, rejections, late defects). The process SME reads these cases as today; turning them into proposals for the owner waits for the digest.
- *Re-asked.* At intake, a result or blocked escalation asking a question whose id the owner already answered for the step in this run opens a `reasked` case with both seqs.
- *Late defects.* When findings are recorded, a finding whose `location` (the part before `:line`) names a file produced by another step P counts as a late defect against P, provided P has a review or findings gate of its own that had passed earlier in the run. "Produced by P" means one of P's result artifacts or a file P's accepted attempt changed in the working tree. `stats` gains `outcome.defects_late` on P. A location that matches nothing is not counted.
- *Left out:* the pay-per-token detector of the positions. The record keeps the routes left out but not the eligible routes not chosen, and default routing already prefers included routes. It would need a new routing field, so it waits until a case shows the need.

### Doc edits

- `design/experts.md` §12.4: case fields, the new kinds and sources, `stats` `cases` and `defects_late`, the detectors, baselines.
- `design/runtime.md` §8.1, §8.2, §8.8: the `repeated_failure` escalation and its event fields; the circuit breaker.
- `design/director-interface.md` §13.1, §13.3, §13.8: `report`, the new `feedback` options, the skill's rules for cases, reports, the hold-or-workaround choice and "Is that clearer?".
- `design/recipes.md` §5.1: `baselines.json`; `recipe baselines`; the satisfiability check in `recipe check`.
- `design/platform-and-security.md` §15.3: the simulated runs of shipped recipes; `design/testing.md` §17: the contract scenarios.

### Manual edits

- `manual/user/when-something-is-wrong.md`: "This looks like a Baton problem" and the choice; a step stopped after the same problem twice.
- `manual/admin/director-commands.md` and `manual/reference/commands.md`: `report`, the new `feedback` options, `recipe baselines`.
- `manual/admin/machine-settings.md`: the off-baseline settings.

### Later (on hold): the positions below


### Positions (2026-11-05 and 2026-11-22; the owner's positions and Claude's suggestions, not decisions unless linked)

**Terms** ("trunk" and "branch" would collide with git in the project repo):
- **Upstream:** a recipe as its maintainer publishes it (`fit-check@2`).
- **Local line:** this owner's version: upstream plus accepted local changes, recorded per run (e.g. `fit-check@2+local.3`).
- **Case:** one recorded incident or measured anomaly.
- **Candidate:** a tentative change being tried.
- **Baseline:** the expected value of a step's measures (cost, time, iterations, owner stops), shipped with the recipe.
- **Digest:** the end-of-run summary of what Baton adjusted, and what it proposes, with evidence and undo.

It's the Linux-distribution pattern: each distribution carries its own patches on top of upstream and sends the general fixes back.

**1. One case for everything.** Cases come from two kinds of source:
- *The Director's judgment* (it is the only part that sees the owner): confusion, redirection, clarification requests, discussing a question instead of answering it, the owner correcting the Director, a Baton problem the owner hits. Cheap runtime signals (a reject with a note, a retry right after a human gate, an owner question while a decision is pending) prompt the Director to look; only its judgment opens a case of this kind.
- *Deterministic detectors* over the record, no model involved: a worker's explicit failure (0180); the same rejection or gate failure on consecutive attempts; a question re-asked after it was answered; a step's measures well off its baseline (track B); a pay-per-token route chosen while an included route was eligible.

A case records what was shown or measured, the owner's words where there are any, and what produced it (a worker output, a recipe prompt or schema, a skill rule, the runtime). To keep the concept budget, a case is a richer `process_feedback` event (new kinds as needed), not a new store.

**2. Classify by where the fix lives.** This decides autonomy, the owner's attention and who pays:

| The fix lives in | Who does it | The owner's attention | Who pays |
|---|---|---|---|
| Local wording or preference | Automatic, replay-gated, undo | One "Is that clearer?" | Owner, small |
| Local step settings (tier, timeouts, attempt budget, context) | Proposed in the digest (0185, item 1) | A yes in the digest | Owner, small |
| Recipe shape (reviews, steps, gates, a program instead of an AI step) | A process SME proposal in the digest | A yes in the digest | Owner, moderate |
| A shipped recipe, the Director skill or the runtime | **Upstream:** a reproducible report, plus a hold, a workaround or a temporary local patch (open question 1) | One choice when blocked; the sharing opt-in | **Provider** |

Classification is the Director's or a cheap model's judgment, recorded with the case and correctable by the maintainer. Most early cases are expected to be upstream ones (first use: six of seven).

**3. Who pays.** The expensive part, fixing Baton, is the provider's job, in the provider's repo and on the provider's accounts: today the maintainer with an agent working through `issues/`; later an analyst/fixer (8, below). A provider API key on owners' machines is ruled out: a key shipped in a client can be extracted, so it would need a hosted relay, and an owner's data would have to pass the sharing opt-in before the provider could use it anyway. The owner's side stays cheap: the Director's existing turn, deterministic detectors, assembling a repro bundle, and small model calls for classification and wording candidates, run as shipped improvement steps on included or free routes under the existing daily budget (Decision [0179](../decisions/0179-trial-and-shadow-routing-details.md), item 4). *Guess, not verified:* well-prompted cheaper models are good enough for classifying and drafting; diagnosing a runtime defect needs a strong model and the code, which is another reason it belongs upstream.

### Track A: what goes wrong

**A1. Capture while the window is open.** After the Director's clarification, a one-line "Is that clearer?" costs almost nothing, since the owner has already stepped out of the subject. The rewording that got the owner unstuck is the first candidate. The owner's "yes" is biased evidence (they now know what was meant): recorded as strong, but replay and recurrence remain the real test.

**A2. Report, hold or work around.** When a case is classified upstream and blocks the run, the Director says, in the owner's terms: "This looks like a Baton problem, not yours. I've written it up. I can hold this step, or try X instead. Which?" The report is a **repro bundle**, assembled mostly deterministically: the case, the events, the packet, the result, the schemas and contracts involved, the logs (machine-local parts redacted), the Baton and recipe versions; written in the project as the `issues/` reports were. "Try X" is a workaround the Director or the process SME proposes (a different worker, a retry with the contradiction pointed out, the temporary patch of open question 1).

**A3. Circuit breaker.** The same reason twice in a row stops the loop (open question 2) and becomes one owner choice, with the spend so far. Explicit worker failures already escalate (0180).

**A4. Prevention.** Contract contradictions are partly detectable before a run:
- a **contract consistency check** when recipe-builder builds a recipe and when a recipe is vendored: do the instructions require something the output schema forbids (e.g. a blocked result whose output cannot validate), or forbid something it requires; does each disposition, answer or evidence rule have a way to be satisfied;
- a **simulated run** of every shipped recipe before release (`baton simulate`, §15.3, with the fake adapter), including the blocked-and-answered path and a second round of every review loop.

**A5. Director quirks by model.** A case about Director behaviour records which harness and model was Director. General fixes go into the skill upstream; harness-specific notes, where a pattern shows, go into the shipped harness data, not the skill.

### Track B: how work goes

**B1. Measures.** Per step and per recipe version: cost, time, attempts, iterations, owner stops, questions, re-asked questions, waiting on the owner, first-time acceptance, rejections, owner edits ([2026-11-process-stats](2026-11-process-stats.md)); plus, here, defects found late (a later review finding a problem in an earlier step's artifact).

**B2. Baselines.** The expected values per step, shipped with the recipe, so one run can be compared with what's expected without local history. For now they are derived from the owner's (Rob's) own runs as the reference owner (0185, item 3), using medians. They are regenerated when a recipe version changes a step.

**B3. The core difficulty: few occurrences.** Processes are project-like; an owner may run recipe-builder a handful of times ever, so local A/B testing gives nothing meaningful. Hence:
- **measures detect, they don't prove:** a step well off its baseline opens a case; the fix is proven by replay, then confirmed by later use;
- **more samples come from within runs than from runs:** iterations and instances of a step;
- **counterfactual replay**, as shadows do for models: replay recorded packets with a candidate change and judge the result, under the daily budget;
- **real statistics only upstream**, from owners who opt in to sharing (shapes only), analysed by the maintainer.

**B4. Levers, by risk.**

| Lever | Example | Autonomy |
|---|---|---|
| Routing | Already built (0175 to 0182) | Automatic, as today |
| Wording | Prompts, labels | Automatic, replay-gated, undo |
| Step settings | The tier asked for, timeouts, attempt budget, tool-call limit, how much context a packet carries | Digest only (0185, item 1) |
| Reviews | Drop one that never finds anything; add one where defects slip through | Digest |
| Step design | **An AI step whose outputs are highly regular and always pass: propose a program instead** (and say what the program costs, per the recorded AI-worker bias) | Digest; then recipe-builder builds it |
| Recipe shape | Merge, split, or skip steps by rating | Digest, or the maintainer |

**B5. Quality holds first (Goodhart).** Every efficiency measure is paired with a guard that must not get worse: defects found late, rework, first-time acceptance. Dropping a review lowers iterations and cost, and quality with them. The rule, as trial routing already applies it (a trial never lowers the step's tier, 0179 item 1): **hold quality, then reduce cost and owner burden.** A proposal whose replay or record shows a guard worsening is not offered.

**B6. The digest.** At the end of a run (or a natural break), only when there is something: what was adjusted automatically (with undo), and each proposal as one yes or no with its evidence and expected saving, e.g. "The design review found nothing in 6 rounds; skip it on simple-rated runs? Saves about $X and Y minutes." It is kept in the project if the Director session ends first.

### Shared machinery

**Replay.** Each case is a replayable test: replay it with the candidate, using a judge from a different vendor (Decision: [0026](../decisions/0026-judges.md)) and, where an owner is involved, a simulated owner; replay all earlier cases for the step so nothing regresses. Reuses the fake adapter and `baton simulate` (§15.3); runs under the daily budget.

**Candidates and local lines.** A candidate is a small overlay on the pinned recipe version, kept outside the recipe's package hash (as `.migrated.json` is, §14.2) and recorded in `run_started`; one candidate per step or question at a time; new runs only. A wording candidate joins the local line after its replay passes and N clean real uses (open question 4), automatically, reported in the digest with undo; a recurrence rolls it back. Every other change joins only on the owner's yes. To keep the concept budget, a candidate is a process proposal (§12.4) and the local line a project file beside `.baton/process/lessons.md`.

**Upgrades.** On an upstream upgrade, local changes are replayed onto the new version and the owner's cases re-run against it: changes upstream made redundant are dropped, conflicting ones become candidates again. The rebase mechanism is shared with derived recipes (2026-11-recipe-tree).

**Sharing upstream (opt-in).** `recipe.yaml` gets an `upstream:` entry naming where the recipe is maintained and where cases go (e.g. issues on its repo); shipped recipes point at `rowama/baton`. Cases go in a shareable form (open question 6). Opt-in is chosen once, at setup (2026-11-zero-friction-setup).

**Analyst and fixer (provider side; last).** A periodic job at the recipe's repo groups similar cases, weighs how many owners and versions they came from, reproduces them from their bundles, replays candidate fixes against all of them, and opens PRs with the evidence for a human to review. It could itself be a Baton recipe, run on the provider's accounts. Until there is volume, the maintainer reading the case list beats an analyst.

### Hard boundaries

- Automatic changes: wording only (and routing, as today). Everything else needs the owner's yes in the digest (0185, item 1); nothing changes steps, gates, schemas or the runtime otherwise (§1.4 #10). The temporary patch of open question 1 is an explicit owner yes, not an automatic change.
- One candidate per step or question at a time.
- Nothing upstream merges without human review.
- Incoming upstream cases are written by strangers: data only, never instructions (a prompt-injection route into the analyst).
- No provider credentials on owners' machines.

### Principle 5

Detection by the Director, the "Is that clearer?" check and the blocked-run choice are conversation (fuzzy, judged). Everything recorded (cases, measures, candidates, promotions, rollbacks, the digest) is structured. Recording a case needs no confirm-back, because it records an observation, not something the owner is taken to have decided; applying anything but wording, and sending anything upstream, needs the owner's confirmation.

### Concepts (§2)

Case, candidate, local line, baseline and digest are internal vocabulary; the owner hears "what Baton adjusted for you" and "a suggestion". To keep the budget: a case is a richer `process_feedback` event; a candidate a process proposal; the local line and baselines files beside existing process records; the digest a Director duty, not a command. If any term becomes user-visible, §2 is updated.

### Risks

- A judge model is a noisy stand-in for people; a simulated owner misses things a real one wouldn't.
- Baselines from one reference owner reflect one person's way of working.
- Local lines can overfit to one person's taste: acceptable locally, a reason upstream needs volume.
- Classification can be wrong, routing a local problem upstream or the reverse; the maintainer corrects it, and the correction is itself evidence.
- Detectors with loose thresholds would fill the digest; the digest says nothing unless something clears its threshold and its guards.
- Separating subject matter from a case's shape isn't fully automatic, hence the owner preview.

### Doc edits for the later changes (anticipated)

- `design/experts.md` §12.4: cases (sources, classification), detectors, baselines, replay as evidence, candidates and local lines, the digest.
- `design/director-interface.md` §13.3, §13.8: the Director records cases silently, asks one "Is that clearer?" after clarifying, offers hold or workaround for a blocking Baton problem, and gives the digest.
- `design/runtime.md` §8.8, §8.10: the circuit breaker for repeated identical failures.
- `design/recipes.md` §5.1: optional `upstream:` entry; baselines shipped with a recipe; the contract consistency check at build and vendor time.
- `design/versioning.md` §14: the local line recorded per run; rebase on upstream upgrade.
- `design/platform-and-security.md` §15.3: `baton simulate` gains case replay and pre-release runs of shipped recipes.
- `design/workers.md` §6.4: harness-specific Director notes in the shipped harness data.
- `principles.md` §2: concept-budget entries if any term becomes user-visible.

### Manual edits for the later changes (anticipated)

- `manual/user/`: what Baton adjusts for the owner and how to undo it; the digest; the blocked-run choice. Settled with Design.

### Decisions

- [0185](../decisions/0185-self-improvement-direction.md) (accepted): setting changes only through the digest; process statistics now (2026-11-process-stats); baselines from the owner's own runs for now.
- [0180](../decisions/0180-worker-failures-escalate.md) (accepted): explicit worker failures escalate; open question 2 would extend it.
- [0183](../decisions/0183-disposition-evidence-in-the-tree.md) (accepted), item 4: rejected results and failed gates keep their automatic retries today.
- [0179](../decisions/0179-trial-and-shadow-routing-details.md) (accepted), items 1 and 4: a trial never lowers a step's tier; the daily budget.
- [0181](../decisions/0181-first-use-feedback-routing-and-answers.md) (accepted): answers last across rounds, so a re-asked question is a detectable fault.
- [0184](../decisions/0184-answers-outside-a-blocked-step.md) (accepted): a completed result may carry questions on its guesses; such guesses are themselves a measure (track B).
- [0026](../decisions/0026-judges.md) (accepted): judges from a different vendor.
- [0188](../decisions/0188-self-improvement-open-questions.md) (accepted): this change's scope (four slices), the temporary local patch, the circuit breaker, the Director skill upstream only, promotion after replay plus 3 clean uses, where the digest goes, what may be shared, baselines across owners left open, and late defects counted deterministically.
- [0187](../decisions/0187-process-stats-details.md) (accepted), items 2, 3 and 6: medians, late defects moved here, what a stop is.

## Plan

Slices get approved criteria with the Design (major). Each pays off on its own. The four later sections are kept as the sketch for the changes that follow.

### Slice 1: cases and the repro bundle

- **Outcome:** D1 and D2: the richer `process_feedback` (kinds, `source`, `fix_in`, evidence, owner's words, Director identity, `clarified`, `report`) through CLI, MCP and engine; `stats` `cases`; `baton report` with its redacted bundle; `.baton/reports/` ignored by git; the Director skill's rules; manual.
- **Criteria:** a case with every field round-trips and `stats` counts it by kind and `fix_in`; an old `process_feedback` event reads unchanged; `report` on a run with a rejected attempt writes `report.md` with the header and the empty sections, and a bundle holding the events, packet, schemas, result, gate output and log tail, with a planted secret and a machine path absent; `report` records no event; the skill text holds the rules (skill test).
- **Effort:** M

### Slice 2: circuit breaker

- **Outcome:** D3.
- **Criteria:** the same rejection twice escalates `repeated_failure` with both attempts and the spend, and records a `repeated_failure` case; reasons differing only in attempt number, SHA or line number match; different reasons retry; the same failure of a different gate retries; with `max_attempts: 2` the reason is `repeated_failure`; trial attempts are skipped; a decision readies the step with a fresh budget; `stats` counts it as a stop; the 2026-11-20 disposition case, replayed through runkit, stops after its second attempt.
- **Effort:** S

### Slice 3: contract checks before runs

- **Outcome:** D4.
- **Criteria:** the contract scenarios pass; the generator yields a valid instance for every output schema of every built-in and example recipe and reports an unsatisfiable one by name (e.g. the recipe-builder@7 research rule, kept as a fixture); every built-in and example recipe completes a simulated run through blocked-and-answered and second review rounds; `recipe check` reports an unsatisfiable schema; recipe-builder's audit prompt holds the contract-consistency check.
- **Effort:** L (the generator and ten recipes' runs)

### Slice 4: baselines and detectors

- **Outcome:** D5.
- **Criteria:** `recipe baselines` writes medians from fixture projects and a recipe with `baselines.json` loads and hashes it; a completed run with a step at more than twice its median opens one `off_baseline` case per measure with the guards recorded, none below `min_samples` or within the factor; a re-asked question opens a `reasked` case; a finding locating a file of a reviewed earlier step counts one late defect on that step, and none for a step without its own review or a location that matches nothing; manual.
- **Effort:** M

## Later (each its own change, on hold)

### Replay

- **Outcome:** a case replays against a candidate and against earlier cases, with a different-vendor judge and a simulated owner, under the daily budget.
- **Effort:** L

### Local lines and the digest

- **Outcome:** wording candidates apply to new runs, promote automatically and roll back on recurrence; every other proposal waits for the owner's yes in the digest; "what has Baton adjusted for me?" answers with undo; local changes rebase on upstream upgrades.
- **Effort:** L

### Sharing cases upstream

- **Outcome:** opt-in at setup; batched preview of the exact text; submission to the recipe's `upstream:`.
- **Effort:** M

### Analyst and fixer

- **Outcome:** clustering, reproduction from bundles, cross-owner replay and evidence PRs at the recipe's repo, on the provider's accounts.
- **Effort:** L

## Log

### Recorded on hold

- **Summary:** First version, 2026-11-05: wording-level improvement for owner confusion, with local lines, replay and opt-in upstream cases. No code changed.
- **Owner decision:** 2026-11-05, put on hold as a change doc.
- **Accepted:** No; proposal only.

### Widened to two tracks

- **Summary:** Rewritten from the 2026-11-22 discussion, checked against first-use evidence (2026-11-first-use-feedback-batch-a F-1 to F-8; `issues/2026-11-19-research-blocked-vs-schema.md`; `issues/2026-11-20-design-evidence-and-lost-answers.md`) and Baton at `a1d25f0` (`sme.stats()`, the track record, 0180, 0183). Track A (what goes wrong) and track B (how work goes, measured) share cases, replay, local lines and the digest; fixes are classified by where they live, and upstream fixes are the provider's. Three answers recorded as Decision 0185; the measuring part split out as 2026-11-process-stats. Title changed. No code changed.
- **Owner decision:** 2026-11-22, "1-only through the digest. 2-yes, now. 3-my own for now. Incorporate all of your suggestions into the change proposal." (0185).
- **Accepted:** No; still on hold. Open questions 1 to 7 await the owner.

### Open questions settled; four slices designed

- **Summary:** The owner answered the seven open questions, the late-defects question 0187 moved here, and the scope (Decision 0188). The hold is lifted for capture with a repro bundle, the circuit breaker, contract checks and baselines with detectors; replay, local lines with the digest, sharing and the analyst stay on hold as later changes. Design D1 to D5 and slice criteria written against the code at `0b9ee8e` (`engine._failed`, `feedback`, `Finding.location`, `recipe_check.py`). The pay-per-token detector is left out (no record of eligible routes not chosen). The temporary local patch waits for local lines. No code changed.
- **Owner decision:** 2026-11-22, "All as suggested" (0188).
- **Accepted:** Yes, 2026-11-23: "Approved" (Request and Design, slices 1 to 4).
