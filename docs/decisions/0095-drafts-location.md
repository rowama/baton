---
id: "0095"
title: "Generated recipe drafts live in recipes/drafts/<run slug>/"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1", "§15.3"]
---

# 0095. Generated recipe drafts live in recipes/drafts/<run slug>/

## Context

A finished package must live somewhere between `generate` and vendoring, separate from vendored recipes.

## Decision

`generate` commits the package to `recipes/drafts/<run slug>/` in the project. No new `project.yaml` key. Alternative not taken: a `paths.recipes` key, which adds a setting the owner might have to touch.
