---
id: "0031"
title: "questions_for_human is structured"
status: accepted
date: 2026-11-04
source: "inline note, §7.2"
sections: ["§7.2", "§13.8"]
---

# 0031. questions_for_human is structured

## Context

Free-text questions forced the Director to read subject matter to hold a conversation, and were forwarded to the owner unconverted.

## Decision

Each question is `{id, ask, why, best_guess?, options?, multi_select?, priority?}` in the owner's terms. A bare string is still accepted and normalized, so existing workers keep working.
