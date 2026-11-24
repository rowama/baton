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
| A step whose prompt and output schema contradict each other: the prompt requires what the schema forbids or forbids what the schema requires, or a rule the prompt states (a disposition, an answer, an evidence rule, or a result status such as returning `blocked` with questions while a choice is still open) that no output the schema accepts can meet | high |
| A program that does more or less than the design's `program.does`, or whose step differs from the design's stage | high |
| An engineered program whose `contract.json` differs from the design's contract, or whose `program.yaml` reach differs from it | high |
| A program that is not one file, imports anything outside the Python standard library, reaches the network, reads a secret, or writes anything but `output.json` and its declared artifacts | high |
| A program whose `reach` declares less than the script touches (files, network, secrets), or a step whose `workspace` differs from it | high |
| A program's examples differ from the ones the owner approved in the design, or were changed to fit the code | high |
| A program that spends money or changes something others depend on with no owner approval before it | high |
| The walkthrough leaves out a program, or an AI step a program could do, or a delegation mark from the design | medium |

For a step whose prompt and schema contradict each other, read every rule the prompt states against the step's output schema, including the schemas it draws on, and name both files in the `location`; an output that only validates by inventing an owner's answer is no way to meet the rule.

For each finding give a short `title`, the `location` (a file and section), the `detail` and a
`suggested_fix`. Set `coverage.complete` to false, with a note, for anything you could not judge.
