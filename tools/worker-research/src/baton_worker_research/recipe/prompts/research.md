# Research models and routes for Baton's known-workers data

You maintain the data Baton uses to set up workers. Propose an updated version
of the `known_workers` input and report on your coverage.

## Scope

Cover the landscape systematically, not a shortlist:

- frontier model creators, reasonably popular alternative creators, and
  open-source and open-weight models;
- the hosting and distribution platforms that reach them (direct APIs,
  intermediaries such as OpenRouter, distribution hubs such as Hugging Face,
  local runtimes);
- every model category that can do a bounded job on its own: LLMs and small
  models, vision, transcription of a supplied file, and so on. An ongoing
  interactive session (live conversation, live transcription) is out of scope.

Model size and modality do not decide inclusion. State your inclusion
criteria, and list what you did not cover or could not confirm as coverage
gaps. Never claim exhaustive coverage without evidence.

## Rules for the data

- Keep the format exactly (`baton-known-workers/1`); keep every entry you
  cannot show to be wrong.
- A `model_id` is `<creator>/<name>` in lower case and names the model, not the
  route: the same model reached directly and through an intermediary has one
  `model_id` and two routes. Variants (fine-tunes, quantizations) take their
  base model's id.
- A route's `invocation` is the exact identifier that route's adapter passes
  on. A mutable alias, or a route whose underlying model is unknown, has
  `alias: true`, no `model_id`, and its `creator`.
- Mark a route `supported: true` only when it uses one of the `adapters`
  input; otherwise `supported: false`. Research may describe models no adapter
  can run.
- Capabilities and tiers come only from the `capabilities` input. Never list a
  machine-dependent capability.
- Every model and every new route carries `sources` (`url`, `retrieved`:
  today) and models carry `researched`. **Never add or change `verified`**:
  that field records a live check you did not perform.
- Mark a model you find withdrawn `retired: true`; do not delete it.

## What to return

Write the whole proposed file as the `known_workers` artifact. The output is
your report: inclusion criteria, providers and categories covered, coverage
gaps, and each change with why and its sources.
