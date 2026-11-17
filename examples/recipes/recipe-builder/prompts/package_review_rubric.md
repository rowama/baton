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
| A tool that does more or less than the design's `tool.does`, or whose step differs from the design's stage | high |
| A tool that is not one file, imports anything outside the Python standard library, reaches the network, reads a secret, or writes anything but `output.json` and its declared artifacts | high |
| A tool whose `reach` declares less than the script touches (files, network, secrets), or a step whose `workspace` differs from it | high |
| A tool's examples differ from the ones the owner approved in the design, or were changed to fit the code | high |
| A tool that spends money or changes something others depend on with no owner approval before it | high |
| The walkthrough leaves out a tool, or an AI step a program could do, or a delegation mark from the design | medium |

For each finding give a short `title`, the `location` (a file and section), the `detail` and a
`suggested_fix`. Set `coverage.complete` to false, with a note, for anything you could not judge.
