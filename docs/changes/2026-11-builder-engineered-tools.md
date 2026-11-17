---
id: 2026-11-builder-engineered-tools
title: "Recipe builder can build a tool that needs real engineering: tests from the owner's examples first, then a bounded build and review loop"
status: proposed
level: major
decisions: ["0155", "0154", "0156", "0158"]
touches: [design/recipes.md, design/director-interface.md]
manual: []
---

# Recipe builder can build a tool that needs real engineering: tests from the owner's examples first, then a bounded build and review loop

## Request

### Problem

After [2026-11-builder-step-design](2026-11-builder-step-design.md), `recipe-builder` writes a tool in one pass: one file, the standard library only, checked against examples it drafted. That covers adding up a list. It does not cover a tool that parses a real export, matches records with rules that have exceptions, or needs a package. Written in one pass with invented examples, such a tool passes its own tests and fails on the owner's data.

The owner's direction (Decision [0155](../decisions/0155-recipe-builder-builds-software.md)): the builder handles more than one-shot software, with a test and verification loop, for possibly many tools, while knowing it cannot do large-scale engineering. The tests come from the owner's examples, are written before the code by a different worker, and are then protected. A tool budget bounds what is built; anything over it is a separate software project. Choosing this path means the recipe may need the attention a software project needs, and the owner is told so.

This change depends on `2026-11-builder-step-design` being done.

### Acceptance criteria

1. **A third setting.** The builder's `software` rating gains `engineered` above `simple`, in a new version of `recipe-builder`. Projects pinned to an earlier version keep it. Choosing `engineered` always waits on the owner, who is told plainly what it gives and what it asks of them: real examples, more decisions, and upkeep when the work changes.
2. **Each engineered tool has a contract.** The design gives, for each one: what it does, its input and output schemas, what it may touch, every package it needs with the reason, and why it is within the tool budget.
3. **The examples are the owner's.** For each engineered tool the owner supplies example inputs with the results they expect, as files. At least three per tool, one of them a case the owner considers awkward. The builder may propose further examples; each counts only once the owner has confirmed its expected result.
4. **Tests are written before the code, by a different worker.** The examples are placed in the tool's folder before anything is implemented, by a worker other than the one that will write the tool. The implementing worker cannot change them: a changed example fails the attempt.
5. **Each tool is built in a bounded loop.** Implement, run the examples, review independently; repeat with the failures and findings, at most three times per tool. At the limit the owner chooses: try again with their note, simplify (the stage is done another way, with the record `2026-11-builder-step-design` requires), or stop.
6. **Passing means the owner's examples pass.** A tool is accepted only when every example passes in the tool's own environment, twice running with identical results where the stage must be repeatable.
7. **The review is independent and specific.** A reviewer from a different vendor checks the tool against its contract: it does what the contract says, touches only what it declares, uses only the packages the design named, and handles the awkward case for the right reason and not by special-casing the example.
8. **Packages are named, pinned and shown.** A tool may use third-party packages. Each is named in the design and shown to the owner before the build. The lock holds exact versions with hashes (§5.9).
9. **The budget is enforced.** The audit blocks a design whose tool exceeds the budget of Decision 0155 (one entry command, inputs in and outputs out, no service kept running, no state beyond what it declares, one effort band, testable from examples). `baton recipe check` enforces the parts that can be checked mechanically. Work over the budget is recorded as a separate software project the owner may start, and the stage is done another way meanwhile.
10. **Tools are built one at a time and reported plainly.** With several engineered tools, each has its own loop and its own result. The walkthrough says for each tool which examples it passed, in the owner's terms, and what it needs installed and may touch.
11. **Simple tools are unchanged.** A tool at the `simple` setting is still written in one pass as in `2026-11-builder-step-design`.
12. **Manual and design are current.**

### Open questions

Each has a suggested answer, assumed until the owner decides.

1. **How do the owner's examples reach the builder?** *Suggested:* as project documents bound to a role, `examples` (many), one folder per tool; the Director helps the owner gather and attest them (Decision 0142). *Rationale:* they are the owner's files, they get provenance, and a later builder run can reuse them.
2. **How many examples at least?** *Suggested:* three per tool, including one awkward case, as in criterion 3. *Rationale:* one example proves a happy path; three with an awkward one start to pin behaviour without burdening the owner.
3. **When does the owner supply them?** *Suggested:* after approving the design, before the build; the build of a tool waits on its examples, and other tools proceed. *Rationale:* the owner cannot give examples for a contract they have not seen.
4. **Who places the examples and writes the tool's step?** *Suggested:* `generate`, which already writes the package; the implementing worker must differ from it by vendor. *Rationale:* it satisfies "a different worker" with no new step.
5. **May the implementing worker add its own tests?** *Suggested:* yes, in the tool's folder, but only the owner's examples decide acceptance. *Rationale:* its own tests help it work; they prove nothing about the owner's intent.
6. **What can `baton recipe check` enforce of the budget?** *Suggested:* one entry command; no listening socket or background process left after a run (checked by the tool runner); reach as declared; a cap on the tool's size, proposed at 600 lines across its files, above which the audit must record why it is still one tool. *Rationale:* a size cap is crude, but it is the only mechanical signal that a tool has become a project, and it only asks for a reason.
7. **How does `simplify` work at the limit?** *Suggested:* the group's instance is abandoned for that tool and `design` is revised for that stage only, behind the owner's decision. *Rationale:* it reuses revision; nothing else is redone.
8. **Building needs the network** (to resolve and download packages). *Suggested:* the implementing step requires a worker with shell and network access and says so; tools with no packages need neither. *Rationale:* honest requirements; routing does the rest.
9. **What happens when a recipe with engineered tools is later specialized or changed?** *Suggested:* a builder run rebuilds only tools whose contract or examples changed, and reruns every tool's examples. *Rationale:* examples are cheap to rerun and catch a break in an untouched tool.

