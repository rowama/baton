# Assess chosen models for Baton

The owner of this machine asked Baton to judge the models in the `models`
input. For each, decide its **tier** and which **judgment capabilities** it
reliably has, from sources you read, and write an overlay file Baton merges
into its model knowledge.

## What to judge

- Use only the tiers and capabilities in the `capabilities` input. Never list
  a machine-dependent capability.
- Judge conservatively. Baton treats every claim as `likely` and checks it by
  use, but a tier set too high sends hard steps to a model that cannot do them.
  When a source does not support a claim, omit the capability or lower the tier.
- Every capability you claim has a `capability_basis` entry:
  - `documented`: a page states it. Give `source` (`url`, `retrieved`: today).
  - `catalog`: the `litellm` input shows it. Give `litellm`, the field:
    `supports_response_schema` for `structured_output`,
    `supports_function_calling` for `tool_use`, `supports_vision` for `vision`.
  - `judgment`: a one-line `reason` (for example a published benchmark or the
    creator class's normal capabilities).
- Take `context_tokens` from the listing facts or a page. Omit it when unknown.
- A model you cannot find reliable information about is not assessed: list it
  in `not_assessed` with the reason. Do not guess.

## Rules for the file

- Format: `format: baton-known-workers/1`, then `models:` only. Do not add
  routes, providers or any other section.
- A `model_id` is `<creator>/<name>` in lower case: use the `model_id` given
  for each model. Each entry has `creator`, `capabilities`, `capability_basis`,
  `tier`, optional `context_tokens`, `sources` (`url`, `retrieved`: today) and
  `researched` (today).
- **Never add `verified`**: that records a live check you did not perform.
- Models in the `models` input that already have a judgment elsewhere are not
  included; judge only what is asked.

## Check your work

If you can run commands, validate the file before returning it: append its
path to the `validator` input's command and run it. It prints why Baton would
refuse the file and exits 1, or exits 0 when it would accept it. Fix what you
can; what you cannot fix goes in `not_assessed` or `notes`.

## What to return

Write the overlay as the `overlay` artifact. The output is your report:
`assessed` (each model with its tier, a plain one-or-two-sentence summary and
its sources) and `not_assessed`.
