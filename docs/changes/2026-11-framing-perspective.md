---
id: 2026-11-framing-perspective
title: "The Director bridges the process and owner perspectives; framing's breakdown and the owner's notes are kept as project documents"
status: in-progress
level: standard
decisions: ["0062", "0063", "0064", "0065", "0066", "0067", "0068", "0069", "0070", "0071", "0072"]
touches: [principles.md, design/adoption-and-framing.md, design/director-interface.md, design/persistence.md, design/runtime.md, design/layouts.md]   # §1.3, §2, §11.6, §13.1, §13.3, §10.4, §8.2, §4.3; also defaults/labels.yaml and skills/baton-director/SKILL.md
---

# The Director bridges the process and owner perspectives; framing's breakdown and the owner's notes are kept as project documents

## Request

### Problem

Evidence: Grok Director transcripts on the pure-water project, 2026-11-05.

- Framing's question "which parts should we start work on now" is correct from the process side: choosing a part starts a quick fit check (or a fitting recipe), not the work itself. But the owner thinks about the goal, not the process, and read it as "start marketing now".
- The label made it worse: `frame.select`'s effect says "Work starts now on the parts you chose", which overstates what happens.
- Unchosen parts are lost. A backlog is a valid project artifact; the non-goal "no backlog or idea management" (§1.3) was too severe.
- When the owner asks the Director to remember a thought, Baton has nowhere to put it.

Owner decisions (records 0062–0065):

