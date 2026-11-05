---
id: "0001"
title: "Inputs too large for an API worker are a hard error"
status: accepted
date: 2026-11-02
source: "§18 #1"
sections: ["§6.3"]
---

# 0001. Inputs too large for an API worker are a hard error

## Context

Large inputs for API workers: hard error, auto-chunking, or require a file-capable worker?

Suggested: hard error.

## Decision

hard error, as suggested (§6.3).
