---
id: 2026-11-diagnostics
title: "Baton records the conditions it works around, keeps them bounded, and doctor speaks up when they become unusual"
status: proposed
level: standard
decisions: ["0094"]
touches: [principles.md, design/layouts.md, design/runtime.md, design/director-interface.md, design/platform-and-security.md]   # §2, §4.4, §8.3, §8.4, §13.1, §13.2, §13.4, §15
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
  - Raw days older than `raw_days` (default 14) are deleted, and raw days are deleted oldest first while the raw total exceeds `raw_max_bytes` (default 64 MiB). The current day is never deleted.
  - Before a raw day is deleted, it is rolled up into `diag/counts/<YYYY-MM-DD>.json`: counts per `(project, code)`, written atomically and idempotently. Counts are kept `count_days` (default 180); a day's file is a few KB.
  - Per process, per code, per day, the first `burst` records (default 100) are written in full; after that, only every 100th, carrying `suppressed: 99`, so counts stay exact while a storm cannot fill the disk.
  - Maintenance (rollup, then prune) runs at most once per UTC day per machine. The first `note` of the day that wins an exclusive-create of `diag/.maintained-<day>` does it, and `doctor` runs it too. A maintenance failure is noted once (`diag.maintenance_failed`) and never raised.
  - Limits are machine settings with these defaults; nothing to configure when healthy.
- **Recorded sites** (slice 2), each with a test:
  - every swallowed exception in `src/baton/` is either noted with its code, or marked expected in a comment saying why (e.g. `ProcessLookupError` in a liveness check is the answer, not a fault); a test lists every broad `except` and fails on one that is neither;
  - cache replays, with the reason (`missing`, `size_mismatch`, `key_mismatch`);
  - capability-version checks skipped for a profile, with the reason;
  - routing exclusions on **every** dispatch (see Decisions: these go into the `worker_selected` event, not the diagnostic channel).
- **`baton diag`** (CLI and MCP tool `diag`): by default, counts per code for the last 7 days next to each code's 30-day daily baseline, with any unusual codes first; `--since`, `--code <prefix>`, `--run`, `--records` (raw records, newest last), `--json`. Exit 0.
- **`doctor`** adds one warning, and nothing when healthy: `diagnostics: N unusual condition(s); see baton diag`, with `diag_unusual [{code, last_7d, baseline_per_day, first_seen?}]` in `--json`. A code is unusual when its last-7-day count is at least `min_count` (default 5) and either more than 3× its 30-day baseline rate, or it has no baseline (first seen). `detect` leaves the warning out, as it does the wake warning (0061).
- The platform SME's evidence for an incident (§12.3) includes the diagnostic records for that run, step and attempt.
- `pytest` green; tests cover: `note` never raising (unwritable home, full disk simulated), concurrent writers, burst suppression keeping counts exact, rollup idempotence, pruning by age and by size, never deleting the current day, the unusual rule, and redaction with sentinel secrets.

### Open questions

- **Event or diagnostic for routing exclusions?** Proposed: add `excluded [{profile, reasons}]` to `worker_selected`'s data. It is deterministic, small, belongs with the run, and travels with the repo to any machine. Does adding an optional field need an event-format version bump (§14.2), or is it a compatible addition?
- **Concept budget (§0 rule 8).** `baton diag` is a new command visible to Directors. Proposed: diagnostics join the "machinery that owners and recipe authors never configure" line in §2, not the concept table, since owners never see them. Agree?
- **Default limits.** 14 days raw / 64 MiB / 180 days of counts / burst 100 / unusual at ≥5 and 3×. These are guesses; tune after real use?
- **Raw worker logs.** `~/.baton/logs/` has no retention today either (no pruning found in `src/`). Bring it under the same maintenance pass (e.g. delete attempt logs of runs finished more than `raw_days` ago), or leave it to a separate change?
- **Worker cost and token telemetry** (attempts record exit code, duration and timeout only) is out of scope here; a separate change, since it needs adapter parsing.

## Design

### Doc edits

- `principles.md` §2: diagnostics added to the line listing machinery owners and recipe authors never configure.
- `design/layouts.md` §4.4: `diag/` in the machine-local tree (`raw/<day>/`, `counts/`, `.maintained-<day>`).
- `design/runtime.md` §8.3: cache replays are noted with their reason. §8.4: `worker_selected` carries the exclusions (pending the open question). New paragraph on the diagnostic channel: what it is for, that it is never a source of truth and never read by the state machine, and the retention rules.
- `design/director-interface.md` §13.1, §13.2: the `diag` call. §13.4: the unusual-conditions warning and its rule.
- `design/platform-and-security.md` §15: diagnostic records are redacted on write; they stay machine-local.

### Decisions

- **0094 (new, proposed): Diagnostics are a separate, machine-local, bounded channel.** They are not events: the event log stays the record of legal transitions, and diagnostics can be written by any process at any time without the state machine. They never decide anything. Their retention is enforced on write, with no daemon. Open until the owner decides.
- Relies on 0061 (doctor warnings that `detect` leaves out), 0084 and 0086 (capability states and version reset, whose silent skips are among the sites recorded).

## Plan

### Diagnostic writer, retention and rollup

- **Outcome:** `diag.note` exists and is safe to call anywhere; storage is bounded; counts survive the raw detail.
- **Criteria:**
  - `note` never raises; per-process files; redaction on write
  - burst suppression keeps counts exact
  - daily maintenance: rollup is idempotent, pruning by age and size, current day kept
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
  - the unusual rule, including first-seen codes; healthy `doctor` stays one line; `detect` unchanged
  - the platform SME's incident evidence includes the matching records
- **Effort:** M

## Log
