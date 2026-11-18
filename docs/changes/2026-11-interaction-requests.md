---
id: 2026-11-interaction-requests
title: "Everything Baton asks the owner is a renderer-neutral interaction request, which any client may show in its own way"
status: proposed
level: major
decisions: ["0169", "0170", "0031", "0121", "0125", "0161"]
touches: [principles.md, design/recipes.md, design/packets.md, design/runtime.md, design/director-interface.md, design/versioning.md]
manual: [user/answer-questions-and-decide.md, admin/director-commands.md, admin/recipes-and-vendoring.md, reference/commands.md]
---

# Everything Baton asks the owner is a renderer-neutral interaction request, which any client may show in its own way

## Request

### Problem

Baton asks the owner things in several shapes, each tied to one way of answering:

- a worker's structured questions (`questions_for_human`, §7.2), answered in conversation and recorded with `decide … --answers`;
- human gates and other decisions, offered as `[{decision, label, effect}]` in `status` and `board` and recorded with `decide`;
- a person's step, answered by writing a result folder and running `submit`.

Some asks fit none of these well. Matching twenty receipt lines to twenty items is a table with a choice per row: too long for a conversation, error-prone as a hand-edited file. And every way of answering is defined by Baton, so the owner cannot answer in a terminal form, a web panel or a desktop window without Baton itself growing each one.

The owner's direction (Decision [0169](../decisions/0169-interaction-requests.md)): a step or worker only asks for a structured interaction; how it is shown is the client's choice at the time; recipes ship no rendering script; and one call takes every answer back.

This replaces `2026-11-person-step-forms` (abandoned).

### Acceptance criteria

1. **One format.** Every ask of the owner is an interaction request in the format `baton-interaction/1`:
   - its id, run and the step or gate it belongs to;
   - its kind, title and message, in the owner's terms;
   - its context: text, documents, tables and images to show;
   - the answer's shape, as a schema, with any prefilled values;
   - its choices with labels and effects, where it is a decision;
   - optional hints and renderer-specific extensions.
   It says nothing about how it is drawn and carries no script.
2. **Every ask is one.** The runtime builds a request for each pending owner act: every pending decision `status` and `board` list (every kind in `labels.yaml`, findings and stale steps awaiting the owner included), every blocked step's questions, and every person's step. Call-time confirmations that return `needs_owner` (push, permissions, vendoring, policy, the notes offer, bind, attest) are not requests and stay in conversation (Decision [0170](../decisions/0170-interaction-requests-details.md), item 9). Nothing about these acts changes except that each is also a request.
3. **Person steps can ask for structured answers.** A person's step may give `interaction` hints (§5.3); its answer's shape is its output schema. Without hints it still gets a request, built from the schema alone.
4. **A renderable subset.** A request's answer schema uses a defined subset of JSON Schema: objects with named fields; strings (with choices, a date or a long-text hint); numbers and integers with bounds; booleans; lists of choices (several may be chosen); lists of objects (shown as a table, with rows fixed by the context or added by the owner); nested objects (a group). A step whose output schema falls outside the subset still gets a request, marked `renderable: false`, so renderers fall back to the file.
5. **Hints are advice.** `hints` may set field order, groups, a preferred widget per field, help text and labels. A renderer that ignores all of them still produces a valid answer. `extensions.<renderer kind>` holds anything for one kind of renderer and is ignored by the rest.
6. **Requests can be listed and read.** `interactions(run?)` lists open requests and `interaction(id)` returns one in full, in the CLI and MCP. `status` and `board` give each pending decision's request id.
7. **One way back in.** `answer(id, …, words)` (CLI `baton answer <id> --file <answer.json> --note "<words>"`) takes every answer: a choice, field values, answers to questions, or a person's step result, with any files it declares given by path (`--attach name=path`, 0170 item 11). It checks it against the request, refuses a stale request (one already answered, no longer pending, or changed since: a request's id changes whenever what it asks changes, 0170 item 10), and records it through the same path as today's `decide` and `submit`. The answer may say which renderer was used.
8. **Two renderers with no new software.** The Director in conversation renders any request: it walks a table one row at a time and confirms back as today (§13.8). `baton answer <id> --template` writes an answer file with the prefilled values and a comment per field for the owner or anyone to edit.
9. **Existing commands still work.** `decide`, `submit` and `decide … --answers` keep working as they are and are recorded the same way; `answer` is the general form of them.
10. **Nothing in a recipe requires a renderer.** Every request can always be answered through conversation or the answer file (Decision [0121](../decisions/0121-optional-ui-is-a-client.md)).
11. **Manual and design are current.**

