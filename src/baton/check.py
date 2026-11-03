"""``baton check``: repository consistency, for pre-commit and CI (§13.5).

Needs no network and no worker profiles. Returns every problem as an
``Issue``; the CLI prints one ``ERROR <path>: <message>`` line each and exits
0 only when there are no errors. Checks:

* hash chains, event envelopes and legal state sequences (impossible states),
  for every run log and the project log;
* CAS integrity, and that every blob an event references exists;
* lockfile versus vendored recipes, and each vendored recipe's validation and
  neutrality lint; every run's pinned recipe is vendored with its hash;
* no secrets under ``.baton/`` (sentinels and token patterns; the gitignored
  cache and local profile overrides are skipped);
* ``project.yaml`` and ``communication.md`` present and valid;
* format versions readable by this runtime.

Drift (published deliverables) arrives with the deliverables layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from . import redact, versions
from .data import read_text
from .models import EVENTS_FORMATS, Event, Issue
from .packet import PROTOCOL
from .project import BUILTIN_RECIPES, builtin_recipe, COMM_FILE, GITATTRIBUTES_RULE, LOCAL_PROFILES, LOCK_FILE, PROJECT_FILE, load_config
from .recipe import RecipeError, load_recipe
from .store import BATON_DIR, RunLog, Store
from .vocab import load as load_vocab

#: Paths under .baton/ that are never committed and so are not scanned for secrets.
UNSCANNED = ("cache", LOCAL_PROFILES)


def referenced_blobs(events: Iterable[Event]) -> set[str]:
    """Every CAS hash a run's events reference."""
    out: set[str] = set()
    for ev in events:
        d = ev.data
        for key in ("inputs_sha256", "result_sha256", "output_sha256", "research_sha256", "baseline_sha256"):
            if isinstance(d.get(key), str):
                out.add(d[key])
        arts = d.get("artifacts")
        if isinstance(arts, dict):
            out.update(a["sha256"] for a in arts.values() if isinstance(a, dict) and isinstance(a.get("sha256"), str))
    return out


def run_integrity(store: Store, run_id: str) -> list[Issue]:
    """Chain, state and CAS checks for one run."""
    log = RunLog(store, run_id)
    issues = log.verify()
    events, _ = log.scan()
    issues += log.cas.verify(referenced_blobs(events))
    return issues


def _rel(root: Path, p: Path | str) -> str:
    try:
        return Path(p).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def _relabel(root: Path, issues: list[Issue]) -> list[Issue]:
    out = []
    for i in issues:
        where, sep, line = i.where.rpartition(":") if i.where.rpartition(":")[2].isdigit() else (i.where, "", "")
        out.append(i.model_copy(update={"where": _rel(root, where) + (sep + line if sep else "")}))
    return out


def check(root: Path) -> list[Issue]:
    root = Path(root)
    baton = root / BATON_DIR
    issues: list[Issue] = []
    if not baton.is_dir():
        return [Issue(code="project.missing", where=BATON_DIR, message="not a Baton project (run `baton init`)")]

    # project.yaml and communication.md
    _, cfg_issues = load_config(baton / PROJECT_FILE)
    issues += cfg_issues
    comm = baton / COMM_FILE
    if not comm.is_file():
        issues.append(Issue(code="project.no_communication", where=str(comm), message="communication.md is missing (run `baton init`)"))
    elif not read_text(comm).strip():
        issues.append(Issue(code="project.no_communication", where=str(comm), message="communication.md is empty"))

    # line endings: git must store .baton/ byte for byte (§15.1)
    ga = baton / ".gitattributes"
    if not ga.is_file() or GITATTRIBUTES_RULE not in read_text(ga).splitlines():
        issues.append(
            Issue(
                code="project.line_endings",
                where=str(ga),
                message=f"must contain `{GITATTRIBUTES_RULE}` so git never converts line endings in hashed files (run `baton init`)",
            )
        )

    # lockfile and vendored recipes
    lock: dict[str, Any] = {}
    lock_path = baton / LOCK_FILE
    if not lock_path.is_file():
        issues.append(Issue(code="lock.missing", where=str(lock_path), message="baton.lock is missing (run `baton init`)"))
    else:
        try:
            lock = json.loads(read_text(lock_path))
        except json.JSONDecodeError as e:
            issues.append(Issue(code="lock.invalid", where=str(lock_path), message=f"not valid JSON: {e}"))
    if lock:
        issues += _check_lock(baton, lock_path, lock)

    # logs and CAS
    store = Store(root)
    try:
        issues += store.project_log().verify()
        recipes = lock.get("recipes", {}) if lock else {}
        for rid in store.run_ids():
            issues += run_integrity(store, rid)
            events, _ = RunLog(store, rid).scan()
            if events and events[0].type == "run_started":
                ref, sha = events[0].data.get("recipe"), events[0].data.get("recipe_sha256")
                entry = recipes.get(ref)
                if entry is None and ref in BUILTIN_RECIPES:
                    entry = {"sha256": builtin_recipe(ref).sha256}  # the runtime's own (§11.1)
                if entry is None or entry.get("sha256") != sha:
                    issues.append(
                        Issue(code="run.recipe_not_vendored", where=str(RunLog(store, rid).path), message=f"pinned recipe {ref} ({sha}) is not vendored with that hash")
                    )
    finally:
        store.close()

    # secrets
    issues += _scan_secrets(baton)
    return _relabel(root, issues)


