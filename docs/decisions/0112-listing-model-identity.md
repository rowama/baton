---
id: "0112"
title: "A listing id takes its identity from a matching researched route, else its canonical slug"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.1", "§6.4"]
---

# 0112. A listing id takes its identity from a matching researched route, else its canonical slug

## Context

OpenRouter's ids differ from Baton's (`anthropic/claude-opus-5.5` against `anthropic/claude-opus-5-5`).

## Decision

Identity is the `model_id` of a researched route whose `invocation` matches the listing id. Otherwise it is the listing's `canonical_slug`, lower-cased, as `<creator>/<name>`, with `alias: true` when the listing marks an alias (`alias_target`) or a router (`openrouter/auto`). Otherwise it is unknown, and unknown is never independent (0076).
