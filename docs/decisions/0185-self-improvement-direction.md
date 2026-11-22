---
id: "0185"
title: "Self-improvement: setting changes only through the digest, process statistics extended now, baselines from the owner's own runs"
status: accepted
date: 2026-11-22
source: 'Owner, 2026-11-22: "1-only through the digest. 2-yes, now. 3-my own for now. Incorporate all of your suggestions into the change proposal."'
sections: ["§12.4"]
---

# 0185. Self-improvement: setting changes only through the digest, process statistics extended now, baselines from the owner's own runs

## Context

[2026-11-self-improvement](../changes/2026-11-self-improvement.md) was widened on 2026-11-22 from wording-level fixes for owner confusion to two tracks: Baton learning from what goes wrong (unexpected behaviour, contract contradictions, defects) and from how work goes (efficiency, effectiveness, owner burden, measured). Three questions were put to the owner:

1. Should a step's settings (the tier asked for, timeouts, attempt budget, how much context a packet carries) change automatically once a replay passes, or only through the digest at the end of a run?
2. Should cost, owner burden and outcome be added to the process statistics (`stats`, §12.4) now, as a small change of their own?
3. Who sets the expected baselines that a run's measures are compared against?

## Decision

1. **Setting changes only through the digest.** A change to a step's settings is never applied automatically, even after a passing replay. It is offered in the digest at the end of a run, with its evidence, and applied only on the owner's yes. Automatic application stays limited to what the change doc allows for wording (replay-gated, with undo), and routing keeps its existing automatic behaviour (Decisions 0175, 0179).
2. **Process statistics now.** Cost, owner burden and outcome are added to `stats` as their own change, [2026-11-process-stats](../changes/2026-11-process-stats.md), ahead of the rest of self-improvement, which stays on hold.
3. **Baselines from the owner's own runs, for now.** Expected values per step are derived from the owner's (Rob's) own runs, acting as the reference owner, and shipped with the recipe. How baselines are set once other owners exist is left open.

The owner also asked that all the suggestions of that discussion be written into the change doc. They are recorded there as positions; they are not decisions.
