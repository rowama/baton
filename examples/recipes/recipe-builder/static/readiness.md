# Readiness rubric

A design is ready when every check below passes. Report a finding, at the severity shown, for each
that does not. Complete means complete within the agreed scope: every material requirement and
foreseeable failure is handled, and anything left out is an `excluded` ledger entry the walkthrough
names.

| # | Check | Severity |
|---|---|---|
| 1 | Every goal in the ledger maps to a stage whose output shows it was met | high |
| 2 | Every stage's inputs have a producer, and nothing depends on itself, directly or in a loop | high |
| 3 | Every output has an acceptance check, not just "the worker finished" | high |
| 4 | Every foreseeable failure has a disposition: retry, revise, escalate, stop, or accepted risk | high |
| 5 | No `open` ledger entry reaches the design | high |
| 6 | Every consequential `inferred` entry was confirmed by the owner. Consequential: it changes who does a stage, what a check requires, or what the owner gets at the end | high |
| 7 | Every `confirmed` entry carries the owner's words | high |
| 8 | Loops are bounded and say what happens at the limit | medium |
| 9 | Too narrow: a job the owner placed inside the chosen rung would need a stage the design lacks | high |
| 10 | Too broad: a stage's instructions cannot say anything specific to the work, so its check is empty | high |
| 11 | A script check runs only commands the owner would expect | high |
| 12 | No fact about the owner's one job (`instance` scope) appears in the stages | high |
| 13 | The design follows `patterns.md`: its process shape, bounded loops and failure dispositions match the reusable shapes there, or a stated departure is justified | high |
| 14 | Something left out on purpose has an `excluded` ledger entry and is listed in `excluded` | medium |
| 15 | The document is in the owner's terms, with no jargon, and shows who does each stage, what the owner decides, what happens on failure, and what is out of scope | medium |
| 16 | Every discovery record reaches the design, with its timing reason; none was dropped or left unexamined because the work was rated simple | high |
| 17 | A choice that changes the stages, workers, artifacts or checks is decided by the owner (a confirmed `decision` entry with their words) before the stages it affects | high |
| 18 | A comparison rests on sources actually read, with the date each was read, and says what each option needs from the process; an unsupported claim is not marked researched | high |
| 19 | A deferred choice has a research stage, an owner decision stage and the stages that use it, in that order, with the decision handed on as an input; the claim that one shape serves every alternative is argued | high |
| 20 | A recommendation, inference or a worker's claim of approval does not stand in for the owner's choice; a firm constraint the owner named is not compared away, and a fixed target appears only where the agreed scope is specific to it | high |
| 21 | One kind of work per stage: no stage both interprets open-ended material and applies rules, has two doers, or has outputs that need different checks (patterns 8 and 9) | high |
| 22 | Every stage's `traits` are given with a basis that fits the work, and its doer follows from them by pattern 10 | high |
| 23 | An AI stage that software could do (complete rules and structured input) carries its `executor_choice`, and the reason holds: the software rating is `none`, the owner chose it (a confirmed ledger entry with their words), or the work is over the tool budget | high |
| 24 | A stage that must give the same result every time is not done by an AI worker unless the owner chose so, or the software rating is `none` and that is recorded | high |
| 25 | Each acceptance check names what it establishes, and a stage with an effect or an uncertain result has a check that establishes more than format | high |
| 26 | A tool is within the tool budget for the software rating, declares everything it touches, and, if it is simple, has at least one worked example the owner can read and judge | high |
| 27 | Each stage a person does and each owner decision says whether delegating it is risky, with a reason the owner would understand; one whose effect cannot be undone, or where the owner accepts a risk or waives a check, is marked risky | high |
| 28 | An engineered tool appears only at the `software` rating `engineered`, and only where a simple tool would not do; its contract gives input and output schemas, every package with a reason, and a budget reason that holds (one command, inputs in and outputs out, nothing kept running, testable from examples) | high |
| 29 | An engineered tool's `examples_needed` are at least three, one awkward, each saying in the owner's terms what goes in and what should come out, so the owner can supply them | high |

Judge 23, 24, 26 and 28 against the run's `software` rating (the packet carries the run's ratings).

Judge 9 and 10 against the rung recorded in the ledger, not against what you think the owner should
have chosen. The owner decides how general a process is.
