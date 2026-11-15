"""Project policy (§13.7; Decisions 0143, 0151, 0153): a few rules every run follows.

The policy is ``project.yaml``'s ``policy`` block (``floors``, ``governing``) plus
its ``permissions`` (the release authority, 0151). Its **value** is the
validated configuration as plain JSON, so formatting and comments never change
it, and its hash is the SHA-256 of that value's canonical JSON.

Changes are recorded: ``policy set`` and ``policy confirm`` append
``human_decision {kind: policy}`` and ``policy_changed {before, after, sha256,
decision_id}`` to the project log, with ``after`` also stored in the project CAS.
``init`` records the defaults it writes (``policy_changed`` by ``runtime:init``).

The policy **in force** is the latest recorded one. Three states:

* ``recorded``: the file holds the recorded policy;
* ``edited``: the file differs (a hand edit). The recorded policy stays in force
  until the owner confirms the edit (0151);
* ``unrecorded``: nothing recorded yet (a project from before policy). The file
  is in force until the first record (0153).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .data import read_text
from .models import PermissionsConfig, PolicyConfig
from .packet import EngineError
from .store import atomic_write, canonical_json

PARTS: tuple[str, ...] = ("floors", "governing", "permissions")
RULES: tuple[str, ...] = ("allow", "ask", "deny")
#: The permission keys ``policy set`` takes, flattened (``push.other``, ``tag``, ...).
PERMISSION_KEYS: tuple[str, ...] = ("push.docs_only", "push.after_verified", "push.other", "tag", "force_push", "merge", "deploy")


def value_of(config: Any) -> dict[str, Any]:
    """The policy part of a project configuration, as plain JSON."""
    pol = config.policy
    return {
        "floors": {r: dict(sorted(axes.items())) for r, axes in sorted(pol.floors.items())},
        "governing": [{"work": g.work, "recipe": g.recipe} for g in pol.governing],
        "permissions": config.permissions.model_dump(),
    }


def sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def flatten(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """``floors.<recipe>.<axis>``, ``governing.<work>``, ``permissions.<action>`` (``permissions.push.<kind>``)."""
    out: dict[str, Any] = {}
    if not value:
        return out
    for r, axes in (value.get("floors") or {}).items():
        for a, v in axes.items():
            out[f"floors.{r}.{a}"] = v
    for g in value.get("governing") or []:
        out[f"governing.{g['work']}"] = g["recipe"]
    perms = value.get("permissions") or {}
    for k, v in perms.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out[f"permissions.{k}.{kk}"] = vv
        else:
            out[f"permissions.{k}"] = v
    return out


def differences(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What changed, one entry per flattened key: ``{key, before, after}`` (``None`` for absent)."""
    a, b = flatten(before), flatten(after)
    return [{"key": k, "before": a.get(k), "after": b.get(k)} for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


@dataclass
class State:
    state: str                         # recorded | edited | unrecorded
    in_force: dict[str, Any]
    file: dict[str, Any]
    recorded: dict[str, Any] | None
    changes: list[Any]                 # the project log's policy_changed events, oldest first

    @property
    def sha256(self) -> str:
        return sha256(self.in_force)

    def permissions(self) -> PermissionsConfig:
        return PermissionsConfig.model_validate(self.in_force["permissions"])

    def policy(self) -> PolicyConfig:
        return PolicyConfig.model_validate({k: self.in_force[k] for k in ("floors", "governing")})

    def notice(self) -> dict[str, Any] | None:
        """For ``status``, ``board`` and ``doctor``: what the owner is asked, or ``None`` when recorded."""
        if self.state == "recorded":
            return None
        if self.state == "edited":
            return {"state": "edited", "differences": differences(self.recorded, self.file),
                    "message": "project.yaml's policy was edited by hand; runs keep the recorded policy until the owner confirms the edit",
                    "next": "show the owner the differences and ask; on yes: `baton policy confirm --note \"<their words>\"`"}
        return {"state": "unrecorded",
                "message": "project.yaml's policy (permissions included) has not been confirmed by the owner yet; it is in force meanwhile",
                "next": "show the owner `baton policy` and ask once; on yes: `baton policy confirm --note \"<their words>\"`"}


def current(events: list[Any], config: Any) -> State:
    """The policy state from the project log's events and the loaded configuration."""
    changes = [e for e in events if e.type == "policy_changed"]
    file = value_of(config)
    if not changes:
        return State("unrecorded", file, file, None, changes)
    recorded = changes[-1].data["after"]
    return State("recorded" if sha256(recorded) == sha256(file) else "edited", recorded, file, recorded, changes)


def decided(changes: list[Any]) -> dict[str, dict[str, Any]]:
    """For each flattened key in force, the change that last set it: ``decision_id`` (``None`` for init), actor, time."""
    out: dict[str, dict[str, Any]] = {}
    for e in changes:
        for d in differences(e.data.get("before"), e.data["after"]):
            if d["after"] is None:
                out.pop(d["key"], None)
            else:
                out[d["key"]] = {"decision_id": e.data.get("decision_id"), "actor": e.actor, "at": e.ts}
    return out


def listing(state: State) -> dict[str, Any]:
    """What ``policy`` returns: the policy in force, each rule with the decision that last changed it."""
    who = decided(state.changes)
    items = [{"key": k, "value": v, **(who.get(k) or {"decision_id": None, "actor": None, "at": None})}
             for k, v in flatten(state.in_force).items()]
    out: dict[str, Any] = {"state": state.state, "sha256": state.sha256, "policy": state.in_force, "rules": items}
    notice = state.notice()
    if notice is not None:
        out["unconfirmed"] = notice
    return out


# -- changes -----------------------------------------------------------------


def _norm_work(work: str) -> str:
    return " ".join(work.lower().split())


def apply(value: Mapping[str, Any], *, floors: Mapping[str, Mapping[str, str | None]] | None = None,
          governing: Mapping[str, str | None] | None = None, permissions: Mapping[str, str] | None = None) -> dict[str, Any]:
    """``value`` with the changes: a ``None`` floor or governing recipe removes it."""
    out = {"floors": {r: dict(a) for r, a in (value.get("floors") or {}).items()},
           "governing": [dict(g) for g in value.get("governing") or []],
           "permissions": {k: (dict(v) if isinstance(v, dict) else v) for k, v in (value.get("permissions") or {}).items()}}
    for r, axes in (floors or {}).items():
        for a, v in axes.items():
            if v is None:
                if a not in out["floors"].get(r, {}):
                    raise EngineError("policy.no_such_floor", f"there is no floor for {a} of {r} to remove")
                del out["floors"][r][a]
                if not out["floors"][r]:
                    del out["floors"][r]
            else:
                out["floors"].setdefault(r, {})[a] = v
    for work, recipe in (governing or {}).items():
        idx = next((i for i, g in enumerate(out["governing"]) if _norm_work(g["work"]) == _norm_work(work)), None)
        if recipe is None:
            if idx is None:
                raise EngineError("policy.no_such_governing", f"no recipe governs {work!r} to remove")
            del out["governing"][idx]
        elif idx is None:
            out["governing"].append({"work": " ".join(work.split()), "recipe": recipe})
        else:
            out["governing"][idx]["recipe"] = recipe
    for key, rule in (permissions or {}).items():
        if key not in PERMISSION_KEYS:
            raise EngineError("policy.unknown_permission", f"unknown permission {key!r}; known: {', '.join(PERMISSION_KEYS)}")
        if rule not in RULES:
            raise EngineError("policy.bad_rule", f"permission {key} is allow, ask or deny, got {rule!r}")
        if "." in key:
            head, kind = key.split(".", 1)
            out["permissions"].setdefault(head, {})[kind] = rule
        else:
            out["permissions"][key] = rule
    try:
        cfg = PolicyConfig.model_validate({k: out[k] for k in ("floors", "governing")})
        perms = PermissionsConfig.model_validate(out["permissions"])
    except ValueError as e:
        raise EngineError("policy.invalid", str(e)) from e
    return {"floors": {r: dict(sorted(a.items())) for r, a in sorted(cfg.floors.items())},
            "governing": [{"work": g.work, "recipe": g.recipe} for g in cfg.governing],
            "permissions": perms.model_dump()}


def floor_problems(value: Mapping[str, Any], scales_of: Any, *, unknown_ok: bool = False) -> tuple[list[str], list[str]]:
    """(refusals, warnings) for the floors in ``value``.

    ``scales_of(recipe_id)`` gives that recipe's axes with their scales (``{}`` with no
    complexity block), or ``None`` when the project knows no such recipe; ``scales_of(None)``
    gives every vendored recipe's, by id. A named recipe's floor must name an axis it
    declares and a value on that axis (``level`` for a one-axis recipe). A ``"*"`` floor
    applies to recipes that declare that axis with that value (0151) and warns when none does.
    With ``unknown_ok`` (``check``, which knows only the vendored recipes), an unknown recipe is not a problem.
    """
    refusals: list[str] = []
    warnings: list[str] = []
    for r, axes in (value.get("floors") or {}).items():
        if r == "*":
            every = scales_of(None) or {}
            for a, v in axes.items():
                if not any(v in sc.get(a, []) for sc in every.values()):
                    warnings.append(f"the floor {a} {v} for every recipe matches no vendored recipe (none declares {a} with {v})")
            continue
        sc = scales_of(r)
        if sc is None:
            if unknown_ok:
                continue
            refusals.append(f"no recipe {r} is vendored or in the catalog")
            continue
        if not sc:
            refusals.append(f"{r} has no ratings to set a floor on")
            continue
        for a, v in axes.items():
            if a not in sc:
                refusals.append(f"{r} has no axis {a!r} (its axes: {', '.join(sc)})")
            elif v not in sc[a]:
                refusals.append(f"{a} of {r} has no value {v!r} (its scale: {', '.join(sc[a])})")
    return refusals, warnings


# -- project.yaml --------------------------------------------------------------


def write(path: Path, value: Mapping[str, Any]) -> None:
    """Replace ``project.yaml``'s ``policy`` and ``permissions`` blocks, keeping its other lines and comments."""
    text = read_text(path)
    lines = text.splitlines(keepends=True)
    blocks = {"policy": {"floors": value["floors"], "governing": value["governing"]}, "permissions": value["permissions"]}
    for key, block_value in blocks.items():
        block = yaml.safe_dump({key: block_value}, sort_keys=False, default_flow_style=False, allow_unicode=True)
        start = next((i for i, ln in enumerate(lines) if re.match(rf"^{key}\s*:", ln)), None)
        if start is None:
            lines.append(("" if not lines or lines[-1].endswith("\n") else "\n") + block)
            continue
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        comment = re.search(r"\s+#.*$", lines[start].rstrip("\n"))
        head = block.splitlines(keepends=True)
        if comment:
            head[0] = head[0].rstrip("\n") + comment.group(0) + "\n"
        lines[start:end] = head
    atomic_write(path, "".join(lines).encode("utf-8"))
