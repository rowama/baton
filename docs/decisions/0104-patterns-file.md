---
id: "0104"
title: "static/patterns.md is a design input and an audit rubric, enforced"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1"]
---

# 0104. static/patterns.md is a design input and an audit rubric, enforced

## Context

Reusable process shapes keep designs consistent; advice that nothing checks is ignored.

## Decision

`static/patterns.md` holds reusable shapes (research → options → decide → plan → execute → review; bounded design/audit loops; failure dispositions). `design` consumes it and `audit` checks the design against it, blocking on high. It is the interim broad recipe in prose; a proven pattern may later become a loadable broad recipe.
