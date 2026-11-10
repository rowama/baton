"""The worker resource manager (§6.4; Decisions 0074, 0077–0082).

Combines three inputs into generated worker profiles, one file each in
``$BATON_HOME/workers/`` (0079):

1. the shipped known-workers data (``known_workers.py``), read-only;
2. local discovery: which harness CLIs are installed here and logged in;
3. the owner's declarations in ``$BATON_HOME/resources.yaml``
   (``baton-resources/1``, 0078): resources discovery cannot find (an
   OpenRouter account, a direct API key), each with an explicit ``kind``,
   credentials only as ``secret:<name>`` references, and per-kind setup state.

It never writes ``workers.yaml`` and never changes a profile it did not
generate (no ``generated`` marker, or content that no longer matches its
``content_sha256``). Live checks run only when asked (``verify``, 0081).
Nothing here runs on install or upgrade: only an explicit ``setup`` adds
profiles.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import diag
from . import __version__
from . import known_workers as kw_mod
from . import listings as listings_mod
from . import profiles as profiles_mod
from . import vocab as vocab_mod
from .data import YamlError, load_yaml
from .models import Issue, WorkerProfile
from .store import canonical_json

FORMAT = "baton-resources/1"
RESOURCES_FILE = "resources.yaml"
GENERATED_DIR = "workers"
#: Resource kinds this runtime knows (0078). A new kind is added here, with its own model.
KINDS = ("worker",)
SECRET_REF = r"^secret:[A-Za-z0-9_.-]+$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkerResource(_Strict):
    """A worker resource: access to models that discovery cannot find, or facts about one it can."""

    kind: Literal["worker"]
    provider: str
    credential: str | None = Field(default=None, pattern=SECRET_REF)
    base_url: str | None = None
    #: Allowlist of model_ids this account may use; empty = whatever the routes offer.
    models: list[str] = Field(default_factory=list)
    #: Machine-dependent capabilities the owner declares for this resource (0082).
    capabilities: list[str] = Field(default_factory=list)
    note: str | None = None


class SetupState(_Strict):
    completed: dt.date | None = None
    runtime: str | None = None
    nothing_more: bool = False


class Resources(_Strict):
    format: str = FORMAT
    resources: dict[str, WorkerResource] = Field(default_factory=dict)
    setup: dict[str, SetupState] = Field(default_factory=dict)

    def workers(self) -> dict[str, WorkerResource]:
        return {n: r for n, r in self.resources.items() if r.kind == "worker"}


class ResourcesError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


def resources_path(home: Path) -> Path:
    return Path(home) / RESOURCES_FILE


def generated_dir(home: Path) -> Path:
    return Path(home) / GENERATED_DIR


def validate_resources(raw: object, machine_dependent: list[str], source: str = RESOURCES_FILE) -> tuple[Resources | None, list[Issue]]:
    def issue(code: str, where: str, message: str) -> Issue:
        return Issue(code=f"resources.{code}", where=f"{source}:{where}" if where else source, message=message)

    if raw is None:
        return Resources(), []
    if not isinstance(raw, dict):
        return None, [issue("not_a_mapping", "", "resources.yaml must be a mapping")]
    issues: list[Issue] = []
    if raw.get("format", FORMAT) != FORMAT:
        issues.append(issue("format", "format", f"expected {FORMAT}, got {raw.get('format')!r}"))
    for name, body in (raw.get("resources") or {}).items():
        where = f"resources.{name}"
        if not isinstance(body, dict) or "kind" not in body:
            issues.append(issue("no_kind", where, f"every resource names its kind ({', '.join(KINDS)})"))
            continue
        if body["kind"] not in KINDS:
            issues.append(issue("unknown_kind", where, f"kind {body['kind']!r} is not one this runtime knows ({', '.join(KINDS)})"))
            continue
        cred = body.get("credential")
        if isinstance(cred, str) and not re.fullmatch(SECRET_REF, cred):
            issues.append(issue("literal_credential", f"{where}.credential",
                                "a credential is only ever a secret:<name> reference (§6.1), never the value itself"))
        for cap in body.get("capabilities") or []:
            if cap not in machine_dependent:
                issues.append(issue("capability", f"{where}.capabilities",
                                    f"only machine-dependent capabilities are declared here ({', '.join(machine_dependent) or 'none'}); {cap!r} comes from the known-workers data"))
    for kind in raw.get("setup") or {}:
        if kind not in KINDS:
            issues.append(issue("unknown_kind", f"setup.{kind}", f"kind {kind!r} is not one this runtime knows ({', '.join(KINDS)})"))
    if issues:
        return None, issues
    try:
        return Resources.model_validate(raw), []
    except ValidationError as e:
        return None, [issue("invalid", ".".join(map(str, err["loc"])), err["msg"]) for err in e.errors()]


def load_resources(home: Path, machine_dependent: list[str]) -> Resources:
    path = resources_path(home)
    if not path.is_file():
        return Resources()
    try:
        raw = load_yaml(path)
    except YamlError as e:
        raise ResourcesError([Issue(code="resources.yaml", where=str(path), message=str(e))]) from e
    res, issues = validate_resources(raw, machine_dependent, source=str(path))
    if issues or res is None:
        raise ResourcesError(issues)
    return res


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_resources(home: Path, res: Resources) -> Path:
    path = resources_path(home)
    body = res.model_dump(mode="json", exclude_none=True, exclude_defaults=False)
    for r in body.get("resources", {}).values():
        for k in [k for k, v in r.items() if v in ([], None)]:
            r.pop(k)
    header = "# Machine resources (baton-resources/1, §6.4). Edit with `baton workers declare` or by hand.\n"
    _atomic_write(path, header + yaml.safe_dump(body, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# Generated profiles: marker and ownership (0079)
# ---------------------------------------------------------------------------


#: What a refresh of an untouched generated profile may change (0079); everything else is its binding.
REFRESHABLE = ("capabilities", "tier", "context_tokens", "price")
#: Never changed by a refresh: a different value here is a different worker, left for the owner.
BINDING = ("adapter", "creator", "model_id", "provider", "model", "resource", "auth", "options")
HEADER = "# Generated by baton workers setup (§6.4). Edit freely: an edited file is yours and is never changed again.\n"


def content_sha256(body: dict[str, Any]) -> str:
    """Hash of a generated profile's fields, without its ``generated`` marker."""
    plain = {k: v for k, v in body.items() if k != "generated"}
    return hashlib.sha256(canonical_json(plain).encode("utf-8")).hexdigest()


