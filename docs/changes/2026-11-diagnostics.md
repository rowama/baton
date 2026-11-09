---
id: 2026-11-diagnostics
title: "Baton records the conditions it works around, keeps them bounded, and doctor speaks up when they become unusual"
status: in-progress
level: standard
decisions: ["0094", "0075"]
touches: [principles.md, design/layouts.md, design/runtime.md, design/versioning.md, design/director-interface.md, design/platform-and-security.md]   # §2, §4.4, §8.3, §8.4, §14.2, §13.1, §13.2, §13.4, §15
---

# Baton records the conditions it works around, keeps them bounded, and doctor speaks up when they become unusual

## Request

### Problem

Baton is young, and the conditions most likely to be costing quality or money right now are the ones it handles silently. The event logs (§8.2) record every legal state transition, and raw worker output goes to `~/.baton/logs/` (§8.8), but the runtime's own fallbacks and decisions that do not produce an event leave no trace. `src/` uses no `logging` at all. Found in the code at `e251e85` (2026-11-09):

- **Routing alternatives are recorded only on total failure.** `routing.eligible_workers` computes `eligible` and `excluded` with reasons, but `worker_selected` (`engine.py` `_dispatch_attempt`) records only the chosen identity; exclusions are written only by `escalate_no_worker` when nothing qualifies. A profile that is quietly skipped every time (a capability gone `absent`, a preference, an independence rule) is invisible while another worker carries the load.
- **About 35 broad `except` blocks end in `pass`, `continue` or a default return.** Most are correct fallbacks, but none leaves a trace. Examples:
  - `engine.py` capability-version check: a profile whose environment fails to build (`SetupError`) is skipped with `continue`, so its stale capability states are never reset (0084, 0086).
  - `engine.py` tool-evidence scan: an unreadable worker log returns `[]`, so a denied tool looks like no denial.
  - `engine.py` `harness_version`: a failed `stat` returns `None`, which feeds the version-drift logic.
  - `engine.py` `platform_incident(resolve)`: a `StoreError` while checking the run means the escalated step is silently not retried.
- **Cache replays are unrecorded.** `Store._state` replays a run whenever the cache does not match the log (§8.3). That is correct behavior, but frequent replays would point to concurrent writers or a cache bug, and nobody can see the pattern.

Who needs this: the owner never should (§1.1 *Invisible when healthy*). The platform SME (§12), a Director troubleshooting a run, and the developer do. "Silent when healthy" governs what reaches the owner, not what is recorded.

Storage must stay bounded without a daemon (§0 rule 3). Detail is needed only long enough to troubleshoot recent work; trends need only counts, kept longer, so `doctor` can tell unusual from normal.

### Acceptance criteria

- One function, `diag.note(code, where, **data)`, records a diagnostic. It **never raises** and never blocks work: any failure inside it is swallowed (and counted, see retention).
- Records are written to `$BATON_HOME/diag/`, never to the project or its event logs. Each record carries `ts`, `code` (dotted, as issue codes are), `where` (module:function), `pid`, `project` (root path, when known), `run`/`step_path`/`attempt` when known, and `data`. Every string passes `redact_text` before it is written, so a record can be handed to an SME as is.
- Concurrent writers (Directors, supervisors, the MCP server, on POSIX and Windows) never interleave or lose lines: each process writes its own file, `diag/raw/<YYYY-MM-DD>/<pid>-<rand>.jsonl` (UTC day), so no locking is needed.
- **Retention, without a daemon:**
  - Raw records are kept for the last `raw_days` (default 14) **usage days**, not calendar days: a usage day is a UTC day with at least one raw record on this machine, so idle weeks do not age detail out. Older raw days are deleted, and raw days are deleted oldest first while the raw total exceeds `raw_max_bytes` (default 64 MiB). The current day is never deleted.
  - Before a raw day is deleted, it is rolled up into `diag/counts/<YYYY-MM-DD>.json`: counts per `(project, code)`, written atomically and idempotently. Counts are kept for the last `count_days` (default 180) usage days; a day's file is a few KB.
  - Per process, per code, per day, the first `burst` records (default 100) are written in full; after that, only every 100th, carrying `suppressed: 99`, so counts stay exact while a storm cannot fill the disk.
  - Maintenance (rollup, then prune) runs at most once per UTC day per machine. The first `note` of the day that wins an exclusive-create of `diag/.maintained-<day>` does it, and `doctor` runs it too. A maintenance failure is noted once (`diag.maintenance_failed`) and never raised.
  - Limits are machine settings with these defaults; nothing to configure when healthy.
