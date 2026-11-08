---
id: "0087"
title: "structured_output is absent after three schema-gate failures in a row on one profile"
status: accepted
date: 2026-11-08
source: "change 2026-11-capability-confidence (owner, 2026-11-08)"
sections: ["§6.1", "§9.1"]
---

# 0087. structured_output is absent after three schema-gate failures in a row on one profile

## Context

`structured_output` is a model-quality capability: one failed schema gate may be the prompt's fault, not the model's. Most steps require it, so marking it absent too readily would starve routing.

## Decision

- Three schema-gate failures in a row on one profile, counted machine-wide across projects, mark its `structured_output` `absent`. A passed schema gate on that profile resets the count (Open question 1, owner, 2026-11-08).
- One failure changes nothing. Other model-quality capabilities (`technical_reasoning`, `long_form_writing`) are never changed automatically.
