---
id: 2026-11-builder-engineered-tools
title: "Recipe builder can build a tool that needs real engineering: tests from the owner's examples first, then a bounded build and review loop"
status: in-progress
level: major
decisions: ["0155", "0164", "0154", "0156", "0158", "0159", "0162", "0034"]
touches: [design/recipes.md, design/director-interface.md, design/workers.md, design/runtime.md, design/gates-and-reviews.md]
manual: [admin/recipes-and-vendoring.md, reference/commands.md, anchors.yaml, recipe-sources/recipe-builder.md, recipes/recipe-builder.md]
---

# Recipe builder can build a tool that needs real engineering: tests from the owner's examples first, then a bounded build and review loop

## Request

### Problem

After [2026-11-builder-step-design](2026-11-builder-step-design.md), `recipe-builder` writes a tool in one pass: one file, the standard library only, checked against examples it drafted. That covers adding up a list. It does not cover a tool that parses a real export, matches records with rules that have exceptions, or needs a package. Written in one pass with invented examples, such a tool passes its own tests and fails on the owner's data.

The owner's direction (Decision [0155](../decisions/0155-recipe-builder-builds-software.md)): the builder handles more than one-shot software, with a test and verification loop, for possibly many tools, while knowing it cannot do large-scale engineering. The tests come from the owner's examples, are written before the code by a different worker, and are then protected. A tool budget bounds what is built; anything over it is a separate software project. Choosing this path means the recipe may need the attention a software project needs, and the owner is told so.

This change depends on `2026-11-builder-step-design`, now done.

### Acceptance criteria

1. **A third setting.** The builder's `software` rating gains `engineered` above `simple`, in `recipe-builder@6`. Projects pinned to an earlier version keep it. Choosing `engineered` always waits on the owner, who is told plainly what it gives and what it asks of them: real examples, more decisions, and upkeep when the work changes.
2. **Each engineered tool has a contract.** The design gives, for each one: what it does, its input and output schemas, what it may touch, every package it needs with the reason, and why it is within the tool budget.
3. **The examples are the owner's: supplied, or drafted and approved.** Each engineered tool has at least three examples, one of them a case the owner considers awkward. The owner supplies them as files. An owner who supplies fewer than three is warned plainly that three good examples are the minimum and that with fewer the tool is more likely to differ from what they expect; they may still go ahead, recorded with their words, and the builder drafts the missing ones, each counting only once the owner has approved it before the build (Decision 0164, items 2 and 4).
4. **Tests are placed before the code, by a different worker.** The examples are placed in the tool's folder before anything is implemented, by a step whose worker is of a different vendor than the one that will write the tool. Supplied files are copied byte for byte, and a check proves it. The implementing worker cannot change them: a changed example fails the attempt.
5. **Each tool is built in a bounded loop.** Implement, run the examples, review independently; repeat with the failures and findings, at most three times per tool. At the limit the owner chooses: try again with their note, simplify (the stage is done another way, with the record `2026-11-builder-step-design` requires), or stop.
6. **Passing means the owner's examples pass.** A tool is accepted only when every example passes in the tool's own environment, twice running with identical results (Decision 0164, item 10).
7. **The review is independent and specific.** A reviewer from a different vendor checks the tool against its contract: it does what the contract says, touches only what it declares, uses only the packages the design named, and handles the awkward case for the right reason and not by special-casing the example.
8. **Packages are named, pinned and shown.** A tool may use third-party packages. Each is named in the design and shown to the owner before the build. The lock holds exact versions with hashes (§5.9).
9. **The budget is enforced.** The audit blocks a design whose tool exceeds the budget of Decision 0155 (one entry command, inputs in and outputs out, no service kept running, no state beyond what it declares, one effort band, testable from examples). `baton recipe check` and the tool runner enforce the parts that can be checked mechanically (Decision 0164, item 6). Work over the budget is recorded as a separate software project the owner may start, and the stage is done another way meanwhile.
10. **Tools are built one at a time and reported plainly.** With several engineered tools, each has its own loop and its own result. The owner is shown for each tool which examples it passed, in the owner's terms, and what it needs installed and may touch.
11. **Simple tools are unchanged.** A tool at the `simple` setting is still written in one pass as in `2026-11-builder-step-design`.
12. **Manual and design are current.**

### Open questions

