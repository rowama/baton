"""The machine-level routing preferences file, ``~/.baton/preferences.yaml`` (§8.4; Decision 0124).

The same format as the project's ``.baton/preferences.yaml``. This module edits the machine level only
(`baton workers prefs`, the setup page); routing merges it under the project's (``routing.load_preferences``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import resources
from .models import Preferences
from .routing import PREFERENCES_FILE, PreferencesError, _load_preferences_file

HEADER = "# Machine-level routing preferences (§8.4, 0124). Edit with `baton workers prefs`; a project's own file overrides it.\n"


def path(home: Path) -> Path:
    return Path(home) / PREFERENCES_FILE


def load(home: Path) -> Preferences:
    return _load_preferences_file(path(home))


def known_profiles(home: Path) -> set[str]:
    """Machine profiles the owner may name: generated ones and the owner's own file's."""
    return set(resources.read_generated_dir(home)) | resources._owner_names(home)


def as_dict(p: Preferences) -> dict[str, Any]:
    return {"cheapest_first": p.cheapest_first, "exclude": sorted(p.exclude), "prefer_by_capability": dict(p.prefer.by_capability)}


def save(home: Path, p: Preferences) -> Path:
    body: dict[str, Any] = {}
    if p.cheapest_first:
        body["cheapest_first"] = True
    if p.exclude:
        body["exclude"] = sorted(set(p.exclude))
    prefer = {k: v for k, v in {"by_step": p.prefer.by_step, "by_capability": p.prefer.by_capability}.items() if v}
    if prefer:
        body["prefer"] = prefer
    target = path(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(HEADER + yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    tmp.replace(target)
    return target


def update(home: Path, *, exclude: list[str] | None = None, include: list[str] | None = None, cheapest_first: bool | None = None,
           prefer: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Change the machine preferences. ``prefer`` maps a capability to its preferred profiles in order (``[]`` clears it).

    Every profile to turn off or prefer must exist on this machine. Raises ``PreferencesError`` in plain words.
    """
    home = Path(home)
    p = load(home)
    known = known_profiles(home)
    named = [*(exclude or []), *(n for v in (prefer or {}).values() for n in v)]
    unknown = sorted({n for n in named if n not in known})
    if unknown:
        raise PreferencesError(f"no worker profile named {', '.join(unknown)} on this machine (`baton workers status` lists them)")
    ex = (set(p.exclude) | set(exclude or [])) - set(include or [])
    by_cap = dict(p.prefer.by_capability)
    for cap, names in (prefer or {}).items():
        if names:
            by_cap[cap] = list(names)
        else:
            by_cap.pop(cap, None)
    new = Preferences(prefer={"by_step": p.prefer.by_step, "by_capability": by_cap}, exclude=sorted(ex),
                      cheapest_first=p.cheapest_first if cheapest_first is None else cheapest_first)
    save(home, new)
    return {**as_dict(new), "path": str(path(home))}
