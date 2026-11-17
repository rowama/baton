# Design the process

Design the process for the rung in `profile`, in plain terms first. The `patterns` input holds
reusable process shapes: use them, and say in `summary` where and why you depart from one.

Return `stages`. Split the work until each stage has one kind of work (patterns 8 and 9). For each
stage give:

- `traits`: what its work is like, with a one-line `basis`: whether complete `rules` can be written
  for every input in scope (`complete`, `partial`, `none`); the form of its `input` (`structured`,
  `open`); whether the same input must give the same result (`repeatable`: `required`,
  `not_required`); its `effect` (`none`, `reversible`, `irreversible`: it spends money, changes
  something others depend on, or cannot be undone); whether a correct result can still be wrong
  about the world (`result`: `certain`, `uncertain`); and how its output can be `check`ed
  (`mechanical`, `source`, `judgment`).
- `done_by`: the simplest means that can do it, by pattern 10: `tool`, `automatic_check`, `person`
  or `ai`. Software before an AI worker.
- `acceptance`: the check on its output and what it establishes (`kind`: `format`, `rule`,
  `source` or `judgment`; `what`, in one line).
- what it needs, what it hands on, any decision the owner makes there, and what happens when it
  fails (`retry`, `revise`, `escalate`, `stop` or `accepted_risk`, with a `failure_note`).
- For a `tool` stage, `tool`: an `id` (lower case, digits and `_`), what it `does` in the owner's
  terms, its `input` and `output`, its `reach` (`workspace`, and `network: false` with no
  `secrets` at `software: simple`), and at least one worked example: the JSON `input`, any `files`
  it reads (`<input name>.<ext>` and their exact text), the `expected` output, any `artifacts` it
  writes (`<artifact>.<ext>` and their exact text), and what the example `says` in the owner's
  words. Draft the examples from what the owner told you; the owner approves them with the design.
- A tool is `kind: simple` (as above) unless the run's `software` rating is `engineered` and the
  stage needs real engineering: a real data format, rules with exceptions, or a package. Then give
  `kind: engineered`, no drafted `examples`, and instead a `contract` (the `input_schema` of its
  inputs file, the `output_schema` of its `output.json`, every `package` it needs with `why`, and
  the `budget_reason`: why it is one tool, with one command, inputs in and outputs out, nothing kept
  running and testable from examples; a `size_reason` only if it will be over 600 lines) and
  `examples_needed`: at least three examples the owner should supply, each saying `what` goes in and
  what should come out in their terms, one of them `awkward` (a case the owner finds hard). It is
  built later, to the owner's examples, by another worker. When the base recipe already has the
  tool, give `base`: `unchanged` when neither its contract nor the examples it needs change,
  `changed` otherwise; a tool the base recipe does not have is `new`.
- For an `ai` stage that software could do (`rules: complete` and `input: structured`, or
  `repeatable: required`), `executor_choice`: what `could_be` doing it, the `reason` (`ceiling`,
  `owner_choice` with the owner's confirmed entry as `ledger_id`, or `over_budget`), what it
  `gives_up` and what the software `would_cost`, in plain words.
- For each stage a person does and each one with an owner decision, `delegation`: whether letting
  the owner's AI assistant act for them there would be `risky`, and the `reason` in plain words.
  It is risky when the effect is `irreversible`, or when the owner accepts a risk or waives a check.

The run's ratings (in the packet) set the most software you may plan. At `software: none`, give a
stage software could do to another doer, record `executor_choice` with reason `ceiling`, and add a
`rating_signal` to your result once: `{axis: "software", suggested: "simple", reason}`, naming the
stages in the owner's terms, so the owner can raise the limit or keep it. At `software: simple`, a
tool stays within the tool budget (pattern 10); work over it is done another way, with reason
`over_budget`. A tool is `engineered` only at `software: engineered`; even then, prefer `simple`
where a one-file standard-library script will do. Where existing software the owner has could do a stage, record a `discovery` and do
the stage another way. When the process is made to run elsewhere, the stages here are the ones that
make it; for each step of the process being made, give in the document what its work is like and
who should do it, and plan no tool for it.

Then:

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
fails, and what is out of scope. For each small program: what it does, what it may touch, and its
worked examples in plain words. For each program built to the owner's examples: what it does, what
it may touch, the packages it needs and why, and the examples the owner will be asked to supply. For each part an AI worker does that a program could do: what a
program would have given (the same result every time, no cost each run, no AI service needed),
what it would have cost, and why it was not used. Mark the parts where letting an assistant act
for the owner would be risky, and why. No jargon.

Return the `discovery` records, updated.

`open_findings`, when given, are the audit's findings and the owner's note from the last attempt:
fix each one, or say in the document why not. Return the updated `ledger`. You may not promote an
`inferred` entry to `confirmed`.
