---
id: "0070"
title: "The owner's answer to the notes-file offer is a project decision"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§13.1", "§8.2"]
---

# 0070. The owner's answer to the notes-file offer is a project decision

## Context

0065 has the Director offer the notes file once. "Once" must hold across sessions and Directors.

## Decision

The answer is recorded in the project event log as `human_decision {kind: notes, accepted, note}`, so "offer once" is enforced in code: `note` reports that the file should be offered until the owner has answered, and that it was declined after a no. The owner can still accept later (`baton note --keep-file yes`).
