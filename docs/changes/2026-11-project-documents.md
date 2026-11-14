---
id: 2026-11-project-documents
title: "Runs bind the project's accepted or attested documents as inputs, by role, so one process can build on what another settled"
status: in-progress
level: major
decisions: ["0142", "0146"]
touches: [principles.md, design/recipes.md, design/packets.md, design/runtime.md, design/persistence.md, design/director-interface.md, design/adoption-and-framing.md, design/layouts.md]
manual: [user/start-with-a-goal.md, user/check-on-your-work.md, user/answer-questions-and-decide.md, admin/recipes-and-vendoring.md, admin/director-commands.md, reference/commands.md]
---

# Runs bind the project's accepted or attested documents as inputs, by role, so one process can build on what another settled

## Request

### Problem

A project is made of many processes of different kinds. In the owner's example, a water-vending business is first set up (business plan, sites, equipment), then marketed, and later gets a process for developing its operating procedures. Marketing needs the business's settled constraints and target customers; developing operations needs the project's decisions and policies.

Baton's first guarantee, reliable context handoff (§1.2), holds only inside a run. A step's declared inputs come from its own run, recorded human decisions, platform facts or the recipe catalog (§5.2). Earlier runs publish their deliverables into the repo (§10.4), so a worker with workspace read access *may* find them, but nothing lets a step declare that it needs one, receive the accepted version, be stopped when it is missing, or record which version it used. At project scale the guarantee stops exactly where it is needed. The owner: "If that is true, we've made it too brittle."

The owner's direction (2026-11-13, `docs/catchall/project-process-linkage.md`): a project holds any number of recipes, some oblivious to the project, most intentionally linked; links are possible, never mandatory, never prohibited; runs stay work items and are loosely coupled. Decision [0142](../decisions/0142-project-documents-bound-by-role.md) settles the shape. This change builds it. Project policy (0143), tailoring axes (0144, `2026-11-tailoring-axes`), quick runs (0145) and a project review recipe build on it in their own changes.

### Acceptance criteria

- **Project documents are listed.** `documents()` (CLI `baton documents`, MCP, API) lists every project document, derived from run records and the project log, never from a hand-kept index: each with its path, current hash, kind (`deliverable` or `attested`), source (run, step and artifact, or attestation decision), when it was accepted, and whether the file has changed since (edited, deleted). A completed run's published deliverable appears without any extra action.
- **The owner can attest a file.** `attest(path, note)` (`baton attest <path> --note "<owner's words>"`) records an owner decision in the project log with the file's hash, stores the file in the project CAS, and the file appears in `documents()` as `attested`. Paths outside the project, inside `.git` or `.baton`, missing files and a missing note are refused. Attesting a file again records a new version.
- **Recipes declare roles.** A recipe may declare `project_inputs` (`role`, `description`, `media_type`, `required`, `many`). Steps reference them as `project.<role>`. The loader refuses an undeclared role, a duplicate role, a malformed entry, and a role whose name or description names another recipe or step (neutrality lint). A recipe with no `project_inputs` loads, runs and hashes its packets exactly as before (golden tests unchanged).
- **Roles are visible to whoever proposes bindings.** `catalog.summaries`, framing's run inputs and the recipe topics in the manual show each recipe's roles.
- **Binding is recorded and confirmed.** `bind(run, role, path, note)` (and `start --bind <role>=<path> … --note`) checks that the path is a project document and its media type fits (a `many` role takes a list of paths, a single role exactly one), stores the bound content in the run's CAS, and records `project_input_bound {role, path, sha256, source, edited_since_accepted, decision_id}` with the owner's words. Binding a role the recipe does not declare is refused. A role can be bound at start or later.
- **Bound documents reach the packet like any input.** `project.<role>` resolves from the run's record only (never from the living file), appears in `manifest.json` with its hash and its source, and changes `packet_sha256` exactly as any input does. An optional unbound role is `not_applicable`. A required unbound role refuses the dispatch with `HandoffError` naming the role; `status` and `board` show the step as waiting on that binding.
- **Upstream change is reported, not propagated.** When a bound document has a newer version (a later publication, a later attestation, or an edited or deleted file), `status`, `board` and `check` say so for active runs, naming the run, role, bound version and current version. Nothing becomes stale and no run is blocked or held from completing.
- **Rebinding is the owner's choice and stays local.** Rebinding a role in a run records a new `project_input_bound` (owner's words required). Accepted steps in that run that consumed the role, and their accepted dependents, become `stale`, exactly as `revise` stales its dependents; steps not yet started use the new binding. Rebinding is refused while a consuming attempt is in flight. Other runs are never affected.
- **Records explain it.** Step records and the run summary (§10.6) list each project input with its role, path, hash and source.
- **The Director proposes and confirms.** The Director skill proposes bindings from `documents()` and the role descriptions when a run starts or a role becomes needed, confirms them back in the owner's terms (§13.8), and never binds silently.
- **Manual and design are current.** §2 lists the new concept; §5.2, §7.1, §8.6, §8.9, §10 and §13 describe the mechanics; the manual explains it to owners and administrators.

