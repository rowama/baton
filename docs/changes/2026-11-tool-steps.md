---
id: 2026-11-tool-steps
title: "A step can be run by a script the recipe ships, with pinned dependencies and a record of what ran"
status: proposed
level: major
decisions: ["0154", "0156", "0085"]
touches: [principles.md, design/recipes.md, design/layouts.md, design/workers.md, design/packets.md, design/runtime.md, design/platform-and-security.md, design/director-interface.md]
manual: []
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

1. Environments are built with `uv` from a requirements file with exact versions and hashes **[VERIFY against the installed uv]**.
2. Python only in the first version; `tool.yaml` names the runtime kind.
3. Network reach is declared, shown at vendoring and recorded; it is enforced only under `isolation: container`, and the manual says so.
4. One attempt by default; a failure escalates with the tool's error output; a recipe may raise the limit.
5. `start` warns about a tool that is not ready; dispatch refuses.
6. Environments live in `~/.baton/tools/<lock hash>/`.
7. The recipe format stays `baton-recipe/1`.
8. Tool steps use the effort bands, defaulting to `S`.

### Out of scope

- **External software and specified interfaces** (Decision 0154, forms 2 and 3): the second change.
- **Waiting steps and the scheduler helper:** the third change.
- **`recipe-builder` choosing between a tool, an AI worker and a person,** and writing and testing tools: its own change, after this one.
- **Tools offered to a model inside a worker** ([2026-11-step-tool-harness](2026-11-step-tool-harness.md), on hold). That change gives an AI worker tools to call; this one runs a tool with no model. The two may later share tool definitions.
- **A catalog of tools shared between recipes.** A tool lives in its recipe for now.
- **The `command` adapter** stays as it is, for relaying to other agents and for machine-local tools.

## Design

For the owner's approval, with the Request (a major change: Request and Design are approved before the Plan is final).

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
  entry: ["python", "backtest.py", "--input", "{input}", "--output", "{output}"]
  dependencies: { lock: requirements.lock }
  reach: { network: false, secrets: [] }
  ```
  `{input}`, `{output}` and `{workspace}` are the only placeholders. `entry[0]` resolves inside the tool's environment.
- **Runner.** A new adapter, `tool`, runs `python -m baton.tool_runner` as the child, as `litellm_api` runs `worker_runner` (§6.3). The runner writes the inputs file from the packet, starts the entry command in the tool's environment with the tool's directory as its working directory, and turns `output.json` and the artifacts into `result.json`. Exit 0 with a valid output is `completed`; anything else is `failed` with the last lines of the tool's error output in `notes`. A tool cannot return `blocked` or questions.
- **Supervision.** Unchanged: the per-dispatch supervisor, running marker, deadline, intake, hooks and checkpoint (§8.7). A tool step is async like any other.
- **Identity.** A tool's result is recorded with creator `tool` and identity `tool/<recipe>/<id>@<hash>`. Independence rules (§8.4) therefore never match a tool against a model or a person.
- **Readiness.** One function answers "is this tool ready here, and if not, why": runtime found, environment built for this lock hash, named secrets resolvable. `check`, `doctor`, `start`, `eligible` and dispatch all use it. `baton tools setup` builds the environments for the vendored recipes' tools.
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

To be listed when the change is accepted. Expected: an administrator topic on tools (what a recipe's tools need, `baton tools setup`, where environments live), the owner's topic on what Baton may do (tools and what they may touch), and the generated command reference.

### Decisions

- [0154](../decisions/0154-tool-steps.md) (accepted): a tool is a third kind of executor; pinned; three forms; three changes.
- [0085](../decisions/0085-harness-tool-maps.md) (accepted): least privilege for a worker's tooling; this change applies the same rule to tools.
- [0156](../decisions/0156-tool-steps-details.md) (accepted): the environment builder, runtimes, network reach, retries, readiness, where environments live, the format version, time limits.
- [0155](../decisions/0155-recipe-builder-builds-software.md) (accepted): what `recipe-builder` will do with tools; out of scope here.

## Plan

Slices as proposed; refined once the Request and Design are approved.

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
- **Criteria:** readiness in `check`, `doctor`, `start` and `eligible`; `baton tools setup`; the vendoring summary lists each tool in plain words; `baton recipe check` rules; a shipped example recipe with one tool step; manual topics.
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
