---
id: 2026-11-program-steps
title: "A recipe's tool is renamed a program, so \"tool\" means only what a model or a harness calls"
status: proposed
level: standard
decisions: ["0166", "0167", "0154", "0155", "0085"]
touches: [principles.md, design/recipes.md, design/layouts.md, design/workers.md, design/packets.md, design/runtime.md, design/director-interface.md, design/platform-and-security.md, design/adoption-and-framing.md]
manual: [user/getting-started.md, user/what-baton-may-do.md, user/when-something-is-wrong.md, admin/director-commands.md, admin/directors.md, admin/files-and-paths.md, admin/install-and-versions.md, admin/recipes-and-vendoring.md, admin/scheduling-checks.md, recipes/recipe-builder.md, recipes/spreadsheet-reconcile.md, recipe-sources/recipe-builder.md, recipe-sources/spreadsheet-reconcile.md, reference/commands.md, reference/diagnostics.md]
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

1. **The recipe format uses the new names.** A step names its program with `program: <id>`. The package keeps it in `programs/<id>/` with `program.yaml`. A waiting step's check is a program. The format stays `baton-recipe/1` (Decision [0167](../decisions/0167-program-steps-details.md) item 1).
2. **The old spelling fails plainly.** A step with `tool:`, or a package with a `tools/` folder holding `tool.yaml`, is a load error naming the new key or folder. It is not accepted as a synonym.
3. **Commands use the new names.** `baton programs setup`, `baton programs test` and `baton programs examples`, in the CLI and MCP. `baton tools …` no longer exists.
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

- `user/getting-started.md`, `user/what-baton-may-do.md`, `user/when-something-is-wrong.md`: "program" where an owner reads "tool" today.
- `admin/director-commands.md`, `admin/directors.md`, `admin/files-and-paths.md` (with the note on the old folder), `admin/install-and-versions.md`, `admin/recipes-and-vendoring.md`, `admin/scheduling-checks.md`: the commands, folders and words.
- `recipes/recipe-builder.md`, `recipes/spreadsheet-reconcile.md` and their `recipe-sources/` files: the shipped recipes in program terms.
- `reference/commands.md`, `reference/diagnostics.md`: regenerated.

### Decisions

- [0166](../decisions/0166-tools-renamed-programs.md) (accepted): the rename, outright, keeping the other senses and history.
- [0154](../decisions/0154-tool-steps.md), [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): what is renamed; its meaning is unchanged.
- [0085](../decisions/0085-harness-tool-maps.md) (accepted): harness tools, which keep the word.
- [0167](../decisions/0167-program-steps-details.md) (accepted): the answers to the five open questions, all as suggested.

## Plan

Each slice leaves the repository passing its tests.

### Slice 1: the runtime, the format and the records

- **Outcome:** the loader, runtime, commands, records, error codes and environments use the new names, and the old spelling fails plainly.
- **Criteria:**
  - `program:` and `programs/<id>/program.yaml` load; `tool:` and `tools/<id>/tool.yaml` are load errors naming the new spelling;
  - `baton programs setup|test|examples` in the CLI and MCP;
  - the renamed event keys, profile, adapter, creator, effort default, vendor flag, `programs_not_ready` and error codes;
  - environments under `~/.baton/programs/`;
  - the modules and tests renamed (if open question 3 is accepted), and the test fixtures moved;
  - every existing test passes under the new names.
- **Effort:** M

### Slice 2: the shipped recipes and the builder

- **Outcome:** `spreadsheet-reconcile` and `recipe-builder` are written in program terms and behave exactly as before.
- **Criteria:**
  - the packages use `program:` and `programs/`;
  - the builder's schemas use `done_by: program`, and its prompts, patterns and rubric say program and program budget;
  - their scenario tests pass;
  - `baton recipe check` passes on both.
- **Effort:** M

### Slice 3: the docs, the skill and the manual

- **Outcome:** an owner, an administrator and a maintainer read "program" for §5.9 everywhere current, and "tool" only in its kept senses.
- **Criteria:**
  - the design and principles edits listed above;
  - the Director skill;
  - the manual topics listed above, the reference regenerated;
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
