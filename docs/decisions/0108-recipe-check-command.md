---
id: "0108"
title: "Ledger and instance-leak checks are a built-in command, baton recipe check"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§2", "§5.3", "§13.2"]
---

# 0108. Ledger and instance-leak checks are a built-in command, baton recipe check

## Context

Script gates run in the project root under a reduced environment, and a catalog recipe is not vendored, so a checker shipped in a recipe's `static/` is not on disk at gate time. The ledger and instance-leak rules are deterministic and needed by every generated recipe (ground rule 2).

## Decision

`baton recipe check <package> --ledger <file>` runs the ledger rules (no `open` entry; every `confirmed` entry carries the owner's words) and the instance-leak rule (no `instance` value in the package's prompts or static files), and exits non-zero with one line per problem. `generate` calls it as a script gate. It is a CLI-only helper for gates, not a Director call, so it has no MCP tool; it adds no concept (§2), only a command listed with `plan` and `check`. The ledger schema is shipped with the runtime and the recipe's `schemas/ledger.json` is its copy.