- **Recorded sites** (slice 2), each with a test:
  - every swallowed exception in `src/baton/` is either noted with its code, or marked expected in a comment saying why (e.g. `ProcessLookupError` in a liveness check is the answer, not a fault); a test lists every broad `except` and fails on one that is neither;
  - cache replays, with the reason (`missing`, `size_mismatch`, `key_mismatch`);
  - capability-version checks skipped for a profile, with the reason;
  - routing exclusions on **every** dispatch: `worker_selected`'s data gains `excluded [{profile, reasons}]` (empty list when nothing was excluded). This is an event field, not a diagnostic: deterministic, small, and it travels with the repo. The field is additive, so no event-format version changes, as for the identity fields (§14.2; 0075); an older event is read as `excluded` unknown.
- **`baton diag`** (CLI and MCP tool `diag`): by default, counts per code for the last 7 usage days next to each code's baseline rate, with any unusual codes first; `--since`, `--code <prefix>`, `--run`, `--records` (raw records, newest last), `--json`. Exit 0.
- **`doctor`** adds one warning, and nothing when healthy: `diagnostics: N unusual condition(s); see baton diag`, with `diag_unusual [{code, last_7d, baseline_per_day, first_seen?}]` in `--json`. A code is unusual when its count over the last 7 usage days is at least `min_count` (default 5) and either more than 3× its baseline rate (per usage day, over the 30 usage days before those), or it has no baseline (first seen). `detect` leaves the warning out, as it does the wake warning (0061).
- `doctor --json` and `diag` report raw worker logs: total size under `~/.baton/logs/` and the age of the oldest attempt log. Nothing is deleted.
- The platform SME's evidence for an incident (§12.3) includes the diagnostic records for that run, step and attempt.
- `pytest` green; tests cover: `note` never raising (unwritable home, full disk simulated), concurrent writers, burst suppression keeping counts exact, rollup idempotence, pruning by age and by size, never deleting the current day, the unusual rule, and redaction with sentinel secrets.

### Resolved questions (owner, 2026-11-09)

- **Routing exclusions** go into the `worker_selected` event, not the diagnostic channel. No format bump: additive field, per the 0075 precedent.
- **Concept budget:** diagnostics are machinery (the §2 line of things owners and recipe authors never configure), not a new concept.
- **Default limits** accepted, with retention counted in **usage days**, not calendar days. Applied to the raw window (14) as decided; the counts window (180) and the unusual rule's windows (7 and 30) use usage days too, for consistency (the agent's reading; confirm or revert at Design).
- **Raw worker logs:** check and report for now (see acceptance criteria); no pruning.
- **Worker cost and token telemetry** stays out of scope (a separate change; needs adapter parsing).

## Design

### Doc edits

- `principles.md` §2: diagnostics added to the line listing machinery owners and recipe authors never configure.
- `design/layouts.md` §4.4: `diag/` in the machine-local tree (`raw/<day>/`, `counts/`, `.maintained-<day>`).
- `design/versioning.md` §14.2: `worker_selected` gains `excluded`, additive, no version change.
- `design/runtime.md` §8.3: cache replays are noted with their reason. §8.4: `worker_selected` carries the exclusions (pending the open question). New paragraph on the diagnostic channel: what it is for, that it is never a source of truth and never read by the state machine, and the retention rules.
- `design/director-interface.md` §13.1, §13.2: the `diag` call. §13.4: the unusual-conditions warning and its rule.
- `design/platform-and-security.md` §15: diagnostic records are redacted on write; they stay machine-local.

### Decisions

- **0094 (accepted 2026-11-09): Diagnostics are a separate, machine-local, bounded channel.** They are not events: the event log stays the record of legal transitions, and diagnostics can be written by any process at any time without the state machine. They never decide anything. Their retention is enforced on write, with no daemon, and counted in usage days.
- Relies on 0075 (additive `worker_selected` fields need no format version), 0061 (doctor warnings that `detect` leaves out), 0084 and 0086 (capability states and version reset, whose silent skips are among the sites recorded).

## Plan

