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
- A script a check runs must be a command the owner would expect; say what it runs and why.

Write the same design as a readable document in the `design_doc` artifact (markdown), for the
owner: the stages in order, who does each, what the owner decides, what happens when something
fails, and what is out of scope. No jargon.

`open_findings`, when given, are the audit's findings and the owner's note from the last attempt:
fix each one, or say in the document why not. Return the updated `ledger`. You may not promote an
`inferred` entry to `confirmed`.
