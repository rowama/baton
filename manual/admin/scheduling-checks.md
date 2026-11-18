---
id: admin.scheduling-checks
title: Waiting steps and scheduling their check
audience: admin
order: 55
summary: How a waiting step is checked, the optional scheduler entry for cron or Task Scheduler (and WSL), and how to write a check.
related: [user.waiting-for-something, admin.director-commands, admin.project-settings, admin.platform-notes]
---

## Here, now {#here-now}

A waiting step is held in the run's record with no process. `baton waits check` checks every waiting step once and exits. The assistant runs it when it resumes; you can run it by hand; a scheduler can run it. All three are the same command, and two checks never overlap: a second one reports that a check is already running and exits.

Baton never installs anything to run it unless the owner asks. To see what would be installed on this computer:

```baton
baton waits schedule
```

It prints the entry and what it does. `--install` installs it, after showing it; `--remove` removes this project's entry.

## What is installed where {#where}

| Computer | Entry |
|---|---|
| Linux, macOS | A line in your crontab, marked with `# baton-waits <project>`, that runs `baton --project <project> waits check` and appends its output to `~/.baton/logs/waits-check.log` |
| Windows | A Task Scheduler task named `Baton waits <id>` that runs `baton --project <project> waits check` |
| WSL | A Windows Task Scheduler task that runs the check inside your WSL distribution (`wsl.exe -d <distro> -- sh -c "…"`) |

On WSL, cron runs only while WSL itself is running, so a cron entry stalls when no Linux terminal is open. That is why `waits schedule` offers Task Scheduler there, and why `doctor` warns when only a cron entry exists.

The interval is the shortest `every` among the waiting steps (or, with none waiting, among the vendored recipes' waiting steps), never under five minutes; 30 minutes when none gives one. Baton does not enforce it: the scheduler belongs to the machine.

`status`, `board`, `start` and `doctor` say when steps are waiting and nothing is scheduled to check them, with how to fix it.

## How long a step may wait {#how-long}

A step's `until` is its longest wait, from the first check that found the condition not met. The project's `waits.max` (in `project.yaml`, default `30d`) caps it; `start` says when a recipe asks for longer. At the deadline the step goes to the owner, who keeps it waiting, goes on without it where the recipe allows, or sets it aside.

## Writing a check {#writing-a-check}

A check is a tool (a script the recipe ships) on a step that declares `wait`:

```yaml
- id: price_reached
  title: Wait for the price to reach the level
  depends_on: [levels]
  tool: price_check
  workspace: none
  wait: { until: 14d, every: 30m, on_expire: escalate }
  inputs:
    - { name: levels, from: steps.levels.output, required: true }
  output_schema: schemas/price_reached_out.json
  gates: [ { type: schema } ]
```

It writes `output.json` with `met: true` or `met: false`. When met, the rest of the object is the step's output, checked against its schema:

```python
import json, sys
from pathlib import Path

args = sys.argv[1:]
inputs = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
out = Path(args[args.index("--output") + 1])
price = current_price()                      # your own code: read the price from where it lives
met = price >= inputs["levels"]["target"]
result = {"met": met, "price": price} if met else {"met": False}
(out / "output.json").write_text(json.dumps(result), encoding="utf-8")
```

A check should look and change nothing: a waiting step may be `workspace: read` or `none`, never `write`. A check that crashes, exits non-zero or reports no `met` is a failed check, not "not met". It is counted, and the third failure in a row goes to the owner. A check that finds nothing records nothing in the run's log; when it last ran is kept in `.baton/cache/waits.json` on this machine.

Something outside Baton can also hand in a waiting step's result: `baton submit <run> <step> --result <folder holding result.json>`.
