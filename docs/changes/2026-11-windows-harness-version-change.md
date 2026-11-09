---
id: 2026-11-windows-harness-version-change
title: "A harness upgrade is noticed on Windows, so observed capability states return to likely"
status: proposed
level: minor
decisions: ["0086"]
touches: [design/workers.md]   # §6.1, §6.3: only if the fix changes what "an upgrade is seen" means; otherwise a test fix
---

# A harness upgrade is noticed on Windows, so observed capability states return to likely

## Request

### Problem

`tests/test_harness_tools.py::test_a_new_harness_version_returns_observed_states_to_likely` fails on native Windows, on Python 3.11 and 3.14. It passes on Linux. It failed in CI before the 2026-11-fast-tests change (runs 42522295546 and 42529519383), so it is not caused by parallel runs.

The test records a profile's `web_access` as `absent` (observed, harness version 9.9.0), upgrades the fake CLI (writes `version.txt`, touches the file `claude`, and moves its mtime 5 s ahead), then asks which profiles are eligible. It expects `claude-a`, whose observed state is stale for the new version, to be eligible again and forgotten. On Windows `eligible` returns no profile at all, so the version change is not noticed.

`harness_version` (`src/baton/engine.py`, around line 1056) caches `<exe> --version` per executable file `(path, mtime, size)` (Decision [0086](../decisions/0086-capability-absent-reroutes.md)). **Hypotheses, to be checked before fixing:**

1. On Windows the fake CLI that `install_fake` writes is a `claude.cmd` (or similar), so the test's `touch` and `utime` on a file named `claude` change nothing the cache looks at. This would be a test defect, fixed by touching the real executable.
2. The Windows path of the version probe (spawning the `.cmd`, parsing its output, or the cache key) does not see a changed version file. This would be a runtime defect: a real harness upgrade on Windows would go unnoticed, and a profile would keep a stale `absent`.

### Acceptance criteria

- The test passes on native Windows (Python 3.11 and 3.14) and on Linux, and CI shows it.
- If the cause is a runtime defect, a test fails before the fix and passes after it on Windows, and the Log records which hypothesis was true.

## Design

### Doc edits

- None expected if the cause is the test. If the runtime changes, `design/workers.md` §6.3 (the sentence on `harness_version` cached per executable file) is updated.

## Plan

One slice (minor).

## Log

<One entry per slice, written in the slice's own commit together with its code, tests and design doc edits.>

### Fix

- **Commit:** <subject>
- **Summary:** <which hypothesis was true; what changed>
- **Review:** <findings and dispositions, or "clean">
- **Accepted:** <yes or no, date, the owner's words>
