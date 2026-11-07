---
id: 2026-11-cli-model-routes
title: "Research proposes a route for every model each harness can run, and the capabilities that should be present"
status: proposed
level: standard
decisions: ["0080", "0083"]   # extends; new records listed under Design > Decisions
touches: [design/workers.md, design/layouts.md]
---

# Research proposes a route for every model each harness can run, and the capabilities that should be present

Depends on [2026-11-capability-confidence](2026-11-capability-confidence.md) for the `likely` state. A proposed capability is used and then checked, rather than left out.

## Request

### Problem

`baton workers setup` makes one profile per supported route in `defaults/known-workers.yaml`. The research run of 2026-11-06 (`tools/worker-research/reports/2026-11-06.md`) added 31 API routes but no harness routes:

- **Claude Code** still has routes only for Opus 5.5 and Sonnet 5.5. The report says Fable 5.1 and Haiku 5.5 were skipped because "the model-config page was not re-read this run".
- **Codex** has only its default-model alias. No OpenAI model is reachable through Codex as a pinned, identified profile.
- **The prompt never asks for harness routes.** Its scope covers creators, hosts and categories, not "which models can each harness run".
- **Capabilities that should be present are omitted.** The prompt allows a capability only with documented evidence. So no new model claims `structured_output`, and no route claims `web_access`. The report itself says this was because no page it read confirmed them.
- **The proposal was not machine-validated by the worker** ("the Python run was not approved"). `baton-worker-research` does validate it after the run, but the worker cannot fix its own mistakes in the same attempt.

Which models a harness can run, and which tools it provides, are documented facts. The researcher should find them, and a deterministic check should catch it when it does not.

### Acceptance criteria

1. For each harness provider, the researcher proposes:
   - one pinned route per current model the harness documents it can run (Claude Code: every current Claude model; Codex: every OpenAI model it documents), each with `model_id`, invocation and sources;
   - the harness's default-model alias route as now.
2. For each harness provider, the researcher proposes:
   - the **tool map**: per tooling capability, the args that turn it on, the CLI version range and sources;
   - the flag for machine-readable output used as tool-call evidence.

   Each harness route lists the tooling capabilities that map covers. The report calls out any flag that widens permissions.
3. **The researcher proposes capabilities that should or could be present,** each with a basis:
   - `documented`, with a source;
   - `catalog`, from LiteLLM's model map (`supports_response_schema` → `structured_output`, `supports_function_calling` → `tool_use`, `supports_vision` → `vision`, and `max_input_tokens` → `context_tokens`);
   - `judgment`, the creator class's normal capabilities with a one-line reason.

   All ship as `likely` and are checked by use. A capability with no basis at all is still omitted.
4. `baton-worker-research` gives the worker, as inputs:
   - the current tool maps, and the capability vocabulary's tooling capabilities;
   - a maintainer-kept list of starting documentation URLs for each harness;
   - the installed LiteLLM model-map entries for every API route already in the data.

   It records the LiteLLM version in the report.
5. **Deterministic coverage check.** After the run, the tool lists every model whose creator matches a harness's creator (anthropic → `claude_code`, openai → `codex`) that has no pinned route on that harness and no coverage-gap entry naming it. Any such model makes the run refused, like an invalid proposal (saved beside the report, not written to the repository).
6. The worker can validate its proposal during its attempt: the validator is given to it as a command it may run. Failures it cannot fix go into the report.
7. The report shows, for each harness: models routed, models not routed with the reason, and tools proposed.
8. A real run on this machine, then `baton workers setup`, generates one profile per model for each logged-in CLI (e.g. `claude-code-claude-haiku-5-5`, `codex-<model>`) next to the API profiles of the same models. Independence still treats a CLI profile and an API profile of one model as the same model (0075).
9. Tests cover the coverage check, the capability basis validation and the new inputs; `pytest` passes.

### Open questions

1. Account entitlement (which models a ChatGPT or Claude plan allows in its CLI) depends on the owner's plan. Is it enough to leave this to verification by use (an unavailable model is classified `platform` and the profile re-routed)? Or should `workers setup` ask the CLI where it can list models **[VERIFY whether either CLI can]**?
2. Should `catalog` facts from LiteLLM's model map be read by the researcher (reviewed in the diff), or by `workers setup` at run time from the installed LiteLLM (always current, but unreviewed)? The proposal assumes the researcher.
3. Starting URL list: kept in `tools/worker-research/` (maintainer data), or in the prompt?

## Design

### Doc edits

- `design/workers.md` §6.4:
  - harness providers carry a researched tool map (capability → args, CLI version range, sources), validated against the tooling capabilities of the vocabulary;
  - routes and models carry a capability basis (`documented` / `catalog` / `judgment`);
  - harness routes are one per model the harness documents;
  - research inputs and the coverage check;
  - `known-workers` format stays `baton-known-workers/1` if the basis is an optional field, else a version bump (decide in slice 1).
- `design/layouts.md` §4.1: maintainer data for the researcher's starting URLs, if kept as a file.
- Prompt `tools/worker-research/.../prompts/research.md`:
  - a Harness section (the model list and tools per harness);
  - the capability basis rules replace "only with documented evidence";
  - the validator command.

### Decisions

- **New:** a researched capability needs a basis (`documented`, `catalog` or `judgment`), not proof; it ships as `likely`.
- **New:** the research tool refuses a proposal that leaves a model of a harness's creator without a pinned harness route or a stated gap.
- **New:** harness CLI flags are researched data (tool maps), reviewed in the diff like model IDs. Drift found at run time goes to the platform SME (2026-11-capability-confidence).
- **Extend 0083:** the researcher's inputs include the current tool maps, starting URLs and LiteLLM model-map entries.

## Plan

### 1. Capability basis in the data

- **Outcome:**
  - `known_workers.py` validates `basis` on capabilities.
  - Existing seed entries are marked `judgment` or `documented` as they were made.
  - Setup carries capabilities over as `likely`.
- **Criteria:** 3 (schema part), 9.
- **Effort:** S

### 2. Researcher inputs and prompt

- **Outcome:**
  - The tool passes tool maps, starting URLs, LiteLLM model-map entries and the validator command.
  - The prompt asks for per-model harness routes, harness tool maps with flags and capabilities with a basis.
- **Criteria:** 1, 2, 3, 4, 6, 7.
- **Effort:** M

### 3. Coverage check

- **Outcome:** the tool refuses a proposal with an unrouted, unexplained model of a harness's creator.
- **Criteria:** 5, 9.
- **Effort:** S

### 4. Real run and setup

- **Outcome:** a maintainer run lands reviewed data, and `workers setup` produces the per-model CLI profiles.
- **Criteria:** 8.
- **Effort:** S

## Log

<One entry per slice, written in the slice's own commit together with its code, tests and design doc edits.>
