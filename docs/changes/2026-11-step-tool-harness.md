---
id: 2026-11-step-tool-harness
title: "Baton runs a bounded tool loop for API workers, with only the tools a step requires"
status: proposed            # ON HOLD: after 2026-11-capability-confidence and 2026-11-cli-model-routes
level: major
decisions: []
touches: [design/workers.md, design/runtime.md, design/recipes.md, design/platform-and-security.md, principles.md]
---

# Baton runs a bounded tool loop for API workers, with only the tools a step requires

> **On hold.** Discussed 2026-11-06. For now, web steps are steered to subscription CLIs ([2026-11-capability-confidence](2026-11-capability-confidence.md), criterion 10). This change makes API routes able to do the same work without a CLI.

## Request

### Problem

The `litellm_api` adapter's runner (`worker_runner.call_model`) makes one `litellm.completion` call and reads the reply. It passes no tools and runs no loop. The runner already does some tool work itself: it builds the messages from the packet, enforces the schema and writes the artifacts. So API workers have `file_write` through Baton, but no `web_access` or file reading. Steps that need those can only go to a harness (Claude Code, Codex), which ties them to a CLI subscription and its quotas.

A recipe already states what tools a step needs (`requires`). Baton knows how to provide those tools, what goes into them and what to do with their output. A small loop owned by Baton, built per step from its `requires`, would let any API model with tool calling do those steps.

LiteLLM does not run tool loops: the caller must execute the tool calls and call `completion` again ([LiteLLM: function calling](https://docs.litellm.ai/docs/completion/function_call)).

### Acceptance criteria (draft)

1. The runner offers the model only the tools named by the step's `requires`, each implemented by Baton:
   - `fetch` (HTTP GET of a URL, text extracted);
   - `web_search`;
   - `read_input` (files in the packet, or the working tree for `read` steps).
2. The loop runs until the model's final structured reply or the step's tool-call budget (a recipe or level default). Running out of budget is a step failure with the transcript kept.
3. `web_search` uses, in order:
   - the provider's own search, where LiteLLM reports `supports_web_search` (passed as `web_search_options`, so no extra account; [LiteLLM: web search](https://docs.litellm.ai/docs/completion/web_search));
   - otherwise an owner-declared search provider through LiteLLM's search interception or a direct call ([LiteLLM: web search interception](https://docs.litellm.ai/docs/integrations/websearch_interception));
   - otherwise the capability is not offered.

   No scraping of search engine result pages.
4. Tooling capabilities the runner provides are facts about Baton's code, recorded as `verified` once their backend is present, rather than researched. A model qualifies only if it supports tool calling (`supports_function_calling`).
5. Every tool call and result is recorded in the attempt log. Tool output is treated as untrusted data in the prompt.
6. Routing prefers the runner for read-only tool sets (`web_access`, `workspace_read`) and harnesses for workspace and code tools (`shell`, `code_exec`, `repo_workspace`). Baton does not reimplement a coding agent.

### Open questions

- **Quota and credit exhaustion on harnesses.** This should be general failover: mark the profile unavailable until reset and re-route to the next eligible worker. Should that be its own change? LiteLLM's Router fallbacks should not be used inside a dispatch, since a silent model switch would break the recorded identity and independence checks (0075, 0076).
- Default tool-call budget, and whether it counts against the step's time limit or separately.
- Can a step combine fetched web content with write tools? Suggest not in the first version (prompt injection risk).
- Does the runner become its own adapter (e.g. `baton_runner`), or an option of `litellm_api`?

## Design

To be written when taken off hold.

## Plan

Suggested first slice: `fetch` plus provider-native `web_search` only, proven by routing the `worker-research` step to an API model.

## Log
