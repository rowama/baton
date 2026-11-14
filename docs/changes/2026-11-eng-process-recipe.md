---
id: 2026-11-eng-process-recipe
title: "An engineering recipe carries work from discovery through shipping and reflection using the eng-process workflow"
status: proposed            # ON HOLD: after 2026-11-project-policy (2026-11-project-documents and 2026-11-tailoring-axes are done)
level: major
decisions: ["0138", "0139", "0149", "0142", "0146", "0144", "0147", "0143", "0050"]
touches: [design/recipes.md, design/gates-and-reviews.md, design/adoption-and-framing.md]
manual: [recipes/eng-process.md, recipes/software-feature.md]
---

# An engineering recipe carries work from discovery through shipping and reflection using the eng-process workflow

## Request

### Problem

The owner asked: “Take a look at /mnt/d/rob/projects/eng-process and propose a change that creates a baton recipe to implement the same process as eng-process.”

Baton's `software-feature` recipe covers requirements, design, planning and accepted slices. It does not implement the complete engineering process the owner already uses: explicit scope and factual research, architecture approval, independent re-execution of checks, final verification, release preparation, and reflection with evidence-based learning.

Source inspected: eng-process v2.5.9, checkout HEAD `cd615b415a88199c81f0bf75261d98cad470dd28`; canonical `PROCESS.md`, `README.md`, and the plan, implement-slice, verify, ship, retro and inbox skills. This is a source baseline, not a dependency on that local directory. The source worktree was clean when inspected. Before implementation, check for upstream changes and freeze the actual source material used.

The proposal is a new, separately versioned `eng-process` recipe, leaving existing `software-feature@1` runs pinned to their process.

**Amended 2026-11-14.** eng-process is Baton's *one* software recipe (Decision [0149](../decisions/0149-one-software-recipe.md)): tailored deeply enough to serve a personal utility and a consequential production system with the same, familiar process, so that `software-feature` can be retired. Three changes it builds on:
- **Tailoring axes** (`2026-11-tailoring-axes`, done): the source's small, medium and large become ratings on four axes, so each concern changes only the phases it affects (`docs/catchall/project-process-linkage.md` §4).
- **Project documents** (`2026-11-project-documents`, done): each increment builds on the project's settled architecture, conventions and decisions instead of rediscovering them.
- **Project policy** (`2026-11-project-policy`, proposed): rating floors and release authority come from it. Preserve the source's engineering outcomes and owner decisions, with every departure made explicit. Its vendor names and machine-specific runners belong in project worker selection, not recipe requirements.

### Acceptance criteria

