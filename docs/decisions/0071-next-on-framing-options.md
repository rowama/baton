---
id: "0071"
title: "next is an optional option field; framing's options carry it first"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§13.1", "§11.6"]
---

# 0071. next is an optional option field; framing's options carry it first

## Context

The change asks for decision options to gain `next`: what choosing the option triggers, computed from the record. Every option already carries a static `effect` from `labels.yaml`. For most kinds (escalations, blocked steps, publish conflicts, drift) a computed `next` would repeat that effect; framing is where the outcome depends on the record.

## Decision

`next` is an optional field of a decision option, `[{decision, label, effect, next?}]`, added by any kind whose outcome depends on the record. In this change only framing's options carry it: `select` lists each part with what choosing it starts, and `reject` says the breakdown is redone. Other kinds may add it later.
