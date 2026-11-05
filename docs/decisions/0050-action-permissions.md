---
id: "0050"
title: "Explicit push with categories; permission checks for Director actions"
status: accepted
date: 2026-11-03
source: "inline note, §13.7"
sections: ["§13.7"]
---

# 0050. Explicit push with categories; permission checks for Director actions

## Context

Action permissions bound what the runtime and Director do to the repo and its remotes; how pushes are categorized and how `ask` is settled were open.

## Decision

Nothing pushes automatically and `push` never forces. Commits are sorted into `docs_only`, `after_verified` or `other`; `deny` is refused, `allow` records `permission_used`, `ask` returns `needs_owner` and is settled by repeating the call with `--approved` and the owner's words. `permission <action>` applies the same rule to tag, merge, deploy and force push. Defaults add `.baton/project/**` to `docs_only_globs`.
