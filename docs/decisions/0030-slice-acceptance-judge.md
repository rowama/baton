---
id: "0030"
title: "software-feature's slice acceptance is a judge"
status: accepted
date: 2026-11-03
source: "inline note, §5.1"
sections: ["§5.1", "§5.7"]
---

# 0030. software-feature's slice acceptance is a judge

## Context

In the original §5.1 example `accept` had no gate, so a person answering `accepted: false` still passed the slice.

## Decision

`accept` has a human gate and is named in `repeat_until`; rejecting it starts the next iteration at `implement` with the owner's note.
