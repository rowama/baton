---
id: "0153"
title: "Project policy: the file is in force until the first record, and floors raise baseline ratings"
status: accepted
date: 2026-11-14
source: "Owner, 2026-11-14: approved the Request and Design of 2026-11-project-policy with the suggested answers (file in force until first record; floors in the baseline proposal)."
sections: ["§5.5", "§11.5", "§13.7"]
---

# 0153. Project policy: the file is in force until the first record, and floors raise baseline ratings

## Context

Checking the Design of `2026-11-project-policy` against the code raised two gaps. Enforcement reads only the recorded policy (0151), but a project that predates policy has no record, so a project with customized permissions would revert to the defaults until confirmed. Floors were designed for triage and re-triage, but an adopted run's ratings come from the adoption baseline (§11.5), which bypasses triage.

## Decision

1. **Until a project's first policy record, `project.yaml` is in force**, as before policy existed. `check` warns that the policy is not yet recorded (an error under `--strict`), `status` says so, and the Director asks the owner once; `policy confirm` or `policy set` makes the first record. From then on, 0151's rule applies: a hand edit waits for confirmation.
2. **Floors raise the ratings of an adoption baseline** when the baseline proposal is built, so the owner sees and approves the raised rating. The run's `complexity_set` records `floors_applied` like a triage would.
