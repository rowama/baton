---
id: "0147"
title: "Tailoring axes: additive format, guarded lowest ratings, rating signals wait on the owner"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: Accept all."
sections: ["§5.1", "§5.3", "§5.5", "§7.2"]
---

# 0147. Tailoring axes: additive format, guarded lowest ratings, rating signals wait on the owner

## Context

Writing `2026-11-tailoring-axes` from Decision 0144 raised six questions, including the format question 0144 left to Design. The suggested answers were put to the owner in one batch.

## Decision

1. **Format.** Additive within `baton-recipe/1`: `complexity.levels` and `complexity.axes` are mutually exclusive, and the loader tells the forms apart by key. No migration.
2. **Guarded lowest.** All axes at their lowest still applies at once (0144), except that a recipe may mark an axis `confirm_lowest: true`, whose lowest rating also asks the owner. eng-process marks its assurance axis.
3. **Rating signals.** A worker's `rating_signal` becomes a pending owner decision (`rating:<axis>`, options `retriage` or `dismiss`, with the worker's reason). It blocks no step and does not hold completion.
4. **No AND.** `applies_to` is OR across axes and OR within an axis's values. AND only if a real recipe needs it.
5. **Recipe builder.** Keeps generating one-axis recipes in this change; generating axes is a follow-up after eng-process.
6. **Nothing else is rating-driven.** Only `applies_to`, plus the ratings in every packet.
