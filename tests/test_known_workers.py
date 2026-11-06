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
    # One identity, two routes with their own invocation identifiers.
    assert {r.provider for r in opus} == {"anthropic", "openrouter"} and len({r.invocation for r in opus}) == 2
    # Harness defaults are mutable aliases: no identity, a creator.
    for r in kw.routes:
        if kw.providers[r.provider].kind == "harness":
            assert r.alias and r.model_id is None and r.creator
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
