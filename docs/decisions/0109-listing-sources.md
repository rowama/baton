---
id: "0109"
title: "Listings come first from OpenRouter, then other providers through the same mechanism"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4"]
---

# 0109. Listings come first from OpenRouter, then other providers through the same mechanism

## Context

Which providers' model lists does the first version read?

## Decision

OpenRouter (public listing, then the per-account listing) first, since it alone covers most free and cheap models. Then Groq, Gemini, DeepSeek, Mistral and xAI through the same mechanism, using LiteLLM's model map for metadata where a provider's own list is bare. models.dev is used only after its licence and API have been checked.
