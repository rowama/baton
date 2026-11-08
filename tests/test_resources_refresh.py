"""Bounded refresh and repeat runs of the worker resource manager (§6.4; 0079)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from baton import known_workers, resources
from baton.project import Project, init

from test_resources import found, gen, run_setup

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup_home(tmp_path, monkeypatch):
    """A home with an OpenRouter and an Anthropic resource, set up once against a copy of the data."""
    data_path = tmp_path / "known-workers.yaml"
    data_path.write_text((ROOT / "defaults" / "known-workers.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(known_workers, "default_path", lambda: data_path)
    home = tmp_path / "home"
    home.mkdir()
    resources.declare(home, "openrouter-main", provider="openrouter", credential="secret:or")
    resources.declare(home, "anthropic-key", provider="anthropic", credential="secret:an")
    run_setup(home, found("codex"))

    def change(fn):
        raw = yaml.safe_load(data_path.read_text(encoding="utf-8"))
        fn(raw)
        data_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    return home, change


def snapshot(home: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((home / "workers").glob("*.yaml"))}


def test_a_repeat_run_changes_nothing(setup_home):
    home, _ = setup_home
    before = snapshot(home)
    out = run_setup(home, found("codex"))
    assert out["written"] == out["refreshed"] == [] and snapshot(home) == before


def test_untouched_profiles_get_metadata_refreshes_edited_ones_never(setup_home):
    home, change = setup_home
    edited = home / "workers" / "anthropic-key-claude-opus-5-5.yaml"
    edited.write_text(edited.read_text(encoding="utf-8").replace("tier: strong", "tier: standard"), encoding="utf-8")
    mine = edited.read_bytes()

    def bump(raw):
        m = raw["models"]["anthropic/claude-opus-5-5"]
        m["context_tokens"] = 500000
        m["capabilities"] = [c for c in m["capabilities"] if c != "tool_use"]
        m["capability_basis"].pop("tool_use", None)
    change(bump)
    out = run_setup(home, found("codex"))
    assert out["refreshed"] == ["openrouter-main-claude-opus-5-5"]
    body = gen(home, "openrouter-main-claude-opus-5-5")
    assert body["context_tokens"] == 500000 and "tool_use" not in body["capabilities"]
    assert resources.ownership(body) == "untouched"  # still recognized as generated
    assert edited.read_bytes() == mine
    assert {"profile": "anthropic-key-claude-opus-5-5", "reason": "edited by the owner; never changed"} in out["kept"]


def test_a_refresh_never_changes_the_binding(setup_home):
    home, change = setup_home
    before = gen(home, "openrouter-main-claude-opus-5-5")

    def reroute(raw):
        for r in raw["routes"]:
            if r["provider"] == "openrouter" and r.get("model_id") == "anthropic/claude-opus-5-5":
                r["invocation"] = "openrouter/anthropic/claude-opus-5.5-preview"
    change(reroute)
    out = run_setup(home, found("codex"))
    assert gen(home, "openrouter-main-claude-opus-5-5") == before
    assert any(k["profile"] == "openrouter-main-claude-opus-5-5" and "its model would change" in k["reason"] for k in out["kept"])


def test_a_retired_model_keeps_its_profile_flagged(setup_home):
    home, change = setup_home
    change(lambda raw: raw["models"]["anthropic/claude-sonnet-5-5"].update(retired=True))
    out = run_setup(home, found("codex"))
    assert (home / "workers" / "anthropic-key-claude-sonnet-5-5.yaml").is_file()
    assert out["not_offered"]["anthropic-key-claude-sonnet-5-5"].startswith("retired")
    st = resources.status(home, discover_fn=found("codex"))
    assert st["generated"]["anthropic-key-claude-sonnet-5-5"]["flag"].startswith("retired")


def test_new_models_appear_only_with_an_explicit_run(setup_home, tmp_path):
    home, change = setup_home

    def add(raw):
        raw["models"]["anthropic/claude-newer-9-9"] = {**raw["models"]["anthropic/claude-sonnet-5-5"], "tier": "basic"}
        raw["routes"].append({"model_id": "anthropic/claude-newer-9-9", "provider": "anthropic", "adapter": "litellm_api",
                              "invocation": "anthropic/claude-newer-9-9", "supported": True})
    change(add)  # what installing a runtime with newer data amounts to
    root = tmp_path / "proj"
    root.mkdir()
    init(root, bare=True)
    assert "anthropic-key-claude-newer-9-9" not in Project.open(root, home=home).profiles()
    assert "anthropic-key-claude-newer-9-9" in resources.status(home, discover_fn=found("codex"))["available_not_generated"]
    run_setup(home, found("codex"))
    assert "anthropic-key-claude-newer-9-9" in Project.open(root, home=home).profiles()


def test_one_failing_profile_does_not_stop_the_others(setup_home, monkeypatch):
    home, change = setup_home
    change(lambda raw: raw["models"]["anthropic/claude-opus-5-5"].update(context_tokens=400000))
    real = resources._atomic_write

    def flaky(path, text):
        if path.name == "anthropic-key-claude-opus-5-5.yaml":
            raise OSError("disk full")
        real(path, text)
    monkeypatch.setattr(resources, "_atomic_write", flaky)
    out = run_setup(home, found("codex"))
    assert out["failed"] == [{"profile": "anthropic-key-claude-opus-5-5", "reason": "OSError: disk full"}]
    assert out["refreshed"] == ["openrouter-main-claude-opus-5-5"]


def test_verifying_an_unknown_name_says_nothing_was_checked(setup_home):
    home, _ = setup_home
    out = run_setup(home, found("codex"), verify=["nope"], verifier=lambda h, n, p: (True, "ok"))
    assert out["failed"] == [{"profile": "nope", "reason": "not a generated profile this machine offers now; nothing was checked"}]
