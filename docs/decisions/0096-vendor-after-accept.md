---
id: "0096"
title: "The Director vendors a finished recipe only after the owner accepts, and the builder never vendors"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1", "§11.6"]
---

# 0096. The Director vendors a finished recipe only after the owner accepts, and the builder never vendors

## Context

Vendored recipes are trusted code: their script gates run commands.

## Decision

After `accept`, the Director asks the owner and runs `vendor` on the draft, with the owner's approval recorded as for any vendoring. The builder never vendors on its own.
