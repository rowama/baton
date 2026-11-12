---
id: "0138"
title: "The eng-process recipe uses Baton machinery without duplicate process state"
status: accepted
date: 2026-11-12
source: "Owner, 2026-11-12: Use Baton machinery (recommended)"
sections: ["§5.7"]
---

# 0138. The eng-process recipe uses Baton machinery without duplicate process state

## Context

The proposed engineering recipe translates eng-process into Baton. It could preserve the engineering process using Baton machinery or require the original CLI and file-state conventions as well.

## Decision

Preserve the engineering phases and checkpoints using Baton's existing state, handoff and worker machinery. Do not require the eng-process CLI or duplicate authoritative process state files. Engineering deliverables remain project artifacts. This settles the proposal's compatibility boundary; it does not approve the remaining policy choices or authorize implementation.
