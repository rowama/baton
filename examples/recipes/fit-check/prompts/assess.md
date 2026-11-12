# Score against the fit rubric

Score the `profile` input against the `rubric` input, row by row.

- Give one reason per rubric row, saying which way the row leans and why, using the
  profile's own facts.
- Choose the verdict the rubric's balance supports: `fits`, `fits_per_occurrence`
  or `operations_engine`.
- Give the next step the rubric names for that verdict, made concrete for this idea.

Do not add rows, weights or criteria the rubric does not contain.

If a `recipes` input is given, it lists the recipes this project can already run, each with a
`scope` (what it covers and what it is not for) where the recipe has one. For a `fits` verdict,
set `recipe` to the one recipe whose scope or description covers the whole idea, as `{id, version}`,
and say so in the next step; set it to `null` when none does, and the next step is then to
author one. Never name a recipe that is not in the list. Leave `recipe` out for any other verdict.

If a `context` input is given, it summarizes an existing project the idea is about. Use it to
choose the recipe: prefer the recipe whose steps produce what the project already has. Do not
add rubric rows for it, and do not claim to know which files exist beyond what it says.
