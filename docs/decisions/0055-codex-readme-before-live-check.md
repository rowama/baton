---
id: "0055"
title: "The Codex README section ships before the live check, marked unverified"
status: accepted
date: 2026-11-04
source: "change 2026-11-codex-director-sandbox, slice 2"
sections: ["§13.2"]
---

# 0055. The Codex README section ships before the live check, marked unverified

## Context

The change doc's slice 2 adds a README section "Using Codex as Director", but its Risk paragraph says the README may not recommend MCP for Codex until the slice 3 live test passes on Linux: the claim that Codex runs MCP servers outside its sandbox rests on a maintainer's statement and one third-party macOS report.

## Decision

Write the section in slice 2 with a one-line note that it is not yet confirmed by a live run. Slice 3 removes the note if the live test passes, or reworks the section (and reopens decision 0053) if it fails.
