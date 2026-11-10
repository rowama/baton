---
id: "0120"
title: "Owner-run assessment fetches its recipe pinned to the runtime's version and reuses the runtime's validator"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: fetch with pinned version; reuse the validator)"
sections: ["§6.4", "§14.1"]
---

# 0120. Owner-run assessment fetches its recipe pinned to the runtime's version and reuses the runtime's validator

## Context

Decision 0111 lets an owner assess chosen models into a machine-local overlay. The research recipe ships only from a source checkout (0083), so an installed Baton does not have it. The options were to ship it in the wheel or to fetch it.

## Decision

- `baton workers assess` fetches the assessment recipe from the repository at the tag of the running runtime's version (`v<version>`), using the repository named by `~/.baton/launcher.yaml`'s `source` (the one the launcher installs from), and caches it under `~/.baton/assessment/<version>/`. It never fetches "latest". With no network and no cache it refuses in plain words, and an overlay can still be written by hand.
- The wheel keeps shipping only `defaults/` (0083 stands). The recipe lives in the repository at `tools/worker-research/assessment/`.
- The runtime's own validator checks every assessment: the worker is given `baton workers check-overlay <file>` to run on its draft, and the result is checked again with the same code before the overlay is written. No second validator is fetched or written.
- The recipe runs through the owner's own workers in a scratch project, like research (0083), and its output only ever reaches the overlay (0111).
