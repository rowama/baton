---
id: "0075"
title: "Profiles separate a model's identity from the route used to reach it"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§6.1", "§8.2", "§8.4", "§14.2"]
---

# 0075. Profiles separate a model's identity from the route used to reach it

## Context

A profile had `vendor` and `model`; `model` is the string passed to the adapter, and independence compared those strings literally. The same model reached directly and through OpenRouter looked like two models.

## Decision

A profile's identity fields:

| Field | Meaning |
|---|---|
| `creator` | Who made the model (`anthropic`, `openai`, `human`…). Required. Used by `different_vendor` |
| `model_id` | The model's canonical identity, `<creator>/<name>`, lower case, the same for every route. Optional; absent means **unknown**. Used by `different_model` |
| `provider` | The access provider (a direct API, `openrouter`, `local`…). Optional; execution and diagnostics only |
| `model` | Unchanged: the provider- or harness-specific invocation identifier passed to the adapter |
| `resource` | Optional: the machine resource (`resources.yaml`) the profile is bound to |

Canonical identity rules:

- A `model_id` names one model as its creator publishes it, revision included when the creator distinguishes revisions. A mutable alias (`latest`, a harness's default model) has no `model_id`.
- Fine-tunes, quantizations and other variants take their base model's `model_id`: for independence they are the same model.
- A route whose underlying model or host is unknown (e.g. an aggregator that does not say) has no `model_id`; its `creator` is the creator it claims, never the provider.
- A `manual` profile's identity is its person: `model_id` defaults to `human/<person>`.
- Nothing is inferred from an arbitrary `model` or provider string.

Compatibility:

- `vendor` is read as a legacy alias for `creator` (its documented meaning was already "used for independence checks"). A profile giving both with different values is a load error. Existing profiles have no `model_id`, so their model is unknown.
- `worker_selected` and `sme_requested` also record `creator`, `model_id`, `provider` and `adapter` as they were at dispatch, and keep writing `vendor` (equal to `creator`) and `model` (the invocation identifier). An older event is read as `creator = vendor`, `model_id` unknown. Independence reads these snapshots, never the current profiles or known-workers data.
- The fields are additive, so no format version changes (as in 0019).
