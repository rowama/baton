---
id: "0056"
title: "Codex setup includes a config line so Baton's tools need no per-call approval"
status: accepted
date: 2026-11-04
source: "change 2026-11-codex-director-sandbox, slice 3"
sections: ["§13.2", "§13.4"]
---

# 0056. Codex setup includes a config line so Baton's tools need no per-call approval

Amends [0053](0053-codex-director-via-mcp.md), which said setup needs no config file editing.

## Context

In the slice 3 live run (codex-cli 0.166.0, Linux), Codex treated every Baton MCP tool call as needing approval: `codex exec`, whose approval policy is `never`, refused them all ("MCP tool call requires approval, but approval policy is never") until the baton server had `default_tools_approval_mode = "approve"`. Interactive Codex would likely prompt on each call instead (not driven live), which brings back the frequent prompts the change doc rejected for "approve when asked". `codex mcp add` has no flag for the setting.

## Decision

Codex setup is the command `codex mcp add baton -- baton mcp`, then one line, `default_tools_approval_mode = "approve"`, under the `[mcp_servers.baton]` section it wrote in `~/.codex/config.toml`, then a restart. The owner message, its `blocking.config` field, §13.2 and the README say so. With that setting the live run completed `fit-check` over MCP inside Codex's sandbox with a real worker, confirming 0053.
