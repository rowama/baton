---
id: 2026-11-fit-check-work-scope
title: "Fit-check distinguishes developing a process from executing it and can recommend against Baton"
status: done
level: standard
decisions: ["0140", "0029", "0134", "0135", "0136", "0097"]
touches: [design/recipes.md, design/adoption-and-framing.md, design/director-interface.md]
manual: [recipes/fit-check.md, recipes/baton-frame.md, recipes/recipe-builder.md, user/bring-an-existing-project.md]
---

# Fit-check distinguishes developing a process from executing it and can recommend against Baton

## Request

### Problem

The owner expects fit-check to recommend against Baton for unsuitable work while recognizing projects to develop business processes as eligible Baton work. Current fit-check v4 instead has only `fits`, `fits_per_occurrence` and `operations_engine`. Its [rubric](../../examples/recipes/fit-check/static/rubric.md) assumes that an unsuitable workload should become a software-development project. Its [profile prompt](../../examples/recipes/fit-check/prompts/describe.md) does not explicitly distinguish developing a process from executing its instances.

This can reject a development project because its eventual deliverable processes many transactions, has low inference needs, or requires a dedicated execution environment. It also cannot recommend a simpler alternative for a small task that does not warrant Baton coordination. The recent [adoption change](2026-11-adopt-recipe-selection.md) preserved these rules; it exposed the limitation rather than introducing it.

The intended deliverable may be a workflow targeting n8n, Temporal or LangGraph; a BPMN/CMMN process; or a custom combination of SOPs, artifacts, templates and software. Fit depends on the work Baton coordinates, not the target's name or execution model. This is consistent with the [recipe-builder change's operations-package scope](2026-11-recipe-builder.md), but its instruction to convert operations into development must also respect the owner's choice.

Requested by the owner, 2026-11-12. The owner accepted the policy recommendations, including retaining `fits_per_occurrence`, and requested this proposal. Implementation has not been requested. Level standard: versioned recipe behavior and aligned guidance, using existing runtime mechanisms.

### Scope

- A new fit-check version with an explicit assessment scope, a general negative verdict, and a rubric that values useful coordination and dependent reasoning.
- Consistent framing, recipe-builder and adoption guidance, including no automatic conversion of an execution goal into a development goal.
- Version compatibility, regression scenarios, owner-facing documentation and recorded behavioral evidence.
- Excluded: executing external workflows, integrating particular engines, adding a scheduler, or providing a maintained catalog of implementation targets. The owner's separate question about proactive discovery of implementation options is not authorization to add that feature here.

### Acceptance criteria

- The profile identifies the requested work and distinguishes process development from execution. Clear requests need no extra question; ambiguous or mixed requests use the existing structured-question/framing mechanisms rather than silently choosing a scope.
- A development project's verdict uses the development work's facts. Scenarios cover a high-volume automated workflow, an AI-integrated workflow, a BPMN/CMMN process, and a package of SOPs/templates/software. Target-system frequency, data load, duration or inference needs alone cannot reject development work.
- The new verdict schema allows exactly `fits`, `fits_per_occurrence` and `not_recommended`. Each verdict explains the assessment scope, reasons and a concrete next step. A negative result can recommend an appropriate simpler approach without requiring an operations engine or software project.
- Both a high-volume execution workload and a trivial task with little value from coordinated reasoning/handoffs can receive `not_recommended`. A recurring, substantive project-like task can receive `fits_per_occurrence`; adding an external scheduler cannot turn unsuitable execution into a fit.
- When execution does not fit, developing a replacement is offered separately. Accepting the verdict does not authorize that new project. Mixed goals keep the owner's original intent and selection visible.
- A suitable development project selects an existing recipe covering the whole work, or reports no matching recipe and offers recipe authoring. Missing recipe coverage is not a negative Baton-fit verdict; `software-feature` is not forced on non-software or mixed deliverables it does not cover.
- Optional project context, inference-first questioning, the existing verdict human gate and fit-check's minutes-long/no-file-reading scope remain. Adoption continues only with a fitting recipe under the established adoption policy; negative results start no adoption or substitute project.
- Existing pinned recipes and their `operations_engine` records remain readable and runnable. New catalog versions, starter selection, framing rubric consumption, profile handoff to recipe-builder, fixtures and golden records agree on their versioned contracts.
- Automated tests demonstrate schemas, packet handoffs, compatibility and state transitions. Recorded worker scenarios demonstrate interpretation of scope and recommendations; scripted outputs alone are not evidence of an actual worker's judgment. The manual agrees with the implemented behavior.

