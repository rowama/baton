---
id: "0149"
title: "Baton has one software recipe, eng-process, tailored deeply enough for every scale"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: I only want two software related recipes if there is a very strong reason. I prefer one process with deep tailoring that keeps the process at all scale levels familiar."
sections: ["§5.7"]
---

# 0149. Baton has one software recipe, eng-process, tailored deeply enough for every scale

## Context

The catalog ships `software-feature`, and `2026-11-eng-process-recipe` proposes a fuller engineering recipe. Keeping both would give owners a lightweight and a rigorous software process to choose between, each with its own shape.

## Decision

eng-process is Baton's one software recipe, tailored on its axes (Decisions 0144, 0147) from a personal utility to a consequential production system, so the process is familiar at every scale. A second software recipe needs a very strong reason. `software-feature` is retired once eng-process's lowest ratings cover what it does; projects with `software-feature` pinned keep it (§5.8).
