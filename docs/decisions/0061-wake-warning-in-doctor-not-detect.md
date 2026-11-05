---
id: "0061"
title: "No wake path is a doctor warning; detect shows it only as a problem"
status: accepted
date: 2026-11-04
source: "change 2026-11-director-wake (owner, while building slice 1)"
sections: ["§13.4", "§1.1"]
---

# 0061. No wake path is a doctor warning; detect shows it only as a problem

## Context

`init` writes empty hooks, so every fresh project has no wake path. Criterion 3 of the change makes `doctor` warn about that. `detect` runs `doctor` and passes its warnings on, so every hook-less project would carry a warning line at every session start, even with an attached Director that `wait`s and is never at risk. That breaks principle 1 ("invisible when healthy"; the healthy-project test, §19).

## Decision

`doctor`, the setup check someone runs on purpose, warns whenever no hook would wake a Director. `detect`, the routine check, leaves that warning out, and shows it only when it is a problem: an active run's lease names a harness other than `cli`. A project with no wake path is not fully healthy, so the healthy-project test configures an `on_needs_human` hook, and it checks that `detect` on a hook-less project with an attached Director is still one line.
