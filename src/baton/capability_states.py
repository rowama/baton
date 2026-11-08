"""Capability states (§6.1; Decision 0084): likely, verified or absent, kept machine-wide.

A profile *claims* capabilities in its file. Whether each claim has been seen to
hold on this machine is a separate fact, kept in ``$BATON_HOME/capability-states.yaml``
(``baton-capability-states/1``) and never in a profile file, so recording one
changes no profile's content hash (0079) or ``worker_profile_sha256`` (§7.1)::

    format: baton-capability-states/1
    profiles:
      codex:
        web_access: {state: verified, date: 2026-11-08, by: observed, evidence: "...",
                     run: ..., step_path: ..., attempt: 1, harness_version: "0.166.0"}
        structured_output: {state: likely, failures: 2}

* A claimed capability with no entry is ``likely``.
* A state qualifies only a capability the profile claims; it never adds one.
* ``absent`` makes the profile ineligible for steps that need the capability
  (§8.4); ``verified`` is preferred over ``likely``.
* ``by`` says who recorded it: ``observed`` (a real dispatch), ``owner``
  (``baton workers declare``), ``probe`` (a passing probe, 0082).

Writes take a file lock beside the store, so concurrent runs on one machine
never lose each other's observations.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from .data import YamlError, load_yaml

FORMAT = "baton-capability-states/1"
STATES_FILE = "capability-states.yaml"
LOCK_FILE = ".capability-states.lock"
STATES = ("likely", "verified", "absent")
#: Capabilities a harness provides through its tools and flags, not its model (0085).
TOOLING = ("web_access", "shell", "file_write", "code_exec", "repo_workspace", "workspace_read")


class CapabilityStatesError(Exception):
    pass


@dataclass(frozen=True)
class CapabilityState:
    """One capability's state on one profile, as recorded."""

    state: str = "likely"
    date: str | None = None
    by: str | None = None
    evidence: str | None = None
    run: str | None = None
    step_path: str | None = None
    attempt: int | None = None
    harness_version: str | None = None
    failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, 0) or k == "state"}

    def describe(self) -> str:
        """``verified 2026-11-08 (observed: ...)`` in plain words."""
        if self.state == "likely" and not self.date:
            return "likely (not yet observed)"
        text = self.state + (f" {self.date}" if self.date else "")
        detail = ", ".join(x for x in (self.by, self.evidence) if x)
        return text + (f" ({detail})" if detail else "")


def path(home: Path) -> Path:
    return Path(home) / STATES_FILE


def load(home: Path) -> dict[str, dict[str, CapabilityState]]:
    """Every recorded state: profile -> capability -> state. Missing file: none."""
    p = path(home)
    if not p.is_file():
        return {}
    try:
        raw = load_yaml(p) or {}
    except YamlError as e:
        raise CapabilityStatesError(f"{p}: {e}") from e
    if not isinstance(raw, dict) or raw.get("format", FORMAT) != FORMAT:
        raise CapabilityStatesError(f"{p}: expected a {FORMAT} mapping")
    out: dict[str, dict[str, CapabilityState]] = {}
    for profile, caps in (raw.get("profiles") or {}).items():
        if not isinstance(caps, dict):
            raise CapabilityStatesError(f"{p}: profiles.{profile} must be a mapping of capability -> state")
        for cap, body in caps.items():
            if not isinstance(body, dict) or body.get("state") not in STATES:
                raise CapabilityStatesError(f"{p}: profiles.{profile}.{cap}: state must be one of {', '.join(STATES)}")
            known = {k: v for k, v in body.items() if k in CapabilityState.__dataclass_fields__}
            if known.get("date") is not None:
                known["date"] = str(known["date"])
            out.setdefault(str(profile), {})[str(cap)] = CapabilityState(**known)
    return out


