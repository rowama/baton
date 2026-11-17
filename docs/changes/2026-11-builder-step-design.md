---
id: 2026-11-builder-step-design
title: "Recipe builder designs each step for the simplest means that can do it, and uses an AI worker only where software or a rule cannot"
status: accepted
level: major
decisions: ["0155", "0154", "0156", "0158", "0144", "0147", "0145", "0161", "0162", "0159"]
touches: [design/recipes.md, design/director-interface.md]
manual: [recipe-sources/recipe-builder.md, recipes/recipe-builder.md, admin/recipes-and-vendoring.md, reference/commands.md, anchors.yaml, user/what-baton-may-do.md]
---

# Recipe builder designs each step for the simplest means that can do it, and uses an AI worker only where software or a rule cannot

## Request

### Problem

`recipe-builder@3` records one thing about who does a stage: `person`, `ai` or `automatic_check`. Nothing asks why a stage is given to an AI worker, nothing says how to split a process into stages, and the readiness rubric has no check on either. So the builder reaches for an AI worker by default, including for work a few lines of code would do the same way every time at no cost per run.

Baton can now run a script a recipe ships (Decision [0154](../decisions/0154-tool-steps.md), `2026-11-tool-steps`). The owner's direction (Decision [0155](../decisions/0155-recipe-builder-builds-software.md)): the builder is a process engineer first. It prefers software to an AI worker where software can do the step, tells the owner plainly what they give up and what it costs when they choose otherwise, and builds software only up to a ceiling the owner sets.

