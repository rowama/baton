---
id: 2026-11-tool-steps
title: "A step can be run by a script the recipe ships, with pinned dependencies and a record of what ran"
status: in-progress
level: major
decisions: ["0154", "0156", "0158", "0159", "0160", "0085"]
touches: [principles.md, design/recipes.md, design/layouts.md, design/workers.md, design/packets.md, design/runtime.md, design/platform-and-security.md, design/director-interface.md, design/adoption-and-framing.md]
manual: [admin/recipes-and-vendoring.md, admin/files-and-paths.md, user/what-baton-may-do.md, reference/commands.md, context.yaml, anchors.yaml, recipe-sources/spreadsheet-reconcile.md, recipes/spreadsheet-reconcile.md]
---

# A step can be run by a script the recipe ships, with pinned dependencies and a record of what ran

## Request

### Problem

A recipe can only say what kind of AI worker or person a step needs (`requires`). Work that plain code does better (a calculation, a backtest, a file conversion, a reconciliation) has two homes today, and neither fits:

- **A script gate** (§9.1) runs a command, but a gate judges a step's result. It produces no output that another step takes as an input.
- **A `command` worker profile** (§6.3) runs any command line as a worker. But:
  - it is machine-local and hand-written (`~/.baton/workers.yaml`), so a recipe cannot ship it;
  - it is routed by capabilities and tier, so it must claim AI abilities to be chosen, and the Director may pick another worker;
  - the command must speak the packet protocol itself, and its instructions are prose written for a model;
  - nothing states what it needs installed, and no run records which version ran.

So a recipe author who wants a step done by code gives it to an AI worker with `shell`, which costs a model call, varies between runs and ties the step to a harness. The owner's direction (Decision [0154](../decisions/0154-tool-steps.md)): a tool is a third kind of executor, visible to the recipe designer at the same level as AI capabilities, separable from any harness, and more locked down than an AI worker.

This is the first of three changes. It covers scripts a recipe ships. External software and waiting steps come later (see *Out of scope*).

### Acceptance criteria

1. **A step names its tool.** A step has `tool: <id>` instead of `requires` and `prompt`. The tool lives in the recipe package (`tools/<id>/`), so it is vendored, hashed and pinned with the recipe. Having both `tool` and `requires` or `prompt` is a load error.
2. **A tool declares what it is.** `tools/<id>/tool.yaml` gives the entry command (a list of words; no shell runs it), the runtime it needs, a lock file of exact dependency versions with hashes, and what it may touch (workspace mode, network, named secrets).
3. **No routing.** `eligible` returns the tool as the step's one executor, or says why it is not ready. The Director still dispatches the step and cannot substitute another executor.
4. **The tool author never sees the packet protocol.** Baton's runner gives the tool one JSON file of the step's inputs and an output directory. The tool writes `output.json` and any artifacts. The runner checks them, writes `result.json` and echoes the packet hash. Input values never appear on a command line.
5. **Dependencies are resolved before use.** Baton builds an isolated environment for the tool from its lock file, on the machine, reused while the lock is unchanged. A missing runtime or a failed build is a platform failure with a plain reason, not the step's failure.
6. **Not ready is said early.** `check`, `doctor` and `start` report each tool of the recipe that is not ready on this machine and why. Dispatch refuses a tool that is not ready.
7. **Every run records what ran.** `dispatched` records the tool's id and hash, the lock file's hash, the runtime's exact version and the environment's id. The step record shows them.
8. **A tool gets only what it declares.** Its environment is clean: no secrets except those it names, resolved from machine-level configuration. Its workspace mode is enforced as for any worker (§6.3). Network reach is declared and shown to the owner; it is enforced only where the machine isolates the tool (Decision 0156, item 3).
9. **Gates and inputs work as for any step.** A tool step's output and artifacts feed later steps, and its gates (schema, script, review, human) run unchanged. A reviewer of a tool step is always independent of it.
10. **The owner approves tools with the recipe.** Vendoring a recipe that has tools lists each one in the owner's terms: what it does, what it needs installed and what it may touch. `baton recipe check` rejects a tool with no lock file, an unpinned dependency, or a declared file that is missing.
11. **Nothing changes for recipes without tools.** Their packets, hashes and events are byte for byte as before.

