---
id: 2026-11-director-note-capture
title: "The Director records whatever the owner frames as a note, and a note given before the notes file is accepted is not lost"
status: in-progress
level: standard
decisions: ["0065", "0067", "0070", "0191"]
touches: [design/director-interface.md, design/layouts.md]
manual: [reference/commands.md]
---

# The Director records whatever the owner frames as a note, and a note given before the notes file is accepted is not lost

## Request

### Problem

On 2026-11-22, in the baton-recipes project, the owner wrote a message that began "note: " (about the software recipe's build handoff and adoption). The Director didn't call `note`. It kept the text "in my own tracking for the recipe's next version" instead. When the owner later ran `baton note`, it said "No notes file yet". Evidence: `baton-recipes/.baton/project/events.jsonl` has no note activity until seq 54–56 (18:17), after the owner asked where the note was. Commits `48e727e` and `561187c` are from that point.

Three weaknesses let this happen:

1. **The skill doesn't say what counts as asking for a note.** §13.3 "Notes" says to take a note "only when the owner asks you to remember or note something". It gives no examples, so a "note:" prefix is left to the Director's judgement. It also says a note meant to shape the work "is an instruction in its own right". A note about the work therefore reads as work, and the Director kept it as work instead of recording it.
2. **A note given before the offer is answered is dropped.** `note "<text>"` in `notes: offer` records nothing. The note survives only if the Director sends it again with the owner's yes. The result's `next` hint doesn't even include the text (`baton note --keep-file yes|no --note "<their words>"`). In this case the Director took two calls and put the note text into `--note`, the field meant for the owner's answer (project log seq 54).
3. **A leading "note:" is recorded as part of the note.** `docs/notes.md` now starts the note with "note:". That word was meant for the Director, not as part of the note.

### Acceptance criteria

- The Director skill (and §13.3) says that anything the owner frames as a note ("note:", "note that…", "remember…", "write this down", "jot down") is recorded with `note` first, whatever it is about. It never goes only into the Director's own memory or tracking. If the note also reads as something for the work, the Director asks about that separately, after recording it.
- The skill says `--note` holds the owner's answer to the offer (for example "yes, keep a notes file"), not the note.
- A note given while the offer is unanswered is held, and the owner's yes appends it to the notes file verbatim, with no second `note "<text>"` call. A no discards it, and the result says so.
- A leading label addressed to the Director ("note:", case-insensitive) is not recorded as part of the note. The rest is verbatim.
- Tests in `tests/test_conversation.py` show each criterion.

### Open questions

Answered by the owner on 2026-11-23, all as suggested (Decision [0191](../decisions/0191-held-notes-and-note-label.md)): Q1, held in the local cache; Q2, strip a leading "note:" in code; Q3, record the note, then ask once.

## Design

`note "<text>"` while the offer is unanswered writes the text, and the time it was given, to `.baton/cache/notes-held.json` (a list; gitignored, never committed, no event). The result carries `held` (how many notes are waiting) and a `next` that says the held note is kept on a yes. `--keep-file yes` records the decision. It then appends each held note in order, each under the time it was given, and finally the call's own text if there is one. Each note gets its own `note_recorded` event, and all of them go in one checkpoint. `--keep-file no` deletes the held file and reports `discarded`. Before a note is held or recorded, a leading `note:` label (case-insensitive, with the whitespace after it) is removed. A note that is empty after that is `note.empty`. The CLI says when a note is held, and the help for `--note` says it is the owner's answer to the offer.

### Doc edits

- `design/director-interface.md` §13.1, the `note` row: a held note, the leading label, `held` and `discarded`. §13.3, the skill's Notes section: what counts as a note, recording first, asking once when a note reads as work, and what `--note` holds.
- `design/layouts.md` §4 layout: `cache/` also holds held notes.

### Manual edits

- `manual/reference/commands.md` (generated from the CLI): `baton note`'s `--note` help now says it is the owner's answer to the offer.

### Decisions

- [0191](../decisions/0191-held-notes-and-note-label.md) (new, accepted): held notes in the local cache, the leading label stripped in code, and recording before asking.

## Plan

### Slice 1: a held note is kept on the owner's yes, and a leading "note:" is not recorded

- **Outcome:** a note given before the offer is answered reaches the notes file when the owner says yes, with no second call. A no discards it. "note:" never lands in the file.
- **Criteria:**
  - `note "<text>"` in `offer` holds the note (`held: 1`). Nothing is written to the project, the log or git.
  - `--keep-file yes` appends the held notes verbatim, under the times they were given, with one `note_recorded` each.
  - `--keep-file no` reports `discarded` and leaves no held file.
  - A leading `note:` / `Note :` is stripped, and the rest is verbatim. A label-only note is `note.empty`.
- **Effort:** S

### Slice 2: the Director records anything framed as a note, first

- **Outcome:** the skill (and §13.3) says what counts as a note, to record it before anything else, never to keep it only in the Director's own tracking, to ask once when it reads as work, and that `--note` is the owner's answer.
- **Criteria:**
  - A skill test checks that these rules are in the shipped skill (and §13.3 matches it, as already tested).
- **Effort:** S

## Log
