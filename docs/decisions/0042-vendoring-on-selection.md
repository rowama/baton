---
id: "0042"
title: "Framing vendors a catalog recipe on selection"
status: accepted
date: 2026-11-04
source: "inline note, §11.6"
sections: ["§11.6", "§15.2"]
---

# 0042. Framing vendors a catalog recipe on selection

## Context

A framed part may propose a recipe that the project has not vendored yet.

## Decision

A vendored version is used when there is one; otherwise a catalog recipe (shipped with the runtime) of that id is vendored as part of applying the selection. The owner's selection is the approval. Any other recipe is vendored only by `vendor`.
