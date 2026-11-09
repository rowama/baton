---
id: 2026-11-windows-supervisor-console
title: "A supervisor on Windows opens no console window"
status: done
level: minor
decisions: []
touches: [design/runtime.md, design/platform-and-security.md]   # §8.7, §15.1
---

# A supervisor on Windows opens no console window

## Request

### Problem

The owner saw Windows Terminal open a tab during a background test run (2026-11-08): `[error 2147942632 (0x800700e8) when launching '…\.venv-run\Scripts\python.exe -m baton.supervisor']`. `0x800700e8` is `ERROR_NO_DATA`: Windows Terminal, the default terminal, was handed a new console for a supervisor that ended before the handoff completed. A longer-lived supervisor would keep a visible window open for its whole worker run, which breaks "invisible when healthy" (§1.1).

The supervisor is started with `DETACHED_PROCESS` (no console). But under a venv, `sys.executable` is the venv's `Scripts\python.exe`, a launcher that starts the base interpreter as its child, and a console program whose parent has no console gets a new, visible one. Measured with a probe that reports `GetConsoleWindow()` and `IsWindowVisible()` from the started interpreter: the venv launcher with `DETACHED_PROCESS` gives a visible console window; the venv launcher with `CREATE_NO_WINDOW` gives none; the base interpreter with `DETACHED_PROCESS` gives none. Baton installed with `uv tool install` runs from a venv too, so owners would see it. Workers are already started with `CREATE_NO_WINDOW`.

The owner chose (2026-11-08) a separate minor change.

### Acceptance criteria

- On Windows, a supervisor started from a venv has no console window; a test fails before the fix and passes after.
- A dispatch still survives its caller's shell (the kill-on-close job test).
- CI passes on all four cells.

## Design

### Doc edits

- `design/runtime.md` §8.7: on Windows the supervisor is a process with its own hidden console, never a visible window.
- `design/platform-and-security.md` §15.1: the same, and why it is not a `DETACHED_PROCESS`.

## Plan

One slice (minor).

## Log

### Fix

- **Commit:** 2026-11-windows-supervisor-console: Start the supervisor with a hidden console
- **Summary:** `supervisor._detached` (dispatch's supervisor and doctor's self-test) uses `CREATE_NO_WINDOW` instead of `DETACHED_PROCESS`, keeping `CREATE_NEW_PROCESS_GROUP` and the job break-away with its fallback. The self-test now also reports its `console_window` (`GetConsoleWindow()`; `None` off Windows).
- **Tests:** new `tests/test_async.py::test_a_supervisor_opens_no_console_window` (a self-test supervisor reports console window 0) failed before the fix in the Windows dev venv with a real window handle (`assert 37948278 == 0`) and passes after. `test_dispatch_survives_its_callers_shell_exiting` still passes on Windows, not skipped. On CI, where the interpreter is not a venv launcher, the new test passes either way; it guards local and installed venvs.
- **Also affected:** `tools/testrun.py start` detaches its background run with the same `_detached`, so on Windows each background run had a visible console window too. The run of dad9302 was recorded `lost` (its process gone, its log empty) while that window was open; closing the window ends the run, which is the likely cause, not confirmed. It was re-run with this fix in place.
- **Repairs 2026-11-windows-running-marker's repair (dad9302, red in the ledger):** the re-run of dad9302 (its own code still starting supervisors as `DETACHED_PROCESS`) took 404 s against about 185 s for earlier Windows runs, and failed four tests: doctor's supervisor self-test "did not start" within its 30 s in `test_api_worker.py::test_doctor_quiet_when_healthy_and_reports_problems`, `test_harness.py::test_doctor_reports_effective_auth_and_passes_preflight` and `test_real_use.py::test_a_healthy_project_makes_no_routine_owner_prompts`, and a queued dispatch's supervisor did not finish within 30 s in `test_work_items.py::test_write_steps_from_two_runs_are_serialized`. Starting 40 self-test supervisors at once from the dev venv: all 40 reported in 9.1 s as `DETACHED_PROCESS` (each opening a console handed to Windows Terminal), against 0.6 s with `CREATE_NO_WINDOW`. The owner's screenshot shows a launch that failed outright during that handoff. A console per supervisor is the likely cause of these four; a failed launch was not reproduced here.
- **Review:** clean
- **Accepted:** <pending the owner>

### Confirmation

- **Summary:** the owner reported (2026-11-09) a cascade of console windows that made the desktop unusable. Those runs started before the fix: the 8- and 16-copy load runs of the real-use scenario (change 2026-11-windows-real-use-timeout), about 150 supervisors per copy, and the background run of dad9302. A run of any commit before this change's fix still opens one window per supervisor.
- **Measured** on the owner's machine at bd0b478. A watcher polled every 20 ms for new visible `ConsoleWindowClass` and `CASCADIA_HOSTING_WINDOW_CLASS` windows and for new `OpenConsole.exe` processes (one per Windows Terminal tab):
  - control, 2 self-test supervisors started as `DETACHED_PROCESS`: 2 windows and 2 tabs;
  - 40 started with this change's flags: 0;
  - the whole suite (1247 passed; 1004 python processes, 345 hidden consoles): 0.
- **CI (2026-11-09):** c5c6a88 (run 42653576739), which holds this fix, is green on all four cells (Ubuntu and Windows, Python 3.11 and 3.14). Locally on Windows with Python 3.11 at e251e85: 1249 passed.
