---
id: "0164"
title: "Engineered tools: three examples per tool, from the owner or drafted and approved, placed by their own step, a bounded loop, mechanical budget rules, every run repeated"
status: accepted
date: 2026-11-17
source: "Owner, 2026-11-17: \"2-three without warning; against advice, a user can elect to provide no examples and the builder will generate filler examples than ask for the user to approve them before moving on.  3,4-Two paths, one for user supplied examples and one for AI generated examples.  Accept all.\""
sections: ["§5.7", "§5.9", "§13.1", "§13.3"]
---

# 0164. Engineered tools: three examples per tool, from the owner or drafted and approved, placed by their own step, a bounded loop, mechanical budget rules, every run repeated

## Context

`2026-11-builder-engineered-tools` carries Decision [0155](0155-recipe-builder-builds-software.md) item 5 into the recipe builder: tools that need real engineering are built from the owner's examples in a bounded loop. The change doc raised nine open questions. Checking them against `recipe-builder@5` as `2026-11-builder-step-design` and `2026-11-quick-runs` left it revised three suggested answers (1, 4 and 7) and raised a tenth:

- A role is bound once for the whole run, so a tool's build could not wait on its own examples while other tools went ahead without per-instance roles, and one example is several files.
- `generate` cannot both require the examples role and run at `software: simple`, so placing the examples needed a step of its own.
- Revising `design` is refused, because it is inside the `shape` group (Decision [0034](0034-revise-in-groups-deferred.md)), so simplifying a tool revises the `foreach` source.

The owner accepted every suggested answer and changed two: question 2 (an owner may choose not to supply examples) and questions 3 and 4 (two paths for examples).

## Decision

1. **The owner's examples reach the builder as project documents.** The owner puts each example's files under `examples/<tool>/<example>/` in the project (the input files and the expected result). The Director says what each tool needs, from the design's `examples_needed`, and makes the folders. The owner attests the files with their words, and the run binds them to one `many` role, `examples`. The build waits until they are bound. Per-instance roles are not built.
2. **Three examples per tool, one of them a case the owner considers awkward.** Three is a minimum, with no softer mode that warns and lets fewer through. An owner may choose, against the builder's advice and recorded with their words, to supply fewer or none: the builder then drafts the missing ones (filler, including the awkward case) and the owner approves each one before the build starts. A drafted example counts only once the owner has approved it.
3. **Examples come after the design is approved, before the build.** At `software: engineered` the design's approval gate always applies, at any `approach`.
4. **Two paths, one step.** For each tool, the owner chooses whether to supply its examples or have them drafted (question 2). A new step, `examples`, runs at `engineered` only, after `generate`. It copies the owner's files byte for byte into the tool's `examples/` folder, writes `expected.json` only from results the owner stated, drafts any examples the owner chose not to supply, and writes no code. A check confirms that every copied file is identical to its bound document. The owner approves the drafted examples, and any `expected.json` written from their words, before the build. The worker that implements a tool must be from a different vendor than the `examples` step's worker.
5. **The implementing worker may add its own tests** in the tool's folder. Only the owner's examples, supplied or approved, decide acceptance.
6. **`baton recipe check` enforces of the budget:** one entry command; reach as declared; a size cap of 600 lines across the tool's files, above which the audit must record why it is still one tool. The tool runner ends the tool's whole process tree after a run and reports any process it found still running. Listening sockets are not checked: no check is reliable on every platform, and the process check covers the real risk.
7. **Simplifying at the limit revises `generate`** with the owner's words as the reason. It does the stage another way and writes the record that `2026-11-builder-step-design` requires. `build_tools` re-expands without that tool, and the instances of unchanged tools keep their results.
8. **The implementing step requires shell and network access,** to resolve packages and lock them with hashes. A tool with no packages needs neither.
9. **A later builder run on a recipe with engineered tools** rebuilds only the tools whose contract or examples changed, and reruns every tool's examples.
10. **Every engineered tool is run twice on each example.** `baton tools test --repeat 2` applies to every engineered tool, whatever the stage's `same result` trait: in a tool, a different result from the same input is a bug.