The owner answered all ten on 2026-11-17 (Decision [0164](../decisions/0164-builder-engineered-tools-details.md)): questions 1 and 5 to 10 as suggested, question 2 changed, and questions 3 and 4 given two paths. Questions 1, 4 and 7 were revised, and question 10 added, after checking them against `recipe-builder@5`.

1. **How do the owner's examples reach the builder?** *Decided:* the owner puts each example's files under `examples/<tool>/<example>/` in the project; the Director says what each tool needs and makes the folders; the owner attests the files, and the run binds them to one `many` role, `examples`. The build waits until they are bound. *Revised because* a role is bound once per run, so a per-tool wait would need per-instance roles, and one example is several files.
2. **How many examples at least?** *Decided:* three good examples per tool, one awkward. An owner who supplies fewer is warned that with fewer the tool is more likely to differ from what they expect, and may still go ahead; the builder drafts the missing ones and the owner approves them before moving on.
3. **When does the owner supply them?** *Decided:* after approving the design, before the build. The design's approval gate always applies at `engineered`.
4. **Who places the examples?** *Decided:* two paths in one new step, `examples` (at `engineered` only, after `generate`): supplied files copied byte for byte, the rest drafted and approved by the owner. It writes no code. The implementing worker differs from it by vendor. *Revised because* `generate` cannot require the role and still run at `simple`.
5. **May the implementing worker add its own tests?** *Decided:* yes, in the tool's folder; only the owner's examples decide acceptance.
6. **What can be enforced of the budget mechanically?** *Decided:* one entry command; reach as declared; 600 lines across the tool's files, above which the audit records why it is still one tool; the tool runner ends the tool's process tree and reports any process still running. Listening sockets are not checked.
7. **How does `simplify` work at the limit?** *Decided:* `generate` is revised with the owner's words; it does the stage another way with its record, and `build_tools` re-expands without that tool. *Revised because* revising `design` inside the `shape` group is refused (Decision [0034](../decisions/0034-revise-in-groups-deferred.md)).
8. **Building needs the network.** *Decided:* the implementing step requires shell and network access; a tool with no packages needs neither.
9. **A recipe with engineered tools changed later.** *Decided:* a builder run rebuilds only the tools whose contract or examples changed, and reruns every tool's examples.
10. **Must every run of an engineered tool give the same result?** *Decided:* yes; `--repeat 2` for every engineered tool.

### Out of scope

- **Software over the tool budget.** A separate project, through `eng-process` once it exists (Decision 0155, item 6).
- **Tools that drive other software, and waiting tools:** their own changes.
- **Screens for a person's step:** [2026-11-person-step-forms](2026-11-person-step-forms.md), on hold.
- **Runtimes other than Python** (Decision 0156, item 2).
- **Per-instance roles**, so that one tool's build waits only on its own examples (Decision 0164, item 1).
- **Testing the finished recipe end to end** (Decision [0098](../decisions/0098-no-scenario-testing-yet.md)).

## Design

For the owner's approval, with the Request. It builds on `recipe-builder@5` as `2026-11-builder-step-design` and `2026-11-quick-runs` left it.

### Shape

