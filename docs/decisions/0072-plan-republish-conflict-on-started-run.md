---
id: "0072"
title: "A process-plan conflict at --from-plan waits on the run it started"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§10.4", "§11.6"]
---

# 0072. A process-plan conflict at --from-plan waits on the run it started

## Context

The process plan is re-published under the §10.4 conflict rules when a part is started with `--from-plan` (0068). A conflict is normally a pending decision on the publishing run, holding its completion, but a framing run completes at selection, so no open framing run can hold it.

## Decision

The conflict waits as a pending decision on the run `--from-plan` just started: its start caused the re-publish, it is active, and it shows on the board. That run cannot complete until the conflict is decided (`overwrite`, `keep` or `alternate`). A completed framing run is never reopened.
