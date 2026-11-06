---
id: "0081"
title: "Live verification runs only on request; unverified generated profiles are eligible, flagged"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§6.1", "§13.4"]
---

# 0081. Live verification runs only on request; unverified generated profiles are eligible, flagged

## Context

A no-op round trip proves a model is usable on the owner's account but costs quota; a provider may list models a plan does not include.

## Decision

- A live check runs only on `baton workers setup --verify [<profile>…]`; that call is the owner's authorization for that run. Each check is one minimal round trip.
- Each generated profile records its availability as `declared` (by the owner), `detected` (local discovery) or `verified` (a successful live check, with its date and tool version).
- Unverified generated profiles are eligible for dispatch, as hand-written ones are; `workers status` and `doctor` show them as unverified.
- A failed live check keeps the profile out of the generated set and explains why in plain words, with login or install instructions where they apply.