def ownership(body: Any) -> str:
    """``untouched`` (generated, content unchanged), ``edited`` (generated, changed since) or ``owner`` (no marker)."""
    if not isinstance(body, dict) or not isinstance(body.get("generated"), dict):
        return "owner"
    return "untouched" if body["generated"].get("content_sha256") == content_sha256(body) else "edited"


def read_generated_dir(home: Path) -> dict[str, tuple[Path, Any]]:
    """Every ``workers/<name>.yaml``: name -> (path, raw body)."""
    out: dict[str, tuple[Path, Any]] = {}
    d = generated_dir(home)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.yaml")):
        try:
            out[p.stem] = (p, load_yaml(p))
        except YamlError:  # expected: None marks the file as unreadable; status reports it
            out[p.stem] = (p, None)
    return out


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    """What this machine has for one harness provider."""

    provider: str
    adapter: str
    found: bool
    executable: str | None = None
    auth_mode: str | None = None  # cli_login | api_key | none | unknown
    via_search: list[str] = field(default_factory=list)
    problem: str | None = None
    #: Tool-map capabilities whose flag the installed CLI's ``--help`` shows (True) or lacks (False);
    #: ``None``: not checked (0085).
    tools: dict[str, bool] | None = None
    version: str | None = None

    @property
    def usable(self) -> bool:
        return self.found and self.auth_mode in ("cli_login", "api_key")

    def as_dict(self) -> dict[str, Any]:
        out = {"provider": self.provider, "adapter": self.adapter, "found": self.found, "executable": self.executable,
               "auth_mode": self.auth_mode, "usable": self.usable, "problem": self.problem}
        if self.tools is not None:
            out["tools"] = dict(self.tools)
        if self.version:
            out["version"] = self.version
        return out


#: How to fix what discovery found missing, in plain words.
LOGIN_HINTS = {"claude_code": "run `claude` once and log in", "codex": "run `codex login`"}
INSTALL_HINTS = {"claude_code": "install Claude Code (the `claude` command)", "codex": "install the Codex CLI (the `codex` command)"}


#: Where discovery looks for a harness CLI beyond the minimal PATH (§6.2 sources): nvm-managed
#: Node installs, and ``~/.local/bin`` (where native installers such as Claude Code's put it).
DISCOVERY_SEARCH = ["nvm", "~/.local/bin"]


def _probe_profile(adapter: str, creator: str) -> WorkerProfile:
    return WorkerProfile.model_validate({"adapter": adapter, "creator": creator, "auth": {"mode": "cli_login"}, "path": {"search": DISCOVERY_SEARCH}})


