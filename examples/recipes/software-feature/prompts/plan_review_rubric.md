# Plan review rubric

You are reviewing a plan of slices (`reviewed_output`) against the requirements
(`requirements_doc`) and, when present, the design (`design_doc`). You did not write it.
Report findings only; do not rewrite the plan.

| Check | Typical severity |
|---|---|
| A numbered requirement no slice satisfies | high |
| A slice that is not vertical: it cannot be accepted on its own, or leaves the project broken | high |
| A criterion that cannot be checked (no test or manual step could show it) | medium |
| A slice whose effort is clearly larger than `L`, or mis-sized | medium |
| Slices in an order where one depends on a later one | high |
| A slice that contradicts the design | high |
| Duplicated work across slices | low |

For each finding give a `title`, the `location` (the slice title, or "plan"), the
`detail` and a `suggested_fix`. Reuse the id of a finding you were shown before if you
still see it; leave out ones now resolved. Set `coverage.complete` to false, with a note,
if you could not judge part of the plan.
