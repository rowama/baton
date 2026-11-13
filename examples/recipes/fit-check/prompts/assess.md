# Score against the fit rubric

Score the `profile` input against the `rubric` input, row by row. You are judging the work the
profile's `scope` names, using that work's own facts.

- Say in `assessed_work` which work you scored, in a sentence: developing a process, executing it,
  or other work, as `scope` states it. A `scope.target` is not scored.
- Give one reason per rubric row, saying which way the row leans and why, using the profile's own
  facts. Set `basis` to `stated` for a fact the owner or the project context gave, or `assumed`
  for one the profile lists under `assumptions`.
- Choose the verdict the rubric's balance supports: `fits`, `fits_per_occurrence` or
  `not_recommended`.
- Give the next step the rubric names for that verdict, made concrete for this work.

Do not add rows, weights or criteria the rubric does not contain. Frequency and duration are
signals, not cutoffs. Do not reject development work because of how the finished process will
run.

For `not_recommended`, name a simpler `alternative` that suits the work (a script, asking an
assistant directly, an existing tool, a manual procedure, or an operations engine). If the work
asked for was executing a process, you may offer, in `development_offer`, developing a suitable
process or system as a **separate** project; the owner has not asked for it, so say so, and do not
word the next step as if it had been chosen.

If a `recipes` input is given, it lists the recipes this project can already run, each with a
`scope` (what it covers and what it is not for) where the recipe has one. For `fits` or
`fits_per_occurrence`, set `recipe` to the one recipe whose scope or description covers the whole
of the assessed work, as `{id, version}`, and say so in the next step; set it to `null` when none
does, and the next step is then to author one. A recipe that covers only part of the work, or is
for a different kind of deliverable, does not cover it. Never name a recipe that is not in the
list. Leave `recipe` out for `not_recommended`.

If a `context` input is given, it summarizes an existing project the request is about. Use it to
choose the recipe: prefer the recipe whose steps produce what the project already has. Do not add
rubric rows for it, and do not claim to know which files exist beyond what it says.