def discover(home: Path, data: kw_mod.KnownWorkers) -> dict[str, Detection]:
    """Find each harness provider's CLI and ask it whether it is logged in (no model call)."""
    from . import adapters
    from .doctor import _effective_auth
    from .profiles import SetupError, build_env

    out: dict[str, Detection] = {}
    for route in data.routes:
        prov = data.providers.get(route.provider)
        if prov is None or prov.kind != "harness" or route.provider in out or not route.supported:
            continue
        adapter = adapters.ADAPTERS.get(route.adapter)
        if adapter is None:
            continue
        profile = _probe_profile(route.adapter, data.route_creator(route) or "unknown")
        try:
            env = build_env(profile, home=home, config_home_var=getattr(adapter, "config_home_var", None), resolve=True)
        except SetupError as e:
            out[route.provider] = Detection(route.provider, route.adapter, False, problem=f"not installed here ({INSTALL_HINTS.get(route.adapter, e)})")
            continue
        exe = env.resolved.executable if env.resolved else None
        how = env.resolved.how if env.resolved else ""
        eff = _effective_auth(SimpleNamespace(home=Path(home)), f"setup-{route.provider}", profile, adapter, env)
        mode = eff.get("mode")
        det = Detection(route.provider, route.adapter, True, exe, mode, [how.split(":", 1)[1]] if how.startswith("search:") else [])
        if mode not in ("cli_login", "api_key"):
            det.problem = f"installed but not logged in ({LOGIN_HINTS.get(route.adapter, 'log in to it')})"
        if exe:
            det.tools = check_tool_flags(exe, data.tool_map(route.provider), env.env)
            from .engine import harness_version

            det.version = harness_version(exe, adapter, env.env)
        out[route.provider] = det
    return out


def check_tool_flags(exe: str, tool_map: dict[str, Any], env: dict[str, str]) -> dict[str, bool]:
    """Whether the installed CLI's help shows each mapped flag (0085); a missing flag means the tool is not offered here."""
    import subprocess

    helps: dict[tuple[str, ...], str] = {}
    out: dict[str, bool] = {}
    for cap, t in tool_map.items():
        key = tuple(t.help)
        if key not in helps:
            try:
                r = subprocess.run([exe, *t.help], env=env, capture_output=True, text=True, timeout=30, check=False)
                helps[key] = (r.stdout or "") + (r.stderr or "")
            except (OSError, subprocess.SubprocessError):  # expected: an unreadable help text means the flags are not confirmed
                helps[key] = ""
        out[cap] = re.search(rf"(?<![\w-]){re.escape(t.flag)}(?![\w-])", helps[key]) is not None
    return out


# ---------------------------------------------------------------------------
# Planning profiles
# ---------------------------------------------------------------------------


@dataclass
class Planned:
    name: str
    body: dict[str, Any]
    availability: str  # detected | declared


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def profile_name(route: kw_mod.KnownRoute, resource: str | None) -> str:
    base = _slug(resource or route.provider)
    if route.model_id:
        return f"{base}-{_slug(route.model_id.split('/', 1)[1])}"
    return base


def plan_profiles(data: kw_mod.KnownWorkers, res: Resources, detected: dict[str, Detection], home: Path | None = None) -> tuple[list[Planned], list[dict[str, Any]]]:
    """The profiles the inputs support, and every route left out with why."""
    planned: list[Planned] = []
    skipped: list[dict[str, Any]] = []
    declared = res.workers()
    if home is not None:
        _plan_listings(data, declared, home, planned, skipped)
    for route in data.routes:
        prov = data.providers.get(route.provider)
        label = f"{route.provider} {route.model_id or route.invocation or '(default model)'}"
        if not route.supported:
            skipped.append({"route": label, "reason": f"no adapter in this runtime runs it ({route.adapter})"})
            continue
        model = data.models.get(route.model_id) if route.model_id else None
        if model is not None and model.retired:
            skipped.append({"route": label, "reason": "retired"})
            continue
        caps = list(dict.fromkeys([*(model.capabilities if model else []), *route.capabilities]))
        base: dict[str, Any] = {"adapter": route.adapter, "creator": data.route_creator(route)}
        if route.model_id and not route.alias:
            base["model_id"] = route.model_id
        base["provider"] = route.provider
        if route.invocation:
            base["model"] = route.invocation
        tier = route.tier or (model.tier if model else None)
        ctx = route.context_tokens or (model.context_tokens if model else None)
        if prov is not None and prov.kind == "harness":
            det = detected.get(route.provider)
            if det is None or not det.usable:
                skipped.append({"route": label, "reason": det.problem if det else "not checked"})
                continue
            extra = [c for r in declared.values() if r.provider == route.provider for c in r.capabilities]
            tools = [c for c, ok in (det.tools or {}).items() if ok]  # the tool map's, when this CLI has the flag (0085)
            body = {**base, "capabilities": list(dict.fromkeys(caps + tools + extra))}
            if tier:
                body["tier"] = tier
            if ctx:
                body["context_tokens"] = ctx
            body["auth"] = {"mode": det.auth_mode}
            if prov.env_deny:
                body["env_deny"] = list(prov.env_deny)
            if det.via_search:
                body["path"] = {"search": det.via_search}
            planned.append(Planned(profile_name(route, None), body, "detected"))
            continue
        matches = {n: r for n, r in declared.items() if r.provider == route.provider}
        if not matches:
            skipped.append({"route": label, "reason": f"no {route.provider} resource declared"})
            continue
        for rname, r in sorted(matches.items()):
            if r.models and route.model_id not in r.models:
                skipped.append({"route": label, "reason": f"not in {rname}'s models"})
                continue
            if r.credential is None:
                skipped.append({"route": label, "reason": f"{rname} has no credential"})
                continue
            if prov is None or not prov.api_key_env:
                skipped.append({"route": label, "reason": f"known-workers names no key variable for {route.provider}"})
                continue
            body = {**base, "resource": rname, "capabilities": list(dict.fromkeys(caps + r.capabilities))}
            if tier:
                body["tier"] = tier
            if ctx:
                body["context_tokens"] = ctx
            body["auth"] = {"mode": "api_key", "env": {prov.api_key_env: r.credential}}
            if r.base_url:
                body["options"] = {"base_url": r.base_url}
            planned.append(Planned(profile_name(route, rname), body, "declared"))
    return planned, skipped


