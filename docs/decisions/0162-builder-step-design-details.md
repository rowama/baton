---
id: "0162"
title: "Builder step design: six traits, two rating axes, standard-library simple tools, examples in the tool's folder with file inputs beside them"
status: accepted
date: 2026-11-16
source: "Owner, 2026-11-16: \"Accept all.\" (the ten suggested answers of 2026-11-builder-step-design, and its Request and Design)."
sections: ["§5.5", "§5.7", "§5.9", "§13.1"]
---

# 0162. Builder step design: six traits, two rating axes, standard-library simple tools, examples in the tool's folder with file inputs beside them

## Context

`2026-11-builder-step-design` carries Decision [0155](0155-recipe-builder-builds-software.md) into `recipe-builder@4`: the builder characterizes each stage, picks the simplest means that can do it, and writes simple tools within a ceiling the owner sets. The change doc raised nine open questions; checking it against what `2026-11-tool-steps` built raised a tenth (a tool's inputs file names files, Decision [0159](0159-tool-runs-env-inputs-build-outputs.md), so an example needs a way to supply them). Each was put to the owner with a suggested answer, and the owner accepted all of them.

## Decision

1. **Six traits per stage:** whether complete rules can be written (`complete`, `partial`, `none`), the input's form (`structured`, `open`), whether the same input must give the same result (`required`, `not_required`), its effect (`none`, `reversible`, `irreversible`), whether a correct result can still be wrong about the world (`certain`, `uncertain`), and how the output can be checked (`mechanical`, `source`, `judgment`). Each changes either the doer or what the check must establish.
2. **Existing software is not yet a doer.** Until the external-software change, a stage existing software could do is a discovery record and is done another way.
3. **The builder is rated on two axes:** `approach: [simple, standard, complex]` and `software: [none, simple]`. `2026-11-quick-runs` adds `quick` below `simple` (with `confirm_lowest`), and the profile schema then requires `software: none` with `quick`; the engineered-tools change adds `engineered` above `simple`.
4. **A `simple` tool** is one file, uses the Python standard library only, reaches no network and needs no secrets. Packages come with `engineered`.
5. **Examples live in the tool's folder:** `tools/<id>/examples/<name>/input.json` and `expected.json`, plus `expected/<artifact>` for an artifact compared byte for byte. They are hashed with the recipe. `baton tools test <package>` is built in this change, as its first slice.
6. **At a ceiling of `none`, one rating signal per run** on `software`, however many stages software could do, and the list in the walkthrough.
7. **`profile` recommends `software: simple`** when the idea shows rule-like work (calculating, converting, matching, recording), otherwise `none`; the owner approves either way.
8. **For a process meant to run elsewhere,** traits and the recommended doer are recorded for every stage; tools are built only for stages Baton runs.
9. **A `simple` tool's examples are drafted by the builder** from what the owner said, and the owner approves them with the design. Examples the owner supplies as files are required only for `engineered` tools (0155 item 5).
10. **An example's file inputs sit beside its `input.json`,** as `examples/<name>/inputs/<input name>.<ext>`. JSON inputs stay in `input.json`. `baton tools test` builds the tool's inputs file from both exactly as dispatch does (0159 item 2), so an example exercises the same path as a run.
