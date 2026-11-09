---
id: 2026-11-windows-running-marker
title: "A supervisor on Windows survives a Director reading its running marker"
status: in-progress
level: minor
decisions: []
touches: [design/platform-and-security.md]   # §15.1
---

# A supervisor on Windows survives a Director reading its running marker

## Request

### Problem

Found while finishing 2026-11-windows-harness-version-change (its Log has the probes): on native Windows, `tests/test_harness_tools.py::test_absent_on_every_profile_escalates_at_once` fails intermittently with `assert 'passed' == 'escalated'`, 1 to 3 in 60 when repeated on 15 workers, and it failed one background full run.

The cause is in the runtime. The supervisor rewrites the running marker with `os.replace` (`supervisor.write_marker`) right after it starts the worker, while `dispatch` polls the marker every 20 ms (`await_start`). On Windows a file another process has open cannot be replaced, so `os.replace` raises `PermissionError: [WinError 5] Access is denied` and the supervisor dies (`supervisor.py`, the `write_marker` after the worker starts; the supervisor log has the traceback, and the marker folder keeps the `d_<id>.<pid>.tmp`). In isolation, 5262 of 9385 replaces failed against one process reading the file in a loop. The worker runs on unsupervised: no deadline, no intake, no hooks. A waiting Director then reconciles (dead supervisor, result written) and intakes the result through `submit`, which records no tool evidence, so a denied tool passes the step. A Director that ended its turn is never woken, because no completion hook fires. `remove_marker`'s `unlink` has the same exposure.

The owner chose (2026-11-08) a separate minor change for it, fixed before the harness-version change is finished, so that change's finish gets an honest green run.

### Acceptance criteria

- On Windows the supervisor rewrites and removes its marker while another handle has it open; a test fails before the fix and passes after.
- The intermittent failure is gone: the escalation test repeated many times under load on Windows passes, and no supervisor log shows a `PermissionError`.
- CI passes on all four cells.

## Design

### Doc edits

- `design/platform-and-security.md` §15.1: on Windows a file another process has open cannot be replaced or deleted; the supervisor replaces and removes the running marker with a short retry.

## Plan

One slice (minor).

## Log

### Fix

- **Commit:** 2026-11-windows-running-marker: Retry marker replace and remove while a reader has it open
- **Summary:** `supervisor._while_open_elsewhere` retries a change for up to about 2 s (8 tries, 5 ms to 1 s apart) while Windows refuses it with `PermissionError`; elsewhere it re-raises at once. `write_marker` replaces and `remove_marker` unlinks through it. Readers are unchanged (they hold the marker for a moment, and `read_marker` already treats an unreadable file as no marker). Other `os.replace` sites (`store.atomic_write`, `project.py`, `publish.py`, `packet.py`, `worker_runner.py`) were not changed: none of them is known to replace a file that another process polls, and no test or probe showed them failing; they are left until one does.
- **Tests:** new `tests/test_async.py::test_the_marker_is_rewritten_and_removed_while_a_reader_has_it_open` (a thread holds the marker open for 0.2 s while it is rewritten, then while it is removed) failed before the fix on Windows with `PermissionError: [WinError 5] Access is denied` and passes after. `test_absent_on_every_profile_escalates_at_once` repeated 300 times on 15 workers (5 × 60): 0 failures and no supervisor log with `PermissionError`, against 12 failures in 600 runs (12 batches of 40 or 60) before it.
- **Review:** clean
- **Accepted:** <pending the owner>
