---
id: "0141"
title: "Implementation options are discovered before recipe design when they change its structure, otherwise within the generated recipe"
status: accepted
date: 2026-11-12
source: "Owner, 2026-11-12: I like the timing distinctions. I think we're on the same page, so please produce a change proposal for this also."
sections: ["§5.7", "§12.1"]
---

# 0141. Implementation options are discovered before recipe design when they change its structure, otherwise within the generated recipe

## Context

An owner may describe a business-process outcome without knowing which products, frameworks, standards or manual approaches could implement it. Recipe-builder has research and a reusable research/options/decision pattern, but it does not explicitly require discovery of implementation options or decide when it belongs. Project SME consultation alone does not make discovery required recipe work.

Following decision 0140, the owner asked how Baton could help discover implementations as well as develop a process targeting them. The owner agreed with recognizing discovery needs during recipe-building and explicitly accepted the timing distinction below.

## Decision

- Recipe-builder identifies unresolved implementation choices that matter to the goal. Signals such as recurrence, integrations, durable state, human approvals, regulatory requirements and data processing identify questions to investigate, not fixed keyword-to-technology mappings.
- If a choice changes the stages, worker requirements, artifacts or acceptance checks needed for the agreed scope, investigate it during recipe-building, early enough to shape the recipe. Settle consequential owner choices before finalizing the affected design.
- If the recipe can already accommodate the alternatives, include discovery and decision work in the generated recipe before dependent work. A reusable recipe need not choose every future project's target during authoring.
- Distinguish a named target that is a firm constraint from a preference or example. Research plausible approaches against the requirements with sources and tradeoffs, considering existing products, frameworks, standards, manual procedures and custom development where relevant. The owner need not supply candidate names.
- Preserve the owner's control of generality and consequential choices. Recommendations and inferred facts are not owner decisions. Avoid unnecessary comparison when the approach is settled or no material choice remains.
- The builder defines the development process; workers executing it perform project-specific research. A project SME can contribute domain advice, a platform SME infrastructure constraints, and the process SME advice about Baton and recipes. Existing consultation and promotion rules continue to apply.

Prefer extending the existing profile/research/design/audit responsibilities and patterns. Exact contracts and flow remain proposed implementation work. The Director cannot add stages during execution: uncertainty must be resolved or explicitly accommodated in the recipe. This records approval of the direction and timing policy; the owner requested a proposal, not implementation.
