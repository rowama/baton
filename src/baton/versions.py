"""Format versions, the lockfile and the published format schemas (§14.1, §14.2, §15.3).

Regenerate the files under ``formats/`` with ``python -m baton.versions``;
a test fails if they drift from the models.

**Format families** (``FAMILIES``): the stored formats a project keeps for
its lifetime: event logs (per event), the lockfile and vendored recipes. Each
family has a current version and a chain of *upcasters* (``n -> n+1``) kept
from version 1 forever. A runtime reads the current and the previous version
directly, upcasting in memory (``WINDOW``, §18 #15). Older versions are
refused with ``format.needs_migration`` naming ``baton migrate``, which writes
an upcast copy alongside (never rewriting history) and records ``migrated``.
Newer versions than the runtime knows are refused with ``format.too_new``.

**Lockfile** (``.baton/baton.lock``, JSON): the runtime version, the format
and vocabulary versions in use, and for every vendored recipe version its
package hash and per-step signatures (§5.8). Entries for older recipe
versions are kept, so later vendoring can compare against every version the
project has used (Phase 15).
"""

from __future__ import annotations

import json
import sys
import re
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Callable

from . import data

FINDINGS_FORMAT = "baton-findings/1"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

# ---------------------------------------------------------------------------
# Format families (§14.2)
# ---------------------------------------------------------------------------

#: How many versions of a family a runtime reads directly: the current and the
#: previous one (owner decision, 2026-11-03, §18 #15). Older ones need ``migrate``.
WINDOW = 2

Upcaster = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class Family:
    """One stored format: ``<prefix>/<n>``; ``upcasters[n]`` turns version n into n+1."""

    name: str
    prefix: str
    current: int
    what: str  # how messages name a document of this family
    upcasters: dict[int, Upcaster] = field(default_factory=dict)

    def fmt(self, n: int) -> str:
        return f"{self.prefix}/{n}"


#: The registry. Every family is at version 1, so no upcaster exists yet; a new
#: version adds its upcaster here and bumps ``current``.
FAMILIES: dict[str, Family] = {
    "events": Family("events", "baton-events", 1, "event"),
    "lock": Family("lock", "baton-lock", 1, "lockfile"),
    "recipe": Family("recipe", "baton-recipe", 1, "recipe"),
}

_FMT = re.compile(r"^(?P<prefix>[a-z][a-z0-9-]*)/(?P<n>[1-9][0-9]*)$")


def family(name: str) -> Family:
    return FAMILIES[name]


def current_format(name: str) -> str:
    f = FAMILIES[name]
    return f.fmt(f.current)


def readable_formats(name: str) -> tuple[str, ...]:
    """Versions read directly, oldest first; the last is the current one."""
    f = FAMILIES[name]
    return tuple(f.fmt(n) for n in range(max(1, f.current - WINDOW + 1), f.current + 1))


def version_of(name: str, fmt: Any) -> int | None:
    m = _FMT.match(fmt) if isinstance(fmt, str) else None
    if m is None or m["prefix"] != FAMILIES[name].prefix:
        return None
    return int(m["n"])


def classify(name: str, fmt: Any) -> str:
    """``current`` | ``readable`` | ``needs_migration`` | ``too_new`` | ``unknown``."""
    f = FAMILIES[name]
    n = version_of(name, fmt)
    if n is None:
        return "unknown"
    if n == f.current:
        return "current"
    if n > f.current:
        return "too_new"
    if any(k not in f.upcasters for k in range(n, f.current)):
        return "unknown"  # no migration path: a version this runtime never had
    return "readable" if n > f.current - WINDOW else "needs_migration"


def upcast(name: str, obj: dict[str, Any], key: str = "format") -> dict[str, Any]:
    """A copy of ``obj`` brought to the current version of its family (any version with a path)."""
    f = FAMILIES[name]
    n = version_of(name, obj.get(key))
    if n is None or n > f.current:
        raise ValueError(f"cannot upcast {obj.get(key)!r} to {f.fmt(f.current)}")
    out = dict(obj)
    while n < f.current:
        out = dict(f.upcasters[n](out))
        n += 1
        out[key] = f.fmt(n)
    return out


