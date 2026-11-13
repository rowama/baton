"""``baton recipe check``: the deterministic ledger and instance-leak rules for a generated recipe (§5.3; Decision 0108).

A script gate runs it, so the rules are code, not prompting (§0 rule 2). It judges nothing: whether a design meets its
goals is ``audit``'s work. It reads a requirements ledger (the recipe-builder's, §recipe-builder change doc) and a
recipe package, and returns one line per problem.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STATUSES = ("confirmed", "researched", "inferred", "open", "excluded")
SCOPES = ("class", "instance")
#: An instance value shorter than this (after normalizing) is not searched for: it would match ordinary words.
MIN_LEAK_CHARS = 8
#: Package folders whose text must hold no instance value (the run inputs carry them instead).
SCANNED_DIRS = ("prompts", "static")


def _entries(raw: Any) -> list[Any] | None:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("ledger", "entries"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def ledger_problems(raw: Any) -> list[str]:
    """Problems in a ledger: malformed entries, ``open`` entries, ``confirmed`` entries without the owner's words."""
    entries = _entries(raw)
    if entries is None:
        return ["ledger: expected a list of entries, or an object with a `ledger` list"]
    out: list[str] = []
    seen: set[str] = set()
    for n, e in enumerate(entries):
        where = f"ledger[{n}]"
        if not isinstance(e, dict):
            out.append(f"{where}: an entry must be an object")
            continue
        eid = e.get("id")
        if not isinstance(eid, str) or not eid:
            out.append(f"{where}: `id` must be a non-empty string")
        else:
            where = f"ledger entry {eid}"
            if eid in seen:
                out.append(f"{where}: duplicate id")
            seen.add(eid)
        if not isinstance(e.get("statement"), str) or not e["statement"].strip():
            out.append(f"{where}: `statement` must be a non-empty string")
        if e.get("scope") not in SCOPES:
            out.append(f"{where}: `scope` must be one of {list(SCOPES)}")
        status = e.get("status")
        if status not in STATUSES:
            out.append(f"{where}: `status` must be one of {list(STATUSES)}")
        elif status == "open":
            out.append(f"{where}: is still open; resolve it, or have the owner exclude it, before generating")
        elif status == "confirmed" and not (isinstance(e.get("owner_words"), str) and e["owner_words"].strip()):
            out.append(f"{where}: is confirmed but carries no `owner_words`")
    return out


def _instance_values(raw: Any) -> list[tuple[str, str]]:
    """(entry id, normalized text) for each searchable text an ``instance`` entry holds."""
    out: list[tuple[str, str]] = []
    for e in _entries(raw) or []:
        if not isinstance(e, dict) or e.get("scope") != "instance":
            continue
        for key in ("statement", "value", "owner_words"):
            v = e.get(key)
            if isinstance(v, str) and len(_norm(v)) >= MIN_LEAK_CHARS:
                out.append((str(e.get("id")), _norm(v)))
    return out


def leak_problems(raw: Any, package: Path) -> list[str]:
    """Problems where an ``instance`` entry's text appears in the package's prompts or static files."""
    values = _instance_values(raw)
    if not values:
        return []
    out: list[str] = []
    for d in SCANNED_DIRS:
        base = package / d
        if not base.is_dir():
            continue
        for f in sorted(p for p in base.rglob("*") if p.is_file()):
            try:
                text = _norm(f.read_text(encoding="utf-8-sig", errors="replace"))
            except OSError as e:  # pragma: no cover - unreadable file
                out.append(f"{f.relative_to(package).as_posix()}: cannot be read: {e}")
                continue
            for eid, value in values:
                if value in text:
                    out.append(
                        f"{f.relative_to(package).as_posix()}: holds the text of instance entry {eid}; "
                        "a fact about this one job belongs in a run input, not in the recipe"
                    )
    return out


TIMINGS = ("before_design", "in_generated_recipe", "settled", "not_needed")
TARGET_STATUSES = ("none", "firm_constraint", "preference", "example")


