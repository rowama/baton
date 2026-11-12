---
id: "0131"
title: "The Director can read the manual through a read-only `help` action"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§13.2", "§13.7"]
---

# 0131. The Director can read the manual through a read-only `help` action

## Context

Open question 5. The owner (2026-11-11) concurred with the suggestion.

## Decision

- One read-only `help` action in the CLI and MCP returns a topic's text (and lists or searches topics); it needs no owner decision (§13.7). The Director skill says to answer "how do I..." from it, not from the Director's own inference.
