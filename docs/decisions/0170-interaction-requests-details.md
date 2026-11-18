---
id: "0170"
title: "Interaction requests: confirmed in the renderer with an optional note, a small schema subset, a closed set of hints, context by reference, the delegate's format, no MCP elicitation yet, no expiry, hints in their own file, every pending decision but no call-time confirmation, an id that changes with what is asked, files by path"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"1-8 concur. 11 concur. Expound on 9 and 10, I don't understand the question.\"; after they were explained: \"I concur.\""
sections: ["§2", "§5.3", "§7.2", "§8.2", "§13.1", "§13.3", "§13.8", "§14"]
---

# 0170. Interaction requests: confirmed in the renderer with an optional note, a small schema subset, a closed set of hints, context by reference, the delegate's format, no MCP elicitation yet, no expiry, hints in their own file, every pending decision but no call-time confirmation, an id that changes with what is asked, files by path

## Context

`2026-11-interaction-requests` carries Decision [0169](0169-interaction-requests.md) into the runtime: everything Baton asks the owner is a renderer-neutral request, answered through one call. The change doc raised eight open questions, each with a suggested answer. Three more came up when the draft was checked against the design before asking: the draft named only some of the pending decisions `status` and `board` list, its request id would not change when a pending act changed while open (a second rating signal joining `rating:<axis>`), and a person's step may return files that the answer schema cannot carry. The owner accepted all eleven suggested answers; 9 and 10 after they were explained with examples.

## Decision

1. **Confirmation outside conversation.** A renderer other than the Director's conversation shows the owner a summary of what will be recorded and a Confirm button with an optional note. The words recorded are the note or, without one, a fixed phrase naming the renderer ("confirmed in the local page").
2. **The answer schema subset** of `baton-interaction/1`: objects with named fields; strings (with choices, a date or a long-text hint); numbers and integers with bounds; booleans; lists of choices; lists of objects (a table, rows fixed by the context or added by the owner); nested objects (a group). No `$ref`, conditions or computed fields. A schema outside it gives a request marked `renderable: false`.
3. **Hints, a closed set:** `order`, `groups [{title, fields}]`, `widget` per field (`radio`, `dropdown`, `checkboxes`, `textarea`, `table`, `slider`), `help` and `label` per field, and `summary` (the fields shown in the confirmation). A renderer may ignore any of them.
4. **Context.** Text is inline up to a limit; files and images are references a renderer fetches through `interaction(id, item)`.
5. **The delegate uses this format.** `2026-11-ai-delegates` builds on interaction requests; a delegate is one more answerer of the same request, and that change follows this one.
6. **No MCP elicitation in this change.** It is a later renderer path for Directors whose client supports it, limited to requests that fit MCP's flat form.
7. **No expiry.** A request is open as long as its act is pending.
8. **Hints live in their own file:** `interaction: {hints: <file>}` on a step or human gate, the file (YAML or JSON) in the recipe package, checked at load against the step's schema.
9. **Which acts are requests.** Every pending decision that `status` and `board` list (every kind in `labels.yaml`: gates, triage, protected files, framing's `frame`, escalations, blocked steps, iteration limits, baseline, skip notices, rating signals, publish conflicts, drift; and findings and stale steps awaiting the owner), every blocked step's questions and every person's step. Call-time confirmations that return `needs_owner` (push, permissions, vendoring, policy, the notes offer, bind, attest) are not requests: they have no pending state, and the Director asks for them in conversation at that moment.
10. **A request's id changes with what is asked.** It is derived from the run, the ref, the kind and the sequence number of the last event that opened or changed the act. Any change to what is asked (a further rating signal, new questions from a step blocked again) gives a new id, and an answer to the old id is refused as stale, with the current request.
11. **Files from a person's step.** The request lists the step's declared artifacts with their names and descriptions. The answer names a path for each (`artifacts: {name: path}` in the answer file, CLI `--attach name=path`), taken in as `submit` takes a result folder's files. The answer schema subset has no file field; a renderer offers files through its own picker and maps them to the same paths.
