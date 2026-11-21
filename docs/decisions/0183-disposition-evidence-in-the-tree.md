---
id: "0183"
title: "A worker's fixed evidence is checked in the working tree, and a claim that fails its check is dropped, not the result"
status: accepted
date: 2026-11-20
source: 'Owner, 2026-11-20, fixing issues/2026-11-20-design-evidence-and-lost-answers.md: "Drop the claim, keep result (Recommended)"'
sections: ["§7.2", "§8.10", "§9.2"]
---

# 0183. Disposition evidence in the working tree; a failed claim is dropped

## Context

In run `r_20261119_ee96`, recipe-builder's second design round marked all 19 audit findings `fixed`, each citing a line of the design document it had just written in its own `result/`. §9.2 says `fixed` evidence is a `file:line` "in the current tree", but intake checked it at the HEAD commit, made before the attempt began. A worker cannot commit (Baton commits after intake), so no honest `fixed` claim on a new document, or on a workspace step's uncommitted change, could pass. Every claim was refused, the whole 30-minute result was rejected, and the step retried with the same impossible check.

The report also asked whether a contract failure the worker cannot fix by retrying should escalate rather than loop. Once the check is corrected, a failed claim is a real worker mistake, such as a wrong line. A worker's claim never closes a finding by itself (§18 #12): the next review decides.

## Decision

1. `fixed` evidence given as `file:line`, and the file of a `rejected` test reference `path::name`, are checked in the working tree as it is when the disposition is checked, uncommitted files included. A worker cites its own result by its path from the project root; result directories are committed at the checkpoint that follows, so the citation stays valid. `rejected` `file:line` evidence keeps the reviewed-commit rule. A commit given as `fixed` evidence must still exist.
2. A worker's disposition that fails its check (evidence that does not exist, or a finding the step was not shown or that is ambiguous) is dropped. The result is not rejected for it: it goes on to its gates as if the claim had not been made. Each dropped claim is recorded on `result_submitted` as `dispositions_dropped [{index, step, finding, disposition, evidence, reasons}]` and shown in the step's record. A malformed `dispositions` entry (bad shape, or `accepted-risk`) is still an envelope error.
3. A Director's `disposition` call with bad evidence is still refused at once: the Director can correct it in the same conversation at no cost.
4. Rejected results and failed gates keep their automatic retries (Decision [0180](0180-worker-failures-escalate.md)).
