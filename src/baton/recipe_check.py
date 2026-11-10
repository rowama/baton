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


def check(package: Path, ledger_file: Path) -> list[str]:
    """Every problem, in order: the package folder, the ledger file, the ledger rules, then instance leaks."""
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
        problems += leak_problems(raw, package)
    return problems
