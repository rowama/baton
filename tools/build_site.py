"""Build the manual as a static site (maintainers only; never shipped; decision 0130).

    python tools/build_site.py [--out build/site] [--version 0.9]

The site is the same corpus, the same page script and the same URLs and anchors as `baton ui`'s Manual: every topic is at
`/<version>/manual/<part>/<slug>/` with its `#anchor`, and the script reads JSON files where the page reads the local API. One
copy is written per released minor version; `index.html` forwards to the newest. Choosing a host and publishing are separate.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path

from baton import __version__, manual

ROOT = Path(__file__).resolve().parents[1]

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="{base}/app.css">
</head>
<body>
<a class="skip" href="#doc">Skip to content</a>
<header class="top">
  <a class="brand" href="{base}/manual"><span class="mark" aria-hidden="true"></span>Baton <span class="muted">manual {version}</span></a>
  <div class="search">
    <input id="q" type="search" placeholder="Search the manual" aria-label="Search the manual" autocomplete="off" spellcheck="false" aria-controls="hits" aria-expanded="false">
    <kbd class="hint" aria-hidden="true">/</kbd>
    <ul id="hits" role="listbox" aria-label="Search results" hidden></ul>
  </div>
  <button id="quit" class="quiet" hidden>Close</button>
</header>
<div id="view-setup" hidden></div>
<div id="view-manual" hidden>
  <button id="nav-toggle" class="quiet nav-toggle" aria-expanded="false" aria-controls="nav">Contents</button>
  <div class="reader">
    <nav id="nav" aria-label="Manual contents"></nav>
    <main id="doc" tabindex="-1">
      {content}
    </main>
    <aside id="toc" aria-label="On this page"></aside>
  </div>
</div>
<script>window.BATON_BASE = {base_js}; window.BATON_STATIC = true;</script>
<script src="{base}/render.js"></script>
<script src="{base}/manual.js"></script>
</body>
</html>
"""


def minor(version: str) -> str:
    m = re.match(r"(\d+)\.(\d+)", version)
    return f"{m.group(1)}.{m.group(2)}" if m else version


def _noscript(title: str, summary: str) -> str:
    """What a crawler or a reader without scripts sees: the title and summary (the script fills in the rest)."""
    return f"<h1>{html.escape(title)}</h1><p class=\"lead\">{html.escape(summary)}</p><noscript><p>This page needs JavaScript to show the manual.</p></noscript>"


def build(out: Path, version: str, base: Path | None = None) -> list[Path]:
    """Write one version of the site under ``out/<version>``; returns every file written."""
    m = manual.Manual(base)
    problems = manual.validate(m)
    if problems:
        raise SystemExit("the manual does not validate:\n" + "\n".join(problems[:20]))
    site_base = f"/{version}"
    dest = out / version
    if dest.exists():
        shutil.rmtree(dest)
    written: list[Path] = []

    def write(rel: str, text: str) -> None:
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        written.append(p)

    def page(title: str, description: str, content: str) -> str:
        return SHELL.format(title=html.escape(title), description=html.escape(description), base=site_base, version=html.escape(version),
                            base_js=json.dumps(site_base), content=content)

    for name in ("app.css", "render.js", "manual.js"):
        write(name, (ROOT / "ui" / name).read_text(encoding="utf-8"))
    tree = m.tree()
    write("api/manual/tree.json", json.dumps({"ok": True, "parts": tree}, ensure_ascii=False))
    for t in m.topics.values():
        write(f"api/manual/topic/{t.id}.json", json.dumps({"ok": True, **m.page(t.id)}, ensure_ascii=False))
        write(f"manual/{t.part}/{t.slug}/index.html", page(f"{t.title} · Baton manual", t.summary, _noscript(t.title, t.summary)))
    write("search.json", json.dumps([{"id": t.id, "title": t.title, "summary": t.summary, "text": re.sub(r"\s+", " ", t.body),
                                     "headings": [{"text": h.text, "anchor": h.anchor} for h in t.headings]} for t in m.topics.values()], ensure_ascii=False))
    landing = page("Manual · Baton", "Everything about using and running Baton.", _noscript("Baton manual", "Everything about using and running Baton."))
    write("manual/index.html", landing)
    write("404.html", landing)
    return written


def index(out: Path) -> None:
    """``out/versions.json`` and an ``index.html`` that forwards to the newest version present."""
    versions = sorted((d.name for d in out.iterdir() if d.is_dir() and re.fullmatch(r"\d+\.\d+", d.name)), key=lambda v: tuple(map(int, v.split("."))))
    if not versions:
        return
    (out / "versions.json").write_text(json.dumps({"latest": versions[-1], "versions": versions}), encoding="utf-8")
    (out / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>Baton manual</title><meta http-equiv="refresh" content="0; url=/{versions[-1]}/manual/">'
        f'<a href="/{versions[-1]}/manual/">Baton manual {versions[-1]}</a>\n', encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "site")
    ap.add_argument("--version", default=minor(__version__))
    a = ap.parse_args()
    files = build(a.out, a.version)
    index(a.out)
    print(f"{len(files)} files in {a.out / a.version}")


if __name__ == "__main__":
    main()
