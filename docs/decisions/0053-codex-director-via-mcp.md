---
id: "0053"
title: "Codex directs Baton through MCP, not shell commands"
status: accepted
date: 2026-11-04
source: "change 2026-11-codex-director-sandbox"
sections: ["§13.2", "§13.3", "§13.4", "§15"]
---

# 0053. Codex directs Baton through MCP, not shell commands

Amended by [0056](0056-codex-tool-approval.md): setup also needs one config line. Confirmed by the live run of 2026-11-04 (codex-cli 0.166.0, Linux).

## Context

In the first real use with Codex as Director, `baton detect --json` and `baton doctor --json` crashed with `OSError: [Errno 30] Read-only file system` writing under `~/.baton/logs/doctor/`. Codex's default `workspace-write` sandbox lets commands, and the child processes they start, write only inside the project and configured `writable_roots`, usually without network. Every dispatch from that shell would put the supervisor and workers in the same sandbox (inferred, not yet reproduced). Approving each command is unreliable as the main path. Details and sources: [the change doc](../changes/2026-11-codex-director-sandbox.md).

## Decision

Codex directs Baton through MCP (`baton mcp`, §13.2), registered once with `codex mcp add baton -- baton mcp`; Codex's own commands stay sandboxed. A Codex maintainer states that MCP servers run outside the Codex exec sandbox. This rests on that statement and one third-party macOS report, so the change's live test (Codex over MCP with `workspace-write` completing `fit-check` on Linux) must pass before the README recommends it; if it fails, this decision is reopened.