- A self-contained `eng-process@1` package loads, validates, vendors, and appears in the shipped recipe catalog. It requires neither the source checkout nor an installed `eng` command.
- A source-to-recipe coverage table accounts for PROCESS sections 1–13 and every eng-* skill: implemented step, existing Baton machinery, project convention, approved departure, or explicitly excluded behavior. No silent omission is described as parity.
- **Four axes.** The recipe rates `discovery`, `coordination`, `assurance` (`confirm_lowest`) and `release`, each `low`/`medium`/`high`, with the triage criteria drawn from the nine concerns of `project-process-linkage.md` §4. Every phase is placed by the axes that call for it (Design, *Proposed process mapping*).
- **Scenarios across the range.** Scenario tests cover every axis at its lowest, each axis raised alone, and the six examples of `project-process-linkage.md` §4 (personal app, disposable prototype, small-team tool, file deleter, tenant authorization fix, storage migration). Each demonstrates its phase path and checkpoints, and shows that missing required artifacts, approval, review or test evidence prevents dependent work.
- **The lowest path is as light as `software-feature minor`:** one triage, then per slice implement, review where required, verify and accept, with no fabricated plan or architecture.
- **Increments build on the project.** The recipe declares optional project roles for the settled architecture, the conventions and the project's decisions (`many`). An inception run (discovery and coordination high) publishes architecture and conventions to stable paths, so later increments bind them; triage reads them when bound.
- **Policy is respected.** Project floors raise ratings (`2026-11-project-policy`); release actions go through the action permissions (§13.7), and the ship phase states the authority it acted under.
- **`software-feature` is retired, not removed.** Once eng-process is done, `software-feature` is marked retired in favor of eng-process. Catalog listings show it as retired, fit-check and framing propose eng-process for software work, and pinned and vendored copies keep working.
- Plans rated coordination medium or high have vertical slices, explicit exclusions, requirement IDs, automated commands, manual criteria, a demo script and mandatory independent plan review before CP-C (0139, read as coordination medium or high). At coordination low, work gets one slice without a fabricated plan.
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
3. **Release authority?** *Updated 2026-11-14:* Baton already enforces it. The action permissions (§13.7, Decision 0050) default to allowing docs-only and verified pushes, asking for others, and denying merge and deploy, and nothing ever pushes automatically. `2026-11-project-policy` makes them recorded project policy. Recommend: the ship phase prepares the release and records CP-P, and every push, tag, merge or deploy goes through those permissions. The source's automatic docs-only push becomes an allowed push the Director makes explicitly, never one the recipe makes on its own.
4. **Project support behavior?** Recommend resume/handoff, research staleness, scratch-note ownership, friction recording, brownfield readiness and prediction scoring be covered. Keep inbox/backlog management outside this recipe, using Baton's existing optional notes/framing where appropriate. Confirm this boundary: automatic inbox-prefix capture and rotation are source behaviors but exceed a single work-item recipe and touch Baton's backlog non-goal.
5. **How do the source's sizes map onto the axes?** Recommend the mapping in Design. Discovery and research follow `discovery`; scope, architecture and the reviewed plan follow `coordination`; verifier independence, security review and recovery evidence follow `assurance`; release preparation depth follows `release`. 0139's "medium/large" plan review becomes coordination medium or high. *Rationale:* each source phase exists for one kind of concern, so it should be triggered by that concern rather than by overall size.
6. **What is the minimum independent checking at the lowest assurance?** Recommend: a separate verifying worker for every slice at every rating, as the source requires. At assurance low it may share the implementer's vendor. Raise independence (different vendor), not the step count, with assurance. *Rationale:* independent re-execution is the source's core guarantee, and its cost at low risk falls by relaxing independence, not by skipping it.
7. **Which checkpoints combine for one-slice, low-rated work?** Recommend: when there is one slice and assurance and release are low, final verification and CP-D combine with that slice's verification and CP-S into one owner decision, and CP-P is asked only if a release action is wanted. Authority for external actions stays separate at every rating. *Rationale:* the same evidence reviewed twice costs the owner attention without adding assurance. *Caution:* the number of slices is not a rating, so Design must show this is expressible (for example, the plan's output deciding whether the final checks are a separate step) before it is promised.
8. **When does reflection run?** Recommend: as a phase when any axis is high (expressible: OR across the four axes), and otherwise as a short completion note (what surprised us, one improvement). The note is a field of the final verification result, so it needs no step that applies only when nothing is high, which the axes cannot express (no NOT or AND, 0147). *Rationale:* full retros pay off on consequential work, and a one-line note keeps the habit at almost no cost.
9. **How is `software-feature` retired?** Recommend: a recipe metadata field, `retired: {replaced_by: eng-process}`. Listings and summaries show it, fit-check and framing prefer the replacement, `vendor` warns, and pinned runs are untouched. The recipe stays in the package as the §5.1 example and test fixture. *Rationale:* retiring without removing breaks nothing, and removing it would break the design's example and much of the test suite for no gain.

## Design

Design awaits Request approval and the decisions above. The mapping below is a feasibility outline for review, not an approved step graph or executable recipe. It was amended on 2026-11-14 to place phases by axis (open question 5).

### Proposed process mapping

