# Design the process

Design the process for the rung in `profile`, in plain terms first. The `patterns` input holds
reusable process shapes: use them, and say in `summary` where and why you depart from one.

Return `stages`. For each stage: who does it (`person`, `ai` or `automatic_check`), what it needs,
what it hands on, any decision the owner makes there, and what happens when it fails (`retry`,
`revise`, `escalate`, `stop` or `accepted_risk`, with a `failure_note`). Then:

- Every goal in the ledger maps to a stage whose output shows it was met.
- Every stage's inputs have a producer; nothing depends on itself.
- Every output has an acceptance check, not only "the worker finished".
- Every loop is bounded and says what happens at its limit.
- Anything left out on purpose is listed in `excluded`, and has an `excluded` ledger entry.
- A fact about this one job stays out of the process; it becomes an input a run supplies. An
  `instance` ledger entry never appears in the stages.
- Take the `discovery` records from `research` when it is given (it holds the owner's decisions), otherwise from `profile`.
  Every `discovery` record reaches the design. A `before_design` record is `decided` (the owner's
  confirmed `decision` entry is in the ledger and `decision.ledger_id` names it) and the stages
  are shaped for that choice. If you find a choice that changes the stages that is not decided,
  return `blocked`: say which question needs research and the owner's answer; do not guess, and do
  not add or reorder stages around it later.
- An `in_generated_recipe` record is a stage that researches the options for the job, a stage the
  owner decides at, and the stages that use that decision, in that order, before any work that
  depends on the choice. Name them in `generated` (`research_step`, `decision_step`, `consumers`,
  each a stage `id`). The research stage needs a worker able to read current external sources.
  The decision stage hands the owner's choice on as an output the consuming stages take as an
  input. Say why one shape serves every alternative. The choice itself is a value a job supplies,
  never a fixed target, unless the ledger shows the owner's rung is specific to one target.
- A script a check runs must be a command the owner would expect; say what it runs and why.

Write the same design as a readable document in the `design_doc` artifact (markdown), for the
owner: the stages in order, who does each, what the owner decides, what happens when something
fails, and what is out of scope. No jargon.

Return the `discovery` records, updated.

`open_findings`, when given, are the audit's findings and the owner's note from the last attempt:
fix each one, or say in the document why not. Return the updated `ledger`. You may not promote an
`inferred` entry to `confirmed`.
