"""Guidance documents (§5.7; Decisions 0145, 0163): the harness-neutral Markdown a quick run follows.

A guide is Markdown with front matter (``format: baton-guide/1``, ``id``, ``version``, ``title``,
``description``, ``produces``) and a body with four sections: purpose, what to produce, what good
looks like, and what to ask the owner. Guides ship under ``examples/guides/`` (beside the recipe
catalog) and a project keeps its own under ``guides/``. ``check`` refuses a malformed guide and any
vendor name (the recipe neutrality lint, §5.3); ``listing`` is ``guides()`` and the ``catalog.guides``
input (§5.2); ``copy`` puts a shipped guide into the project as an owner-attested project document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import data

FORMAT = "baton-guide/1"
#: The project's own guides, relative to its root (Decision 0163, item 3).
PROJECT_DIR = "guides"
FIELDS = ("format", "id", "version", "title", "description", "produces")
#: The body's sections, in order (Decision 0145, item 2).
SECTIONS = ("Purpose", "What to produce", "What good looks like", "What to ask the owner")
_ID = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


@dataclass
class Guide:
    id: str
    version: int
    title: str
    description: str
    produces: str
    where: str  # "shipped" or "project"
    path: str   # the file: project-relative for a project guide, package-relative for a shipped one
    file: Path

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "title": self.title, "description": self.description,
                "produces": self.produces, "where": self.where, "path": self.path}


@dataclass
class Checked:
    guide: Guide | None
    problems: list[str] = field(default_factory=list)


def shipped_dir() -> Path:
    """Where the guides shipped with the runtime live (``examples/guides``)."""
    return data.path("examples") / "guides"


def _split(text: str) -> tuple[str | None, str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text
    return text[4:end + 1], text[end + 5:]


def check_text(text: str, *, where: str = "project", path: str = "", file: Path | None = None) -> Checked:
    """Check a guide's text: its front matter, its four sections, and no vendor names anywhere."""
    from .vocab import DEFAULT, load as load_vocab

    problems: list[str] = []
    head, body = _split(text)
    meta: Any = None
    if head is None:
        problems.append("no front matter: the file must start with a '---' block")
    else:
        try:
            meta = yaml.load(head, Loader=data._StrictLoader)  # noqa: S506 - SafeLoader subclass
        except yaml.YAMLError as e:
            problems.append(f"front matter is not valid YAML: {e}")
        if meta is not None and not isinstance(meta, dict):
            problems.append("front matter must be a mapping")
            meta = None
    meta = meta or {}
    if head is not None and isinstance(meta, dict):
        for k in FIELDS:
            if k not in meta:
                problems.append(f"front matter: missing {k!r}")
        for k in meta:
            if k not in FIELDS:
                problems.append(f"front matter: unknown key {k!r}")
        if "format" in meta and meta["format"] != FORMAT:
            problems.append(f"front matter: format must be {FORMAT!r}, not {meta['format']!r}")
        if "id" in meta and not (isinstance(meta["id"], str) and _ID.match(meta["id"])):
            problems.append(f"front matter: id {meta['id']!r} must be lower-case words joined by '-'")
        if "version" in meta and not (isinstance(meta["version"], int) and not isinstance(meta["version"], bool)
                                      and meta["version"] >= 1):
            problems.append(f"front matter: version {meta['version']!r} must be a whole number from 1")
        for k in ("title", "description", "produces"):
            if k in meta and not (isinstance(meta[k], str) and meta[k].strip()):
                problems.append(f"front matter: {k} must be non-empty text")
    headings = [m.group(1).strip() for m in re.finditer(r"^## +(.+?)\s*$", body, re.M)]
    for s in SECTIONS:
        if s not in headings:
            problems.append(f"body: missing the section '## {s}'")
    for s in SECTIONS:  # each section says something
        m = re.search(rf"^## +{re.escape(s)}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
        if m and not m.group(1).strip():
            problems.append(f"body: the section '## {s}' is empty")
    hit = load_vocab(DEFAULT).find_vendor_string(text)
    if hit:
        problems.append(f"names the vendor {hit!r}: a guide must work with any worker (§5.3)")
    if problems:
        return Checked(None, problems)
    return Checked(Guide(id=meta["id"], version=meta["version"], title=meta["title"].strip(),
                         description=meta["description"].strip(), produces=meta["produces"].strip(),
                         where=where, path=path, file=file or Path(path)))


def check_file(file: Path, *, where: str = "project", path: str | None = None) -> Checked:
    try:
        text = data.read_text(file)
    except (OSError, UnicodeDecodeError) as e:
        return Checked(None, [f"cannot be read: {e}"])
    return check_text(text, where=where, path=path if path is not None else str(file), file=file)


def _scan(directory: Path, where: str, rel_of) -> tuple[list[Guide], list[dict[str, Any]]]:
    guides: list[Guide] = []
    problems: list[dict[str, Any]] = []
    if not directory.is_dir():
        return guides, problems
    for f in sorted(directory.glob("*.md")):
        if not f.is_file():
            continue
        rel = rel_of(f)
        c = check_file(f, where=where, path=rel)
        if c.guide is None:
            problems.append({"path": rel, "where": where, "problems": c.problems})
        elif f.stem != c.guide.id:
            problems.append({"path": rel, "where": where,
                             "problems": [f"the file is named {f.name!r} but its id is {c.guide.id!r}"]})
        else:
            guides.append(c.guide)
    return guides, problems


def shipped() -> dict[str, Guide]:
    """The shipped guides, by id."""
    gs, problems = _scan(shipped_dir(), "shipped", lambda f: f"examples/guides/{f.name}")
    if problems:  # pragma: no cover - shipped guides are tested
        raise ValueError(f"a shipped guide is invalid: {problems}")
    return {g.id: g for g in gs}


def project_guides(root: Path) -> tuple[list[Guide], list[dict[str, Any]]]:
    return _scan(root / PROJECT_DIR, "project", lambda f: f"{PROJECT_DIR}/{f.name}")


def listing(root: Path | None) -> dict[str, Any]:
    """Every guide: the project's own, then the shipped ones, sorted by id (a project guide first when both
    share an id). ``problems`` lists the project's files under ``guides/`` that are not valid guides."""
    own, problems = project_guides(root) if root is not None else ([], [])
    every = own + list(shipped().values())
    every.sort(key=lambda g: (g.id, 0 if g.where == "project" else 1))
    return {"guides": [g.summary() for g in every], "problems": problems}


def catalog_input(root: Path | None) -> list[dict[str, Any]]:
    """The ``catalog.guides`` input (§5.2): the valid guides only, deterministic."""
    return listing(root)["guides"]


def copy(store: Any, guide_id: str, note: str, *, recorded_by: str | None = None) -> dict[str, Any]:
    """Copy a shipped guide into the project's ``guides/`` and record the owner's attestation of the copy
    (Decision 0163, item 5), so ``quick-run`` can bind it. Never overwrites a file."""
    from . import documents
    from .packet import EngineError

    if not (note or "").strip():
        raise EngineError("attest.note_required", "copying a guide is the owner's decision; give their words with --note")
    found = shipped().get(guide_id)
    if found is None:
        known = ", ".join(sorted(shipped())) or "none"
        raise EngineError("guide.unknown", f"no shipped guide {guide_id!r} (shipped: {known})")
    rel = f"{PROJECT_DIR}/{guide_id}.md"
    target = store.root / rel
    if target.exists():
        raise EngineError("guide.exists", f"{rel} already exists; the project's guide is kept as it is")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(found.file.read_bytes())
    out = documents.attest(store, rel, note, recorded_by=recorded_by)
    return {"guide": {**found.summary(), "where": "project", "path": rel}, **out}
