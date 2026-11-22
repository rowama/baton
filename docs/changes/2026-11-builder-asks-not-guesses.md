---
id: 2026-11-builder-asks-not-guesses
title: "Recipe builder's design asks the owner about a choice that is theirs instead of guessing it, and a gate holds it to that"
status: accepted
level: standard
decisions: ["0186", "0184"]
touches: [design/recipes.md, design/director-interface.md]   # §5.7 (recipe-builder), §5.3 and §13.2 (the helper a script gate runs)
manual: [recipe-sources/recipe-builder.md, admin/recipes-and-vendoring.md, reference/commands.md]
---

# Recipe builder's design asks the owner about a choice that is theirs instead of guessing it, and a gate holds it to that

## Request

### Problem

Found by the owner on 2026-11-22 in run `r_20261119_ee96` of baton-recipes (`recipe-builder@7`), group `shape/x5b12127`. Evidence under `/mnt/d/rob/projects/baton-recipes/.baton/runs/r_20261119_ee96/`.

- Round 3's design (`i3/design`, `attempt-1/result/result.json`) could not settle five choices that change the stages: version bumps (A-VER-1), re-checking hand-checked work (A-SLICE-1), unchecked gaps (A-GAP-1), rollout widening (A-ROLL-1) and the limit stop (A-LATE-1). It guessed them: each is a ledger entry `kind: decision`, `status: inferred`, listed in its document under "14. Your answers this design rests on". It returned `completed` with no `questions_for_human`. Its ledger carried a sixth inferred decision from the profile, E26 (the four dials replace small, medium and large).
- The audit (`i3/audit`) failed it, rightly, for F33, "Consequential design choices remain unconfirmed" (readiness checks 17 and 20). That spent the group's last round (`max_iterations: 3`; events 223 to 226). The owner approved another round and answered (events 229 to 232). One round of a strong model, about 35 minutes, plus its audit, went on questions only the owner could answer.
- The design prompt already forbids it (`prompts/design.md`: "If you find a choice that changes the stages that is not decided, return `blocked` … do not guess"). The rule sits in the middle of the discovery rules, far from the ledger rules the worker did follow ("You may not promote an `inferred` entry to `confirmed`"). A rule that must hold is enforced in code, not by a prompt (principle §0, rule 2).

Baton's side of the same incident (answers outside a blocked step had no way in) is done: change `2026-11-answers-between-rounds`, Decision 0184. A completed result may now carry `questions_for_human` that hold nothing up.

### Acceptance criteria

- A new published version of recipe-builder (10); version 9 is kept as a test fixture under `tests/fixtures/recipes/recipe-builder-v9`, like the earlier versions.
- The design step has a script gate that fails a completed design whose ledger holds a `kind: decision` entry with `status: inferred`, naming each entry, and telling the worker to return `blocked` with a question for each (`id`, `ask`, `why`, `best_guess`, `options`; §7.2). A design with none passes it.
- The design prompt states the rule next to the ledger rules: a choice that is the owner's is asked, not guessed; a choice for the owner to confirm is a question, not a section of the document; and the shape of a good question.
- The audit's rubric is unchanged; the gate's rule and readiness checks 17 and 20 say the same thing.
- The recipe's manual page says the builder asks before it designs around a choice that is the owner's.

The owner approved this Request on 2026-11-22 and answered the open questions (Decision 0186).

## Design

The stages do not name the ledger entries they rest on, so code cannot tell whether a guess changes them; the entry's kind can. A `decision` is the owner's choice, so a completed design may hold none that is still `inferred`, whichever step wrote it. A smaller guess passes the gate, and the design asks the owner to confirm it with a question that holds nothing up (Decision 0184); the audit still judges it.

The check is a new CLI-only helper, `baton recipe check-guesses [<ledger file>] | --result`, beside `recipe check`. With `--result`, in a script gate, it reads the ledger of the latest submitted result of the step being verified (`BATON_RUN_ID`, `BATON_STEP_PATH`), from the run's record, as `guides check --artifact` does. `recipe check` is not changed, because a recipe already pinned runs today's Baton commands in its gates: a new rule there would change what an old version's `generate` accepts. A failure names each entry, its statement and its guess, so the next attempt can ask at once without redoing the design.

