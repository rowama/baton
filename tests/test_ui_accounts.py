"""Connecting, re-keying and disconnecting an account, by the page and by the CLI (§6.1, §13.9; 0123)."""

from __future__ import annotations

import json
import os
import sys
import types
import urllib.error
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from baton import cli, listings, resources, ui
from baton.profiles import resolve_secret

from test_resources import found
from test_ui import Page, home  # noqa: F401  (the fixture)

KEY = "sk-or-SENTINEL-0123456789abcdef"
NEW = "sk-or-NEWKEY-0123456789abcdef"
RAW = {"data": [{"id": "acme/big", "name": "Big", "context_length": 200000, "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                 "supported_parameters": ["tools"], "architecture": {"output_modalities": ["text"], "input_modalities": ["text"]}}]}
KEYINFO = {"data": {"limit": 10, "limit_remaining": 7.5, "usage": 2.5}}


def provider_fake(good: set[str], seen: list[str] | None = None):
    """A provider that accepts only the keys in ``good``; records every URL asked."""
    def fetch(url, headers=None):
        key = (headers or {}).get("Authorization", "").removeprefix("Bearer ")
        if seen is not None:
            seen.append(url)
        if url == listings.KEY_SOURCES["openrouter"]:
            if key not in good:
                raise urllib.error.HTTPError(url, 401, "no", {}, None)
            return KEYINFO
        return RAW
    return fetch


@pytest.fixture
def fake(monkeypatch):
    good = {KEY, NEW}
    seen: list[str] = []
    monkeypatch.setattr(listings, "http_fetch", provider_fake(good, seen))
    monkeypatch.setattr(resources, "discover", found())
    return types.SimpleNamespace(good=good, seen=seen)


@pytest.fixture
def blank(tmp_path, monkeypatch):
    h = tmp_path / "blank"
    h.mkdir()
    monkeypatch.setattr(ui, "_discover", found())
    monkeypatch.setattr(resources, "discover", found())
    monkeypatch.delenv("BATON_SECRET_OPENROUTER_MAIN", raising=False)
    return h


def everything_under(home: Path) -> str:
    out = []
    for p in home.rglob("*"):
        if p.is_file() and p.parent.name != "secrets":
            out.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(out)


def connect_via_page(p, key=KEY, **extra):
    return p.post("/api/accounts", {"provider": "openrouter", "key": key, **extra})


@pytest.mark.not_slow("loopback requests only")
def test_connecting_checks_stores_declares_and_sets_up(blank, fake):
    p = Page(blank)
    try:
        r, raw = connect_via_page(p)
        out = json.loads(raw)
        assert r.status == 200 and out["account"] == "openrouter-main" and out["stored_in"] == "file" and out["check"]["ok"]
        assert any(x.startswith("openrouter-main-") for x in out["setup"]["written"])
        # The key is checked by one key-info read, never a model call, and it is stored outside every YAML.
        assert fake.seen[0] == listings.KEY_SOURCES["openrouter"]
        assert resolve_secret("openrouter_main", blank) == KEY
        assert yaml.safe_load((blank / "resources.yaml").read_text())["resources"]["openrouter-main"]["credential"] == "secret:openrouter_main"
        assert KEY not in raw.decode() and KEY not in everything_under(blank)
        if os.name == "posix":
            assert ((blank / "secrets" / "openrouter_main").stat().st_mode & 0o077) == 0 and ((blank / "secrets").stat().st_mode & 0o077) == 0
        state = json.loads(p.req("GET", "/api/state")[1])
        assert state["accounts"]["openrouter-main"]["kept_in"] == ["file"]
        assert any(m["resource"] == "openrouter-main" for m in state["models"])
        assert KEY not in json.dumps(state)
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_a_refused_key_changes_nothing(blank, fake):
    p = Page(blank)
    try:
        r, raw = connect_via_page(p, key="sk-or-WRONG-0123456789")
        out = json.loads(raw)
        assert r.status == 422 and out["error"] == "accounts.key_refused" and "did not accept" in out["message"]
        assert "WRONG" not in raw.decode()
        assert not (blank / "resources.yaml").exists() and not (blank / "secrets").exists()
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_a_bad_replacement_leaves_the_old_key_and_account_working(blank, fake):
    p = Page(blank)
    try:
        assert connect_via_page(p)[0].status == 200
        r, raw = p.post("/api/accounts/openrouter-main/key", {"key": "sk-or-BAD-0123456789"})
        out = json.loads(raw)
        assert r.status == 422 and "Your current key is unchanged" in out["message"]
        assert resolve_secret("openrouter_main", blank) == KEY
        assert "openrouter-main" in yaml.safe_load((blank / "resources.yaml").read_text())["resources"]
        # A good one replaces it.
        r, raw = p.post("/api/accounts/openrouter-main/key", {"key": NEW})
        assert r.status == 200 and json.loads(raw)["replaced"] is True
        assert resolve_secret("openrouter_main", blank) == NEW
        assert NEW not in raw.decode() and NEW not in everything_under(blank)
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_disconnecting_flags_its_profiles_and_removes_the_key_only_when_asked(blank, fake):
    p = Page(blank)
    try:
        connect_via_page(p)
        r, raw = p.req("DELETE", "/api/accounts/openrouter-main", headers={"X-Baton-UI": "1"}, body={})
        out = json.loads(raw)
        assert r.status == 200 and out["key_removed_from"] == [] and out["key_kept"] == "openrouter_main"
        assert (blank / "secrets" / "openrouter_main").is_file()
        state = json.loads(p.req("GET", "/api/state")[1])
        mine = [n for n, g in state["generated"].items() if n.startswith("openrouter-main-")]
        assert mine and all(state["generated"][n]["flag_code"] == "resource_gone" for n in mine)
        connect_via_page(p)
        r, raw = p.req("DELETE", "/api/accounts/openrouter-main", headers={"X-Baton-UI": "1"}, body={"forget_key": True})
        assert json.loads(raw)["key_removed_from"] == ["file"] and not (blank / "secrets" / "openrouter_main").exists()
        assert p.req("DELETE", "/api/accounts/nope", headers={"X-Baton-UI": "1"}, body={})[0].status == 422
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_a_key_in_the_environment_is_not_silently_shadowed(blank, fake, monkeypatch):
    p = Page(blank)
    try:
        connect_via_page(p)
        monkeypatch.setenv("BATON_SECRET_OPENROUTER_MAIN", KEY)
        r, raw = p.post("/api/accounts/openrouter-main/key", {"key": NEW})
        assert r.status == 422 and "BATON_SECRET_OPENROUTER_MAIN" in json.loads(raw)["message"]
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_the_keyring_is_used_when_it_works_and_the_file_when_it_does_not(blank, fake, monkeypatch):
    store: dict[tuple[str, str], str] = {}
    kr = types.ModuleType("keyring")
    kr.set_password = lambda s, n, v: store.__setitem__((s, n), v)
    kr.get_password = lambda s, n: store.get((s, n))
    kr.delete_password = lambda s, n: store.pop((s, n), None)
    monkeypatch.setitem(sys.modules, "keyring", kr)
    p = Page(blank)
    try:
        out = json.loads(connect_via_page(p)[1])
        assert out["stored_in"] == "keyring" and store[("baton", "openrouter_main")] == KEY
        assert not (blank / "secrets" / "openrouter_main").exists()
        out = json.loads(p.req("DELETE", "/api/accounts/openrouter-main", headers={"X-Baton-UI": "1"}, body={"forget_key": True})[1])
        assert out["key_removed_from"] == ["keyring"] and not store
        def broken(*a):
            raise RuntimeError("no backend")
        kr.set_password = broken
        assert json.loads(connect_via_page(p)[1])["stored_in"] == "file"
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_the_page_and_the_cli_write_the_same_files(tmp_path, monkeypatch, fake):
    monkeypatch.setattr(ui, "_discover", found())
    page_home, cli_home = tmp_path / "page", tmp_path / "cli"
    page_home.mkdir(); cli_home.mkdir()
    p = Page(page_home)
    try:
        assert connect_via_page(p)[0].status == 200
    finally:
        p.close()
    monkeypatch.setenv("BATON_HOME", str(cli_home))
    res = CliRunner().invoke(cli.app, ["workers", "connect", "openrouter", "--key-stdin", "--json"], input=KEY + "\n")
    assert res.exit_code == 0, res.output
    assert KEY not in res.output
    def tree(h: Path) -> dict[str, str]:
        return {str(f.relative_to(h)): f.read_text(encoding="utf-8") for f in sorted(h.rglob("*"))
                if f.is_file() and f.parent.name != "listings" and f.name not in ("ui.json", "capability-states.yaml") and "diag" not in f.parts}
    a, b = tree(page_home), tree(cli_home)
    assert a.keys() == b.keys() and "secrets/openrouter_main" in a
    for k in a:
        if k.startswith("workers/") or k == "resources.yaml" or k.startswith("secrets/"):
            assert a[k].replace(str(page_home), "H") == b[k].replace(str(cli_home), "H"), k


@pytest.mark.not_slow("loopback requests only")
def test_the_cli_refuses_a_bad_key_and_disconnects(tmp_path, monkeypatch, fake):
    monkeypatch.setenv("BATON_HOME", str(tmp_path))
    monkeypatch.setattr(resources, "discover", found())
    bad = CliRunner().invoke(cli.app, ["workers", "connect", "openrouter", "--key-stdin", "--json"], input="sk-or-BAD-0123456789\n")
    assert bad.exit_code == 1 and "accounts.key_refused" in bad.output and "BAD" not in bad.output
    assert json.loads(bad.output)["help"] == "user.connect-an-account#key-refused"  # the pointer the page shows too
    plain = CliRunner().invoke(cli.app, ["workers", "connect", "openrouter", "--key-stdin"], input="sk-or-BAD-0123456789\n")
    assert "More: baton help user.connect-an-account#key-refused" in plain.output
    ok = CliRunner().invoke(cli.app, ["workers", "connect", "openrouter", "--key-stdin", "--json"], input=KEY + "\n")
    assert ok.exit_code == 0
    off = CliRunner().invoke(cli.app, ["workers", "disconnect", "openrouter-main", "--forget-key", "--json"])
    assert off.exit_code == 0 and json.loads(off.output)["key_removed_from"] == ["file"]


@pytest.mark.not_slow("loopback requests only")
def test_a_key_is_in_no_response_log_event_or_diagnostic(blank, fake, monkeypatch):
    p = Page(blank)
    try:
        bodies = [connect_via_page(p)[1], connect_via_page(p, key="sk-or-WRONG-0123456789")[1],
                  p.post("/api/accounts/openrouter-main/key", {"key": NEW})[1], p.req("GET", "/api/state")[1]]
    finally:
        p.close()
    for b in bodies:
        assert KEY.encode() not in b and NEW.encode() not in b and b"WRONG" not in b
    assert KEY not in everything_under(blank) and NEW not in everything_under(blank)
    from baton import diag
    for f in diag.home().rglob("*"):
        if f.is_file():
            assert KEY not in f.read_text(encoding="utf-8", errors="replace")


@pytest.mark.not_slow("loopback requests only")
def test_a_local_endpoint_needs_no_key(blank, fake):
    p = Page(blank)
    try:
        r, raw = p.post("/api/accounts", {"provider": "ollama", "name": "ollama-here"})
        assert r.status == 200 and json.loads(raw)["stored_in"] is None
        r, raw = p.post("/api/accounts", {"provider": "openrouter"})
        assert r.status == 422 and json.loads(raw)["error"] == "accounts.no_key"
    finally:
        p.close()
