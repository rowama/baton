## 8. Runtime

### 8.1 The state machine

```
blocked_on_deps → ready → dispatched → running → submitted → verifying → passed
                    ↑          │          ├→ timed_out ──────────┤ (classified)
                    │          └──────────┴→ orphaned ───────────┤
                    └── retry (attempt+1) ◄──────────────────────┤ gate failed, attempts < max
                                                                 └→ escalated
ready            → escalated  (no eligible worker, §8.4)
escalated        → ready (after a decision) | abandoned | verifying (a waiver of the held failed gate, §9.3)
verifying        ⇄ awaiting_human (human gate)
blocked_on_deps  → skipped    (complexity level)        skipped → blocked_on_deps (approved re-triage)
ready            → skipped    (approved re-triage; only a step never dispatched)
blocked_on_deps  → imported   (adoption seed)
passed|imported  → superseded (revised)                 passed|imported → stale (an upstream step was revised)
superseded       → ready      (the revised step's new attempt)
stale            → ready | passed (re-run when dispatched, or confirmed by a human decision)
```

- **Review steps** (§9.1) have the path `<step_path>~review` (`~review.<gate index>` when the step has several review gates) and follow the same machine. While one runs, the reviewed step stays `verifying`. Each attempt of the reviewed step gets its own review: a passed review is marked `stale` and readied again.
- `escalated → verifying` (`verification_started`) is legal only for a step holding an attempt (attempt ≥ 1, carried on the event).
- `skipped` and `imported` satisfy `depends_on`; `stale` and `superseded` do not. A group's state is derived, never stored (§8.5).
- A `stale` step is never readied automatically (Decision: [0032](../decisions/0032-stale-steps-not-auto-readied.md)). Once its dependencies are satisfied it is **runnable**: it is listed with the ready steps, and dispatching it records `step_ready` (`rerun`) before the attempt; or the owner confirms it unchanged (`decide <step> confirm`), which records the decision and a `step_passed` repeating the earlier accepted result (`confirmed`). Confirming is refused until its dependencies are satisfied again. It is not a pending owner decision.
- `escalated` reasons: attempts exhausted, `blocked` result, no eligible worker, iteration limit, platform failure, a read or none step that changed the working tree (`workspace_modified`, §6.3).
- Only `engine.py` performs transitions; each appends exactly one event. Illegal transitions raise. Test every edge.
- A step with no events is `blocked_on_deps`. Attempt numbers are assigned at `dispatched` (previous + 1); `worker_selected` and `packet_built` carry that next number, events about the attempt in flight carry the current one. The attempt budget (`max_attempts`, recorded in `run_started`) restarts whenever a step becomes `ready` other than by retry.

