# Choose or write the guide for a quick run

The owner chose a quick guided run instead of a full process. A helper will follow the guide you
return and write one document good enough to use. You return the guide, not the document.

## What you have

- `idea`: what the owner asked for, in their words.
- `profile`: what the first step understood: the `goal`, the ledger of facts, and `guide_choice`,
  the guide to `adopt`, to `adapt`, or a new one to `write`, with why.
- `guides`: the guides available, each with its `id`, what it `produces` and its full `text`.

## What to do

- **Adopt:** return the listed guide's text unchanged as the artifact `guide`.
- **Adapt:** start from the listed guide and change only what this owner's job needs (a section
  their kind of business must have, a question that matters for them, a measure of good that fits).
  Keep it general enough to use again for the same kind of document. Give it a new `id` that names
  what it is for, and `version: 1`. List each change in `changes`.
- **Write:** write a new guide in the same form as the listed ones.

Never put this owner's own facts in the guide (their figures, names, places): those come from the
owner when the quick run asks, or from documents the owner gives it. The guide says what to ask.

## The form a guide takes

Markdown, starting with front matter, then exactly these four sections, each with content:

```markdown
---
format: baton-guide/1
id: <lower-case words joined by hyphens>
version: 1
title: <a short name>
description: <one sentence: what the document is and who it is for>
produces: <what the run returns, for example "a lean business plan (Markdown, two to four pages)">
---

## Purpose
## What to produce
## What good looks like
## What to ask the owner
```

**What to produce** sets out the document's sections in order. **What good looks like** is a list
of checks a reader can apply to the finished document. **What to ask the owner** lists what usually
has to come from them. Name no AI model, vendor or tool: the guide must work with any helper. A check
refuses a guide that breaks any of this, and your work is redone.

## What to return

- The artifact `guide`: the guide.
- `id` (as in its front matter), `action` (`adopted`, `adapted` or `written`), `base` (the listed
  guide's id, or null for a new one), `summary` (what the guide asks for and what the quick run
  will produce, in the owner's terms: they read it before approving), and `changes`.
