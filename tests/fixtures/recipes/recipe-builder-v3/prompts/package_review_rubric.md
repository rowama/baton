# Package review rubric

You are reviewing a generated recipe package in the working tree against the approved design. You
did not write it. Report findings only.

| Check | Typical severity |
|---|---|
| A stage, input, check or owner decision in the design that the package lacks | high |
| Something in the package the design does not call for | medium |
| A script check that runs a command the owner would not expect | high |
| A prompt that names a vendor or a model, or holds a fact about one job | high |
| The ledger copy differs from the design's ledger | high |
| The `scope` block does not match the chosen generality | medium |
| `parent` missing, or naming a recipe the package was not built from | medium |
| A deferred discovery in the design (`in_generated_recipe`) that the package does not carry as research, decision and using steps, in that order, or whose using steps do not take the owner's choice as an input | high |
| A fixed implementation target in a recipe whose agreed scope is not specific to it | high |
| A step whose instructions cannot say anything specific to the work, so its check is empty | high |

For each finding give a short `title`, the `location` (a file and section), the `detail` and a
`suggested_fix`. Set `coverage.complete` to false, with a note, for anything you could not judge.
