---
id: "0186"
title: "Recipe builder's design may not rest on a guessed choice: a gate refuses any inferred decision, smaller guesses are asked without blocking"
status: accepted
date: 2026-11-22
source: 'Owner, 2026-11-22, change 2026-11-builder-asks-not-guesses: "Any guessed choice (Recommended)"; "Pass, ask to confirm (Recommended)"; "Next build only (Recommended)"; Request "Approve"'
sections: ["§5.3", "§5.7", "§13.2"]
---

# 0186. Recipe builder's design asks about a choice that is the owner's instead of guessing it

## Context

In run `r_20261119_ee96` (baton-recipes, `recipe-builder@7`), round 3's design guessed five choices that change the stages (ledger entries `kind: decision`, `status: inferred`), listed them in its document and returned `completed` with no questions. The audit failed it for that (F33; readiness checks 17 and 20), which spent the group's last round. The design prompt already said to return `blocked` rather than guess; a prompt rule failed where principle §0 rule 2 asks for code. The same ledger carried a guessed decision from the profile (E26), which no step asked about.

Whether a guess changes the stages is a judgment, and the stages do not name the ledger entries they rest on, so code cannot tell. What code can tell is the entry's kind: a `decision` is the owner's choice by definition.

Options for the gate: refuse any `inferred` decision in a completed design (including inherited ones); refuse only those the design added; or no gate, the prompt alone. For smaller guesses (`assumption`, `requirement` and others): pass and ask the owner to confirm them without blocking (Decision [0184](0184-answers-outside-a-blocked-step.md)); block on them too; or not ask.

## Decision

1. **A gate refuses any guessed choice.** `recipe-builder@10`'s design step has a script gate that fails a completed design whose ledger holds any entry `kind: decision` with `status: inferred`, whichever step wrote it. It names each entry and tells the worker to return `blocked` with a question for each (`id`, `ask`, `why`, `best_guess`, `options`; §7.2). A Baton helper the gate runs does the check (`baton recipe check-guesses --result`), reading the step's latest submitted result from the run's record, as `guides check --artifact` does; `recipe check` is unchanged, so recipes already pinned keep their gates' behavior.
2. **Smaller guesses are asked without blocking.** An `inferred` entry of another kind does not fail the gate. The design may pass and list such guesses as `questions_for_human` for the owner to confirm, which hold nothing up (Decision 0184). The audit still judges whether a guess matters (readiness checks 6, 17 and 20), including a decision written down as an assumption.
3. **The prompt says it where the ledger rules are.** A choice that is the owner's is asked, not guessed; something for the owner to confirm is a question, not a section of the document; an entry the owner answered becomes `confirmed` with their words.
4. **The audit is unchanged.** Its checks 17 and 20 already say what the gate enforces.
5. **Rollout.** `recipe-builder@9` is frozen as a test fixture. A run keeps the version it was started with (§5.8): the run in progress in baton-recipes keeps `@7`, and its next build uses `@10`.