### Open questions

All eleven were answered as suggested (Decision [0170](../decisions/0170-interaction-requests-details.md)); 9 to 11 were raised on review before the first eight were put to the owner, and 9 and 10 were explained with examples before the owner decided them.

1. **How is the owner's confirmation recorded when a renderer other than conversation is used?** *Suggested:* the renderer shows the owner a summary of what will be recorded and a Confirm button with an optional note. The words recorded are the note, or a fixed phrase naming the renderer ("confirmed in the local page") when there is none. *Rationale:* the confirm-back exists so nothing is recorded that the owner did not see and accept; a summary and an explicit Confirm do that, and typing words into every form would be friction for nothing.
2. **Is the answer schema subset enough?** *Suggested:* yes, as listed in criterion 4, with no `$ref`, conditions or computed fields in the first version. *Rationale:* it covers choices, forms, and the table-per-row case that started this, and every renderer can draw it; richer shapes can come in `baton-interaction/2` when a recipe needs them.
3. **Which hints are defined?** *Suggested:* `order`, `groups [{title, fields}]`, `widget` per field (`radio`, `dropdown`, `checkboxes`, `textarea`, `table`, `slider`), `help` and `label` per field, and `summary` (which fields to show in the confirmation). *Rationale:* a small, closed set that every GUI-like renderer can honour and any other can skip.
4. **How does context show large or binary material?** *Suggested:* context items carry text inline (up to a limit) and refer to files and images by a reference the renderer fetches through `interaction(id, item)`. *Rationale:* a request stays small and readable, and a terminal renderer can skip an image without failing.
5. **Should the delegate's interface use this format?** *Suggested:* yes. `2026-11-ai-delegates` builds its requests on interaction requests, and a delegate is one more answerer of the same request. *Rationale:* one contract for every answerer; two would drift apart. That change would then follow this one.
6. **Does Baton send MCP elicitations?** *Suggested:* not in this change; recorded as a later renderer path for Directors whose client supports it, limited to requests that fit MCP's flat form. *Rationale:* useful, but it rides on the Director's client and needs care with the run's lease.
7. **Does a request expire?** *Suggested:* no; it stays open as long as its act is pending, as today. *Rationale:* it adds no time limit to what has none (§8.7).
8. **Where does `hints` live in a recipe?** *Suggested:* `interaction: {hints: <file>}` on a step or a human gate, the file in the package (YAML or JSON), checked at load against the step's schema. *Rationale:* hints are presentation, and keeping them out of `recipe.yaml` keeps the recipe readable.
9. **Which owner acts become requests?** Criterion 2 names gates, questions, escalations, limits, rating signals and person steps, but `status` and `board` also hold framing's `frame` gate, findings (`accept-risk`), stale steps (`confirm`), skip notices, publish conflicts and drift; and some calls return `needs_owner` at call time (push, permissions, vendoring, policy, the notes offer, bind, attest). *Suggested:* every pending decision `status` and `board` list (every kind in `labels.yaml`), every blocked step's questions and every person's step are requests; the call-time `needs_owner` confirmations are not, and stay in conversation. *Rationale:* a request is pending state that can be listed and answered later, from anywhere; a call-time confirmation has no pending state to list, and the Director is already asking at that moment.
10. **When does a request's id change?** The draft derives it from run, ref, attempt and kind, but a pending act can change while open (a second rating signal joins `rating:<axis>`; a step blocks again with new questions). *Suggested:* the id is derived from run, ref, kind and the sequence number of the last event that opened or changed the act, so any change to what is asked gives a new id, and an answer to the old one is refused as stale. *Rationale:* an owner must never have recorded an answer to something they were not shown.
11. **How does a person's step return files?** A person's step may declare artifacts (a photo, a signed document), which the answer schema cannot carry. *Suggested:* the request lists the step's artifacts with their names and descriptions; the answer file names a path for each (`artifacts: {name: path}`, CLI `--attach name=path`), taken in as `submit` takes a result folder's files. The answer schema subset gets no file field in `baton-interaction/1`; a renderer offers files through its own picker, mapped to the same paths. *Rationale:* keeps the schema subset pure data while making every person's step answerable through `answer`.

