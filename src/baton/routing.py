"""Routing: which profiles may do a step (§8.4).

Phase 3 needs only the requirement check the packet builder re-runs before it
builds anything (§8.6 step 1). Profile loading order, independence and
preferences arrive with the routing layer (Phase 5).
"""

from __future__ import annotations

from .models import Requires, WorkerProfile
from .vocab import Vocabulary

#: Capability a profile needs for each workspace mode (§8.4 step 2).
WORKSPACE_CAPABILITY = {"read": "workspace_read", "write": "repo_workspace"}


def requirement_gaps(requires: Requires, workspace: str, profile: WorkerProfile, vocab: Vocabulary) -> list[str]:
    """Why ``profile`` cannot do a step with these requirements; empty when it can."""
    gaps: list[str] = []
    needed = list(requires.capabilities)
    ws_cap = WORKSPACE_CAPABILITY.get(workspace)
    if ws_cap and ws_cap not in needed:
        needed.append(ws_cap)
    missing = [c for c in needed if c not in profile.capabilities]
    if missing:
        gaps.append(f"missing capabilities: {', '.join(missing)}")
    if requires.tier is not None:
        if profile.tier is None:
            gaps.append(f"needs tier {requires.tier}; profile declares no tier")
        elif vocab.tier_rank(profile.tier) < vocab.tier_rank(requires.tier):
            gaps.append(f"needs tier {requires.tier}; profile is {profile.tier}")
    if requires.min_context_tokens is not None:
        have = profile.context_tokens or 0
        if have < requires.min_context_tokens:
            gaps.append(f"needs context_tokens >= {requires.min_context_tokens}; profile has {have or 'none declared'}")
    return gaps
