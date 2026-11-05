---
id: "0051"
title: "The launcher is the package's own entry point"
status: accepted
date: 2026-11-03
source: "inline note, §14.1"
sections: ["§14.1"]
---

# 0051. The launcher is the package's own entry point

## Context

§18 #15 chose a uv-managed launcher; how it picks and runs a version was open.

## Decision

`baton.launcher:main` reads `runtime` from `baton.lock` and runs in-process when it matches, else re-runs the command under `~/.baton/versions/<v>/`. Version choice: `BATON_VERSION`, then `upgrade --to`, then the launcher's own for `init` or no project, else the lockfile's. Installs use uv from a `source` template in `~/.baton/launcher.yaml`; `BATON_LAUNCHED` prevents loops.
