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
    assert out["refreshed"] == [] and any("network down" in f["reason"] for f in out["failed"])
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


# ---------------------------------------------------------------------------
# Assessed models: the owner's overlay (slice 5; Decisions 0110, 0111, 0112)
# ---------------------------------------------------------------------------

OVERLAY = """\
format: baton-known-workers/1
models:
  acme/big-2:
    creator: acme
    capabilities: [structured_output, technical_reasoning]
    capability_basis:
      structured_output: { kind: catalog, litellm: supports_response_schema }
      technical_reasoning: { kind: judgment, reason: assessed on the owner's machine }
    tier: standard
    context_tokens: 64000
    sources: [{ url: "https://example.com/acme", retrieved: 2026-11-10 }]
    researched: 2026-11-10
"""


def test_an_assessed_model_lifts_its_listing_profiles_from_basic(home):
    declare_or(home)
    listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    (home / "known-workers.local.yaml").write_text(OVERLAY, encoding="utf-8")
    resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    big = yaml.safe_load((home / "workers" / "or-acme-big.yaml").read_text(encoding="utf-8"))
    assert big["tier"] == "standard" and "technical_reasoning" in big["capabilities"] and big["context_tokens"] == 32000  # listing's context wins
    assert yaml.safe_load((home / "workers" / "or-acme-small-free.yaml").read_text(encoding="utf-8"))["tier"] == "basic"  # unassessed stays basic


@pytest.mark.parametrize("edit, fragment", [
    (lambda t: t.replace("acme/big-2:", "anthropic/claude-opus-5-5:").replace("creator: acme", "creator: anthropic"), "never edits one"),
    (lambda t: t + "routes:\n  - { model_id: acme/big-2, provider: openrouter, adapter: litellm_api, invocation: x, supported: true, verified: { date: 2026-11-10, tool: t, version: '1' } }\n", "only a live check"),
    (lambda t: t.replace("      technical_reasoning: { kind: judgment, reason: assessed on the owner's machine }\n", ""), "has no basis"),
    (lambda t: t + "providers: {}\n", "only models and routes"),
])
def test_an_overlay_is_refused_when_it_edits_shipped_data_claims_verified_or_lacks_a_basis(home, edit, fragment):
    from baton import known_workers as kw

    (home / "known-workers.local.yaml").write_text(edit(OVERLAY), encoding="utf-8")
    with pytest.raises(kw.KnownWorkersError) as e:
        resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    assert fragment in str(e.value)


# ---------------------------------------------------------------------------
# Slice 7: account listing, quota figures, provider summary and the switch (Decisions 0109, 0113, 0114)
# ---------------------------------------------------------------------------

KEY = {"data": {"limit": 10, "limit_remaining": 7.5, "usage": 2.5, "free_model_daily_requests": {"used": 50, "limit": 50, "remaining": 0}}}
ACCOUNT = {"data": [m for m in RAW["data"] if m["id"] in ("acme/big", "acme/small:free")]}


def account_fetch(calls):
    def fetch(url, headers=None):
        calls.append((url, bool(headers)))
        if url.endswith("/models/user"):
            return ACCOUNT
        if url.endswith("/key"):
            return KEY
        return RAW
    return fetch


@pytest.fixture
def keyed(home, monkeypatch):
    monkeypatch.setenv("BATON_SECRET_OR_KEY", "k")
    monkeypatch.setattr(resources.profiles_mod, "resolve_value", lambda ref, h: "k")
    declare_or(home)
    return home


def test_a_key_makes_refresh_read_the_account_list_and_the_quota_figures(keyed):
    calls: list = []
    out = resources.refresh_listings(keyed, fetch=account_fetch(calls), today=TODAY)
    assert out["refreshed"][0]["models"] == 2 and out["refreshed"][0]["source"].endswith("/models/user")
    assert "0 free-model requests left today of 50" in out["quota"][0]["line"] and "7.5 credit left" in out["quota"][0]["line"]
    assert all(h for _u, h in calls) and not out["failed"]


def test_a_failed_account_list_falls_back_to_the_public_list_and_says_so(keyed):
    def fetch(url, headers=None):
        if url.endswith("/models/user"):
            raise OSError("forbidden")
        if url.endswith("/key"):
            return KEY
        return RAW

    out = resources.refresh_listings(keyed, fetch=fetch, today=TODAY)
    assert out["refreshed"][0]["models"] == len(listings.normalize_openrouter(RAW, TODAY))
    assert "account list" in out["failed"][0]["reason"] and "public list is read instead" in out["failed"][0]["reason"]


def test_a_failed_key_read_keeps_the_last_figures(keyed):
    resources.refresh_listings(keyed, fetch=account_fetch([]), today=TODAY)

    def fetch(url, headers=None):
        if url.endswith("/key"):
            raise OSError("down")
        return ACCOUNT if url.endswith("/user") else RAW

    out = resources.refresh_listings(keyed, fetch=fetch, today=TODAY)
    assert "remaining quota" in out["failed"][0]["reason"]
    assert listings.load_key_info(keyed, "openrouter")["free_requests"]["remaining"] == 0


def test_status_summarises_listing_profiles_by_provider_with_quota_and_doctor_warns(keyed):
    resources.refresh_listings(keyed, fetch=account_fetch([]), today=TODAY)
    resources.setup(keyed, today=TODAY, discover_fn=lambda h, d: {})
    st = resources.status(keyed, discover_fn=lambda h, d: {})
    s = st["providers"]["or"]
    assert (s["profiles"], s["free"], s["enabled"], s["listing_fetched"]) == (2, 1, True, "2026-11-10")
    assert s["cheapest"]["basic"]["free"] is True and "0 free-model requests left" in s["quota_line"]
    assert resources.readiness(keyed)["quota"]["or"] == s["quota_line"]


def test_switching_a_provider_off_keeps_its_workers_but_routing_skips_them(keyed):
    resources.refresh_listings(keyed, fetch=account_fetch([]), today=TODAY)
    resources.setup(keyed, today=TODAY, discover_fn=lambda h, d: {})
    assert resources.switched_off(keyed) == set()
    resources.declare(keyed, "or", enabled=False)
    assert resources.switched_off(keyed) == {"or"}
    assert (keyed / "workers" / "or-acme-big.yaml").exists()  # recorded, not deleted
    assert "enabled: false" in (keyed / "resources.yaml").read_text(encoding="utf-8")
    el = order({"a": prof({"free": True}).with_switched_off(True), "b": prof({"input": 1.0, "output": 2.0})}, Preferences())
    assert [e["profile"] for e in el.eligible] == ["b"] and "switched off" in el.excluded[0]["reasons"][0]
    resources.declare(keyed, "or", enabled=True)
    assert resources.switched_off(keyed) == set() and "enabled" not in (keyed / "resources.yaml").read_text(encoding="utf-8")


def test_the_workers_commands_refresh_disable_and_enable(keyed, monkeypatch):
    from typer.testing import CliRunner

    from baton.cli import app

    monkeypatch.setattr(resources.listings_mod, "http_fetch", account_fetch([]))
    monkeypatch.setattr("baton.project.machine_home", lambda: keyed)
    r = CliRunner()
    out = r.invoke(app, ["workers", "refresh"]).output
    assert "openrouter: 2 models listed" in out and "free-model requests" in out
    assert "no longer uses its workers" in r.invoke(app, ["workers", "disable", "or"]).output
    assert resources.switched_off(keyed) == {"or"}
    assert "uses its workers again" in r.invoke(app, ["workers", "enable", "or"]).output
