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

from . import __version__
from . import known_workers as kw_mod
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
        except YamlError:
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

    @property
    def usable(self) -> bool:
        return self.found and self.auth_mode in ("cli_login", "api_key")

    def as_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "adapter": self.adapter, "found": self.found, "executable": self.executable,
                "auth_mode": self.auth_mode, "usable": self.usable, "problem": self.problem}


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
        out[route.provider] = det
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


def plan_profiles(data: kw_mod.KnownWorkers, res: Resources, detected: dict[str, Detection]) -> tuple[list[Planned], list[dict[str, Any]]]:
    """The profiles the inputs support, and every route left out with why."""
    planned: list[Planned] = []
    skipped: list[dict[str, Any]] = []
    declared = res.workers()
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
            body = {**base, "capabilities": list(dict.fromkeys(caps + extra))}
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
    data = kw_mod.load(voc, path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return data, sha, load_resources(home, data.machine_dependent)


def _owner_names(home: Path) -> set[str]:
    from .project import MACHINE_PROFILES

    names: set[str] = set()
    path = Path(home) / MACHINE_PROFILES
    if path.is_file():
        try:
            raw = load_yaml(path) or {}
            names |= set(raw) if isinstance(raw, dict) else set()
        except YamlError:
            pass
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
    data, _sha, res = _inputs(home)
    detected = discover_fn(home, data)
    planned, skipped = plan_profiles(data, res, detected)
    gen = generated_profiles(home)
    state = res.setup.get("worker") or SetupState()
    owner = _owner_names(home)
    new = [p.name for p in planned if p.name not in gen and p.name not in owner]
    unverified = sorted(n for n, g in gen.items() if g["ownership"] != "owner" and not g.get("verified"))
    return {
        "setup_complete": state.completed is not None,
        "setup": state.model_dump(mode="json"),
        "detected": [d.as_dict() for d in detected.values()],
        "declared": {n: r.model_dump(mode="json", exclude_none=True) for n, r in res.workers().items()},
        "generated": gen,
        "available_not_generated": new,
        "unverified": unverified,
        "skipped": skipped,
    }


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
    planned, skipped = plan_profiles(data, res, detected)
    existing = read_generated_dir(home)
    owner = _owner_names(home)
    written: list[str] = []
    kept: list[str] = []
    collisions: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    verified: list[str] = []
    want_all = verify is not None and len(verify) == 0
    for p in planned:
        if p.name in owner or (p.name in existing and ownership(existing[p.name][1]) == "owner"):
            collisions.append({"profile": p.name, "reason": "an owner profile already has this name; left alone"})
            continue
        if p.name in existing:
            kept.append(p.name)
            continue
        body = dict(p.body)
        marker: dict[str, Any] = {"by": f"baton {__version__}", "known_workers_sha256": kw_sha, "availability": p.availability}
        if verify is not None and (want_all or p.name in verify):
            ok, why = verifier(home, p.name, WorkerProfile.model_validate(body))
            if not ok:
                failed.append({"profile": p.name, "reason": why})
                continue
            marker["verified"] = {"date": today.isoformat(), "adapter": body["adapter"], "runtime": __version__}
            verified.append(p.name)
        marker["content_sha256"] = content_sha256(body)
        body["generated"] = marker
        _atomic_write(generated_dir(home) / f"{p.name}.yaml",
                      f"# Generated by baton workers setup (§6.4). Edit freely: an edited file is yours and is never changed again.\n"
                      + yaml.safe_dump(body, sort_keys=False))
        written.append(p.name)
    if verify is not None:
        for name in sorted(existing):
            path, body = existing[name]
            if name in written or not (want_all or name in verify) or ownership(body) != "untouched":
                continue
            try:
                profile = WorkerProfile.model_validate({k: v for k, v in body.items()})
            except ValidationError as e:
                failed.append({"profile": name, "reason": f"invalid: {e.errors()[0]['msg']}"})
                continue
            ok, why = verifier(home, name, profile)
            if not ok:
                failed.append({"profile": name, "reason": why})
                continue
            body = dict(body)
            body["generated"] = {**body["generated"], "verified": {"date": today.isoformat(), "adapter": body["adapter"], "runtime": __version__}}
            _atomic_write(path, f"# Generated by baton workers setup (§6.4). Edit freely: an edited file is yours and is never changed again.\n"
                          + yaml.safe_dump(body, sort_keys=False))
            verified.append(name)
    state = res.setup.get("worker") or SetupState()
    res.setup["worker"] = SetupState(completed=today, runtime=__version__, nothing_more=state.nothing_more)
    save_resources(home, res)
    return {"written": written, "kept": kept, "collisions": collisions, "verified": verified, "failed": failed,
            "skipped": skipped, "detected": [d.as_dict() for d in detected.values()], "setup_complete": True}


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
