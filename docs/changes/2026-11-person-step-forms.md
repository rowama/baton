---
id: 2026-11-person-step-forms
title: "A person's step can show a form built from the step's data, when the Director's questions are not enough"
status: proposed            # ON HOLD: deferred by the owner (2026-11-15); after 2026-11-tool-steps and the recipe-builder changes of Decision 0155
level: major
decisions: ["0155", "0031", "0121"]
touches: [design/director-interface.md, design/packets.md, design/recipes.md, design/platform-and-security.md]
manual: []
---

# A person's step can show a form built from the step's data, when the Director's questions are not enough

> **On hold.** Discussed 2026-11-15 and deferred by the owner ("I don't want to forget it, but it needs to be deferred"). Not to be designed further until taken off hold.

## Request

### Problem

A person answers a step in two ways today: the Director asks a worker's structured questions (choices, one topic at a time; Decision [0031](../decisions/0031-structured-questions.md)), or the person edits a file and submits it (`manual`, §6.3). Some steps fit neither. Matching twenty lines of a receipt to twenty photographed items is a table with a choice per row: too much for a conversation, and error-prone in a hand-edited file.

The alternative raised was for `recipe-builder` to write custom screen code for such a step. Generated screens are the hardest software to verify automatically, since the builder's test loop (Decision [0155](../decisions/0155-recipe-builder-builds-software.md)) would need browser automation, which is itself on hold ([2026-11-browser-automation](2026-11-browser-automation.md)).

Three tiers were agreed in outline:

1. **Structured questions** through the Director. Exists.
2. **A generated form:** Baton renders a form from the step's output schema and its input data. Written once in Baton and tested once; a recipe supplies only the schema and data. This change.
3. **Custom screen code** written by the builder for one step. Last resort; a later change, if ever.

### Acceptance criteria (draft)

1. A person's step may ask for a form. Baton builds it from the step's output schema and inputs: fields, choices, and tables with a value to give per row.
2. The form is an aid, never a requirement. The person can always complete the step by the existing means (the Director's questions, or editing and submitting the file), so a form that cannot be shown never blocks a run. This keeps the rule that nothing in a recipe requires a UI (Decision [0121](../decisions/0121-optional-ui-is-a-client.md)).
3. What the person enters is checked against the output schema and recorded as their answer, with the confirm-back the Director already uses (§13.8).
4. A form has no time limit, as a person's step has none (§8.7).
5. The form is served only on this machine, under the same rules as the local setup page (§15.2).

### Open questions

- Is the form a page of the optional local UI (§13.9), a file the person opens, or both?
- Which schema shapes are rendered in the first version (flat fields, one table, nested objects)?
- How does the Director tell the owner a form is waiting, and where?
- Does a worker's request for input (`questions_for_human`) also get a form when it has many questions?
- Tier 3 (custom screen code): is it ever built, and what would have to exist first?

## Design

To be written when taken off hold.

## Plan

To be written when taken off hold.

## Log

### Proposal recorded

- **Summary:** Recorded from the owner's discussion of 2026-11-15 so the idea is not lost. No design, no code.
- **Owner decision:** 2026-11-15, "drop in the on hold change proposal for a more capable director/human interaction capability."
- **Accepted:** No; on hold.
