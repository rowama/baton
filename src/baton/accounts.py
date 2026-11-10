"""Connecting, re-keying and disconnecting an API account (§6.1, §6.4, §13.9; Decision 0123).

The one core path under both ``baton workers connect|disconnect`` and the setup
page: check the key with one cheap read (never a model call), keep it in the
keyring or the owner-only file, declare the resource, fetch its model list and
run setup. A key is held in memory only for the call; it is never written to a
resource file, a result, a log, an event or a diagnostic.
"""

from __future__ import annotations

import re
import urllib.error
from pathlib import Path
from typing import Any

from . import diag
from . import listings as listings_mod
from . import profiles as profiles_mod
from . import redact, resources
from .resources import ResourcesError

#: One free read that fails on a bad key, per provider: (url, header names for the key). Providers not listed
#: have no check ahead of first use. [VERIFY against each provider's current API reference before adding one.]
KEY_CHECKS: dict[str, tuple[str, dict[str, str]]] = {
    "openrouter": (listings_mod.KEY_SOURCES["openrouter"], {"Authorization": "Bearer {key}"}),
    "openai": ("https://api.openai.com/v1/models", {"Authorization": "Bearer {key}"}),
    "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": "{key}", "anthropic-version": "2023-06-01"}),
}


class AccountError(Exception):
    """A refusal in plain words; ``code`` names it for the CLI and the page."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def secret_name_for(resource: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", resource.lower()).strip("_") or "account"


def check_key(provider: str, key: str, *, base_url: str | None = None, fetch: Any = None) -> dict[str, Any]:
    """Ask the provider one cheap question with this key: ``{checked, ok, reason}``.

    ``checked`` is False when this provider has no free check (the key is then
    tried at first use). A refusal by the provider is ``ok: False`` with its
    reason; a network failure is also ``ok: False``, because an unchecked key is not a connected one.
    """
    fetch = fetch or listings_mod.http_fetch
    if provider in KEY_CHECKS:
        url, header_tpl = KEY_CHECKS[provider]
    elif base_url:
        url, header_tpl = base_url.rstrip("/") + "/models", {"Authorization": "Bearer {key}"}
    else:
        return {"checked": False, "ok": True, "reason": f"{provider} has no free key check; the key is tried the first time it is used"}
    headers = {k: v.format(key=key) for k, v in header_tpl.items()}
    try:
        fetch(url, headers=headers)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"checked": True, "ok": False, "reason": f"{provider} did not accept this key (it answered {e.code}). Check it was copied whole."}
        return {"checked": True, "ok": False, "reason": f"{provider} answered {e.code} when the key was checked; try again in a moment."}
    except Exception as e:  # noqa: BLE001 - any network or decoding failure means "could not check"; the reason is shown without the key
        diag.note("accounts.check_failed", "accounts:check_key", provider=provider, error=type(e).__name__)
        return {"checked": True, "ok": False, "reason": f"could not reach {provider} to check the key ({type(e).__name__}); nothing was changed."}
    return {"checked": True, "ok": True, "reason": "accepted"}


def _clean(key: str | None) -> str | None:
    key = (key or "").strip()
    return key or None


def connect(home: Path, provider: str, key: str | None, *, name: str | None = None, base_url: str | None = None,
            fetch: Any = None, today: Any = None, discover_fn: Any = None) -> dict[str, Any]:
    """Connect an API account, or replace the key of one that exists (Decision 0123).

    New: check, store, declare, fetch the model list, run setup. Existing (``name`` is declared): the new key is
    checked first and only then replaces the stored one, so a bad paste never breaks a working account.
    """
    home = Path(home)
    data, _sha, res = resources._inputs(home)
    declared = res.workers()
    prov = data.providers.get(provider)
    if prov is None or prov.kind == "harness":
        raise AccountError("accounts.unknown_provider", f"{provider!r} is not an account provider Baton knows")
    name = name or f"{provider}-main"
    existing = declared.get(name)
    if existing is not None and existing.provider != provider:
        raise AccountError("accounts.name_taken", f"{name!r} is already a {existing.provider} account")
    key = _clean(key)
    base = base_url or (existing.base_url if existing else None) or prov.base_url
    if key is None and not (prov.kind == "openai_compatible" and base):
        raise AccountError("accounts.no_key", f"{provider} needs an API key" + (f" (get one at {prov.signup_url})" if prov.signup_url else ""))
    secret = secret_name_for(name)
    out: dict[str, Any] = {"account": name, "provider": provider, "replaced": existing is not None}
    if key is not None:
        redact.register(key)
        if existing is not None and "environment" in profiles_mod.secret_places(secret, home):
            raise AccountError("accounts.key_from_environment", f"{name}'s key comes from the environment variable "
                               f"{profiles_mod.secret_env_name(secret)}; change it there, or unset it to let Baton keep the key")
        checked = check_key(provider, key, base_url=base if prov.kind == "openai_compatible" else None, fetch=fetch)
        out["check"] = checked
        if not checked["ok"]:
            raise AccountError("accounts.key_refused", checked["reason"] + (" Your current key is unchanged." if existing else ""))
        out["stored_in"] = profiles_mod.store_secret(secret, key, home)
        credential = f"secret:{secret}"
    else:
        credential = None
        out["check"] = {"checked": False, "ok": True, "reason": "no key needed"}
        out["stored_in"] = None
    resources.declare(home, name, provider=provider, credential=credential, base_url=base_url if base_url else None)
    out["listing"] = _refresh(home, fetch, today)
    done = resources.setup(home, today=today, **({"discover_fn": discover_fn} if discover_fn is not None else {}))
    out["setup"] = {"written": done["written"], "refreshed": done["refreshed"], "failed": done["failed"]}
    return out


def _refresh(home: Path, fetch: Any, today: Any) -> dict[str, Any]:
    try:
        r = resources.refresh_listings(home, fetch=fetch, today=today)
    except ResourcesError as e:  # expected: the account is connected; the list can be fetched again with `workers refresh`
        return {"refreshed": [], "failed": [{"reason": str(e)}]}
    return {"refreshed": r["refreshed"], "failed": r["failed"]}


def disconnect(home: Path, name: str, *, forget_key: bool = False) -> dict[str, Any]:
    """Remove an account's declaration; its stored key too only when ``forget_key`` (the owner confirmed).

    Generated profiles that depended on it stay and are flagged ``resource_gone`` by status (0079); routing stops using them.
    """
    home = Path(home)
    _data, _sha, res = resources._inputs(home)
    r = res.workers().get(name)
    if r is None:
        raise AccountError("accounts.unknown", f"no account named {name!r}")
    ref = r.credential
    resources.declare(home, name, remove=True)
    out: dict[str, Any] = {"disconnected": name, "key_removed_from": [], "key_kept": None}
    if ref:
        secret = ref[len("secret:"):]
        still_used = [n for n, o in res.workers().items() if n != name and o.credential == ref]
        if forget_key and not still_used:
            out["key_removed_from"] = profiles_mod.delete_secret(secret, home)
        else:
            out["key_kept"] = secret
            if forget_key and still_used:
                out["note"] = f"the key is also used by {', '.join(still_used)}, so it was kept"
    return out


def account_info(home: Path, name: str) -> dict[str, Any]:
    """Where an account's key is kept and nothing else: never the key."""
    _data, _sha, res = resources._inputs(Path(home))
    r = res.workers().get(name)
    if r is None or not r.credential:
        return {"account": name, "kept_in": []}
    return {"account": name, "kept_in": profiles_mod.secret_places(r.credential[len("secret:"):], Path(home))}
