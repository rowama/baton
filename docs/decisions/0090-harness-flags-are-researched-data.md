---
id: "0090"
title: "Harness CLI flags are researched data, reviewed in the diff; drift goes to the platform SME"
status: accepted
date: 2026-11-08
source: "change 2026-11-cli-model-routes (owner, 2026-11-08)"
sections: ["§6.4"]
---

# 0090. Harness CLI flags are researched data, reviewed in the diff; drift goes to the platform SME

## Context

0085 made the args that turn a harness tool on data (a tool map), seeded by hand from `--help`. Research should now produce and refresh them.

## Decision

The researcher proposes each harness's tool map (per tooling capability: args, CLI version range, sources) and the flag for machine-readable output used as tool-call evidence, and reports any flag that widens permissions. They are reviewed in the diff like model IDs. Drift found at run time (a rejected flag) goes to the platform SME as in 0085.
