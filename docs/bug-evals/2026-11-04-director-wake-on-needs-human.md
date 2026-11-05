# Bug evaluation: Director not woken when a dispatch ends in needs_human

- Date: 2026-11-04 (times below are UTC from the event log, with America/Chicago CST in parentheses)
- Baton: 0.1.0, source /mnt/d/rob/projects/baton at a539bdf
- Project: /mnt/d/rob/projects/pure-water (host Merkle, WSL), run `r_20261104_1949` (recipe `baton-frame@1`)
- Director: Gus (Grok Bot, cloud chat agent driving `baton` via a remote Shell on Merkle)
- Status at time of writing: step `frame` is `awaiting_human` (attempt 2). The framing **select decision is still pending**: setup / sites-equipment / launch-marketing / operations.

## 1. Summary
Gus ran `baton dispatch r_20261104_1949 frame --worker claude-code-sub --wait --json` as a background Shell job and ended its turn, expecting a "job finished" wake. Both times the worker succeeded (exit 0), Baton recorded the result and opened an owner decision, and the CLI exited with **4** (`EXIT_OWNER`). That is how Baton is designed to behave. No completion hook was configured, so Baton had no way to wake anyone. The Grok Bot background-job wake also did not reach Gus, and the terminal was marked `failed`. Rob had to ask. Attempt 1 waited ~47 min for Rob (23:38:33Z → 00:25:03Z). Attempt 2 has been waiting since 00:26:14Z.

The cause is three gaps together. Any one of them alone would have let Gus notice:
1. **Baton:** `init` writes empty hooks. Nothing warns a `--wait` caller about that. The only "no hook" warning is skipped when you pass `--wait`.
2. **Platform:** a background remote-machine Shell job that ended (with exit 4) did not reliably wake the agent, and exit 4 was shown as "failed".
3. **Operator:** Gus ended the turn with only an unverified platform wake. There was no Baton hook and no follow-up check scheduled.

## 2. Repro steps
1. `baton init` a project and accept the default `.baton/project.yaml` (all hooks `""`). Have no `~/.baton/hooks.yaml`.
2. Start a framing run. From a detached harness (a Grok Bot Shell with machineId and `block_until_ms: 0`), run `wsl -e bash -lc 'cd <proj> && baton dispatch <run> frame --worker <harness-profile> --wait --json'`.
3. End the Director turn.
4. The worker finishes. Baton opens a human gate or escalation and the CLI exits 4. No `completion_hook_*` event is logged and the agent is not woken.