def _check_lock(baton: Path, lock_path: Path, lock: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    where = str(lock_path)
    if lock.get("format") != versions.LOCK_FORMAT:
        issues.append(Issue(code="lock.unknown_format", where=where, message=f"lockfile format {lock.get('format')!r} is not readable by this runtime"))
        return issues
    formats = lock.get("formats") or {}
    readable = {"events": EVENTS_FORMATS, "packet": (PROTOCOL,), "recipe": versions.RECIPE_FORMATS}
    for k, supported in readable.items():
        if formats.get(k) not in supported:
            issues.append(Issue(code="lock.unknown_format", where=where, message=f"{k} format {formats.get(k)!r} is not readable by this runtime"))
    for v in lock.get("vocab") or []:
        try:
            load_vocab(v)
        except Exception:
            issues.append(Issue(code="lock.unknown_vocab", where=where, message=f"capability vocabulary {v!r} is not shipped with this runtime"))
    recipes = lock.get("recipes") or {}
    rdir = baton / "recipes"
    on_disk = {p.name for p in rdir.iterdir() if p.is_dir() and not p.name.startswith(".")} if rdir.is_dir() else set()
    for ref in sorted(on_disk - set(recipes)):
        issues.append(Issue(code="lock.unrecorded_recipe", where=str(rdir / ref), message="vendored recipe is not in baton.lock"))
    for ref in sorted(recipes):
        target = rdir / ref
        if ref not in on_disk:
            issues.append(Issue(code="lock.missing_recipe", where=str(target), message=f"{ref} is in baton.lock but not vendored"))
            continue
        try:
            loaded = load_recipe(target)
        except RecipeError as e:
            for i in e.issues:
                if i.severity == "error":
                    issues.append(i.model_copy(update={"where": f"{target}/{i.where}" if i.where else str(target)}))
            continue
        if loaded.recipe.ref != ref:
            issues.append(Issue(code="lock.recipe_ref", where=str(target), message=f"directory {ref} holds {loaded.recipe.ref}"))
        if loaded.sha256 != recipes[ref].get("sha256"):
            issues.append(Issue(code="lock.recipe_hash", where=str(target), message=f"{ref} does not match its baton.lock hash (edited in place?)"))
    return issues


def _scan_secrets(baton: Path) -> list[Issue]:
    issues = []
    for p in sorted(baton.rglob("*")):
        rel = p.relative_to(baton)
        if not p.is_file() or p.is_symlink() or (rel.parts and rel.parts[0] in UNSCANNED):
            continue
        try:
            data = p.read_bytes()
        except OSError:  # pragma: no cover
            continue
        names = sorted({h.pattern for h in redact.scan_bytes(data)})
        if names:
            issues.append(Issue(code="secret.found", where=str(p), message=f"possible secret ({', '.join(names)}); remove it and rotate the credential"))
    return issues
