## 17. Testing Strategy

- **Unit:** loader and lint, vocabulary, routing and independence, hashing, the state machine, groups, gates and findings, env and PATH construction, classification rules, permissions, publishing and drift.
- **Property-based** (`hypothesis`): packet determinism; required-input removal; any legal event sequence rebuilds to the same state; `foreach` re-expansion is stable for unchanged items.
- **Fake adapter:** scripted good, bad-schema, wrong-hash, blocked, findings, timeout, crash, hang and exit-127 results.
- **Process control:** detachment, process-tree termination and marker liveness on POSIX and Windows.
- **Secret leak:** sentinel secrets through a full run; absent from the working tree and git history.
- **Golden files:** `INSTRUCTIONS.md`, records, summary, `explain` output.
- **Conversation review** (opt-in, with live tests): transcripts of a real Director with a scripted owner, reviewed by the owner against §13.8 *Review*. Not a pass/fail gate in CI: phrasing is judged, not enforced.
- **Live tests** (opt-in): real API models and harness CLIs.

### 17.1 Test tiers

(Decision: [0092](../decisions/0092-two-tier-test-gate.md); timing knob: [0093](../decisions/0093-test-time-scale.md).) Change 2026-11-fast-tests.

- **Quick gate:** the tests a slice's changes affect, minus those marked `slow`, run in parallel. It is the slice-commit gate. `python tools/testrun.py quick` runs it. `pytest-testmon` finds the tests that `.py` changes affect, and the tool never runs less than is safe: with no testmon data, or no record of the last commit the gate passed on, or when any file that is neither under `docs/` nor `.py` has changed, it runs every non-`slow` test; a change under `docs/` adds `tests/test_docs.py`. Code that runs only in child processes is invisible to testmon and is covered by the `slow` tests, which only the full suite runs.
- **Full suite:** every default test, run in parallel (`pytest -n auto --dist worksteal`). It is the finish gate and runs in CI on every push.
- **Background full run:** after each slice commit, the full suite on that exact SHA, with the result recorded per SHA. `python tools/testrun.py start [SHA]` makes a git worktree under the git directory, gives it its own venv in which `baton` is that worktree's `src` (the development install points at the main checkout, and children that tests spawn must not import it), runs the suite on one fewer worker than cores, detached, and records `{sha, tree, state, passed, failed, wall_s, python, os}` in `<git-dir>/baton-testruns/<sha>.json`. The ledger is never committed and is shared by every worktree. `status` lists it (`--red`: red SHAs, for `git bisect skip`). `require-green [SHA] [--wait]` exits 0 only for a finished, green record of that exact commit, and for `HEAD` only on a clean worktree; a missing, running, lost, errored or red record, or a dirty tree, fails. It gates finishing a change.

`slow` marks a test that spawns Baton processes, waits on real time, or measured over 1 s on the baseline. `not_slow("reason")` marks a quick test in a process-spawning file. A test (`tests/test_markers.py`) fails if a test in such a file has neither, so the marking cannot drift. The markers only choose what the quick gate leaves out: the full suite is never deselected, and registered markers are strict (`--strict-markers`).

**Where the interpreter lives matters more than any test change.** On WSL with the repository under `/mnt/<drive>`, a virtual environment on that Windows drive makes every Baton child process import its dependencies over the slow cross-OS file system: `import baton.cli` took 1.6 s (0.2–0.4 s on the Linux file system) and `import litellm` 19 s cold. The full suite took 4 m 36 s there and 2 m 10 s with the environment on the Linux file system (for example `uv venv ~/.venvs/baton && uv pip install -e ".[dev]"`, then `.venv` a symlink to it), with the repository unchanged.

## 19. Definition of Done

- All phases' acceptance criteria pass, on Linux and native Windows.
- README covers:
  - installing the launcher and `baton init`;
  - writing worker profiles;
  - `doctor` and `check`;
  - authoring a neutral recipe (including groups, complexity levels and reviews);
  - vendoring a recipe;
  - adopting an existing project;
  - framing a goal into work items, and choosing the conversational or operator communication style;
  - resuming on a new machine;
  - trialing a new version on a branch.
- Three example recipes ship (§5.7): `fit-check`, `software-feature` (software) and `backyard-project` (non-software).
- Swapping the Director harness or any worker needs only machine-local configuration. New recipes need no runtime changes.
- Principle checks, demonstrated in Phase 16:
  - after setup, a healthy project produces no routine owner prompts;
  - adoption needs exactly one owner decision;
  - every owner touchpoint is a recipe gate, an escalation, the baseline or a framing selection;
  - an owner unfamiliar with Baton can frame a goal and answer a step's questions without meeting Baton's vocabulary, and every answer recorded was confirmed back (Phase 17).