### Diagnostic writer, retention and rollup

- **Outcome:** `diag.note` exists and is safe to call anywhere; storage is bounded; counts survive the raw detail.
- **Criteria:**
  - `note` never raises; per-process files; redaction on write
  - burst suppression keeps counts exact
  - daily maintenance: rollup is idempotent, pruning by usage-day age and by size, current day kept; idle calendar days do not age records out
- **Effort:** M

### Record the silent paths

- **Outcome:** every broad `except` in `src/baton/` either notes a diagnostic or says why it is expected; replays, skipped version checks and routing exclusions are recorded.
- **Criteria:**
  - the audit test fails on an unmarked swallowed exception
  - each recorded site has a test that triggers it and finds its record
  - `worker_selected` carries `excluded` on every dispatch
- **Effort:** M

### `baton diag` and the doctor warning

- **Outcome:** a Director or the developer can see what Baton has been working around, and `doctor` says so only when it is unusual.
- **Criteria:**
  - `diag` summary, filters and `--records`, CLI and MCP alike
  - raw worker log size and oldest age reported by `doctor --json` and `diag`
  - the unusual rule, including first-seen codes; healthy `doctor` stays one line; `detect` unchanged
  - the platform SME's incident evidence includes the matching records
- **Effort:** M

## Log

### Diagnostic writer, retention and rollup

- **Commit:** 2026-11-diagnostics: Diagnostic writer, retention and rollup
- **Summary:** `src/baton/diag.py`: `note` (never raises; failures counted in `diag.failures()`), per-process raw files by UTC day, redaction of every string, burst suppression with a final `flush` at exit so counts stay exact (each record carries `count`; sampled records also `suppressed`), `rollup`, `maintain` (usage-day and size pruning, counts pruning, current day kept) and `maintain_once` (exclusive create of `.maintained-<day>`; failure noted once). `daily_counts()` merges raw days with rollups for the later `diag` and doctor slice. Limits come from the optional `diag.yaml` (the "machine settings" of the criteria). Design edits: principles §2, layouts §4.4, runtime §8.3. `tests/conftest.py` gains an autouse fixture so no test writes to the real `~/.baton`.
- **Tests:** `tests/test_diag.py`: record shape and per-process file; never raising on an unwritable home, a full disk and unprintable data; redaction with a sentinel secret; four concurrent processes; burst suppression keeping counts exact; rollup idempotence; pruning by usage days (including an idle gap), by size, never the current day, and counts by age; once-per-day maintenance; a failing maintenance noted once; UTC day boundaries.
- **Review:** clean
- **Accepted:** <pending the owner>

### Record the silent paths

- **Commit:** 2026-11-diagnostics: Record the silent paths
- **Summary:** The audit counts a handler as swallowing when it neither re-raises, nor uses the exception, nor calls anything; the change's "about 35 broad `except`" was too narrow, since the examples it names catch specific types (`SetupError`, `OSError`). That found 67 handlers in `src/baton/`: 20 now call `diag.note` with a dotted code (`harness.version_*`, `capability.version_check_skipped`, `tool_evidence.*`, `queue.dequeue_run_unreadable`, `incident.resolve_run_unreadable`, `permissions.*`, `sme.*`, `resources.yaml_invalid`, `supervisor.marker_unreadable`, `hooks.config_invalid`, `docs.record_unreadable`, `frame.profiles_unreadable`, `profiles.keyring_failed`, `known_workers.load_failed`), the other 47 say `# expected: <why>` on the `except` line. `worker_runner.py` is a standalone worker process that imports nothing from the runtime, so its one handler is marked expected. Cache replays are noted with `missing`, `size_mismatch` or `key_mismatch` (`_Cache.key_changed` carries the last, since opening a cache of another runtime empties it); a log with nothing in it yet is not noted, or every new run would be. `worker_selected` gains `excluded` on every dispatch (`begin_attempt(excluded=)`); an event without it reads as unknown. Design edits: runtime §8.2, §8.3, §8.4 text, versioning §14.2.
- **Tests:** `tests/test_diag_sites.py`: the audit (fails on an unmarked swallowed exception), a triggering test for each noted site, the three cache replay reasons, `excluded` on a dispatch; `tests/test_routing.py` expects `excluded` in `worker_selected`.
- **Review:** clean
- **Accepted:** <pending the owner>