| Source activity | Proposed Baton expression | Applies when (axes) / owner checkpoint |
|---|---|---|
| Triage and readiness | Triage ratings on four axes, with reasons; bound project documents read; adoption crosswalk and prerequisite checks | always; triage gate (assurance always confirmed, `confirm_lowest`) |
| Discover | Requirements, metric, scope baseline, acceptance examples | discovery or coordination medium/high; CP-A |
| Scope | Explicit in/out relative to approved baseline; cuts are project deliverables | coordination high; source's CP-A relationship needs precise approval ordering |
| Research | Read-only factual codebase research with file/line and provenance | discovery medium/high; CP-R at discovery high |
| Architecture | Contracts, data, sequences, failure/rollback, security, observability; advisory review | coordination high or assurance high; CP-B |
| Plan | Vertical slices and executable specs where applicable; independent blocking plan review | coordination medium/high; CP-C (low: one slice, no fabricated plan) |
| Slice delivery | Sequential foreach; implement, advisory diff review, separate verifying worker (independence by assurance), human acceptance; bounded repair loop; security review and negative tests at assurance high | always; CP-S per slice |
| Recovery evidence | Backup, rollback or recovery rehearsal for destructive or hard-to-reverse changes | assurance high |
| Final verification | Re-run whole-increment criteria, DoD and acceptance channels, publish evidence and PASS/FAIL | always; CP-D (combined with CP-S for one low-rated slice, open question 7) |
| Ship | Prepare changelog/version/PR, verify CI; external actions only through action permissions | always; preparation depth and staged rollout by release; CP-P when a release action is wanted |
| Reflect | Evidence-based retro and approved project improvements; shared recipe improvements are proposals | phase when any axis is high; otherwise a completion note (open question 8) |

### Machinery and gaps to resolve

Use existing schemas, required packet inputs, human/script/review/findings gates, groups, effort budgets, workspace controls, publishing, revisions and expert routing. The Director coordinates; research, planning, verification and retro are worker dispatches. Source-specific planner names, implementer names, platform contact and timeout mechanics map to profiles, runtime supervision and SMEs.

Do not claim instructions alone enforce a required invariant. During Design, test the actual loader/runtime for conditional review skips, independent verifier eligibility, per-slice PASS requirements, final aggregation of group outputs, approval invalidation on revise, WIP scope and release authorization. A limitation becomes an explicit dependency or a separate proposed change, not an invented recipe field or hidden runtime expansion.

Approved spec identity needs special attention. Current protected-file gates compare dispatch with intake; design §9.4 explicitly defers an approval-time protected hash set. A spec changed between CP-C and implementation could otherwise escape that check. Evaluate a recipe-owned approved manifest artifact and deterministic checks over specs and the DSL public interface, including edits before dispatch, additions/deletions, re-lock/re-approval and assertion-body review evidence. Do not replace this with a prompt to avoid edits. Any required core extension needs separate approval.

Source details need explicit treatment: research rejection means redo rather than patch; changed design requires fresh approval; three failed fixes stop; review rejection requires evidence and risk acceptance belongs to the owner. The source's source-code line budget is guidance, not permission to omit tests. Safety skips escalate immediately. Two counted non-safety skips raise a redesign recommendation, never automatically modify a recipe.

### Doc edits

- `design/recipes.md` §5.7: add the shipped engineering recipe, its axis/checkpoint matrix, its project roles, and `software-feature`'s retirement; §5.1 and §5.3: the `retired` metadata field.
- `design/adoption-and-framing.md` §11.6 and §5.7's fit-check: prefer a retired recipe's replacement.
- `design/gates-and-reviews.md` §9.4: document the agreed recipe-owned spec approval checks and their limits, without silently implementing the deferred core feature.
- `docs/README.md`: index newly recorded decisions and any new stable section, if needed.

### Manual edits

- `manual/recipes/eng-process.md`: new owner guide to the process, checkpoints, adoption, tests/specs, review exceptions and release authority.
- `manual/recipes/software-feature.md`: say it is retired in favor of eng-process, and that pinned projects keep it.
- Update manual navigation and anchors as required; retain published anchors.

### Decisions

Decision [0138](../decisions/0138-eng-process-uses-baton-machinery.md): the owner chose process equivalence using Baton machinery, without requiring the eng-process CLI or duplicate authoritative state files. Decision [0139](../decisions/0139-eng-process-review-policy.md): medium/large plan review is blocking, code review is advisory, and vendor selection belongs to worker profiles. Decision [0149](../decisions/0149-one-software-recipe.md): eng-process is the one software recipe. Decisions [0144](../decisions/0144-tailoring-axes.md) and [0147](../decisions/0147-tailoring-axes-details.md): the axes it is rated on. Decisions [0142](../decisions/0142-project-documents-bound-by-role.md) and [0146](../decisions/0146-project-document-details.md): its project roles. Decisions [0143](../decisions/0143-project-policy.md) and [0050](../decisions/0050-action-permissions.md): floors and release authority. The remaining choices are open. The only currently proposed Baton decision, 0016 (optional telemetry), is unrelated. Existing Baton principles constrain the design: vendor-neutral recipes, deterministic enforcement, Director/worker separation, immutable pinned versions and owner-authorized process changes.