def _plan_listings(data: kw_mod.KnownWorkers, declared: dict[str, WorkerResource], home: Path, planned: list[Planned],
                   skipped: list[dict[str, Any]]) -> None:
    """Profiles for listed models no researched route covers (Decisions 0109, 0110, 0112, 0113)."""
    researched = {r.invocation: r.model_id for r in data.routes if r.invocation and r.model_id and not r.alias}
    have = {r.invocation for r in data.routes if r.invocation}
    for rname, r in sorted(declared.items()):
        prov = data.providers.get(r.provider)
        generic = prov is not None and prov.kind == "openai_compatible"
        listing = listings_mod.load(home, rname if generic else r.provider)
        base = (r.base_url or prov.base_url) if prov is not None else None
        if listing is None or prov is None or (generic and not base):
            continue
        if not generic and (r.credential is None or not prov.api_key_env):
            continue
        for c in listings_mod.candidates(listing, researched, r.provider):
            invocation = f"openai/{c.id}" if generic else f"{r.provider}/{c.id}"
            if invocation in have or (r.models and (c.model_id or c.id) not in r.models):
                continue
            known = data.models.get(c.model_id) if c.model_id and not c.alias else None  # judged by research or an assessment (0112)
            body: dict[str, Any] = {"adapter": "litellm_api", "creator": known.creator if known else c.creator}
            if c.model_id and not c.alias:
                body["model_id"] = c.model_id
            body.update({"provider": r.provider, "model": invocation, "resource": rname,
                         "capabilities": list(dict.fromkeys([*(known.capabilities if known else []), *c.capabilities, *r.capabilities])),
                         "tier": (known.tier if known and known.tier else "basic")})
            if c.context_tokens or (known and known.context_tokens):
                body["context_tokens"] = c.context_tokens or known.context_tokens
            if c.price:
                body["price"] = {**c.price, "source": listing["source"], "date": listing["fetched"]}
            if generic and r.credential is None:  # a local runtime: no key; the OpenAI client wants some value (0118)
                body["auth"] = {"mode": "none"}
                body["options"] = {"base_url": base, "api_key": "not-needed"}
            else:
                body["auth"] = {"mode": "api_key", "env": {prov.api_key_env: r.credential}}
                if base:
                    body["options"] = {"base_url": base}
            planned.append(Planned(f"{_slug(rname)}-{_slug(c.id)}", body, "declared"))


# ---------------------------------------------------------------------------
# Verification (0081)
# ---------------------------------------------------------------------------

Verifier = Callable[[Path, str, WorkerProfile], tuple[bool, str]]


def live_check(home: Path, name: str, profile: WorkerProfile) -> tuple[bool, str]:
    """One minimal round trip through the profile's adapter (its no-op). Costs one small model call."""
    from . import adapters
    from .doctor import NOOP_TIMEOUT_S, _run
    from .engine import classify_exit
    from .profiles import SetupError, build_env, executable_for

    adapter = adapters.ADAPTERS.get(profile.adapter)
    noop = getattr(adapter, "noop_command", None)
    if adapter is None or noop is None:
        return False, f"adapter {profile.adapter} has no live check"
    try:
        env = build_env(profile, home=home, config_home_var=getattr(adapter, "config_home_var", None), resolve=bool(executable_for(profile)))
        with tempfile.TemporaryDirectory(prefix="baton-verify-") as tmp:
            child = _run(noop(profile), env, Path(tmp), Path(home) / "logs" / "workers" / f"{name}-verify.log", NOOP_TIMEOUT_S)
    except SetupError as e:
        return False, str(e)
    if child.timed_out:
        return False, f"no answer within {NOOP_TIMEOUT_S} s"
    if child.exit_code != 0:
        cls = classify_exit(child, adapter.failure_signals)
        return False, f"{cls['class']} ({cls['code']}): {cls['message']}"
    return True, "ok"