- **Rating.** `software: { scale: [none, simple, engineered] }` in `recipe-builder@6`. Every rating already waits on the owner at `profile` (`confirm_lowest` on `approach`, Decision 0163), so `engineered` does too. `profile` recommends `engineered` only when the idea shows work with exceptions or real data formats, and says what it asks of the owner. The profile schema keeps requiring `software: none` with `approach: quick`.
- **Design output.** A stage with `done_by: tool` gains `tool.kind` (`simple` | `engineered`). An engineered tool carries `contract {input_schema, output_schema, reach, packages [{name, why}], budget_reason, size_reason?}` and `examples_needed` (what the owner should supply, in plain words, including the awkward case). The schema allows `engineered` only when the run's rating is `engineered`.
- **The design's approval gate** (on `audit`) applies at `software: [simple, engineered]`, so at `engineered` the owner sees every contract and package before anything is built, at any `approach`.
- **`generate`** writes, for an engineered tool: `tools/<id>/tool.yaml`, `tools/<id>/contract.json` (the design's contract, so the checks and the reviewer read it beside the tool), the schemas, an empty `requirements.lock`, an empty `examples/` folder, and the step that names the tool; no implementation. Its output gains `engineered_tools [{id?, tool, title}]` (the `foreach` source below). Its `baton tools test` gate gains `--allow-unbuilt`: a tool with no implementation yet is listed as not built and skipped, so the gate still checks every simple tool.
- **The role.** `recipe-builder@6` declares a project input role `examples` (`many`, optional).
- **`example_plan`** (new, `applies_to: {software: [engineered]}`, after `generate`, a person's step like `accept`): for each engineered tool the owner chooses to supply its examples or to have some or all drafted. The Director shows `examples_needed`, warns an owner who would supply fewer than three that the tool is then more likely to differ from what they expect, makes the folders `examples/<tool>/<example>/`, and helps the owner attest and bind the files (§13.3). Choosing to have examples drafted is recorded with the owner's words. Output: `{tools: [{tool, supplied, drafted, owner_words?}]}`, where `supplied + drafted >= 3`.
- **`examples`** (new, `applies_to: {software: [engineered]}`, after `example_plan`): workspace write. Its inputs are `project.examples`, the plan and `generate`'s output. For each tool it copies supplied files byte for byte into `tools/<id>/examples/<name>/` (inputs to `inputs/`, an expected artifact to `expected/`), writes `expected.json` only from results the owner stated, drafts the missing examples (the awkward case first if it is missing), and writes `about.json` per example: `{source: owner | drafted, awkward, from: [paths]}`. It writes no code. Gates: schema; `baton tools examples <package> --run {{ run.id }}` (every engineered tool has at least three examples, one awkward; every `owner` file is byte-identical to the document bound to `examples` it names); then a human gate, "Build the tools to these examples?", that shows each drafted example and each `expected.json` written from the owner's words.
- **A new group, `build_tools`** (`applies_to: {software: [engineered]}`, after `examples`): `foreach: steps.generate.output.engineered_tools`, `foreach_if_source_skipped: skip`, `repeat_until` the review passes, `repeat_from: implement`, `max_iterations: 3`, `concurrency: 1`.
  - `implement`: workspace write, shell and network; `independence: {from_step: examples, level: different_vendor}`; `protect: {paths: ["recipes/drafts/**/tools/*/examples/**"], on_violation: fail}`; it writes the tool and its lock with hashes and may add its own tests in the tool's folder. Gates: `baton tools test <package> --tool {{ item.tool }} --repeat 2`, then `baton recipe check` for the budget.
  - `review`: `different_vendor` from `implement`, with `static/tool_review_rubric.md`: the contract, reach, named packages only, and the awkward case handled for the right reason. Findings gate blocks on critical and high.
  - At the limit: retry with the owner's note; simplify, by revising `generate` with the owner's words (Decision 0164, item 7); or stop (abandon the instance and the run's result waits on the owner).
- **`baton tools test`** gains `--tool <id>`, `--repeat <n>` (run each example n times; the results must match each other as well as the expected one) and `--allow-unbuilt`.
- **`baton tools examples`** (new): the check above. Its `--run` (default `BATON_RUN_ID`, which a script gate's environment carries) reads the run's `project_input_bound` record for `examples`.
- **The tool runner** ends the tool's process tree after each run (a process group on POSIX, a job object on Windows) and fails the attempt, naming the process, when one was still running.
- **`baton recipe check`** gains the budget rules: one entry command; reach as declared; a tool over 600 lines across its files needs `size_reason` in the design (`tool.over_size`).
- **`accept`** depends on `build_tools`; its inputs gain `steps.build_tools.outputs`, so the owner is shown each tool's result (examples passed in the owner's terms, what it needs installed, what it may touch) with the walkthrough.
- **Later builder runs.** With a `base_recipe` that has engineered tools, `design` marks each tool `unchanged`, `changed` or `new`; `generate` lists only changed and new tools in `engineered_tools`, and its gate reruns every tool's examples.
- **`static/patterns.md`** gains *contract, examples, then code*; **`static/readiness.md`** gains checks for the contract, the named packages, the budget and `examples_needed`.

### Doc edits

- `design/recipes.md` §5.7: `recipe-builder@6`, the `engineered` setting, the contract, `example_plan`, `examples`, `build_tools` and its limits. §5.9: `--tool`, `--repeat`, `--allow-unbuilt`, `baton tools examples`, the size rule.
- `design/workers.md` (the `tool` adapter): the process-tree check.
- `design/director-interface.md` §13.1: the `tools test` options and `tools examples`; §13.3: how the Director helps an owner gather, attest and bind examples, and records a choice to have them drafted.

### Manual edits

- Slice 1: `admin/recipes-and-vendoring.md` (`tools test --tool --repeat`, engineered tools' `contract.json` and `about.json`, `tool.unbuilt` and `--allow-unbuilt`, `tools examples`, a tool leaving a process running, the budget rules in `recipe check`); `reference/commands.md` and `anchors.yaml` regenerated (the new options and `baton tools examples`).
- Slice 2: `recipe-sources/recipe-builder.md` and the generated `recipes/recipe-builder.md` (the `engineered` limit, the new questions, a section "Programs built to your examples" (`#engineered-tools`) on supplying examples and the warning; the parts table gains the two steps); `anchors.yaml`.
- Slice 3: `recipe-sources/recipe-builder.md` and the generated `recipes/recipe-builder.md` (the three choices at the limit, each tool's result before approval; the parts table gains the build loop).

### Decisions

- [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): the ceiling, the budget, examples from the owner, the planned changes.
- [0164](../decisions/0164-builder-engineered-tools-details.md) (accepted): the answers to this change's ten open questions.
- [0154](../decisions/0154-tool-steps.md), [0156](../decisions/0156-tool-steps-details.md), [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md), [0159](../decisions/0159-tool-runs-env-inputs-build-outputs.md) (accepted): what a tool is and how it runs.
- [0162](../decisions/0162-builder-step-design-details.md) (accepted): the two rating axes, simple tools and where examples live.
- [0034](../decisions/0034-revise-in-groups-deferred.md) (accepted): revising inside a group is refused, which shapes `simplify`.

## Plan

Slices as proposed; refined once the Request and Design are approved.

### Slice 1: the checks an engineered tool must pass

- **Outcome:** `baton tools test --tool --repeat --allow-unbuilt`, `baton tools examples`, the tool runner's process-tree check and the budget rules of `baton recipe check` exist and are tested on fixtures.
- **Criteria:** one tool selected; repeat comparison; an unbuilt tool skipped and listed; a copied example that differs from its bound document; too few examples or no awkward one; a tool leaving a process behind; the size rule and its reason; reach as declared.
- **Effort:** M

### Slice 2: the design carries contracts, and the examples are placed

- **Outcome:** at `engineered`, a design gives each such tool a contract and says what examples the owner must supply; the audit blocks one over budget or with unnamed packages; `generate` writes the skeleton; `example_plan` and `examples` place supplied and drafted examples behind the owner's approval.
- **Criteria:** the rating and what the owner is told; schema rules; the pattern and rubric checks; the design's approval gate at `engineered`; supplied examples copied byte for byte; an owner who declines has examples drafted and approves them; the Director's guidance.
- **Effort:** M

### Slice 3: the build loop

- **Outcome:** a described process with one awkward rule-based stage yields a recipe whose engineered tool passes the owner's examples, reviewed independently and approved.
- **Criteria:** one instance per tool; protected examples; the loop's three outcomes at the limit; packages locked with hashes; scenarios for a tool that passes first time, one that needs a second iteration, one simplified at the limit and a run with two tools; each tool's result at `accept`; a later run rebuilding only a changed tool; the manual.
- **Effort:** L

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0155 and the owner's discussion of 2026-11-15. It builds on `2026-11-builder-step-design`, which is not yet approved, so its Design is provisional on that change's final form. No code changed.
- **Owner decision:** 2026-11-16, "Go ahead and write 3 and 4."
- **Accepted:** No; proposal only. Nine open questions await the owner.

### Open questions answered

- **Summary:** Checked the Request and Design against `recipe-builder@5`. Three suggested answers were revised: 1 (a role is bound once per run, so examples are bound together and the build waits on all of them), 4 (a step of its own, `examples`, since `generate` cannot require the role at `simple`) and 7 (simplify revises `generate`, since revising `design` inside `shape` is refused). Question 10 was added (repeat every engineered tool), and the socket check was dropped from 6. The owner accepted all ten, changing 2 (an owner may decline to supply examples; the builder drafts them for approval) and 3–4 (two paths: supplied and drafted). Recorded as Decision 0164. Request and Design updated: `recipe-builder@6`, `example_plan` and `examples` steps, `baton tools examples`, the process-tree check, `accept` showing each tool's result; `design/workers.md` added to `touches`. No code changed.
- **Owner decision:** 2026-11-17, "2-three without warning; against advice, a user can elect to provide no examples and the builder will generate filler examples than ask for the user to approve them before moving on. 3,4-Two paths, one for user supplied examples and one for AI generated examples. Accept all." (0164).
- **Accepted:** No; the Request and Design await the owner's approval.

### Question 2 clarified

- **Summary:** The record first read question 2 as a hard minimum with no warning. The owner meant the opposite: warn an owner who supplies fewer than three that the tool is then more likely to differ from what they expect, and let them go ahead. Decision 0164 item 2, criterion 3, question 2 and `example_plan` corrected. Drafted examples still fill each tool up to three, approved by the owner. No code changed.
- **Owner decision:** 2026-11-17, "I meant warn the user that 3 good examples are a minimum, without which there is a higher risk of deviation from expectations."
- **Accepted:** No; the Request and Design await the owner's approval.

### Request and Design approved

- **Summary:** The owner approved the Request and Design as they stood after Decision 0164 and its clarification. Status set to `in-progress`.
- **Owner decision:** 2026-11-17, "Approved. Start."
- **Accepted:** Yes.

### Slice 1: the checks an engineered tool must pass

- **Summary:** An engineered tool is recognised by `tools/<id>/contract.json` (the design's contract, written by `generate`; the loader checks its shape, `tool.bad_contract`), and each of its examples may carry `about.json` (`source`, `awkward`, `from`; `tool.bad_example`). An engineered tool whose entry file is not written yet loads with a warning (`tool.unbuilt`) and `vendor` refuses it (`vendor.tool_unbuilt`); a simple tool's missing entry file stays `file.missing`. `baton tools test` gains `--tool`, `--repeat` (each run compared with the expected result, the failing run named) and `--allow-unbuilt`. New `baton tools examples` (`example_check.py`): at least three examples, one awkward, each with `about.json`; an owner's files listed in `from` and byte-identical to the documents the run bound to `examples`; drafted and stated examples listed for the owner. The tool runner runs a tool in its own process group (a job object on Windows), writes its output to files, and fails the result naming any process left running, which it ends. `baton recipe check` gains the budget rules: reach as the contract declares, named packages pinned, 600 lines of code unless `size_reason`. Design choice made while building: the run-against-run comparison of `--repeat` is the comparison of every run with the expected result, since passing runs then agree with each other.
- **Modules:** `tools.py`, `recipe.py`, `project.py`, `tool_test.py`, `example_check.py` (new), `tool_runner.py`, `recipe_check.py`, `cli.py`.
- **Design docs:** `design/recipes.md` §5.3, §5.9; `design/director-interface.md` §13.1; `design/workers.md` (the `tool` adapter).
- **Tests:** `tests/test_engineered_tool_checks.py`: the contract and `about.json` (valid and malformed); an unbuilt tool loads with a warning, is refused at vendoring, and a simple tool is never unbuilt; the examples check (enough, awkward, drafted listed, owner copies proven against the binding, a changed or unlisted copy, a simple tool not checked unless named, the latest binding of the role); `tools test --tool`, `--repeat` with a tool that changes on its second run, `--allow-unbuilt`; a tool leaving a process running (POSIX); the budget rules and `recipe check` reporting them. The Windows job object is exercised only by the Windows CI.
- **Accepted:** Yes; the full suite was green on `46f9021`.

### Slice 2: the design carries contracts, and the examples are placed

- **Summary:** `recipe-builder@6` ships; version 5 is frozen as `tests/fixtures/recipes/recipe-builder-v5`. `software` is `[none, simple, engineered]`. A tool stage's `tool` gains `kind`; an engineered tool gives a `contract` and `examples_needed` (at least three, one awkward) instead of drafted examples. `generate` writes its `contract.json` and everything but the program and its examples, and its `tools test` gate passes `--allow-unbuilt`. The recipe declares the role `examples` (`many`, optional) and two steps at `engineered`: `example_plan` (a person's step: supplied and drafted counts, `warned` and the owner's words when any are drafted) and `examples` (copies the owner's files, drafts the rest, writes `about.json`; gated by `baton tools examples --run` and "Build the tools to these examples?"). The design's approval gate and the package review apply at `engineered`. `accept` depends on `examples`. The Director's skill and §13.3 gain "Examples for a tool the builder builds". Found while building: (1) the design schema cannot see the run's ratings, so "engineered only at the engineered rating" is the audit's check 28, as the simple ceiling already is; (2) `baton tools examples` reads the run's record directly (`Store`), as `guides check --artifact` does, so it runs in a gate without opening the project; (3) the generated manual topic comes from `recipe-sources/`, and a role description may not hold angle brackets.
- **Modules:** `cli.py` (`tools examples` reads the run's record). Recipe package: `recipe.yaml`, `schemas/profile_out.json`, `schemas/design_out.json`, `schemas/example_plan_out.json` (new), `schemas/examples_out.json` (new), `prompts/profile.md`, `prompts/design.md`, `prompts/generate.md`, `prompts/example_plan.md` (new), `prompts/examples.md` (new), `prompts/package_review_rubric.md`, `static/patterns.md`, `static/readiness.md`. Skill: `skills/baton-director/SKILL.md`.
- **Design docs:** `design/recipes.md` §5.7; `design/director-interface.md` §13.3.
- **Tests:** `tests/test_project_documents.py`: recipe-builder may declare a role. `tests/test_recipe_builder.py`: v6 loads and plans at every pair of ratings; the frozen v5; the example steps, the design approval and the package review at `engineered`; the role and the examples step's gates; the contract and `examples_needed` schema rules; the owner's choice to have examples drafted records the warning and their words; at least three placed examples, one awkward; the prompts, patterns and rubric. `tests/test_recipe_builder_runs.py`: an engineered run where the owner's files are attested and bound, a changed copy fails the check and the exact copy passes, before any code; an owner who supplies none, is warned, sends a drafted example back and approves the second draft. `tests/realkit.py`: the Director helper can do other person's steps.
- **Accepted:** Yes; the full suite was green on `f16b413`.

### Slice 3: the build loop

- **Summary:** `generate` lists `engineered_tools`, the source of a new group, `build_tools` (one instance per tool, one at a time, at most three iterations): `implement` (another vendor than `examples`, the examples protected with `on_violation: fail`) writes the tool to its examples and locks its named packages; its gates run `baton tools test --tool {{ item.tool }} --repeat 2 --require-examples` and `baton recipe check`; `review` (another vendor than `implement`) checks it against its contract with `static/tool_review_rubric.md`. At the limit the owner retries, simplifies (revise `generate`, then confirm `example_plan` and `examples` unchanged; the group re-expands without the tool) or abandons. `accept` takes each tool's result. A later run marks tools `base: unchanged | changed | new` and rebuilds only changed and new ones. Two engine changes, found while building, were needed for the approved shape: (1) a step in a group may be independent of a top-level step its group depends on (loader and routing), since `implement` must differ from `examples`; (2) a script gate in a `foreach` instance renders `item.*`, a text value only when it holds nothing a shell could read as syntax. Gap recorded: the capability vocabulary has no network capability, so `implement` requires `shell` and its prompt says to return `blocked` without the network; packages locked with hashes are checked by the loader and `recipe check`, but no test downloads a package.
- **Modules:** `intake.py` (`item` in gate commands), `recipe.py` (independence from a top-level ancestor of the group), `engine.py` (its routing source). Recipe package: `recipe.yaml`, `schemas/generate_out.json`, `schemas/implement_out.json` (new), `schemas/design_out.json` (`base`), `prompts/implement.md` (new), `prompts/tool_review.md` (new), `prompts/generate.md`, `prompts/design.md`, `prompts/accept.md`, `static/tool_review_rubric.md` (new). Skill: `skills/baton-director/SKILL.md` (the limit's three choices).
- **Design docs:** `design/recipes.md` §5.3, §5.7; `design/runtime.md` §8.4 (independence in a group); `design/gates-and-reviews.md` §9.1 (`item` in a script gate); `design/director-interface.md` §13.3.
- **Tests:** `tests/test_engineered_tool_engine.py`: independence from a top-level ancestor of the group, and from a step that is not one refused; `item` rendered in a gate command, unsafe text refused, undefined outside a group. `tests/test_recipe_builder.py`: the group's shape, gates, independence and protection, at `engineered` only; `accept`'s input; `engineered_tools`; the prompts and rubric. `tests/test_recipe_builder_runs.py`: two tools built one at a time to the owner's examples (one set supplied and a changed copy sent back, one drafted), each built by a vendor other than the examples' and reviewed by another than its builder, routing excluding the examples' worker, both vendored; a tool that special-cases the awkward example found by the review and fixed in a second round; a tool that does not pass in three rounds simplified at the owner's word, the group re-expanded without it.
- **Accepted:** Pending the full suite on this commit.
