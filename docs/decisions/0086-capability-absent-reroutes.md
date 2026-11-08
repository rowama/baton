---
id: "0086"
title: "capability_absent re-routes without spending an attempt; absent everywhere escalates at once"
status: accepted
date: 2026-11-08
source: "change 2026-11-capability-confidence (owner, 2026-11-08)"
sections: ["§8.4", "§8.8"]
---

# 0086. capability_absent re-routes without spending an attempt; absent everywhere escalates at once

## Context

When a worker turns out not to have a tool the step needs, the attempt failed because of the worker, not the work. Charging it to the step's attempts would make an unlucky routing choice cost the step a retry.

## Decision

- A denied or unavailable tool classifies the attempt `platform` / `capability_absent`. The step is readied again for the next eligible worker, and the attempt does not count toward `max_attempts`.
- An `absent` tooling capability goes back to `likely` when its harness's version changes, since an upgrade may add the tool.
- When the capability is `absent` on every profile, the step escalates at once as `no_eligible_worker` does (0002), and for a `web_access` step the escalation says how to give it a worker (a subscription CLI, criterion 10). It does not wait silently for the owner to add a worker (Open question 4, owner, 2026-11-08).
