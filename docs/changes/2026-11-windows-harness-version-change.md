---
id: 2026-11-windows-harness-version-change
title: "A harness upgrade is noticed on Windows, so observed capability states return to likely"
status: in-progress
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

- **Commit:** 2026-11-windows-harness-version-change: Upgrade the executable the profile runs
- **Summary:** Hypothesis 1 was true: a test defect, not a runtime one. Reproduced on native Windows 11 (Python 3.14.0): the test failed with `assert [] == ['claude-a']`. Tracing `harness_version` during the test showed both calls probing `bin-a\claude.cmd` (the file `install_fake` writes on Windows, and the profile's `executable`) with the same mtime and size, so the cache rightly returned `9.9.0`; the test's `touch` had created a separate, empty file `claude` that nothing runs. Hypothesis 2 was ruled out directly: on Windows, after `version.txt` changes, `harness_version(claude.cmd)` still returns `9.9.0` until the `.cmd` file's mtime moves, and then returns `9.10.0`, so spawning the `.cmd`, parsing its output and the `(path, mtime, size)` key all work and a real upgrade is noticed. The fix is in the test only: `tests/harnesskit.py` gains `fake_exe(bin_dir, name)`, the file `install_fake` writes (`<name>.cmd` on Windows, `<name>` on POSIX), which `install_fake` now uses too; the test touches and moves the mtime of that file. No assertion changed. No runtime or design doc change (§6.3 stands as written).
- **Tests:** `tests/test_harness_tools.py` passes on native Windows (7 passed); Linux and Python 3.11 are left to CI.
- **Review:** clean
- **Accepted:** <pending the owner>
- **Repair of the fix slice (f1b940f, red in the ledger):** the first background full run on native Windows failed to collect `tests/test_director_surface.py` with `ModuleNotFoundError: No module named 'pywintypes'` (1216 passed, 19 skipped, 1 error). Not caused by this change's test edit: the run venv that `tools/testrun.py` builds (2026-11-fast-tests slice 4) put the current environment's site-packages on `sys.path` as plain `.pth` lines, and Python reads `.pth` files only in site dirs, so pywin32's own `pywin32.pth` (which adds `win32` and `win32\lib`, where `pywintypes` lives) was never read; `mcp` imports `pywintypes` on Windows. Earlier greens were all WSL runs, where no package relies on a nested `.pth`. `_make_run_env` now writes each borrowed folder as `import site; site.addsitedir(...)`, after the worktree's `src`, and takes the folders as an optional `deps` argument. New test `tests/test_testrun.py::test_the_run_venv_reads_the_pth_files_of_the_environment_it_borrows` (a site dir whose `.pth` adds a subfolder, pywin32's shape) failed before the fix with `No module named 'nested_mod'` and passes after; `test_the_background_run_tests_the_worktrees_own_source_even_in_children` still passes, so the development install's `.pth` entry for the main checkout does not take over.
- **Repair of the repair (79f87e9, red in the ledger):** two failures. (1) `tests/test_markers.py`: the new test's `import subprocess` makes `test_testrun.py` a process-spawning file, so its eleven quick tests (each under 0.6 s here) now carry `not_slow("measured under 1 s")`; the new test stays `slow` (it builds a venv). The quick gate did not select `test_markers.py`, because it reads test files as text and testmon cannot see that. (2) `tests/test_harness_tools.py::test_absent_on_every_profile_escalates_at_once` failed intermittently, not because of this change: 1 to 3 in 60 when repeated on 15 workers here. Probing showed the supervisor dying in `write_marker` (a leftover `d_<id>.<supervisor pid>.tmp` beside the marker, the supervisor PID dead, and once no `worker_pid` yet): on Windows `os.replace` onto a file another process has open fails with `PermissionError` (5262 of 9385 replaces failed against one reading process), and the waiting Director reads the marker every 0.1 s. `reconcile` then intakes the result through `submit`, which records no tool evidence, so the step passes. That is a runtime defect in the supervisor, outside this change's Request; where it is fixed is for the owner (asked 2026-11-08).
