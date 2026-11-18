---
id: "0168"
title: "Tool loop for API workers: part of litellm_api, web access needs search and fetch, any LiteLLM search provider or SearXNG, replies through finish, 40 calls by default, fetch limited to found or given URLs when a step also reads the project, no routing preference, no programs as tools, searches counted"
status: accepted
date: 2026-11-17
source: "Owner, 2026-11-17: \"As suggested.\""
sections: ["§5.6", "§6.3", "§6.4", "§8.2", "§8.4", "§15"]
---

# 0168. Tool loop for API workers: part of litellm_api, web access needs search and fetch, any LiteLLM search provider or SearXNG, replies through finish, 40 calls by default, fetch limited to found or given URLs when a step also reads the project, no routing preference, no programs as tools, searches counted

## Context

`2026-11-step-tool-harness` gives the `litellm_api` runner a bounded loop that offers a model only the tools its step requires (`search`, `fetch`, `list_files`, `read_file`, and always `finish`). The change doc raised eight open questions, each with a suggested answer; one more was raised when they were put to the owner: provider web search is billed per search, apart from tokens. The owner accepted every suggested answer.

## Decision

1. **Part of `litellm_api`, not a new adapter.** The loop runs in the same runner, with the same profiles, routes and recorded identity.
2. **`web_access` needs both search and fetch.** A profile that can fetch but has no search backend does not offer `web_access`; no fetch-only capability is added.
3. **Search providers.** Any provider LiteLLM's search interface supports may be declared, once per machine, with `workers declare` and a `secret:` key; a self-hosted SearXNG needs only its base URL. Baton has no code per provider. Search engine result pages are never scraped.
4. **The model replies by calling `finish`.** Its arguments are the step's reply, checked against the reply schema as today, on every route that offers tools.
5. **At most 40 tool calls per attempt by default**; a recipe may set `tool_calls: <n>` on a step. The figure is a starting guess, to be revised from recorded use. Reaching the limit without `finish` is a `failed` result.
6. **A step may read the project and the web at once**, but then `fetch` opens only URLs that appeared, during this attempt, in a search result (for provider-native search, the citations the provider returns) or in the step's inputs. A provider that returns no citations allows no fetch on such a step.
7. **No routing preference.** The runner's profiles compete by tier and capability state like any other worker.
8. **A recipe's programs (§5.9) are not offered to a model as tools** in this change; that is a possible later change.
9. **Searches are counted, not priced.** Each attempt records how many searches it made; `doctor` and the setup page say when a profile's web access is billed per search by its provider. Baton does not estimate the charge.
