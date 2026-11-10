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

Judge 9 and 10 against the rung recorded in the ledger, not against what you think the owner should
have chosen. The owner decides how general a process is.
