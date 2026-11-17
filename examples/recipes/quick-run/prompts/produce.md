# Write the document

The owner wants one document, good enough to use, without a full process. A guide says what to
produce and what good looks like. Follow it closely; it is the standard the owner will judge by.

## What you have

- `title`: a short name for the document.
- `request`: what the owner asked for, in their words.
- `guide`: the guide. Its sections are **Purpose**, **What to produce**, **What good looks like**
  and **What to ask the owner**.
- `context`, when present: documents the owner wants this one to build on, such as an earlier
  plan. Use what they settle; never contradict them without saying so in `assumptions`.

## Ask only what you cannot infer

The guide's **What to ask the owner** lists what usually has to come from them. Look for each
answer first in `request` and `context`. Ask only what is still missing and would change the
document: set `status` to `blocked` and ask through `questions_for_human`, each question an object
`{id, ask, why, best_guess?, options?: [{id, label}], multi_select?, priority?}`, in the owner's
words, a few at most. Where a reasonable guess will do, guess, and record it in `assumptions`
instead of asking.

## What to return

- The artifact `deliverable`: the document, in Markdown, as the guide's **What to produce** sets
  it out. Write in the owner's terms; it is theirs to use and to show others.
- `summary`: what the document says, in two or three sentences.
- `checklist`: every point of the guide's **What good looks like**, whether the document meets it
  (`met`), and how. Fix the document rather than report a point unmet, unless it cannot be met
  without the owner; then say what is needed in `how`.
- `assumptions`: every figure, fact or choice you supplied that the owner did not, with its basis
  (`about`, `value`, `basis`). Mark the same assumptions in the document itself.

If you are given feedback from an earlier attempt, it is the owner's note on what was not good
enough: address every point of it.
