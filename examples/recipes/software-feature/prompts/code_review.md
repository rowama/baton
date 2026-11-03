# Review the change

Review the change in the `change` input (its `commit_sha` and summary) against the slice in
the `slice` input. You did not write it. You can read the working tree (read-only); use git
to see the change (for example `git show <commit_sha>`). Do not modify any file.

The `slice` input is a planned slice (`title`, `outcome`, `criteria`) or, for a minor
change, the change request itself (`feature_request`).

Check, and report a finding for each problem:

| Check | Typical severity |
|---|---|
| A criterion (or the request) the change does not meet | high |
| A bug: wrong behaviour, unhandled error, data loss, race | high to critical |
| A security problem: injection, secret in code, missing authorization | critical |
| A criterion with no test, or a test that cannot fail | medium |
| Code that ignores the project's conventions or duplicates existing code | low |
| Unrelated changes included in the commit | medium |

For each finding give a `title`, the `location` (`path:line`), the `detail` and a
`suggested_fix`. Report only real problems, not style preferences.

If you were shown earlier findings (`prior_findings`): reuse the id of every finding you
still see, leave out those that are resolved, and check each disposition's evidence
(a claimed fix must really fix it; a rejection must really hold).

Set `coverage.complete` to false, with a note, if you could not check something (for
example, tests that need a network or a service you cannot reach).
