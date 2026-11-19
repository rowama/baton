"""Tiers from published evaluations (§6.4; change 2026-11-model-assessment, slice 2; Decisions 0175, 0176, 0178)."""

from __future__ import annotations

import copy

import pytest

from baton import known_workers, vocab
from baton.adapters import ADAPTERS
from baton.data import load_yaml

pytestmark = pytest.mark.not_slow("pure validation")

VOCAB = vocab.load(vocab.DEFAULT)
SRC = {"url": "https://artificialanalysis.ai/leaderboards/models", "retrieved": "2026-11-18"}


def aa(score, version="5.0.1"):
    return {"name": "aa-intelligence-index", "version": version, "score": score, "configuration": "Max", "source": SRC}


def arena(score):
    return {"name": "lmarena-text", "version": "2026-11", "score": score, "source": {"url": "https://arena.ai/leaderboard/text", "retrieved": "2026-11-18"}}


def model(tier, basis, caps=(), cap_basis=None):
    return {"creator": "acme", "capabilities": list(caps), "capability_basis": cap_basis or {}, "tier": tier, "tier_basis": basis,
            "sources": [SRC], "researched": "2026-11-18"}


def issues(m) -> dict[str, str]:
    raw = copy.deepcopy(load_yaml(known_workers.default_path()))
    raw["models"]["acme/test-1"] = m
    _kw, found = known_workers.validate(raw, VOCAB, set(ADAPTERS))
    return {i.code.removeprefix("known_workers."): i.message for i in found if "acme/test-1" in i.where}


def test_the_shipped_mapping_loads_and_names_its_thresholds():
    ev = known_workers.load_evaluations()
    aa_entry = ev.evaluations["aa-intelligence-index"]
    assert aa_entry.independent and aa_entry.decides_tier and aa_entry.versions["5.0.1"] == {"strong": 50, "standard": 25}
    assert aa_entry.grants == {"technical_reasoning": "standard"}
    assert not ev.evaluations["lmarena-text"].decides_tier  # support only (0178, item 1)
    for name, e in ev.evaluations.items():
        for cuts in e.versions.values():
            assert set(cuts) <= set(VOCAB.tiers)
            if e.decides_tier:
                assert {"strong", "standard"} <= set(cuts), name
        assert all(t in VOCAB.tiers and c in VOCAB.capabilities for c, t in e.grants.items())


@pytest.mark.parametrize("score, tier", [(65, "strong"), (50, "strong"), (49.9, "standard"), (25, "standard"), (24, "basic"), (4, "basic")])
def test_the_index_decides_the_tier_at_50_and_25(score, tier):
    assert issues(model(tier, {"kind": "evaluation", "evaluations": [aa(score)]})) == {}
    wrong = "strong" if tier != "strong" else "basic"
    assert "tier_mismatch" in issues(model(wrong, {"kind": "evaluation", "evaluations": [aa(score)]}))


def test_several_results_give_the_lower_median():
    ev = known_workers.load_evaluations()
    rs = [known_workers.EvaluationResult.model_validate(aa(s)) for s in (60, 30, 55)]
    assert ev.tier_from(rs, VOCAB.tiers) == "strong"
    assert ev.tier_from(rs[:2], VOCAB.tiers) == "standard"  # strong and standard: the lower


def test_supporting_evidence_never_decides_and_unknown_versions_are_refused():
    assert "evaluation_supporting" in issues(model("strong", {"kind": "evaluation", "evaluations": [arena(1520)]}))
    assert "basis_incomplete" in issues(model("strong", {"kind": "evaluation", "evaluations": [], "supporting": [arena(1520)]}))
    assert issues(model("strong", {"kind": "evaluation", "evaluations": [aa(59)], "supporting": [arena(1507)]})) == {}
    msg = issues(model("strong", {"kind": "evaluation", "evaluations": [aa(59, version="4.3.2")]}))
    assert "never compare" in msg["unknown_evaluation"]
    assert "unknown_evaluation" in issues(model("strong", {"kind": "evaluation", "evaluations": [dict(aa(59), name="vibes")]}))
    assert "basis_incomplete" in issues(model("strong", {"kind": "judgment"}))
    assert issues(model("strong", {"kind": "judgment", "reason": "no published result yet; the creator's flagship"})) == {}


