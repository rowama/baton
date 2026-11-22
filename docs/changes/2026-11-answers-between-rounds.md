---
id: 2026-11-answers-between-rounds
title: "The owner's answers can be recorded at any decision that retries the work, not only at a blocked step"
status: accepted
level: standard
decisions: ["0184", "0181", "0170"]
touches: [design/packets.md, design/director-interface.md, design/runtime.md]   # §7.2, §8.10, §13.1, §13.3, §13.8
manual: [user/answer-questions-and-decide.md, admin/director-commands.md, reference/commands.md]
---

# The owner's answers can be recorded at any decision that retries the work, not only at a blocked step

## Request

### Problem

Found by the owner on 2026-11-22 in run `r_20261119_ee96` (baton-recipes, `recipe-builder@7`), group `shape/x5b12127`.

- Round 3's design (`i3/design`) could not settle five choices (A-VER-1, A-SLICE-1, A-GAP-1, A-ROLL-1, A-LATE-1). It guessed them, marked them `inferred` in its ledger, listed them in its document under "Your answers this design rests on", and passed with no `questions_for_human`.
- The audit (`i3/audit`) failed it, rightly, for F33, "Consequential design choices remain unconfirmed" (readiness checks 17 and 20). The group reached its iteration limit (event 226).
- The owner answered all five, and one scoping question, and approved another round. Baton had no way to take the answers: `decide … retry --answers` works only on a step escalated `blocked` (`_decide_answers`), and the iteration limit's `retry` takes only `--note`.
- The Director (a Grok agent) wrote `human_decision {kind: answers, decision: "recorded"}` events into the run log through Baton's internals (event 229, on `i3/design`, a step that had passed; event 193 on 11-21, the same way, for A-REL-1). It told the owner so. The answers it wrote match the owner's words and did reach round 4's design and audit, because answer collection (`packet.py`) takes any `kind: answers` event on the same step. But nothing checked them, and the hard rule "never compose or edit … anything under `.baton/`" was broken.
- With `--note` alone, the answers reach only round 4's design, as free text in `owner_note`: no ids, not in "The owner's earlier answers", not to round 5, not to the audit (0181, item 2).

The recipe side (the designer should have returned `blocked` instead of guessing a choice that changes the stages) is handed off separately as a recipe-builder change; this change is Baton's side.

### Acceptance criteria

- A `completed` result may carry `questions_for_human`; intake records them on `result_submitted` as `questions` (an empty list when none), and records none for a rejected result. A step's open questions are its latest accepted completed result's questions, every iteration of its group counting as one step, less those answered for that step anywhere in the run.
- `status` and `board` list each active run's `open_questions` (`[{step_path, attempt, request_id, questions}]`); open questions are not pending decisions and do not set `needs_owner`.
- Each asking step's open questions are one interaction request (`kind: open_questions`), listed by `interactions` without setting its `needs_owner`, whose one choice `answer` takes a field per question (none required, best guesses prefilled), and `answer` records it.
- `decide <run> <step> answer --answers <file> --note` records answers to that step's open questions in any state of the run: ids checked against them, `owner_words` required, partial sets allowed. They are recorded as `human_decision {kind: answers}` against the asking step's attempt, close those questions, and reach the step's next attempt in any iteration and its review (`answers_earlier`).
- `decide <run> <instance> retry --answers <file>` at an iteration limit, `decide <run> <step> retry --answers <file>` on an escalation that is not `blocked`, and `decide <run> <step> reject --answers <file>` on a human gate first record answers to the open questions of the steps at or under the ref (one record per asking step; an id two steps both ask is refused), then the decision. Their interaction requests' `retry`/`reject` choice offers those questions as optional fields.
- A blocked step's `retry --answers` is unchanged.
- The packet's result instructions and the API runner's contract say a completed result may ask the owner to confirm a guess, and that an unanswered choice the work cannot go on without is still `blocked`.
- The Director skill says: when Baton has no command for something the owner decided, tell the owner and record what you can (`--note`); never write events or files under `.baton/` to fill the gap.

## Design

### Doc edits

- `design/packets.md` §7.2: `questions_for_human` on a `completed` result asks the owner to confirm guesses, without blocking; what intake records.
- `design/runtime.md` §8.10: intake records an accepted completed result's `questions`.
- `design/director-interface.md` §13.1: `decide … answer`, `--answers` with `retry` and `reject`, `open_questions` in `status` and `board`, the `open_questions` request kind and its answer. §13.3: the skill's hard rule against filling a gap by hand, and *Answering requests* for open questions. §13.8: open questions among what the Director has as data, and the confirm-back seam for their answers.

### Manual edits

- `manual/user/answer-questions-and-decide.md`: a work part may go on with a best guess and ask you to confirm it; you can answer any time, or with "Give it another round"; nothing waits.
- `manual/admin/director-commands.md`: `decide … answer`, `--answers` with a retry or a rejection, `open_questions` in `status`.
- `manual/reference/commands.md`: regenerated (the `decide` help).

### Decisions

- [0184](../decisions/0184-answers-outside-a-blocked-step.md) (accepted 2026-11-22): questions without blocking, answered at any time or with a retry, holding nothing up; the Director never fills a gap by hand; the hand-written records in `r_20261119_ee96` stay.
- [0181](../decisions/0181-first-use-feedback-routing-and-answers.md), item 2: answers last across rounds; this change feeds it, unchanged.
- [0170](../decisions/0170-interaction-requests-details.md): the request format the new kind follows.

## Plan

### Slice 1: open questions from any result

- **Outcome:** a completed result's questions are recorded and listed as the run's open questions, and the worker contracts say a completed result may ask.
- **Criteria:**
  - intake records `questions` on an accepted completed result, and none on a rejected one;
  - a later round's result replaces an earlier round's open questions; an answered question is not listed;
  - `status` and `board` list `open_questions`; `needs_owner` is unchanged;
  - the packet's result instructions and the API runner's contract say a completed result may ask.
- **Effort:** M

### Slice 2: answering open questions, alone or with a retry

- **Outcome:** the owner's answers to open questions are recorded through `decide … answer`, `--answers` with a retry or a rejection, or `answer` on the new request, and reach later rounds and reviews.
- **Criteria:**
  - `decide … answer` checks ids and `owner_words`, records against the asking step, and closes the questions;
  - the answers reach the step's next iteration and its review in `answers_earlier`;
  - `retry --answers` at an iteration limit records per asking step, then readies the next round; an ambiguous id is refused;
  - the `open_questions` request lists and answers through `answer`; the iteration limit's `retry` choice offers the questions;
  - a blocked step's answers are unchanged.
- **Effort:** L

### Slice 3: the Director's rule and the manual

- **Outcome:** the skill and the manual tell the Director and the owner how open questions work, and the Director never fills a gap by hand.
- **Criteria:**
  - the skill's hard rule and *Answering requests* say it (the §13.3 copy matches `skills/baton-director/SKILL.md`);
  - the manual pages above describe open questions; the generated reference is current.
- **Effort:** S

## Log
