---
id: 2026-11-research-blocked-vs-schema
title: "Research can ask unanswered owner questions, and explicit worker failures pause for review"
status: done
level: standard
decisions: ["0141", "0180"]
touches: [design/packets.md, design/runtime.md]
manual: [recipe-sources/recipe-builder.md, recipes/recipe-builder.md, admin/troubleshooting.md]
---

# Research can ask unanswered owner questions, and explicit worker failures pause for review

## Request

### Problem

The owner requested a fix for `issues/2026-11-19-research-blocked-vs-schema.md`. Recipe-builder research must ask the owner before recording a structural choice as decided, but packet instructions say its output must always match the completed-output schema. Intake already exempts blocked and failed results from that schema. Workers can therefore mistake a valid blocked response for an impossible contract and report failure instead.

### Acceptance criteria

- Packet exit criteria and result instructions explicitly limit output-schema validation to completed results and permit partial output or an empty object for blocked/failed results.
- A before-design comparison can return blocked with structured questions and no owner decision; intake escalates, the confirmed answer reaches the retry, and only decided research reaches design.
- Completed research with an unanswered choice remains invalid; provenance and envelope checks still apply to blocked results.
- Owner documentation explains the research pause and answer/retry flow.
- Explicit worker failures escalate with their explanation and can be retried by decision; schema and gate failures retain automatic retries.

### Open questions

None. The owner chose to escalate explicit worker failures (0180).

## Design

### Doc edits

- `design/packets.md` §7.2: distinguish completed output from partial blocked/failed results.
- `design/runtime.md` §8.1, §8.8 and §8.10: document status-specific intake validation and immediate escalation of explicit worker failures.

### Manual edits

- `manual/recipe-sources/recipe-builder.md` and generated `manual/recipes/recipe-builder.md`: explain the pause for an unanswered choice and the confirmed answer on retry.
- `manual/admin/troubleshooting.md`: explicit failure pauses and review before retry.

### Decisions

- Decision 0141 preserves owner authority over consequential choices. This repair documents existing runtime behavior (the issue's suggested fix 3); no recipe version or pinned package changes are needed.
- Decision 0180: all explicit worker failures escalate for review, without parsing notes.

## Plan

### Clarify and exercise the blocked result contract

- **Outcome:** honest research can ask an unanswered question without claiming an owner decision.
- **Criteria:** packet regressions, intake checks and a scripted research/question/answer/retry run demonstrate the acceptance criteria; quick gate and exact-commit full suite pass.
- **Effort:** S

## Log

### Clarify and exercise the blocked result contract

- **Commit:** 2026-11-research-blocked-vs-schema: clarify partial result contract
- **Summary:** Clarified packet exit criteria and result examples: only completed output must satisfy the step schema and provide required artifacts. Blocked results may keep a researched comparison without fabricating a decision. Intake already had this behavior. Explicit worker failures now escalate as `worker_failed` with their explanation; an explicit retry preserves the failure and owner guidance. Updated the design, manual, packet golden and affected tailoring/interaction tests.
- **Tests:** Packet and intake checks; 377 focused intake, tailoring, interaction, documentation and manual checks passed. The research lifecycle regressions exercise a partial comparison, structured questions, confirmed answers reaching retry, and the decided choice reaching design; completed unanswered research stays rejected. Blocked results still require packet provenance. Quick gate and exact-finish-SHA full-suite evidence are recorded by `tools/testrun.py` in the test ledger.
- **Repair:** `2026-11-research-blocked-vs-schema: repair partial result contract verification`. The full suite found two stale expectations: step-record packet hashes and a program-crash test expecting automatic retry. Regenerated the saved records; the program budget test now uses completed output that fails its schema, preserving coverage of automatic retries, and explicit program failures are tested with both one and two allowed attempts to prove immediate escalation. No production behavior changed in the repair.
- **Review:** Kept research/design/generation schemas strict and pinned recipe packages untouched. No inference from failure prose, no automatic platform incident for explicit worker failures, and no change to gate/schema retry behavior. The initial sandbox suite could not create sockets; verification runs outside that sandbox.
- **Accepted:** Fix requested by the owner, 2026-11-19; explicit-failure escalation selected by the owner in this session (0180).
