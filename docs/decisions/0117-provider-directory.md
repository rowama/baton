---
id: "0117"
title: "The provider directory is the providers section, extended and researched separately from models"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4"]
---

# 0117. The provider directory is the providers section, extended and researched separately from models

## Context

Which providers go in the directory first, and where do their facts live?

## Decision

The existing `providers:` section gains fields: display name, base URL, key variable or header, API style, listing source, key-info or quota endpoint, sign-up URL. Research proposes provider entries with sources, and the validator checks them. First entries: the intermediaries with free or cheap tiers (OpenRouter, Groq, Chutes, Requesty, Together, Fireworks, Cerebras, DeepInfra), the direct APIs already in the data, and the local runtimes (Ollama, LM Studio, vLLM) as `openai_compatible`. A directory provider needs no researched models.
