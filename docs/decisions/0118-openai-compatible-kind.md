---
id: "0118"
title: "openai_compatible is a provider kind needing only a base URL and an optional key"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4"]
---

# 0118. openai_compatible is a provider kind needing only a base URL and an optional key

## Context

Many intermediaries and local runtimes speak the OpenAI API, including `GET <base_url>/models`.

## Decision

A provider kind `openai_compatible` needs a base URL and a key (omitted for a local runtime). Baton reads `<base_url>/models` and dispatches through LiteLLM's OpenAI-compatible route with that base URL. Directory entries for such providers use the same kind. What the listing does not say (price, tool support) stays unknown. A local runtime may have no `credential`; whether the API adapter's child process can reach `localhost` on every platform is checked in Design.
