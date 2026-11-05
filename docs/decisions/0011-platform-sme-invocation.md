---
id: "0011"
title: "Baton invokes no platform SME itself; on_platform_failure does"
status: accepted
date: 2026-11-02
source: "§18 #11"
sections: ["§8.7"]
---

# 0011. Baton invokes no platform SME itself; on_platform_failure does

## Context

Automatic platform-SME invocation on platform failures.

Suggested: only when `on_platform_failure` is configured.

## Decision

as suggested; Baton invokes no SME itself. A `platform` failure fires `on_platform_failure` when configured, otherwise `on_complete` (§8.7).
