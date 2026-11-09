---
id: "0092"
title: "Slice commits are gated by a quick gate; finish commits by a green full run of their exact SHA"
status: accepted
date: 2026-11-08
source: "change 2026-11-fast-tests (owner, 2026-11-08)"
sections: ["§17"]
---

# 0092. Slice commits are gated by a quick gate; finish commits by a green full run of their exact SHA

## Context

Every slice paid for the whole suite, serially, about 6.5 minutes. The owner's requirement was to cut testing time without weakening the tested status of finish commits.

## Decision

- A slice commit needs only the *quick gate*: the tests affected by its changes, minus those marked `slow`, run in parallel. Selection uses `pytest-testmon` where it works with `pytest-xdist`, backed by deterministic fallbacks (a change to any non-`.py` file outside `docs/` selects every non-`slow` test; a docs-only change selects `tests/test_docs.py`).
- After each slice commit the full suite runs in the background on that exact SHA, and the result goes in a ledger keyed by SHA. The next slice commit and the finish check the ledger first.
- A finish commit (`status: done`) requires a green, finished full run of its exact SHA, checked by `tools/testrun.py require-green`. The full suite is never deselected, and CI runs it on every push on both OSes.
- Intermediate slice commits may turn out red. This is accepted: finish SHAs are the tested points, `git bisect` skips slice commits the ledger marks red, and a red result is fixed first in a commit that names the slice it repairs.
