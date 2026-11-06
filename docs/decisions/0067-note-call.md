---
id: "0067"
title: "note(text): no tag, an append-only file, no confirm-back"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§13.1", "§13.8"]
---

# 0067. note(text): no tag, an append-only file, no confirm-back

## Context

0065 keeps notes informal. They need a call, a file format and a rule on confirm-back.

## Decision

- The call is `note(text)`, `baton note "<owner's words>"`. Answering the one-time offer is `baton note --keep-file yes|no --note "<owner's words>"`. There is no `about` tag: tagging is the start of organizing, and what a note is about is in the owner's words anyway.
- The notes file is append-only: each note is a `## <date and time>` heading followed by the owner's words verbatim. Baton only ever appends, so the owner may edit the file freely and no conflict arises.
- A note needs no confirm-back (§13.8): it is recorded word for word, so nothing was interpreted. The Director says it is noted and where.
