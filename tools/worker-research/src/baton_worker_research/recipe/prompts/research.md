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
- Every capability you claim for a model or route has a `capability_basis`
  entry. A claim ships as `likely` and Baton checks it by use, so claim what
  should or could be present; omit one only when you have no basis at all:
  - `documented`: a page states it. Give `source` (`url`, `retrieved`).
  - `catalog`: the `litellm` input shows it. Give `litellm`, the field:
    `supports_response_schema` for `structured_output`,
    `supports_function_calling` for `tool_use`, `supports_vision` for
    `vision`. Take `context_tokens` from `max_input_tokens` when no page gives
    one. The input holds the installed LiteLLM's entry for every API route
    already in the data; its version is recorded in the report.
  - `judgment`: the creator class's normal capabilities. Give a one-line
    `reason`.
- Every model and every new route carries `sources` (`url`, `retrieved`:
  today) and models carry `researched`. **Never add or change `verified`**:
  that field records a live check you did not perform.
- Mark a model you find withdrawn `retired: true`; do not delete it.

## Harnesses

A harness provider (`kind: harness`) is a CLI that runs models. The
`harness_docs` input lists starting pages for each; follow their links, and
name the pages you used in `sources`. For each harness provider:

- Add a `creators` list to the provider: the creators whose models the CLI can
  run (a harness may run more than one creator's).
- Give **one pinned route per current model the CLI documents it can run**:
  `model_id`, `invocation` (the exact value passed to `--model`), `adapter`
  as the provider's existing routes have it, `sources`, and the capabilities
  the route adds with their `capability_basis`. Keep the default-model alias
  route. A model the CLI cannot run goes in the report's `models_not_routed`
  with the reason. The tool checks that no model of the harness's creators is
  left out without being named there, and refuses the run if one is.
- Give the provider's **`tools` map**: for each of the `tooling_capabilities`
  the CLI can switch on, the `args`, `position`, `off_args`, the `help` args
  and `flag` that show it exists, the stream event names that show its use
  (`evidence`), the CLI `versions` checked and `sources`. The current maps are
  the `tool_maps` input. List the tooling capabilities each route covers in
  its `capabilities`. In the report, list under `widens_permissions` every flag
  that gives the CLI more than it has by default.
- Name the flag that makes the CLI print machine-readable events: Baton reads
  them as the evidence that a tool was used.
- A route for another CLI that this runtime has no adapter for is
  `supported: false`.

## Check your work

If you can run commands, validate the proposal before returning it:
append the file's path to the `validator` input's command and run it. It
prints why the tool would refuse the proposal and exits 1, or exits 0 when it
would accept it. Fix what you can. What you cannot fix goes in the report's
`coverage_gaps` and `notes`.

## What to return

Write the whole proposed file as the `known_workers` artifact. The output is
your report: inclusion criteria, providers and categories covered, coverage
gaps, one `harnesses` entry per harness provider (models routed, models not
routed with the reason, tools proposed, flags that widen permissions), and
each change with why and its sources.
