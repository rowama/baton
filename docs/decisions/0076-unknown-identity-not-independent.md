---
id: "0076"
title: "An unknown model identity is never proof of independence"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§8.4", "§9.3"]
---

# 0076. An unknown model identity is never proof of independence

## Context

Every existing hand-written profile, and any harness on its default model, has no `model_id` (0075). A fallback to comparing invocation strings would keep today's behaviour but reintroduce the direct-versus-OpenRouter confusion.

## Decision

Strict. Two workers are the same at:

- `different_profile`: the same profile.
- `different_model`: the same profile; or both `model_id`s known and equal; or either `model_id` unknown while the creators are the same or either creator is unknown. Workers whose creators are known and differ are different models.
- `different_vendor`: the same profile; or the same creator (case-insensitive); or either creator unknown.

Switching provider, endpoint, account or adapter alone satisfies neither level. An exclusion caused by an unknown identity says so and names the fixes: set `model_id` on the profile, or the existing one-dispatch waiver (§9.3).
