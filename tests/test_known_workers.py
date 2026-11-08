"""Known-workers data: schema, validation, the shipped seed and packaging (0080, 0082)."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path

import pytest

from baton import data, known_workers, vocab
from baton.adapters import ADAPTERS
from baton.data import load_yaml

ROOT = Path(__file__).resolve().parents[1]
VOCAB = vocab.load(vocab.DEFAULT)


def shipped() -> dict:
    return load_yaml(known_workers.default_path())


def codes(raw: dict) -> set[str]:
    _kw, issues = known_workers.validate(raw, VOCAB, set(ADAPTERS))
    return {i.code for i in issues}


def test_the_shipped_seed_validates_and_spans_harness_direct_and_intermediary():
    kw = known_workers.load(VOCAB)
    kinds = {kw.providers[r.provider].kind for r in kw.routes if r.supported}
    assert {"harness", "direct_api", "intermediary"} <= kinds
    opus = [r for r in kw.routes if r.model_id == "anthropic/claude-opus-5-5"]
    # One identity, several routes with their own invocation identifiers: direct,
    # an intermediary, and a harness pinned to it.
    assert {r.provider for r in opus} == {"anthropic", "openrouter", "claude_code"} and len({r.invocation for r in opus}) == 3
    # A harness either runs its default (a mutable alias: no identity, a creator)
    # or is pinned to a known model by its full ID.
    for r in kw.routes:
        if kw.providers[r.provider].kind == "harness" and r.invocation is None:
            assert r.alias and r.model_id is None and r.creator
        elif kw.providers[r.provider].kind == "harness":
            assert not r.alias and r.model_id in kw.models and r.invocation == r.model_id.split("/", 1)[1]
    # Research and verification are separate: nothing in the seed claims a live check.
    assert all(r.verified is None for r in kw.routes)
    assert all(m.sources and m.researched for m in kw.models.values())


def test_packaging_ships_the_data_and_not_the_researcher():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/baton"]
    included = wheel["force-include"]
    assert included.get("defaults") == "baton/_data/defaults"
    assert not any(k.startswith("tools") for k in included)
    assert (data.path("defaults") / "known-workers.yaml").is_file()


def _bad(mutate) -> set[str]:
    raw = copy.deepcopy(shipped())
    mutate(raw)
    return codes(raw)


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda r: r["models"]["anthropic/claude-opus-5-5"]["capabilities"].append("telepathy"), "known_workers.unknown_capability"),
        (lambda r: r["models"]["anthropic/claude-opus-5-5"]["capabilities"].append("loopback_network"), "known_workers.machine_dependent"),
        (lambda r: r["routes"][-1]["capabilities"].append("loopback_network"), "known_workers.machine_dependent"),
        (lambda r: r["models"]["anthropic/claude-opus-5-5"].update(tier="mythic"), "known_workers.unknown_tier"),
        (lambda r: r["models"]["anthropic/claude-opus-5-5"].update(creator="openai"), "known_workers.model_id"),
        (lambda r: r["models"]["anthropic/claude-opus-5-5"].update(sources=[]), "known_workers.invalid"),
        (lambda r: r["routes"][0].update(model_id="anthropic/nope"), "known_workers.unknown_model"),
        (lambda r: r["routes"][0].update(provider="nowhere"), "known_workers.unknown_provider"),
        (lambda r: r["routes"][0].update(adapter="vision_api"), "known_workers.unknown_adapter"),
        (lambda r: r["routes"][0].pop("invocation"), "known_workers.no_invocation"),
        (lambda r: r["routes"][-1].pop("creator"), "known_workers.no_identity"),
        (lambda r: r["routes"][-1].update(alias=False), "known_workers.no_identity"),
        (lambda r: r["routes"][0].update(creator="openai"), "known_workers.creator_mismatch"),
        (lambda r: r["routes"].append(dict(r["routes"][0])), "known_workers.duplicate_route"),
        (lambda r: r.update(format="baton-known-workers/9"), "known_workers.format"),
        (lambda r: r["routes"][0].update(verified={"date": "2026-11-06"}), "known_workers.invalid"),
    ],
)
def test_validation_rejects(mutate, code):
    assert code in _bad(mutate)


def test_research_may_cover_what_the_runtime_cannot_execute():
    def add_unsupported(r):
        r["models"]["acme/transcriber-1"] = {"creator": "acme", "category": "transcription", "researched": "2026-11-06",
                                             "sources": [{"url": "https://example.org/acme", "retrieved": "2026-11-06"}]}
        r["providers"]["acme"] = {"kind": "direct_api"}
        r["routes"].append({"model_id": "acme/transcriber-1", "provider": "acme", "adapter": "audio_api", "invocation": "t-1", "supported": False})
    assert _bad(add_unsupported) == set()


def _validate(raw: dict, require_basis: bool = False) -> set[str]:
    _kw, issues = known_workers.validate(raw, VOCAB, set(ADAPTERS), require_basis=require_basis)
    return {i.code for i in issues}


def test_every_shipped_capability_has_a_basis_and_the_seed_is_judgment():
    raw = shipped()
    assert _validate(raw, require_basis=True) == set()
    kw = known_workers.load(VOCAB)
    for m in kw.models.values():
        assert set(m.capability_basis) == set(m.capabilities)
    for r in kw.routes:
        assert set(r.capability_basis) == set(r.capabilities)


@pytest.mark.parametrize(
    "basis, code",
    [
        ({"kind": "documented"}, "known_workers.basis_incomplete"),
        ({"kind": "catalog", "litellm": "supports_vision"}, "known_workers.basis_incomplete"),   # shows vision, not structured_output
        ({"kind": "catalog"}, "known_workers.basis_incomplete"),
        ({"kind": "judgment"}, "known_workers.basis_incomplete"),
        ({"kind": "judgment", "reason": ""}, "known_workers.invalid"),
        ({"kind": "hunch", "reason": "x"}, "known_workers.invalid"),
    ],
)
def test_a_basis_must_carry_what_its_kind_needs(basis, code):
    def mutate(r):
        r["models"]["anthropic/claude-opus-5-5"]["capability_basis"]["structured_output"] = basis
    assert code in _bad(mutate)


def test_basis_kinds_and_unclaimed_basis():
    def good(r):
        b = r["models"]["anthropic/claude-opus-5-5"]["capability_basis"]
        b["structured_output"] = {"kind": "catalog", "litellm": "supports_response_schema"}
        b["tool_use"] = {"kind": "documented", "source": {"url": "https://example.org/x", "retrieved": "2026-11-08"}}
    assert _bad(good) == set()

    def unclaimed(r):
        r["models"]["anthropic/claude-opus-5-5"]["capability_basis"]["web_access"] = {"kind": "judgment", "reason": "x"}
    assert "known_workers.basis_unclaimed" in _bad(unclaimed)


def test_research_requires_a_basis_but_the_format_does_not():
    raw = copy.deepcopy(shipped())
    raw["models"]["anthropic/claude-opus-5-5"]["capability_basis"].pop("vision")
    assert _validate(raw) == set()
    assert _validate(raw, require_basis=True) == {"known_workers.basis_missing"}


def test_only_a_harness_names_creators():
    raw = copy.deepcopy(shipped())
    raw["providers"]["anthropic"]["creators"] = ["anthropic"]
    assert "known_workers.creators_not_harness" in codes(raw)
    kw = known_workers.load(VOCAB)
    assert kw.providers["claude_code"].creators == ["anthropic"] and kw.providers["codex"].creators == ["openai"]