### Doc edits

- `design/recipes.md` §5.3: `baton recipe check-guesses` and what it reports. §5.7: recipe-builder@10, the design step's new gate in the steps table, and a paragraph on the rule and the frozen `@9`.
- `design/director-interface.md` §13.2: `recipe check-guesses` among the CLI-only helpers script gates run.

### Manual edits

- `manual/admin/recipes-and-vendoring.md`: `baton recipe check-guesses`, beside `recipe check`.
- `manual/reference/commands.md`: regenerated (the new command's help).
- `manual/recipe-sources/recipe-builder.md`: the builder asks before it designs around a choice that is yours, and may ask you to confirm smaller guesses without stopping.

### Decisions

- [0186](../decisions/0186-builder-asks-not-guesses.md) (accepted 2026-11-22): the gate refuses any inferred decision; smaller guesses are asked without blocking; the audit is unchanged; `@9` frozen, a run keeps its version.
- [0184](../decisions/0184-answers-outside-a-blocked-step.md): questions on a completed result that hold nothing up, which the smaller guesses use.

## Plan

### Slice 1: a check for guessed choices

- **Outcome:** `baton recipe check-guesses` refuses a ledger, or a step's submitted result, that holds a guessed choice.
- **Criteria:**
  - a ledger with an `inferred` `decision` entry fails (exit 1), one `ERROR` line per entry with its id, statement and the instruction to return `blocked` with a question;
  - a ledger with only other inferred kinds, or confirmed decisions, passes (exit 0);
  - `--result` reads the latest submitted result of `BATON_STEP_PATH` in `BATON_RUN_ID`; outside a gate, or with no result, it is a usage error; a file and `--result` together are refused;
  - a malformed ledger is reported, not crashed on.
- **Effort:** S

### Slice 2: recipe-builder@10 asks instead of guessing

- **Outcome:** the published recipe-builder's design step is gated by the check, and its prompt says plainly when to ask.
- **Criteria:**
  - `recipe-builder@10` loads cleanly; its design step's gates are schema, then `baton recipe check-guesses --result`;
  - `@9` is frozen under `tests/fixtures/recipes/recipe-builder-v9` and still loads as `@9`;
  - the design prompt states the rule next to the ledger rules and the shape of a question;
  - a run of `@10` whose design guesses a choice fails the gate and retries; one that asks with `blocked` escalates with the questions; one that passes with smaller guesses as questions passes the gate and lists them as open questions;
  - the manual's recipe page says it.
- **Effort:** M

## Log

### Slice 1: a check for guessed choices

- **Commit:** 2026-11-builder-asks-not-guesses: Slice 1, a check for guessed choices
- **Summary:** `recipe_check.py`: `guessed_choices` (one problem per `decision` entry still `inferred`, quoting its statement, cut at 200 characters, and saying to return `blocked` with a question for it or record the owner's answer as `confirmed`; other inferred kinds pass; a malformed ledger or entry is a problem), `check_guesses_file`, and `check_guesses_result` (the `ledger` in the output of the latest `result_submitted` for the step, read from the run's CAS, as `guides.check_artifact` does). CLI: `baton recipe check-guesses [<ledger>] | --result` (CLI only, a gate helper; `recipe.check_guesses_usage` for both or neither, or `--result` outside a gate). `recipe check` is unchanged, so pinned recipes' gates keep their behavior.
- **Design docs:** `design/recipes.md` §5.3 (the new helper); `design/director-interface.md` §13.2 (among the CLI-only gate helpers).
- **Manual:** `manual/admin/recipes-and-vendoring.md` (the helper, beside `recipe check`); `manual/reference/commands.md` regenerated; `manual/anchors.yaml` (its anchor).
- **Tests:** `tests/test_recipe_check.py` (quick): a guessed choice is named with what to do instead; other guesses, confirmed and excluded choices pass; every guess is reported and a long statement cut; a malformed ledger or file is reported; the CLI with a file, `--json`, and its three usage errors; `--result` reads the step's latest submitted result in a real run, and reports a step with no result, an unknown run and an output with no `ledger`.
- **Review:** clean
- **Accepted:** <pending the owner>
