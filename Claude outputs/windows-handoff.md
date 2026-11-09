# Handoff: fix the two Windows-only test failures

Two change docs are waiting, both `status: proposed`, level minor. Neither was caused by the parallel-test work (2026-11-fast-tests); both also failed in serial CI runs before it.

- `docs/changes/2026-11-windows-harness-version-change.md`: `tests/test_harness_tools.py::test_a_new_harness_version_returns_observed_states_to_likely` (Windows, Python 3.11 and 3.14).
- `docs/changes/2026-11-windows-real-use-timeout.md`: `tests/test_real_use.py::test_remote_director_completes_a_multi_slice_work_item_across_sessions` (Windows, Python 3.11; hits its own 600 s deadline).

The failures only reproduce on native Windows, so work on them from a Windows command prompt.

## One-time setup (Windows cmd prompt, not WSL)

A Windows virtual environment already exists at `D:\rob\projects\baton\.venv-win` (Python 3.14.0 from `C:\Python314`). It predates the new test tools, so it needs two more packages. Run each line and check the result.

1. Open a Command Prompt (not a WSL terminal) and go to the repository:

       cd /d D:\rob\projects\baton

2. Check git and Python are there:

       git --version
       C:\Python314\python.exe --version

   Expect a git version and `Python 3.14.0` (or later 3.14). If either command is not found, install it first (git for Windows; Python 3.14 from python.org).

3. Check git knows who you are (needed for commits):

       git config user.name
       git config user.email

   If either prints nothing: `git config --global user.name "Rob Martin"` and `git config --global user.email "rob.w.martin@gmail.com"`.

4. Install the development packages into the existing Windows environment (adds pytest-xdist and pytest-testmon):

       .venv-win\Scripts\python.exe -m pip install -e ".[dev]"

5. Check the install worked:

       .venv-win\Scripts\python.exe -c "import baton, xdist, testmon; print(baton.__file__)"

   Expect a path ending `D:\rob\projects\baton\src\baton\__init__.py`.

6. Delete the test-selection cache, because it was built by the Linux side and must not be reused:

       del .testmondata

   (If it says the file is not found, that is fine.) Do the same, `rm -f .testmondata`, the first time you go back to WSL.

7. Check the two failing tests fail the way CI said (each takes seconds to a few minutes):

       .venv-win\Scripts\python.exe -m pytest tests/test_harness_tools.py::test_a_new_harness_version_returns_observed_states_to_likely -p no:cacheprovider
       .venv-win\Scripts\python.exe -m pytest tests/test_real_use.py::test_remote_director_completes_a_multi_slice_work_item_across_sessions -p no:cacheprovider

   The first should fail with `assert [] == ['claude-a']`. The second may pass locally (it was borderline on the runner); if it does, note how long it took (`--durations=1`).

Python 3.11 is optional: CI's 3.11 cell fails the same tests. Install Python 3.11 and make a second environment (`py -3.11 -m venv .venv-win311`, then the same `pip install -e ".[dev]"`) only if the 3.14 results do not explain a 3.11 failure.

## Rules for working on this tree from both sides

- Use the Windows and WSL sessions one at a time; they share this working tree, and `.git`.
- The `.venv` entry in the repository is a symlink to a WSL environment. Windows cannot use it; leave it alone. Wherever `AGENTS.md` says `.venv/bin/python`, use `.venv-win\Scripts\python.exe`.
- The test-tier tools work from Windows too: `.venv-win\Scripts\python.exe tools/testrun.py quick`, `start`, `status`, `require-green HEAD --wait`. They have only been run on Linux, so if one misbehaves on Windows, say so: that is a bug in `tools/testrun.py`, not in your setup.
- Ask before pushing.

## Prompt to give Claude Code in the Windows prompt

Start it from `D:\rob\projects\baton` (`claude`), then paste:

> Read AGENTS.md, then docs/principles.md and docs/README.md, as the working instructions say. This is native Windows, so wherever the instructions say `.venv/bin/python` use `.venv-win\Scripts\python.exe`; `.venv` is a WSL symlink you cannot use. Delete `.testmondata` before the first `tools/testrun.py quick`.
>
> Two Windows-only CI failures are waiting, each with its own proposed change doc: `docs/changes/2026-11-windows-harness-version-change.md` and `docs/changes/2026-11-windows-real-use-timeout.md`. Do the harness-version one first. The Request in each lists what is known and the hypotheses to test; reproduce the failure here before changing anything, and say which hypothesis the evidence supports before you fix it. Follow AGENTS.md: set each change to `in-progress` (and its register row) when you start it, one commit per fix, the quick gate before each commit, a background full run after it, `require-green` before setting `done`. Do not skip, xfail or delete a test to make it pass, and do not weaken an assertion; if a test is wrong for Windows, fix what it does, and say so in the Log. CI is the final check on all four cells (Linux and Windows, Python 3.11 and 3.14): ask me before pushing, and tell me which CI run to look at.