## Design

### Proposed behavior

Use fit-check v5 (or the next unused version at implementation). First establish what work is being assessed, then profile and score that work. A target description may accompany a development scope, but it is not the occurrence being scored. Keep the two-step describe/assess structure and existing human gate.

Replace the binary Baton-versus-operations-engine rubric with Baton-fit reasoning. Include coordination overhead, dependent reasoning and reliable handoffs alongside operational constraints. Avoid universal daily-frequency or duration cutoffs. Reasons must refer to the assessed work and distinguish observed facts from confirmed assumptions. The exact schema and rubric rows are implementation design details to be documented and tested before changing consumers.

Keep the three outcomes from decision 0140. A negative next step need not involve Baton. If a separate development project is offered, the Director confirms that new goal through existing owner selection/confirm-back before starting it. Do not infer approval of a new project from acceptance of the fit verdict.

Align framing and recipe-builder wording so that operations are neither categorically rejected by domain label nor automatically rewritten into development work. Recipe-builder still produces a Baton recipe; the recipe can coordinate development of an external process. It does not thereby become an exporter for external engines. Preserve adoption's established distinction between a fitting recipe and no fitting recipe, and its stop behavior for other verdicts.

Change published recipe contracts through new versions (§5.8), including framing or recipe-builder if their package contents change. Check all consumers of the profile and shared rubric. Do not rewrite old vendored copies, historical results or completed change logs. No new runtime concept is proposed.

### Doc edits

- `design/recipes.md` §5.7: scope, rubric, verdicts, recipe selection and separate development offer; version notes for every changed package. The accepted future rule is recorded there now, explicitly distinguished from shipped v4.
- `design/adoption-and-framing.md` §11.1 and §11.6: consistent goal separation, fit-check referral and adoption routing; remove dependence on `operations_engine` in the new flow.
- `design/director-interface.md` §13.3 and §13.8: align the mirrored Director guidance and owner-facing explanation; accepting a negative verdict does not select a replacement goal.

### Manual edits

- `manual/recipes/fit-check.md`, through `manual/recipe-sources/fit-check.md`: explain assessed scope, the three new verdicts, recurrence and positive/negative examples.
- `manual/recipes/baton-frame.md` and `manual/recipes/recipe-builder.md`, through their recipe sources: distinguish the process being developed from the Baton recipe coordinating its development, and explain separate owner selection.
- `manual/user/bring-an-existing-project.md`: development projects remain eligible even when their deliverables execute elsewhere; explain stopping after a negative result.
- Regenerate the manual with `tools/build_manual.py`; update anchors with `tools/manual_anchors.py` if topics/headings are added, retaining published anchors.

### Decisions

- [0140](../decisions/0140-fit-check-assesses-requested-work.md): accepted policy, including the general negative verdict, development/execution distinction, recurrence and no silent change of goal.
- [0029](../decisions/0029-fit-check-infers-first.md): infer first and use existing structured questions for unresolved scope.
- [0134](../decisions/0134-fit-check-takes-optional-project-context.md): preserve optional text context and no file access; 0140 supersedes its unchanged-rubric/verdict restriction for the future version.
- [0135](../decisions/0135-director-writes-the-project-context.md) and [0136](../decisions/0136-adopt-without-recipe-returns-recipe-needed.md): preserve existing-project context and find/build/stop adoption flow.
- [0097](../decisions/0097-builder-never-edits-vendored.md) and §5.8: preserve pinned packages and publish changed recipes as new versions.

