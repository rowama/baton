# Build the recipe package

Translate the approved design into a recipe package, and nothing more. The approved design is in
`shaped` (the last iteration's design and audit); the goal and chosen generality are in `profile`.
You work in the project; commit your work.

1. Write the package to `recipes/drafts/<run slug>/` (the run slug is the one `profile` was
   published under; use the same words, lower-case and hyphenated): `recipe.yaml`, `prompts/`,
   `schemas/` and `static/` as needed. Use the recipe format the other shipped recipes use. Name no
   model or vendor of a worker in the recipe: require capabilities, never a model. A product or
   standard the owner's work is *about* (a legitimate target of what the process delivers) may be named
   when the agreed scope is specific to it; otherwise the target is a run input.
2. Include a `scope` block that states what the recipe covers, what it is not for (naming a recipe
   that is, when you know one) and what varies by job. Set `parent: {id, version}` to the recipe in
   `profile.existing_recipe`/the base recipe when you built from one, otherwise `parent: null`.
3. A fact about the owner's one job (an `instance` ledger entry) goes in no prompt and no static
   file. Write it into an example run input instead.
4. Write the final ledger file to `recipes/drafts/<run slug>.ledger.json` and attach it as the
   `ledger` artifact: a JSON object `{"ledger": <the design's ledger, copied exactly>, "discovery":
   <the design's discovery records, copied exactly>}`. Do not edit either.
   A record with timing `in_generated_recipe` is part of the process: write its research stage
   (it requires `web_access`), its decision stage (a human gate, taking the research output as a
   required input) and the stages named in `generated.consumers`, each taking the decision stage's
   output as a required input, with the ids `generated` names. The target is a run input of the
   recipe, never a fixed value.
5. Write the `walkthrough` artifact (markdown) for the owner: what the process does, who does each
   stage, what they decide, what happens when something fails, and what it covers and does not.
   No file names, no jargon.

Run `baton plan recipes/drafts/<run slug>` yourself before you finish, and fix what it reports. The
runtime runs it again, and `baton recipe check`, as gates. Return the commit, the package path, the
ledger path and a short summary.
