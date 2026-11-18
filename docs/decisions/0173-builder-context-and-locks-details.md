---
id: "0173"
title: "Approved file sets: content hashes of the matching files, binding every later step of the run, released when the step is revised; recipe-builder's context role in the next version; a retired recipe stays listed, marked"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"accept all\" (the five suggested answers of 2026-11-builder-context-and-locks)"
sections: ["§5.3", "§5.7", "§9.4", "§13.1"]
---

# 0173. Approved file sets: content hashes of the matching files, binding every later step of the run, released when the step is revised; recipe-builder's context role in the next version; a retired recipe stays listed, marked

## Context

`2026-11-builder-context-and-locks` fills three gaps that writing `2026-11-software-recipe` found (Decision [0172](0172-software-recipe.md)): recipe-builder takes no reference documents, nothing protects a set of files once the owner has approved it (§9.4 deferred it), and a recipe cannot say it is retired (Decision [0149](0149-one-software-recipe.md)). The change asked five questions.

## Decision

1. **A lock compares content.** When the owner approves a human gate that declares `locks`, Baton records the sha256 of every file matching its globs. A later edit, a new matching file or a deleted file is a difference. Paths outside the project, `.git` and `.baton` are never matched: the rules `protect` uses (§9.4), extended across steps.
2. **A lock binds every later step of the run**, including later instances of a group. A step meant to change a locked file needs the owner's approval of the change. A lock exists to stop silent change, so an intended change is the owner's decision, made explicitly.
3. **A lock is released with its approval.** When the gate's step is revised (or goes stale and is re-run), its lock is released; approving the gate again locks the set afresh.
4. **recipe-builder's `context` role goes in its next version, in landing order.** Today that is `recipe-builder@7`; `2026-11-ai-delegates` then takes the version after it.
5. **A retired recipe stays in `recipes()`**, marked retired with its replacement, so an owner who has it pinned sees why it is no longer proposed.
