---
id: 2026-11-eng-process-recipe
title: "An engineering recipe carries work from discovery through shipping and reflection using the eng-process workflow"
status: proposed
level: major
decisions: ["0138", "0139"]
touches: [design/recipes.md, design/gates-and-reviews.md]
manual: [recipes/eng-process.md, recipes/software-feature.md]
---

# An engineering recipe carries work from discovery through shipping and reflection using the eng-process workflow

## Request

### Problem

The owner asked: “Take a look at /mnt/d/rob/projects/eng-process and propose a change that creates a baton recipe to implement the same process as eng-process.”

Baton's `software-feature` recipe covers requirements, design, planning and accepted slices. It does not implement the complete engineering process the owner already uses: explicit scope and factual research, architecture approval, independent re-execution of checks, final verification, release preparation, and reflection with evidence-based learning.

Source inspected: eng-process v2.5.9, checkout HEAD `cd615b415a88199c81f0bf75261d98cad470dd28`; canonical `PROCESS.md`, `README.md`, and the plan, implement-slice, verify, ship, retro and inbox skills. This is a source baseline, not a dependency on that local directory. The source worktree was clean when inspected. Before implementation, check for upstream changes and freeze the actual source material used.

The proposal is a new, separately versioned `eng-process` recipe, leaving existing `software-feature@1` runs pinned to their process. Preserve the source's engineering outcomes and owner decisions, with every departure made explicit. Its vendor names and machine-specific runners belong in project worker selection, not recipe requirements.

### Acceptance criteria

- A self-contained `eng-process@1` package loads, validates, vendors, and appears in the shipped recipe catalog. It requires neither the source checkout nor an installed `eng` command.
- A source-to-recipe coverage table accounts for PROCESS sections 1–13 and every eng-* skill: implemented step, existing Baton machinery, project convention, approved departure, or explicitly excluded behavior. No silent omission is described as parity.
- Small, medium and large scenario tests demonstrate the source's distinct phase paths and checkpoints; missing required artifacts, approval, review or test evidence prevents dependent work.
- Medium/large plans have vertical slices, explicit exclusions, requirement IDs, automated commands, manual criteria, a demo script and mandatory independent plan review before CP-C. Small work gets one slice without a fabricated plan.
- One slice runs at a time. Implementation, advisory review where required, independent verification and CP-S acceptance precede the next slice. Rejection returns the appropriate work with feedback; bounded retries escalate.
- Verification re-executes criteria and the project's definition of done against identified code. Final PASS and CP-D precede release preparation; CP-P records the owner's release decision. Merge, deployment and push authority are explicit.
- Executable acceptance specs preserve REQ traceability, approved spec/DSL interface identity, changed assertion-body review, and re-approval when required. Tests distinguish source warning behavior during implementation from final verification failure.
- Research records source revisions/read dates and verification status, separates facts from recommendations, and carries evidence into architecture and planning.
- Reflection scores due predictions, examines findings and evidence, processes friction/adoption and time/waste, and proposes concrete improvements. Changes to process or shared lessons require owner approval; it cannot silently edit a pinned recipe.
- Resume, adoption and backing up demonstrate that stale downstream approvals cannot authorize changed upstream work. Reports and manual steps identify readiness and partial review coverage.
- Owner documentation explains the phases, approvals, review policy, adoption, spec locking, release permissions and differences from eng-process and software-feature.

### Open questions

These recommendations are proposals, not owner decisions. Settle them together before Design; record each durable choice in a decision record and add it to `decisions:` and the docs index.

