---
id: 2026-11-marker-read-race
title: "A live supervisor is not judged dead because one read of its running marker failed"
status: done
level: minor
decisions: []
touches: [design/runtime.md, design/platform-and-security.md]   # §8.7, §15.1
manual: [reference/diagnostics.md, reference-notes.yaml]
---

# A live supervisor is not judged dead because one read of its running marker failed

## Request

### Problem

Found by the owner on 2026-11-22 in run `r_20261119_ee96` (baton-recipes, `recipe-builder@7`), step `shape/x5b12127/i4/audit`, dispatch `d_626bb2ad` (`codex-gpt-6-1-terra`). The project is on `/mnt/d`, a Windows drive mounted in WSL2 (drvfs).

- 06:38:27.8Z: the audit was dispatched; the supervisor started and kept its running marker.
- 06:40:00.9Z: a Director call reconciled the run (`Api.reconcile`). `supervisor.liveness` found no marker, so the attempt was recorded `attempt_orphaned {"supervisor": "dead", "marker": false}`, classified `platform` / `supervisor_died` and escalated.
- 06:40:02.5Z: the worker wrote a schema-valid `result/result.json` (10 findings). The attempt log ends at 06:40:08 with a completed turn, and the supervisor log is empty: the supervisor was alive throughout, and exited normally.
- The supervisor's `Api.complete` found the attempt already recorded and returned `None` (`engine.py`, `complete`). The result was dropped silently, with no event or diagnostic. The owner was told the review "finished but Baton lost track of it" and must pay for it again.

Cause: the supervisor rewrites the marker with `os.replace` on every heartbeat (30 s). The reconcile came about 2 s after a heartbeat was due. `read_marker` treats any `OSError` or `ValueError` as "no marker", and §8.7 treats "no marker for a running attempt" as a dead supervisor, so one failed read ends a healthy attempt. A probe on the same drive (one process replacing a file every 10 ms, another reading it in a loop for 8 s) got 1 failed read in about 4,100, `OSError` errno 61 (`ENODATA`). Rare, but a long run with a Director polling `status` or `wait` meets it.

`2026-11-windows-running-marker` fixed the writer's side of the same race (the supervisor retries a replace that a reader blocks). Its Log says "Readers are unchanged… `read_marker` already treats an unreadable file as no marker": that is this gap.

### Acceptance criteria

- A marker read that fails while the marker file exists is retried for a short time (about 1 s). If it still cannot be read, the attempt is reported as running, not judged; a `supervisor.marker_unreadable` diagnostic is recorded either way.
- Reconciliation judges a supervisor dead for lack of a marker only when the marker file is absent, and absent again on a second look after a short pause (longer than one rewrite). A test that makes one read fail mid-run passes after the fix (the attempt stays running and its result is taken in) and fails before it.
- When a supervisor finishes an attempt that was already recorded, Baton records a diagnostic (`supervisor.late_completion`, with the run, step, attempt, dispatch and whether a result was written) instead of returning silently, and `doctor` can report it.
- The marker table in §8.7 and the note in §15.1 say all of this.

## Design

### Doc edits

- `design/runtime.md` §8.7: the running-marker table gets a row for a marker that is present but unreadable (left running, re-read next time). "A running process attempt with no marker counts as a dead supervisor" becomes "no marker on two looks, a short pause apart". A late completion of an attempt that was already recorded leaves a diagnostic.
- `design/platform-and-security.md` §15.1: a read of a file that another process is replacing can fail briefly on Windows and on a Windows drive under WSL, so readers of the running marker retry, as its writer does.

### Manual edits

- `manual/reference/diagnostics.md` and `manual/reference-notes.yaml`: `supervisor.marker_unreadable` now means the dispatch is treated as still running, not as not running; a new row for `supervisor.late_completion`.

## Plan