No relevant proposed decision remains open. The separate discovery discussion is outside this proposal.

## Plan

### Scope-aware fit-check and aligned entry paths

- **Outcome:** the new recipe assesses requested work, permits a general negative verdict, and carries that meaning consistently through framing, recipe-builder and adoption guidance.
- **Criteria:**
  - Specify and implement profile/verdict contracts and rubric; validate positive, recurring and negative outputs and reject the old negative value under the new version.
  - Verify optional context, mixed/ambiguous scope questions, recipe matching and profile handoff with automated packet/schema tests.
  - Update all affected recipe versions and consumers together; test preserved old pinned recipes/records and new starter/catalog selection, updating content-hash goldens.
  - Test that a negative verdict starts no adoption or replacement project; keep the separate choice explicit in prompts and Director guidance.
  - Update the design, manual and generated files in the same slice. Run the quick gate, commit, then start the full suite on that SHA.
- **Effort:** L

### Demonstrate judgments and finish

- **Outcome:** recorded evidence shows that actual workers distinguish developing a process from executing it and can recommend against Baton for unrelated unsuitable work.
- **Criteria:**
  - Exercise paired development/execution cases, mixed goals, a trivial task and suitable recurring work using actual workers. Record inputs, scope, verdicts, reasons, owner review and limitations in this Log; do not claim model quality from fake outputs or prompt-string assertions.
  - Resolve any contrary results in the relevant prompts/contracts and add meaningful regressions. Do not require one verdict where the supplied facts genuinely leave fit uncertain; require honest scope and supported reasoning.
  - All Request criteria have test or recorded scenario evidence. Mark done only after implementation and acceptance evidence, with a green full suite on the exact finish SHA (§17.1).
- **Effort:** M

## Log

### Proposal and accepted policy

- **Commit:** 2026-11-fit-check-work-scope: propose assessment of requested work
- **Summary:** Recorded the owner's accepted policy as decision 0140, this proposed change, its register row and the future rule in §5.7. No recipe or runtime behavior changed. Implementation-option discovery remains a separate discussion.
- **Review:** Checked against shipped fit-check v4, framing and recipe-builder prompts, adoption decision 0134, and versioning rules. Documentation validation uses the repository quick gate; the exact commit's full-suite result is recorded in the test ledger.
- **Accepted:** Policy yes, 2026-11-12: "Concur with your recommendations." The owner requested a proposal; implementation remains proposed.

### Slice 1: Scope-aware fit-check and aligned entry paths

- **Commit:** 2026-11-fit-check-work-scope: Slice 1, fit-check v5 and aligned guidance
- **Summary:** `fit-check` is now version 5: the profile has `scope` (`developing_a_process`, `executing_a_process`, `other_work`, with a described-never-scored `target`) and `work`; the verdict is `fits`, `fits_per_occurrence` or `not_recommended` and names `assessed_work`, each reason's `basis` (`stated` or `assumed`), and, for a negative, an `alternative` and an optional separate `development_offer`; a recipe may be named for either positive verdict. The rubric has five rows (coordination, dependent reasoning, recurrence, duration, record) with no standalone frequency or duration cutoffs. `recipe-builder` is version 2 (profile prompt and patterns no longer convert operations into development; the target is a deliverable fact). The built-in `baton-frame@1` prompt and rubric description are reworded in place: built-ins ship with the runtime and are never vendored or pinned, so they have no separate published versions. Adoption guidance (`adopt` steps, Director skill, §13.3) stops on `not_recommended` and makes the development offer the owner's separate choice. The pre-change v4 package is kept at `tests/fixtures/recipes/fit-check-v4` to prove pinned v4 stays loadable and its `operations_engine` records stay valid under their own schema. Tests moved from `fit-check@4` to `@5`; goldens regenerated. Repair: the slice's first full run was red (`test_records_golden`: the describe record golden pinned the old `BAD_PROFILE` text); regenerated in a following commit.
- **Tests:** `tests/test_fit_check_scope.py` covers the schemas (exactly three verdicts, negative needs an alternative and no recipe, positive forbids both, v4 records still valid under v4), the scope kinds, the packet inputs and human gate, and the prompts/rubric wording across fit-check, framing and recipe-builder. Existing suites cover framing selection, packet handoff and adoption's stop steps.
- **Manual:** `recipes/fit-check.md`, `recipes/baton-frame.md`, `recipes/recipe-builder.md` (via their sources) and `user/bring-an-existing-project.md`, regenerated; no anchors added or removed.
- **Not done:** slice 2. The acceptance criteria that depend on a worker's actual judgment (paired development/execution cases, mixed goals, a trivial task, suitable recurring work) have no recorded evidence yet, and scripted outputs cannot stand in for it. Status stays `in-progress`.