1. **Session stops and project WIP?** Recommend owner checkpoints remain mandatory, with each phase a separate worker dispatch; Baton may continue between non-checkpoint phases. Sequential slices are recipe-local. The source's literal one-phase-per-session and one-project-phase limits differ from Baton's multi-run model. Does the owner require project-wide WIP enforcement and a stop after every phase?
2. **Executable-spec adoption?** The plan skill initializes specs for new medium/large plans, while PROCESS section 13 grandfathers existing projects until opt-in. Recommend that distinction, and an explicit exception for projects without an applicable API/UI (CLI/library projects need appropriate channels). Confirm whether to retain pytest/API/UI conventions exactly or use project-specific equivalents.
3. **Release authority?** Recommend explicit project authorization, ask before pushes by default, and owner-controlled merge/deploy. The source permits automatic docs-only pushes to main; carrying that exception over needs an explicit decision. This proposal grants no push authority.
4. **Project support behavior?** Recommend resume/handoff, research staleness, scratch-note ownership, friction recording, brownfield readiness and prediction scoring be covered. Keep inbox/backlog management outside this recipe, using Baton's existing optional notes/framing where appropriate. Confirm this boundary: automatic inbox-prefix capture and rotation are source behaviors but exceed a single work-item recipe and touch Baton's backlog non-goal.

## Design

Design awaits Request approval and the decisions above. The mapping below is a feasibility outline for review, not an approved step graph or executable recipe.

### Proposed process mapping

| Source activity | Proposed Baton expression | Levels / owner checkpoint |
|---|---|---|
| Triage and readiness | Triage result plus adoption crosswalk and prerequisite checks | all; small / medium / large |
| Discover | Requirements, metric, scope baseline, acceptance examples | medium/large; CP-A |
| Scope | Explicit in/out relative to approved baseline; cuts are project deliverables | large; source's CP-A relationship needs precise approval ordering |
| Research | Read-only factual codebase research with file/line and provenance | medium/large; CP-R required for large, optional medium |
| Architecture | Contracts, data, sequences, failure/rollback, security, observability; advisory review | large; CP-B |
| Plan | Vertical slices and executable specs where applicable; independent blocking plan review | medium/large; CP-C |
| Slice delivery | Sequential foreach; implement, advisory diff review, separate verifying worker, human acceptance; bounded repair loop | all; CP-S per slice |
| Final verification | Re-run whole-increment criteria, DoD and acceptance channels, publish evidence and PASS/FAIL | all; CP-D |
| Ship | Prepare changelog/version/PR, verify CI; distinguish preparation from authorized external actions | all; CP-P |
| Reflect | Evidence-based retro and approved project improvements; shared recipe improvements are proposals | medium/large; small behavior must follow agreed source interpretation |

### Machinery and gaps to resolve

Use existing schemas, required packet inputs, human/script/review/findings gates, groups, effort budgets, workspace controls, publishing, revisions and expert routing. The Director coordinates; research, planning, verification and retro are worker dispatches. Source-specific planner names, implementer names, platform contact and timeout mechanics map to profiles, runtime supervision and SMEs.

Do not claim instructions alone enforce a required invariant. During Design, test the actual loader/runtime for conditional review skips, independent verifier eligibility, per-slice PASS requirements, final aggregation of group outputs, approval invalidation on revise, WIP scope and release authorization. A limitation becomes an explicit dependency or a separate proposed change, not an invented recipe field or hidden runtime expansion.

Approved spec identity needs special attention. Current protected-file gates compare dispatch with intake; design §9.4 explicitly defers an approval-time protected hash set. A spec changed between CP-C and implementation could otherwise escape that check. Evaluate a recipe-owned approved manifest artifact and deterministic checks over specs and the DSL public interface, including edits before dispatch, additions/deletions, re-lock/re-approval and assertion-body review evidence. Do not replace this with a prompt to avoid edits. Any required core extension needs separate approval.

Source details need explicit treatment: research rejection means redo rather than patch; changed design requires fresh approval; three failed fixes stop; review rejection requires evidence and risk acceptance belongs to the owner. The source's source-code line budget is guidance, not permission to omit tests. Safety skips escalate immediately. Two counted non-safety skips raise a redesign recommendation, never automatically modify a recipe.

### Doc edits

