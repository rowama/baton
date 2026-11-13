---
id: 2026-11-recipe-implementation-discovery
title: "Recipe builder discovers implementation options early enough to shape the process, or includes discovery in the generated recipe"
status: in-progress
level: standard
decisions: ["0141", "0140", "0099", "0104", "0108", "0097"]
touches: [design/recipes.md, design/experts.md]
manual: [recipes/recipe-builder.md]
---

# Recipe builder discovers implementation options early enough to shape the process, or includes discovery in the generated recipe

## Request

### Problem

Owners may know the outcome they want without knowing existing approaches that could implement it. Baton should discover and compare those approaches before committing to an unsuitable development process. The owner's examples include n8n, Temporal, LangGraph, BPMN, CMMN, and custom combinations of SOPs, artifacts, templates and software. These illustrate possible targets; they are not an exhaustive list or endorsements.

Current [recipe-builder research](../../examples/recipes/recipe-builder/prompts/research.md) learns usual stages, standards, failure modes and deliverables. The [patterns file](../../examples/recipes/recipe-builder/static/patterns.md) includes research, options and a decision, but neither explicitly requires implementation-option discovery or determines its timing. Research skips the simple level. Project SME consultation is available, but its default requirements do not guarantee web access and optional advice does not ensure required discovery or downstream handoff.

Choosing between a procedures-and-training package and deployed software may change the recipe's stages. Choosing among options that the same development graph supports can be left to each project run. The Director cannot add or reorder stages after discovering this distinction during execution (§1.4).

Requested by the owner, 2026-11-12, following agreement with the timing distinction in decision 0141. This is separate from [fit-check work scope](2026-11-fit-check-work-scope.md). Level standard: versioned recipe contracts, prompts, patterns and checks using existing runtime mechanisms. Implementation has not been requested.

### Scope

- Recognize material implementation uncertainty and determine whether discovery belongs in the builder or the generated recipe.
- Produce sourced comparisons, recommendations and consequential owner choices, with reliable downstream handoff.
- Extend design, audit and package validation to preserve timing, generality and research requirements.
- Excluded: an engine directory, built-in integrations/exporters, operating external systems, a universal preferred target, new SME subjects or dynamic recipe rewriting. Fit-check's verdicts remain the separate proposal's responsibility.

### Acceptance criteria

- The builder identifies material unresolved implementation choices even when the owner names no candidates. It records the evidence for discovery and its timing, or why discovery is unnecessary. Triggers identify questions; they never select a technology by keyword alone.
- Named targets are distinguished as firm constraints, preferences or examples. Settled approaches avoid unnecessary comparisons; contradictory evidence is surfaced rather than silently overriding the owner.
- Choices affecting the agreed recipe's stages, workers, artifacts or checks are researched during authoring and resolved before finalizing those parts. Necessary early discovery cannot disappear because the initial complexity estimate was simple.
- Choices that the graph can accommodate become explicit discovery and decision work in the generated recipe, before dependent work. The builder explains why deferral is appropriate and what output and approval it requires.
- Research produces a proportionate shortlist, criteria tied to requirements, sources with read dates/version context where relevant, tradeoffs, exclusions, uncertainty and a recommendation. Consider existing tools, frameworks, standards, procedures and custom work where relevant; require neither a fixed number nor an irrelevant alternative from every category.
- Current external claims require a research-capable worker and actual evidence. Missing access/evidence and unresolved consequential choices use existing blocked/question/escalation paths. Unsupported claims are never marked researched or owner-confirmed.
- Consequential choices are confirmed in the owner's terms and carried by declared inputs into dependent work. A recommendation alone cannot satisfy a required owner decision. Rejection, revision and resume preserve the applicable evidence and decision.
- The owner's generality is preserved: a future job's target is a run-specific value unless the agreed recipe scope is target-specific. Deferred discovery is a settled requirement of the generated process, not permission to pass an unresolved builder decision through the ledger checker.
- Audit rejects missing discovery, unsupported claims that alternatives fit the graph, assumed owner choices, and deferred discovery without stages/decisions/handoffs. Mechanical checks reject malformed records or missing declared dependencies/approvals; semantic adequacy remains an independent judgment.
- An existing recipe is recommended only if its actual process accommodates required discovery; a matching domain label is insufficient. Generated packages demonstrate findings and recorded choices reaching dependent packets; missing required inputs or approval prevents advancement.
- New builder packages load/plan at every level; pinned versions retain their behavior. Preserve no-open-ledger and instance-leak checks. Automated tests demonstrate contracts and execution, while recorded actual-worker scenarios demonstrate discovery quality and timing; scripted outputs alone do not prove judgment quality.

