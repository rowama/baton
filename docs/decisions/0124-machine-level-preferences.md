---
id: "0124"
title: "Routing preferences have a machine level that project preferences override"
status: accepted
date: 2026-11-10
source: "change 2026-11-setup-ui (owner, 2026-11-10: accept the suggested answer)"
sections: ["§8.4", "§4.4", "§13.9"]
---

# 0124. Routing preferences have a machine level that project preferences override

## Context

Open question 5. Preferences were per project (`.baton/preferences.yaml`) while the stable is per machine.

## Decision

- `~/.baton/preferences.yaml` has the project file's format. Routing reads both.
- Merge: `prefer.by_step` and `prefer.by_capability` are replaced per key by the project's entry; `exclude` is the union of both (a machine exclusion cannot be lifted by a project, since the owner turned the model off for the machine); `cheapest_first` is the project's value when the project file sets it, else the machine's.
- The page and `baton workers prefs` edit the machine level only. Per-project preferences stay a Director or CLI matter and are unchanged.
- The `worker_selected` event's exclusions name which level excluded a profile.
