---
id: 2026-11-fit-check-work-scope
title: "Fit-check distinguishes developing a process from executing it and can recommend against Baton"
status: proposed
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
