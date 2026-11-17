"""Guidance documents (change 2026-11-quick-runs, Slice 1; Decisions 0145, 0163; §5.2, §5.7):
their format and check, the shipped starter set, `guides()`, `catalog.guides`, and `guides copy`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from baton import engine, guides
from baton.mcp_server import build_server
from baton.recipe import validate_recipe
from baton.store import Store
from projectkit import Cli, git, make_git_project, make_home
from runkit import WRITER, Clock, make_recipe, start

GOOD = """---
format: baton-guide/1
id: shop-rota
version: 2
title: Shop rota
description: Who works which shift.
produces: a weekly rota (Markdown)
---

## Purpose

Plan the week's shifts.

## What to produce

A table of shifts.

## What good looks like

Every shift covered.

## What to ask the owner

Who is available.
"""


def _problems(text: str) -> list[str]:
    c = guides.check_text(text)
    assert c.guide is None
    return c.problems


# ---------------------------------------------------------------------------
# The format and its check
# ---------------------------------------------------------------------------


def test_a_well_formed_guide_passes_with_its_fields():
    c = guides.check_text(GOOD, path="guides/shop-rota.md")
    assert c.problems == []
    assert c.guide.summary() == {"id": "shop-rota", "version": 2, "title": "Shop rota", "description": "Who works which shift.",
                                 "produces": "a weekly rota (Markdown)", "where": "project", "path": "guides/shop-rota.md"}


def test_windows_line_endings_are_read_as_the_same_guide():
    assert guides.check_text(GOOD.replace("\n", "\r\n")).problems == []


@pytest.mark.parametrize("field", guides.FIELDS)
def test_each_missing_field_is_refused(field):
    text = "\n".join(line for line in GOOD.splitlines() if not line.startswith(f"{field}:")) + "\n"
    assert f"front matter: missing {field!r}" in _problems(text)


@pytest.mark.parametrize("old,new,expected", [
    ("format: baton-guide/1", "format: baton-guide/2", "format must be 'baton-guide/1'"),
    ("id: shop-rota", "id: Shop Rota", "id 'Shop Rota' must be lower-case words"),
    ("version: 2", "version: 0", "version 0 must be a whole number from 1"),
    ("version: 2", "version: two", "version 'two' must be a whole number"),
    ("title: Shop rota", "title: ''", "title must be non-empty text"),
    ("produces: a weekly rota (Markdown)", "produces: [a, b]", "produces must be non-empty text"),
    ("version: 2", "version: 2\nworker: someone", "unknown key 'worker'"),
])
def test_bad_front_matter_is_refused(old, new, expected):
    assert any(expected in p for p in _problems(GOOD.replace(old, new)))


def test_no_front_matter_is_refused():
    assert _problems(GOOD.split("---\n", 2)[2])[0].startswith("no front matter")


@pytest.mark.parametrize("section", guides.SECTIONS)
def test_each_missing_or_empty_section_is_refused(section):
    assert f"body: missing the section '## {section}'" in _problems(GOOD.replace(f"## {section}\n", ""))
    emptied = GOOD.split(f"## {section}\n")
    rest = emptied[1].split("\n## ", 1)
    text = emptied[0] + f"## {section}\n\n" + ("## " + rest[1] if len(rest) > 1 else "")
    assert f"body: the section '## {section}' is empty" in _problems(text)


@pytest.mark.parametrize("where", ["title: Shop rota for gemini", "Plan the week's shifts with claude-sonnet."])
def test_a_vendor_name_anywhere_is_refused(where):
    text = GOOD.replace("title: Shop rota", where) if where.startswith("title") else GOOD.replace("Plan the week's shifts.", where)
    assert any("names the vendor" in p for p in _problems(text))


# ---------------------------------------------------------------------------
# The starter set and the listing
# ---------------------------------------------------------------------------

STARTERS = ["decision-record", "lean-business-plan", "marketing-plan", "project-charter", "standard-operating-procedure"]


def test_the_starter_guides_ship_and_pass_the_check():
    shipped = guides.shipped()
    assert sorted(shipped) == STARTERS
    for gid, g in shipped.items():
        assert guides.check_file(g.file).problems == [], gid
        assert g.where == "shipped" and g.path == f"examples/guides/{gid}.md"


def test_the_listing_puts_the_projects_guides_beside_the_shipped_ones(tmp_path):
    (tmp_path / "guides").mkdir()
    (tmp_path / "guides" / "shop-rota.md").write_text(GOOD, encoding="utf-8")
    (tmp_path / "guides" / "lean-business-plan.md").write_text(
        GOOD.replace("id: shop-rota", "id: lean-business-plan"), encoding="utf-8")
    (tmp_path / "guides" / "broken.md").write_text("# not a guide\n", encoding="utf-8")
    (tmp_path / "guides" / "misnamed.md").write_text(GOOD, encoding="utf-8")
    out = guides.listing(tmp_path)
    assert [(g["id"], g["where"]) for g in out["guides"]] == [
        ("decision-record", "shipped"), ("lean-business-plan", "project"), ("lean-business-plan", "shipped"),
        ("marketing-plan", "shipped"), ("project-charter", "shipped"), ("shop-rota", "project"),
        ("standard-operating-procedure", "shipped")]
    assert {p["path"] for p in out["problems"]} == {"guides/broken.md", "guides/misnamed.md"}
    assert "its id is 'shop-rota'" in next(p for p in out["problems"] if p["path"] == "guides/misnamed.md")["problems"][0]
    assert guides.catalog_input(tmp_path) == out["guides"]


# ---------------------------------------------------------------------------
# catalog.guides (§5.2)
# ---------------------------------------------------------------------------


def _reader(root: Path) -> Path:
    return make_recipe(root, [{"id": "look", "output_schema": "schemas/out.json",
                               "inputs": [{"name": "guides", "from": "catalog.guides", "required": True}]}],
                       schemas={"out.json": {"type": "object"}})


def test_a_step_receives_catalog_guides_deterministically(tmp_path):
    recipe = _reader(tmp_path / "toy")
    with Store(tmp_path / "project", clock=Clock()) as store:
        (store.root / "guides").mkdir(parents=True)
        (store.root / "guides" / "shop-rota.md").write_text(GOOD, encoding="utf-8")
        ctx = start(store, recipe, {})
        p = engine.begin_attempt(ctx, "look", "owner", WRITER)
        got = (p.dir / "inputs" / "guides.json").read_bytes()
        assert [g["id"] for g in json.loads(got)] == sorted(STARTERS + ["shop-rota"])
        assert json.loads(got) == guides.catalog_input(store.root)


def test_a_misspelt_catalog_source_is_a_reference_error(tmp_path):
    recipe = _reader(tmp_path / "toy")
    (recipe / "recipe.yaml").write_text((recipe / "recipe.yaml").read_text(encoding="utf-8").replace("catalog.guides", "catalog.guide"),
                                        encoding="utf-8")
    _, issues = validate_recipe(recipe)
    assert "ref.invalid" in {i.code for i in issues}


# ---------------------------------------------------------------------------
# guides, guides copy, guides check (CLI, MCP, API)
# ---------------------------------------------------------------------------


def _project(tmp_path: Path) -> tuple[Path, Cli]:
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project), "--bare")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "Adopt Baton")
    return project, cli


@pytest.mark.not_slow("in-process CLI, one commit")
def test_guides_copy_attests_a_shipped_guide_and_never_overwrites(tmp_path):
    project, cli = _project(tmp_path)
    assert [g["id"] for g in cli.run("guides")["guides"]] == STARTERS
    out = cli.run("guides", "copy", "lean-business-plan", "--note", "Use the standard business plan guide.")
    target = project / "guides" / "lean-business-plan.md"
    assert target.read_bytes() == guides.shipped()["lean-business-plan"].file.read_bytes()
    assert out["guide"]["where"] == "project" and out["guide"]["path"] == "guides/lean-business-plan.md"
    doc = {d["path"]: d for d in cli.run("documents")["documents"]}["guides/lean-business-plan.md"]
    assert doc["kind"] == "attested" and doc["media_type"] == "text/markdown"
    assert out["checkpoint"]["committed"] is True
    assert git(project, "status", "--porcelain").strip() == ""
    listed = cli.run("guides")["guides"]
    assert [(g["id"], g["where"]) for g in listed if g["id"] == "lean-business-plan"] == [
        ("lean-business-plan", "project"), ("lean-business-plan", "shipped")]
    again = cli("guides", "copy", "lean-business-plan", "--note", "Again.", expect=1).payload
    assert again["error"] == "guide.exists"
    assert cli("guides", "copy", "no-such-guide", "--note", "Yes.", expect=1).payload["error"] == "guide.unknown"
    assert cli("guides", "copy", "marketing-plan", "--note", " ", expect=1).payload["error"] == "attest.note_required"
    assert not (project / "guides" / "marketing-plan.md").exists()


@pytest.mark.not_slow("in-process CLI, no commits")
def test_guides_check_is_a_gate_helper(tmp_path):
    project, cli = _project(tmp_path)
    good = tmp_path / "good.md"
    good.write_text(GOOD, encoding="utf-8")
    assert cli.run("guides", "check", str(good))["guide"]["id"] == "shop-rota"
    bad = tmp_path / "bad.md"
    bad.write_text(GOOD.replace("version: 2\n", ""), encoding="utf-8")
    res = cli("guides", "check", str(bad), expect=1).payload
    assert res["ok"] is False and "front matter: missing 'version'" in res["problems"]


@pytest.mark.not_slow("in-process MCP, no commits")
def test_mcp_and_api_list_the_same_guides(tmp_path, monkeypatch):
    from mcp import Client

    from baton.engine import Api

    project, cli = _project(tmp_path)
    monkeypatch.setenv("BATON_HOME", str(tmp_path / "home"))

    async def main():
        async with Client(build_server(project, "bob@host2")) as c:
            return (await c.call_tool("guides", {})).structured_content

    via_mcp = asyncio.run(main())
    api = Api.open(project, home=tmp_path / "home")
    try:
        via_api = api.guides()
    finally:
        api.close()
    assert via_mcp["guides"] == via_api["guides"] == cli.run("guides")["guides"]