### Open questions

None open. The eight questions this change raised were answered by the owner on 2026-11-15 as suggested, and are recorded in Decision [0156](../decisions/0156-tool-steps-details.md):

1. Environments are built with `uv` from a requirements file with exact versions and hashes (verified against uv 0.13.7: `uv pip compile --generate-hashes`, `uv venv --python`, `uv pip install --require-hashes`).
2. Python only in the first version; `tool.yaml` names the runtime kind.
3. Network reach is declared, shown at vendoring and recorded; it is enforced only under `isolation: container`, and the manual says so.
4. One attempt by default; a failure escalates with the tool's error output; a recipe may raise the limit.
5. `start` warns about a tool that is not ready; dispatch refuses.
6. Environments live in `~/.baton/tools/<lock hash>/`.
7. The recipe format stays `baton-recipe/1`.
8. Tool steps use the effort bands, defaulting to `S`.

Checking the Design before approval confirmed item 1 against uv 0.13.7 and raised two more questions, answered by the owner on 2026-11-16 as suggested and recorded in Decision [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md): uv never downloads a Python (a missing one makes the tool not ready), and a tool runs in a fresh scratch folder, reaching its own files through `{tool}`.

### Out of scope

- **External software and specified interfaces** (Decision 0154, forms 2 and 3): the second change.
- **Waiting steps and the scheduler helper:** the third change.
- **`recipe-builder` choosing between a tool, an AI worker and a person,** and writing and testing tools: its own change, after this one.
- **Tools offered to a model inside a worker** ([2026-11-step-tool-harness](2026-11-step-tool-harness.md), on hold). That change gives an AI worker tools to call; this one runs a tool with no model. The two may later share tool definitions.
- **A catalog of tools shared between recipes.** A tool lives in its recipe for now.
- **The `command` adapter** stays as it is, for relaying to other agents and for machine-local tools.

## Design

Approved by the owner with the Request on 2026-11-16.

### Shape

- **Recipe.**
  ```yaml
  - id: backtest
    title: Test the strategy against past prices
    depends_on: [parameters]
    tool: backtest                       # tools/backtest/ in this package
    workspace: none
    inputs:
      - { name: parameters, from: steps.parameters.output, required: true }
    output_schema: schemas/backtest_out.json
    artifacts:
      - { name: trades, required: true, media_type: text/csv }
    gates: [ { type: schema } ]
  ```
