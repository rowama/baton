# Audit the design

You did not write this design. Review the `design` output and the `document` against the
`rubric` and the `patterns`, and against the `ledger` it carries. Report findings only; do not
rewrite the design.

Report a finding for each failed check in the rubric, with the severity it names. In particular:
an `open` ledger entry that reaches the design is `high`; a consequential `inferred` entry that
the owner has not confirmed is `high` (consequential: it changes who does a stage, what a check
requires, or what the owner gets); a departure from the patterns file with no stated reason is
`high`. Judge "too narrow" and "too broad" against the chosen rung in the ledger.

Give each finding a short `title`, a `location` (a stage id or a heading of the document), the
`detail` and a `suggested_fix`. Reuse the id of a finding you were shown before if you still see
it; leave out ones now resolved. Set `coverage.complete` to false, with a note, for anything you
could not judge.