## Design

### Proposed behavior

Extend existing responsibilities. Specify the versioned records and recipe flow before implementation:

| Responsibility | Required result |
|---|---|
| Profile | Identify uncertainty, constraints/preferences/examples, discovery signals, and whether choices could change the graph for the owner's chosen scope. Explain timing or why discovery is unnecessary. |
| Research | Compare plausible approaches with evidence and explain what each requires from development. Return focused owner questions when a consequential choice remains. |
| Design | Shape the recipe around settled structural choices, or explicitly include research, a decision and downstream consumers in the generated recipe. Justify the graph's ability to accommodate deferred alternatives. |
| Audit | Check timing, evidence, owner authority, generality and the actual research-to-decision-to-design handoff against the patterns/readiness rubric. |
| Generate/accept | Preserve the approved flow, capabilities, artifacts and checks in a runnable package; explain when the owner chooses an implementation in its walkthrough. |

Research may refine the timing assessment. A structural choice discovered during design returns to research/owner input through declared flow; the Director cannot invent stages. A generated run that discovers its graph is inadequate uses existing revision/escalation or a new recipe version.

Prefer the existing ledger and recipe artifacts. Distinguish "which target will this future project use?" from the confirmed requirement "each run compares targets and records a choice before design." The latter can be settled during authoring without choosing the future value. Genuinely unresolved builder requirements remain `open` and block generation; never relabel an unanswered question as confirmed to satisfy the checker.

Implementation design must address `research.applies_to: [standard, complex]`: necessary early discovery needs a reachable path under declared levels/steps while simple, settled work stays proportionate. Specify and test triage/applicability rules before implementing; dispatching a skipped step is not a solution.

Use schema/script gates for mechanically verifiable records, required evidence fields, dependencies and approvals; use independent audit for relevance and adequacy. Demonstrate how the actual owner response reaches the consuming packet rather than accepting a worker's claim of approval. Preserve bounded retries and existing escalation behavior.

Ordinary research steps provide required work and referenceable outputs. Project SME advice can supplement them, platform SMEs can clarify infrastructure constraints, and process SMEs advise on Baton recipes. SME answers enter step work only through owner-approved promotion (§12.2); consultations do not replace gates. Declare `web_access` where current external research is required rather than relying on default SME eligibility.

The generated recipe coordinates development. Domain implementation targets can be part of agreed scope or run inputs; worker models/vendors and machine execution settings remain separate. Clarify the generator's broad "name no ... tool" wording so it preserves legitimate target requirements without weakening worker neutrality.

Publish the next available recipe-builder version, reconciling shared prompt/schema/version changes from the fit-check proposal before shipping both. Neither proposal is contingent on implementing the other first. Existing pinned packages remain untouched (§5.8); no new runtime concept is proposed.

### Doc edits

- `design/recipes.md` §5.7: discovery triggers/timing, builder responsibilities, level applicability, generated-recipe requirements and version notes. The accepted future rule is recorded here now, distinguished from shipped behavior.
- `design/recipes.md` §5.3: any mechanical discovery checks added to the package checker, with their limits; preserve ledger/instance-leak rules.
- `design/experts.md` §12.1 and §12.2: clarify subjects and optional advice versus required research/decision artifacts, retaining isolation and promotion.