def test_a_score_grants_technical_reasoning_only_at_standard_or_better():
    ok = model("standard", {"kind": "evaluation", "evaluations": [aa(36)]}, ["technical_reasoning"],
               {"technical_reasoning": {"kind": "evaluation", "evaluation": aa(36)}})
    assert issues(ok) == {}
    low = model("basic", {"kind": "evaluation", "evaluations": [aa(14)]}, ["technical_reasoning"],
                {"technical_reasoning": {"kind": "evaluation", "evaluation": aa(14)}})
    assert "needs standard or better" in issues(low)["evaluation_grants"]
    writing = model("strong", {"kind": "evaluation", "evaluations": [aa(59)]}, ["long_form_writing"],
                    {"long_form_writing": {"kind": "evaluation", "evaluation": aa(59)}})
    assert "grants no 'long_form_writing'" in issues(writing)["evaluation_grants"]  # 0178, item 3
    assert "basis_incomplete" in issues(model("basic", None, ["technical_reasoning"], {"technical_reasoning": {"kind": "evaluation"}}))


def test_an_overlay_may_tier_a_model_from_evaluations(tmp_path):
    overlay = {"format": "baton-known-workers/1", "models": {"acme/test-1": model(
        "standard", {"kind": "evaluation", "evaluations": [aa(29)]}, ["technical_reasoning"],
        {"technical_reasoning": {"kind": "evaluation", "evaluation": aa(29)}})}}
    merged = known_workers.merge_overlay(VOCAB, overlay)
    assert merged.models["acme/test-1"].tier == "standard"
    overlay["models"]["acme/test-1"]["tier"] = "strong"
    with pytest.raises(known_workers.KnownWorkersError) as e:
        known_workers.merge_overlay(VOCAB, overlay)
    assert "give standard" in str(e.value)


def test_shipped_tiers_with_an_evaluation_basis_agree_with_the_mapping():
    kw = known_workers.load(VOCAB)
    based = {mid: m for mid, m in kw.models.items() if m.tier_basis is not None and m.tier_basis.kind == "evaluation"}
    assert len(based) >= 15  # the 2026-11-19 refresh
    for mid in ("anthropic/claude-opus-5-5", "anthropic/claude-sonnet-5-5", "anthropic/claude-haiku-5-5"):
        assert mid in based
    assert kw.models["anthropic/claude-fable-5.2-20261109"].tier == "strong"


def test_the_page_offers_rating_unrated_listed_models_and_calls_assess(tmp_path, monkeypatch):
    import datetime as dt

    from baton import assess, listings, resources, ui

    home = tmp_path / "home"
    home.mkdir()
    resources.declare(home, "or", provider="openrouter", credential="secret:k")
    raw = {"data": [{"id": "acme/big", "canonical_slug": "acme/big", "context_length": 32000, "pricing": {"prompt": "0.000001", "completion": "0.000001"},
                     "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}, "supported_parameters": ["response_format", "tools"]}]}
    listings.refresh(home, "openrouter", fetch=lambda url: raw, today=dt.date(2026, 11, 19))
    resources.setup(home, discover_fn=lambda h, d: {})
    monkeypatch.setattr(ui, "_discover", lambda h, d: {})
    state = ui._state(home, {}, {})
    row = next(m for m in state["models"] if m["profile"] == "or-acme-big")
    assert row["listed"] and not row["judged"]
    opus = next(m for m in state["models"] if m["model_id"] == "anthropic/claude-opus-5-5")
    assert opus["judged"]
    calls = []
    monkeypatch.setattr(assess, "assess", lambda h, ids, profile: calls.append((ids, profile)) or {"assessed": [], "not_assessed": []})
    assert ui._assess(home, {"models": ["acme/big"], "profile": "researcher"}, {}) == {"assessed": [], "not_assessed": []}
    assert calls == [(["acme/big"], "researcher")]
    with pytest.raises(ui.UiError):
        ui._assess(home, {"models": [], "profile": "x"}, {})

    def refuse(h, ids, profile):
        raise assess.AssessError("acme/big already has a judgment")

    monkeypatch.setattr(assess, "assess", refuse)
    with pytest.raises(ui.UiError) as e:
        ui._assess(home, {"models": ["acme/big"], "profile": "researcher"}, {})
    assert e.value.code == "assess.refused"
