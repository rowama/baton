---
id: "0017"
title: "Relay is the formal expert mode; handoff is a runtime-made prompt"
status: accepted
date: 2026-11-03
source: "§18 #17"
sections: ["§12.1"]
---

# 0017. Relay is the formal expert mode; handoff is a runtime-made prompt

## Context

SME handoff mode support per harness.

Suggested: relay first; handoff per harness later.

## Decision

relay is the formal mode. Handoff needs nothing per harness: the runtime (never the Director) generates a copy-and-paste prompt from the consultation, saved as `handoff.md`, which is the whole record; nothing returns except through promotion. The runtime refuses it, with the reason, when the expert relies on `shell`, `code_exec`, `workspace_read`, `repo_workspace` or `file_write`, unless the expert is a `command` black box. SMEs are never people; a person is consulted through a proxy SME that drafts and never sends (§12.1).
