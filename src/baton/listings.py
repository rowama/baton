"""Provider model listings (§6.4; Decisions 0109, 0110, 0112, 0113).

A listing is the list of models a provider says it offers, fetched
deterministically (no agent) and cached machine-locally in
``~/.baton/listings/<provider>.json`` (``baton-listing/1``) with its fetch date
and source. A failed fetch never replaces the last good cache. Each listed
model is a candidate route: context, price and catalog-basis capabilities come
straight from listing fields; nothing here needs judgment, so a listing never
adds a judgment capability and never marks anything ``verified``.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import MODEL_ID

FORMAT = "baton-listing/1"

#: Where each provider's public listing is read (Decision 0109: OpenRouter first).
SOURCES = {"openrouter": "https://openrouter.ai/api/v1/models"}

#: The account's own listing, read with its key: only what its provider preferences, privacy settings and guardrails allow (Decision 0109).
USER_SOURCES = {"openrouter": "https://openrouter.ai/api/v1/models/user"}

#: A provider's key endpoint: remaining credit and free-model requests (Decision 0114).
KEY_SOURCES = {"openrouter": "https://openrouter.ai/api/v1/key"}

#: Listing parameters that show a capability (basis ``catalog``, 0088, named by field).
PARAMETER_CAPABILITIES = {
    "response_format": "structured_output",
    "structured_outputs": "structured_output",
    "tools": "tool_use",
}

#: What an OpenAI-style listing does not show, a ``litellm_api`` reply still meets: the schema goes in the prompt (§6.3), and the claim is checked by use (0087).
PROMPT_SCHEMA = "adapter prompt-schema fallback (§6.3)"

Fetcher = Callable[..., Any]


class ListingError(Exception):
    """A listing could not be fetched or read; the last good cache is untouched."""


def listings_dir(home: Path) -> Path:
    return Path(home) / "listings"


def listing_path(home: Path, provider: str) -> Path:
    return listings_dir(home) / f"{provider}.json"


def http_fetch(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "baton-listings", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https source
        return json.loads(r.read().decode("utf-8"))


def _per_million(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):  # expected: a price that is not a number is no price
        return None
    return round(v * 1_000_000, 6) if v >= 0 else None


def normalize_openrouter(raw: Any, today: dt.date) -> list[dict[str, Any]]:
    """The listing's models in Baton's candidate form, or ``ListingError`` for a malformed response."""
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, list) or not data:
        raise ListingError("the listing response has no model list")
    out: list[dict[str, Any]] = []
    for m in data:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str):
            continue
        exp = m.get("expiration_date")
        if isinstance(exp, str) and exp[:10] < today.isoformat():
            continue
        arch = m.get("architecture") or {}
        outs, ins = arch.get("output_modalities") or [], arch.get("input_modalities") or []
        params = [p for p in (m.get("supported_parameters") or []) if isinstance(p, str)]
        caps: dict[str, str] = {}
        for p in params:
            cap = PARAMETER_CAPABILITIES.get(p)
            if cap and cap not in caps:
                caps[cap] = p
        if "image" in ins:
            caps["vision"] = "architecture.input_modalities"
        pricing = m.get("pricing") or {}
        pin, pout = _per_million(pricing.get("prompt")), _per_million(pricing.get("completion"))
        out.append({
            "id": m["id"],
            "canonical_slug": m.get("canonical_slug") or m["id"],
            "alias_target": m.get("alias_target"),
            "text": outs == ["text"] or ("text" in outs and not (set(outs) - {"text"})),
            "context_tokens": m.get("context_length") if isinstance(m.get("context_length"), int) and m["context_length"] > 0 else None,
            "capabilities": caps,
            "price": ({"input": pin, "output": pout} if pin is not None and pout is not None else None),
            "free": pin == 0 and pout == 0,
        })
    return out


def normalize_openai(raw: Any, today: dt.date) -> list[dict[str, Any]]:
    """An OpenAI-style ``GET <base_url>/models`` (Decision 0118): ids only. Price, context and tool support stay unknown."""
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, list) or not data:
        raise ListingError("the listing response has no model list")
    return [{"id": m["id"], "canonical_slug": m["id"], "alias_target": None, "text": True, "context_tokens": None,
             "capabilities": {"structured_output": PROMPT_SCHEMA}, "price": None, "free": False}
            for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]


def refresh(home: Path, provider: str, *, fetch: Fetcher = http_fetch, today: dt.date | None = None, key: str | None = None,
            url: str | None = None, headers: dict[str, str] | None = None, style: str = "openrouter") -> dict[str, Any]:
    """Fetch and cache one listing (``key``: its cache name, default the provider's). On any failure the last good cache stays; ``ListingError`` is raised."""
    today = today or dt.date.today()
    if url is None:
        if provider not in SOURCES:
            raise ListingError(f"no listing source is known for {provider}")
        url = SOURCES[provider]
    try:
        raw = fetch(url, headers=headers) if headers else fetch(url)
        models = (normalize_openai if style == "openai" else normalize_openrouter)(raw, today)
    except ListingError:
        raise
    except Exception as e:  # expected: network, TLS and decoding errors all mean "no new listing"
        raise ListingError(f"{type(e).__name__}: {e}") from e
    body = {"format": FORMAT, "provider": provider, "source": url, "fetched": today.isoformat(), "models": models}
    path = listing_path(home, key or provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return body


def load(home: Path, provider: str) -> dict[str, Any] | None:
    """The cached listing, or None when there is none or it is unreadable."""
    try:
        body = json.loads(listing_path(home, provider).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: no or unreadable cache means no listing
        return None
    return body if isinstance(body, dict) and body.get("format") == FORMAT else None


@dataclass
class Candidate:
    """A listed model that can become a profile (Decisions 0110, 0112, 0113)."""

    id: str
    creator: str
    model_id: str | None
    alias: bool
    context_tokens: int | None
    capabilities: dict[str, str]
    price: dict[str, Any] | None


def identity(entry: dict[str, Any], researched: dict[str, str], provider: str = "openrouter") -> tuple[str | None, bool]:
    """``(model_id, alias)`` for a listing entry (0112): a researched route's id, else the lower-cased canonical slug, else unknown."""
    if provider == "openai_compatible":  # the ids are the endpoint's own: nothing says whose model it is
        return None, False
    inv = f"{provider}/{entry['id']}"
    if inv in researched:
        return researched[inv], False
    alias = bool(entry.get("alias_target")) or entry["id"].startswith("openrouter/")
    slug = str(entry.get("canonical_slug") or entry["id"]).lower().split(":", 1)[0]
    if not alias and re.match(MODEL_ID, slug):
        return slug, False
    return None, alias


def candidates(listing: dict[str, Any], researched: dict[str, str], provider: str = "openrouter") -> list[Candidate]:
    """Text models whose listing shows a structured-output parameter (the ``litellm_api`` reply contract, §6.3; 0113)."""
    out: list[Candidate] = []
    for e in listing.get("models", []):
        if not e.get("text") or "structured_output" not in e.get("capabilities", {}):
            continue
        model_id, alias = identity(e, researched, provider)
        creator = (model_id or e["id"]).split("/", 1)[0].lower() if (model_id or "/" in e["id"]) else "unknown"
        if not re.match(r"^[a-z0-9][a-z0-9._-]*$", creator):
            creator = "unknown"
        price = e.get("price")
        if price is not None and e.get("free"):
            price = {"input": 0.0, "output": 0.0, "free": True}
        out.append(Candidate(e["id"], creator, model_id, alias, e.get("context_tokens"), dict(e["capabilities"]), price))
    return out


def quota_path(home: Path, provider: str) -> Path:
    return listings_dir(home) / f"{provider}.quota.json"


def _number(v: Any) -> float | int | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def normalize_key_info(raw: Any) -> dict[str, Any]:
    """OpenRouter's ``GET /api/v1/key`` in the form ``workers status`` shows, or ``ListingError``."""
    d = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(d, dict):
        raise ListingError("the key response has no data")
    out: dict[str, Any] = {}
    credit = {k: _number(d.get(k)) for k in ("limit", "limit_remaining", "usage")}
    if any(v is not None for v in credit.values()):
        out["credit"] = {k: v for k, v in credit.items() if v is not None}
    free = d.get("free_model_daily_requests")
    if isinstance(free, dict):
        got = {k: _number(free.get(k)) for k in ("used", "limit", "remaining")}
        if any(v is not None for v in got.values()):
            out["free_requests"] = {k: v for k, v in got.items() if v is not None}
    if not out:
        raise ListingError("the key response shows no credit or free-request figures")
    return out


def refresh_key_info(home: Path, provider: str, *, headers: dict[str, str], fetch: Fetcher = http_fetch,
                     today: dt.date | None = None) -> dict[str, Any]:
    """Cache what the provider's key endpoint says about remaining quota; a failure keeps the last good record."""
    url = KEY_SOURCES.get(provider)
    if url is None:
        raise ListingError(f"no key endpoint is known for {provider}")
    try:
        info = normalize_key_info(fetch(url, headers=headers))
    except ListingError:
        raise
    except Exception as e:  # expected: network, TLS and decoding errors all mean "no new figures"
        raise ListingError(f"{type(e).__name__}: {e}") from e
    body = {"format": "baton-listing-quota/1", "provider": provider, "source": url,
            "fetched": (today or dt.date.today()).isoformat(), **info}
    path = quota_path(home, provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return body


def load_key_info(home: Path, provider: str) -> dict[str, Any] | None:
    try:
        body = json.loads(quota_path(home, provider).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: no or unreadable record means no figures
        return None
    return body if isinstance(body, dict) and body.get("format") == "baton-listing-quota/1" else None


def quota_line(info: dict[str, Any]) -> str:
    """One plain line from a cached key record, dated because the figures are as of the last refresh."""
    parts: list[str] = []
    f = info.get("free_requests") or {}
    if "remaining" in f:
        parts.append(f"{f['remaining']} free-model requests left today" + (f" of {f['limit']}" if "limit" in f else ""))
    c = info.get("credit") or {}
    if "limit_remaining" in c:
        parts.append(f"{c['limit_remaining']} credit left")
    elif "usage" in c:
        parts.append(f"{c['usage']} credit used")
    return f"{', '.join(parts)} (as of {info['fetched']})"