def _text(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _discovery_list(raw: Any) -> list[Any] | None:
    if isinstance(raw, dict) and isinstance(raw.get("discovery"), list):
        return raw["discovery"]
    return None


def discovery_problems(raw: Any, package: Path, require: bool = False) -> list[str]:
    """Problems in the ledger file's ``discovery`` records (Decision 0141): form, owner authority and handoff.

    Mechanical only: whether a comparison is adequate or relevant is the independent audit's judgment. With ``require``
    the records must be present, so discovery cannot be dropped silently.
    """
    records = _discovery_list(raw)
    if records is None:
        return ["discovery: the ledger file must be an object with a `discovery` list of records"] if require else []
    if require and not records:
        return ["discovery: at least one record is required, even if only to say no implementation choice is material"]
    ledger = {e.get("id"): e for e in _entries(raw) or [] if isinstance(e, dict)}
    out: list[str] = []
    seen: set[str] = set()
    recipe: dict[str, Any] | None = None
    for n, r in enumerate(records):
        where = f"discovery[{n}]"
        if not isinstance(r, dict):
            out.append(f"{where}: a record must be an object")
            continue
        rid = r.get("id")
        if _text(rid):
            where = f"discovery {rid}"
            if rid in seen:
                out.append(f"{where}: duplicate id")
            seen.add(rid)
        else:
            out.append(f"{where}: `id` must be a non-empty string")
        for key in ("question", "timing_reason"):
            if not _text(r.get(key)):
                out.append(f"{where}: `{key}` must be a non-empty string")
        if r.get("target_status") not in TARGET_STATUSES:
            out.append(f"{where}: `target_status` must be one of {list(TARGET_STATUSES)}")
        timing = r.get("timing")
        if timing not in TIMINGS:
            out.append(f"{where}: `timing` must be one of {list(TIMINGS)}")
        elif timing == "before_design":
            out += _decided_problems(where, r, ledger)
        elif timing == "in_generated_recipe":
            if recipe is None:
                recipe = _load_recipe_yaml(package)
            out += _generated_problems(where, r, recipe)
    return out


def _decided_problems(where: str, r: dict[str, Any], ledger: dict[Any, Any]) -> list[str]:
    out: list[str] = []
    if r.get("status") != "decided":
        return [f"{where}: a choice that shapes the process is still `{r.get('status')}`; the owner must decide it before generating"]
    cmp_ = r.get("comparison")
    if not isinstance(cmp_, dict):
        return [f"{where}: a decided choice carries no `comparison`"]
    options = cmp_.get("options")
    if not isinstance(options, list) or not options:
        out.append(f"{where}: the comparison lists no option")
    sources = [s for o in options or [] if isinstance(o, dict) for s in (o.get("sources") or [])]
    if not sources and not _text(cmp_.get("uncertainty")):
        out.append(f"{where}: the comparison cites no source and states no uncertainty")
    for s in sources:
        if not isinstance(s, dict) or not _text(s.get("title")) or not _text(s.get("read_on")):
            out.append(f"{where}: every source needs a `title` and the date it was read (`read_on`)")
            break
    if not _text(cmp_.get("recommendation")):
        out.append(f"{where}: the comparison makes no recommendation")
    d = r.get("decision")
    entry = ledger.get(d.get("ledger_id")) if isinstance(d, dict) else None
    if entry is None:
        out.append(f"{where}: `decision.ledger_id` names no ledger entry")
    elif entry.get("kind") != "decision" or entry.get("status") != "confirmed" or not _text(entry.get("owner_words")):
        out.append(f"{where}: the decision entry {entry.get('id')} must be a confirmed `decision` carrying the owner's words; a recommendation is not the owner's choice")
    return out


def _load_recipe_yaml(package: Path) -> dict[str, Any] | None:
    import yaml

    try:
        data = yaml.safe_load((package / "recipe.yaml").read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError):  # expected: no readable recipe.yaml is reported as a problem by the caller
        return None
    return data if isinstance(data, dict) else None


def _walk_steps(steps: Any) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for s in steps if isinstance(steps, list) else []:
        if isinstance(s, dict):
            if isinstance(s.get("id"), str):
                found[s["id"]] = s
            found.update(_walk_steps(s.get("steps")))
    return found


def _generated_problems(where: str, r: dict[str, Any], recipe: dict[str, Any] | None) -> list[str]:
    g = r.get("generated")
    if not isinstance(g, dict):
        return [f"{where}: discovery deferred to the recipe needs `generated`: the research step, the decision step and the steps that use the choice"]
    if recipe is None:
        return [f"{where}: the package has no readable recipe.yaml to carry the deferred discovery"]
    steps = _walk_steps(recipe.get("steps"))
    research, decide = g.get("research_step"), g.get("decision_step")
    consumers = g.get("consumers")
    out: list[str] = []
    rs, ds = steps.get(research), steps.get(decide)  # type: ignore[arg-type]
    if rs is None:
        out.append(f"{where}: the recipe has no research step `{research}`")
    elif "web_access" not in ((rs.get("requires") or {}).get("capabilities") or []):
        out.append(f"{where}: research step `{research}` must require `web_access`; current external claims need a research-capable worker")
    if ds is None:
        out.append(f"{where}: the recipe has no decision step `{decide}`")
    else:
        if not any(isinstance(x, dict) and x.get("type") == "human" for x in ds.get("gates") or []):
            out.append(f"{where}: decision step `{decide}` needs a human gate; the owner's approval cannot be assumed")
        if rs is not None and not _takes(ds, research, required=True):
            out.append(f"{where}: decision step `{decide}` must take the findings of `{research}` as a required input")
    if not isinstance(consumers, list) or not consumers:
        out.append(f"{where}: no step is named as using the choice; a deferred choice that nothing consumes is not handed on")
    else:
        for c in consumers:
            cs = steps.get(c)
            if cs is None:
                out.append(f"{where}: the recipe has no consuming step `{c}`")
            elif ds is not None and not _takes(cs, decide, required=True):
                out.append(f"{where}: step `{c}` must take the output of `{decide}` as a required input, or the choice never reaches it")
    return out


def _takes(step: dict[str, Any], source: Any, required: bool) -> bool:
    for i in step.get("inputs") or []:
        ref = i.get("from") if isinstance(i, dict) else None
        if isinstance(ref, str) and ref.startswith(f"steps.{source}.") and (i.get("required") is True or not required):
            return True
    return False


def check(package: Path, ledger_file: Path, require_discovery: bool = False) -> list[str]:
    """Every problem, in order: the package folder, the ledger file, the ledger rules, discovery, then instance leaks."""
    if not package.is_dir():
        return [f"{package}: is not a recipe folder"]
    try:
        raw = json.loads(ledger_file.read_text(encoding="utf-8-sig"))
    except OSError as e:
        return [f"{ledger_file}: cannot be read: {e}"]
    except ValueError as e:
        return [f"{ledger_file}: is not valid JSON: {e}"]
    problems = ledger_problems(raw)
    if _entries(raw) is not None:
        problems += discovery_problems(raw, package, require_discovery)
        problems += leak_problems(raw, package)
    return problems