def format_problem(name: str, fmt: Any, subject: str) -> tuple[str, str] | None:
    """(code, message) when ``fmt`` cannot be read directly, else None. ``subject`` names the document."""
    from . import __version__

    status = classify(name, fmt)
    if status in ("current", "readable"):
        return None
    cur = current_format(name)
    if status == "needs_migration":
        return "format.needs_migration", (
            f"{subject} is in {fmt}, which Baton {__version__} no longer reads directly (it reads {', '.join(readable_formats(name))}); "
            "run `baton migrate` (preview with `baton migrate --dry-run`)"
        )
    if status == "too_new":
        return "format.too_new", (
            f"{subject} is in {fmt}, newer than Baton {__version__} reads (up to {cur}); it was written by a newer runtime: "
            "run Baton through the launcher (the `baton` command uses the version pinned in baton.lock)"
        )
    return "format.unknown", f"{subject} has format {fmt!r}, which Baton {__version__} does not know (it reads {', '.join(readable_formats(name))})"

def issue_code(prefix: str, code: str) -> str:
    """``<prefix>.needs_migration`` for a format to migrate, else ``<prefix>.unknown_format``."""
    return f"{prefix}.needs_migration" if code == "format.needs_migration" else f"{prefix}.unknown_format"


def _with_header(schema: dict[str, Any], title: str) -> dict[str, Any]:
    return {"$schema": DRAFT_2020_12, "title": title, **{k: v for k, v in schema.items() if k != "title"}}


def recipe_json_schema() -> dict[str, Any]:
    from .models import Recipe

    return _with_header(Recipe.model_json_schema(by_alias=True), current_format("recipe"))


@cache
def findings_json_schema() -> dict[str, Any]:
    """The runtime-owned ``baton:findings`` schema (§9.2)."""
    from .models import Findings

    return _with_header(Findings.model_json_schema(by_alias=True), FINDINGS_FORMAT)


@cache
def crosswalk_json_schema() -> dict[str, Any]:
    """``baton-crosswalk/1`` (§11.3). Rules against the recipe are checked by the loader."""
    from .models import CROSSWALK_FORMATS, Crosswalk

    return _with_header(Crosswalk.model_json_schema(by_alias=True), CROSSWALK_FORMATS[-1])


def published_schemas() -> dict[str, dict[str, Any]]:
    """File name under ``formats/`` -> schema."""
    return {
        "baton-recipe-1.schema.json": recipe_json_schema(),
        "baton-findings-1.schema.json": findings_json_schema(),
        "baton-crosswalk-1.schema.json": crosswalk_json_schema(),
    }


