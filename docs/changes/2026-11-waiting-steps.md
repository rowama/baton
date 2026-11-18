---
id: 2026-11-waiting-steps
title: "A step can wait for a condition for days without a process running, and an optional helper run from a scheduler checks on it"
status: in-progress
level: major
decisions: ["0165", "0154", "0156", "0058", "0059"]
touches: [principles.md, design/recipes.md, design/runtime.md, design/workers.md, design/director-interface.md, design/platform-and-security.md]
manual: [user/waiting-for-something.md, admin/scheduling-checks.md, admin/director-commands.md, user/long-running-work.md, context.yaml, reference-notes.yaml, reference/commands.md, reference/diagnostics.md, reference/environment.md, reference/project-settings.md, anchors.yaml]
---

# A step can wait for a condition for days without a process running, and an optional helper run from a scheduler checks on it

## Request

### Problem

Some processes must pause until something outside them happens: a price reaches a level, a signed contract comes back, an approval is posted, enough survey answers arrive. Baton has two ways to hold a step open, and neither fits:

- **A dispatched worker** is kept by a supervisor process with a deadline sized for work (§8.7). A reboot or a sleeping laptop kills it, and that is classed as a platform failure.
- **A person's step** (`manual`) is held as recorded state with no process, until someone runs `submit`. But a person must notice the condition and act.

The owner's direction (Decision [0154](../decisions/0154-tool-steps.md), item 5): waiting is held as state, like a person's step, with no Baton process kept alive; an optional helper run from a scheduler may check waiting steps and wake the process; Baton never requires it. Baton stays "not a general scheduler": nothing starts on a clock. A waiting step was dispatched by the Director like any other; only its completion is late.

### Acceptance criteria

1. **A step can wait.** A tool step may declare `wait: { until: <duration> }`. Its tool is a *check*: it looks at a condition and reports whether it is met, with the step's output when it is.
2. **Dispatch checks once.** Dispatching a waiting step runs the check. If the condition is met, the step goes on as any tool step does. If not, the step is recorded as waiting, with its deadline, and the dispatch returns. No process stays running.
3. **Waiting survives.** A waiting step is unaffected by a reboot, a closed Director session or a sleeping machine. Reconciliation (`resume`, `wait`) never judges it orphaned or timed out.
4. **One command checks.** `baton waits check` runs once and exits: for each waiting step in the project it runs the check; when a condition is met it takes in the result, runs the step's gates and fires the completion hooks, so the Director is woken as for any finished step. Two checks never overlap.
5. **Anyone may run it.** The Director runs `waits check` when it resumes or is asked how things stand. An owner may run it by hand. A scheduler may run it. All three are the same command.
6. **The helper is optional and visible.** `baton waits schedule` prints the entry to install for this machine (cron on Linux, macOS and WSL; Task Scheduler on Windows) and what it will do. Baton never installs it without the owner asking. Without it, waits still resolve whenever the command is run.
7. **Every wait ends.** At its deadline a waiting step stops waiting and the owner decides: keep waiting for another period, go on without it where the recipe allows, or stop. Nothing waits forever, and nothing is abandoned silently.
8. **The owner can see it.** `status`, `board` and the step record show each waiting step in plain words: what it waits for, since when, until when and when it was last checked. `start` and `doctor` say when a run has waiting steps and nothing is scheduled to check them, with how to fix it.
9. **Checks are cheap and declared.** A check tool is a tool like any other (§5.9): pinned, with its reach declared. It is meant to look and not to change anything; the recipe's reviewer and the owner see what it reaches.
10. **Little is recorded per check.** The log records that a wait started, was met, or expired. Routine checks that find nothing update a last-checked time and are kept only in diagnostics.
11. **The principle is reworded, not dropped.** "Not a general scheduler" stays: Baton starts nothing on a clock. The text says that a dispatched step may finish later through a check.

### Open questions

The owner answered all nine on 2026-11-17, each as suggested (Decision [0165](../decisions/0165-waiting-steps-details.md)).

1. **A new state, or reuse `running`?** *Decided:* a new state, `waiting` (`dispatched → waiting → submitted`, or `→ escalated` at the deadline).
2. **How does a check report?** *Decided:* the tool writes `output.json` with `met: true|false`; when met, the rest of the output is the step's output and is checked against its schema. A failed check (the tool crashed, the site was down) is not "not met": it is counted, and after three in a row the step escalates to the owner.
3. **May something outside deliver the result?** *Decided:* yes, `submit` works on a waiting step as it does for a person's step.
4. **How often should checks run?** *Decided:* the recipe may give `every: <duration>` as advice; `waits schedule` uses the shortest among waiting steps, never under five minutes. Baton does not enforce an interval.
5. **Is there a longest wait?** *Decided:* `project.yaml` `waits: { max: 30d }`; a recipe asking for longer is cut to it and the owner is told at `start`.
6. **Does `waits schedule` ever install the entry?** *Decided:* `waits schedule --install` does, after showing it, and `--remove` removes it; plain `waits schedule` only prints.
7. **WSL.** *Decided:* `doctor` detects WSL and recommends the Windows Task Scheduler entry that starts the check inside WSL; `--install` on WSL installs that entry.
8. **May a step other than a tool step wait?** *Decided:* not in this change.
9. **What does "go on without it" mean at the deadline?** *Decided:* the step may declare `on_expire: escalate` (default) or `skip`; with `skip` the owner's `decide <step> skip` marks the step skipped, which satisfies what depends on it. This adds the edge `escalated → skipped`, legal only for an expired wait that declares `skip` (today an escalated step's decisions are `retry` and `abandon`).

