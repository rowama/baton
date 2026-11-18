---
id: 2026-11-program-steps
title: "A recipe's tool is renamed a program, so \"tool\" means only what a model or a harness calls"
status: accepted
level: standard
decisions: ["0166", "0167", "0154", "0155", "0085"]
touches: [principles.md, design/recipes.md, design/layouts.md, design/workers.md, design/packets.md, design/runtime.md, design/director-interface.md, design/platform-and-security.md, design/adoption-and-framing.md]
manual: [user/what-baton-may-do.md, admin/files-and-paths.md, admin/recipes-and-vendoring.md, admin/scheduling-checks.md, recipes/recipe-builder.md, recipes/spreadsheet-reconcile.md, recipe-sources/recipe-builder.md, recipe-sources/spreadsheet-reconcile.md, reference/commands.md, context.yaml, reference-notes.yaml, anchors.yaml]
---

# A recipe's tool is renamed a program, so "tool" means only what a model or a harness calls

## Request

### Problem

Since `2026-11-tool-steps`, a **tool** in Baton is code a recipe ships that does a step with **no model** (§5.9). Everywhere else in Baton, and across agent software, a tool is something a model or a harness **calls**:

| Sense | Where |
|---|---|
| A model's tool calling | LiteLLM's `tools=` and `tool` messages, the `tool_use` capability (§5.6) |
| A harness's built-in tools | tooling capabilities, harness tool maps (Decision 0085), `tool_evidence` |
| MCP tools | `baton mcp`, and the delegate's interface ([2026-11-ai-delegates](2026-11-ai-delegates.md)) |
| A recipe's script that does a step with no model | §5.9: the odd one out |

The collision became concrete in [2026-11-step-tool-harness](2026-11-step-tool-harness.md), which offers tools to a model inside an API worker's attempt. One word would mean both "done with no model" and "called by a model". The owner-facing distinction between AI and non-AI work, which Decision [0155](../decisions/0155-recipe-builder-builds-software.md) relies on, would blur. Records would clash too: `dispatched.tool` is defined as present only on a §5.9 step.

The owner's decision (Decision [0166](../decisions/0166-tools-renamed-programs.md)): the §5.9 concept becomes a **program**, renamed outright with no alias, while Baton has no users.

### Acceptance criteria

1. **The recipe format uses the new names.** A step names its program with `program: <id>`. The package keeps it in `programs/<id>/` with `program.yaml`. An entry command names the program's folder as `{program}`. A waiting step's check is a program. The format stays `baton-recipe/1` (Decision [0167](../decisions/0167-program-steps-details.md) item 1).
2. **The old spelling fails plainly.** A step with `tool:`, or a package with a `tools/` folder holding `tool.yaml`, is a load error naming the new key or folder. It is not accepted as a synonym.
3. **Commands use the new names.** `baton programs setup`, `baton programs test` (with `--program <id>`) and `baton programs examples`, CLI only, as their predecessors were. `baton tools …` no longer exists.
4. **Records use the new names.** `dispatched.program`, `wait_started.program`, profile `program:<id>`, adapter, creator and vendor `program`, `effort_source: program default`, the vendor flag `program`, `programs_not_ready` from `start`, and error codes `program.*`. `step.tool_workspace_mismatch` becomes `step.program_workspace_mismatch`, and `tool_command_missing` becomes `program_command_missing`.
5. **Environments live under `~/.baton/programs/`.** Programs' environments are built there, as before, named by lock and Python.
6. **The shipped recipes use the new names.** `spreadsheet-reconcile`, `recipe-builder` (its schemas, prompts, patterns and rubric: `done_by: program`, the program budget, simple and engineered programs) and the test fixtures.
7. **The docs and the manual use the new names.** The principles glossary defines **Program** and no longer **Tool**, and the Step entry reads "done by one worker or one program per attempt". The design docs, the Director skill and every manual topic follow. The generated command reference is regenerated.
8. **The other senses keep "tool".** Tool calling, harness tools and tooling capabilities, tool maps, `tool_evidence`, MCP tools, the `tool_use` capability and the maintainers' `tools/` folder in the repository are unchanged.
9. **History is unchanged.** Decision records and finished change docs keep "tool" as written.
10. **Nothing else changes.** Every behaviour of tool steps, waiting steps and the builder's software settings is as before; the existing tests pass under the new names.

