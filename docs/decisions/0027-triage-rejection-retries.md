---
id: "0027"
title: "Rejecting a triage level retries triage"
status: accepted
date: 2026-11-02
source: "inline note, §5.5"
sections: ["§5.5"]
---

# 0027. Rejecting a triage level retries triage

## Context

Above the lowest level the owner approves the triage level (§18 #8). What a rejection does was open.

## Decision

Rejecting fails the implicit `triage` gate; triage gets another attempt with the owner's note as feedback.