## Plan

Provisional slices; refine after Request and Design approval. Each implementation slice carries tests, design/manual updates and a Log entry, and follows the quick/background/full gates in AGENTS.md.

### Establish the process contract and first runnable path

- **Outcome:** Owner choices recorded; complete source coverage matrix and validated package implementing small work through verification and acceptance.
- **Criteria:** Loader/catalog/vendor checks; four axes and their triage criteria; lowest-everywhere path, single-slice fallback, combined checkpoints, missing evidence, failed verification and CP-S/CP-D rejection tests; support gaps disclosed before claiming parity.
- **Effort:** M

### Deliver discovery through approved planning

- **Outcome:** Medium/large paths publish research/design/architecture/plan deliverables with the correct prerequisites and checkpoint order.
- **Criteria:** Axis matrix (discovery and coordination raised); missing/skipped inputs; mandatory plan review retries and owner waiver; advisory architecture findings; CP-A/R/B/C rejection; provenance and acceptance-example traceability tests.
- **Effort:** L

### Enforce specs and slice delivery

- **Outcome:** Sequential slices use reviewed plans, approved acceptance specs and independent re-execution before owner acceptance.
- **Criteria:** Assurance raised (independence, security review, recovery evidence); spec and DSL drift before/during dispatch; re-approval; assertion-body review; advisory findings with dispositions; required security review; partial coverage; failed tests; retry limit; changed upstream artifacts and stale approvals; two-slice ordering tests.
- **Effort:** L

### Complete shipping, reflection and adoption

- **Outcome:** Release preparation, owner release decision, learning artifacts and cold resume/adoption work end to end.
- **Criteria:** The six example scenarios end to end; project roles bound by an increment after an inception run; policy floors; `software-feature` retired; CI failure and unapproved external action; no inferred merge; due predictions and evidence; approved improvements; brownfield missing prerequisites; back-up and resume; no dependency on the source checkout or eng CLI. Manual examples and full suite pass.
- **Effort:** L

## Log

### Proposal drafted

- **Summary:** Inspected eng-process v2.5.9 and Baton's existing recipe/gate design; proposed a separate recipe, source coverage requirements, explicit decisions and staged acceptance tests. No recipe or runtime behavior implemented.
- **Baseline:** HEAD `46ec3a855c89` had a clean worktree and a recorded green full suite (1554 passed, 9 skipped).
- **Validation:** Documentation checks passed (193 tests after recording 0138; rechecked after 0139). Broad quick gate outside the sandbox: 1246 passed, 3 skipped. The first sandbox run reported failures and was interrupted by a server restart; the unsandboxed rerun passed.
- **Review:** Awaiting owner answers to the Request's open questions; Design and Plan remain provisional.
- **Owner decision:** 2026-11-12, “Use Baton machinery (recommended)” (0138). “Blocking plan, advisory code (recommended)” (0139). Request as a whole is not yet accepted.
- **Accepted:** No; proposal only.

### On hold

- **Summary:** Owner, 2026-11-13: eng-process is to be Baton's single software recipe, tailored on a few axes and linked to project documents and policy. It waits for three changes still to be proposed: `2026-11-project-documents`, `2026-11-project-policy` and `2026-11-tailoring-axes`. The direction and the amendments this change will need are in `docs/catchall/project-process-linkage.md` (§5 F). Open questions 1-4 remain open.

### Amended for one software recipe

- **Summary:** Amended after `2026-11-project-documents` and `2026-11-tailoring-axes` were done. The changes:
  - eng-process is the one software recipe (Decision 0149, recorded from the owner's words of 2026-11-13).
  - The source's sizes become four axes, and the phase mapping is placed by axis.
  - New acceptance criteria cover scenarios across the range, a lowest path as light as `software-feature minor`, project roles for increments, policy, and retiring `software-feature`.
  - Open question 3 is updated, since the action permissions already enforce release authority, and questions 5 to 9 are added.
  - Still on hold, now only for `2026-11-project-policy`. No code changed.
- **Owner decision:** 2026-11-14, "Write the B, D, E and F change proposals". The Request is not yet accepted; open questions 1 to 9 are unanswered.
- **Accepted:** No; proposal only.
