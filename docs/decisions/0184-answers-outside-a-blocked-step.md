---
id: "0184"
title: "Questions without blocking: a result may ask the owner to confirm its guesses, answered at any time or with a retry, holding nothing up"
status: accepted
date: 2026-11-22
source: 'Owner, 2026-11-22, change 2026-11-answers-between-rounds: "Non-blocking questions (Recommended)"; "Any time, plus with a retry (Recommended)"; "No; listed, reviews judge (Recommended)"; "Leave them (Recommended)"'
sections: ["§7.2", "§13.1", "§13.8"]
---

# 0184. How the owner's answers are recorded when the questions did not come from a blocked step

## Context

The owner's confirmed answers can be recorded in exactly one way: `decide <run> <step> retry --answers <file>`, on a step escalated `blocked` with `questions_for_human` (§13.8). Ids are checked against those questions, `owner_words` is required, and the answers last across rounds (Decision [0181](0181-first-use-feedback-routing-and-answers.md), item 2).

Questions also reach the owner another way. In run `r_20261119_ee96`, recipe-builder's design step guessed five choices, marked them `inferred` in its ledger, listed them for the owner in its document, and passed. The audit failed it for relying on unconfirmed choices (F33), and the group reached its iteration limit. The owner answered all of them and approved another round, but the iteration limit's `retry` takes only `--note`. The Director wrote `human_decision {kind: answers}` events into the run log by hand (events 193 and 229), breaking the hard rule against editing anything under `.baton/`, so that the answers would carry as 0181 intends. A note alone reaches only the next attempt, as free text, without question ids, and does not reach later rounds or the review.

Options:

1. **A result may carry questions without blocking.** A `passed` result may list `questions_for_human` (§7.2) too: choices the worker made on a guess that the owner should confirm. A review step may raise them the same way. Baton keeps every unanswered question in the run. The step's or its group's next pending decision (an iteration limit, an escalation, a rejected gate) lists them, and its `retry` accepts `--answers` checked against them. Its interaction request gets one field per question, as a blocked step's does. The answers are recorded against the step that asked, so 0181's carry-forward works unchanged. Generic: it reuses §7.2 and adds no concept or recipe declaration.
2. **A recipe names its own assumptions field.** A step declares where its output keeps its guesses (for recipe-builder, ledger entries with `status: inferred`), and Baton reads them as questions. More precise for recipes that already keep such a list, but it puts a reading of recipe output into the runtime and is one more declaration.
3. **Answers without a question list.** `--answers` is accepted at any pending decision. Ids are not checked; `owner_words` still is. Least work, but loses the check that every answer answers something that was asked.

Suggested: option 1. It generalizes the existing mechanism instead of adding a parallel one (principle 2), keeps the runtime recipe-neutral, and gives every renderer the same answer form a blocked step already has.

## Decision

Option 1, with these details:

1. **A result may carry questions without blocking.** A `completed` result may list `questions_for_human` (§7.2): choices the worker made on a guess that the owner should confirm. A review step may raise them the same way. Intake records them, normalized, on `result_submitted` as `questions` (an empty list when there are none), for a result it accepts; a rejected result records none. A worker that cannot go on without an answer still returns `blocked`.
2. **Open questions.** A step's open questions are those of its latest accepted `completed` result, every iteration of its group counting as one step, less those answered anywhere in the run for that step. A question the latest round no longer asks is no longer open. `status` and `board` list them (`open_questions`), and each asking step's open questions are one interaction request (`kind: open_questions`).
3. **Answered at any time, or with a retry.** `decide <run> <step> answer --answers <file> --note "<owner's words>"` records answers to the open questions of `<step>` (the asking step's path, as listed), whatever state the run is in, and `answer` does the same for the request. With a retry, `decide <run> <ref> retry --answers <file>` on an iteration limit or an escalation that is not `blocked` (and `reject --answers` on a human gate) first records answers to the open questions of the steps at or under `<ref>`, one record per asking step, then the decision. Each answer is checked as a blocked step's is (its id among the open questions, `owner_words` required); a partial set is always allowed, since nothing waits for them, and an id that two steps in scope both ask is refused (answer those one step at a time). Each is recorded as `human_decision {kind: answers}` against the asking step and attempt, so the answers reach every later attempt and review of that step (Decision [0181](0181-first-use-feedback-routing-and-answers.md), item 2). A blocked step's answers are unchanged.
4. **Nothing waits for them.** Open questions are not pending decisions: they do not set `needs_owner`, and no step, group or run waits for them. A recipe's review decides whether work may rest on a guess.
5. **The Director never fills a gap by hand.** When Baton has no command for something the owner decided, the Director tells the owner and records what it can (`--note`); it never writes events or files under `.baton/`.
6. **The records already written by hand stay.** The two `human_decision {kind: answers}` events a Director wrote into run `r_20261119_ee96` (seq 193 and 229) match the owner's words and keep their place in the append-only log.
