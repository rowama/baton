"""The manual page's Markdown renderer (ui/render.js; §13.10): nodes, never HTML; nesting does not loop."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.slow, pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's script")]

SAMPLE = """## Here, now {#here-now}

Choose **Get a key** (see [the guide](admin.secrets#where-keys-are-kept)), then `baton help` and *this*.

1. First **bold with `code`**
2. Second [site](https://example.com)

> **Warning:** careful <script>alert(1)</script>

| A | B |
|---|---|
| 1 | 2 |

```baton
baton ui
```

## Next {#next}
"""


def render(md: str) -> dict:
    out = subprocess.run(["node", str(ROOT / "tests" / "ui_render_check.mjs"), str(ROOT / "ui" / "render.js")], input=md,
                         capture_output=True, text=True, timeout=20, check=True)
    return json.loads(out.stdout)


def walk(n):
    yield n
    if isinstance(n, dict):
        for k in n["k"]:
            yield from walk(k)


def text(n) -> str:
    return n if isinstance(n, str) else "".join(text(k) for k in n["k"])


def test_sections_anchors_and_links():
    tree = render(SAMPLE)
    sections = [n for n in tree["k"] if n["t"] == "section"]
    assert [s["a"]["id"] if "id" in s["a"] else s["k"][0]["a"]["id"] for s in sections] == ["here-now", "next"]
    assert "here-now" in sections[0]["a"]["class"]
    links = {n["a"]["href"]: n for n in walk(tree) if isinstance(n, dict) and n["t"] == "a" and "href" in n["a"] and not n["a"]["href"].startswith("#")}
    assert "/manual/admin/secrets#where-keys-are-kept" in links
    ext = links["https://example.com"]["a"]
    assert ext["rel"] == "noopener noreferrer" and ext["target"] == "_blank"


def test_nested_inline_renders_and_terminates():
    tree = render(SAMPLE)
    strong = [n for n in walk(tree) if isinstance(n, dict) and n["t"] == "strong"]
    assert any(text(s) == "bold with code" for s in strong)
    assert any(n["t"] == "code" and text(n) == "baton help" for n in walk(tree) if isinstance(n, dict))


def test_html_in_a_topic_is_text_not_markup():
    tree = render(SAMPLE)
    assert not any(n["t"] == "script" for n in walk(tree) if isinstance(n, dict))
    assert "<script>alert(1)</script>" in text(tree)


def test_tables_notes_and_code():
    tree = render(SAMPLE)
    tags = [n["t"] for n in walk(tree) if isinstance(n, dict)]
    assert {"table", "th", "td", "pre", "ol"} <= set(tags)
    note = next(n for n in walk(tree) if isinstance(n, dict) and n["t"] == "div" and "callout" in n["a"].get("class", ""))
    assert "warning" in note["a"]["class"]