def dump(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_published() -> None:
    out = data.path("formats")
    out.mkdir(exist_ok=True)
    for name, schema in published_schemas().items():
        (out / name).write_text(dump(schema), encoding="utf-8", newline="\n")
        print(out / name, file=sys.stderr)


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------


def new_lock() -> dict[str, Any]:
    from . import __version__
    from .vocab import DEFAULT

    return {
        "format": current_format("lock"),
        "runtime": __version__,
        "formats": current_formats(),
        "vocab": [DEFAULT],
        "recipes": {},
    }


def current_formats() -> dict[str, str]:
    """The formats this runtime writes, as the lockfile records them."""
    from .packet import PROTOCOL

    return {"events": current_format("events"), "packet": PROTOCOL, "recipe": current_format("recipe")}


def dump_lock(lock: dict[str, Any]) -> str:
    return json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def step_signatures(loaded: Any) -> dict[str, dict[str, Any]]:
    """Per step id: kind, enclosing group, output schema hash, required capabilities (§5.8)."""
    import hashlib

    from .models import Group

    out: dict[str, dict[str, Any]] = {}

    def schema_hash(ref: str | None) -> str | None:
        if ref is None:
            return None
        if ref.startswith("baton:"):
            return ref
        return hashlib.sha256((loaded.root / ref).read_bytes()).hexdigest()

    def visit(nodes: list, group: str | None) -> None:
        for n in nodes:
            if isinstance(n, Group):
                out[n.id] = {"kind": "group", "group": group, "output_schema_sha256": None, "capabilities": []}
                visit(n.steps, n.id)
            else:
                out[n.id] = {
                    "kind": "step",
                    "group": group,
                    "output_schema_sha256": schema_hash(n.output_schema),
                    "capabilities": sorted(n.requires.capabilities),
                }

    visit(loaded.recipe.steps, None)
    return out


# ---------------------------------------------------------------------------
# Migration and upgrade (§14.2, §14.3)
# ---------------------------------------------------------------------------


def _event_logs(project: Any) -> list[tuple[str | None, Any]]:
    """(run id or None, log) for the project log and every run log."""
    store = project.store
    logs: list[tuple[str | None, Any]] = []
    if store.project_log().path.is_file():
        logs.append((None, store.project_log()))
    for rid in store.run_ids():
        logs.append((rid, store.run(rid)))
    return logs


def _log_formats(log: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """The log's events as this runtime would interpret them (migrated copy applied), and any problems."""
    rows, issues = log.raw()
    problems = [f"{i.where}: {i.message}" for i in issues]
    objs = [o for _, o, _ in rows]
    translated, problem = log.translations(objs)
    if problem is not None:
        return [], problems + [f"{problem.where}: {problem.message}"]
    return [translated.get(o["seq"], o) for o in objs], problems


def _rel(project: Any, p: Any) -> str:
    from pathlib import PurePosixPath

    return PurePosixPath(p.relative_to(project.root)).as_posix()


def migration_plan(project: Any) -> dict[str, Any]:
    """What ``migrate`` would do: every stored document below the readable window (§14.2).

    Documents newer than this runtime, or with no migration path, are ``problems``:
    migration cannot help them.
    """
    import hashlib

    from .data import load_yaml, read_text
    from .project import LOCK_FILE
    from .recipe import RECIPE_FILE, migrated_recipe, migrated_recipe_path

    items: list[dict[str, Any]] = []
    problems: list[str] = []

    def judge(name: str, fmt: Any, subject: str) -> str:
        status = classify(name, fmt)
        if status in ("too_new", "unknown"):
            problems.append(format_problem(name, fmt, subject)[1])  # type: ignore[index]
        return status

    lock_path = project.baton / LOCK_FILE
    if lock_path.is_file():
        try:
            lock = json.loads(read_text(lock_path))
        except json.JSONDecodeError as e:
            problems.append(f"{_rel(project, lock_path)}: not valid JSON: {e}")
        else:
            old = [lock.get("format")] if judge("lock", lock.get("format"), "baton.lock") == "needs_migration" else []
            formats = lock.get("formats") if isinstance(lock.get("formats"), dict) else {}
            old += [formats[k] for k in ("events", "recipe") if judge(k, formats.get(k), f"baton.lock's {k} format") == "needs_migration"]
            if old:  # the lock is rewritten in the current format, recording the current formats
                items.append({"family": "lock", "path": _rel(project, lock_path), "from": sorted(set(old)), "to": current_format("lock")})

    rdir = project.recipes_dir
    for root in sorted(p for p in rdir.iterdir() if p.is_dir() and not p.name.startswith(".")) if rdir.is_dir() else []:
        try:
            raw = load_yaml(root / RECIPE_FILE)
        except Exception as e:  # noqa: BLE001 - reported, check names the details
            problems.append(f"{_rel(project, root)}: {e}")
            continue
        fmt = raw.get("format") if isinstance(raw, dict) else None
        if judge("recipe", fmt, f"vendored recipe {root.name}") == "needs_migration" and migrated_recipe(root) is None:
            src = hashlib.sha256((root / RECIPE_FILE).read_bytes()).hexdigest()
            items.append({"family": "recipe", "recipe": root.name, "path": _rel(project, migrated_recipe_path(root)),
                          "from": [fmt], "to": current_format("recipe"), "source_sha256": src})

    for rid, log in _event_logs(project):
        objs, bad = _log_formats(log)
        problems += bad
        if bad:
            continue
        old: set[str] = set()
        for o in objs:
            status = judge("events", o.get("format"), f"{_rel(project, log.path)} seq {o.get('seq')}")
            if status == "needs_migration":
                old.add(o["format"])
        if old and objs:
            upto = objs[-1]["seq"]
            items.append({"family": "events", "run": rid, "log": _rel(project, log.path),
                          "path": _rel(project, log.path.parent / f"events.migrated-{upto}.jsonl"),
                          "from": sorted(old), "to": current_format("events"), "upto_seq": upto})
    return {"items": items, "problems": sorted(set(problems))}


def apply_migration(project: Any, plan: dict[str, Any]) -> list[Any]:
    """Write every planned migration and record ``migrated``; returns the paths written (for the commit).

    Never rewrites an event: a log gets an upcast copy alongside and a ``migrated`` record.
    """
    import hashlib

    from .data import load_yaml, read_text
    from .locks import run_lock
    from .recipe import RECIPE_FILE
    from .store import atomic_write, canonical_json

    paths: list[Any] = []
    project_records: list[dict[str, Any]] = []
    for item in plan["items"]:
        target = project.root / item["path"]
        if item["family"] == "lock":
            lock = upcast("lock", json.loads(read_text(target)))
            lock["formats"] = {**(lock.get("formats") or {}), **{k: v for k, v in current_formats().items() if k != "packet"}}
            atomic_write(target, dump_lock(lock).encode("utf-8"))
            project_records.append({"family": "lock", "path": item["path"], "from": item["from"], "to": item["to"]})
        elif item["family"] == "recipe":
            root = project.recipes_dir / item["recipe"]
            doc = {"source_sha256": item["source_sha256"], "from": item["from"][0], "to": item["to"],
                   "recipe": upcast("recipe", load_yaml(root / RECIPE_FILE))}
            body = (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
            atomic_write(target, body)
            project_records.append({"family": "recipe", "recipe": item["recipe"], "path": item["path"], "from": item["from"],
                                    "to": item["to"], "sha256": hashlib.sha256(body).hexdigest(), "source_sha256": item["source_sha256"]})
        else:
            rid = item["run"]
            log = project.store.run(rid) if rid else project.store.project_log()
            with run_lock(project.baton, rid) if rid else _nullcontext():
                objs, bad = _log_formats(log)
                if bad or not objs or objs[-1]["seq"] != item["upto_seq"]:
                    raise ValueError(f"{item['log']} changed since the migration was planned; run `baton migrate` again")
                lines = [canonical_json(upcast("events", o)) + "\n" for o in objs]
                body = "".join(lines).encode("utf-8")
                atomic_write(target, body)
                log.append_migration({"family": "events", "from": item["from"], "to": item["to"], "upto_seq": item["upto_seq"],
                                      "upto_sha256": objs[-1]["sha256"], "path": target.name, "sha256": hashlib.sha256(body).hexdigest()})
            paths.append(log.path)
        paths.append(target)
    if project_records:
        log = project.store.project_log()
        for rec in project_records:
            log.append_migration(rec)
        paths.append(log.path)
    return paths


def _nullcontext() -> Any:
    import contextlib

    return contextlib.nullcontext()


def upgrade_lock(project: Any, to: str | None) -> dict[str, Any]:
    """Pin this runtime in baton.lock and re-vendor the skills; nothing else changes (§14.3).

    Runs under the target runtime: the launcher starts it for ``upgrade --to``. Refused when
    the project holds a format this runtime cannot read or migrate (a downgrade too far).
    """
    from . import __version__
    from .data import read_text
    from .packet import EngineError
    from .project import LOCK_FILE, vendor_skills, write_lock

    if to is not None and to != __version__:
        raise EngineError("upgrade.wrong_runtime", f"this is Baton {__version__}; `upgrade --to {to}` must run under Baton {to}: "
                          "use the launcher (the `baton` command), which installs and starts it")
    lock_path = project.baton / LOCK_FILE
    try:
        lock = json.loads(read_text(lock_path))
    except (OSError, json.JSONDecodeError) as e:
        raise EngineError("project.bad_lock", f"{lock_path} cannot be read: {e}") from e
    plan = migration_plan(project)
    if plan["problems"]:
        raise EngineError("upgrade.unreadable", f"Baton {__version__} cannot read this project: " + "; ".join(plan["problems"]))
    previous = lock.get("runtime")
    lock = upcast("lock", lock)
    lock["runtime"] = __version__
    lock["formats"] = current_formats()
    write_lock(project, lock)
    skills = vendor_skills(project.root)
    pending = [i for i in plan["items"] if i["family"] != "lock"]
    out: dict[str, Any] = {"previous": previous, "runtime": __version__, "formats": lock["formats"], "skills": skills,
                           "changed": previous != __version__ or bool(skills["created"] or skills["replaced"]),
                           "needs_migration": pending}
    if pending:
        out["message"] = f"{len(pending)} stored file(s) are in formats Baton {__version__} no longer reads directly: run `baton migrate`"
    return out


if __name__ == "__main__":
    write_published()
