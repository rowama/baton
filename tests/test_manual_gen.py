"""The generated provider pages follow the directory (§13.10; decisions 0117, 0133), and the page's help controls resolve."""

from __future__ import annotations

import re
from pathlib import Path

from baton import manual, manual_gen

ROOT = Path(__file__).resolve().parents[1]


def test_generated_pages_match_the_directory():
    assert manual_gen.stale() == [], "run: python tools/build_manual.py"


def test_every_directory_provider_has_a_page_with_its_command():
    m = manual.Manual()
    for name in manual_gen._providers():
        t, _ = m.resolve(f"providers.{manual_gen.slug(name)}")
        assert f"baton workers connect {name}" in t.body


def test_a_new_directory_entry_is_a_stale_manual(monkeypatch, tmp_path):
    real = manual_gen._providers()
    extra = type(next(iter(real.values())))(kind="openai_compatible", display_name="Newco", base_url="https://api.newco.example/v1", signup_url="https://newco.example/keys")
    monkeypatch.setattr(manual_gen, "_providers", lambda: {**real, "newco": extra})
    assert any("newco" in s for s in manual_gen.stale())
    assert "[Newco](https://newco.example/keys)" in manual_gen.render_all()["providers/newco.md"]


def test_the_local_runtimes_say_no_key_is_needed():
    text = (ROOT / "manual" / "providers" / "ollama.md").read_text(encoding="utf-8")
    assert "baton workers connect ollama --no-key" in text and "no key by default" in text


def test_the_page_uses_only_help_ids_the_map_knows_and_the_map_has_no_dead_ids():
    ctx = manual.context()
    used = set()
    for f in ("index.html", "app.js"):
        used |= set(re.findall(r'["\']((?:ui)\.[a-z.-]+)["\']', (ROOT / "ui" / f).read_text(encoding="utf-8")))
    assert used == set(ctx["ui"]), (used ^ set(ctx["ui"]))
    m = manual.Manual()
    for ref in list(ctx["ui"].values()) + list(ctx["errors"].values()):
        m.resolve(ref)


def test_the_page_opens_a_provider_topic_that_exists_for_every_directory_entry():
    js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert '"providers." + slug(' in js and 'slug = (name) => name.replace(/_/g, "-")' in js
    m = manual.Manual()
    assert all(f"providers.{manual_gen.slug(n)}" in m.topics for n in manual_gen._providers())


def test_every_refusal_the_map_explains_is_a_real_account_error_code():
    src = (ROOT / "src" / "baton" / "accounts.py").read_text(encoding="utf-8")
    for code in manual.context()["errors"]:
        assert f'"{code}"' in src, code