### Out of scope

- **Any GUI.** The first one is `2026-11-interaction-ui`.
- **Script in a request** (Decision 0169, item 4).
- **MCP elicitation** (open question 6).
- **The delegate's own interface** (`2026-11-ai-delegates`).

## Design

For the owner's approval, with the Request.

### Shape

- **A request.**
  ```json
  {
    "format": "baton-interaction/1",
    "id": "ir_7f3a…", "run": "r_…", "ref": "slices/2/accept", "kind": "person_step",
    "title": "Match the receipt to the items",
    "message": "For each receipt line, choose the item it pays for.",
    "context": [
      { "id": "c1", "kind": "table", "label": "Receipt lines", "columns": ["line", "amount"], "rows": [["Widget A", 12.5]] },
      { "id": "c2", "kind": "image", "label": "Receipt photo", "ref": "inputs/receipt.jpg" }
    ],
    "answer": {
      "schema": { "type": "object", "properties": { "matches": { "type": "array", "items": { "type": "object",
        "properties": { "line": { "type": "string" }, "item": { "type": "string", "enum": ["i1", "i2"] } } } } } },
      "prefill": { "matches": [ { "line": "Widget A" } ] },
      "renderable": true
    },
    "choices": [],
    "hints": { "fields": { "matches": { "widget": "table" } } },
    "extensions": {},
    "needs_confirmation": true
  }
  ```
  For a decision, `answer` is absent and `choices` are the `[{decision, label, effect}]` of today. For a blocked step's questions, `answer.schema` is built from `questions_for_human`.
- **Ids.** A request's id is derived from the run, the ref, the kind and the sequence number of the last event that opened or changed its act (0170 item 10), so it is stable while nothing about the ask changes, and changes when it does: a further rating signal joining `rating:<axis>`, a step blocked again with new questions, a new attempt. `answer` to an old id is refused (`interaction.stale`) and returns the current request, if any.
- **Files.** A person's step's request lists its declared artifacts (`files [{name, description, required}]`); the answer gives `artifacts: {name: path}` (0170 item 11).
- **Confirmation.** `needs_confirmation: true` on every request. A renderer other than conversation shows a summary (the `summary` hint's fields, or all) and a Confirm with an optional note; `answer` records the note, or a fixed phrase naming the renderer from `via`, as the owner's words (0170 item 1).
- **`answer`.** One engine function maps the answer to today's paths: `decide` (gates, escalations, limits, ratings), `decide --answers` (questions) or `submit` (a person's step, whose result folder is written from the values and the attached files). The recorded `human_decision` and `result_submitted` gain `request_id` and `via` (the renderer, as it names itself).
- **The answer file.** `baton answer <id> --template` writes `answer-<id>.yaml` with each field, its prefilled value and a comment from its label and help; `baton answer <id> --file` reads it back.
- **The format** is defined in `formats/baton-interaction-1.schema.json` with the format version rules of §14.
- **No new concept for renderers.** A renderer is a client (Decision [0125](../decisions/0125-ui-adds-no-concept.md)). **Interaction request** is a new concept in the glossary.

### Doc edits

