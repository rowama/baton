---
id: "0080"
title: "Known-workers data: models, providers and routes, with research and verification kept apart"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§4.1", "§6.1", "§6.3"]
---

# 0080. Known-workers data: models, providers and routes, with research and verification kept apart

## Context

Shared knowledge about models and harnesses ships as read-only data. Research may cover models the runtime cannot execute; unverified findings must not be presented as tested.

## Decision

`defaults/known-workers.yaml`, format `baton-known-workers/1`, three sections:

- **`models`**, keyed by `model_id` (0075): `creator`, intrinsic `capabilities` (vocabulary-checked, never machine-dependent ones, 0082), `tier`, `context_tokens`, `category` (e.g. `llm`, `vision`, `transcription`), `sources: [{url, retrieved}]`, `researched` (date).
- **`providers`**, keyed by name: `kind` (`direct_api`, `intermediary`, `harness`, `local`), `sources`.
- **`routes`**: `model_id`, `provider`, `adapter`, `invocation` (the profile's `model`), `alias` (a mutable alias: the generated profile gets no `model_id`), `supported` (whether this runtime can execute it; an unsupported route never generates a profile), optional `verified: {date, tool, version}` for an actual live check.
- Research claims (`sources`, `researched`) and live checks (`verified`) are separate fields. A `supported` route must name an existing adapter; validation checks schema, vocabulary, adapters and that every route's `model_id` exists.
- Vendors and models here are profile data, beside the adapters; recipes stay model-neutral and the recipe neutrality lint is unchanged.
