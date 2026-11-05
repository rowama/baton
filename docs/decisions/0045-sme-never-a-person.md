---
id: "0045"
title: "An SME is never a person; people are reached through a proxy"
status: accepted
date: 2026-11-03
source: "inline note, §12.1"
sections: ["§12.1"]
---

# 0045. An SME is never a person; people are reached through a proxy

## Context

Some questions need a person's input (a supplier, an inspector), but Baton must never contact anyone.

## Decision

Baton never engages a person as an SME. A person is consulted through a proxy consultation that names them (`--contact`); the proxy drafts what the owner needs and sets `awaiting`; proxies draft, never send. The reply comes back as the next turn, attached by the owner.
