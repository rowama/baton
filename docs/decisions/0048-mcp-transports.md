---
id: "0048"
title: "MCP over stdio, and over loopback HTTP with a token"
status: accepted
date: 2026-11-03
source: "inline note, §13.2"
sections: ["§13.2"]
---

# 0048. MCP over stdio, and over loopback HTTP with a token

## Context

MCP is an equal Director interface; a daemon is out of bounds (§0 rule 3) and remote Directors may lack a shell.

## Decision

stdio by default (the harness starts `baton mcp` per session). HTTP only as an owner-started foreground process, loopback-only, with a bearer token from `~/.baton/mcp.yaml`; remote access goes through a TLS proxy or tunnel of the owner's choice.
