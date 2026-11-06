---
id: "0079"
title: "Generated profiles live one per file in ~/.baton/workers/, owned by content hash"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§4.4", "§6.1"]
---

# 0079. Generated profiles live one per file in `~/.baton/workers/`, owned by content hash

## Context

Rewriting `~/.baton/workers.yaml`, which the owner also edits by hand, would risk the owner's profiles, comments and formatting.

## Decision

- Generated profiles are written to `~/.baton/workers/<profile>.yaml`, one profile per file, named by the file. `~/.baton/workers.yaml` stays the owner's and is never written by the manager. Profiles load from `workers/`, then `workers.yaml` (wins on a name), then `.baton/workers.local.yaml`.
- A generated file carries `generated: {by: baton <version>, known_workers_sha256, content_sha256}`. It is **untouched** while `content_sha256` matches its content; a file without the marker, or with a mismatching hash, is the owner's and is never changed, refreshed or removed.
- A refresh of an untouched file may change only `capabilities`, `tier` and `context_tokens`. It never changes `creator`, `model_id`, `provider`, `model`, `adapter`, `resource` or `auth`.
- A model retired from known-workers keeps its profile, flagged as retired in `workers status`; it is not removed.
- A generated name already taken by an owner profile is skipped and reported.
- Each resource is processed on its own; one failing does not stop the others. Each file is written atomically.
- New models appear only through `baton workers setup`; upgrading the runtime adds none.
