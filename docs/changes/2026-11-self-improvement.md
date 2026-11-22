---
id: 2026-11-self-improvement
title: "Baton learns from what goes wrong and from how work goes, taking as little of the owner's attention as possible"
status: proposed            # ON HOLD: discussion stage, not ready for Design approval; its measuring part goes ahead as 2026-11-process-stats
level: major
decisions: ["0185", "0184", "0180", "0179", "0026", "0181", "0183"]
touches: [design/experts.md, design/director-interface.md, design/recipes.md, design/versioning.md, design/platform-and-security.md, design/runtime.md, design/workers.md]
manual: []
---

# Baton learns from what goes wrong and from how work goes, taking as little of the owner's attention as possible

> **On hold.** Recorded so the thinking isn't lost. Widened on 2026-11-22 from wording-level fixes for owner confusion (the first version, 2026-11-05) to two tracks: **A, learning from what goes wrong**, and **B, learning from how work goes**. The owner settled three questions (Decision [0185](../decisions/0185-self-improvement-direction.md)) and asked for every suggestion of that discussion to be written in; apart from 0185, everything below is a position, not a decision. The measuring part of track B goes ahead now as [2026-11-process-stats](2026-11-process-stats.md). Related: [2026-11-recipe-tree](2026-11-recipe-tree.md) (on hold), whose tree is the route for cases upstream; [2026-11-model-assessment](2026-11-model-assessment.md) (done), which already improves routing from evidence.

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

### Open questions

Each with a suggested answer and its rationale, for the owner to settle in one batch before Design approval:

1. **A temporary local patch?** For a contract contradiction blocking a run (e.g. a schema that a blocked result cannot meet), may Baton offer a temporary local patch (a loosened schema, a reworded rule), applied on the owner's one-line yes and dropped automatically when upstream fixes it? *Suggested:* yes, offered only when the case's classification is a contract contradiction and the patch makes the check less strict, never stricter or different in meaning; recorded as a candidate and in the run. *Rationale:* holding the build was the right call in first use, but an owner without a maintainer would just be stuck; loosening a self-contradictory check removes an impossible requirement and doesn't change what the step is meant to do.
2. **Circuit breaker for schema and gate failures.** 0180 left rejected results and failed gates on automatic retry; the disposition case showed they loop too. *Suggested:* the same rejection or gate failure (same reason, same check) on consecutive attempts stops after the second and escalates as one choice; different reasons keep retrying. *Rationale:* a repeated identical reason means the worker cannot fix it by trying again, which is the condition 0180 cared about, detected without reading prose.
3. **Director skill in scope?** *Suggested:* the Director skill is improved upstream only (cases and reports, fixed by the maintainer); local lines cover recipes and the owner's communication preferences. *Rationale:* the skill is vendored per project and re-vendored on upgrade (§14.2), so local edits would conflict, and every owner hits it.
4. **How many clean uses before a wording candidate joins the local line?** *Suggested:* all replayed cases pass, plus 3 clean real uses; a recurrence rolls it back. A machine setting, like the trial thresholds. *Rationale:* volume per owner is low; replay carries most of the evidence, and real use confirms.
5. **Where does the digest reach the owner?** *Suggested:* the Director gives it at the end of a run (or at a phase's natural break), in the owner's terms; it is also kept in the project for a detached Director to pick up, and shown on the setup page later. *Rationale:* end of run is the natural break; keeping it means it is never lost when the Director session ends.
6. **What may be shared upstream?** *Suggested:* the case's shape (step, kind, measures, the reaction, the local fix), never the subject matter or the owner's words, shown to the owner exactly as it would be sent, in batches at natural breaks; after a few batches sent unedited, Baton offers "send without asking". *Rationale:* separating subject matter from shape isn't fully automatic, so the preview is the safeguard.
7. **Baselines once other owners exist** (left open by 0185, item 3). *Suggested:* leave open until shared cases exist; then baselines are medians across owners who share, kept beside the reference owner's. *Rationale:* no data to decide on yet.

## Design

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

### Doc edits (anticipated)

- `design/experts.md` §12.4: cases (sources, classification), detectors, baselines, replay as evidence, candidates and local lines, the digest.
- `design/director-interface.md` §13.3, §13.8: the Director records cases silently, asks one "Is that clearer?" after clarifying, offers hold or workaround for a blocking Baton problem, and gives the digest.
- `design/runtime.md` §8.8, §8.10: the circuit breaker for repeated identical failures.
- `design/recipes.md` §5.1: optional `upstream:` entry; baselines shipped with a recipe; the contract consistency check at build and vendor time.
- `design/versioning.md` §14: the local line recorded per run; rebase on upstream upgrade.
- `design/platform-and-security.md` §15.3: `baton simulate` gains case replay and pre-release runs of shipped recipes.
- `design/workers.md` §6.4: harness-specific Director notes in the shipped harness data.
- `principles.md` §2: concept-budget entries if any term becomes user-visible.

### Manual edits (anticipated)

- `manual/user/`: what Baton adjusts for the owner and how to undo it; the digest; the blocked-run choice. Settled with Design.

### Decisions

- [0185](../decisions/0185-self-improvement-direction.md) (accepted): setting changes only through the digest; process statistics now (2026-11-process-stats); baselines from the owner's own runs for now.
- [0180](../decisions/0180-worker-failures-escalate.md) (accepted): explicit worker failures escalate; open question 2 would extend it.
- [0183](../decisions/0183-disposition-evidence-in-the-tree.md) (accepted), item 4: rejected results and failed gates keep their automatic retries today.
- [0179](../decisions/0179-trial-and-shadow-routing-details.md) (accepted), items 1 and 4: a trial never lowers a step's tier; the daily budget.
- [0181](../decisions/0181-first-use-feedback-routing-and-answers.md) (accepted): answers last across rounds, so a re-asked question is a detectable fault.
- [0184](../decisions/0184-answers-outside-a-blocked-step.md) (accepted): a completed result may carry questions on its guesses; such guesses are themselves a measure (track B).
- [0026](../decisions/0026-judges.md) (accepted): judges from a different vendor.
- To write once the owner decides: open questions 1 to 7.

## Plan

Sketch only; slices get criteria after Request and Design are approved (major). Depends on [2026-11-process-stats](2026-11-process-stats.md) for track B. Ordered so each slice pays off on its own, even if nothing ever goes upstream.

### Capture and classify, with a repro bundle

- **Outcome:** the Director records cases silently, asks "Is that clearer?" after clarifying, and for a Baton problem writes a repro bundle and offers hold or a workaround; deterministic detectors open cases from the record. Formalizes what the Director did by hand for `issues/`.
- **Effort:** M

### Circuit breaker

- **Outcome:** a repeated identical failure stops and reaches the owner as one choice, with the spend so far.
- **Effort:** S

### Contract checks before runs

- **Outcome:** recipe-builder and `vendor` check a recipe's contracts for contradictions; shipped recipes are simulated before release.
- **Effort:** M

### Baselines and detectors

- **Outcome:** baselines derived from the reference owner's runs ship with recipes; a step well off its baseline, guards holding, opens a case.
- **Effort:** M

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
