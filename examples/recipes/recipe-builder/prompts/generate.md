# Build the recipe package

Translate the approved design into a recipe package, and nothing more. The approved design is in
`shaped` (the last iteration's design and audit); the goal and chosen generality are in `profile`.
You work in the project; commit your work.

1. Write the package to `recipes/drafts/<run slug>/` (the run slug is the one `profile` was
   published under; use the same words, lower-case and hyphenated): `recipe.yaml`, `prompts/`,
   `schemas/` and `static/` as needed. Use the recipe format the other shipped recipes use. Name no
   model, vendor or tool in the recipe: require capabilities, never a model.
2. Include a `scope` block that states what the recipe covers, what it is not for (naming a recipe
   that is, when you know one) and what varies by job. Set `parent: {id, version}` to the recipe in
   `profile.existing_recipe`/the base recipe when you built from one, otherwise `parent: null`.
3. A fact about the owner's one job (an `instance` ledger entry) goes in no prompt and no static
   file. Write it into an example run input instead.
4. Write the final ledger, copied exactly from the design's `ledger`, to
   `recipes/drafts/<run slug>.ledger.json`, and attach it as the `ledger` artifact. Do not edit it.
5. Write the `walkthrough` artifact (markdown) for the owner: what the process does, who does each
   stage, what they decide, what happens when something fails, and what it covers and does not.
   No file names, no jargon.

Run `baton plan recipes/drafts/<run slug>` yourself before you finish, and fix what it reports. The
runtime runs it again, and `baton recipe check`, as gates. Return the commit, the package path, the
ledger path and a short summary.
