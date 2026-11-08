---
id: "0085"
title: "Tooling capabilities belong to the harness: researched tool maps, least privilege, verified by use"
status: accepted
date: 2026-11-08
source: "change 2026-11-capability-confidence (owner, 2026-11-08)"
sections: ["§5.6", "§6.3", "§6.4", "§8.8"]
---

# 0085. Tooling capabilities belong to the harness: researched tool maps, least privilege, verified by use

## Context

`web_access`, `shell`, `file_write`, `code_exec`, `repo_workspace` and `workspace_read` are provided by a harness (Claude Code, Codex) and the flags Baton passes it, not by the model behind it. The adapters passed only a permission or sandbox mode, so whether web tools were available was left to each CLI's defaults.

## Decision

- Each harness provider in the known-workers data carries a **tool map**: for each tooling capability, the args that turn it on, where they go on the command line, the CLI version range and sources. It is researched data, not adapter code; the adapter only places the args.
- A step gets only the tool args its `requires` names (least privilege).
- `baton workers setup` checks each mapped flag against the installed CLI's `--help`; a missing flag means the capability is not offered on that machine.
- A flag the CLI rejects at dispatch is classified `platform` / `harness_flag_rejected` and opens a platform incident (§12.3); the platform SME proposes the data fix. The capability is `absent` on that profile until the fix lands or the CLI version changes.
- Evidence of tool use is read from the harness's machine-readable event stream (Claude Code `--output-format stream-json`, `codex exec --json`; both seen in the installed CLIs, `claude` 2.1.319 and `codex-cli` 0.166.0). Intake still reads only `result.json`; the stream is the attempt's log, scanned only for tool calls and denials (Open question 3, owner, 2026-11-08).
- A successful tool call in a step that required the capability records `verified`; a denied or unavailable tool records `absent`; a step that passed without using the tool records nothing. No extra model call is made to verify (amending 0081).