### Slice 2: Recorded worker scenarios

- **Commit:** 2026-11-fit-check-work-scope: Slice 2, recorded worker scenarios
- **Method:** fit-check@5 vendored in a scratch project (`baton init`), one real run per scenario. `describe` by the `claude-code-claude-sonnet-5-5` profile and `assess` by the `codex` profile (a different vendor), each a headless dispatch with no scripted output. No `context` input; the catalog listed `software-feature@1`, `backyard-project@1`, `recipe-builder@2`. The human verdict gate was left pending (not an owner review); no assumptions were confirmed by a person, so most reasons carry `basis: assumed`.
- **Results** (inputs abbreviated):

| Scenario | Scope the profile chose | Verdict | Recipe / alternative |
|---|---|---|---|
| Build an n8n workflow for ~5,000 daily refunds | developing_a_process (target kept apart, not scored) | `fits` | `software-feature@1` |
| Process each of ~5,000 daily refunds within seconds, no person | executing_a_process | `not_recommended` | existing tool or operations engine; separate development offer, stated as not chosen |
| Design and test a LangGraph email classify-and-reply workflow | developing_a_process | `fits` | `software-feature@1` |
| Model onboarding as a BPMN diagram, document handoffs | developing_a_process | `fits` | none: recipe-builder@2 |
| SOPs, forms and a small tracking tool for clinic intake | developing_a_process | `fits` | none: recipe-builder@2; said `software-feature` does not cover the whole deliverable |
| Set up a vending business and run it day to day | other_work, two parts | blocked, one multi-select question | not decided silently; the Director would suggest framing |
| Rename one file | other_work | `not_recommended` | ask an assistant directly |
| Monthly board report, independent review, CFO sign-off | executing_a_process | `fits_per_occurrence` | none: recipe-builder@2 |

- **Assessment against the criteria:** the paired development/execution refund cases reached opposite verdicts for the stated reasons: the development case's volume was not held against it, and the execution case was rejected on its own frequency and latency. The package and BPMN cases did not force `software-feature`. The trivial task and the high-volume execution both got `not_recommended` with a non-software alternative. The mixed goal was blocked with a question rather than narrowed. A recurring, substantive task got `fits_per_occurrence`.
- **Limitations:** one run per scenario, one worker pair, no repeats, so variance is unmeasured. The two `software-feature` choices (n8n, LangGraph) are judgment calls the owner may disagree with, since both are workflows rather than ordinary application features. No scenario was ambiguous between developing and executing within a single request, and none was a substantive one-off execution, so those boundaries are untested. No owner review of the verdicts has taken place. No prompt change was needed, so no regression was added.
- **Accepted:** results yes, 2026-11-12: "Accepted, mark done", including the two `software-feature` choices (n8n, LangGraph). Status `done`; the full suite on the finish SHA is recorded in the test ledger.
