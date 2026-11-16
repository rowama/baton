---
id: "0160"
title: "Tool steps: the first shipped recipe with a tool is spreadsheet-reconcile"
status: accepted
date: 2026-11-16
source: "Owner, 2026-11-16: chose \"spreadsheet-reconcile (Recommended)\" for 2026-11-tool-steps Slice 3."
sections: ["§5.7", "§5.9"]
---

# 0160. Tool steps: the first shipped recipe with a tool is spreadsheet-reconcile

## Context

The Plan of `2026-11-tool-steps` called for "a shipped example recipe with one tool step". A shipped recipe joins the catalog: framing and project review may propose it to owners, and it has its own manual topic. A toy such as the test fixture's backtest does not belong there. The alternatives were put to the owner: a small, genuinely useful catalog recipe, or none yet (the example stays a test fixture).

## Decision

Ship **`spreadsheet-reconcile`**: a tool compares two CSV files on a key column and lists the added, removed and changed rows (deterministic, no model cost); an AI worker explains the differences in plain words; the owner accepts the report. It joins the catalog with its own manual topic. It is built as its own slice, after readiness and approval.