- **Tool.**
  ```
  <recipe>/tools/backtest/
  ├── tool.yaml
  ├── requirements.lock        # exact versions with hashes
  └── backtest.py
  ```
  ```yaml
  id: backtest
  description: Runs a strategy over a price history and reports its trades and returns.
  runtime: { kind: python, version: ">=3.11" }
  entry: ["python", "{tool}/backtest.py", "--input", "{input}", "--output", "{output}"]
  dependencies: { lock: requirements.lock }
  reach: { network: false, secrets: [] }
  ```
  `{input}`, `{output}`, `{tool}` (the tool's folder) and `{workspace}` are the only placeholders. `entry[0]` resolves inside the tool's environment.
- **Runner.** A new adapter, `tool`, runs `python -m baton.tool_runner` as the child, as `litellm_api` runs `worker_runner` (§6.3). The runner writes the inputs file from the packet, starts the entry command in the tool's environment, in a fresh, empty scratch folder as its working directory (Decision [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md), item 2), and turns `output.json` and the artifacts into `result.json`. Exit 0 with a valid output is `completed`; anything else is `failed` with the last lines of the tool's error output in `notes`. A tool cannot return `blocked` or questions.
- **Supervision.** Unchanged: the per-dispatch supervisor, running marker, deadline, intake, hooks and checkpoint (§8.7). A tool step is async like any other.
- **Identity.** A tool's result is recorded with creator `tool` and identity `tool/<recipe>/<id>@<hash>`. Independence rules (§8.4) therefore never match a tool against a model or a person.
- **Readiness.** One function answers "is this tool ready here, and if not, why": runtime found on the machine (uv never downloads a Python: Decision [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md), item 1), environment built for this lock hash, named secrets resolvable. `check`, `doctor`, `start`, `eligible` and dispatch all use it. `baton tools setup` builds the environments for the vendored recipes' tools.
- **Trust.** Tools are part of the recipe's hash, so the existing rule holds: vendored recipes are trusted code, reviewed before vendoring, and `check` and `doctor` verify their hashes (§15.2). A changed tool file is a changed recipe.

### Doc edits

- `principles.md` §2: **Tool**, a new concept; **Step** now reads "done by one worker or tool per attempt".
- `design/recipes.md` §5.1 (a tool step in the example), §5.3 (load rules for `tool`), a new section for tools in recipes (`tool.yaml`, the lock file, reach).
- `design/layouts.md` §4.2 (`tools/` in a recipe package), §4.4 (`~/.baton/tools/`).
- `design/workers.md` §6.3: the `tool` adapter and its runner; how it differs from `command`.
- `design/packets.md` §7.1, §7.2: the inputs file and output directory the runner gives a tool; no `INSTRUCTIONS.md` is read by a tool.
- `design/runtime.md` §8.2 (`dispatched.tool`), §8.4 (no routing for tool steps; tool identity), §8.8 (tool failures and platform failures).
- `design/platform-and-security.md` §15.2: what a tool may touch, and what is and is not enforced.
- `design/director-interface.md` §13.1: `eligible` for a tool step; `tools setup`; what `start` reports.
- `docs/README.md`: the new section and Decision 0154.

### Manual edits

- `manual/admin/recipes-and-vendoring.md`: new section *Tools a recipe ships* (`#tools`): what a tool is, approving it at vendoring, what it needs (uv, a Python, never downloaded), `baton tools setup`, where environments live, readiness in `check`, `doctor` and `start`, and what `reach` enforces (network declared, not enforced); *Review before you vendor* names tools. (Slice 3.)
- `manual/admin/files-and-paths.md`: `~/.baton/tools/`. (Slice 3.)
- `manual/user/what-baton-may-do.md`: new section *Scripts a process runs* (`#tools`), in the owner's terms. (Slice 3.)
- `manual/reference/commands.md` (generated): `baton tools setup`; `vendor`'s help. `manual/context.yaml`: `tools` explained by the recipes topic. `manual/anchors.yaml`: the two new anchors. (Slice 3.)
- `manual/recipe-sources/spreadsheet-reconcile.md`, generated into `manual/recipes/spreadsheet-reconcile.md`: the recipe's topic for owners (what it does, what is asked, what it produces and needs, its parts, an example, what goes wrong); `manual/anchors.yaml`. (Slice 4.)

### Decisions

- [0154](../decisions/0154-tool-steps.md) (accepted): a tool is a third kind of executor; pinned; three forms; three changes.
- [0085](../decisions/0085-harness-tool-maps.md) (accepted): least privilege for a worker's tooling; this change applies the same rule to tools.
- [0156](../decisions/0156-tool-steps-details.md) (accepted): the environment builder, runtimes, network reach, retries, readiness, where environments live, the format version, time limits.
- [0158](../decisions/0158-tool-steps-no-python-download-scratch-cwd.md) (accepted): uv never downloads a Python; a tool runs in a fresh scratch folder.
- [0159](../decisions/0159-tool-runs-env-inputs-build-outputs.md) (accepted): environments named by lock and Python; the inputs file; built at dispatch; undeclared output files fail.
- [0160](../decisions/0160-tool-steps-ship-spreadsheet-reconcile.md) (accepted): the first shipped recipe with a tool is `spreadsheet-reconcile`.
- [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): what `recipe-builder` will do with tools; out of scope here.

## Plan

Final: the Request and Design are approved (2026-11-16).

### Slice 1: a recipe declares tools

- **Outcome:** a recipe with `tools/` loads, plans and is checked; nothing runs yet.
- **Criteria:** `tool` on a step and `tool.yaml` are loaded and validated; load errors for `tool` with `requires` or `prompt`, an unknown tool, a missing file, a lock without hashes; `baton plan` shows a tool step as done by its tool; the recipe hash covers the tool's files; recipes without tools are unchanged.
- **Effort:** M

### Slice 2: a tool step runs

- **Outcome:** a tool step is dispatched, supervised, taken in and gated like any step, in an environment built from its lock.
- **Criteria:** the environment is built and reused by lock hash; the runner's inputs file and `result.json`; exit and output failures; platform failures for a missing runtime and a failed build; clean environment with only named secrets; workspace mode enforced; `dispatched` records tool, lock, runtime and environment; the output feeds a later step; a review gate on a tool step.
- **Effort:** L

### Slice 3: readiness, approval and the manual

- **Outcome:** an owner knows before a run what its tools need, and approves them with the recipe.
- **Criteria:** readiness in `check`, `doctor`, `start` and `eligible`; `baton tools setup`; the vendoring summary lists each tool in plain words and needs the owner's approval; `baton recipe check` rules (the loader's, Slice 1); the manual topics for administrators and owners.
- **Effort:** M