### Open questions

All five were answered as suggested (Decision [0167](../decisions/0167-program-steps-details.md)). The **[VERIFY]** of question 2 was checked first: a recipe's hash is compared only with a project's own lockfile, so an edit in place affects only a project that already vendored that version, and none has.

1. **Does the format version stay `baton-recipe/1`?** *Suggested:* yes, as a deliberate exception made before release, recorded with the answers to these questions. *Rationale:* renaming a key would normally mean a new format version; with nothing in use, a new version adds a migration with nothing to migrate.
2. **Are the shipped recipes edited in place, without new versions?** *Suggested:* yes: `recipe-builder` stays `@6` and `spreadsheet-reconcile` keeps its version. *Rationale:* no project has pinned them with tool steps, and `2026-11-ai-delegates` already plans `recipe-builder@7`. *Verified:* `vendor` and loading compare a recipe's hash only with the project's own lock entry (`vendor.version_exists`, `recipe.lock_mismatch`); nothing records a shipped recipe's hash across projects.
3. **Are the Python modules renamed too?** *Suggested:* yes: `tools.py`, `tool_env.py`, `tool_runner.py`, `tool_test.py` and `adapters/tool.py` become `programs.py`, `program_env.py`, `program_runner.py`, `program_test.py` and `adapters/program.py`, and the test files likewise; `tool_evidence.py` stays, as it is about harness tools. *Rationale:* code read beside the design should use the design's words.
4. **What happens to environments already built under `~/.baton/tools/`?** *Suggested:* nothing; they are no longer used, and `programs setup` builds new ones. The administrator topic on files says the old folder can be deleted. *Rationale:* Baton never deletes the owner's files unasked, and rebuilding is quick.
5. **How is completeness checked?** *Suggested:* the last slice's Log records a search for the old names (`tool:` step keys, `tools/<id>`, `tool.yaml`, `tool.*` codes, `tools setup|test|examples`, `dispatched.tool`) and lists each remaining hit with its kept sense. No permanent test. *Rationale:* a test would need an allowlist as long as the senses it protects, and would block legitimate uses of the word.

## Design

### Doc edits

