"""The static site is the same manual at the same URLs and anchors (tools/build_site.py; decision 0130)."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from baton import manual

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "tools" / "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tool = load_tool()
    out = tmp_path_factory.mktemp("site")
    files = tool.build(out, "9.9")
    tool.index(out)
    return tool, out, files


def test_every_topic_has_its_page_data_and_anchors(built):
    _tool, out, _files = built
    m = manual.Manual()
    for t in m.topics.values():
        assert (out / "9.9" / "manual" / t.part / t.slug / "index.html").is_file(), t.id
        data = json.loads((out / "9.9" / "api" / "manual" / "topic" / f"{t.id}.json").read_text(encoding="utf-8"))
        assert data["markdown"] == t.body.strip("\n") and [h["anchor"] for h in data["headings"]] == t.anchors
    assert (out / "9.9" / "manual" / "index.html").is_file() and (out / "9.9" / "404.html").is_file()


def test_the_site_is_self_contained_under_its_version_prefix(built):
    _tool, out, _files = built
    shell = (out / "9.9" / "manual" / "user" / "connect-an-account" / "index.html").read_text(encoding="utf-8")
    assert 'href="/9.9/app.css"' in shell and 'src="/9.9/render.js"' in shell and 'window.BATON_BASE = "/9.9"' in shell
    assert "localhost" not in shell and "127.0.0.1" not in shell and "<h1>Connect an API account</h1>" in shell
    for name in ("app.css", "render.js", "manual.js"):
        assert (out / "9.9" / name).read_text(encoding="utf-8") == (ROOT / "ui" / name).read_text(encoding="utf-8")


def test_search_data_and_the_version_index(built):
    tool, out, _files = built
    search = json.loads((out / "9.9" / "search.json").read_text(encoding="utf-8"))
    assert {s["id"] for s in search} == set(manual.Manual().topics) and all(s["title"] and s["text"] for s in search)
    tool.build(out, "9.10")
    tool.index(out)
    versions = json.loads((out / "versions.json").read_text(encoding="utf-8"))
    assert versions == {"latest": "9.10", "versions": ["9.9", "9.10"]}
    assert 'url=/9.10/manual/' in (out / "index.html").read_text(encoding="utf-8")


def test_a_manual_that_does_not_validate_is_not_published(tmp_path):
    tool = load_tool()
    base = tmp_path / "manual"
    shutil.copytree(ROOT / "manual", base)
    target = base / "user" / "connect-an-account.md"
    target.write_text(target.read_text(encoding="utf-8").replace("(admin.secrets#where-keys-are-kept)", "(admin.nope)"), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        tool.build(tmp_path / "out", "9.9", base)
    assert "does not resolve" in str(e.value) and not (tmp_path / "out" / "9.9").exists()


def test_the_page_script_is_prefix_aware_and_reads_json_in_the_site():
    js = (ROOT / "ui" / "manual.js").read_text(encoding="utf-8")
    assert "window.BATON_BASE" in js and "window.BATON_STATIC" in js and "/search.json" in js and ".json" in js
    assert "window.BATON_BASE" in (ROOT / "ui" / "render.js").read_text(encoding="utf-8")
