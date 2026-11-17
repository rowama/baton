# Learn how this work is usually done, and compare the ways to do it

The `profile` input holds the owner's goal, the chosen generality, the requirements so far and
`discovery`: the implementation choices the profile found, with their timing.

## 1. How this class of work is usually done

Find how this class of work is normally done, so the process is not designed from nothing: the
usual stages and their order, standards and rules that apply, common ways it goes wrong, who
usually signs off, and what is usually produced.

- Add what you learn to the `ledger` as entries with status `researched` and a `basis` that names
  your source; add each source to `sources` with what it supports.
- Do not change or promote an owner's `confirmed` entry. If research contradicts one, add an entry
  of kind `assumption` with status `open` that states the conflict, in the owner's terms.
- Keep to the class of jobs the chosen rung covers. Do not add stages for jobs the owner did not
  place inside it.
- Mark a finding `inferred`, not `researched`, when you have no source for it.

## 2. Choices that shape the process (`before_design`)

For each `discovery` record whose timing is `before_design`, find the plausible ways to do it.
Look at what actually exists now, from sources you have read, not from memory: existing products,
frameworks, standards, manual procedures and custom work, whichever are relevant. The owner need not
have named any. Do not use a fixed number of options, and do not add an irrelevant one to fill a
category.

- Fill `comparison`: `criteria` tied to the owner's requirements; each `options` entry with what
  building the process would need to do differently for it (`requires_of_development`), its
  `tradeoffs` and its `sources`, each with a title, a link where there is one, and the date you read
  it (`read_on`, with the version where it matters); `exclusions` with the reason; what is
  uncertain; and your recommendation.
- If you cannot reach current sources, do not fill the gap from memory and call it researched.
  Return `blocked` with a question saying what you could not check.
- A named target that is a `firm_constraint` is not compared away. A `preference` or `example` is
  one candidate among the others.
- If the comparison shows the choice does not change the process after all, say so: set the
  record's `timing` to `in_generated_recipe` (and `generated` to name the stages that will carry it
  out) or `settled`, with the reason. Do not drop a record.
- The choice is the owner's. A recommendation is not a decision. Return `blocked` with one
  structured question per choice: plain words, the options (including "none of these"), your
  recommendation as the `best_guess`, and why it matters. When the owner's answers arrive, set the
  record's `status` to `decided`, add a ledger entry of kind `decision` and status `confirmed`
  whose `owner_words` quote their answer, and set `decision.ledger_id` to it. Never confirm an
  entry the owner has not answered.

## 3. Deferred choices (`in_generated_recipe`)

Leave these records as they are. The generated process will do this research for each job; you
only check that it is reasonable for one process shape to serve the alternatives you see, and say
if it is not (change the timing as above).