- `principles.md` §2: **Program** replaces **Tool**; **Step** reads "done by one worker or one program per attempt".
- `design/recipes.md` §5.1 (the example), §5.3 (load rules, the old-spelling error), §5.6 (the note that tooling capabilities are a harness's, unchanged, now beside programs), §5.7 (`recipe-builder@6` in program terms), §5.9 retitled *Programs in a recipe*, and the waiting steps' check program.
- `design/layouts.md` §4.2 (`programs/<id>/` in a package), §4.4 (`~/.baton/programs/`).
- `design/workers.md` §6.3: the `program` adapter and runner.
- `design/packets.md` §7.1, §7.2: what a program is given and writes.
- `design/runtime.md` §8.1, §8.2, §8.4, §8.7, §8.8: the renamed records, profile, effort default and failure codes.
- `design/director-interface.md` §13.1 (`programs setup|test|examples`, `programs_not_ready`), §13.3 (the Director skill's words to the owner).
- `design/platform-and-security.md` §15.2: what a program may touch.
- `design/adoption-and-framing.md`: a part whose recipe brings a program the project has not approved.

### Manual edits

The owner topics already said "program"; only their anchors and the gate's question change. The other topics first listed here (`getting-started`, `when-something-is-wrong`, `director-commands`, `directors`, `install-and-versions`, `reference/diagnostics`) use "tool" only in its kept senses (MCP tools, `uv tool install`, `tool_evidence.*`) and are unchanged.

- `user/what-baton-may-do.md`: the section *Programs a process runs* `{#programs}`, the old anchor `#tools` kept as an alias.
- `admin/recipes-and-vendoring.md`: *Programs a recipe ships* `{#programs}` (alias `#tools`), `programs/<id>/program.yaml`, `baton programs setup|test|examples`, `--program <id>`, the program budget.
- `admin/files-and-paths.md`: `~/.baton/programs/`, and that a `~/.baton/tools/` folder left by an earlier Baton can be deleted (Decision 0167 item 4).
- `admin/scheduling-checks.md`: a check is a program; the example uses `program:`.
- `recipe-sources/recipe-builder.md` (and the generated `recipes/recipe-builder.md`): "Build the programs to these examples?", the section `{#engineered-programs}` with the alias `#engineered-tools`; the parts table follows the recipe's new titles.
- `recipe-sources/spreadsheet-reconcile.md` (and `recipes/spreadsheet-reconcile.md`): the link to `admin.recipes-and-vendoring#programs`.
- `reference/commands.md`: regenerated; `reference-notes.yaml` gains `command_anchor_aliases`, which the generator writes into the page's `anchor_aliases`, so `#baton-tools…` still resolve.
- `context.yaml`: the `programs` command opens `admin.recipes-and-vendoring`. `anchors.yaml` refreshed.

### Decisions

- [0166](../decisions/0166-tools-renamed-programs.md) (accepted): the rename, outright, keeping the other senses and history.
- [0154](../decisions/0154-tool-steps.md), [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): what is renamed; its meaning is unchanged.
- [0085](../decisions/0085-harness-tool-maps.md) (accepted): harness tools, which keep the word.
- [0167](../decisions/0167-program-steps-details.md) (accepted): the answers to the five open questions, all as suggested.

## Plan

Each slice leaves the repository passing its tests.

### Slice 1: the runtime, the format, the records, the shipped recipes and the manual

- **Outcome:** the loader, runtime, commands, records, error codes and environments use the new names, and the old spelling fails plainly; `spreadsheet-reconcile` and `recipe-builder` are written in program terms and behave exactly as before; the manual and the Director skill follow.
- **Criteria:**
  - `program:` and `programs/<id>/program.yaml` load; `tool:` and `tools/<id>/tool.yaml` are load errors naming the new spelling;
  - `baton programs setup|test|examples` in the CLI;
  - the renamed event keys, profile, adapter, creator, effort default, vendor flag, `programs_not_ready` and error codes;
  - environments under `~/.baton/programs/`;
  - the modules and tests renamed, and the test fixtures moved;
  - the packages use `program:` and `programs/`; the builder's schemas use `done_by: program`, and its prompts, patterns and rubric say program and program budget;
  - the manual topics and the Director skill, the reference regenerated;
  - every existing test passes under the new names.
- **Effort:** L

### Slice 2: the design docs and the completeness search

- **Outcome:** a maintainer reads "program" for §5.9 everywhere current in `docs/`, and "tool" only in its kept senses.
- **Criteria:**
  - the design and principles edits listed above;
  - the completeness search of open question 5 recorded in the Log;
  - `tests/test_docs.py` passes.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Change doc written from the owner's discussion of 2026-11-17 (Decision 0166). The current names were taken from the code and docs at `0e980ea`. No code changed.
- **Owner decision:** 2026-11-17, "Yes write the full change proposal program-steps."
- **Accepted:** No; proposal only. Five open questions await the owner.

### Open questions answered

- **Summary:** Checked the **[VERIFY]** of question 2 before asking: a recipe's hash is compared only with the project's own lockfile (`src/baton/project.py`, `vendor` and `Project.recipe`), so the shipped recipes can be edited in place. The owner accepted all five suggested answers. Recorded as Decision 0167; the Request and Design now cite it. The proposal drafted earlier (this doc, Decision 0166, and the edits to `2026-11-ai-delegates`, `2026-11-step-tool-harness`, `docs/README.md` and the register) is committed with it. No code changed.
- **Owner decision:** 2026-11-17, "Concur with commit and all question suggestions." (0167).
- **Accepted:** No; the Request and Design await the owner's approval.

### Accepted

- **Summary:** The owner approved the Request and Design as updated with Decision 0167's answers. No code changed.
- **Owner decision:** 2026-11-17, "Approve"
- **Accepted:** Yes.

### Slice 1: the runtime, the format, the records, the shipped recipes and the manual

- **Summary:** The §5.9 concept is a program throughout the code, the shipped recipes, the tests, the manual and the Director skill. Modules: `tools.py`, `tool_env.py`, `tool_runner.py`, `tool_test.py` and `adapters/tool.py` became `programs.py`, `program_env.py`, `program_runner.py`, `program_test.py` and `adapters/program.py` (Decision 0167 item 3), and their names inside them (`LoadedProgram`, `ProgramSpec`, `ProgramSetupError`, `PROGRAMS_DIR`, `PROGRAM_FILE`, ...). Format: a step's `program:`, `programs/<id>/program.yaml`, the entry placeholder `{program}`, still `baton-recipe/1` (item 1); `formats/baton-recipe-1.schema.json` regenerated. The old spelling fails plainly: a `tool:` key is `recipe.renamed_key` ("`tool:` is now `program:`") and a `tools/<id>/tool.yaml` is `recipe.renamed_folder`, naming the new path. Records: `dispatched.program`, `wait_started.program`, profile `program:<id>`, adapter, creator and vendor `program`, `effort_source: program default`, the vendor flag code `program`, the lock entry's `programs` map, `programs_not_ready` from `start`, `doctor`'s `programs`, and the codes `program.*`, `step.program_and_worker`, `step.program_workspace_mismatch`, `step.wait_needs_program`, `step.max_attempts_needs_program`, `vendor.program_unbuilt`, `configuration.not_a_program`, `programs.unknown_program`, `programs.examples_usage`. Commands: `baton programs setup|test|examples`, `programs test --program <id>`; the runner takes `--program-dir`. Environments: `~/.baton/programs/` (item 4: the old folder is left alone). Recipes: `spreadsheet-reconcile` and `recipe-builder@6` edited in place (item 2): `programs/csv_diff/`; the builder's step `build_programs`, its input `programs`, `engineered_programs`, `done_by: program`, `prompts/program_review.md`, `static/program_review_rubric.md`, the gate "Build the programs to these examples?", and its prompts, patterns and rubric in program terms. Plain-English uses ("a workflow tool", "name no AI model, vendor or tool") were kept. Fixtures: `tool-demo` is `program-demo`; the frozen `recipe-builder-v4` and `-v5` fixtures had only their `baton tools test` gate commands changed, since the command is gone. Manual: as listed under *Manual edits*; published anchors kept as aliases, and `manual_gen` writes `command_anchor_aliases` from `reference-notes.yaml` into the generated command reference. Skill: the vendor flag, `programs_not_ready` and the builder's examples section, in `skills/baton-director/SKILL.md` and its copy in `design/director-interface.md` §13.3 (a test keeps them equal). Kept senses unchanged: `tool_evidence`, harness tool maps and `ToolPlan`, tooling capabilities, `tool_use`, the MCP server's tools, the Codex approval setting, and the repository's `tools/` folder.
- **Plan change, told to the owner:** the former Slice 2 (the shipped recipes and the builder), the manual and the Director skill are folded into this slice. The builder's gates call `baton tools test`, the manual's tests check every command it names, and the skill names the runtime's records, so none of them can lag the rename without a broken commit. The design docs, the principles and the completeness search remain, as Slice 2.
- **Criterion 3 corrected:** the `programs` commands are CLI only, as `tools …` were (§13.1); the Request said "in the CLI and MCP".
- **Tests:** every existing test passes under the new names (test files `test_program_steps`, `test_program_runs`, `test_program_readiness`, `test_program_examples`, `test_engineered_program_checks`, `test_engineered_program_engine`); two new tests in `test_program_steps.py` show the old key and the old folder fail with the new names.
- **Accepted:** Yes.

### Slice 2: the design docs and the completeness search

- **Summary:** `principles.md` §2 defines **Program** (`programs/<id>/`), says it was called a tool until Decision 0166, and the Step entry reads "one worker or one program per attempt". `design/recipes.md`: §5.1's note on program steps, §5.3's load rules (`step.program_and_worker`, and the old spelling's `recipe.renamed_key` and `recipe.renamed_folder`, with `baton-recipe/1` kept as an exception, Decision 0167 item 1), §5.6's note that tooling capabilities are tools in the kept sense, §5.7's `recipe-builder` and `spreadsheet-reconcile` in program terms (`build_programs`, `engineered_programs`, `done_by: program`, the program budget), and §5.9 retitled *Programs in a recipe* (its `docs/README.md` § index row too). `design/layouts.md` §4.2 `programs/<id>/` and §4.4 `~/.baton/programs/`, with the note on the old folder (item 4). `design/workers.md` §6.3 the `program` adapter. `design/packets.md` §7.1 a program step's packet. `design/runtime.md` §8.1, §8.2, §8.4, §8.7, §8.8: the waiting state, `step_max_attempts`, `wait_started.program`, `dispatched.program`, `program:<id>`, `effort_source: program default`, a failed check. `design/director-interface.md` §13.1 `eligible` and `baton programs setup|test|examples` with `--program`, `programs_not_ready`, `program.not_ready`, `programs.unknown_program`. `design/platform-and-security.md` §15.2 and `design/adoption-and-framing.md` §11.6 likewise. Links to decision records keep their file names (`0156-tool-steps-details.md`, `0159-tool-runs-…`), and the decision list in `docs/README.md` keeps the records' titles as written (criterion 9). The frozen `recipe-builder-v4` and `-v5` fixtures' `generate` prompts now name `programs/<id>/program.yaml`, `{program}` and `program: <id>`, so a project pinned to them would still write packages that load; their design fields (`tool.does`) are unchanged, as their schemas are.
- **Completeness search (Decision 0167 item 5):** over every tracked file in `src`, `tests`, `examples`, `builtin`, `formats`, `manual`, `skills`, `docs` (less `docs/history/`, `docs/decisions/` and finished change docs), `ui`, `defaults`, `vocab`, `README.md`, `AGENTS.md`, `install.sh` and `pyproject.toml`, for `tool:` keys, `tools/<id>` and `tools/<name>/` paths, `tool.yaml`, `tool.<code>`, `tools setup|test|examples`, `dispatched.tool`, `tools_not_ready` and `{tool}`. Remaining hits, each kept:
  - this change doc and `tests/test_program_steps.py`'s two old-spelling tests, and the loader's own message for the old folder (`src/baton/recipe.py`): they name the old spelling on purpose;
  - `design/recipes.md` §5.3: the sentence that the old spelling is refused;
  - `docs/README.md`: Decision 0154's title, as written;
  - `pyproject.toml` `[tool.hatch…]`, `[tool.pytest…]`: Python packaging's own word;
  - `known_workers.py` (`tool: str`) and `tests/test_listings.py` (`verified: {tool: …}`): the research tool that verified a route;
  - `tests/test_harness.py` (`tool.write_text`, a command adapter's relay script) and `tests/test_manual_site.py` (`tool.build`, the maintainers' site builder): local variable names for other tools;
  - `recipe-builder/prompts/guide.md` and the v5 fixture's copy: "name no AI model, vendor or tool", plain English;
  - the v4 and v5 fixtures' `tool.does`: those versions' own design field.
  A wider search for the bare word in the design docs found only the kept senses (harness tools and tool maps, tooling capabilities, `tool_use`, MCP tools, `tool_evidence`, `uv tool install`, the repository's `tools/` folder) and decision-record file names.
- **Tests:** `tests/test_docs.py` (every § reference and link resolves; the register matches); the quick gate.
- **Accepted:** Yes.
