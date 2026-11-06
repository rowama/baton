---
id: "0078"
title: "Machine resources are declared in ~/.baton/resources.yaml, each with an explicit kind"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§4.4", "§6.1"]
---

# 0078. Machine resources are declared in `~/.baton/resources.yaml`, each with an explicit kind

## Context

Resources that inspection cannot discover must be declared by the owner, kept apart from generated profiles. The owner asked that the file distinguish the kind of resource explicitly, so later kinds can be added to the same file.

## Decision

`~/.baton/resources.yaml`, format `baton-resources/1`:

```yaml
format: baton-resources/1
resources:
  openrouter-main:
    kind: worker               # required; the only kind so far
    provider: openrouter
    credential: secret:openrouter_main
    base_url: null             # optional endpoint
    models: []                 # optional allowlist of model_ids; empty = whatever the routes offer
    note: "personal account"
setup:
  worker:                      # completion state, per kind
    completed: 2026-11-06
    runtime: 0.x.y
    nothing_more: true         # the owner said there is nothing else to add
```

- `kind` is required on every resource; an unknown kind is a load error naming the kinds this runtime knows. Setup state is kept per kind.
- Credentials are only `secret:<name>` references, resolved through the §6.1 chain; a literal credential value is a load error.
- The owner edits it through `baton workers declare` (or the Director), or by hand; `baton workers setup` revisits it.