- `design/recipes.md` §5.7: add the shipped engineering recipe, level/checkpoint matrix and its relationship to software-feature.
- `design/gates-and-reviews.md` §9.4: document the agreed recipe-owned spec approval checks and their limits, without silently implementing the deferred core feature.
- `docs/README.md`: index newly recorded decisions and any new stable section, if needed.

### Manual edits

- `manual/recipes/eng-process.md`: new owner guide to the process, checkpoints, adoption, tests/specs, review exceptions and release authority.
- `manual/recipes/software-feature.md`: explain when to choose the complete engineering workflow.
- Update manual navigation and anchors as required; retain published anchors.

### Decisions

Decision [0138](../decisions/0138-eng-process-uses-baton-machinery.md): the owner chose process equivalence using Baton machinery, without requiring the eng-process CLI or duplicate authoritative state files. Decision [0139](../decisions/0139-eng-process-review-policy.md): medium/large plan review is blocking, code review is advisory, and vendor selection belongs to worker profiles. The remaining choices are open. The only currently proposed Baton decision, 0016 (optional telemetry), is unrelated. Existing Baton principles constrain the design: vendor-neutral recipes, deterministic enforcement, Director/worker separation, immutable pinned versions and owner-authorized process changes.

## Plan

Provisional slices; refine after Request and Design approval. Each implementation slice carries tests, design/manual updates and a Log entry, and follows the quick/background/full gates in AGENTS.md.

### Establish the process contract and first runnable path

- **Outcome:** Owner choices recorded; complete source coverage matrix and validated package implementing small work through verification and acceptance.
- **Criteria:** Loader/catalog/vendor checks; small path, single-slice fallback, missing evidence, failed verification and CP-S/CP-D rejection tests; support gaps disclosed before claiming parity.
- **Effort:** M

### Deliver discovery through approved planning

- **Outcome:** Medium/large paths publish research/design/architecture/plan deliverables with the correct prerequisites and checkpoint order.
- **Criteria:** Level matrix; missing/skipped inputs; mandatory plan review retries and owner waiver; advisory architecture findings; CP-A/R/B/C rejection; provenance and acceptance-example traceability tests.
- **Effort:** L

### Enforce specs and slice delivery

- **Outcome:** Sequential slices use reviewed plans, approved acceptance specs and independent re-execution before owner acceptance.
- **Criteria:** Spec and DSL drift before/during dispatch; re-approval; assertion-body review; advisory findings with dispositions; required security review; partial coverage; failed tests; retry limit; changed upstream artifacts and stale approvals; two-slice ordering tests.
- **Effort:** L

### Complete shipping, reflection and adoption

- **Outcome:** Release preparation, owner release decision, learning artifacts and cold resume/adoption work end to end.
- **Criteria:** Small/medium/large full scenarios; CI failure and unapproved external action; no inferred merge; due predictions and evidence; approved improvements; brownfield missing prerequisites; back-up and resume; no dependency on the source checkout or eng CLI. Manual examples and full suite pass.
- **Effort:** L

## Log

### Proposal drafted

- **Summary:** Inspected eng-process v2.5.9 and Baton's existing recipe/gate design; proposed a separate recipe, source coverage requirements, explicit decisions and staged acceptance tests. No recipe or runtime behavior implemented.
- **Baseline:** HEAD `46ec3a855c89` had a clean worktree and a recorded green full suite (1554 passed, 9 skipped).
- **Validation:** Documentation checks passed (193 tests after recording 0138; rechecked after 0139). Broad quick gate outside the sandbox: 1246 passed, 3 skipped. The first sandbox run reported failures and was interrupted by a server restart; the unsandboxed rerun passed.
- **Review:** Awaiting owner answers to the Request's open questions; Design and Plan remain provisional.
- **Owner decision:** 2026-11-12, “Use Baton machinery (recommended)” (0138). “Blocking plan, advisory code (recommended)” (0139). Request as a whole is not yet accepted.
- **Accepted:** No; proposal only.
