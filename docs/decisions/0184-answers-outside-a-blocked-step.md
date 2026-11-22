---
id: "0184"
title: "How the owner's answers are recorded when the questions did not come from a blocked step"
status: proposed
date: null
source: "Owner, 2026-11-22, run r_20261119_ee96: answers to the design's guessed choices had no supported way in (change 2026-11-answers-between-rounds)"
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

Not decided. The suggested answer is assumed until the owner decides; ask before building anything that depends on it.