### Slice 4: a shipped recipe with a tool

Added on 2026-11-16 when Slice 3 was split (Decision 0160).

- **Outcome:** the catalog has `spreadsheet-reconcile`, whose tool compares two CSV files deterministically.
- **Criteria:** the recipe loads, plans and vendors with the owner's approval of its tool; its tool reports added, removed and changed rows by key, end to end; its manual topic; the catalog, framing and project review list it like any recipe.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Change doc written from the owner's discussion of 2026-11-15 (Decision 0154). Found that the `command` adapter already runs a command line as a worker, so the proposal adds a recipe-shipped, pinned tool beside it and reuses the supervisor, intake and gates. No code changed.
- **Owner decision:** 2026-11-15, "Yes." (to drafting the tool-steps change doc).
- **Accepted:** No; proposal only. Eight open questions await the owner.

### Open questions answered

- **Summary:** The eight questions the proposal raised were answered as suggested and recorded as Decision 0156. The Request has no open questions; the Design is ready for approval. No code changed.
- **Owner decision:** 2026-11-15, "1-concur. 2-concur. 3-concur. 4-concur. 5-concur. 6-concur. 7-concur. 8-concur." (0156).
- **Accepted:** Request and Design await the owner's approval.

### Request and Design approved

- **Summary:** Confirmed Decision 0156 item 1 against uv 0.13.7. Two new questions (whether uv may download a Python; a tool's working folder) were answered as suggested and recorded as Decision 0158; the Design now runs a tool in a fresh scratch folder with a `{tool}` placeholder and builds environments with `--no-python-downloads`. Status set to accepted. No code changed.
- **Owner decision:** 2026-11-16, "No download", "Fresh scratch folder", "Approve" (0158).
- **Accepted:** Yes; Plan final, Slice 1 next.

### Slice 1: a recipe declares tools

- **Summary:** A step may name `tool: <id>` in place of `requires` and `prompt` (`models.Step`; both now optional, and the loader reports a worker step missing either as `recipe.missing_key`, as before). `tools/<id>/tool.yaml` is `models.ToolSpec` (`runtime`, `entry`, `dependencies.lock`, `reach {workspace, network, secrets}`); the new `tools.py` holds the lock parser (`parse_lock`: `name==version`, extras and markers allowed, at least one sha256 hash each, no options or URLs, checked against real `uv pip compile --generate-hashes` output from uv 0.13.7), the placeholders (`{input}`, `{output}`, `{tool}`, `{workspace}`) and `LoadedTool` (the spec, its folder, its own hash and its lock's hash). The loader checks each named tool once and returns them as `LoadedRecipe.tools`; `tool.yaml` gets the neutrality lint, and tools' files the vendor-mention warning. Two rules the Design left implicit, settled within it: the step's `workspace` must match the tool's `reach.workspace` (criterion 2 has the tool declare its workspace mode, and the example has it on the step), and the entry must pass `{output}`. `baton plan` shows `by tool <id>` (`PlanStep.tool`). No worker can do a tool step: `requirement_gaps` says so, so `eligible` lists no worker and dispatch refuses until Slice 2; `doctor` skips tool steps in its no-worker check; `versions.step_signatures` adds `tool` only for tool steps. The published `formats/baton-recipe-1.schema.json` is regenerated (the format stays `baton-recipe/1`, Decision 0156 item 7).
- **Design docs:** `principles.md` §2 (**Tool**; **Step**); `design/recipes.md` §5.1 (a pointer), §5.3 (steps and tools; neutrality covers `tool.yaml`), new §5.9 (tools in a recipe); `design/layouts.md` §4.2 (`tools/<id>/`); `docs/README.md` § index.
- **Manual:** none in this slice: no shipped recipe has a tool yet, and nothing an owner sees or an administrator configures changes; the manual edits come with Slice 3.
- **Tests:** `tests/test_tool_steps.py`: the `tool-demo` fixture (`tests/fixtures/recipes/tool-demo`: a worker step, a tool step, and a worker step taking the tool's output and artifact) loads, plans and conforms to the published schema; the recipe hash and the tool's hash cover the tool's files; a uv-written lock loads with its markers; an unused tool folder warns; 27 broken cases, each with its code; lock errors name their line; worker steps still need `requires` and `prompt`; recipes without tools have no tools, no `tool` in their step signatures or plans; no worker can do a tool step; the lock parser on its own.
- **Accepted:** Yes; slice of the in-progress change.

### Four details settled before Slice 2

- **Summary:** Starting Slice 2 raised four details the Design left open, answered by the owner as suggested and recorded as Decision 0159: an environment is named by its lock and its Python (`<lock sha256>-py<x.y>`, refining 0156 item 6); the inputs file is keyed by input name, JSON inputs as values and others as `{path, media_type}`; dispatch builds a missing environment, a failure being a platform failure; an undeclared file in the output folder fails the attempt.
- **Owner decision:** 2026-11-16, "Lock + Python", "Values and file refs", "Build at dispatch", "Attempt fails" (0159).
- **Accepted:** Yes.

### Slice 2: a tool step runs

- **Summary:** A tool step is dispatched to `tool:<id>`, its one executor: `engine.tool_routing` gives it as the only eligible entry, `Api._dispatch` makes the in-memory profile (`engine.tool_profile`: adapter and creator `tool`, a `clean` environment, `auth.env` only for the secrets in `reach.secrets`) after `tool_env.ensure` finds or builds the environment, and a worker profile cannot take a tool step nor the tool another step (`routing.ineligible`, `configuration.unknown_profile`; a machine profile with `adapter: tool` is never eligible). New `tool_env.py`: `uv python find --no-python-downloads --system --no-project` (a missing Python is `tool.no_runtime`, a missing uv `tool.no_uv`), `uv venv` and `uv pip install --require-hashes` into `~/.baton/tools/<lock>-py<x.y>/`, `env.json` written last, a file lock around the build, reused while the lock is unchanged; a `ToolSetupError` opens a platform incident and nothing is dispatched. New `adapters/tool.py` and `tool_runner.py`: the inputs file, a scratch working folder and an output folder outside the repository, the entry command with its placeholders and its first word from the environment's `bin` only, no `BATON_*` variables, and `result.json` from `output.json` and the declared artifacts (exit codes, missing or invalid `output.json` and undeclared files fail, with the last 20 lines of error output). Found while testing: a tool that printed its secret into its error output had it recorded in the notes, so the runner now masks the values of the secrets the tool names (`--secret-names`). The packet of a tool step has no `INSTRUCTIONS.md` and carries `manifest.tool`; `dispatched.tool` records the tool, lock, runtime, environment and reach (criterion 7). Effort defaults to `S` (`effort_source: tool default`). A tool step has one attempt unless it sets `max_attempts` (new `Step.max_attempts`, tool steps only, `step.max_attempts_needs_tool`): `run_started.step_max_attempts` (only in recipes with tool steps), `RunState.limit_for`, and a `step_limits` table in the SQLite cache (cache schema 2, so old caches rebuild). `routing.same_at` never matches a tool against a worker, so a reviewer of a tool step is always independent of it. `formats/baton-recipe-1.schema.json` regenerated.
- **Design docs:** `design/workers.md` §6.3 (the `tool` adapter); `design/packets.md` §7.1 (tool packets); `design/runtime.md` §8.2 (`run_started.step_max_attempts`, `dispatched.tool`), §8.4 (no routing; independence), §8.7 (effort `S`); `design/recipes.md` §5.9 (`max_attempts`, effort); `design/layouts.md` §4.4 (`~/.baton/tools/`); `design/platform-and-security.md` §15.2 (what a tool may touch, and what is enforced); Decision 0159 and `docs/README.md`.
- **Manual:** none in this slice: no shipped recipe has a tool yet, and nothing an administrator configures is added (environments are built by Baton); the administrator's topic on tools and `baton tools setup` come with Slice 3.
- **Tests:** `tests/test_tool_runs.py` (end to end, `slow`): the tool-demo run, the tool's output and artifact feeding the next step, `eligible`, `dispatched.tool`, effort `S`, the environment built; a probe tool sees only its named secret, no `BATON_*` variable, an empty scratch working folder, its inputs as values and none on its command line, and the environment's Python; a failing tool fails with its error output and escalates after one attempt, and `max_attempts: 2` gives a retry; an undeclared output file fails; no fitting Python is a platform failure with an incident and no dispatch; a missing secret refuses the dispatch; a read step's tool that writes the workspace is escalated; the environment is reused by a second run; a worker cannot take the tool step, nor the tool another; runs without tools record no tool limits; a secret printed by a failing tool is masked. Quick: the inputs file, output collection, placeholders, the per-step limit and independence. `tests/test_tool_steps.py`: `max_attempts` rules; review and human gates on a tool step load.
- **Accepted:** Yes; slice of the in-progress change.

### Slice 3: readiness, approval and the manual

- **Summary:** `tool_env.readiness` is the one answer to "is this tool ready here, and why not": uv found, a Python fitting `runtime.version` found (never downloaded), each named secret stored (`profiles.secret_places`, values never read); an environment not built yet is ready, with a note (Decision 0159, item 3). It feeds `eligible` (`engine.tool_routing`: the tool, or the one exclusion with the reasons), `start` (`tools_not_ready` and a warning each, never a refusal; `engine.tools_not_ready`), `doctor` (`tools`, and a warning each) and `check` (`tool.not_ready` warnings; `check(home=...)`). Dispatch of a tool that is not ready goes on to build, so a missing Python is a platform failure with an incident (Decision 0159) and a missing secret is refused as configuration. Vendoring: `project.tool_flags` asks the owner about each tool not yet approved in this project (new, or with different files), in the owner's terms (`tool_env.describe`: `does`, `needs`, `touches`); the lock entry of a recipe with tools records `tools {id: sha256}`; the CLI prints each tool's flag in plain words. `baton tools setup` (`Api.tools_setup`, CLI only, like `workers setup`) builds or reuses each vendored tool's environment and reports `built`, `reused`, `failed` or `not_ready`. The Director skill tells the owner about tool flags and tools not ready. The Plan's Slice 3 was split: the shipped recipe is Slice 4 (Decision 0160).
- **Design docs:** `design/recipes.md` §5.9 (approval at vendoring, the lock's `tools`); `design/director-interface.md` §13.1 (`eligible` for a tool step; `tools setup`; readiness in `check`, `doctor`, `start`; the Director skill's text); `docs/README.md` (Decision 0160).
- **Manual:** `manual/admin/recipes-and-vendoring.md` (*Tools a recipe ships*), `manual/admin/files-and-paths.md` (`~/.baton/tools/`), `manual/user/what-baton-may-do.md` (*Scripts a process runs*), the generated command reference, `manual/context.yaml`, `manual/anchors.yaml`.
- **Tests:** `tests/test_tool_readiness.py`: vendoring a recipe with a tool needs the owner and says what the tool does, needs and touches, in JSON and plain text, and the approval is recorded in the lock; an unchanged tool is not asked about again and a changed one is; a recipe without tools vendors as before; a tool with no fitting Python is reported by `check`, `doctor`, `start` and `eligible` and refused at dispatch; a missing secret makes a tool not ready until it is stored; `tools setup` builds, then reuses, and `doctor` then shows the environment; `tools setup` reports a tool it cannot build, and a project with no tools. `tests/test_tool_runs.py` vendors with the owner's approval.
- **Accepted:** Yes; slice of the in-progress change.

### Slice 4: a shipped recipe with a tool

- **Summary:** `examples/recipes/spreadsheet-reconcile` (Decision 0160): the roles `before` and `after` (CSV), run inputs `title`, `key` and optional `purpose`; `compare` is done by the tool `csv_diff` (standard library, empty lock, `reach` none), which outputs the counts and the `differences` CSV and exits 1 with a plain reason for a table its key cannot identify (missing column, empty key, a key twice) or one that is not UTF-8; `explain` is an ordinary worker step with a human gate. Being in the catalog, framing and project review may propose it, so framing now handles a shipped recipe with a tool: a part's `next` describes each tool not yet approved in the owner's terms (`frame.tool_flags_for`), and choosing the part approves it, recorded as a project `human_decision {kind: vendor, via: <framing run>}` with the selection's words before vendoring with that decision (`frame._vendor_decision`); `start --from-plan` needs `--note` for such a part; a recipe whose vendoring would also change step ids is refused (`frame.vendor_needs_owner`). Without this, choosing such a part would have failed, since its vendoring needs the owner.
- **Design docs:** `design/recipes.md` §5.7 (`spreadsheet-reconcile`); `design/adoption-and-framing.md` §11.6 item 4 (tools in framing); `design/layouts.md` (the catalog).
- **Manual:** `manual/recipe-sources/spreadsheet-reconcile.md`, generated into `manual/recipes/spreadsheet-reconcile.md`; `manual/anchors.yaml`.
- **Tests:** `tests/test_project_documents.py` lets the new recipe declare roles. `tests/test_spreadsheet_reconcile.py`: the recipe is in the catalog with its tool; the comparison's counts and differences; a table its key cannot identify is refused plainly (three cases); end to end, vendoring by name asks about the tool, then with the owner's approval the two attested files are bound, the tool compares them, and the report step receives the counts and differences; in framing, the part's `next` describes the tool, and choosing it vendors the recipe with the owner's words recorded as the approval. The catalog lists in `tests/test_conversation.py`, `tests/test_manual_gen.py` and `tests/test_real_use.py` include it.
- **Accepted:** Yes; slice of the in-progress change.