## 3. Expected vs actual
| | Expected (by Rob, and by the director skill's promise) | Actual |
|---|---|---|
| Worker finishes | Director resumes and talks to the owner within minutes | Nothing happens until the owner asks |
| CLI exit | Treated as "done, owner decision needed" | Exit 4, shown as `status: failed` in the Grok Bot terminal file |
| Hooks | Something wakes the Director (skill step 4: "the completion hook … brings you back") | No hook is configured, so `choose_hook` returns None and nothing fires |
| Warning | The Director is told nothing will wake it | The warning is suppressed because `--wait` was passed |

## 4. Evidence (`.baton/runs/r_20261104_1949/events.jsonl`)
| seq | ts (UTC) | CST | event | notes |
|---|---|---|---|---|
| 6 | 23:37:40.29Z | 5:37 PM | dispatched a1 | d_777ebc63, claude_code, deadline 01:37:40Z |
| 8 | 23:38:33.14Z | 5:38 PM | result_submitted a1 | status `blocked`, worker_exit.exit_code 0, 51.9 s |
| 10 | 23:38:33.23Z | 5:38 PM | step_escalated a1 | owner decision opened (needs_owner) |
| 11 | 23:38:33.64Z | 5:38 PM | checkpoint_committed | Shell 217411 ended 23:38:34Z, exit 4 |
| 13 | 00:25:03.34Z | 6:25 PM | human_decision | ~46.5 min later, after Rob asked |
| 18 | 00:25:11.71Z | 6:25 PM | dispatched a2 | d_0ea29bb0 |
| 20 | 00:26:14.19Z | 6:26 PM | result_submitted a2 | status `completed`, exit_code 0, 61.5 s |
| 22–23 | 00:26:14Z | 6:26 PM | gate_passed ×2 | provenance and schema |
| 24 | 00:26:14.35Z | 6:26 PM | human_gate_opened a2 | `select` gate; Shell 217412 ended 00:26:14Z, exit 4 |

- The log has **no `completion_hook_fired` or `completion_hook_failed` events**, which fits "no hooks configured".
- `.baton/project.yaml` hooks: `on_complete: ""`, `on_needs_human: ""`, `on_platform_failure: ""`. `~/.baton/` holds only `logs/` and `workers.yaml` (no `hooks.yaml`).
- `baton status` currently shows `needs_owner: true`, `pending_decisions[0].kind = gate`, and lease `rob@Merkle`, **harness `cli`** (BATON_HARNESS is unset, so Baton doesn't know the Director is a detached chat agent).

## 5. Code and doc citations (baton repo)
**Exit code 4**
- `src/baton/cli.py:27`: `EXIT_OK, EXIT_PROBLEM, EXIT_USAGE, EXIT_LEASE, EXIT_OWNER = 0, 1, 2, 3, 4`
- `src/baton/cli.py:159` (`_done`): `code = EXIT_OWNER if payload.get("needs_owner") else EXIT_OK`. Any payload that needs the owner exits 4, whatever the worker's exit was.
- `src/baton/cli.py:488`: for dispatch, only `outcome == "retry"` without needs_owner gives exit 1. Otherwise `_done` applies, so a finished `--wait` that opens a gate exits 4. The same rule is at `cli.py:585` for `wait`.
- `src/baton/engine.py:1776-1782` (Api docstring): "`needs_owner` in a payload means the run now waits on an owner decision (CLI exit code 4)."
- `src/baton/mcp_server.py:11`: "`needs_owner: true` in a result is the CLI's exit code 4."
- `src/baton/cli.py:283` and `cli.py:1000`: exit 4 also means "ask" for vendoring and `permission`. In `skills/baton-director/SKILL.md:40` and build guide `:1239`, "`ask` (exit 4): ask the owner".
- **Gap:** the README and the director skill never say that exit 4 from `dispatch --wait` / `wait` is a *success-path* outcome ("finished, owner decision now pending"). Harnesses treat it as a failure.

**Completion hooks**
- `src/baton/project.py:64-67`: the `init` template has all three hooks `""`, with comments "falls back to on_complete" and "machine hooks: ~/.baton/hooks.yaml".
- `src/baton/models.py:626-628`: `HooksConfig` defaults are all `""`.
- `src/baton/supervisor.py:30-40`: machine hooks live in `$BATON_HOME/hooks.yaml` (may use `secret:`). A platform failure uses `on_platform_failure`, a step waiting on the owner uses `on_needs_human`, and each falls back to `on_complete`.
- `src/baton/supervisor.py:355-370` (`load_hooks`): drops empty values. Project and machine hooks are both used if present.
- `src/baton/supervisor.py:384-389` (`choose_hook`): returns `None` when nothing is configured, so **nothing fires**.
- `src/baton/supervisor.py:~419-450` (`fire_hooks` / `run_hook`): runs after intake and records `completion_hook_fired` / `_failed`.
- `docs/baton-framework-build-guide.md:833-840` (§8.7): hooks fire on every outcome, including `needs_human`. It lists the `BATON_*` environment variables and gives an example `on_complete` curl to `secret:director_wake_url`.
- `src/baton/engine.py:3260`: a `skipped_step` notice also fires `on_needs_human`.
- `src/baton/doctor.py:30` and `:293-304`: doctor checks that configured hooks *can run*. It does not flag "no hooks configured".

**Intended Director wake/resume when detached**
- `README.md:111-118`: "A Director whose turn ends while work runs (a cloud chat agent with a shell on this machine, for example) is woken by a **completion hook** in `.baton/project.yaml` or `~/.baton/hooks.yaml`." This describes Gus exactly, but it's opt-in.
- `skills/baton-director/SKILL.md:30` (= guide `:1229`): "If you can stay attached, `wait`; otherwise end your turn — the completion hook or the next `board` brings you back." It assumes a hook exists and says nothing about what to do when none does.
- `src/baton/engine.py:2378-2381`: on dispatch **without** `--wait` and with no hooks, the payload gets the warning "no completion hook is configured: nothing will wake you when this finishes; check with `baton status …` or `baton wait …`". **With `--wait` this warning is skipped**, but a detached `--wait` is exactly the case that needs it. The same pattern is at `engine.py:3484-3485` for SME consultations.
- Build guide `:828-831`: reconciliation (`resume`, `wait`) finishes missed intakes, and hooks fire for reconciled outcomes too.

**What `dispatch --wait` returns**
- `cli.py:32`: `--wait` means "Block until the worker finishes and its result is recorded."
- `cli.py:482-489`: without an `outcome` (async), it returns at once with "Then: baton wait …". With an outcome, the exit code is 0 (done, nothing pending), 1 (retry, no owner), or **4 (needs owner: gate, escalation, blocked questions)**. The worker's own exit code is inside the payload (`worker_exit.exit_code`) and does not affect the process exit code.

**Guidance about external harnesses**
- Guide `:130`, `:1190-1193`, README `:100`, `:118`: any harness with the skill plus a shell or MCP. MCP registration is listed for Claude Code, Codex and Hermes. **There is no Grok Bot or cloud-chat guidance** beyond the one README sentence. `BATON_HARNESS` (`locks.py:59`) is never mentioned to operators, so leases show `harness: cli`.

## 6. Are empty hooks the default, and is that a footgun?
Yes, empty hooks are the documented default (`project.py:64-67`, `models.py:626-628`, guide §8.7 shows hooks as opt-in). For attached Directors (a local Claude Code session running `wait`) that's fine. For detached Directors it is a footgun, and Baton knows it:
- it has a warning for this case (`engine.py:2378`), but the warning is suppressed under `--wait`, only goes into the JSON `warnings`, and only appears on stderr in text mode;
- `doctor` does not report "no hooks configured";
- the director skill promises "the completion hook … brings you back" without checking one exists.

## 7. Root-cause hypotheses (ranked)
1. **A, Baton product gap. High confidence, primary.** Defaults plus a silent `--wait` path mean a detached Director gets no Baton-side wake. Evidence: empty hooks, no hook events, `choose_hook` → None, and the warning is skipped for `--wait`. A hook would have fired at 23:38:33Z and 00:26:14Z no matter what the harness did.
2. **B, Grok Bot platform gap. Medium-high confidence, contributing. Ulrik needs to confirm.** A background Shell on a registered machine (machineId Merkle, `block_until_ms: 0`) completed twice, and Gus was not woken either time. Possible causes: (a) end-of-turn completion notifications aren't delivered for machine-targeted jobs, or are dropped after the turn ends; (b) a non-zero exit is marked `failed` and handled differently; (c) a delivery or timing problem across the PowerShell → wsl wrapper. The terminal's `status: failed` for exit 4 is at least a presentation bug, because exit 4 is a defined success-with-decision code.
3. **C, Operator/Director misuse. Medium confidence, contributing.** Gus ended the turn relying on one unverified wake mechanism. Gus didn't check that hooks existed, didn't schedule a fallback check (routine or timer), didn't set `BATON_HARNESS`, and repeated the same pattern on attempt 2 after attempt 1 had already gone unnoticed. The skill's wording ("completion hook … brings you back") makes this an easy mistake, so the blame is shared with A.
4. *Rejected:* runtime or supervisor failure. The supervisor finished intake and committed checkpoints within ~0.5 s of the worker exiting both times, and there is no `attempt_orphaned` event.

## 8. Impact
- Owner-facing latency: ~47 min on attempt 1, and the attempt 2 gate is still open. Rob has to supervise the Director, which defeats the point of a detached Director.
- It hits every detached Director on a default install and every needs-owner outcome (gates, escalations, blocked questions, permission asks).
- Misread exit codes make successful work look failed.

## 9. Recommended fixes
### Baton (repo changes)
| # | Fix | Cost / friction | Decision needed? |
|---|---|---|---|
| B1 | **Always emit the "no completion hook" warning when a Director is detached or unknown**, including with `--wait`. Put it in the JSON `warnings` and on stderr (`engine.py:2378`, `:3484`). | Tiny | No |
| B2 | **Director skill step 4:** "Before ending your turn, check a wake path exists (`baton doctor` or `hooks` set, or your harness reliably wakes you on job end). If none, stay attached with `wait`, or schedule your own check of `status`. Never end the turn with no wake path." Add "exit 4 from `dispatch --wait`/`wait` = finished, owner decision pending: go talk to the owner now." | Tiny (docs) | No |
| B3 | **Document exit codes** in the README and the skill (table: 0 done, 1 problem/retry, 2 usage, 3 lease, 4 owner needed or ask), and say that 4 is not a failure. Add a `--exit-zero-on-owner` flag (or `BATON_OWNER_EXIT=0`) for harnesses that treat non-zero as failure. | Small | Flag: no. Changing the default exit code: **yes, avoid** (breaks scripts) |
| B4 | **`doctor` check: "no completion hooks configured"**. A warning, escalated when the lease harness isn't `cli`. | Small | No |
| B5 | **Hook templates** in `examples/hooks/`: a curl webhook, a local notify file (`echo "$BATON_RUN_ID $BATON_OUTCOME" >> ~/.baton/inbox.log`), and a Grok Bot or mmbridge wake when the platform exposes one. Have `init --director-wake <url>` write `~/.baton/hooks.yaml`. | Small–medium | No |
| B6 | **`BATON_HARNESS` / `--detached` awareness.** If the Director declares itself detached (`BATON_HARNESS=grokbot`), `dispatch` refuses or loudly warns when no hook exists, unless `--wait` runs in the foreground. | Medium; changes behavior | **Yes** |
| B7 | **Built-in fallback wake:** always append outcomes to `.baton/notices.jsonl` (or `~/.baton/inbox`), even with no hooks, so harnesses can poll or watch one file. | Medium | **Yes** (new protocol surface) |
| B8 | Non-empty default hook in `init`, e.g. a desktop or log notifier. | Low code, but platform-specific and noisy | **Yes**. Narrower alternative: B4 + B5 |

### Grok Bot platform (asks for Ulrik)
| # | Ask | Cost |
|---|---|---|
| P1 | Confirm whether completion of background Shell jobs on a **registered machine** (vs the box) wakes the agent after its turn ends, and reproduce with exit 0 vs exit 4. | Investigation |
| P2 | Wake on completion whatever the exit code. Show the exit code instead of a bare `failed`, or allow per-command "expected exit codes". | Platform change |
| P3 | Provide an inbound wake endpoint (webhook or mmbridge channel) a Baton `on_complete` hook can curl. That makes A independent of B. | Platform change, medium |
| P4 | Until fixed, document that Directors must not rely on the machine-job wake, and must use a routine or timer, or block in the foreground. | Docs |

### Operator / Director (Gus) now
| # | Action | Cost |
|---|---|---|
| O1 | Prefer foreground: `dispatch … --wait` with `block_until_ms` large enough (framing ~1 min), then handle exit 4 in the same turn. | None |
| O2 | If detaching, create a one-shot routine to check `baton status <run>` in ~N minutes, plus a hook once P3 exists. | Low |
| O3 | Set `BATON_HARNESS=grokbot` and `BATON_DIRECTOR=gus@…` so leases and records show the real Director. | None |
| O4 | Treat exit 4 as "go talk to Rob", never as failure. | None |

**Narrowest effective fix set (no decision needed):** B1 + B2 + B3 (docs + flag) + B4 on the Baton side, P1/P2 on the platform side, and O1/O2 now.

## 10. Open questions for Ulrik / platform
1. Are end-of-turn completion notifications delivered for Shell jobs started with `machineId` + `block_until_ms: 0`? Were they emitted for jobs 217411 and 217412, and if so, why weren't they acted on?
2. Does a non-zero exit (`status: failed`) change notification delivery?
3. Can the bot get an authenticated inbound wake URL (or mmbridge DM) for Baton hooks? What is its auth model? A secret can go in `~/.baton/hooks.yaml` via `secret:`.
4. Should "expected" exit codes (like 4) be configurable per command?

## Appendix A. Raw event snippets (truncated)
```json
{"actor":"director:rob@Merkle","attempt":1,"data":{"adapter":"claude_code","auth_mode":"cli_login","deadline":"2026-11-05T01:37:40.046680Z","dispatch_id":"d_777ebc63","effort":"M","effort_source":"default","executable":"/home/rob/.local/bin/claude", ...},"seq":6,"type":"dispatched"}
{"actor":"worker:claude-code-sub","attempt":1,"data":{"artifacts":{},"output_sha256":null,"result_sha256":"3643e55e…5e","status":"blocked","worker_exit":{"duration_s":51.869,"exit_code":0,"timed_out":false}},"seq":8,"type":"result_submitted"}
{"actor":"director:rob@Merkle","attempt":2,"data":{"adapter":"claude_code","dispatch_id":"d_0ea29bb0","deadline":"2026-11-05T02:25:11.465829Z", ...},"seq":18,"type":"dispatched"}
{"actor":"worker:claude-code-sub","attempt":2,"data":{"output_sha256":"446bda11…85c","result_sha256":"926df730…6a6","status":"completed","worker_exit":{"duration_s":61.49,"exit_code":0}},"seq":20,"type":"result_submitted"}
{"actor":"runtime","attempt":2,"data":{"gate":"select","implicit":true,"parts":[{"id":"setup"},{"id":"sites-equipment"},{"id":"launch-marketing"},{"id":"operations"}]},"seq":24,"type":"human_gate_opened"}
```
## Appendix B. Current `baton status r_20261104_1949 --json` (excerpt)
```json
{"state":"active","steps":{"frame":{"state":"awaiting_human","attempt":2}},
 "pending_decisions":[{"ref":"frame","kind":"gate","options":[{"decision":"select"},{"decision":"reject"}]}],
 "needs_owner":true,
 "lease":{"director_id":"rob@Merkle","harness":"cli","host":"Merkle","expires_at":"2026-11-05T01:25:03.279264Z"},
 "last_checkpoint":"0b5bba7923e4364889af9ce90afdbdd31aad381d","last_seq":24}
```
Platform-side: Shell 217411 ended 2026-11-04T23:38:34Z (5:38 PM CST) and 217412 ended 2026-11-05T00:26:14Z (6:26 PM CST), both exit_code 4 with terminal `status: failed`, as reported by Gus and not re-verified here.
