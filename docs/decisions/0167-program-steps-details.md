---
id: "0167"
title: "Programs rename: the format stays baton-recipe/1, shipped recipes edited in place, modules renamed, old environments left alone, completeness checked by one recorded search"
status: accepted
date: 2026-11-17
source: "Owner, 2026-11-17: \"Concur with commit and all question suggestions.\""
sections: ["§4.4", "§5.3", "§5.7", "§5.9", "§14"]
---

# 0167. Programs rename: the format stays baton-recipe/1, shipped recipes edited in place, modules renamed, old environments left alone, completeness checked by one recorded search

## Context

`2026-11-program-steps` carries out Decision [0166](0166-tools-renamed-programs.md): the §5.9 tool becomes a program, outright. The change doc raised five open questions, each with a suggested answer. Checked before asking (the **[VERIFY]** of question 2): a recipe's hash is compared only with the copy recorded in a project's own lockfile (`vendor` refuses different content under a vendored `id@version`, `vendor.version_exists`; loading refuses a vendored copy that differs from its lock entry, `recipe.lock_mismatch`). There is no catalog-wide record of a shipped recipe's hash, so editing a shipped recipe in place affects only a project that has already vendored that version, and none has. The owner accepted every suggested answer.

## Decision

1. **The format stays `baton-recipe/1`.** Renaming the `tool:` key and the `tools/` folder would normally mean a new format version; this is a deliberate exception, made before release, because a new version would add a migration with nothing to migrate.
2. **The shipped recipes are edited in place.** `recipe-builder` stays `@6` and `spreadsheet-reconcile` keeps its version. No project has vendored them with tool steps; `2026-11-ai-delegates` already plans `recipe-builder@7`.
3. **The Python modules are renamed.** `tools.py`, `tool_env.py`, `tool_runner.py`, `tool_test.py` and `adapters/tool.py` become `programs.py`, `program_env.py`, `program_runner.py`, `program_test.py` and `adapters/program.py`, and the test files for §5.9 likewise. `tool_evidence.py`, `test_tool_evidence.py` and `test_harness_tools.py` keep their names: they are about harness tools.
4. **Environments already built under `~/.baton/tools/` are left alone.** They are no longer used; `programs setup` builds new ones under `~/.baton/programs/`. The administrator's topic on files and paths says the old folder can be deleted. Baton never deletes the owner's files unasked.
5. **Completeness is checked by one recorded search, not a permanent test.** The last slice's Log records a search for the old names (`tool:` step keys, `tools/<id>`, `tool.yaml`, `tool.*` codes, `tools setup|test|examples`, `dispatched.tool`) and lists each remaining hit with the sense of "tool" it keeps. A permanent test would need an allowlist as long as the senses it protects.