This change covers the design of steps and the building of simple scripts. Engineered tools (tests written first from the owner's examples, a bounded build loop) are the next change.

### Acceptance criteria

1. **A new version.** `recipe-builder@4` ships. Projects with `@3` pinned keep it.
2. **One kind of work per stage.** The design splits the process until each stage has one kind of work, one doer and one output that can be checked. A stage that both interprets open-ended material and applies rules is split into two: interpret, then enforce.
3. **Every stage says what its work is like.** The design records six traits for each stage, with a one-line basis:
   - whether complete rules can be written for every input in scope (`complete`, `partial`, `none`);
   - the form of its input (`structured`, `open`);
   - whether the same input must give the same result (`required`, `not_required`);
   - its effect (`none`, `reversible`, `irreversible`: it spends money, changes something others depend on, or cannot be undone);
   - whether a correct result can still be wrong about the world (`certain`, `uncertain`: a forecast, a reading of a scan);
   - how its output can be checked (`mechanical`, `source`, `judgment`).
4. **The doer follows from the traits.** A stage is done by a `tool`, an `ai` worker, a `person` or an `automatic_check`. The patterns file gives the rule: the simplest means that can do the work, software before an AI worker.
5. **Choosing an AI worker over software is recorded.** An `ai` stage whose rules are complete and whose input is structured carries a record: what could have done it, why it was not used (the owner's ceiling, the owner's choice, or the work is over the tool budget), what is given up (the same result every time, no cost per run, no dependence on a harness) and what the software would have cost (building it, and the attention software needs). An owner's choice is a confirmed ledger entry with their words.
6. **A check says what it establishes.** Each stage's acceptance check names its kind: `format`, `rule`, `source` or `judgment`. A stage with an effect, or with an uncertain result, has a check that establishes more than format.
7. **The audit enforces it.** The readiness rubric gains checks for criteria 2 to 6, the tool budget and the delegation marks, at high severity, so the audit sends back a design that fails them.
8. **The owner sets how much software the builder may write.** The builder rates two things at `profile`, each with a reason: `approach` (`simple`, `standard`, `complex`: today's levels, unchanged in what they add) and `software` (`none`, `simple`). `simple` and `none` together apply at once, as a `simple` build does today. Any other ratings wait on the owner.
9. **A ceiling of `none` is not silent.** When the design finds a stage software could do and the ceiling is `none`, it does the stage another way, records why, and sends one rating signal on `software` (§5.5), so the owner can raise the ceiling or keep it.
10. **At `software: simple` the builder writes the script.** For each `tool` stage, `generate` writes `tools/<id>/` (the script, `tool.yaml`, the lock, the examples) and a step that names the tool. A simple tool is one file, uses only the standard library, reaches no network and needs no secrets.
11. **A tool ships its worked examples and passes them.** A tool's examples (an input and the expected result) live in the tool's folder. A new command, `baton tools test <package>`, runs every tool on every example in the tool's environment and fails with a plain report on any difference. It is a gate on `generate`.
12. **The owner sees software before it is built, and it is reviewed after.** When `software` is above `none`, the owner approves the design, which shows each tool's purpose and examples in plain words, and an independent reviewer checks the finished package: the script does what the design says and touches only what it declares.
13. **The walkthrough says who does each step.** It lists each tool with what it does, what it needs installed and what it may touch, and lists every step an AI worker does that software could do, with both sides of the trade.
14. **The quick path has a place.** The `approach` scale is where `2026-11-quick-runs` adds `quick`. Nothing quick ships in this change.
15. **A person's stage says whether delegating it is risky.** For each stage a person does and each decision the owner makes, the design records whether handing it to the owner's AI delegate is risky, with the reason in plain words. It is risky when the stage's effect is `irreversible`, or when the owner accepts a risk or waives a check there. The design document and the walkthrough show these marks. They enter the recipe itself when Baton can act on them ([2026-11-ai-delegates](2026-11-ai-delegates.md), on hold; Decision [0161](../decisions/0161-ai-delegates.md)).
16. **Manual and design are current.** §5.7 describes `recipe-builder@4`; §5.9 describes tool examples; the manual's recipe-builder topic and command reference are updated.

### Open questions

The owner accepted every suggested answer on 2026-11-16 (Decision [0162](../decisions/0162-builder-step-design-details.md)).

1. **Are these the right six traits?** *Suggested:* yes, as listed in criterion 3. *Rationale:* each one changes either who does the stage or what its check must establish; a trait that changed neither was left out.
2. **What about existing software as a doer?** *Suggested:* not yet. Until the external-software change, a stage existing software could do is a discovery record and is done another way. *Rationale:* Baton cannot yet check that a product is installed or bind an instance.
3. **How is the builder rated?** *Suggested:* two axes, `approach: [simple, standard, complex]` and `software: [none, simple]`. `2026-11-quick-runs` adds `quick` below `simple` with `confirm_lowest`, and the profile schema then requires `software: none` with `quick`. The tool-building change adds `engineered` above `simple`. *Rationale:* one conversion from levels to axes serves all three changes, and it answers quick-runs question 1 as suggested there. A rule on `quick` is needed because `applies_to` joins axes with OR (§5.5).
4. **What may a `simple` tool use?** *Suggested:* the Python standard library only, no network, no secrets, one file. Packages come with `engineered`. *Rationale:* it keeps the two settings visibly different, needs no download at build time, and CSV, JSON, dates, arithmetic and SQLite are all in the standard library.
5. **Where do tool examples live, and does `baton tools test` belong here?** *Suggested:* `tools/<id>/examples/<name>/input.json` and `expected.json`, plus `expected/<artifact>` for any artifact to compare byte for byte; built in this change as its first slice. *Rationale:* examples that ship with a tool also let `doctor` re-check it on another machine. The alternative is an addendum to `2026-11-tool-steps`.
6. **When the ceiling is `none`, how hard does the builder push?** *Suggested:* one rating signal per run, however many stages software could do, and the list in the walkthrough. *Rationale:* the owner is told once at the moment it matters and can see the detail later; repeated prompts would be nagging.
7. **What does `profile` recommend for `software`?** *Suggested:* `simple` whenever the idea shows rule-like work (calculating, converting, matching, recording), otherwise `none`; the owner approves either way. *Rationale:* it carries the preference of Decision 0155 into the first question the owner sees.
8. **Does this apply to a process meant to run elsewhere?** *Suggested:* traits and the recommended doer are recorded for every stage; tools are built only for stages Baton runs. *Rationale:* the analysis is useful to whoever implements the process elsewhere, and Baton builds only what it can run and check.
9. **Must a `simple` tool's examples come from the owner?** *Suggested:* the builder drafts them from what the owner said, and the owner approves them with the design (criterion 12). Examples the owner supplies as files are required only for `engineered` tools (Decision 0155, item 5). *Rationale:* a simple tool's behaviour fits in an example the owner can read and judge.
10. **How does an example supply file inputs?** A tool's inputs file names any non-JSON input by path (Decision [0159](../decisions/0159-tool-runs-env-inputs-build-outputs.md)), and the shipped `csv_diff` tool takes two CSV files. *Suggested:* JSON inputs stay in `input.json`; each file input sits beside it as `examples/<name>/inputs/<input name>.<ext>`, and `baton tools test` builds the inputs file from both exactly as dispatch does. *Rationale:* an example then exercises the same path as a run.

### Out of scope

- **Engineered tools:** tests written first by a different worker and protected, a bounded build loop per tool, third-party packages. The next change.
- **The quick path** (`quick`, guides, the `quick-run` recipe): `2026-11-quick-runs`.
- **External software and waiting steps:** their own changes.
- **A form for a person's step:** [2026-11-person-step-forms](2026-11-person-step-forms.md), on hold.
- **How the recipes the builder writes are rated.** They keep levels or axes as the design calls for; nothing changes there.

## Design

Approved by the owner with the Request on 2026-11-16.

### Shape

- **Ratings.** `recipe.yaml` replaces `complexity.levels` with:
  ```yaml
  complexity:
    axes:
      approach: { scale: [simple, standard, complex] }
      software: { scale: [none, simple] }
    triage_step: profile
  ```
  `applies_to` becomes: `research` `{approach: [standard, complex]}`; the audit's owner gate `{approach: [standard, complex], software: [simple]}`; the package review gate `{approach: [complex], software: [simple]}`. The profile schema's rule that a design-shaping choice makes the work at least `standard` is kept on `approach`.
- **A stage in `design_out.json`** gains:
  ```json
  {
    "done_by": "tool",
    "traits": { "rules": "complete", "input": "structured", "repeatable": "required",
                "effect": "reversible", "result": "certain", "check": "mechanical",
                "basis": "Totals are sums of the listed amounts; the same list must always give the same total." },
    "acceptance": { "kind": "rule", "what": "The total equals the sum of the lines." },
    "tool": { "id": "total-lines", "does": "Adds up the amounts on each list.",
              "input": "...", "output": "...", "reach": { "workspace": "none" },
              "examples": [ { "name": "two-lines", "input": {}, "expected": {} } ] }
  }
  ```
  The schema requires `traits` and `acceptance` on every stage; `tool` with at least one example when `done_by` is `tool`; and `executor_choice {could_be, reason, gives_up, would_cost, ledger_id?}` when `done_by` is `ai`, `rules` is `complete` and `input` is `structured`. `reason` is `ceiling`, `owner_choice` (then `ledger_id` is required) or `over_budget`.
- **`static/patterns.md`** gains three shapes: *one kind of work per stage* (the splitting rule and where to stop: when a further split would change neither the doer nor the check); *interpret, then enforce* (an AI worker or a person turns open-ended material into a structured proposal; software or a check validates it and acts); and *the simplest means that can do the work* (the rule from traits to doer, the tool budget, and that an irreversible effect has the owner's decision before it whoever does the stage).
- **`static/readiness.md`** gains checks 21 to 26, all high: one kind of work per stage; traits given with a basis and the doer following from them; an `ai` stage software could do has its record; a stage that must repeat is not done by an AI worker unless the owner chose so; a check says what it establishes and is more than format where there is an effect or an uncertain result; a tool is within its budget, declares what it touches and has an example.
- **Delegation mark.** A stage with `done_by: person` or an `owner_decision` carries `delegation {risky, reason}`; the schema requires it, and requires `risky: true` when `traits.effect` is `irreversible`. Rubric check 27 (high): a risky stage is marked, with a reason the owner would understand.
- **`prompts/profile.md`** asks, in plain words, whether the process may include small programs written for it, saying what they give and need, and returns `ratings`.
- **`prompts/generate.md`** writes each tool and its step, runs `baton tools test` itself, and adds the two walkthrough lists. `generate` gets the gate `{ type: script, run: "baton tools test recipes/drafts/{{ run.slug }}" }`.
- **`prompts/package_review_rubric.md`** gains the checks on a script: it does what the design says, uses only the standard library, and touches only what it declares.
- **`baton tools test <package>`** builds each tool's environment if needed (as `tools setup` does), runs the tool on each example through the tool runner in a scratch folder (Decision 0158), and builds the inputs file from the example's `input.json` and `inputs/<name>.<ext>` files as dispatch does (Decision 0159), and compares `output.json` to `expected.json` as JSON and each `expected/<artifact>` byte for byte. Exit 0 when all pass; otherwise it names the tool, the example and the first difference. A tool with no example is a failure under `--require-examples`, which the builder's gate passes. The loader treats `examples/` as part of the tool's files, so it is hashed with the recipe.

### Doc edits

- `design/recipes.md` §5.7: `recipe-builder@4` (the two ratings, the traits, the doer rule, the tool budget, what `generate` writes). §5.9: tool examples.
- `design/director-interface.md` §13.1: `tools test`.

### Manual edits

- `reference/commands.md` (generated), `anchors.yaml`, `admin/recipes-and-vendoring.md`: `baton tools test`, tool examples and keeping git from converting them (Slice 1).
- `recipe-sources/recipe-builder.md` (and the generated `recipes/recipe-builder.md`): the two ratings, who does each step, the walkthrough lists, the delegation marks (Slices 2 to 4).
- `user/what-baton-may-do.md`: small programs the builder may write for a process, and the ceiling the owner sets (Slice 4).

### Decisions

- [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): one recipe, the owner's ceiling, software preferred, the tool budget, the planned changes.
- [0154](../decisions/0154-tool-steps.md), [0156](../decisions/0156-tool-steps-details.md), [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md) (accepted): what a tool is and how it runs.
- [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md) (accepted): axes, OR across them, rating signals.
- [0145](../decisions/0145-quick-runs-through-recipe-builder.md) (accepted): the quick path this change leaves room for.
- [0161](../decisions/0161-ai-delegates.md) (accepted): a recipe's author marks the stages that are risky to delegate.
- [0162](../decisions/0162-builder-step-design-details.md) (accepted): the answers to the ten open questions.
- [0159](../decisions/0159-tool-runs-env-inputs-build-outputs.md) (accepted): the inputs file an example's inputs are built into.

## Plan

Approved 2026-11-16. `2026-11-tool-steps` is done.

### Slice 1: tools ship examples and can be tested

- **Outcome:** `baton tools test <package>` runs each tool on its examples and reports any difference.
- **Criteria:** `examples/` loaded and hashed with the tool; file inputs from `inputs/`; JSON and artifact comparison; plain report naming tool, example and first difference; `--require-examples`; exit codes; `spreadsheet-reconcile`'s `csv_diff` has an example that passes.
- **Effort:** M

### Slice 2: recipe-builder@4 is rated on two axes

- **Outcome:** `@4` behaves as `@3` at every `approach`, with `software` rated and recorded and nothing yet depending on it.
- **Criteria:** the axes and the `applies_to` mapping; `simple` with `none` applied at once; any other ratings wait on the owner; the `@3` scenario tests pass against `@4`; `@3` pinned runs keep `@3`.
- **Effort:** S

### Slice 3: the design characterizes every stage

- **Outcome:** a design records traits, the kind of each check and the reason for every AI worker that software could replace, and the audit blocks a design that does not.
- **Criteria:** the schema rules; the three pattern shapes; rubric checks 21 to 26; the rating signal at a ceiling of `none`; scenario tests for a stage that must be split, an AI stage with no record, and a format-only check on a stage with an effect.
- **Effort:** M

### Slice 4: the builder writes simple tools

- **Outcome:** a described process with rule-like work yields a recipe whose tool step passes its examples, approved by the owner and independently reviewed.
- **Criteria:** `generate` writes the tool, its step and examples; the `tools test` gate; the owner gate and the review gate at `software: simple`; the walkthrough lists; a scenario from description to accepted package with one tool; the same scenario at a ceiling of `none` yields an AI stage, its record and one signal; the manual.
- **Effort:** L

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0155 and the owner's discussion of 2026-11-15, with the rating that `2026-11-quick-runs` needs folded into the same conversion. No code changed.
- **Owner decision:** 2026-11-16, "Draft 3 with quick-runs rating folded in."
- **Accepted:** No; proposal only. Nine open questions await the owner.

### Delegation marks added

- **Summary:** Added criterion 15 (a person's stage says whether delegating it is risky), its schema field and rubric check 27, from Decision 0161. Later criteria renumbered. No code changed.
- **Owner decision:** 2026-11-16, "I want to address it before we're done with recipe-builder." (0161).
- **Accepted:** No; proposal only. Nine open questions await the owner.

### Accepted

- **Summary:** The owner accepted all ten suggested answers (nine from the proposal, a tenth on file inputs to examples raised against Decision 0159) and approved the Request and Design, delegation marks included. Recorded as Decision 0162; manual files listed. No code changed.
- **Owner decision:** 2026-11-16, "Accept all." (0162).
- **Accepted:** Yes.

### Slice 1: tools ship examples and can be tested

- **Summary:** A tool's worked examples live in `tools/<id>/examples/<name>/` (`input.json`, `inputs/<input>.<ext>`, `expected.json`, `expected/<artifact>.<ext>`, and `workspace/` for a tool that reaches one). The loader checks them (`tool.bad_example`) and hashes them with the recipe. `baton tools test <package> [--require-examples]` runs each example as a dispatch would: the tool's environment, `engine.tool_profile`'s constructed environment variables, and `baton.tool_runner` on a packet built from the example, declaring only the expected artifacts. It names the tool, the example and the first difference (JSON path, or line), and exits 0 only when all pass. `spreadsheet-reconcile`'s `csv_diff` ships the example `price-change`, which passes.
- **Found on the way:** the repository's `* text=auto eol=lf` would have converted the CRLF endings `csv` writes in expected artifacts and broken the byte comparison on checkout. `.gitattributes` now has `**/tools/*/examples/** -text`; projects' vendored recipes were already covered by `.baton/.gitattributes`. Drafts the builder writes outside `.baton/` are tested on the machine that wrote them (Slice 4).
- **Modules:** `tools.py` (`Example`, `load_examples`), `recipe.py` (examples loaded with the tool), new `tool_test.py`, `cli.py` (`tools test`).
- **Design docs:** §5.9 (tool examples, `tools test`), §13.1 (`tools test`).
- **Manual:** `admin/recipes-and-vendoring.md`; `reference/commands.md` regenerated; `anchors.yaml` (`baton-tools-test`).
- **Tests:** `tests/test_tool_examples.py`: the shipped example loads with file inputs and an artifact; examples change the tool's and the recipe's hash; nine malformed examples refused where they are; JSON and byte differences in plain words; `tools test` passes the shipped tool, fails a changed artifact or output naming the difference, fails a failing tool and an undeclared file, fails a tool with no examples only under `--require-examples`, and refuses a package that does not load.

### Slice 2: recipe-builder@4 is rated on two axes

- **Summary:** `recipe-builder` is version 4. `complexity.levels` became `axes: {approach: [simple, standard, complex], software: [none, simple]}`; `research` applies at `approach: [standard, complex]`, the audit's owner gate at `{approach: [standard, complex], software: [simple]}` and the package review at `{approach: [complex], software: [simple]}`. `profile` returns `ratings` (each axis a value and a reason in the owner's terms) instead of `level`, recommends `software: simple` for rule-like work (Decision 0162, item 7), and the profile schema keeps a shaping choice at `approach` `standard` or above. At `software: none` every approach plans exactly as version 3's level of the same name. Version 3 is frozen as `tests/fixtures/recipes/recipe-builder-v3`, as version 2 was.
- **Modules:** none (recipe package only): `examples/recipes/recipe-builder/recipe.yaml`, `schemas/profile_out.json`, `prompts/profile.md`.
- **Design docs:** §5.7 (version 4, the ratings table, the two axes).
- **Manual:** `recipe-sources/recipe-builder.md` (what the owner is asked: the two ratings), `recipes/recipe-builder.md` regenerated.
- **Tests:** `tests/test_recipe_builder.py`: v4's axes and plans at every pair of ratings; each approach with no software plans as v3's level; software adds the design approval and the package review at every approach and no research; `simple`+`none` applies at once and every other pair waits; the profile schema needs both axes with reasons and keeps a shaping choice out of a simple approach; the frozen v3 loads with its levels. `tests/test_recipe_builder_runs.py`: the v3 scenarios run against v4 with ratings; a pinned v3 still runs on its one scale; `software: simple` at a simple approach asks for the ratings and the design and runs the package review. `tests/test_fit_check_scope.py` now checks the builder is at least version 3 (version 2's guidance carries forward).
- **Repair (full suite red on bda7186):** `test_framing_records_and_renders_as_before[baton-frame@1]` failed: `recipe-builder@4` is the first catalog recipe with axes, and framing's recipe listing then carried `axes`, which the frozen `baton-frame@1` run-input schema refuses. `frame.recipe_listing(with_axes=False)` leaves them out for a `@1` run; `@2` and `catalog.summaries` keep them (`src/baton/frame.py`; §5.2 and §11.6 say so).