- `principles.md` §2: **Interaction request**.
- `design/recipes.md` §5.3: `interaction` hints on a step or human gate and their load checks.
- `design/packets.md` §7.2: how `questions_for_human` become a request.
- `design/runtime.md` §8.2: `request_id` and `via` on decisions and submissions.
- `design/director-interface.md` §13.1 (`interactions`, `interaction`, `answer`), §13.3 (the Director renders requests in conversation), §13.8 (confirmation through renderers).
- `design/versioning.md` §14: the `baton-interaction/1` format.

### Manual edits

- `user/answer-questions-and-decide.md`: answering in conversation or through an answer file; what happens when a question changed before you answered.
- `admin/director-commands.md`: `interactions`, `interaction`, `answer`.
- `admin/recipes-and-vendoring.md`: `interaction` hints on a step or human gate.
- `reference/commands.md`: `baton interactions`, `baton interaction`, `baton answer` (`--template`, `--file`, `--attach`, `--note`).

### Decisions

- [0169](../decisions/0169-interaction-requests.md) (accepted): the principle.
- [0031](../decisions/0031-structured-questions.md) (accepted): structured questions, now one source of requests.
- [0121](../decisions/0121-optional-ui-is-a-client.md), [0125](../decisions/0125-ui-adds-no-concept.md) (accepted): a UI is an optional client and adds no concept.
- [0161](../decisions/0161-ai-delegates.md) (accepted): the delegate, which would answer the same requests.
- [0170](../decisions/0170-interaction-requests-details.md) (accepted): the answers to the eleven open questions, all as suggested.

## Plan

Slices as proposed; refined once the Request and Design are approved.

### Slice 1: the format and requests for decisions

- **Outcome:** every pending decision and blocked step's questions is an interaction request, listed and read, and answered with `answer`.
- **Criteria:** the format and its schema; ids that change with what is asked; requests for every pending decision kind, escalations, limits, rating signals and questions; `interactions` and `interaction`; `answer` recorded as `decide` would be, with `request_id` and `via`; stale requests refused; `decide` unchanged.
- **Effort:** L

### Slice 2: person steps, hints and the answer file

- **Outcome:** a person's step asks for a structured answer, with hints, and can be answered through the answer file.
- **Criteria:** the renderable subset and `renderable: false`; `interaction` hints loaded and checked; context items and their references; `answer --template`, `--file` and `--attach`; the result folder written from the values and taken in as `submit` would; `submit` unchanged.
- **Effort:** M

### Slice 3: the Director renders requests

- **Outcome:** the Director holds any request in conversation, including a table one row at a time, and records it with `answer`.
- **Criteria:** the Director skill; confirmation as in open question 1; a scenario with a table-per-row person step answered in conversation and another through the file; the manual.
- **Effort:** M

## Log

### Written to replace person-step-forms

- **Summary:** Written from the owner's direction of 2026-11-18 (Decision 0169). Replaces `2026-11-person-step-forms`, which tied a step's ask to a web form Baton served. No code changed.
- **Owner decision:** 2026-11-18, "Rewrite as interaction-requests and then obsolete the old proposal."
- **Accepted:** No; proposal only. Eleven open questions await the owner (9 to 11 added on review, 2026-11-18: which acts become requests, when an id changes, and files from a person's step).

### Open questions answered

- **Summary:** The eight open questions were put to the owner with their suggested answers, plus three raised on review: which owner acts become requests (the draft named only some of the pending decisions), when a request's id changes (it would not have changed when a pending act changed while open), and how a person's step returns files. The owner accepted 1 to 8 and 11 at once, and 9 and 10 after they were explained with examples. Recorded as Decision 0170; criteria 2 and 7, the Design's ids, files and confirmation, the slices and the manual list now cite it. No code changed.
- **Owner decision:** 2026-11-18, "1-8 concur. 11 concur."; on 9 and 10, "I concur." (0170).
- **Accepted:** No; awaiting approval of Request and Design.