### Manual edits

- `manual/recipes/recipe-builder.md`, through `manual/recipe-sources/recipe-builder.md`: explain that owners need not know target names, early versus per-project choices, sources/tradeoffs, handling of supplied targets and missing research access. Include examples of both timings and a settled/simple case.
- Regenerate with `tools/build_manual.py`; run `tools/manual_anchors.py` if headings are added, preserving published anchors. Update the manual in the same slice as each visible behavior change.

### Decisions

- [0141](../decisions/0141-implementation-discovery-timing.md): accepted discovery responsibility, timing and owner authority; exact contracts and flow are implementation design work within this policy.
- [0140](../decisions/0140-fit-check-assesses-requested-work.md): development/execution separation; discovery does not authorize changing the owner's goal.
- [0099](../decisions/0099-owner-owns-generality.md): the owner controls specialization and generality.
- [0104](../decisions/0104-patterns-file.md): the design consumes and independent audit enforces reusable patterns.
- [0108](../decisions/0108-recipe-check-command.md): preserve deterministic ledger checks; a deliberate future decision differs from an open builder requirement.
- [0097](../decisions/0097-builder-never-edits-vendored.md): publish new package versions and preserve pinned recipes.

No relevant proposed decision remains open. Bring additional policy questions discovered during implementation design to the owner before choosing.

## Plan

### Discover choices that shape the recipe

- **Outcome:** the builder recognizes material uncertainty and resolves structural choices early enough to shape the process.
- **Criteria:**
  - Specify/implement discovery, timing and evidence records and the reachable research/owner-response path, including initially simple and already-settled cases.
  - Update prompts, schemas, patterns and readiness checks together. Verify missing required evidence/approval blocks the affected work and the selected approach reaches design.
  - Demonstrate early research of materially different procedures/training and software deliverables without requiring a particular option to win.
  - Update package versions, design, manual and fixtures; pass the quick gate, commit, then start the exact SHA's full suite.
- **Effort:** L

### Generate processes that make their own implementation choice

- **Outcome:** appropriate generated recipes perform discovery and record a choice before dependent work, preserving generality.
- **Criteria:**
  - Generate research, decision and consuming steps with required capabilities; load/plan the package at every level and exercise decision/rejection/revision/resume.
  - Demonstrate that findings and owner choice reach downstream packets; missing inputs/approval cannot advance work.
  - Verify deliberate deferral without weakening open-ledger rejection, leaking instance values or fixing an unsupported target into a reusable recipe.
  - Extend audit/package checks, existing-recipe matching and the walkthrough/manual; verify old pinned builder versions remain usable.
- **Effort:** L

### Demonstrate discovery quality and finish

- **Outcome:** actual-worker evidence demonstrates useful discovery and appropriate timing with proportionate effort.
- **Criteria:**
  - Record scenarios for an owner unaware of candidates, structural choice, alternatives fitting one graph, firm target/preference/example, simple settled work and missing evidence/access. Capture timing, sources, recommendation, owner response and resulting recipe.
  - Review usefulness/timing without hard-coded technology winners; record limitations and distinguish judgment from mechanical guarantees.
  - Resolve contrary findings with meaningful regressions, demonstrate every acceptance criterion and finish only with a green full suite on the exact finish SHA (§17.1).
- **Effort:** M

## Log

### Proposal and accepted timing policy

- **Commit:** 2026-11-recipe-implementation-discovery: propose discovery timing and handoff
- **Summary:** Recorded decision 0141, this separate proposal, its register row and future design rules. Inspected builder prompts, applicability, ledger/checker rules and SME isolation. No executable recipe or runtime behavior changed.
- **Review:** Distinguishes required research from optional advice, structural choices from per-run choices, and unresolved requirements from an approved future decision stage. Documentation validation uses the quick gate; the exact commit's full-suite result is in the test ledger.
- **Accepted:** Direction and timing policy yes, 2026-11-12: "I like the timing distinctions. I think we're on the same page, so please produce a change proposal for this also." Implementation remains proposed.

