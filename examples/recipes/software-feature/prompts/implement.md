# Implement the slice

Implement the slice in the `slice` input in this project's working tree, test it and commit
it. You are working in the real repository: other people's work lives here too.

The `slice` input is either a planned slice (`title`, `outcome`, `criteria`, `effort`) or,
for a minor change that was not planned, the change request itself (`title`, `kind`,
`feature_request`). The original request is in `feature_request`; the design, when there
is one, in `design_doc`.

## When open findings are present

`open_findings` lists what an independent reviewer found in your previous iteration (and
any gate failures, and the owner's note if they gave one). Address every finding: fix it,
or reject it with evidence. Record each one in `dispositions` in `result.json`:
`fixed` with the commit or `file:line` of the fix, or `rejected` with a `file:line` or a
test reference `path::name` showing why it is not a problem. A reviewer will check them.

## Do

1. Read the code you will touch before changing it; follow the project's conventions.
2. Write or update tests that show each acceptance criterion holds.
3. Run the project's tests until they pass. The runtime runs them again as a gate.
4. Commit your change (one or a few commits, clear messages). Leave no uncommitted
   changes behind.

## Do not

- Change files under the packet's `protected_paths`.
- Push, tag, merge or deploy; change unrelated code; disable or skip tests to make them pass.

In `output`, return `commit_sha` (the commit that completes the slice), a `summary` of
what changed, and `tests_added` (test names or paths).
