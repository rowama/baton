---
id: "0188"
title: "Self-improvement: four slices now, the rest held; local patches, the circuit breaker, upstream-only skill fixes, promotion, digest, sharing and late defects settled"
status: accepted
date: 2026-11-22
source: 'Owner, 2026-11-22: "All as suggested" (to the nine questions put for 2026-11-self-improvement)'
sections: ["§12.4", "§8.8", "§5.1", "§13.3"]
---

# 0188. Self-improvement: four slices now, the rest held; local patches, the circuit breaker, upstream-only skill fixes, promotion, digest, sharing and late defects settled

## Context

[2026-11-self-improvement](../changes/2026-11-self-improvement.md) was on hold at the discussion stage with seven open questions. [2026-11-process-stats](../changes/2026-11-process-stats.md), on which it depended, is done, and moved one more question here (Decision [0187](0187-process-stats-details.md), item 3: defects found late). The owner asked to work on self-improvement, which raised a question of scope. The nine questions were put in one batch, each with a suggested answer; the owner accepted every suggestion.

## Decision

0. **Scope.** The hold is lifted for four slices: capturing cases with a repro bundle, the circuit breaker, contract checks before runs, and baselines with detectors. Replay, local lines with the digest, sharing upstream and the analyst stay on hold, each to become a change of its own later.
1. **Temporary local patch: yes, narrowly.** Offered only for a case classified as a contract contradiction, and only when the patch makes a check less strict, never stricter or different in meaning. Applied on the owner's one-line yes, recorded in the run, dropped automatically when upstream fixes it. (It needs the overlay of local lines, so it arrives with them.)
2. **Circuit breaker.** The same rejection or gate failure (same check, same reason) on two consecutive attempts stops the retries and escalates as one choice, with the spend so far. A different reason keeps retrying. This extends Decision [0180](0180-worker-failures-escalate.md) and narrows [0183](0183-disposition-evidence-in-the-tree.md), item 4.
3. **Director skill: upstream only.** It is improved through cases and reports fixed by the maintainer; local lines cover recipes and the owner's communication preferences.
4. **Promotion of a wording candidate.** All replayed cases pass, plus 3 clean real uses; a recurrence rolls it back. The number is a machine setting.
5. **The digest.** The Director gives it at the end of a run or at a natural break; it is also kept in the project for a detached Director to pick up.
6. **Sharing upstream.** Only a case's shape (step, kind, measures, the reaction, the local fix), never the subject matter or the owner's words, shown to the owner exactly as it would be sent.
7. **Baselines once other owners exist:** left open until shared cases exist.
8. **Defects found late, counted deterministically.** A review finding counts as a late defect against an earlier step when its `location` names a file that earlier step produced and that step had already passed its own review. A finding whose location matches no such file is not counted.