### Slice 1: discover choices that shape the recipe

- **Commit:** 2026-11-recipe-implementation-discovery: Slice 1, builder v3 discovers shaping choices
- **Summary:** recipe-builder@3 (v2 kept as `tests/fixtures/recipes/recipe-builder-v2`, loaded and checked unchanged). New `discovery` records (`schemas/discovery.json`; carried by the profile, research and design outputs; the ledger file is now `{ledger, discovery}`, `schemas/ledger_file.json`). The profile records each material choice, how a named target was named (`firm_constraint`, `preference`, `example`, `none`) and its timing; the profile schema rejects `simple` beside a `before_design` choice, which keeps research reachable without dispatching a skipped step. Research compares options with dated sources, returns `blocked` for the owner, and returns the choice only as `decided` with a confirmed `decision` ledger entry (the schemas refuse an unanswered one). Design carries the records; audit rubric checks 16 to 20; patterns gained "Discovering implementation options"; generate and its package review also know the deferred form, and the generator's "name no tool" wording now separates worker models and vendors from legitimate delivery targets. `baton recipe check --require-discovery` checks form, owner authority (a confirmed `decision` with the owner's words), comparison form, and, for the deferred timing, that the recipe's research, decision and consuming steps exist and are wired. Manual: recipe-builder gained "Choosing how it will be done".
- **Tests:** `test_recipe_check.py` (decided/unconfirmed/undated/deferred wiring), `test_recipe_builder.py` (schemas, level rule, v2 fixture, vocabulary agreement, prompts), `test_recipe_builder_runs.py` (a standard run: research blocks, the owner's confirmed answers reach the retried research packet, the decision and comparison reach the design packet, the draft passes the checks; a recommendation without the owner's decision fails the generate gate; an unanswered choice is refused by the research schema).
- **Limits:** the owner's words in the `decision` entry are copied by the worker from `prior_feedback.answers`; the checker proves they are present and the entry is confirmed, and the runtime's `human_decision` event is the record of what was said; the audit judges that they match. A shaping choice found during design returns as `blocked` and a revision of research (Decision: 0141: the Director cannot add stages).

### Slice 2: generate processes that make their own implementation choice

- **Commit:** 2026-11-recipe-implementation-discovery: Slice 2, generated processes carry deferred discovery
- **Summary:** The deferred form was specified in Slice 1's schemas, prompts and checker; this slice demonstrates it end to end and finishes the walkthrough and matching rules. `generate` now tells the owner, in the walkthrough, when they will choose; `profile` matches an existing recipe only if its own steps do the discovery the job needs. Design doc §5.7 describes how the stages are written.
- **Tests:** a scripted builder run (profile `simple`, because the choice is deferred) produces a draft whose ledger file, research, decision and using steps pass `baton plan` and `baton recipe check --require-discovery`; the draft is vendored and run: findings reach the decision packet, nothing downstream is ready until the owner's gate approves, a rejection returns the choice with the same findings and the owner's note, and the approved second choice, not the first, reaches the dependent packet; a consumer that does not take the choice fails the generate gate; no `open` entry was needed for the deferral; a pinned `recipe-builder@2` (the fixture) still vendors, runs and produces a draft that passes the unchanged checks.
- **Limits:** the research stage of a generated process is only as good as its prompt for that job; Slice 3 records real-worker behavior.
- **Slice 1's full run:** red on `test_harness_tools.py::test_a_denied_tool_reroutes_without_spending_an_attempt` and `::test_absent_on_every_profile_escalates_at_once`, both time-sensitive and unrelated to the builder; they pass in isolation (7 passed) and the full run overlapped a second quick gate. No code change; the exact-SHA full suite is re-run on this slice's commit with the machine otherwise idle.
