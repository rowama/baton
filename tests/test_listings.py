"""Provider model listings become profiles (§6.4; change 2026-11-model-listings; Decisions 0109, 0110, 0112, 0113, 0115)."""

from __future__ import annotations

import datetime as dt
import json

import pytest
import yaml

from baton import listings, resources

TODAY = dt.date(2026, 11, 10)


def model(id_, *, prompt="0", completion="0", params=("response_format", "tools"), out=("text",), ins=("text",), ctx=32000,
          slug=None, **extra):
    return {"id": id_, "canonical_slug": slug or id_, "context_length": ctx, "pricing": {"prompt": prompt, "completion": completion},
            "architecture": {"input_modalities": list(ins), "output_modalities": list(out)}, "supported_parameters": list(params), **extra}


RAW = {"data": [
    model("acme/small:free", slug="acme/small"),
    model("acme/big", prompt="0.000003", completion="0.000015", ins=("text", "image"), slug="acme/Big-2"),
    model("acme/no-schema", params=("temperature",)),
    model("acme/painter", out=("image",)),
    model("acme/gone", expiration_date="2026-01-01"),
    model("anthropic/claude-opus-5.5", prompt="0.000015", completion="0.000075"),
]}


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def declare_or(home):
    resources.declare(home, "or", provider="openrouter", credential="secret:or_key")


def test_listing_candidates_follow_the_adapter_contract_and_cite_fields(home):
    body = listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    assert body["fetched"] == "2026-11-10" and body["source"].startswith("https://openrouter.ai/")
    found = {c.id: c for c in listings.candidates(body, {})}
    assert set(found) == {"acme/small:free", "acme/big", "anthropic/claude-opus-5.5"}  # no schema, image-only and expired are left out
    assert found["acme/big"].capabilities == {"structured_output": "response_format", "tool_use": "tools", "vision": "architecture.input_modalities"}
    assert found["acme/big"].price == {"input": 3.0, "output": 15.0}
    assert found["acme/small:free"].price["free"] is True
    assert found["acme/big"].model_id == "acme/big-2"  # the lower-cased canonical slug (0112)


def test_setup_generates_listing_profiles_with_price_context_and_basic_tier(home):
    declare_or(home)
    listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    out = resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    assert "or-acme-small-free" in out["written"] and "or-acme-big" in out["written"]
    body = yaml.safe_load((home / "workers" / "or-acme-big.yaml").read_text(encoding="utf-8"))
    assert body["adapter"] == "litellm_api" and body["model"] == "openrouter/acme/big" and body["tier"] == "basic"
    assert body["context_tokens"] == 32000 and body["model_id"] == "acme/big-2" and body["creator"] == "acme"
    assert body["price"] == {"input": 3.0, "output": 15.0, "source": "https://openrouter.ai/api/v1/models", "date": "2026-11-10"}
    assert "technical_reasoning" not in body["capabilities"] and "generated" in body and "verified" not in body["generated"]
    free = yaml.safe_load((home / "workers" / "or-acme-small-free.yaml").read_text(encoding="utf-8"))
    assert free["price"]["free"] is True
    # a model research already routes keeps its researched profile, not a listing one
    opus = [f for f in (home / "workers").glob("*.yaml")
            if yaml.safe_load(f.read_text(encoding="utf-8")).get("model") == "openrouter/anthropic/claude-opus-5.5"]
    assert len(opus) == 1 and not opus[0].name.startswith("or-anthropic-claude-opus-5.5")  # one profile: the researched route's
    again = resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    assert again["written"] == [] and again["refreshed"] == []


def test_a_failed_fetch_keeps_the_last_good_cache_and_reports_plainly(home):
    declare_or(home)
    listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    before = listings.listing_path(home, "openrouter").read_text(encoding="utf-8")

    def broken(url):
        raise OSError("network down")

    out = resources.refresh_listings(home, fetch=broken, today=TODAY)
    assert out["refreshed"] == [] and "network down" in out["failed"][0]["reason"]
    assert listings.listing_path(home, "openrouter").read_text(encoding="utf-8") == before
    malformed = resources.refresh_listings(home, fetch=lambda url: {"data": "odd"}, today=TODAY)
    assert malformed["failed"] and listings.listing_path(home, "openrouter").read_text(encoding="utf-8") == before


def test_a_repriced_listing_refreshes_an_untouched_profile_only_through_setup(home):
    declare_or(home)
    listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    cheaper = json.loads(json.dumps(RAW))
    cheaper["data"][1]["pricing"]["prompt"] = "0.000001"
    listings.refresh(home, "openrouter", fetch=lambda url: cheaper, today=TODAY)
    path = home / "workers" / "or-acme-big.yaml"
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["price"]["input"] == 3.0  # fetching changes no profile (acceptance 7)
    out = resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    assert "or-acme-big" in out["refreshed"] and yaml.safe_load(path.read_text(encoding="utf-8"))["price"]["input"] == 1.0


# ---------------------------------------------------------------------------
# Price preference and quota (slice 2; Decisions 0114, 0115)
# ---------------------------------------------------------------------------

from baton import quota, routing  # noqa: E402
from baton import vocab as vocab_mod  # noqa: E402
from baton.models import Preferences, Step, WorkerProfile  # noqa: E402


def prof(price=None, caps=("structured_output",)):
    body = {"adapter": "litellm_api", "creator": "acme", "capabilities": list(caps), "tier": "basic"}
    if price is not None:
        body["price"] = price
    return WorkerProfile.model_validate(body)


