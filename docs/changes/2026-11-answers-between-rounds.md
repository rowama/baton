---
id: 2026-11-answers-between-rounds
title: "The owner's answers can be recorded at any decision that retries the work, not only at a blocked step"
status: proposed
level: standard
decisions: ["0184", "0181", "0170"]
touches: [design/packets.md, design/director-interface.md, design/runtime.md]   # §7.1, §7.2, §13.1, §13.3, §13.8, §8.10
manual: [reference/commands.md, recipes/recipe-builder.md]
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

To be settled with Decision 0184. Under its suggested answer:

- A `passed` result, and a review step's result, may carry `questions_for_human`; they are recorded in the run as open questions of the step that asked.
- Every pending decision whose `retry` starts more work on that step or its group (the iteration limit, an escalation, a rejected human gate) lists the open questions, and its `retry` accepts `--answers <file>` (and `answer --file`), checked as a blocked step's answers are: ids known, `owner_words` required, `needed` questions answered unless `--partial`.
- The answers are recorded as `human_decision {kind: answers}` against the step that asked, and reach every later attempt and review of it through `answers_earlier`, as 0181 says.
- The iteration limit's interaction request carries an answer schema with one field per open question.
- A recorded answer closes its question; a question already answered in the run is not listed again.
- The Director skill's hard rule says that when Baton has no command for something the owner decided, the Director tells the owner and records what it can (`--note`), and never writes events or files under `.baton/` to fill the gap.

### Open questions

- Decision [0184](../decisions/0184-answers-outside-a-blocked-step.md) (proposed): how answers are recorded when the questions did not come from a blocked step. Suggested: a result may carry questions without blocking, and any retrying decision takes `--answers` against them.
- Should events 193 and 229 in `r_20261119_ee96` be left as they are? Suggested: leave them. They match the owner's words, the hash chain is intact, and the log is append-only; this change's Log notes them as the case that prompted it.

## Design

To be written once 0184 is decided. Expected doc edits:

- `design/packets.md` §7.2: `questions_for_human` may appear on a non-blocked result; what intake records. §7.1: `prior_feedback.answers` after a non-blocked retry.
- `design/runtime.md` §8.10: intake records a passed result's questions as open.
- `design/director-interface.md` §13.1 (`decide`, interaction requests: answer schema on the iteration limit and other retrying decisions), §13.3 (the skill's hard rule and *Answering requests*), §13.8 (the confirm-back seam: answers outside a blocked step).

## Plan

To be written once the Design is settled. Likely slices: open questions from any result; `--answers` at retrying decisions and their interaction requests; the skill's rule and the manual.

## Log
