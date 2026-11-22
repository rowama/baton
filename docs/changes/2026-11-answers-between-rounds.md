---
id: 2026-11-answers-between-rounds
title: "The owner's answers can be recorded at any decision that retries the work, not only at a blocked step"
status: done
level: standard
decisions: ["0184", "0181", "0170"]
touches: [design/packets.md, design/director-interface.md, design/runtime.md, design/layouts.md]   # §7.2, §8.10, §13.1, §13.3, §13.8
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

### Slice 1: open questions from any result

- **Commit:** 2026-11-answers-between-rounds: Slice 1, open questions from any result
- **Summary:** intake (`engine.submit`) records an accepted completed result's `questions_for_human`, normalized, on `result_submitted` as `questions`, only when it has some (so no other record changes). New `questions.py`: `step_key` (the step with each enclosing group's iteration as `i*`, packet's `_iteration_free`), `answered_ids` (every `human_decision {kind: answers}` per step key) and `open_questions` (per step key, the latest accepted completed result's questions less those answered; a result intake rejected asks nothing; a later round's accepted result replaces the earlier round's, even when it asks nothing). `status` lists `open_questions` (`[{step_path, attempt, questions}]`) while the run is active and only when any, and `board` per run; neither sets `needs_owner`. The packet's result instructions and the API runner's two contracts say a completed result may list questions for guesses to confirm, and that a choice the work cannot rest on is still `blocked`; the instructions golden (`tests/golden/fit-check-assess-INSTRUCTIONS.md`) is regenerated.
- **Design docs:** `design/packets.md` §7.2 (questions on a completed result; open questions); `design/runtime.md` §8.10 (intake step 3 records them); `design/director-interface.md` §13.1 (`status` and `board` list `open_questions`); `design/layouts.md` (the new module).
- **Tests:** new `tests/test_open_questions.py` (quick): a completed result's questions are recorded and open; none recorded when there are none; a rejected result asks nothing; the next round replaces the last round's questions, and a round that asks nothing leaves none open; an answered question is not open in any later round, even asked again; the contracts say a completed result may ask. `tests/test_conversation.py::test_a_completed_results_questions_are_listed_as_open_and_nothing_waits` (slow): `status` and `board` list them, with `needs_owner` false and no pending decision.
- **Repair:** the full suite was red on this slice and the two after it (`tests/test_continuity.py::test_records_golden`): the reworded result instructions changed every packet's hash, so the record goldens `tests/golden/fit-check-describe-record.md` and `fit-check-assess-record.md` were regenerated (only packet and result hashes moved), in *2026-11-answers-between-rounds: repair Slice 1, record goldens after the instructions change*.
- **Review:** clean
- **Accepted:** <pending the owner>

### Slice 2: answering open questions, alone or with a retry

- **Commit:** 2026-11-answers-between-rounds: Slice 2, answering open questions, alone or with a retry
- **Summary:** `engine.decide` routes `answer` to `_decide_open_answers` (`ref` the asking step: its open questions, any time, no state change), and `--answers` on anything but a blocked step to `_decide_with_open_answers` (`retry` or `reject` only; `--partial` refused): the answers are matched to the open questions at or under the ref and checked first (`_check_open_answers`: an object per answer, `owner_words` required through `check_answers` with partial allowed, an id two asking steps both ask refused), then the decision is recorded, then one `human_decision {kind: answers, decision, open: true}` per asking step against its asking attempt (`_record_open_answers`). A ref with no open questions keeps the old refusal, `decide.nothing_pending`. `interactions.py`: `build_open_questions` (`kind: open_questions`, one `answer` choice, a field per question, none required, best guesses prefilled; id from the run, step, asking `result_submitted` and the questions still open), `open_questions_schema`, and the `retry` of an iteration limit or escalation and a gate's `reject` offering the open questions under the ref as optional fields; those requests' ids include them, only when there are some. `Api`: `_open_requests` lists the open-question requests, `interactions` leaves them out of `needs_owner`, `answer` records them (`decide … answer`; an empty answer refused) and passes a retry's or reject's values as answers; `status` gives each entry its `request_id`. `defaults/labels.yaml`: `open_questions.answer`. CLI and MCP `decide` help describe `answer` and the wider `--answers`.
- **Design docs:** `design/director-interface.md` §13.1 (`decide … answer`, `--answers` with a retry or reject, the `open_questions` request, `request_id` in `status`) and §13.8 (open questions among the Director's data, the label kind, the confirm-back seam for their answers).
- **Manual:** `manual/reference/commands.md` regenerated (the `decide` help).
- **Tests:** `tests/test_open_questions.py` (quick): `decide … answer` records against the asking step, leaves the rest open, and reaches the review and the next round (`answers_earlier`, the packet text); four refusals that record nothing (no `--answers`, no note, an unknown id, no `owner_words`); a step with no open questions names the steps that have them; another round with answers at an iteration limit (the retry choice offers the questions, none required; the answers are recorded against the asking step after the retry and reach round two); an id two steps ask is refused, recording nothing, and is answered on its own step; answers go only with retry or reject and are always partial; the request's shape, and a new id after an answer. `tests/test_conversation.py` (slow): open questions are a request `interactions` lists without `needs_owner`, with the id `status` gives, answered through `answer` with `request_id` and `via` recorded, the rest left open under a new id.
- **Review:** clean
- **Accepted:** <pending the owner>

### Slice 3: the Director's rule and the manual

- **Commit:** 2026-11-answers-between-rounds: Slice 3, the Director's rule and the manual
- **Summary:** the Director skill (`skills/baton-director/SKILL.md`, and its copy in §13.3): the hard rule against editing anything under `.baton/` now says "not even to record something Baton has no command for", and that the Director tells the owner, records what it can (`--note`) and reports the gap with `feedback` (Decision 0184, item 5); *Answering requests* says what open questions are, that nothing waits for them, when to offer them (next time, at the latest with a decision that restarts the work) and the three ways to record them.
- **Design docs:** `design/director-interface.md` §13.3 (the skill's copy).
- **Manual:** `manual/user/answer-questions-and-decide.md` (new section *Choices made on a best guess*, `#best-guesses`; **Give it another round** can carry answers; **Confirm or correct these**); `manual/admin/director-commands.md` (`decide … answer`, `--answers` with a retry or reject, the `open_questions` request not counting as needing the owner); `manual/anchors.yaml` (the new anchor).
- **Tests:** existing checks cover the skill copy (`tests/test_director_surface.py`), the manual's format, anchors and links (`tests/test_manual.py`) and the generated reference (`tests/test_manual_gen.py`).
- **Review:** clean
- **Accepted:** <pending the owner>

### Finish

- **Full suite:** red on Slice 1 (e1f0276), Slice 2 (317610d) and the finish commit (a1d25f0), one record golden; repaired in the Slice 1 repair commit, whose run is required green.