def _save(home: Path, states: dict[str, dict[str, CapabilityState]]) -> None:
    from .resources import _atomic_write

    body = {"format": FORMAT, "profiles": {p: {c: s.as_dict() for c, s in sorted(caps.items())} for p, caps in sorted(states.items()) if caps}}
    header = "# Capability states (baton-capability-states/1, §6.1). Change with `baton workers declare --profile`.\n"
    _atomic_write(path(home), header + yaml.safe_dump(body, sort_keys=False))


def _lock(home: Path):
    from .locks import file_lock

    return file_lock(Path(home) / LOCK_FILE)


def state_of(states: dict[str, dict[str, CapabilityState]], profile: str, capability: str) -> CapabilityState:
    return states.get(profile, {}).get(capability, CapabilityState())


def record(
    home: Path,
    profile: str,
    capability: str,
    state: str,
    *,
    by: str,
    evidence: str | None = None,
    today: dt.date | None = None,
    run: str | None = None,
    step_path: str | None = None,
    attempt: int | None = None,
    harness_version: str | None = None,
) -> tuple[CapabilityState, CapabilityState]:
    """Set one state; returns ``(before, after)``. ``before == after`` means nothing changed."""
    if state not in STATES:
        raise CapabilityStatesError(f"state must be one of {', '.join(STATES)}, not {state!r}")
    today = today or dt.date.today()
    with _lock(home):
        states = load(home)
        before = state_of(states, profile, capability)
        if state == "likely" and by == "owner":
            after = CapabilityState()  # a reset forgets the observation
        else:
            after = CapabilityState(state, today.isoformat(), by, evidence, run, step_path, attempt, harness_version)
        if _same(before, after):
            return before, before
        if after == CapabilityState():
            states.get(profile, {}).pop(capability, None)
        else:
            states.setdefault(profile, {})[capability] = after
        _save(home, states)
    return before, after


def _same(a: CapabilityState, b: CapabilityState) -> bool:
    """Equal in what matters: the same state from the same kind of source (a re-observation is not news)."""
    return a.state == b.state and a.by == b.by and a.failures == b.failures and a.harness_version == b.harness_version


def reset_on_version(home: Path, profile: str, version: str) -> list[str]:
    """Observed states recorded under another harness version go back to ``likely`` (0084, 0086).

    An upgrade may add a tool or break one, so neither ``verified`` nor ``absent``
    outlives the version it was seen on. The owner's own declarations stay.
    """
    with _lock(home):
        states = load(home)
        caps = states.get(profile, {})
        stale = [c for c, st in caps.items() if st.by in ("observed", "probe") and st.harness_version and st.harness_version != version]
        for c in stale:
            caps.pop(c)
        if stale:
            _save(home, states)
    return stale


def declare(home: Path, profile: str, claimed: Iterable[str], *, likely: Iterable[str] = (), absent: Iterable[str] = (),
            today: dt.date | None = None) -> list[dict[str, Any]]:
    """The owner resets capabilities to ``likely`` or declares them ``absent`` (0084).

    Only capabilities the profile claims; a state never adds one.
    """
    claimed = set(claimed)
    likely, absent = list(likely), list(absent)
    both = sorted(set(likely) & set(absent))
    if both:
        raise CapabilityStatesError(f"{', '.join(both)}: both --likely and --absent")
    unclaimed = sorted(c for c in [*likely, *absent] if c not in claimed)
    if unclaimed:
        raise CapabilityStatesError(
            f"profile {profile!r} does not claim {', '.join(unclaimed)}; a state only qualifies a claimed capability "
            "(a generated profile takes its capabilities from the known-workers data and your declared resources)"
        )
    changes = []
    for cap, state in [*((c, "likely") for c in likely), *((c, "absent") for c in absent)]:
        before, after = record(home, profile, cap, state, by="owner", evidence="declared by the owner" if state == "absent" else None, today=today)
        changes.append({"profile": profile, "capability": cap, "from": before.state, "to": after.state, "changed": before != after})
    return changes


def summary(states: dict[str, dict[str, CapabilityState]], profile: str, claimed: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Each claimed capability's state, for ``workers status``."""
    return {c: state_of(states, profile, c).as_dict() for c in claimed}