### Open questions

None open. The six questions this change raised were answered by the owner on 2026-11-13 ("Accept all.") as suggested, and are recorded in Decision [0146](../decisions/0146-project-document-details.md):

1. A binding takes the living file as it is now, recording `edited_since_accepted`; the confirm-back says so, and the owner's binding decision accepts the edit.
2. A role may declare `many: true` to take one or more documents; the default is one.
3. A project document is identified by its path; a moved file is a new document.
4. A deliverable is a project document once its step is accepted and published, whether or not its run has completed.
5. No withdrawal command: a newer attestation supersedes, and a deleted file is listed as deleted.
6. Code from workspace steps is not listed automatically; the owner may attest a file from the tree.

## Design

Approved by the owner with the Request on 2026-11-13 ("Implement project-documents").

### Shape

- **Identity and versions.** A project document is its path (0146). Its versions are, in order, each `artifact_published` at that path in any run (once its step passed) and each attestation of it; its current state is the living file's hash, compared with the latest version (`unchanged`, `edited` or `deleted`).
- **Project log and CAS.** Attestations are `document_attested {path, sha256, note, decision_id}` (after `human_decision {kind: attest}`) in the project log, with the blob in `.baton/project/cas/`. Deliverables need no new event: `documents()` reads `artifact_published` from every run (§10.4) and the project log's attestations, then hashes the living files.
- **Recipe format.** A top-level `project_inputs:` list. `project.<role>` joins the closed grammar of §5.2. The loader and the neutrality lint check it (§5.3). `many: true` makes the input a list in the packet (`inputs/<role>/<n>.<ext>`, in binding order). Recipe hashes change only for recipes that use it.
- **Binding.** `bind` and `start --bind` are owner-approved actions (the runtime requires the words; the Director skill requires the actual approval, as for `waive`). The bound content is the living file at binding time (0146), copied into the run's CAS, so the run stays self-contained and resumable on another machine (§10.3). The event records `edited_since_accepted` when that file differs from the document's latest version, and the Director's confirm-back says so in plain words.
- **Packet.** The packet builder (§8.6) resolves `project.<role>` from the latest `project_input_bound` for that role. Manifest inputs gain a `source` field for project inputs (`{kind, path, run?, step?, artifact?, decision_id?}`), so a worker knows it holds, say, the owner-attested business plan.
- **Rebinding** reuses the stale machinery of `revise` (§8.9): the consuming steps are found from the run's `packet_built` records (each records its inputs' hashes), and they and their accepted dependents become `stale`, group instances included, as `revise` does. A consumer that is the triage step cannot be made stale (§5.5): rebinding its role is refused with a pointer to `retriage`, which reruns triage with the new binding.
- **Reporting.** Upstream changes are computed on demand, like drift (§10.5), and recorded nowhere. They are a warning in `check`, never an error.

### Doc edits

- `principles.md` §2: add **Project document**; §1.2 *Reliable context handoff*: say it covers bound project documents.
- `design/recipes.md` §5.1 (format), §5.2 (`project.<role>`), §5.3 (validation and lint), §5.7 (catalog summaries carry roles).
- `design/packets.md` §7.1: the manifest's `source` for project inputs.
- `design/runtime.md` §8.2 (events `project_input_bound`, `document_attested`), §8.6 (resolution and `HandoffError`), §8.9 (rebind as a local correction).
- `design/persistence.md` §10.4–§10.6: when a deliverable becomes a project document; upstream change beside drift; records.
- `design/director-interface.md` §13.1–§13.3: `documents`, `attest`, `bind`, `start --bind`; the skill's binding conversation.
- `design/adoption-and-framing.md` §11.6: framing's summaries show roles; a part's proposal may include bindings.
- `design/layouts.md`: the project CAS and the attestation records.
- `docs/README.md`: decision 0142 and any new stable section.