| Edge | Event |
|---|---|
| → `ready` (any source) | `step_ready` |
| `ready` → `dispatched` → `running` → `submitted` | `dispatched`, `step_running`, `result_submitted` |
| `submitted` → `verifying` | `verification_started` |
| `verifying` → `awaiting_human` | `human_gate_opened` |
| `awaiting_human` → `verifying` | `gate_passed` / `gate_failed` (the human gate's outcome; `human_decision` itself is a fact, never a transition) |
| → `passed` | `step_passed` (from `stale`, with the confirming decision in `data`) |
| → `timed_out` / `orphaned` / `escalated` / `abandoned` | `step_timed_out`, `attempt_orphaned`, `step_escalated`, `step_abandoned` |
| → `skipped` / `blocked_on_deps` (from `skipped`) / `imported` | `step_skipped`, `step_unskipped`, `step_imported` |
| → `superseded` / `stale` | `step_revised`, `step_stale` |

Some step events record facts without a transition but are legal only in certain states (`worker_selected`, `packet_built` in `ready`; `deadline_extended` in `running`; `gate_passed`, `gate_failed`, `result_rejected`, `findings_recorded`, `protected_path_modified` in `verifying`; `gate_waived` and `finding_dispositioned` are facts recorded in any state; `failure_classified` after an attempt ends; `dispatch_queued` in `ready`; `dispatch_dequeued` in any state, also after the run ends). Run level: `run_started` is first and once; after `run_completed` or `run_abandoned` no step event is accepted.

### 8.2 Events (the single list)

Every event: `format` (`baton-events/N`), `seq`, `ts`, `run_id` (`null` in the project log), `step_path`, `attempt`, `type`, `actor` (`runtime` / `human` / `worker[:<profile>]` / `director[:<id>]`), `data`, `prev_sha256`, `sha256`.

Each event is one line of canonical JSON (sorted keys, no insignificant whitespace, UTF-8, LF). `sha256` is the SHA-256 of the event's canonical JSON without the `sha256` key; `prev_sha256` is the previous event's `sha256` (`null` first); `seq` starts at 1 with no gaps. Any edit, deletion, insertion or reordering is detectable, including an edit to the last event; only truncation of whole trailing events needs an outside anchor (the checkpoint commits, §10.1). The per-event `format` lets one log hold several versions after a migration (§14.2).

| Area | Event types |
|---|---|
| Run | `run_started` (work item, recipe, versions, branch, `max_attempts`), `run_completed`, `run_abandoned` |
| Leases | `lease_claimed`, `lease_renewed`, `lease_taken_over`, `lease_released` |
| Steps | `step_ready`, `dispatch_queued`, `dispatch_dequeued`, `worker_selected` (`profile`, `creator`, `model_id?`, `provider?`, `model?`, `adapter`, and `vendor` equal to `creator`: the identity and route at dispatch, §8.4), `packet_built`, `dispatched`, `step_running`, `result_submitted`, `verification_started`, `result_rejected`, `gate_passed`, `gate_failed`, `human_gate_opened`, `step_passed`, `step_escalated`, `step_abandoned`, `step_timed_out`, `attempt_orphaned`, `failure_classified`, `deadline_extended` |
| Tailoring | `complexity_set` (`level`, `approval` `auto`\|`owner`\|`baseline`, `reasons?`, `decision_seq?`), `step_skipped` / `step_unskipped` (`level`, `cause` `complexity`\|`retriage`), `retriage_requested` (`reason`, `previous_level`), `retriage_applied` (`level`, `previous_level`, `decision_seq`, `skipped`, `unskipped`, `pre_retriage`) |
| Groups | `group_expanded` (on the group path: `mode` `foreach`\|`once`\|`skip`\|`single`, `source`, `source_sha256`, `items` `[{id, sha256, content_sha256, title?}]`, and on re-expansion `kept`/`changed`/`added`/`superseded`), `iteration_started` (on the instance path: `iteration`, `from`, `budget_base`), `iteration_limit_reached` (on the instance path: `iteration`, `max_iterations`, `judged`, `judged_seq`, `reasons`) |
| Corrections | `step_revised`, `step_stale` |
| Reviews | `findings_recorded` (on the recording step: `line`, `gate`, `findings` `[{id, severity, title, location?, status, reopened?, carried?}]`, `counts`, `open`, `blocking`, `partial`, `coverage_notes?`, `reviewed_commit?`, `previous_seq?`, `resolved?`, and for a review gate `review`, `review_attempt`, `reviewer`), `finding_dispositioned` (on the recording step: `line`, `finding`, `evaluation_seq`, `disposition`, `evidence?`, `decision_id?`, `by` `worker`\|`director`\|`owner`, `provisional?`), `gate_waived` (`gate`, `reason`, `decision_id`, `scope` `held`\|`next`, `attempt?`, `judged_seq?`), `protected_path_modified` (`changed`, `mode`) |
| Human | `human_decision`, `human_revision_ingested` (on the step: `artifact`, `path`, `sha256`, `revision`, `feed` `revision_inputs`\|`dependents`, `possibly_stale`, `decision_id`, `source` `drift`\|`sme`) |
| Deliverables | `artifact_published` (on the step: `artifact`, `path`, `sha256`, `attempt`, `passed_seq`, `unchanged?`, `kept?`, `overwrote?`, `alternate?`, `revision?`, `decision_id?`), `drift_detected` (on the step: `artifact`, `path`, `published_sha256`, `current_sha256`) |
| Adoption | `situation_detected` (adoption run: the `detect` result, scope counts), `research_recorded` (§11.1), `step_imported` (§11.4), `baseline_established` (§11.5) |
| Framing | `framing_selected` (framing run: `decision_id`, `selected`, `runs` `[{part, run, recipe}]`, `gaps` `[{part, reason}]`, `plan {path, sha256}`: the process plan's rendering, §11.6); `framing_started_later` (framing run, after it completed: `part`, `run`, `recipe`, `plan`, `vendored?`: a part started with `start --from-plan`); `run_started.framing {run, part}` on each run it starts |
| Answers | `human_decision {kind: answers, answers: [{id, answer, owner_words}], note, decision_id}` (on the step whose questions were answered; precedes the retry it feeds, §13.8) |
| Experts | `sme_requested` (`consultation`, `turn`, `subject`, `mode` `relay`\|`handoff`, `question`, `refs`/`auto`/`attachments` `[{ref, label, path, sha256}]`, `worker`, `creator`, `model_id?`, `provider?`, `model?`, `adapter`, `vendor`, `packet_sha256`, `dispatch_id`, `contact?`; a handoff: `path`, `handoff_sha256`), `sme_answered` (`consultation`, `turn`, `status` `answered`\|`rejected`\|`failed`\|`blocked`, `answer_sha256`, `result_sha256`, `confidence`, `sources_used`, `requested_refs`, `suggests_retriage`, `awaiting?`, `artifacts?`, `reasons?`, `classification?`), `sme_promoted` (`consultation`, `turn`, `target`, `note`, `content_sha256`, `decision_id?`, `path?`) |
| Machinery | `completion_hook_fired`, `completion_hook_failed`, `checkpoint_committed`, `permission_used` / `permission_requested` (project log: `action`, `rule`, and for a push `category`, `remote`, `branch`, `upstream`, `commits`, `paths`, `outside_docs?`, `unverified?`; for a Director action `detail?`; `decision_id` when the owner approved an `ask`), `migrated` (run-level, any run state; `family` `events`\|`lock`\|`recipe`, `from`, `to`, `path`; for a log, in that log: `upto_seq`, `upto_sha256`, `sha256` of the upcast copy; for the lockfile or a vendored recipe, in the project log, a recipe also `recipe`, `sha256`, `source_sha256`; §14.2) |
| Project log | `human_decision {kind: permission, action, decision: approve, note, decision_id}` (an owner's approval of an `ask` action, §13.7), `human_decision {kind: vendor, recipe, decision: approve, note, decision_id, flags}` (§14.2), `human_decision {kind: notes, decision: yes|no, accepted, note, decision_id}` (the owner's answer to the notes-file offer, §13.1), `note_recorded` (`text` redacted, `at`, `path`: an owner's note appended to the notes file), `platform_fact_recorded` (`fact`, `source`, `observed?`), `platform_incident_opened` (`incident`, `run`, `step_path`, `attempt`, `class`, `code`, `message`, `refs`), `platform_incident_resolved` (`incident`, `fix`, `retried`), `process_feedback` (`kind`, `text`, `run?`, `step_path?`, `qualified?`, `gate?`, `informed_owner?`), `capability_observed` (`profile`, `capability`, `state`, `previous`, `evidence`, `run`, `step_path`, `attempt`, `harness_version?`: a dispatch changed a capability's state, §6.1), `step_skip_recorded` (`feedback_seq`, `run`, `step_path`, `gate`, `blocking`, `surfaced`, `informed_owner`); expert events of consultations without a run (§12.1) |

### 8.3 Store

- Run directory `.baton/runs/<run_id>/`: `events.jsonl`, `cas/<sha[:2]>/<sha>` (atomic writes), `steps/`, `sme/`, `docs/`. Project log: `.baton/project/events.jsonl`.
- SQLite (`.baton/cache/state.db`) is a derived cache; `store.rebuild()` replays events; events always win. Every append is checked by the state machine before it is written, so a log holds only legal sequences; the cache is used only while it matches the log's size, otherwise the run is replayed. It is keyed on the runtime version and event format that built it, so another runtime on the same worktree (§14.1) replays the logs itself.
- Large binaries are expected in Git LFS (rules written by `baton init`).

### 8.4 Routing and independence

`eligible_workers(run, step)`:
1. Load profiles (machine, then `.baton/workers.local.yaml`).
2. Keep profiles with all required capabilities, sufficient tier and numeric minimums (`repo_workspace` for write steps, `workspace_read` for read steps). A claimed capability whose state on this machine is `absent` counts as missing, and the exclusion says when and how it was observed and how to reset it (§6.1; Decision: [0084](../decisions/0084-capability-states.md)). First, a harness profile's states observed under another harness version go back to `likely` (the version is the CLI's `--version`, cached per executable file; the owner's own declarations stay; Decision: [0086](../decisions/0086-capability-absent-reroutes.md)).
3. Apply **independence**: if the step or gate declares `independence: {from_step, level}`, exclude profiles that match the worker of `from_step`'s current result at that level (`different_profile` | `different_model` | `different_vendor`). Self-review is refused unless waived (§9.3).
4. Order by `.baton/preferences.yaml` (`prefer.by_step`, `prefer.by_capability`, `exclude`). Preferences reorder or exclude only; they never add an ineligible profile. The profiles no preference names follow with more of the step's required capabilities `verified` first, then by name. Each eligible entry shows its required capabilities' states (`capabilities`), and a reason line names the verified ones.
5. Return the ordered list with reasons and exclusion reasons. Empty → `escalated` (`no_eligible_worker`; §18 #2: the run never fails for this). `eligible` records the escalation for a ready step; the owner's `decide <step> retry` readies it again once a capable profile exists.

The worker of a result is read from the run's record, not from the current machine or the known-workers data: `worker_selected` records the profile's identity and route as they were at dispatch (§6.1). An event from before these fields has only `vendor` and `model`: its creator is the vendor and its model identity is unknown, never guessed from the invocation string (Decision: [0075](../decisions/0075-model-identity-separate-from-route.md)). Two workers match (are not independent) when (Decision: [0076](../decisions/0076-unknown-identity-not-independent.md)):

| Level | Match when |
|---|---|
| `different_profile` | the same profile |
| `different_model` | the same profile; both `model_id`s known and equal; or either unknown while the creators are not known to differ |
| `different_vendor` | the same profile; the same creator (case-insensitive); or either creator unknown |

An unknown identity is never proof of independence, and a route is not a model: the same model reached directly and through OpenRouter satisfies neither level, while two models of one creator satisfy only `different_model`. An exclusion that rests on an unknown identity says so and names the fixes (set `model_id`, §6.1, or the one-dispatch waiver, §9.3). Eligibility lists, `doctor`'s profile reports and SME eligibility show each profile's creator, model identity and provider. `dispatch` refuses a worker outside the eligible set, with its exclusion reasons. `by_step` keys are step ids or step paths.

### 8.5 Groups at runtime

Implemented in `groups.py` (derived view) and `engine.refresh` (events). Paths: `<group>/<instance>/i<n>/<step>`; an instance's own path is `<group>/<instance>`.

- **Expansion:** when the group's dependencies are satisfied and the `foreach` source passes, the runtime creates one instance per item in array order (`group_expanded`, with item ids and content hashes; each item stored in CAS). A skipped source follows `foreach_if_source_skipped`. Instances start (`iteration_started`, iteration 1) in item order as `concurrency` allows.
- **Re-expansion** whenever the source's accepted output differs from the one the last expansion was built from (after a revision), matched by the runtime-assigned ids the worker echoed (§5.8): same id and content → kept; same id, changed → the instance's accepted steps (as of its current iteration) become `stale` and re-run in place; id not echoed → `superseded` (its steps never run again and its decisions are no longer pending); item without an id → added with a new id. Unknown or duplicated ids are rejected at intake.
- **Iteration:** when a judge's gate fails (§5.4), the iteration ends and, below `max_iterations`, `iteration_started` begins the next one at `repeat_from` with `group.previous_iteration.findings`. Earlier iterations stay in the record. At the limit, `iteration_limit_reached` escalates the instance: a pending decision with `ref` = the instance path and options `retry` (a fresh budget of `max_iterations`, starting at `repeat_from`; the note reaches the next iteration as `owner_note`) or `abandon` (the instance is abandoned, so the group cannot pass; the owner revises the plan or abandons the run). Accepting the work as is arrives with waivers (§9.3).
- **Current work:** a step inside a group is dispatchable only when every enclosing instance is live and started, the path belongs to the instance's current iteration, each enclosing group's dependencies are met and its expansion is up to date, and the iteration has not been ended by a judge.
- **Aggregate state:** an instance is `not_started`, `active`, `escalated` (iteration limit), `passed` (every step of its current iteration satisfied, no failed judge), `abandoned` or `superseded`. The group is `blocked_on_deps` until expanded, `skipped` (source skipped with `skip`), `passed` when every live instance is `passed` (an empty `foreach` passes at once), else `active`. Status and the run summary describe it plainly ("3 instances: 1 passed, 1 active, 1 not started; Logout: iteration 2 of 3").

### 8.6 Packet builder (the critical module)

`build_packet(run, step_path, profile)`:
1. Assert dependencies are satisfied and the profile is eligible (re-checked here, never trusted from the caller).
2. Resolve every input. If any required input is unresolvable, raise `HandoffError` listing **all** missing inputs; write nothing.
3. Copy blobs from CAS (never from published copies); render `INSTRUCTIONS.md`; copy the output schema.
4. Hash, write `manifest.json`, make the packet read-only; record `worker_selected` and `packet_built`.

Property tests: same state + same profile ⇒ same `packet_sha256`; removing any required input ⇒ `HandoffError`.

### 8.7 Dispatch, supervision, completion and timeouts

- **Dispatch** returns once the worker has started, with its dispatch id, effort and deadline (`dispatch(…, wait=true)` / `--wait` blocks until the outcome is recorded). A small **per-dispatch supervisor** (no daemon) is started detached from the caller (POSIX: new session; Windows: a detached process in its own group that breaks away from the caller's job object, falling back to staying in the job when the job forbids breaking away), so a Director's shell ending does not affect it. It receives the worker's constructed environment through a pipe (never written to disk), starts the worker, keeps the running marker, enforces the deadline, runs intake when the worker exits, fires hooks, writes records, makes the checkpoint commit and exits. The supervisor is the runtime finishing work a Director started: it writes events as `runtime` / `worker:<profile>` under a short per-run file lock (`.baton/cache/locks/`) and needs no lease. `wait(run, dispatch_id?, timeout?)` lets an attached Director block until completion. **Manual workers** get no supervisor and no timeout; their packet deadline is informational.
- **Running marker** `.baton/cache/running/<dispatch_id>.json`: host, supervisor and worker PIDs, step path, attempt, started, deadline (and whether it was extended), heartbeat (every 30 s). For `read`/`none` steps the tree snapshot taken before the worker started is kept beside it. Removed after intake and hooks.

| Marker | Process (supervisor) | Result | Meaning |
|---|---|---|---|
| present | alive | – | running (overdue if past deadline) |
| present | dead | written | missed completion → finish intake now |
| present | dead | none | died silently → `orphaned`, classified `platform` / `supervisor_died`, escalated |
| absent | – | intake done | finished |

  Reconciliation (`resume`, `wait`) applies this table on this host (a marker from another host is reported, not judged). A worker still alive under a dead supervisor is terminated first. A running process attempt with no marker counts as a dead supervisor. Hooks fire for outcomes recorded by reconciliation too.
- **Completion hooks** fire after intake on every outcome (passed, gate failed, needs human, timed out, failed), and with outcome `overdue` when a deadline is extended. Project-level (non-secret) hooks go in `project.yaml`; machine-level hooks (may reference `secret:` values, substituted shell-quoted at execution, never logged) go in `~/.baton/hooks.yaml`. When both are configured, both fire. A hook is a shell command line.
  ```yaml
  hooks:
    on_complete: "curl -fsS -m 20 -X POST -d run=$BATON_RUN_ID -d step=$BATON_STEP_PATH -d outcome=$BATON_OUTCOME secret:director_wake_url"
    on_needs_human: ""         # optional; falls back to on_complete
    on_platform_failure: ""    # optional; e.g. wake the platform SME; falls back to on_complete
  ```
  Which hook: a `platform` classification uses `on_platform_failure`; a step now waiting on the owner (human gate or escalation) uses `on_needs_human`; otherwise `on_complete` (§18 #11). Environment: the caller's, plus `BATON_RUN_ID`, `BATON_STEP_PATH`, `BATON_OUTCOME` (`passed` \| `gate_failed` \| `needs_human` \| `needs_review` (a review step is ready for the Director to dispatch) \| `timed_out` \| `failed` (ended without a result) \| `overdue` \| `not_started` (a queued dispatch was dropped, §8.9) \| `answered` (an expert consultation turn, §12.1; `failed` when it has no answer)), `BATON_CLASSIFICATION`, `BATON_INCIDENT` (the platform incident the outcome opened, §12.3), `BATON_STEP_STATE` (the step's state after the outcome), `BATON_DISPATCH_ID`, `BATON_REPO`, `BATON_RECORD` (the step record, already regenerated). Each run is recorded as `completion_hook_fired` or `completion_hook_failed` (hook name, source, outcome, exit code; never the command). Hook failures never change outcomes.

  **Wake path** (Decision: [0058](../decisions/0058-detached-director-warned-not-refused.md), [0059](../decisions/0059-warn-owner-before-unwoken-dispatch.md), [0060](../decisions/0060-wake-notice-skips-manual-workers.md)). A Director's *wake path* is a hook that would fire for a step that ends waiting on the owner: `on_needs_human` or `on_complete`, project or machine level (the hook `choose_hook` picks for outcome `needs_human`; `supervisor.wake_path`). `on_platform_failure` alone is none, and so is a machine `hooks.yaml` that does not load. Before dispatch, `eligible` and `sme_eligible` report it as `wake` (§13.1); without one, `wake.notice` is the owner's words for "I might not notice when this finishes; it can take up to about <band> (a little longer if it runs over, when `extend_once` is on); ask me if you haven't heard by then", computed from the effort band, with no Baton vocabulary, and left out when every eligible worker is a person. `dispatch` and `ask_sme` warn whenever there is no wake path, with or without `--wait` and queued or not (JSON `warnings`; text mode: stderr); a dispatch to a manual worker never warns. Nothing is refused. The result appears at the next `status`/`board`, or `wait`.
- **Effort and timeouts:** steps declare `effort` (`S` / `M` / `L`) or `effort_from`; a step with neither, or whose `effort_from` does not resolve to one of them, gets `effort.default` (M). Bands come from `project.yaml` (`effort: { bands: {S: 45m, M: 2h, L: 4h}, extend_once: true, default: M }`; durations as `90s`, `45m`, `2h`). The deadline is dispatch time plus the band. At the deadline: if alive and `extend_once` is on (and not yet used), record `deadline_extended {previous_deadline, deadline, band}`, fire the hook with outcome `overdue` and extend by one band; otherwise terminate the worker's process tree, record `step_timed_out` and classify (`subject` / `timeout`; retried while attempts remain).

### 8.8 Failure classification

`classify.py` applies data-driven rules (`classify/rules-1.yaml`, format `baton-classify-rules/1`, plus adapter `failure_signals`), in order:

| Class | Typical signals | Goes to |
|---|---|---|
| `configuration` | Unknown profile, missing secret, invalid project config | Owner, with the exact fix |
| `platform` | Executable not found (exit 127), auth/login failure, sandbox or permission denial on a gate command, network/DNS, disk full, killed by the OS, supervisor died | Platform SME; incident opened (§12.3) |
| `subject` | Gate failed, schema invalid, worker reported `failed`/`blocked`, timed out | Recipe's normal path: retry, iterate, escalate |
| `unknown` | Nothing matched | Platform SME first, then owner |

A platform failure gets at most one automatic retry, and only after the platform SME records a fix; otherwise the step waits on the incident. Every `platform` and `unknown` classification opens an incident, except `capability_absent`; resolving it with the fix readies the step once (§12.3).

**`capability_absent`** (Decision: [0086](../decisions/0086-capability-absent-reroutes.md)): the event stream shows a tool the step required denied or unavailable (§6.3). The attempt's result is not taken in: `attempt_orphaned {discarded: capability_absent}`, `failure_classified {class: platform, code: capability_absent, capabilities}`, and `step_ready {retry_of, not_counted: true}`, which moves the step's attempt budget up by one, so the attempt is not counted against `max_attempts`. The capability is now `absent` on that profile (§6.1), so routing picks another worker; with none left the step escalates at once as `no_eligible_worker` (§8.4). No incident opens: there is nothing to fix. **`harness_flag_rejected`**: the CLI refused a tool-map flag; it is an ordinary platform failure with an incident, and the tools turned on for the attempt become `absent`.

A worker process that exits without writing `result.json` records `attempt_orphaned`, then `failure_classified`, then `step_escalated` with the class as its reason. The class comes from, in order: the API runner's failure line; the adapter's `failure_signals`; the rules' output patterns (disk full, DNS, network, TLS, out of memory, sandbox and permission denials); the rules' exit codes (127 and cmd.exe's 9009 `executable_not_found`, 126 `not_executable`) and killing signals (SIGKILL as `killed`); otherwise `unknown` with the last output line. Messages are redacted. A **failed script gate** is classified only by rules marked `scope: gate`: exit codes, signals, and output patterns specific enough to mean the command itself could not run (cmd.exe's "is not recognized as an internal or external command", since `cmd /c` then exits 1). Such a gate is `platform` and escalates. General patterns are not applied to gates, since a test suite may legitimately print them. Any other gate failure is `subject`. A worker over its time limit records `step_timed_out` and is retried like a failed gate while attempts remain. Raw worker output goes only to `~/.baton/logs/<run_id>/<step_path>/attempt-<n>.log` (the supervisor's own output beside it, `.supervisor.log`; hook output under `hooks/`).

### 8.9 Work items, concurrency and corrections

- **Runs** are independent work items; `run_started` records `{title, kind, slug, recipe, recipe_sha256, runtime, formats, capabilities_vocab, branch, max_attempts, inputs_sha256}` (the validated run inputs are a CAS blob). `baton board` lists all non-terminal runs (position including group progress, running work, pending decisions, lease holder; `--needs-me` filters to pending owner decisions).
- **Locks:** leases are per run (a Director may hold several). Write-mode workspace steps take a project **workspace lock**: one writer per working tree, across all runs and within one run (§18 #10: lock only; worktree isolation is deferred). Git operations and project-level files use a short **project lock**. Checkpoint commits stage only the committing run's files and its own deliverables, under the project lock. Optional `limits.active_runs` in `project.yaml`: `start` refuses a new run while that many are active.
- **Workspace queue** (Decision: [0033](../decisions/0033-workspace-queue.md)). Dispatching a write-mode step while the working tree is held (or while others are already queued) does not fail: the request (run, step, worker, guidance, Director) joins a first-in-first-out queue in `.baton/cache/`, `dispatch_queued {queue_id, worker, holder, position}` is recorded, and the call returns `queued` with the holder. The step stays `ready`; `status` and `board` show it queued. The lock is held from dispatch through intake and gates (a manual worker: until `submit`) and released by whatever ends the attempt: the supervisor after intake, `submit`, or reconciliation (`resume`, `wait`) of a dead supervisor; a holder whose process is gone is treated as released. The releasing process then starts the next entry itself (no daemon): it builds the packet and the worker's environment at that moment from the record and re-checks routing and the lease, as the queuing Director. Starting records `dispatch_dequeued {queue_id, started: true, dispatch_id}`; an entry that can no longer start (the step moved on, the worker is no longer eligible, the run ended, the lease is held elsewhere) is dropped with `dispatch_dequeued {started: false, reason}` and the hook fires with outcome `not_started`. `cancel(run, step_path)` withdraws a queued request; abandoning a run drops its entries. Read and none steps never wait for the lock.
- **`revise(run, step_path, reason)`** (owner-approved; like `take_over`, the runtime requires the reason and the director skill requires the owner's approval): the step gets a new attempt whose packet includes the previous result and the reason (§7.1); the old result becomes `superseded`; every accepted dependent step in that run becomes `stale` (`step_stale`); stale steps, once their dependencies pass, are re-run when dispatched or confirmed unchanged by the owner (§8.1); the reason is recorded without blame. Other runs are never affected. Revising a `foreach` source re-expands its group (§8.5): that group's instances are not marked stale at revision time, re-expansion judges each one. Refused while any dependent attempt is in flight. Built for top-level steps; revising a step inside a group is refused (deferred; correct in-group work by revising the group's source or through the iteration loop; Decision: [0034](../decisions/0034-revise-in-groups-deferred.md)).

### 8.10 Intake

1. Check `protocol` and `packet_sha256`; validate `output` against the schema (Draft 2020-12, format checks on). For a `foreach` source, echoed item ids must be current and unique (§5.8).
2. Verify required artifacts; ingest into CAS. Check a worker's `dispositions` (§7.2, §9.2). Check protected paths (§9.4).
3. `blocked` → `escalated` with the questions, normalized and validated (§7.2). Otherwise run gates in order (blocking gates stop at the first failure; advisory gates always run and record).
4. All blocking gates pass → `step_passed` → publish (§10.4) → record (§10.6) → checkpoint (§10.1) → dependents ready; group bookkeeping (§8.5); hooks fire.

Recording: `result_submitted` carries the hashes of the stored `result.json`, the output and each registered artifact; the implicit provenance check is recorded as a `gate_passed` with `gate: "provenance"`; declared gates are recorded by index. `step_passed` repeats the output and artifact hashes, and is the only thing downstream packets resolve from. Envelope, hash, schema and artifact problems are one `result_rejected` listing every reason. A rejected result, a failed blocking gate (except on a judge, §5.4), a `failed` worker or a rejected human gate returns the step to `ready` (its reasons become the next packet's `prior_feedback`) while attempts remain, else `escalated` (`attempts_exhausted`). A gate command that cannot be rendered or has a bad `cwd` escalates at once (`configuration`). A human gate's decision is referenced by the step path of the step awaiting it; `human_decision` records the owner's words verbatim, followed by the gate's `gate_passed` / `gate_failed`.
