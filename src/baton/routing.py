"""Routing: which profiles may do a step, in what order (§8.4).

``eligible_workers`` is the whole rule; the packet builder re-checks the
requirement part (``requirement_gaps``) before it builds anything (§8.6).

1. Profiles come from the machine, then ``.baton/workers.local.yaml`` (``project.py``).
2. Keep profiles with every required capability, a sufficient tier and the
   numeric minimums (plus ``repo_workspace`` for write steps and
   ``workspace_read`` for read steps).
3. Independence: when the step declares ``independence: {from_step, level}``,
   drop profiles that match the worker of ``from_step``'s current result at
   that level (``same_at``: creators and canonical model identities; an unknown
   identity is never proof of independence, 0076). The worker's identity is
   read from the run's record (``worker_selected``), not from this machine's
   profiles or the known-workers data.
4. Order by ``.baton/preferences.yaml``: ``exclude`` removes, ``prefer.by_step``
   then ``prefer.by_capability`` put named profiles first; the rest follow with
   more of the step's capabilities ``verified`` first (0084), then by name.
   Preferences never add an ineligible profile.
   A capability recorded ``absent`` on this machine counts as missing (step 2).
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


def needed_capabilities(requires: Requires, workspace: str) -> list[str]:
    """The step's required capabilities plus its workspace mode's (§8.4 step 2)."""
    needed = list(requires.capabilities)
    ws_cap = WORKSPACE_CAPABILITY.get(workspace)
    if ws_cap and ws_cap not in needed:
        needed.append(ws_cap)
    return needed


def requirement_gaps(requires: Requires, workspace: str, profile: WorkerProfile, vocab: Vocabulary) -> list[str]:
    """Why ``profile`` cannot do a step with these requirements; empty when it can.

    A claimed capability whose recorded state is ``absent`` counts as missing (0084).
    """
    gaps: list[str] = []
    needed = needed_capabilities(requires, workspace)
    missing = [c for c in needed if c not in profile.capabilities]
    if missing:
        gaps.append(f"missing capabilities: {', '.join(missing)}")
    for c in needed:
        if c in profile.capabilities and profile.capability_state(c) == "absent":
            rec = profile.capability_record(c)
            gaps.append(f"capability {c} is absent here ({rec.describe()}); "
                        f"`baton workers declare --profile <name> --likely {c}` lets it be tried again")
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


def route_summary(profile_name: str, profile: WorkerProfile) -> dict[str, Any]:
    """Identity and route as shown in eligibility and diagnostics (§8.4)."""
    return {"profile": profile_name, "adapter": profile.adapter, "vendor": profile.creator, "creator": profile.creator,
            "model_id": profile.canonical_model(), "provider": profile.provider}


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
    """Whether ``a`` and ``b`` count as the same worker at an independence level (0076).

    Unknown is never proof of independence:

    * ``different_profile``: the same profile.
    * ``different_vendor``: the same profile, the same creator
      (case-insensitive), or either creator unknown.
    * ``different_model``: the same profile; both ``model_id``s known and
      equal; or either unknown while the creators are not known to differ.

    Provider, endpoint, account and adapter never count: a route is not a model.
    """
    if a.profile == b.profile:
        return True
    if level == "different_profile":
        return False
    ca, cb = (a.creator or "").lower() or None, (b.creator or "").lower() or None
    same_creator = ca is None or cb is None or ca == cb
    if level == "different_vendor":
        return same_creator
    if a.model_id is not None and b.model_id is not None:
        return a.model_id == b.model_id
    return same_creator


def independence_reason(level: str, from_step: str, mine: WorkerIdentity, other: WorkerIdentity) -> str:
    """Why a profile is not independent of ``from_step``'s worker, with the fix when identity is unknown."""
    text = f"independence: {level} from {from_step} (done by {other.profile}, creator {other.creator or '?'}, model {other.model_id or 'unknown'})"
    if level == "different_model" and mine.profile != other.profile and (mine.model_id is None or other.model_id is None):
        text += "; a model identity is unknown, so the models are not proven different: set model_id on the profile, or waive for one dispatch (§9.3)"
    elif level == "different_vendor" and mine.profile != other.profile and (not mine.creator or not other.creator):
        text += "; a creator is unknown, so not proven different"
    return text


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
                reasons.append(independence_reason(indep.level, indep.from_step, identity_of(name, p), other))
            else:
                waived = True
        if name in prefs.exclude:
            reasons.append("excluded by preferences.yaml")
        if reasons:
            out.excluded.append({"profile": name, "reasons": reasons})
            continue
        why = ["meets requirements"]
        caps = {c: p.capability_state(c) for c in needed_capabilities(step.requires, step.workspace)}
        verified = [c for c, st in caps.items() if st == "verified"]
        if verified:
            why.append(f"verified here: {', '.join(verified)}")
        if waived:
            why.append(f"not independent of {indep.from_step} ({indep.level}), waived for one dispatch ({independence_waiver})")
        elif other is not None and indep:
            why.append(f"independent of {indep.from_step} ({indep.level})")
        kept[name] = {**route_summary(name, p), "capabilities": caps, "reasons": why}

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
    # Among the rest, more of the step's capabilities verified first, then by name (0084).
    rest = [n for n in kept if n not in ordered]
    ordered += sorted(rest, key=lambda n: (-sum(st == "verified" for st in kept[n]["capabilities"].values()), n))
    out.eligible = [kept[n] for n in ordered]
    return out


# ---------------------------------------------------------------------------
# Web steps (§13.4; 2026-11-capability-confidence criterion 10)
# ---------------------------------------------------------------------------

#: What to tell the owner when a step needs the web and no worker here has it.
WEB_ADVICE = (
    "Some steps of this work search the web, and no worker on this machine can. The simplest fix is a subscription "
    "coding assistant: install Claude Code (then run `claude` once and log in) or the Codex CLI (then `codex login`), "
    "and run `baton workers setup`. Baton turns on their web tools for exactly the steps that need them."
)


def web_steps(recipe: Any) -> list[str]:
    """Paths of a recipe's steps that require ``web_access``, groups included."""
    from .models import Group

    out: list[str] = []

    def visit(nodes: list[Any], prefix: str) -> None:
        for n in nodes:
            if isinstance(n, Group):
                visit(n.steps, f"{prefix}{n.id}/")
            elif isinstance(n, Step) and "web_access" in n.requires.capabilities:
                out.append(f"{prefix}{n.id}")

    visit(recipe.steps, "")
    return out


def web_capable(profiles: dict[str, WorkerProfile]) -> list[str]:
    """Profiles that claim ``web_access`` with any state but ``absent`` (0084)."""
    return sorted(n for n, p in profiles.items() if "web_access" in p.capabilities and p.capability_state("web_access") != "absent")


def web_advice(recipe: Any, profiles: dict[str, WorkerProfile]) -> dict[str, Any] | None:
    """``{steps, advice}`` when ``recipe`` has web steps and no profile here can do the web; else ``None``."""
    steps = web_steps(recipe)
    if not steps or web_capable(profiles):
        return None
    return {"recipe": recipe.ref, "steps": steps, "advice": WEB_ADVICE}
