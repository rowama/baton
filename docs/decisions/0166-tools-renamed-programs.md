---
id: "0166"
title: "A recipe's tool is renamed a program, outright; \"tool\" keeps its industry meaning of something a model or harness calls"
status: accepted
date: 2026-11-17
source: "Owner, 2026-11-17: \"It seems to me that the 5.9 usage is the odd one out.\"; \"Program.\"; \"Baton is still in development and not being used. No recipes have been developed using 5.9, so the impact to existing recipes is negligible.\""
sections: ["§2", "§5.9", "§6.3", "§8.2"]
---

# 0166. A recipe's tool is renamed a program, outright; "tool" keeps its industry meaning of something a model or harness calls

## Context

Decision [0154](0154-tool-steps.md) named a script a recipe ships, which does a step with no model, a **tool** (§5.9). Baton uses the same word in three other senses, each matching how agent software uses it: a model's tool calling (LiteLLM's `tools=`, the `tool_use` capability), a harness's built-in tools (the tooling capabilities and tool maps, Decision [0085](0085-harness-tool-maps.md)), and MCP tools. Writing out `2026-11-step-tool-harness`, which offers tools to a model inside an API worker's attempt, showed the collision: one word would mean both "done with no model" and "called by a model", and the owner-facing distinction between AI and non-AI work that Decision [0155](0155-recipe-builder-builds-software.md) relies on would blur.

## Decision

1. **The §5.9 concept is a program.** A program is code a recipe ships that does a step with no model. Every current name for it changes: the step key, the package folder and its file, the commands, the adapter, the records and the error codes, the builder's designs, the design docs, the manual and the Director skill.
2. **"Tool" keeps its industry meaning** in Baton: something a model or a harness calls (tool calling, harness tools and tooling capabilities, MCP tools), and maintainers' own utilities in the repository's `tools/` folder.
3. **Renamed outright, with no alias.** Baton is in development and has no users; no recipe outside the repository uses §5.9. The loader does not accept the old spelling as a synonym.
4. **History is not rewritten.** Decision records and finished change docs keep "tool" as written; this record maps the old names to the new.
5. **Done in its own change** ([2026-11-program-steps](../changes/2026-11-program-steps.md)), before `2026-11-step-tool-harness` and `2026-11-ai-delegates` are built, so neither is built on the old word.
