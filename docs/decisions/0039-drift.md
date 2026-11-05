---
id: "0039"
title: "Drift of published deliverables"
status: accepted
date: 2026-11-03
source: "inline note, §10.5"
sections: ["§10.5"]
---

# 0039. Drift of published deliverables

## Context

The published copy of an artifact is a living file; edits to it (drift) needed detection and a way back into the run.

## Decision

Read-only calls compute drift; mutating calls record `drift_detected` once per new hash, while the run is active. Drift is a pending owner decision that blocks no step but holds run completion: `leave`, or `ingest_revision`, which makes `human_revision.<step>.<artifact>` resolve (and, with `--feed dependents`, feeds steps not yet started; passed dependents are flagged possibly stale). An expert's artifact or answer can be promoted the same way.
