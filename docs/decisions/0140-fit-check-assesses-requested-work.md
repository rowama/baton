---
id: "0140"
title: "Fit-check assesses the requested work and can recommend against Baton for any unsuitable goal"
status: accepted
date: 2026-11-12
source: "Owner, 2026-11-12: Concur with your recommendations. Create a proper change proposal for this."
sections: ["§5.7", "§11.6"]
---

# 0140. Fit-check assesses the requested work and can recommend against Baton for any unsuitable goal

## Context

Fit-check v4 offers `fits`, `fits_per_occurrence` and `operations_engine`. Its negative branch assumes the alternative is an operations engine and directs the owner to build software. It does not offer a general recommendation against Baton. Its occurrence-based profile can conflate developing a business process with executing that process.

The owner intends Baton to support projects that develop processes for external execution, including workflows targeting n8n, Temporal or LangGraph, BPMN/CMMN processes, and custom combinations of SOPs, artifacts, templates and software. The characteristics of the finished process must not disqualify the development project. These are examples of possible deliverables, not endorsements or a fixed catalog of targets.

## Decision

- Assess the work the owner asks Baton to coordinate. Establish whether that is developing or improving a process, executing it, or both. Assess distinct development and execution work separately; infer from clear wording and ask only when unresolved.
- Developing, testing, documenting or improving a business process is eligible Baton project work regardless of how the result will execute. Eligibility is not an automatic recommendation: the coordination and handoff benefits must justify the overhead.
- Replace `operations_engine` in the new fit-check version with `not_recommended`, a general recommendation against Baton for the assessed work. An operations engine is one possible alternative; a script, direct assistant interaction, existing tool or manual procedure may be more appropriate. Do not force every alternative into software development.
- Retain `fits` and `fits_per_occurrence`. Recurring work can fit when each instance benefits from Baton and something external starts its runs; recurrence alone does not disqualify it. An external scheduler does not cure an otherwise unsuitable workload.
- Evaluate the assessed work's own frequency, judgment, dependent reasoning, handoffs, duration, data-processing demands, latency/integration requirements and value of a repository record. Frequency and duration are signals, not standalone cutoffs. The finished system's characteristics are not substituted for the development project's characteristics.
- When execution does not fit, developing a suitable process or system may be offered as a separate next step. Never silently change the owner's goal from execution to development or start that different work on acceptance of the negative verdict alone.

This decision authorizes the policy recorded in the proposal, not implementation. Existing pinned recipes and recorded verdicts retain their meanings. It supersedes 0134's requirement to leave verdicts and rubric unchanged only for the future fit-check version; its optional text context and no-file-reading rules remain.