### Manual edits

- `manual/user/start-with-a-goal.md`: later parts of a goal can build on what earlier ones settled; what the owner is asked when a process needs a project document.
- `manual/user/check-on-your-work.md`: seeing which documents a process used and when a newer version exists.
- `manual/user/answer-questions-and-decide.md`: confirming a binding, attesting a document, rebinding.
- `manual/admin/recipes-and-vendoring.md`: declaring `project_inputs` in a recipe, and why roles never name other recipes.
- `manual/admin/director-commands.md` and the generated `manual/reference/commands.md`: `documents`, `attest`, `bind`, `start --bind`.

### Decisions

- [0142](../decisions/0142-project-documents-bound-by-role.md) (accepted): project documents, roles, binding, reporting, listing, the concept.
- [0146](../decisions/0146-project-document-details.md) (accepted): the living file is bound, `many` roles, identity by path, when a deliverable counts, no withdrawal, code by attestation only.

## Plan

Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: the project's documents and attestation

- **Outcome:** `documents()` lists deliverables and attested files; the owner can attest a file.
- **Criteria:** listing from several runs' publications (accepted, edited, deleted, re-published); attestation recorded with words and hash; refusals (outside project, `.git`, `.baton`, missing file, no note); a second attestation is a newer version; CLI, MCP and API return the same.
- **Effort:** M

### Slice 2: recipes declare roles

- **Outcome:** recipes can declare `project_inputs` and reference `project.<role>`; summaries and the manual's recipe topics show roles.
- **Criteria:** loader refusals (undeclared, duplicate, malformed, naming another recipe or step); `many` roles; existing recipes' hashes and goldens unchanged; `catalog.summaries` and framing inputs carry roles.
- **Effort:** S

### Slice 3: binding and the packet

- **Outcome:** roles are bound at start or later, and bound documents reach the packet with their source.
- **Criteria:** `bind` and `start --bind` record the binding with the owner's words; type and role checks; the packet holds the bound content from CAS, not the living file; `packet_sha256` changes with the binding; optional unbound is `not_applicable`; required unbound raises `HandoffError` naming the role and `status` shows the wait; resume on a fresh clone builds the same packet.
- **Effort:** L

### Slice 4: upstream change and rebinding

- **Outcome:** active runs report newer versions of their bound documents; rebinding makes the consumers stale in that run only.
- **Criteria:** newer publication, newer attestation, edit and deletion each reported in `status`, `board` and `check` (a warning); no stale, no hold on completion; rebinding stales exactly the consuming accepted steps and their dependents (group instances included); rebinding a triage input is refused with a pointer to `retriage`; refused while a consumer is in flight; another run bound to the same document is untouched.
- **Effort:** M

### Slice 5: the Director's binding conversation and the manual

- **Outcome:** the Director proposes and confirms bindings in the owner's terms; records and the manual are complete.
- **Criteria:** skill text and its copy in §13.3; step records and run summary list project inputs; manual topics and generated reference updated; an end-to-end scenario: a setup run publishes a plan, a second recipe's run binds it, the plan is edited, the second run reports it and the owner rebinds.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Change doc written from decision 0142 and `docs/catchall/project-process-linkage.md` (§5 A). No code changed.
- **Owner decision:** 2026-11-13, "Concur with section recommendations for A, B, C, E1-4 (no new concept at E5). Write A and C change proposals." (0142). The Request is not yet accepted; the open questions above are unanswered.
- **Accepted:** No; proposal only.

### Open questions answered

- **Summary:** The six questions the proposal raised were answered as suggested and recorded as Decision 0146. The Request has no open questions; the Design section now incorporates the answers and adds two details found against the code: rebinding stales the consumers' dependents as `revise` does, and a triage input is rebound through `retriage`. No code changed.
- **Owner decision:** 2026-11-13, "Accept all." (0146).
- **Accepted:** Request and Design await the owner's approval.

### Request and Design approved

- **Summary:** The owner approved the Request and Design and asked for the change to be built; status `in-progress`. No code changed.
- **Owner decision:** 2026-11-13, "Implement project-documents".
- **Accepted:** Request and Design, yes.