1. Keep framing's mechanism (select starts what each chosen part proposes). Fix how it is presented, not what it does ([0062](../decisions/0062-framing-mechanism-kept-presentation-fixed.md)).
2. Amend the non-goal: Baton does not manage backlogs or ideas as a feature, but a backlog and notes are valid project deliverables and Baton may write them ([0063](../decisions/0063-backlog-and-notes-are-deliverables.md)).
3. Framing publishes its breakdown as a project document listing every part, its description, and what choosing it starts. Unchosen parts stay there, and a part can be started from it later ([0064](../decisions/0064-framing-publishes-its-breakdown.md)).
4. Notes stay informal and under-processed: only when the owner asks the Director to remember or note something. Mention briefly that the owner can keep notes anywhere they like, and offer once to keep a simple notes file for this project. No note is fed automatically into any step. Recording is verbatim and deterministic; recalling or organizing notes goes to the project SME with the notes file as a reference. No new SME subject ([0065](../decisions/0065-owner-notes.md); revised by the owner the same day to drop routing notes into a recipe's backlog deliverable).

Requested runtime changes:

- Decision options in `status`/`board` gain `next`: what choosing the option triggers, in process-neutral words, computed from the record. For frame select, per part: "a fit check: a few questions and a recommendation, no commitment", or "starts <recipe>: <its description>".
- `defaults/labels.yaml` `frame.select`: an accurate label and effect (e.g. label "Include these", effect "Each part you choose gets a first look, or starts its process if one fits; the others stay listed in your plan for later").

Requested Director skill changes (`skills/baton-director/SKILL.md` and the §13.3 copy, identical):

- New section "Two perspectives": workers and Baton describe things from the process side (steps, runs, starting, checks); the owner thinks about their goal. Before asking anything, translate: what does each choice change in the owner's world, and what happens next for them? Use each option's `next` for the facts; never guess what "start" means.
- In "Before you ask the owner anything": when rewording after the owner objects, check Promise and Fit again. Never make a question more comfortable by making it untrue.
- Show labels, never internal ids. Don't narrate Baton's mechanics or its feedback to the owner. When the owner is confused, objects, asks what a question means, or discusses the question instead of answering it, record `feedback confusing` silently, with the question as shown and the owner's words.
- Notes, as in decision 4.

### Acceptance criteria

Scripted scenario tests:

- The water-vending framing publishes the breakdown with all four parts; choosing two starts exactly their proposals; the other two remain in the document and can be started later, starting exactly what they proposed.
- Every frame option in `status --json` carries `next`.
- A note is appended verbatim and dated only after the owner accepts the notes file, and no step's packet ever contains it.
- A `baton-frame@1` run still decides as before.
- `pytest` green.

### Out of scope

- A later, out-of-band interaction that offers the owner the option to incorporate a note more formally, moving it to the appropriate process-formal place (a run's inputs, a recipe's backlog deliverable) through that place's own mechanism (0065). Not designed in this change.

### Open questions

Asked of the owner up front, 2026-11-05 (suggestions in the session; recorded as decisions once answered):

- Default paths for the breakdown and the notes file, and where the owner's "keep a notes file?" answer is stored.
- Settled 2026-11-05: starting a later part (0066); the notes call, file format and no confirm-back (0067); the breakdown rendered by the runtime, its publishing, no new framing version, no new concept (0068); the breakdown is a process plan that lists and never schedules, and its and the notes file's paths (0069); the notes-file answer stored as a project decision (0070).

## Design

### Doc edits

- `principles.md` §1.3: the non-goal becomes "No GUI. Baton manages no backlog or ideas as a feature; a backlog and notes are valid project deliverables Baton may write" (0063). §2: the process plan and the notes file add no concept (0068).
- `design/adoption-and-framing.md` §11.6:
  - the select gate's prompt lists parts by label, never id;
  - each frame option carries `next` (below);
  - on `select` the runtime renders and publishes the **process plan** (0064, 0068, 0069);
  - unchosen parts are started later with `start --from-plan` (0066).
- `design/director-interface.md` §13.1:
  - options become `[{decision, label, effect, next?}]`;
  - `start(recipe, inputs)` gains `from_plan`;
  - a new row `note(text)` / `note(keep_file, note)` (0067, 0070).
  
  §13.3: the director skill text as requested (Two perspectives; the rewording check; labels not ids; silent `feedback confusing`; notes), identical to `skills/baton-director/SKILL.md`.
- `design/persistence.md` §10.4: the process plan is published like a deliverable (artifact `process_plan` of the framing run's `frame` step, recorded `artifact_published`, same conflict rules), but it is rendered by the runtime, not returned by a worker. It is never drift-tracked, because the framing run completes at selection (§10.5).
- `design/runtime.md` §8.2: new events.
  - Project log: `note_recorded {text, at, path}` and `human_decision {kind: notes, accepted, note}`.
  - Framing run: `framing_started_later {part, run}`, recorded when `--from-plan` starts a part.
- `design/layouts.md` §4.3: `paths.process_plans` and `paths.notes`, default `docs`; `init` writes them.

### Mechanics

- **`next`** is computed at read time from the framing record, in process-neutral words.
  - `select`: one entry per part, `{part, label, next}`. A fit-check proposal reads "a fit check: a few questions and a recommendation, no commitment". A recipe reads "starts <recipe>: <its description>". A part that would be a gap reads "can't start yet: <reason>", using the same check `select` runs.
  - `reject`: "the breakdown is redone with what you said".
- **`frame.select` label:** "Include these". Effect: "Each part you choose gets a first look, or starts its process if one fits; the others stay listed in your plan for later."
- **Process plan file:** `<paths.process_plans>/<goal-slug>-process-plan.md`. The slug comes from the framing run's slug, so it is stable across goal rewording.
  - Content: the goal, then each part's label, description, what choosing it starts (`next`), and its state: started (as which run) or for later.
  - The file holds no ids the owner needs to read. Part ids appear only as a small "ref" so the Director can start a part from it.
- **`start --from-plan <part>`** or `<framing run>/<part>`: looks the part up across completed framing runs, refuses a part already started, and plans it with the same code as `select` (gaps are reported the same way). Then it records `run_started.framing`, appends `framing_started_later` to the framing run, and re-publishes the plan; a conflict waits on the started run (0072).
- **`note(text)`:**
  - With no notes decision recorded, it returns `notes: offer` and records nothing.
  - After `--keep-file no`, it returns `notes: declined` and records nothing.
  - After `--keep-file yes`, it appends `\n## <YYYY-MM-DD HH:MM>\n\n<text>\n` to `<paths.notes>/notes.md`, records `note_recorded`, and checkpoints.
  - No input reference resolves to notes, so no packet can contain one.

### Decisions

- 0062–0070 (all accepted 2026-11-05): see the Request and Open questions.
- [0071](../decisions/0071-next-on-framing-options.md): `next` is an optional option field; only framing's options carry it in this change.
- [0072](../decisions/0072-plan-republish-conflict-on-started-run.md): a process-plan conflict at `--from-plan` waits on the run it started.

## Plan

### Framing options say what happens next

- **Outcome:** frame options carry `next`; `frame.select` has its new label and effect; the select prompt lists labels.
- **Criteria:**
  - every frame option in `status --json` carries `next`, matching each part's proposal;
  - a `baton-frame@1` run still decides as before (the existing framing tests stay green).
- **Effort:** S

### The process plan is published at selection

- **Outcome:** `select` publishes the process plan with every part; `init` writes the two path keys, and unmapped keys use the defaults.
- **Criteria:**
  - the water-vending framing publishes the plan with all four parts;
  - choosing two starts exactly their proposals, and the plan marks them started and the other two for later;
  - an existing file at the target raises the §10.4 conflict.
- **Effort:** M

### A part is started later from the plan

- **Outcome:** `start --from-plan` starts a remaining part from the record and re-publishes the plan.
- **Criteria:**
  - the other two water-vending parts start exactly what they proposed, even after the published file is edited;
  - a part already started is refused, naming its run;
  - an ambiguous part id is refused, listing the candidates.
- **Effort:** M

### Owner notes

- **Outcome:** `note` / `baton note` with the one-time offer, recorded in the project log; an append-only notes file.
- **Criteria:**
  - a note is appended verbatim and dated only after the owner accepts the notes file;
  - before that it returns `offer`, and after a no it returns `declined`;
  - no step's packet ever contains a note.
- **Effort:** M

### The director skill bridges the two perspectives

- **Outcome:** the skill and its §13.3 copy are updated, and identical.
- **Criteria:**
  - the shipped skill equals the §13.3 text;
  - every call it names is in the API (the existing test), including `note` and `start --from-plan`.
- **Effort:** S

## Log

### Framing options say what happens next

- **Commit:** `2026-11-framing-perspective: Framing options say what happens next`
- **Summary:**
  - The API adds `next` to a framing run's options in `status`, `board`, `wait` and the other payloads that list pending decisions (`Api._pending`, `frame.annotate_next`). For `select` it is per part, using the same planning check as the selection; for `reject` it is fixed text.
  - `frame.select` is now labeled "Include these", with an accurate effect.
  - The select prompt lists parts by label and says that a chosen part usually gets a first look.
  - Tests: `test_every_frame_option_says_what_choosing_it_triggers` (status and board, all four water-vending parts, the selection unchanged). The existing framing tests are unchanged apart from the label, and show that a `baton-frame@1` run decides as before.
- **Review:** clean.
- **Accepted:** pending (owner).

### The process plan is published at selection

- **Commit:** `2026-11-framing-perspective: The process plan is published at selection`
- **Summary:**
  - Applying a selection renders the framing run's process plan from the record (`frame.render_plan`): the goal, then each part's label, description and status (started / chosen but a gap / for later), what choosing it starts, and its ref. The rendering is stored in CAS and named in `framing_selected.plan`.
  - `publish.due` includes it (`frame.plan_due`) as artifact `process_plan` of the `frame` step, so the existing publishing, conflict, decision and checkpoint machinery applies unchanged.
  - The target is `<paths.process_plans>/<goal-slug>-process-plan.md`, defaulting to `docs`. `init` now writes `paths: { process_plans: docs, notes: docs }`.
  - Tests:
    - `test_selection_publishes_the_process_plan_with_every_part`: all four water-vending parts; choosing two starts exactly their proposals; the other two are listed for later with what they would start; committed in the checkpoint.
    - `test_a_file_already_at_the_process_plan_path_is_a_conflict`: the conflict holds completion; `alternate` resolves it.
    - `test_unmapped_process_plan_path_uses_the_default`.
  - Two adoption tests were updated for the new `init` paths line.
- **Review:** clean.
- **Accepted:** pending (owner).

### A part is started later from the plan

- **Commit:** `2026-11-framing-perspective: A part is started later from the plan`
- **Summary:**
  - `start --from-plan <part>` (CLI), `start(from_plan=…)` (API, MCP).
    - `frame.find_part`: a part id unique across finished framing runs, or `<framing run>/<part>`.
    - `frame.start_from_plan` plans the part from the record with the same code as `select`; `frame.start_part` is factored out of `select`.
    - It refuses a part already started, a gap, a framing run still waiting on the owner, or a recipe/inputs/title given alongside.
  - Recording and re-publishing:
    - The framing run records `framing_started_later` (a new `baton-events/1` type, additive as in 0019), and the plan is rendered again.
    - `publish.Due.owner` lets the re-publication be recorded on the framing run while `plan_due_started` makes its conflict a pending decision of the newly started run (0072).
    - One checkpoint (the new trigger `framing_started_later`) holds the framing record, the new run, the plan and anything vendored.
  - Tests:
    - `test_parts_left_in_the_plan_start_later_exactly_as_proposed`: the other two water-vending parts start exactly what they proposed after the owner edited the plan. The edit is a conflict on the new run, decided by `overwrite`. The next start re-publishes silently. Started and unknown parts are refused, and the tree is committed clean.
    - `test_a_part_id_in_two_plans_must_be_named_with_its_framing_run`.
- **Review:** clean.
- **Accepted:** pending (owner).

### Owner notes

- **Commit:** `2026-11-framing-perspective: Owner notes`
- **Summary:**
  - `note(text?, keep_file?, note?)`: the API in `Api.note`, CLI `baton note`, an MCP tool. Until the owner has answered the one-time offer it records nothing and returns `notes: offer` with `needs_owner`.
  - `--keep-file yes|no --note` records `human_decision {kind: notes}` in the project log; a later yes is allowed.
  - With the file accepted, the text is appended verbatim to `<paths.notes>/notes.md` under a `## <date time>` heading. The file is created with a short header. `note_recorded` (text redacted, as all project-log text is) goes to the project log, and a project checkpoint includes the file.
  - No input reference was added, so notes cannot reach a packet.
  - Tests:
    - `test_a_note_is_kept_verbatim_only_after_the_owner_accepts_the_file`: offer, decline, nothing kept, a later yes, a multi-line note appended verbatim and dated, committed.
    - `test_no_packet_ever_contains_a_note`: fit-check and framing packets.
  - The MCP tool-set test now includes `note`.
- **Review:** clean.
- **Accepted:** pending (owner).
