"""Routing: which profiles may do a step, in what order (§8.4).

``eligible_workers`` is the whole rule; the packet builder re-checks the
requirement part (``requirement_gaps``) before it builds anything (§8.6).

1. Profiles come from the machine, then ``.baton/workers.local.yaml`` (``project.py``).
2. Keep profiles with every required capability, a sufficient tier and the
   numeric minimums (plus ``repo_workspace`` for write steps and
   ``workspace_read`` for read steps).
3. Independence: when the step declares ``independence: {from_step, level}``,
   drop profiles that match the worker of ``from_step``'s current result at
   that level. The worker's vendor and model are read from the run's record
   (``worker_selected``), not from this machine's profiles.
4. Order by ``.baton/preferences.yaml``: ``exclude`` removes, ``prefer.by_step``
   then ``prefer.by_capability`` put named profiles first; the rest follow by
   name. Preferences never add an ineligible profile.
5. An empty list escalates the step (``no_eligible_worker``; §18 #2: escalate,
   never fail the run). The engine records that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .data import YamlError, load_yaml
from .models import Independence, Preferences, Requires, Step, WorkerProfile
from .vocab import Vocabulary

#: Capability a profile needs for each workspace mode (§8.4 step 2).
WORKSPACE_CAPABILITY = {"read": "workspace_read", "write": "repo_workspace"}
PREFERENCES_FILE = "preferences.yaml"


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


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


class PreferencesError(Exception):
    pass


def load_preferences(baton_dir: Path) -> Preferences:
    """``.baton/preferences.yaml``, or empty preferences when absent."""
    path = baton_dir / PREFERENCES_FILE
    if not path.is_file():
        return Preferences()
    try:
        raw = load_yaml(path) or {}
        if "secret:" in str(raw):
            raise PreferencesError(f"{path}: secret: references are not allowed in preferences")
        return Preferences.model_validate(raw)
    except YamlError as e:
        raise PreferencesError(f"{path}: {e}") from e
    except ValidationError as e:
        msgs = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise PreferencesError(f"{path}: {msgs}") from e


# ---------------------------------------------------------------------------
# Independence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerIdentity:
    """Who produced a result, as recorded at dispatch (``worker_selected``; 0075).

    ``creator`` and ``model_id`` decide independence; ``provider``, ``model``
    (the invocation identifier) and ``adapter`` describe the route. ``None``
    is unknown.
    """

    profile: str
    creator: str | None
    model_id: str | None = None
    provider: str | None = None
    model: str | None = None
    adapter: str | None = None

    @property
    def vendor(self) -> str | None:
        return self.creator


def identity_of(profile_name: str, profile: WorkerProfile) -> WorkerIdentity:
    return WorkerIdentity(profile_name, profile.creator, profile.canonical_model(), profile.provider, profile.model, profile.adapter)


def identity_record(profile_name: str, profile: WorkerProfile) -> dict[str, Any]:
    """The identity and route snapshot recorded with a dispatch (0075).

    ``vendor`` is still written (equal to ``creator``) and ``model`` is the
    invocation identifier, so a runtime that knows only those reads it as before.
    """
    ident = identity_of(profile_name, profile)
    out: dict[str, Any] = {"profile": profile_name, "vendor": ident.creator, "creator": ident.creator}
    for key in ("model_id", "provider", "model", "adapter"):
        value = getattr(ident, key)
        if value is not None:
            out[key] = value
    return out


def identity_from_record(d: dict[str, Any], profile_key: str = "profile") -> WorkerIdentity:
    """Read a recorded snapshot. An event from before 0075 has only ``vendor``
    and ``model``: its creator is the vendor, its model identity unknown (never
    guessed from the invocation string)."""
    return WorkerIdentity(
        d.get(profile_key, "?"),
        d.get("creator", d.get("vendor")),
        d.get("model_id"),
        d.get("provider"),
        d.get("model"),
        d.get("adapter"),
    )


def same_at(level: str, a: WorkerIdentity, b: WorkerIdentity) -> bool:
    """Whether ``a`` and ``b`` count as the same worker at an independence level.

    ``different_model``: the same profile, or both declare the same ``model``.
    ``different_vendor``: the same vendor (case-insensitive), or the same profile.
    """
    if a.profile == b.profile:
        return True
    if level == "different_profile":
        return False
    if level == "different_model":
        return a.model is not None and a.model == b.model
    return a.vendor is not None and b.vendor is not None and a.vendor.lower() == b.vendor.lower()


def result_worker(events: list[Any], step_path: str, own: bool) -> WorkerIdentity | None:
    """The worker behind ``step_path``'s current result, from the record.

    For the step itself (``own``) that is its latest attempt; for an ancestor,
    the attempt recorded in its last ``step_passed``.
    """
    attempt = None
    for ev in reversed(events):
        if ev.step_path != step_path:
            continue
        if own and ev.type == "dispatched":
            attempt = ev.attempt
            break
        if not own and ev.type == "step_passed":
            attempt = ev.attempt
            break
    if attempt is None:
        return None
    for ev in reversed(events):
        if ev.type == "worker_selected" and ev.step_path == step_path and ev.attempt == attempt:
            return identity_from_record(ev.data)
    return None


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


@dataclass
class Eligibility:
    step_path: str
    eligible: list[dict[str, Any]] = field(default_factory=list)  # [{profile, adapter, vendor, reasons}]
    excluded: list[dict[str, Any]] = field(default_factory=list)  # [{profile, reasons}]

    def names(self) -> list[str]:
        return [e["profile"] for e in self.eligible]

    def reasons_for(self, name: str) -> list[str]:
        for e in self.excluded:
            if e["profile"] == name:
                return e["reasons"]
        return []

    def as_dict(self) -> dict[str, Any]:
        return {"step_path": self.step_path, "eligible": self.eligible, "excluded": self.excluded}


def eligible_workers(
    step: Step,
    step_path: str,
    profiles: dict[str, WorkerProfile],
    vocab: Vocabulary,
    *,
    events: list[Any] | None = None,
    preferences: Preferences | None = None,
    source_path: str | None = None,
    source_own: bool | None = None,
    independence_waiver: str | None = None,
) -> Eligibility:
    """The ordered eligible profiles with reasons, and every exclusion with its reasons.

    ``source_path`` is the step path of ``independence.from_step`` (inside a
    group: the sibling in the same instance and iteration); default: the id.
    """
    prefs = preferences or Preferences()
    out = Eligibility(step_path)
    indep: Independence | None = step.independence
    other = None
    if indep is not None and events is not None:
        own = indep.from_step == step.id if source_own is None else source_own
        source = source_path or (step_path if own else indep.from_step)
        other = result_worker(events, source, own)

    kept: dict[str, dict[str, Any]] = {}
    for name in sorted(profiles):
        p = profiles[name]
        reasons = requirement_gaps(step.requires, step.workspace, p, vocab)
        waived = False
        if other is not None and indep is not None and same_at(indep.level, identity_of(name, p), other):
            if independence_waiver is None:
                reasons.append(f"independence: {indep.level} from {indep.from_step} (done by {other.profile}, vendor {other.vendor or '?'})")
            else:
                waived = True
        if name in prefs.exclude:
            reasons.append("excluded by preferences.yaml")
        if reasons:
            out.excluded.append({"profile": name, "reasons": reasons})
            continue
        why = ["meets requirements"]
        if waived:
            why.append(f"not independent of {indep.from_step} ({indep.level}), waived for one dispatch ({independence_waiver})")
        elif other is not None and indep:
            why.append(f"independent of {indep.from_step} ({indep.level})")
        kept[name] = {"profile": name, "adapter": p.adapter, "vendor": p.vendor, "reasons": why}

    ordered: list[str] = []
    for name in prefs.prefer.by_step.get(step_path, prefs.prefer.by_step.get(step.id, [])):
        if name in kept and name not in ordered:
            ordered.append(name)
            kept[name]["reasons"].append(f"preferred for step {step.id}")
    for cap in step.requires.capabilities:
        for name in prefs.prefer.by_capability.get(cap, []):
            if name in kept and name not in ordered:
                ordered.append(name)
                kept[name]["reasons"].append(f"preferred for {cap}")
    ordered += [n for n in kept if n not in ordered]
    out.eligible = [kept[n] for n in ordered]
    return out
