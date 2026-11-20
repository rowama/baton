---
id: "0180"
title: "Explicit worker failures escalate for review instead of automatically retrying"
status: accepted
date: 2026-11-19
source: "Owner, 2026-11-19: Escalate explicit worker failures (Recommended)"
sections: ["§8.8", "§8.10"]
---

# 0180. Explicit worker failures escalate for review instead of automatically retrying

## Context

Recipe-builder research reported `failed` because its packet appeared to require an owner decision before it could ask the owner. Automatic retries repeated the same contradiction. There is no structured contract-mismatch failure type; inferring one by parsing the worker's notes would be unreliable.

The owner chose to escalate every explicit worker-reported failure, leaving schema and gate failures on their existing retry paths.

## Decision

A valid result with `status: failed` records `result_rejected` and immediately escalates with reason `worker_failed`, preserving the worker's explanation in the pending decision. It does not automatically retry or open a platform incident. The existing escalation choices allow an explicit retry after review. Schema, envelope, provenance and gate failures keep their existing handling; blocked results keep their structured question path. No classification is inferred from prose.
