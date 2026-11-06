---
id: "0068"
title: "The runtime renders framing's breakdown from the record; no new framing version"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§11.6", "§10.4", "§2"]
---

# 0068. The runtime renders framing's breakdown from the record; no new framing version

## Context

0064 has framing publish its breakdown. Someone has to write it, at some point, and the recipe may or may not need a new version.

## Decision

- The runtime renders the breakdown from the record (the `frame` output plus each option's `next`), never a worker, so it cannot misstate what a part starts.
- It is published when `select` is decided, each part marked as chosen (with its run) or for later, and published again when a part is started with `--from-plan`, under the conflict rules of §10.4 (an owner edit gets overwrite, keep or alternate).
- The `baton-frame/1` output does not change, so there is no `baton-frame@2`. A `baton-frame@1` run open at upgrade decides as before and also gets its document.
- The breakdown and the notes file add no concept (§2): the breakdown is a rendering of a framing run's record, the notes file is the owner's own file.
