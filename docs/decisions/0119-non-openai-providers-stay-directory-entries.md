---
id: "0119"
title: "Providers that are not OpenAI-compatible stay directory entries with their LiteLLM prefix"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4"]
---

# 0119. Providers that are not OpenAI-compatible stay directory entries with their LiteLLM prefix

## Context

Anthropic's own API and Bedrock, for example, are not OpenAI-compatible.

## Decision

They stay directory entries with their LiteLLM provider prefix, as today. Only their listing source differs: LiteLLM's model discovery or the model map.