One slice (minor): `supervisor.read_marker` and `liveness` tell an absent marker from an unreadable one and retry the unreadable one; `Api.reconcile` takes a second look before judging an absent marker; `Api.complete` notes a late completion; tests in `tests/test_async.py` (a reader made to fail once mid-run) and `tests/test_state.py`.

## Log

### Settled marker reads, late completions noted

- **Commit:** 2026-11-marker-read-race: settled marker reads, late completions noted
- **Summary:** `supervisor.settled_marker` reads a marker until it reads, over up to seven looks about 1.2 s apart in all (`SETTLE_DELAYS_S`), and returns `present`, `absent` (no file on any look) or `unreadable` (the file is there but no look could read it). `liveness` uses it. `Liveness` gains `unreadable` and a `dead` property (no live supervisor here, and the marker read or truly absent; an unreadable marker or one from another host is never dead). `read_marker` stays a single look for polling (`await_start`, `wait`'s loop). `Api.reconcile` leaves an unreadable marker's attempt `running` (`unreadable: true`) instead of orphaning it, until the attempt is more than 5 minutes (`Api.UNREADABLE_GRACE`) past its deadline (the last `deadline_extended`, else the dispatch's), so a marker that never reads again cannot hold an attempt for ever; the expert-consultation wait uses `dead`. `Api.complete` notes `supervisor.late_completion` (run, step, attempt, dispatch, run and step state, whether a result was written, exit code) where it used to return `None` without a trace. A retried read is noted as `supervisor.marker_unreadable` with `looks`, `recovered` and the error.
- **Found on the way, fixed here:** `adopt.run_situation`, which `baton detect` runs for every active run, read `live.remote`, a field `Liveness` never had, so `detect` failed with `AttributeError` whenever a supervised attempt was in flight. It now reads `elsewhere` and judges by `dead`, so an unreadable marker is `active_here`, not `orphaned_attempts`.
- **Environment repair, needed for the gate:** typer was upgraded to 0.29.2 in the venv on 2026-11-21 (with an untracked `uv.lock`), after the last green run. Its parameters have no `.type`, so `manual_gen._params` failed and `tests/test_manual_gen.py` failed 5 tests on clean `HEAD`. `manual_gen._type_label` now takes the type from typer 0.29's `type_descriptor` (path, or the annotation's name, `int range` when bounded) and from `.type` on older typer; the generated `reference/commands.md` is byte-identical to the committed one.
- **Design docs:** `design/runtime.md` §8.7 (an unreadable-marker row in the table; settled reads; absent on every look; late completion); `design/platform-and-security.md` §15.1 (the reader's half of the race).
- **Manual:** `manual/reference-notes.yaml` and the generated `manual/reference/diagnostics.md`: `supervisor.marker_unreadable` now says the dispatch is treated as still running; new `supervisor.late_completion`.
- **Tests:** new `tests/test_marker_reads.py` (quick): a read that fails once with `ENODATA` is retried and noted; a marker that stays unreadable is never dead; an absent marker is dead only after every look, with no note; a marker that appears between looks is read; another host's marker is not judged; a dead supervisor with a readable marker is still dead; `read_marker` stays one look; an unreadable marker is judged only past the deadline and grace, an extension counting. `tests/test_async.py` (slow): `test_one_failed_read_of_a_live_supervisors_marker_does_not_orphan_it` (a live supervisor, its liveness read failing once: `running`, no `attempt_orphaned`; then a half-written marker: `running`, `unreadable` in `status`) failed before the fix with `orphaned`; `test_detect_judges_a_running_attempt_by_its_settled_marker` failed before the fix (detect exited on `AttributeError`); `test_a_supervisor_finishing_an_attempt_already_recorded_leaves_a_note`.
- **Review:** self-review of the diff: clean. One gap found and closed before commit: a marker that never reads again would have held its attempt running for ever; it is now judged past the deadline and grace.
- **Accepted:** <pending the owner>
- **Full suite:** green on the slice commit 05ab7a8.
