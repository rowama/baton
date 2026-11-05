---
id: "0046"
title: "Resolving a platform incident readies its step once"
status: accepted
date: 2026-11-03
source: "inline note, §12.3"
sections: ["§12.3", "§8.8"]
---

# 0046. Resolving a platform incident readies its step once

## Context

A platform failure gets at most one automatic retry, and only after a fix is recorded (§8.8); the mechanism was open.

## Decision

`platform_incident resolve <id> --fix` records the fix and readies each step that incident escalated, once, with a fresh attempt budget. A new failure opens a new incident; the owner's `decide <step> retry` still works while it is open.
