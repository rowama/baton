---
id: "0156"
title: "Tool steps: uv environments from a hash-locked file, Python first, declared network reach, one attempt, readiness checked at start and dispatch"
status: accepted
date: 2026-11-15
source: "Owner, 2026-11-15: \"1-concur. 2-concur. 3-concur. 4-concur. 5-concur. 6-concur. 7-concur. 8-concur.\""
sections: ["§5.3", "§6.3", "§8.7", "§8.8", "§15.2"]
---

# 0156. Tool steps: uv environments from a hash-locked file, Python first, declared network reach, one attempt, readiness checked at start and dispatch

## Context

Writing `2026-11-tool-steps` from Decision [0154](0154-tool-steps.md) raised eight questions. The suggested answers were put to the owner in one batch, and the owner concurred with each.

## Decision

1. **Environments are built with `uv`**, which the launcher already requires (§14.1): `uv venv`, then an install from the tool's lock file that requires hashes **[VERIFY against the installed uv]**. The lock file is a requirements file with exact versions and hashes. No new dependency.
2. **Python only in the first version.** `tool.yaml` names the runtime kind, so other runtimes can be added without a format change.
3. **Network reach is declared, shown to the owner at vendoring and recorded.** It is enforced only when the tool runs under `isolation: container`, because Baton cannot block a script's network access without OS isolation. The manual says so plainly. Network tools are not refused meanwhile.
4. **A tool step has one attempt by default.** A failure escalates to the owner with the tool's error output. A recipe may raise the limit for a tool that calls something unreliable.
5. **Not ready:** `start` warns, and the Director tells the owner what to install; dispatch refuses. A tool on a step the run's rating skips never blocks anything.
6. **Environments live in `~/.baton/tools/<lock hash>/`:** machine-local, never committed, shared by every project that uses the same lock.
7. **The recipe format stays `baton-recipe/1`.** The loader rejects unknown step fields, so an older runtime refuses a recipe with tools instead of misreading it.
8. **Tool steps use the effort bands** (§8.7) like any step, with `S` as their default.