def order(profiles, prefs):
    step = Step.model_validate({"id": "s", "prompt": "prompts/s.md", "requires": {"capabilities": ["structured_output"]}, "output_schema": "schemas/o.json"})
    el = routing.eligible_workers(step, "s", profiles, vocab_mod.load(vocab_mod.DEFAULT), preferences=prefs)
    return el


def test_cheapest_first_orders_free_then_cheap_then_dear_then_unpriced_and_never_adds():
    profiles = {"dear": prof({"input": 15.0, "output": 75.0}), "free": prof({"input": 0.0, "output": 0.0, "free": True}),
                "cheap": prof({"input": 0.1, "output": 0.4}), "unpriced": prof(), "weak": prof({"free": True}, caps=())}
    el = order(profiles, Preferences(cheapest_first=True))
    assert [e["profile"] for e in el.eligible] == ["free", "cheap", "dear", "unpriced"]  # the ineligible free one stays out
    assert [x["profile"] for x in el.excluded] == ["weak"]
    assert [e["profile"] for e in order(profiles, Preferences()).eligible] == ["cheap", "dear", "free", "unpriced"]  # off: by name, as before


def test_worker_selected_records_the_price():
    rec = routing.identity_record("free", prof({"input": 0.0, "output": 0.0, "free": True, "source": "x", "date": "2026-11-10"}))
    assert rec["price"] == {"input": 0.0, "output": 0.0, "free": True}
    assert "price" not in routing.identity_record("u", prof())


def test_an_exhausted_route_is_left_out_until_the_reset(home):
    now = dt.datetime(2026, 11, 10, 15, 0, tzinfo=dt.timezone.utc)
    until = quota.record(home, "free", now)
    assert until == dt.datetime(2026, 11, 11, 0, 0, tzinfo=dt.timezone.utc)
    assert set(quota.load(home, now)) == {"free"}
    assert quota.load(home, until) == {}  # reset: the route is back
    el = order({"free": prof({"free": True}).with_quota(until), "paid": prof({"input": 1.0, "output": 2.0})}, Preferences(cheapest_first=True))
    assert [e["profile"] for e in el.eligible] == ["paid"]
    assert "quota exhausted until 2026-11-11 00:00 UTC" in el.excluded[0]["reasons"][0]


def test_a_rate_limit_error_is_classified_quota_exhausted():
    from baton import worker_runner as wr

    class RateLimitError(Exception):
        pass

    f = wr.classify_exception(RateLimitError("429"))
    assert (f.failure_class, f.code) == ("platform", "quota_exhausted")


# ---------------------------------------------------------------------------
# The provider directory (slice 4; Decision 0117)
# ---------------------------------------------------------------------------


def test_a_directory_provider_needs_only_a_credential_and_its_models_come_from_its_listing(home):
    from baton import known_workers as kw
    from baton import vocab as vocab_mod

    data = kw.load(vocab_mod.load(vocab_mod.DEFAULT))
    chutes = data.providers["chutes"]
    assert chutes.kind == "openai_compatible" and chutes.base_url.startswith("https://") and chutes.signup_url
    assert not [r for r in data.routes if r.provider == "chutes"]  # no researched model: the listing is all there is
    seen = []

    def fetch(url, headers=None):
        seen.append((url, headers))
        return {"object": "list", "data": [{"id": "zed/model-a"}, {"id": "plain"}]}

    resources.declare(home, "ch", provider="chutes", credential="secret:chutes_key")  # no --base-url: the directory has it
    (home / "secrets").mkdir()
    (home / "secrets" / "chutes_key").write_text("K", encoding="utf-8")
    out = resources.refresh_listings(home, fetch=fetch, today=TODAY)
    assert out["refreshed"][0]["models"] == 2 and seen == [(chutes.base_url + "/models", {"Authorization": "Bearer K"})]
    done = resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    assert sorted(done["written"]) == ["ch-plain", "ch-zed-model-a"]
    a = yaml.safe_load((home / "workers" / "ch-zed-model-a.yaml").read_text(encoding="utf-8"))
    assert a["model"] == "openai/zed/model-a" and a["options"]["base_url"] == chutes.base_url and a["creator"] == "zed"
    assert yaml.safe_load((home / "workers" / "ch-plain.yaml").read_text(encoding="utf-8"))["creator"] == "unknown"


def test_a_local_runtime_is_a_directory_entry_without_a_key(home):
    resources.declare(home, "mine", provider="ollama")
    out = resources.refresh_listings(home, fetch=lambda url, headers=None: {"data": [{"id": "llama"}]}, today=TODAY)
    assert out["refreshed"][0]["provider"] == "mine"
    resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    body = yaml.safe_load((home / "workers" / "mine-llama.yaml").read_text(encoding="utf-8"))
    assert body["auth"] == {"mode": "none"} and body["options"]["base_url"] == "http://localhost:11434/v1"


def test_the_validator_refuses_a_base_url_on_a_provider_reached_through_litellm():
    from baton import known_workers as kw
    from baton import vocab as vocab_mod

    raw = yaml.safe_load(kw.default_path().read_text(encoding="utf-8"))
    raw["providers"]["xai"]["base_url"] = "https://example.com/v1"
    _, issues = kw.validate(raw, vocab_mod.load(vocab_mod.DEFAULT), {"litellm_api", "subprocess_harness", "manual", "command"})
    assert any(i.code.endswith("base_url_kind") for i in issues)
