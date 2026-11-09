---
id: 2026-11-fast-tests
title: "Slices are checked by a fast run of the affected tests; the full suite runs in parallel in the background and still gates every finish"
status: in-progress
level: standard
decisions: ["0092", "0093"]
touches: [design/testing.md]   # §17; also docs/principles.md §0 rule 5, AGENTS.md, pyproject.toml, .github/workflows/tests.yml, tests/, tools/
---

# Slices are checked by a fast run of the affected tests; the full suite runs in parallel in the background and still gates every finish

## Request

### Problem

Agents spend more time waiting on `pytest` than writing code. AGENTS.md requires the whole suite to be green three times over: before a session starts (step 5), at every slice commit ("Each slice is one commit, with `pytest` green"), and at finish. `docs/principles.md` §0 rule 5 says "`pytest` green at every commit". Every slice therefore pays for the full suite, serially.

Measured at fe87ef1 (2026-11-07) on a 2-core Linux sandbox (the owner's machines will differ; slice 1 re-measures):

- 1175 tests collected (collection 3.7 s). Summed test time is about 381 s, so about 6.5 min serial. With `pytest-xdist -n 2` the wall time is 3 min 17 s.
- The time is top-heavy. The slowest 10% of tests take 61% of the time. They are end-to-end tests in `test_async`, `test_api_worker`, `test_director_surface`, `test_harness`, `test_experts`, `test_backyard`, `test_adoption` and `test_groups`, at 2–9 s each.
- Those tests spawn real processes: the baton CLI, supervisors, worker children, git, and fake harnesses. `import baton.cli` costs about 0.3 s per process. `import litellm` costs about 3.0 s, paid by every litellm worker child (`src/baton/worker_runner.py:294`). Several tests also wait on real deadlines and poll (`tests/test_async.py` `_until(..., every=0.05)`).
- Pytest itself is not the cost, so rewriting the tests in another language would not help. The cost is the Python system under test.

The owner's requirement: squeeze every bit of time out of testing that is possible, without compromising tested status for finish (non-slice) commits.

### Acceptance criteria

1. **Finish is never weaker than today.** A change cannot reach `status: done` unless the full suite is green on the finish commit's exact SHA. The full suite is every test that runs by default today, with nothing deselected by the new markers. A check in code enforces this (`tools/testrun.py require-green`); it is not left to the agent remembering. CI still runs the full suite on every push on both OSes.
2. **Nothing is lost from the suite.** The full run collects the same test ids as at baseline (plus new ones), with the same default skips. No assertion is removed to gain speed. A test that is rewritten for speed (slice 5) keeps every behaviour it asserted, and the Log names the test that now covers each one.
3. **Parallel full suite.** `pytest -n auto` passes reliably, with no order or shared-state dependence, on Linux and native Windows, locally and in CI. Slice 1's Log records the baseline: serial vs `-n auto` wall time, and the top 20 durations on the owner's machine.
4. **Fast slice gate.** A slice commit needs only the *quick gate*: the tests affected by the slice's changes, minus tests marked `slow`, run in parallel. The Log records the quick-gate time against the full-suite time for at least one real slice.
5. **Full suite in the background, attributed per SHA.** After each slice commit, the agent starts a full run of that exact SHA in a separate git worktree and goes on working. Results are written to a ledger keyed by SHA. Before committing the next slice and before finishing, the agent must check the ledger. A red result is fixed first, in a commit that names the slice it repairs, and the fix goes into that slice's Log entry.
6. **Session start uses the ledger.** AGENTS.md step 5 is satisfied by a green ledger entry for `HEAD` with a clean worktree. Without one, it runs the full suite as today.
7. **Conflicting rules are rewritten.** AGENTS.md and `docs/principles.md` §0 rule 5 state the two tiers, and nothing in the docs still says "green at every commit".

### Open questions

Each question has a suggested answer for the owner to accept or change.

1. **Intermediate commits may be red.** Under this change a slice commit can turn out red in its background run. Main's history would then contain red commits, though never a red finish. *Suggested:* accept. Finish SHAs are the tested points, and `git bisect` uses `skip` for slice commits the ledger marks red. Record it as a decision.
2. **Affected-test selection tool.** `pytest-testmon` is the obvious candidate. **[VERIFY]**, per §0 rule 1: (a) whether it works together with `pytest-xdist`, (b) whether it tracks non-Python inputs such as `vocab/`, `defaults/`, `formats/`, `builtin/`, `examples/` and `skills/`, and (c) the fact that it cannot see code that runs only in child processes. *Suggested:* use testmon if (a) holds. Back it with a deterministic rule: any change outside `docs/` and outside `.py` files selects every non-`slow` test. A docs-only change selects `tests/test_docs.py`. Child-process paths are covered by `slow` tests in the background run.
3. **Test-only timing knob.** Some `slow` tests wait out real deadlines (overdue extend-then-terminate, hook timing). Making those intervals scalable, for example a `BATON_TEST_TIME_SCALE` env var read by the supervisor, would cut them sharply. But it adds a code path that exists only for tests, which bears on the §2 concept budget and §0 rule 3. *Suggested:* allow it, but only as an undocumented, non-owner-facing env var that defaults to 1 and that `doctor` ignores. If the owner prefers not to have it, slice 5 drops this item.
4. **Fewer real-litellm children.** Each costs about 3 s of import. *Suggested:* keep real litellm in the tests whose subject is the litellm adapter (`test_api_worker`), and use the fake adapter elsewhere wherever litellm is incidental. Nothing changes unless the slice-5 inventory shows that a test's assertions don't depend on it.
5. **Prerequisite: main is red at fe87ef1.** Two failures in `tests/test_resources_refresh.py` (`test_a_refresh_never_changes_the_binding` and `test_new_models_appear_only_with_an_explicit_run`) come from a duplicate route in shipped `known-workers.yaml` (`routes[5]`: provider `openrouter`, adapter `litellm_api`, invocation `openrouter/anthropic/claude-opus-5.5-preview`). AGENTS.md step 5 blocks starting while this stands, and the baseline needs a green suite. *Suggested:* fix it in the change that introduced the data, before this change starts. This change only checks it as a precondition.

## Design

### Doc edits

- `design/testing.md` §17 gains **Test tiers**:
  - *quick gate*: affected tests, not `slow`, run in parallel. It is the slice-commit gate.
  - *full suite*: every default test, run in parallel. It is the finish gate and runs in CI.
  - *background full run*: per slice SHA, with results in the ledger.

  The section defines `slow` (a test that spawns Baton processes or waits on real time, or measures over 1 s on the baseline) and says that the full suite is never deselected.
- `docs/principles.md` §0 rule 5: "Small, tested increments. Tests alongside each module; the quick gate green at every slice commit; the full suite green at every finish commit (§17)."
- `AGENTS.md`:
  - step 5 per criterion 6;
  - "Doing a change": the quick gate per slice, start the background full run after each slice commit, check the ledger before the next slice commit, and the fix-commit rule;
  - "Finishing a change": `tools/testrun.py require-green HEAD` must pass on the commit that sets `status: done`;
  - the exact commands for each tier.

### Decisions

- New record (from open question 1): slice commits are gated by the quick gate; finish commits are gated by a green full run on their exact SHA. Intermediate red commits are accepted and recorded in the ledger.
- New record (from open question 3), only if the owner accepts the timing knob.

### Mechanism (for the Plan; not owner-facing)

- **Parallelism.** `pytest-xdist` is added to `dev`. Runs use `--dist worksteal`, so the long tail of 2–9 s tests doesn't leave workers idle. `-n auto` is not put in `addopts`, so running one test while debugging stays instant. The commands live in AGENTS.md and the tool. The background run uses one fewer worker than cores, so the quick gate running beside it is not starved.
- **Markers.** `slow` is registered in `pyproject.toml`. Slice 2 assigns it from the measured durations and the spawn/real-time rule. `tests/test_docs.py`, or a sibling test, checks that every test in a file listed as process-spawning carries `slow` or an explicit `not_slow` justification. This keeps the rule from drifting as tests are added.
- **Ledger and tool.** `tools/testrun.py` is plain Python with no new runtime dependency. It runs on POSIX and Windows.
  - `start <sha>`: makes a worktree under the git dir, runs the full suite detached, and writes `<git-dir>/baton-testruns/<sha>.json` with `{sha, tree, started, finished, passed, failed: [nodeids], wall_s, python, os}`. Keeping the ledger under the git dir means it is never committed and is shared by every worktree.
  - `status`: one line per recent SHA.
  - `require-green <sha>`: exits 0 only for a green, finished record of that SHA, and with `HEAD` when the worktree is clean.
  - `quick`: runs the quick gate.

  The tool has its own tests, fast and not `slow`, using a tiny fixture repo.
- **CI.** The workflow runs `pytest -n auto --dist worksteal -q -rs`. Its matrix and timeout are unchanged.

## Plan

### Parallel full suite and baseline

- **Outcome:** the whole suite passes under `-n auto` on Linux and Windows, CI uses it, and the baseline is recorded.
- **Criteria:**
  - `pytest-xdist` is in `dev`. CI runs `-n auto --dist worksteal`, green on all four matrix cells.
  - Any test that fails only in parallel is fixed by isolating its state (tmp dirs, ports, env, cwd). A test is never fixed by serializing it, unless the Log justifies it with an `xdist_group`.
  - The Log has the baseline on the owner's machine: collected count, skips, serial wall time, `-n auto` wall time, and the top 20 durations.
- **Effort:** M

### Slow marker

- **Outcome:** `pytest -m "not slow" -n auto` is a fast subset, and the marker can't silently drift.
- **Criteria:**
  - `slow` is registered and applied per the §17 rule. The Log records the `not slow` wall time and its share of the suite.
  - A test fails if a process-spawning test file has an unmarked test without justification.
  - The full suite, with no `-m` filter, still collects exactly the baseline ids.
- **Effort:** S

### Quick gate

- **Outcome:** a slice runs only what its changes can affect, and is never less than safe.
- **Criteria:**
  - `tools/testrun.py quick` selects affected tests (testmon, per open question 2) and applies the fallback rules: non-`.py` changes outside `docs/` select every non-`slow` test; docs-only changes select `test_docs.py`; no prior data selects every non-`slow` test.
  - Tests show that each fallback triggers.
- **Effort:** M

### Background full runs and the finish gate

- **Outcome:** the full suite runs per slice SHA in the background, and finish cannot happen without a green full run of its exact SHA.
- **Criteria:**
  - `start`, `status` and `require-green` work on Linux and Windows, as shown by the tool's own tests.
  - `require-green` refuses on a missing, running or red record, on a SHA mismatch, and on a dirty tree.
  - AGENTS.md, `docs/principles.md` §0 rule 5 and §17 are rewritten per the Design. `test_docs.py` still passes.
- **Effort:** M

### Hotspots in the slow tests

- **Outcome:** the slow tests themselves get faster, with no behaviour left untested.
- **Criteria:**
  - Each of the following is measured and kept only if it saves time:
    - lazy imports on the worker child path (`baton.models` self-import is about 69 ms; whatever else the import profile shows);
    - the fake adapter instead of real litellm where litellm is incidental (open question 4);
    - event-driven waits instead of fixed polling where the test controls the event;
    - the timing knob, if open question 3 is accepted.
  - The Log lists every changed test, the behaviours it asserts, and where each is now covered. The full run collects the same ids and still passes.
  - The Log records the before and after full-suite wall time.
- **Effort:** L

## Log

### Slice 1: parallel full suite and baseline

Prerequisite (open question 5): main was red at HEAD, not at fe87ef1. `test_resources_refresh.py` now passes, but five tests in `tests/test_resources.py` still expected one profile per harness; the 2026-11-cli-model-routes data now also yields one per pinned model. Fixed in its own commit by asserting membership instead of equality.

Baseline on the owner's machine (16 cores, WSL2, repo on `/mnt/d`), 2026-11-08:

- Collected 1237 tests; 1228 pass, 9 skip (all opt-in live tests, `BATON_LIVE*`).
- Serial: 16 m 13 s wall, but only 3 m 27 s of user CPU, so the time is mostly waiting (real deadlines, polling, process start-up on a slow filesystem), which is why parallelism pays.
- `-n auto --dist worksteal`: 4 m 36 s wall (a previous run: 4 m 42 s). About 3.5x faster. The longest single test, `test_remote_director_completes_a_multi_slice_work_item_across_sessions` (143 s serial, 169 s parallel), now bounds the wall time.
- Top 20 durations (serial): 143 s `test_real_use::test_remote_director_completes_a_multi_slice_work_item_across_sessions`; 41 s `test_api_worker::test_two_vendors_complete_fit_check_and_secrets_stay_out`; 28 s `test_versioning::test_two_worktrees_run_two_runtime_versions_and_the_trial_merges`; 26 s and 25 s `test_real_use::test_software_feature_standard` / `_major`; 24 s `test_harness::test_cli_login_and_api_key_steps_in_one_run`; 23 s `test_harness::test_doctor_reports_effective_auth_and_passes_preflight`; 21 s `test_api_worker::test_doctor_quiet_when_healthy_and_reports_problems`; 18 s `test_director_surface::test_two_directors_complete_the_same_recipe_through_mcp_and_cli`; then 12 s down to 7.6 s: `test_async` (hooks, no-wake-path), `test_director_surface` (checkpoints), `test_groups::test_group_run_through_the_cli`, `test_conversation` (three), `test_real_use` (four).
- No test failed only in parallel; no isolation fixes were needed. (One parallel run failed `test_change_register_matches_change_docs` because the owner added `2026-11-not-offered-reasons` mid-run; its register row is added in this commit.)

Changes: `pytest-xdist` in `dev`; CI runs `-n auto --dist worksteal` (the Windows cells will show on first push; not run locally). Decisions 0092 and 0093 recorded and accepted; status `in-progress`.

### Slice 2: slow marker

- `slow` and `not_slow(reason)` are registered in `pyproject.toml` with `--strict-markers`. A script applied them from the slice-1 timings (call + setup + teardown per test, from a `-n auto` run, so a little inflated by load): 283 tests are `slow` (every test over 1 s, plus the live tests); the other tests in process-spawning files carry `not_slow("measured under 1 s")`.
- `tests/test_markers.py` fails if a test in a file that uses `subprocess`, `sys.executable` or the harness/real/version kits (or any `test_live_*` file) has neither mark, or a `not_slow` without a reason.
- Full suite, no `-m` filter: 1230 passed, 9 skipped (1239 collected: the 1238 from before plus the new marker test); no test was deselected or edited apart from decorators.
- Times on the owner's machine, `-n auto --dist worksteal`: `-m "not slow"` 49 s (946 passed, 9 skipped, before the marker test was added) against 4 m 31 s for the full suite, so the quick tier is 18% of the wall time and runs 955 of 1238 tests (77%); `slow` holds about 96% of the measured time.
- §17.1 Test tiers written; README § index updated.

### Slice 3: quick gate

- **[VERIFY] results (pytest-testmon 2.3.0, pytest-xdist 3.8.0):** (a) testmon works with xdist: `--testmon-forceselect -m "not slow" -n auto` built its data in one 77 s run, and `-m` alone disables selection, so `--testmon-forceselect` is needed to combine selection with the marker. (b) Non-Python inputs are not relied on: a change to any file that is neither under `docs/` nor `.py` selects every non-`slow` test, in the tool. (c) Child-process-only code is invisible to testmon by design; the `slow` tests in the background run cover it.
- `tools/testrun.py quick`: changed files are measured against the commit the gate last passed on (kept in the git dir, per worktree), so a non-`.py` change committed since then is not forgotten. Selection falls back as §17.1 says. `tests/test_testrun.py` shows each fallback (no data, no base, non-`.py` change, docs-only, docs with Python, a base commit that no longer exists) and that a dry run records nothing.
- `pytest-testmon` is in `dev`; `.testmondata` is git-ignored.
- **Timing:** first run on this slice (pyproject change, so all non-`slow` tests): 962 passed, 74 s, against 4 m 31 s for the full suite. A one-line change in `src/baton/redact.py` selected 6 tests and took 20 s wall (a trial before the tool existed).

### Slice 4: background full runs and the finish gate

- `tools/testrun.py start | status | require-green` (§17.1). A run is a detached process that makes a worktree under `<git-dir>/baton-testruns/`, runs the full suite (no `-m`; nothing deselected) on `cpu - 1` workers, writes `<sha>.json` and `<sha>.log`, and removes the worktree. States: running, green, red, lost (the process died with no result), error. `require-green` refuses on a missing, running, lost, error or red record, on a record for another SHA, and on a dirty tree when the SHA is `HEAD`; `--wait` waits for a running suite.
- **Found by the first real run (of 9b51bff): red.** The development install points at the main checkout, so a plain worktree would test the wrong code. The run therefore uses its own venv in which `baton` is the worktree's `src` and the other packages are the current environment's. That also exposed two tests, `test_versioning.py::test_launcher_installs_a_missing_version_with_uv` and `test_two_worktrees_run_two_runtime_versions_and_the_trial_merges`, whose nested test venvs took dependencies only from the interpreter's own site-packages; `tests/versionkit.py` now also takes the site-packages the interpreter reaches through a `.pth`. This is the red result 0092 expects the ledger to catch: it was a defect in the slice-4 mechanism's first run, not in slice 3's code, so slice 3's SHA stays red in the ledger and `git bisect skip` covers it.
- Tests (`tests/test_testrun.py`): green and red runs recorded with their failing node ids, worktree removed, a green run not restarted; every `require-green` refusal; an error record is not green; and the background run's venv tests the worktree's own `src` in the test process and in a child with a bare environment.
- AGENTS.md (step 5, Doing a change, Finishing a change), `docs/principles.md` §0 rule 5 and §17.1 are rewritten; no doc says "green at every commit" any more.
- Quick gate on this slice: 964 passed, 77 s (non-Python changes, so every non-`slow` test).
