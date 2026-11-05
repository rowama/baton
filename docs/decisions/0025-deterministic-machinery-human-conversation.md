---
id: "0025"
title: "Deterministic machinery, human conversation"
status: accepted
date: 2026-11-04
source: "inline note, §1.1"
sections: ["§1.1", "§13.8"]
---

# 0025. Deterministic machinery, human conversation

## Context

The first real-project run (a pure-water vending business) showed the owner abstract rubric questions, plumbing reports and bare decision names. The runtime's determinism was right; its human side was missing.

## Decision

Principle 5: two layers kept separate. The runtime and everything crossing into it stay structured and deterministic; the owner's side is a conversation run by the Director in the owner's terms, with no Baton vocabulary. The seam is the confirm-back: nothing understood from conversation is recorded until the owner confirms it.
