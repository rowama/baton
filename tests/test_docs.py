"""The docs hold together (docs/README.md).

Every § reference in code, tests, skills, shipped data and docs resolves through the § index in
docs/README.md to a file that holds that section; every numbered heading is indexed; relative
links in docs/ resolve; decision records and change docs are well formed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from conftest import ROOT

DOCS = ROOT / "docs"
INDEX = DOCS / "README.md"
SCANNED = ["src", "tests", "skills", "examples", "defaults", "builtin", "docs", "README.md", "CLAUDE.md"]
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".j2", ".txt", ".toml"}
REFERENCE = re.compile(r"§(\d+(?:\.\d+)?)(?: #(\d+))?")
INDEX_ROW = re.compile(r"^\| §(\d+(?:\.\d+)?)(?: #(\d+))? \| \[[^\]]*\]\(([^)#]+)\)")
HEADING = re.compile(r"^(?:## (\d+)\. |### (\d+\.\d+) )")
LINK = re.compile(r"\]\(([^)\s]+)\)")
STATUSES = {"proposed", "accepted", "deferred", "superseded"}
CHANGE_STATUSES = {"proposed", "accepted", "in-progress", "done", "abandoned"}


def _index() -> tuple[dict[str, Path], dict[int, Path]]:
    sections: dict[str, Path] = {}
    open_decisions: dict[int, Path] = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        m = INDEX_ROW.match(line)
        if m:
            target = (DOCS / m.group(3)).resolve()
            if m.group(2):
                open_decisions[int(m.group(2))] = target
            else:
                sections[m.group(1)] = target
    return sections, open_decisions


def _headings(path: Path) -> set[str]:
    found = set()
    fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fence = not fence
            continue
        m = None if fence else HEADING.match(line)
        if m:
            found.add(m.group(1) or m.group(2))
    return found


def _scanned_files():
    for name in SCANNED:
        path = ROOT / name
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for f in files:
            if f.suffix in TEXT_SUFFIXES and "__pycache__" not in f.parts:
                yield f


def _references():
    for f in _scanned_files():
        for lineno, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in REFERENCE.finditer(line):
                yield f.relative_to(ROOT).as_posix(), lineno, m.group(1), m.group(2)


def _front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: no front matter"
    return yaml.safe_load(text[4:text.index("\n---\n", 4)])


def test_every_section_reference_resolves():
    sections, open_decisions = _index()
    headings: dict[Path, set[str]] = {}
    problems = []
    for where, lineno, number, item in _references():
        target = sections.get(number)
        if target is None:
            problems.append(f"{where}:{lineno}: §{number} is not in the docs/README.md index")
            continue
        if not target.is_file():
            problems.append(f"{where}:{lineno}: §{number} maps to missing {target}")
            continue
        if number not in headings.setdefault(target, _headings(target)):
            problems.append(f"{where}:{lineno}: §{number} has no heading in {target.relative_to(ROOT).as_posix()}")
        if item is not None and number == "18" and not open_decisions.get(int(item), Path("/nonexistent")).is_file():
            problems.append(f"{where}:{lineno}: §18 #{item} has no decision record in the index")
    assert not problems, "\n".join(problems)


def test_every_numbered_heading_is_indexed():
    sections, _ = _index()
    docs = [DOCS / "principles.md", INDEX, *sorted((DOCS / "design").glob("*.md")), *sorted((DOCS / "history").glob("*.md"))]
    missing = [f"{d.relative_to(ROOT).as_posix()}: §{n}" for d in docs for n in sorted(_headings(d)) if sections.get(n) != d.resolve()]
    assert not missing, "headings missing from (or misplaced in) the § index:\n" + "\n".join(missing)


def test_every_open_decision_item_has_its_record():
    _, open_decisions = _index()
    assert sorted(open_decisions) == list(range(1, len(open_decisions) + 1))
    for n, target in open_decisions.items():
        assert target.is_file() and target.name.startswith(f"{n:04d}-"), (n, target)


def _links(path: Path):
    fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        for m in LINK.finditer(re.sub(r"`[^`]*`", "", line)):
            yield lineno, m.group(1)


@pytest.mark.parametrize("doc", [*sorted(DOCS.rglob("*.md")), ROOT / "README.md"], ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc):
    broken = []
    for lineno, target in _links(doc):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue  # external, or an anchor in the same file
        path = target.split("#", 1)[0]
        if not (doc.parent / path).exists():
            broken.append(f"{doc.relative_to(ROOT).as_posix()}:{lineno}: {target}")
    assert not broken, "\n".join(broken)


def test_decision_records_are_well_formed():
    records = sorted((DOCS / "decisions").glob("*.md"))
    assert records
    numbers = []
    for path in records:
        m = re.fullmatch(r"(\d{4})-[a-z0-9-]+\.md", path.name)
        assert m, path.name
        meta = _front_matter(path)
        assert meta["id"] == m.group(1), path.name
        assert meta["status"] in STATUSES, path.name
        assert meta["status"] == "proposed" or meta["date"], f"{path.name}: a decided record needs its date"
        text = path.read_text(encoding="utf-8")
        assert "\n## Context\n" in text and "\n## Decision\n" in text, path.name
        numbers.append(int(m.group(1)))
    assert numbers == list(range(1, len(numbers) + 1)), "decision numbers must be consecutive from 0001"


def test_change_docs_name_existing_design_docs_and_decisions():
    decisions = {p.name[:4] for p in (DOCS / "decisions").glob("*.md")}
    changes = [p for p in sorted((DOCS / "changes").glob("*.md")) if p.name != "TEMPLATE.md"]
    for path in changes:
        meta = _front_matter(path)
        assert meta["id"] == path.stem, path.name
        assert meta["status"] in CHANGE_STATUSES and meta["level"] in {"minor", "standard", "major"}, path.name
        for doc in meta.get("touches") or []:
            assert (DOCS / doc).is_file(), f"{path.name}: touches missing {doc}"
        for d in meta.get("decisions") or []:
            assert str(d) in decisions, f"{path.name}: no decision record {d}"
        text = path.read_text(encoding="utf-8")
        for heading in ("## Request", "## Design", "## Plan", "## Log"):
            assert f"\n{heading}\n" in text, f"{path.name}: missing {heading}"
