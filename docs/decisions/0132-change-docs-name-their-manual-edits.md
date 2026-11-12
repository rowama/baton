---
id: "0132"
title: "Every change doc names its manual edits, or says why there are none"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§0", "§19"]
---

# 0132. Every change doc names its manual edits, or says why there are none

## Context

Open question 6. The owner (2026-11-11) concurred with the suggestion.

## Decision

- Every change doc has a `manual:` front-matter field listing the manual files it edits, or `none: <reason>`, and a `### Manual edits` heading under Design. A test refuses `status: done` without it for every change from this one on (changes already `done` are not checked). §0 gets a ground rule and §19 the manual's coverage in place of the README list.
