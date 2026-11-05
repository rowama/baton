---
id: "0035"
title: "A disposition takes effect at the next evaluation"
status: accepted
date: 2026-11-02
source: "inline note, §9.2"
sections: ["§9.2"]
---

# 0035. A disposition takes effect at the next evaluation

## Context

Whether a failed findings gate should wait for dispositions before retrying was open.

## Decision

Nothing waits for dispositions: a failed gate retries or ends the iteration at once, and a disposition takes effect at the next evaluation. Accepting the current failure as is takes a waiver.
