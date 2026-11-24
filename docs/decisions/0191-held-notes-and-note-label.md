---
id: "0191"
title: "A note given before the notes-file offer is answered is held in the local cache; a leading \"note:\" is not recorded; a note that reads as work is recorded, then the owner is asked once"
status: accepted
date: 2026-11-23
source: 'Owner, 2026-11-23, answering change 2026-11-director-note-capture''s open questions: held note "Local cache"; "note:" "Yes, in code"; note vs work "Record, then ask once"'
sections: ["§13.1", "§13.3"]
---

# 0191. A note given before the notes-file offer is answered is held in the local cache; a leading "note:" is not recorded; a note that reads as work is recorded, then the owner is asked once

## Context

On 2026-11-22 the owner's note, which began "note: ", was never recorded (change 2026-11-director-note-capture). The Director kept it as recipe work instead of calling `note`. Separately, a note given while the notes-file offer is open was dropped unless the Director sent it again with the owner's yes. 0065 says a note is recorded only in the notes file, once the owner has accepted it. 0067 says it is recorded verbatim.

## Decision

- **Held note.** `note "<text>"` while the offer is unanswered holds the text in `.baton/cache/notes-held.json`. That file is gitignored and local to the machine; it is not the system of record and is never committed. The owner's yes (`--keep-file yes`) appends every held note to the notes file, each with the time it was given. A no deletes them, and the result says how many were discarded. Nothing about a held note reaches the project log or git until the owner says yes.
- **Leading label.** Baton removes a leading `note:` label (any capitalisation, with the spaces after it) before recording a note. That word is addressed to the Director, not part of the note. Everything after it is recorded verbatim, so 0067 holds for the note itself. This is done in code, so the Director never edits the owner's words.
- **A note that reads as work.** Anything the owner frames as a note is recorded with `note` first, whatever it is about, and never only in the Director's own memory or tracking. If it also reads as something for the work, the Director then asks once whether the owner wants it to shape the work now or just keep it as a note. Taking it into the work is an instruction in its own right, handled the usual way (0065).