# ---------------------------------------------------------------------------
# Status and setup
# ---------------------------------------------------------------------------


def _inputs(home: Path) -> tuple[kw_mod.KnownWorkers, str, Resources]:
    voc = vocab_mod.load(vocab_mod.DEFAULT)
    path = kw_mod.default_path()
    data = kw_mod.load_with_overlay(voc, home, path)  # the owner's assessed models (0111) join the shipped data
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return data, sha, load_resources(home, data.machine_dependent)


def refresh(current: dict[str, Any], planned: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The refreshed body of an untouched generated profile, or why it is left as it is.

    ``(None, None)``: already up to date. ``(None, reason)``: the binding
    changed, so it is not refreshed (a new name would be a new profile).
    """
    for key in BINDING:
        if current.get(key) != planned.get(key):
            return None, f"its {key} would change ({current.get(key)!r} -> {planned.get(key)!r}); left as it is"
    changed = {k: planned[k] for k in REFRESHABLE if k in planned and current.get(k) != planned[k]}
    gone = [k for k in REFRESHABLE if k in current and k not in planned]
    if not changed and not gone:
        return None, None
    body = {k: v for k, v in current.items() if k not in gone}
    body.update(changed)
    return body, None


def _write_generated(home: Path, name: str, body: dict[str, Any], marker: dict[str, Any]) -> None:
    body = {k: v for k, v in body.items() if k != "generated"}
    marker = {**marker, "content_sha256": content_sha256(body)}
    _atomic_write(generated_dir(home) / f"{name}.yaml", HEADER + yaml.safe_dump({**body, "generated": marker}, sort_keys=False))


def _route_for(data: kw_mod.KnownWorkers, body: dict[str, Any]) -> kw_mod.KnownRoute | None:
    """The catalog route a generated profile came from: same provider, and its model id (or its invocation for an alias)."""
    for route in data.routes:
        if route.provider != body.get("provider"):
            continue
        if body.get("model_id"):
            if route.model_id == body["model_id"]:
                return route
        elif route.invocation == body.get("model") and (route.alias or not route.model_id):
            return route
    return None


def _not_offered(
    data: kw_mod.KnownWorkers,
    gen: dict[str, dict[str, Any]],
    planned_names: set[str],
    home: Path,
    *,
    detected: dict[str, Detection] | None = None,
    res: Resources | None = None,
    skipped: list[dict[str, Any]] | None = None,
    kw_sha: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Generated profiles the inputs no longer offer: kept, flagged with one specific reason (0079).

    Each value has ``flag`` (plain words), ``flag_code`` and ``catalog_mismatch``. The
    reason is the first that applies: retired model, harness not usable, resource gone,
    route gone from the catalog in use, any other skipped route.
    """
    out: dict[str, dict[str, Any]] = {}
    files = read_generated_dir(home)
    declared = res.workers() if res is not None else {}
    for name, g in gen.items():
        if g["ownership"] == "owner" or name in planned_names:
            continue
        body = files[name][1] if name in files else None
        body = body if isinstance(body, dict) else {}
        marker = body.get("generated") if isinstance(body.get("generated"), dict) else {}
        then = marker.get("known_workers_sha256")
        mismatch = bool(then and kw_sha and then != kw_sha)
        mid = body.get("model_id")
        prov = data.providers.get(body.get("provider", ""))
        route = _route_for(data, body)
        if mid and mid in data.models and data.models[mid].retired:
            code, why = "retired", "retired: its model is withdrawn; kept, remove it when you like"
        elif prov is not None and prov.kind == "harness" and detected is not None and not (detected.get(body["provider"]) and detected[body["provider"]].usable):
            det = detected.get(body["provider"])
            code, why = "harness_unusable", f"no longer offered here: {body['provider']} is {det.problem if det and det.problem else 'not usable on this machine'}; kept"
        elif body.get("resource") and res is not None and body["resource"] not in declared:
            code, why = "resource_gone", f"no longer offered here: its resource {body['resource']!r} is no longer declared; kept"
        elif body.get("resource") and res is not None and declared[body["resource"]].models and mid not in declared[body["resource"]].models:
            code, why = "resource_gone", f"no longer offered here: resource {body['resource']!r} no longer lists {mid}; kept"
        elif body.get("resource") and res is not None and declared[body["resource"]].credential is None:
            code, why = "resource_gone", f"no longer offered here: resource {body['resource']!r} has no credential; kept"
        elif route is None:
            code, why = "route_gone", "no longer offered here: no route in the known-workers catalog in use produces it; kept"
            if mismatch:
                why += (f" (it was generated from a different catalog, sha {str(then)[:12]}, and this one is {str(kw_sha)[:12]};"
                        " a different Baton runtime or an updated catalog may be the cause)")
        else:
            label = f"{route.provider} {route.model_id or route.invocation or '(default model)'}"
            reason = next((s["reason"] for s in skipped or [] if s["route"] == label), None)
            code, why = "skipped", f"no longer offered here: {reason or 'its route is not offered'}; kept"
        out[name] = {"flag": why, "flag_code": code, "catalog_mismatch": mismatch}
    return out


def _owner_names(home: Path) -> set[str]:
    from .project import MACHINE_PROFILES

    names: set[str] = set()
    path = Path(home) / MACHINE_PROFILES
    if path.is_file():
        try:
            raw = load_yaml(path) or {}
            names |= set(raw) if isinstance(raw, dict) else set()
        except YamlError as e:
            diag.note("resources.yaml_invalid", "resources:_owner_names", error=f"{type(e).__name__}: {e}", path=str(path))
    return names


def generated_profiles(home: Path) -> dict[str, dict[str, Any]]:
    """Each file in ``workers/``: its ownership, availability and verification."""
    out: dict[str, dict[str, Any]] = {}
    for name, (path, body) in read_generated_dir(home).items():
        own = ownership(body)
        marker = body.get("generated") if isinstance(body, dict) else None
        entry: dict[str, Any] = {"path": str(path), "ownership": own}
        if isinstance(marker, dict):
            entry["availability"] = marker.get("availability")
            entry["verified"] = marker.get("verified")
        out[name] = entry
    return out


def status(home: Path, *, discover_fn: Callable[[Path, kw_mod.KnownWorkers], dict[str, Detection]] = discover) -> dict[str, Any]:
    """Read-only: what is discovered, declared and generated, and whether machine setup is complete."""
    home = Path(home)
    data, kw_sha, res = _inputs(home)
    detected = discover_fn(home, data)
    planned, skipped = plan_profiles(data, res, detected, home)
    gen = generated_profiles(home)
    state = res.setup.get("worker") or SetupState()
    owner = _owner_names(home)
    new = [p.name for p in planned if p.name not in gen and p.name not in owner]
    unverified = sorted(n for n, g in gen.items() if g["ownership"] != "owner" and not g.get("verified"))
    for name, detail in _not_offered(data, gen, {p.name for p in planned}, home, detected=detected, res=res, skipped=skipped, kw_sha=kw_sha).items():
        gen[name].update(detail)
    states = _states_or_problem(home)
    claims = machine_claims(home)
    for name, g in gen.items():
        g["capabilities"] = cs_summary(states, name, claims.get(name, []))
    return {
        "catalog": {"path": str(kw_mod.default_path()), "sha256": kw_sha},
        "setup_complete": state.completed is not None,
        "setup": state.model_dump(mode="json"),
        "detected": [d.as_dict() for d in detected.values()],
        "declared": {n: r.model_dump(mode="json", exclude_none=True) for n, r in res.workers().items()},
        "generated": gen,
        "available_not_generated": new,
        "unverified": unverified,
        "skipped": skipped,
        "capability_states": {n: {c: st.as_dict() for c, st in caps.items()} for n, caps in states.items()},
    }


def _states_or_problem(home: Path) -> dict[str, Any]:
    from . import capability_states as cs

    try:
        return cs.load(home)
    except cs.CapabilityStatesError as e:
        raise ResourcesError([Issue(code="resources.capability_states", where=str(cs.path(home)), message=str(e))]) from e


def cs_summary(states: dict[str, Any], profile: str, claimed: list[str]) -> dict[str, str]:
    """Each claimed capability's state word, for ``workers status`` (0084)."""
    from . import capability_states as cs

    return {c: cs.state_of(states, profile, c).state for c in claimed}


def setup(
    home: Path,
    *,
    verify: list[str] | None = None,
    today: dt.date | None = None,
    discover_fn: Callable[[Path, kw_mod.KnownWorkers], dict[str, Detection]] = discover,
    verifier: Verifier = live_check,
) -> dict[str, Any]:
    """The explicit manager run: discover, plan, write new generated profiles, verify when asked, record completion.

    ``verify``: profile names to live-check (``[]``: every generated one). A
    new profile that fails its check is not written; an existing one keeps
    its file and the failure is reported.
    """
    home = Path(home)
    today = today or dt.date.today()
    data, kw_sha, res = _inputs(home)
    detected = discover_fn(home, data)
    planned, skipped = plan_profiles(data, res, detected, home)
    existing = read_generated_dir(home)
    owner = _owner_names(home)
    written: list[str] = []
    refreshed: list[str] = []
    kept: list[dict[str, str]] = []
    collisions: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    verified: list[str] = []
    want_all = verify is not None and len(verify) == 0
    stamp = {"by": f"baton {__version__}", "known_workers_sha256": kw_sha}

    def wants(name: str) -> bool:
        return verify is not None and (want_all or name in verify)

    def check(name: str, body: dict[str, Any]) -> dict[str, Any] | None:
        ok, why = verifier(home, name, WorkerProfile.model_validate({k: v for k, v in body.items() if k != "generated"}))
        if not ok:
            failed.append({"profile": name, "reason": why})
            return None
        verified.append(name)
        return {"date": today.isoformat(), "adapter": body["adapter"], "runtime": __version__}

    for p in planned:
        try:
            if p.name in owner or (p.name in existing and ownership(existing[p.name][1]) == "owner"):
                collisions.append({"profile": p.name, "reason": "an owner profile already has this name; left alone"})
                continue
            if p.name in existing:
                path, current = existing[p.name]
                if ownership(current) == "edited":
                    kept.append({"profile": p.name, "reason": "edited by the owner; never changed"})
                    continue
                marker = dict(current["generated"])
                new_body, why = refresh(current, p.body)
                if why:
                    kept.append({"profile": p.name, "reason": why})
                if wants(p.name):
                    v = check(p.name, new_body or current)
                    if v is None:
                        continue
                    marker["verified"] = v
                if new_body is not None or wants(p.name):
                    _write_generated(home, p.name, new_body or current, {**marker, **stamp})
                    if new_body is not None:
                        refreshed.append(p.name)
                continue
            marker = {**stamp, "availability": p.availability}
            if wants(p.name):
                v = check(p.name, p.body)
                if v is None:
                    continue  # a new profile that fails its check is not written (0081)
                marker["verified"] = v
            _write_generated(home, p.name, p.body, marker)
            written.append(p.name)
        except (OSError, ValidationError) as e:  # one profile failing never stops the others (0079)
            failed.append({"profile": p.name, "reason": f"{type(e).__name__}: {e}"})
    not_offered = {n: d["flag"] for n, d in _not_offered(data, generated_profiles(home), {p.name for p in planned}, home, detected=detected,
                                                         res=res, skipped=skipped, kw_sha=kw_sha).items()}
    for name in verify or []:
        if name not in verified and name not in {f["profile"] for f in failed}:
            failed.append({"profile": name, "reason": "not a generated profile this machine offers now; nothing was checked"})
    state = res.setup.get("worker") or SetupState()
    res.setup["worker"] = SetupState(completed=today, runtime=__version__, nothing_more=state.nothing_more)
    save_resources(home, res)
    return {"written": written, "refreshed": refreshed, "kept": kept, "collisions": collisions, "verified": verified, "failed": failed,
            "not_offered": not_offered, "skipped": skipped, "detected": [d.as_dict() for d in detected.values()], "setup_complete": True}


def refresh_listings(home: Path, *, fetch: listings_mod.Fetcher = listings_mod.http_fetch, today: dt.date | None = None) -> dict[str, Any]:
    """Fetch the listing of every declared provider that has a source (acceptance 6): a failure keeps the last good cache.

    A provider of kind ``openai_compatible`` is listed per resource, from ``<base_url>/models`` (Decision 0118).
    """
    data, _, res = _inputs(home)
    refreshed: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    jobs: list[tuple[str, dict[str, Any]]] = [(p, {}) for p in sorted({r.provider for r in res.workers().values()} & set(listings_mod.SOURCES))]
    for rname, r in sorted(res.workers().items()):
        prov = data.providers.get(r.provider)
        base = (r.base_url or prov.base_url) if prov is not None else None
        if prov is None or prov.kind != "openai_compatible" or not base:
            continue
        headers: dict[str, str] = {}
        if r.credential:
            try:
                headers["Authorization"] = "Bearer " + profiles_mod.resolve_value(r.credential, home)
            except Exception as e:  # expected: an unset secret means this listing cannot be read, reported below
                failed.append({"provider": rname, "reason": f"could not read {rname}'s model list (its key is not available: {e})"})
                continue
        jobs.append((rname, {"provider": r.provider, "key": rname, "url": base.rstrip("/") + "/models", "headers": headers, "style": "openai"}))
    for label, kw in jobs:
        try:
            body = listings_mod.refresh(home, kw.pop("provider", label), fetch=fetch, today=today, **kw)
            refreshed.append({"provider": label, "models": len(body["models"]), "fetched": body["fetched"]})
        except listings_mod.ListingError as e:
            diag.note("listings.fetch_failed", "resources:refresh_listings", provider=label, error=str(e))
            failed.append({"provider": label, "reason": f"could not read {label}'s model list ({e}); the last good list, if any, is kept"})
    return {"refreshed": refreshed, "failed": failed}


def declare(
    home: Path,
    name: str | None = None,
    *,
    provider: str | None = None,
    credential: str | None = None,
    base_url: str | None = None,
    models: list[str] | None = None,
    capabilities: list[str] | None = None,
    note: str | None = None,
    remove: bool = False,
    nothing_more: bool | None = None,
) -> dict[str, Any]:
    """Add, change or remove a worker resource, or record that there is nothing more to add (0077, 0078)."""
    home = Path(home)
    data, _sha, res = _inputs(home)
    changed: dict[str, Any] = {}
    if name is not None:
        if remove:
            if name not in res.resources:
                raise ResourcesError([Issue(code="resources.unknown", where=name, message=f"no resource named {name!r}")])
            res.resources.pop(name)
            changed = {"removed": name}
        else:
            prev = res.resources.get(name)
            body = prev.model_dump() if prev else {"kind": "worker"}
            if provider is None and prev is None:
                raise ResourcesError([Issue(code="resources.no_provider", where=name, message="a new resource needs --provider")])
            for k, v in (("provider", provider), ("credential", credential), ("base_url", base_url), ("models", models),
                         ("capabilities", capabilities), ("note", note)):
                if v is not None:
                    body[k] = v
            checked, issues = validate_resources({"resources": {name: body}}, data.machine_dependent, source="declare")
            if issues or checked is None:
                raise ResourcesError(issues)
            dprov = data.providers.get(checked.resources[name].provider)
            if dprov is not None and dprov.kind == "openai_compatible" and not (checked.resources[name].base_url or dprov.base_url):
                raise ResourcesError([Issue(code="resources.no_base_url", where=name, message="an openai_compatible endpoint needs --base-url")])
            res.resources[name] = checked.resources[name]
            changed = {"declared": name, "resource": res.resources[name].model_dump(mode="json", exclude_none=True)}
            if res.resources[name].provider not in data.providers:
                changed["warning"] = f"no known routes reach provider {res.resources[name].provider!r}; nothing will be generated for it"
    if nothing_more is not None:
        state = res.setup.get("worker") or SetupState()
        res.setup["worker"] = SetupState(completed=state.completed, runtime=state.runtime, nothing_more=nothing_more)
        changed["nothing_more"] = nothing_more
    path = save_resources(home, res)
    return {**changed, "path": str(path)}


def machine_claims(home: Path) -> dict[str, list[str]]:
    """Each machine profile's claimed capabilities (generated files, then ``workers.yaml``), read without validation."""
    from .project import MACHINE_PROFILES

    out: dict[str, list[str]] = {}
    for name, (_p, body) in read_generated_dir(home).items():
        if isinstance(body, dict):
            out[name] = list(body.get("capabilities") or [])
    path = Path(home) / MACHINE_PROFILES
    if path.is_file():
        try:
            raw = load_yaml(path) or {}
        except YamlError as e:
            diag.note("resources.yaml_invalid", "resources:machine_claims", error=f"{type(e).__name__}: {e}", path=str(path))
            raw = {}
        for name, body in raw.items() if isinstance(raw, dict) else []:
            if isinstance(body, dict):
                out[str(name)] = list(body.get("capabilities") or [])
    return out


def declare_capabilities(home: Path, profile: str, *, likely: list[str] | None = None, absent: list[str] | None = None,
                         claimed: list[str] | None = None, today: dt.date | None = None) -> dict[str, Any]:
    """The owner resets capability states to ``likely`` or declares them ``absent`` on one profile (0084).

    ``claimed``: the profile's capabilities when the caller already has them
    (a project's profiles include ``.baton/workers.local.yaml``); otherwise the machine's.
    """
    from . import capability_states as cs

    if claimed is None:
        claims = machine_claims(home)
        if profile not in claims:
            raise ResourcesError([Issue(code="resources.unknown_profile", where=profile, message=f"no profile named {profile!r} on this machine")])
        claimed = claims[profile]
    try:
        changes = cs.declare(home, profile, claimed, likely=likely or [], absent=absent or [], today=today)
    except cs.CapabilityStatesError as e:
        raise ResourcesError([Issue(code="resources.capability_state", where=profile, message=str(e))]) from e
    return {"profile": profile, "capability_states": changes, "path": str(cs.path(home))}


def readiness(home: Path) -> dict[str, Any]:
    """Machine worker setup at a glance, for ``doctor``, ``detect`` and ``init`` (§13.4). Reads files only: no discovery.

    ``offer_setup`` is true until the owner has run setup or said there is nothing
    to add, so the Director offers the setup conversation once per machine, not per project.
    """
    home = Path(home)
    try:
        data = kw_mod.load(vocab_mod.load(vocab_mod.DEFAULT))
        res = load_resources(home, data.machine_dependent)
    except (ResourcesError, kw_mod.KnownWorkersError) as e:
        return {"setup_complete": False, "nothing_more": False, "offer_setup": False, "generated": 0, "problem": str(e)}
    state = res.setup.get("worker") or SetupState()
    gen = generated_profiles(home)
    return {
        "setup_complete": state.completed is not None,
        "nothing_more": state.nothing_more,
        "offer_setup": state.completed is None and not state.nothing_more,
        "generated": sum(1 for g in gen.values() if g["ownership"] != "owner"),
        "declared": len(res.workers()),
    }