### Out of scope

- **Software over the tool budget.** A separate project, through `eng-process` once it exists (Decision 0155, item 6).
- **Tools that drive other software, and waiting tools:** their own changes.
- **Screens for a person's step:** [2026-11-person-step-forms](2026-11-person-step-forms.md), on hold.
- **Runtimes other than Python** (Decision 0156, item 2).
- **Testing the finished recipe end to end** (Decision [0098](../decisions/0098-no-scenario-testing-yet.md)).

## Design

For the owner's approval, with the Request. It builds on `recipe-builder@4` as `2026-11-builder-step-design` leaves it, and is refined against that change's final form.

### Shape

- **Rating.** `software: { scale: [none, simple, engineered] }`. `profile` recommends `engineered` only when the idea shows work with exceptions or real data formats, and says what it asks of the owner.
- **Design output.** A stage with `done_by: tool` gains `tool.kind` (`simple` | `engineered`). An engineered tool carries `contract {input_schema, output_schema, reach, packages [{name, why}], budget_reason}` and `examples_needed` (what the owner should supply, in plain words). The schema allows `engineered` only when the run's rating is `engineered`.
- **`generate`** writes, for an engineered tool: `tools/<id>/tool.yaml`, the schemas, the step that names the tool, and `tools/<id>/examples/` copied from the bound `examples` documents. It writes no implementation. Its `baton tools test` gate applies to simple tools only.
- **A new group, `build_tools`** (`applies_to: {software: [engineered]}`), after `generate`: one instance per engineered tool, `repeat_until` the review passes, `max_iterations: 3`.
  - `implement`: workspace write, shell; independent of `generate` by vendor; `protect: {paths: ["recipes/drafts/<slug>/tools/<id>/examples/**"], on_violation: fail}`; gates: `baton tools test <package> --tool <id> --repeat 2`, then `baton recipe check` for the budget.
  - `review`: a review gate, `different_vendor`, with a rubric for a tool against its contract.
- **`baton tools test`** gains `--tool <id>` and `--repeat <n>` (run each example n times and compare the results with each other as well as with the expected one).
- **`baton recipe check`** gains the mechanical budget rules of open question 6.
- **`accept`** depends on `build_tools`; the walkthrough is completed after the loop with each tool's results.
- **`static/patterns.md`** gains *contract, examples, then code*; **`static/readiness.md`** gains checks for the contract, the named packages and the budget.

### Doc edits

- `design/recipes.md` §5.7: the `engineered` setting, the contract, the `build_tools` group and its limits. §5.9: `--tool`, `--repeat`.
- `design/director-interface.md` §13.1: the `tools test` options; §13.3: how the Director helps an owner gather examples.

### Manual edits

To be listed when the change is accepted. Expected: `recipes/recipe-builder.md`, an owner's topic on supplying examples, `reference/commands.md`.

### Decisions

- [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): the ceiling, the budget, examples from the owner, the planned changes.
- [0154](../decisions/0154-tool-steps.md), [0156](../decisions/0156-tool-steps-details.md), [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md) (accepted): what a tool is and how it runs.
- The nine open questions above become one record when the owner answers them.

## Plan

Slices as proposed; refined once the Request and Design are approved and `2026-11-builder-step-design` is done.

### Slice 1: the checks an engineered tool must pass

- **Outcome:** `baton tools test --tool --repeat` and the budget rules of `baton recipe check` exist and are tested on fixtures.
- **Criteria:** one tool selected; repeat comparison; a tool leaving a process behind is reported; the size rule and its reason; reach as declared.
- **Effort:** M

### Slice 2: the design carries contracts

- **Outcome:** at `engineered`, a design gives each such tool a contract and says what examples the owner must supply; the audit blocks one over budget or with unnamed packages.
- **Criteria:** the rating and what the owner is told; schema rules; the pattern and rubric checks; `generate` writing the skeleton and the examples; a tool with too few examples waits on the owner.
- **Effort:** M

### Slice 3: the build loop

- **Outcome:** a described process with one awkward rule-based stage yields a recipe whose engineered tool passes the owner's examples, reviewed independently and approved.
- **Criteria:** one instance per tool; protected examples; the loop's three outcomes at the limit; packages locked with hashes; scenarios for a tool that passes first time, one that needs a second iteration, one simplified at the limit and a run with two tools; the walkthrough; the manual.
- **Effort:** L

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0155 and the owner's discussion of 2026-11-15. It builds on `2026-11-builder-step-design`, which is not yet approved, so its Design is provisional on that change's final form. No code changed.
- **Owner decision:** 2026-11-16, "Go ahead and write 3 and 4."
- **Accepted:** No; proposal only. Nine open questions await the owner.
