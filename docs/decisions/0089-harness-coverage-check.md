---
id: "0089"
title: "Research is refused when a harness's creator has a model with no pinned harness route and no stated gap"
status: accepted
date: 2026-11-08
source: "change 2026-11-cli-model-routes (owner, 2026-11-08)"
sections: ["§6.4"]
---

# 0089. Research is refused when a harness's creator has a model with no pinned harness route and no stated gap

## Context

The 2026-11-06 report skipped Fable 5.1 and Haiku 5.5 on Claude Code because a page "was not re-read". Nothing noticed. More harness CLIs than Claude Code and Codex exist or will (Gemini, Grok…), and nothing in the data format is specific to two.

## Decision

- A harness provider names the `creators` whose models it can run. The research tool lists every model of those creators that has no pinned route on that harness and no coverage-gap entry naming it; any such model refuses the run, like an invalid proposal (saved beside the report, repository untouched).
- The check reads the data, so a new harness needs a provider entry, not a code change. Adapter presets for further CLIs are a separate change; until one exists their routes are `supported: false`.