### Out of scope

- **Starting runs or steps on a schedule.** Baton remains not a scheduler.
- **A process that keeps watching** (a supervised watcher with a long deadline): considered and not chosen, because Baton would have to keep it alive.
- **Receiving webhooks.** Something outside may call `submit`; Baton ships no listener.
- **`recipe-builder` designing waiting stages.** A later builder change, once this is done.
- **The delegate interface** ([2026-11-ai-delegates](2026-11-ai-delegates.md), on hold), which builds on the waiting state.

## Design

Settled by the answers of Decision 0165. Approved by the owner with the Request on 2026-11-17.

### Shape

- **Recipe.**
  ```yaml
  - id: price_reached
    title: Wait for the price to reach the level
    depends_on: [levels]
    tool: price-check
    workspace: none
    wait: { until: 14d, every: 30m, on_expire: escalate }
    inputs:
      - { name: levels, from: steps.levels.output, required: true }
    output_schema: schemas/price_reached_out.json
    gates: [ { type: schema } ]
  ```
- **Dispatch.** The first check is an ordinary tool run (§6.3): supervised, short, in the tool's environment. Met: intake as usual. Not met: `wait_started {until, deadline, tool, every?}` and the step is `waiting`. The attempt stays open; later checks belong to it.
- **`baton waits check [--run <id>]`.** Takes a project lock, lists `waiting` steps, and for each: past the deadline, record `wait_expired` and escalate (`wait_expired`); otherwise rebuild nothing (the packet from dispatch is reused), run the check tool directly in the foreground with the step's effort band as its limit, and on `met` record `wait_met`, then run intake, gates, hooks and the checkpoint commit as the supervisor would. Exit code 0; it prints one line per step.
- **Last checked** is kept in `.baton/cache/waits.json` (machine-local), with the count of failed checks in a row.
- **`baton waits schedule [--install|--remove]`.** Builds the entry for the platform: a crontab line, or a Task Scheduler task (on WSL, one that runs the check inside WSL).
- **Reconciliation** skips `waiting` steps. A run whose only unfinished steps are waiting is reported as waiting, not stalled.
- **Wake path.** The existing notice for a Director with no wake path (Decisions 0058, 0059) covers waiting steps, worded for a long wait.
- **Owner decision at expiry:** `decide <step> retry` starts another period (`wait_started` again, same attempt budget rules as any retry); `skip` where the step declares `on_expire: skip` (the new edge `escalated → skipped`, `step_skipped` with `cause: wait_expired`); `abandon` as today.
- **Failed checks.** A check that crashes, exits non-zero or writes no valid `met` report is counted in `waits.json`; a good check resets the count; the third in a row escalates the step (`wait_check_failed`, with the last failure's class, §8.8).
- **Ceiling.** `project.yaml` `waits: { max: 30d }` (default); a longer `until` is cut to it when the run starts, and `start` says so.

### Doc edits

- `principles.md`: the "not a general scheduler" non-goal reworded; no new concept (a wait is a property of a step).
- `design/recipes.md` §5.3 (load rules for `wait`), §5.9 (a check tool and what it reports).
- `design/runtime.md` §8.1 (the `waiting` state and its edges), §8.2 (`wait_started`, `wait_met`, `wait_expired`), §8.7 (dispatch of a waiting step; reconciliation), §8.8 (failed checks).
- `design/workers.md` §6.3: running a check outside a supervisor.
- `design/director-interface.md` §13.1 (`waits check`, `waits schedule`; `status` and `start` reports), §13.3 (what the Director tells the owner about a wait).
- `design/platform-and-security.md` §14: cron, Task Scheduler and WSL.

### Manual edits

- Slice 1: `admin/director-commands.md` lists `waits check`; `context.yaml` maps the `waits` command to it; `reference-notes.yaml` describes `waits.max`, the hook outcome `waiting` and the diagnostics `waits.not_met`, `waits.check_failed` and `waits.cache_unreadable`; the generated reference pages (commands, diagnostics, environment, project settings) and `anchors.yaml` rebuilt.
- Slice 2: new owner topic `user/waiting-for-something.md` (what waiting means, where it stands, who checks, the three choices when a wait runs out, failed checks); new administrator topic `admin/scheduling-checks.md` (the command, the entry on Linux, macOS, Windows and WSL, the interval, `waits.max`, writing a check, with a worked example of a recipe step and its check script, and handing in a result from outside); `context.yaml` maps `waits` to it; `admin/director-commands.md` lists `waits schedule`; `user/long-running-work.md` links the new topic; the reference and anchors rebuilt.

### Decisions

- [0154](../decisions/0154-tool-steps.md) (accepted), item 5: waiting is held as state; the helper is optional.
- [0156](../decisions/0156-tool-steps-details.md) (accepted): how tools run.
- [0058](../decisions/0058-detached-director-warned-not-refused.md), [0059](../decisions/0059-warn-owner-before-unwoken-dispatch.md) (accepted): the wake path and its notice.
- [0165](../decisions/0165-waiting-steps-details.md) (accepted): the answers to the nine open questions.

## Plan

Slices as proposed; refined once the Request and Design are approved.

### Slice 1: a step waits as state

- **Outcome:** a waiting step is dispatched, checked once, and held with no process; `waits check` completes it or expires it.
- **Criteria:** load rules; the `waiting` state and its events; met at dispatch; met later; expiry and the owner's three decisions; failed checks counted; reconciliation leaves it alone; no overlap between two checks; hooks fire on met and on expiry.
- **Effort:** L

### Slice 2: the owner can see and schedule it

- **Outcome:** an owner knows what is waiting and whether anything is checking it, and can schedule the check on their machine.
- **Criteria:** `status`, `board`, step record and `start` reports; `doctor` warning with no schedule; `waits schedule` print, install and remove on Linux, macOS, Windows and WSL; `submit` on a waiting step; the Director skill; a shipped example; the manual.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0154, item 5, and the owner's discussion of 2026-11-15. A person's step already waits as state with no process; this change gives a tool step the same shape with a check. No code changed.
- **Owner decision:** 2026-11-16, "Go ahead and write 3 and 4."
- **Accepted:** No; proposal only. Nine open questions await the owner.

### Open questions answered

- **Summary:** Checked the nine suggested answers against the design: an escalated step's decisions are `retry` and `abandon` today, and `skipped` is reached only by tailoring, so answer 9 adds the edge `escalated → skipped` for an expired wait that declares `skip`. The owner accepted all nine as suggested. Recorded as Decision 0165. Request and Design updated (failed-check count, the 30-day ceiling, the skip edge). No code changed.
- **Owner decision:** 2026-11-17, "All as suggested." (0165).
- **Accepted:** No; the Request and Design await the owner's approval.

### Accepted

- **Summary:** The owner approved the Request and Design as updated with Decision 0165's answers. No code changed.
- **Owner decision:** 2026-11-17, "Approved."
- **Accepted:** Yes.

### Slice 1: a step waits as state

- **Summary:** A tool step may declare `wait: {until, every?, on_expire?}`. Its check runs at dispatch under the supervisor as any tool run; the tool runner, given `--wait`, requires a boolean `met` in `output.json`, strips it when met, and writes `not_met.json` in place of `result.json` when not. The supervisor (and reconciliation of a dead supervisor) then records `wait_started` with the deadline, cut to `project.yaml` `waits.max` (default `30d`), fires the hook with outcome `waiting`, and leaves no process. New state `waiting` (`running → waiting → submitted | escalated`), records `wait_met` and `wait_expired`, and the edge `escalated → skipped` only with `cause: wait_expired`. `baton waits check [--run]` holds a non-blocking lock (a second check returns `busy`), and for each waiting step: past the deadline, `wait_expired` and `step_escalated {reason: wait_expired}`; else runs the check in the foreground into the attempt's `check/` folder; met, `wait_met`, then intake, gates, records, incidents, checkpoint and hooks as the supervisor's; not met, only the last-checked time in `.baton/cache/waits.json` and a diagnostic; failed, counted there, and the third in a row escalates (`wait_check_failed`). At expiry the owner's options are `retry` and `abandon`, plus `skip` where the step declares `on_expire: skip` (labels "Keep waiting", "Go on without it", "Stop waiting and set this aside"). Design choices made while building, told to the owner: a waiting step may not be `workspace: write` (`step.wait_workspace_write`), since a check only looks and a write step would hold the working tree for the whole wait; `retry` at expiry readies the step and the Director's next dispatch checks again and starts another period (a new attempt, with a fresh budget as after any owner decision), rather than restarting the wait in place; a re-triage never un-skips a step skipped after its wait; durations accept days (`14d`) everywhere.
- **Modules:** `models.py` (`Wait`, `WaitsConfig`, the `waits` events, `d` durations), `state.py`, `recipe.py`, `groups.py` (`waiting` is in flight), `tool_runner.py`, `adapters/tool.py`, `engine.py` (`start_wait`, `expire_wait`, `checks_failed`, `Api.waits_check`, completion, reconciliation, hook outcomes, the expired-wait decisions, the checkpoint phrase), `waits.py` (new: the check cache and lock), `locks.py` (`try_file_lock`), `cli.py` (`waits check`), `defaults/labels.yaml`, `formats/baton-recipe-1.schema.json` (regenerated).
- **Design docs:** `principles.md` (the "not a general scheduler" non-goal reworded); `design/recipes.md` §5.9; `design/runtime.md` §8.1, §8.2, §8.7, §8.8; `design/workers.md` §6.3; `design/director-interface.md` §13.1.
- **Decisions:** none new (0165 applied).
- **Tests:** `tests/test_waiting_steps.py`: met at dispatch goes on as any tool step; not met, the step waits with no running marker, the hook says `waiting`, `resume` and `wait` leave it alone, a not-met check adds nothing to the log and keeps the last-checked time, a later met check is taken in, gated and passed, and the next step is ready; at the deadline the step escalates with `needs_human`, `skip` is refused without `on_expire: skip`, and `retry` then a dispatch waits another period on attempt 2; an optional wait is skipped and satisfies its dependent; failed checks are counted outside the log, a good check resets the count, the third escalates with the last reason and hook `failed`; a check without `met` fails; a longer `until` is cut to `waits.max`; two checks never overlap; the state edges and records; the load rules and the published schema; the labels; the cache and the lock. `tests/test_state.py` guards the new `escalated → skipped` edge. Not covered by a test: a supervisor that died after its check wrote `not_met.json` (the same `start_wait` as the supervisor's path), and the re-triage rule for a wait-skipped step.
- **Accepted:** Yes, pending the full suite on this commit.

### Slice 2: the owner can see and schedule it

- **Summary:** `status` lists each waiting step (what it waits for, since, until, `every`, `on_expire`, `cut_to`, last checked, failed checks) and carries `waits_notice` while steps wait and nothing on this machine is scheduled to check them; `board` carries the same per run and one notice; the step record says what the step waits on, since when, until when and what happens then (the last-checked time stays machine-local, in `status`, so a routine check never changes a committed record); `start` reports each waiting step's `until`, warns when a wait is cut to `waits.max`, and says whether anything checks waits here; `doctor` warns when steps wait with nothing scheduled. `baton waits schedule` prints the entry for this machine (cron on Linux and macOS; Task Scheduler on Windows; on WSL a Task Scheduler task that runs the check inside WSL, since cron stops with WSL), `--install` installs it after showing it and `--remove` removes it from every scheduler that has it; on WSL only the task counts as scheduled. The interval is the shortest `every` among waiting steps (else among the vendored recipes' waiting steps), at least five minutes, else 30 minutes. `submit` hands in a waiting step's result from outside (`--result`; none is `submit.no_result`). The MCP server gains `waits_check` and `waits_schedule`, so a Director on MCP can check and schedule. The Director skill (and its copy in §13.3) says when to check, how to tell the owner about a wait and its end, and to offer the schedule once and install it only on the owner's yes. Interpretation: the plan's "a shipped example" is a worked example in the administrator's manual topic (a recipe step and its check script); no shipped recipe has a waiting step yet; asked of the owner.
- **Modules:** `waits.py` (describe, interval, the cron and Task Scheduler entries, install, remove, the notice), `engine.py` (`status`, `board`, `start`, `doctor`, `waits_schedule`, `submit` on a waiting step), `docs.py` (the step record), `cli.py` (`waits schedule`, status and board lines), `mcp_server.py`, `skills/baton-director/SKILL.md`.
- **Design docs:** `design/runtime.md` §8.7; `design/director-interface.md` §13.1, §13.3; `design/platform-and-security.md` §15.1.
- **Decisions:** none new (0165 items 3, 4, 6 and 7 applied).
- **Tests:** `tests/test_waiting_steps.py`: the interval and cron specs; cron install keeps other lines and replaces its own, remove; WSL plans a Task Scheduler task inside WSL, a cron entry alone does not count there and the notice says so; Windows plans `schtasks` daily past a day; a missing scheduler is reported; end to end (with a fake scheduler): `status` (JSON and plain words), `board`, the step record and `doctor` show the wait and that nothing checks it, `waits schedule` prints without installing, `--install` installs and the notices go, `--remove` removes; `start` reports a wait cut to `waits.max`; something outside hands in a waiting step's result. `tests/test_director_surface.py`: the MCP tool list. The real `crontab` and `schtasks` are never run by the tests; the Windows and WSL entries are checked as built commands only.
- **Accepted:** Yes, pending the full suite on this commit.
