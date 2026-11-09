---
id: 2026-11-windows-real-use-timeout
title: "The multi-session real-use scenario finishes on the Windows runner instead of hitting its own deadline"
status: proposed
level: minor
decisions: []
touches: []   # a test or runner change; add a design doc if the runtime changes
---

# The multi-session real-use scenario finishes on the Windows runner instead of hitting its own deadline

## Request

### Problem

`tests/test_real_use.py::test_remote_director_completes_a_multi_slice_work_item_across_sessions` fails on the Windows runner (Python 3.11) with `AssertionError: the work item did not finish`: its own 600 s loop deadline expires. It also failed before the 2026-11-fast-tests change (run 42522295546), so it is not caused by parallel runs. It passed on Windows 3.14 in the latest run, so it is borderline, not broken.

The scenario starts about 150 Python processes (34 Director sessions, each running `detect`, `board`, `status` and more, plus supervisors and workers). On Linux it takes 143 s serially on a slow-filesystem venv and 65 s on a fast one. Windows process start-up is slower, and the runner has few cores.

**Unknown, to be measured before fixing:** whether this is only slowness (the scenario needs more than 600 s on the runner), or a stall (a hook or wake that does not fire on Windows, so the loop spins until the deadline).

### Acceptance criteria

- The scenario passes on the Windows runner on both Python versions, and CI shows it on several consecutive runs.
- The Log records the measured time per session on Windows and which cause it was. If it was slowness, the fix reduces the work (for example fewer Director sessions or commands per session, with every behaviour the test asserts still covered, and the Log naming where) or marks the test for a longer deadline on Windows. If it was a stall, the stall is fixed in the runtime and a test fails before the fix.

## Design

### Doc edits

- None expected. If the runtime changes, the design doc for the changed section is added to `touches:`.

## Plan

One slice (minor).

## Log

<One entry per slice, written in the slice's own commit together with its code, tests and design doc edits.>

### Fix

- **Commit:** <subject>
- **Summary:** <cause; what changed>
- **Review:** <findings and dispositions, or "clean">
- **Accepted:** <yes or no, date, the owner's words>
