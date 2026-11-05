---
id: "0029"
title: "fit-check's describe infers first and asks only what it cannot infer"
status: accepted
date: 2026-11-04
source: "inline note, §5.7"
sections: ["§5.7"]
---

# 0029. fit-check's describe infers first and asks only what it cannot infer

## Context

In the first real-project run, `describe` asked five abstract rubric questions at once that the owner could not answer.

## Decision

`describe` fills the profile from the idea as far as it reasonably can, lists each inference under `assumptions` for the Director to confirm, and asks only the rest as structured questions in the owner's terms. An idea holding several kinds of work returns `blocked` with one question offering the parts, and the Director suggests framing. `fit-check` became version 2.
