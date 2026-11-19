---
id: "0178"
title: "Tiers from evaluations: the Artificial Analysis index decides (strong 50+, standard 25+, per index version), LMArena supports; standard or better grants technical_reasoning; a failed check task is run once more"
status: accepted
date: 2026-11-19
source: "Owner, 2026-11-19: \"Concur on the suggestions\" (the four questions of slice 2 of 2026-11-model-assessment)"
sections: ["§5.6", "§6.4"]
---

# 0178. Tiers from evaluations: the Artificial Analysis index decides (strong 50+, standard 25+, per index version), LMArena supports; standard or better grants technical_reasoning; a failed check task is run once more

## Context

Slice 2 of `2026-11-model-assessment` makes tiers rest on published evaluations (Decisions [0175](0175-model-assessment.md), [0176](0176-model-assessment-details.md), item 1). Research on 2026-11-18 found two independent sources that publish their method: the Artificial Analysis Intelligence Index (v5.0.1; nine evaluations it runs itself, across knowledge work, coding, science and general reasoning) and the LMArena text leaderboard (human pairwise preference votes). Real checks on six OpenRouter models in slice 1 showed a model passing a tool task in one run and failing it in the next, so a single failure decided `absent`.

## Decision

1. **Which evaluations decide.** The Artificial Analysis Intelligence Index decides a tier. LMArena is cited as supporting evidence only: it measures which answers people prefer, not whether they are right.
2. **Thresholds.** On the index: **strong at 50 or above, standard at 25 to 49, basic below 25**. They belong to index version 5.0.1; a new version of the index needs its own thresholds in the mapping, since scores across versions do not compare. With several deciding citations, the tier is the lower of the middle values (the lower median).
3. **What a score grants.** A standard-or-better score on the index also grants `technical_reasoning` (the index is half coding and science). `long_form_writing` never comes from a score.
4. **A failed check task is run once more.** A capability check task that fails its graders is run a second time; the capability is `absent` only if a task fails again, and `verified` otherwise. This amends criterion 3 and Decision 0176, item 2, which made one failure decisive.
