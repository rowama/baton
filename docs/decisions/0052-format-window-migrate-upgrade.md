---
id: "0052"
title: "Format families, migrate, upgrade and step-id signatures"
status: accepted
date: 2026-11-03
source: "inline note, §14.2"
sections: ["§14.2", "§5.8"]
---

# 0052. Format families, migrate, upgrade and step-id signatures

## Context

Projects must trial new runtime versions on a branch (§1.1 principle 4) without rewriting history.

## Decision

Stored formats are families (events, lockfile, recipes) with upcasters kept forever; a runtime reads current and previous, refuses older ones naming `migrate` and newer ones naming the launcher. `migrate` writes upcast copies alongside and records `migrated`, in its own commit. `upgrade` runs under its target and changes only the lockfile and skills. Vendoring that changes a kept step id's signature or reuses a retired id needs the owner's words. Recipe upgrade mid-run is deferred.
