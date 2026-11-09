---
id: 2026-11-windows-real-use-timeout
title: "The multi-session real-use scenario finishes on the Windows runner instead of hitting its own deadline"
status: in-progress
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

- **Commit:** 2026-11-windows-real-use-timeout: A longer deadline for the scenario on Windows
- **Summary:** Slowness, not a stall, as far as can be measured off the runner (`gh` was not logged in, so the CI logs were not read). Measured on native Windows 11, 16 cores, Python 3.14.0, with a scratch probe timing each Director session and each idle wait in the owner loop: alone, 56 s in all, 17 sessions at 1.7 to 4.0 s (mean 3.0 s), 83 `baton` commands, 10 idle waits of at most 0.5 s (a hook always came within half a second). Under load, all copies passed and none stalled: 8 copies at once took 146 to 155 s each; 16 copies on 15 workers: the 15 that ran together took 316 to 321 s each, and the 16th, which ran after them, 84 s. So the time grows with the load on the machine; the runner has few cores and runs the rest of the suite beside it. A stall was looked for directly: the solo run's idle waits were all short; in the 24 load runs no copy stalled or left a crashed supervisor's `.tmp` marker, and in the 16-copy run no supervisor log showed an error. The one mechanism found that could stall this scenario (a supervisor dying in `write_marker`, so no completion hook fires) is fixed in 2026-11-windows-running-marker. The fix, the owner's choice (2026-11-08): the loop deadline is 1800 s on Windows (3x, from the slowdown measured under load) and stays 600 s elsewhere, so a stall still fails quickly on Linux. No session, command or assertion is removed. These timings were taken while supervisors still opened a console each (fixed in 2026-11-windows-supervisor-console); re-timed alone after that fix: 51 s, 17 sessions at 1.5 to 3.9 s (mean 2.65 s), idle waits of at most 0.5 s. About 10% faster, so the deadline stays. (A first load run with `--basetemp` under a long scratch path did stall: packet paths passed Windows' 260-character limit. That came from the probe setup, not the runner. With pytest's default temp dir the longest path was 213 characters, about 239 with the runner's user name.)
- **Tests:** the scenario passes on Windows locally. The acceptance criterion of several consecutive green CI runs on both Windows cells is left to the owner's pushes.
- **Review:** clean
- **Accepted:** <pending the owner>
- **CI (2026-11-09):** the first runs with the longer deadline. f497248 (run 42652200877): Windows 3.11 green; Windows 3.14 finished the work item but failed the next assertion, `len({s["pid"] for s in logged}) == len(logged)` (17 sessions, 16 pids). c5c6a88 (run 42653576739): green on all four cells (Windows 3.11 in 911 s, 3.14 in 883 s). Locally on Windows with Python 3.11 at e251e85 (scratch venv, clean worktree): 1249 passed.
- **Repair of the fix slice (red on f497248's CI run):** the deadline held; the test's check that every Director session is a separate process used the pid, and Windows hands a finished process's pid to a new one at once, so two of the 17 sequential sessions logged the same pid. The test was wrong, not the runtime: each session is its own `subprocess.run` of a fresh interpreter. Fix, in the test only: `tests/fakes/remote_director.py` logs a fresh `session` id (`uuid4`) beside its pid, and the assertion counts those ids. Every other assertion is unchanged. The scenario passes locally on Windows (65 s). The pid reuse was not reproduced locally; it is a property of Windows pid allocation, not a timing this test controls.
