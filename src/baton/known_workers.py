"""Known-workers data (``defaults/known-workers.yaml``, ``baton-known-workers/1``; Decision 0080).

Shared, read-only knowledge about models and the routes that reach them,
shipped with the runtime beside the adapters. The worker resource manager
(§6.4) turns it into profiles; nothing else reads it, and independence
(§8.4) never does: it uses the identity recorded at dispatch.

Three sections:

* ``models``, keyed by ``model_id`` (0075): creator, intrinsic capabilities,
  tier, context size, category, sources and research date.
* ``providers``: how access is obtained (``direct_api``, ``intermediary``,
  ``harness``, ``local``), with sources; a harness's ``tools`` map says which
  args turn each tooling capability on (0085).
* ``routes``: one way to run a model: provider, adapter, invocation
  identifier, whether it is a mutable alias, whether this runtime can execute
  it (``supported``), route-level capabilities, and ``verified`` only for an
  actual live check.

Research claims (``sources``, ``researched``) and live checks (``verified``)
are separate fields, so an unverified finding is never shown as tested.
``machine_dependent`` lists capabilities that never come from this data
(0082): they need an owner declaration or a probe on the machine.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import data
from .data import YamlError, load_yaml
from .models import MODEL_ID, Issue
from .vocab import Vocabulary

FORMAT = "baton-known-workers/1"
FILE = "known-workers.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(_Strict):
    url: str = Field(pattern=r"^https?://")
    retrieved: dt.date


#: LiteLLM model-map fields that show a capability (basis ``catalog``, 0088).
CATALOG_FIELDS = {
    "supports_response_schema": "structured_output",
    "supports_function_calling": "tool_use",
    "supports_vision": "vision",
}


class CapabilityBasis(_Strict):
    """Why a capability is claimed (0088): a basis, not proof; the claim ships as ``likely`` (0084)."""

    kind: Literal["documented", "catalog", "judgment"]
    #: ``documented``: where the capability is stated.
    source: Source | None = None
    #: ``catalog``: the LiteLLM model-map field that shows it (``CATALOG_FIELDS``).
    litellm: str | None = None
    #: ``judgment``: one line on why the creator class normally has it.
    reason: str | None = Field(default=None, min_length=1)


class KnownModel(_Strict):
    creator: str
    category: str = "llm"
    capabilities: list[str] = Field(default_factory=list)
    #: Capability -> why it is claimed (0088); optional in the format, required by research.
    capability_basis: dict[str, CapabilityBasis] = Field(default_factory=dict)
    tier: str | None = None
    context_tokens: int | None = Field(default=None, ge=1)
    sources: list[Source] = Field(min_length=1)
    researched: dt.date
    retired: bool = False


class ToolArgs(_Strict):
    """How a harness turns on one tooling capability (0085): researched data, not adapter code."""

    #: Args that turn the tool on, placed by the adapter.
    args: list[str] = Field(min_length=1)
    #: ``with_args``: among the mode args (after a subcommand); ``before_subcommand``: right after the executable.
    position: Literal["with_args", "before_subcommand"] = "with_args"
    #: Args that print the help that must mention ``flag`` (``workers setup`` checks it, 0085).
    help: list[str] = Field(default_factory=lambda: ["--help"])
    flag: str
    #: Args that turn the tool off when a step does not require it (least privilege); empty: off by default.
    off_args: list[str] = Field(default_factory=list)
    off_position: Literal["with_args", "before_subcommand"] = "with_args"
    #: Tool or event names in the harness's event stream that show the capability used (§6.3).
    evidence: list[str] = Field(min_length=1)
    #: The CLI versions the args were checked against, e.g. ``2.1.319``; informational.
    versions: str | None = None
    sources: list[Source] = Field(default_factory=list)
    note: str | None = None


class KnownProvider(_Strict):
    kind: Literal["direct_api", "intermediary", "harness", "local", "openai_compatible"]
    #: A harness's creators: whose models it can run (0089); research must route each of their models or name the gap.
    creators: list[str] = Field(default_factory=list)
    #: A harness's tool map: tooling capability -> how to turn it on (0085).
    tools: dict[str, ToolArgs] = Field(default_factory=dict)
    #: The directory facts (0117), all optional: how the owner is told about the provider and where it is reached.
    display_name: str | None = None
    #: An ``openai_compatible`` provider's endpoint; a resource's own ``base_url`` overrides it. Its listing is ``<base_url>/models``.
    base_url: str | None = Field(default=None, pattern=r"^https?://")
    #: Where the owner gets a key.
    signup_url: str | None = Field(default=None, pattern=r"^https?://")
    #: The variable its adapter reads the API key from (direct APIs, intermediaries).
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    #: Variables a generated profile always removes (a stray key could switch a CLI login's billing, §6.1).
    env_deny: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class Verified(_Strict):
    date: dt.date
    tool: str
    version: str


class KnownRoute(_Strict):
    model_id: str | None = Field(default=None, pattern=MODEL_ID)
    creator: str | None = None          # for a route with no model_id (a mutable alias)
    provider: str
    adapter: str
    invocation: str | None = None       # the profile's ``model``; none: the harness's own default
    alias: bool = False
    supported: bool
    capabilities: list[str] = Field(default_factory=list)   # what the route adds (e.g. a harness's tools)
    capability_basis: dict[str, CapabilityBasis] = Field(default_factory=dict)
    tier: str | None = None             # for an alias route, which has no model entry
    context_tokens: int | None = Field(default=None, ge=1)
    sources: list[Source] = Field(default_factory=list)
    verified: Verified | None = None


class KnownWorkers(_Strict):
    format: str
    machine_dependent: list[str] = Field(default_factory=list)
    models: dict[str, KnownModel] = Field(default_factory=dict)
    providers: dict[str, KnownProvider] = Field(default_factory=dict)
    routes: list[KnownRoute] = Field(default_factory=list)

    def tool_map(self, provider: str | None) -> dict[str, ToolArgs]:
        """The harness provider's tool map; empty when it has none."""
        prov = self.providers.get(provider or "")
        return dict(prov.tools) if prov is not None else {}

    def route_creator(self, route: KnownRoute) -> str | None:
        if route.model_id is not None and route.model_id in self.models:
            return self.models[route.model_id].creator
        return route.creator


class KnownWorkersError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


def default_path() -> Path:
    return data.path("defaults") / FILE


def validate(raw: object, vocab: Vocabulary, adapters: set[str], source: str = FILE, require_basis: bool = False) -> tuple[KnownWorkers | None, list[Issue]]:
    """Schema, vocabulary, adapters, identity consistency and provenance (0080).

    ``require_basis``: every claimed capability must carry a basis (0088); research
    sets it, the optional field keeps older data loading."""
    def issue(code: str, where: str, message: str) -> Issue:
        return Issue(code=f"known_workers.{code}", where=f"{source}:{where}" if where else source, message=message)

    try:
        kw = KnownWorkers.model_validate(raw)
    except ValidationError as e:
        return None, [issue("invalid", ".".join(map(str, err["loc"])), err["msg"]) for err in e.errors()]
    issues: list[Issue] = []
    if kw.format != FORMAT:
        issues.append(issue("format", "format", f"expected {FORMAT}, got {kw.format!r}"))
    for cap in kw.machine_dependent:
        if cap not in vocab.capabilities:
            issues.append(issue("unknown_capability", "machine_dependent", f"capability {cap!r} is not in {vocab.id}"))

    def check_caps(caps: list[str], where: str) -> None:
        for cap in caps:
            if cap not in vocab.capabilities:
                issues.append(issue("unknown_capability", where, f"capability {cap!r} is not in {vocab.id}"))
            elif cap in kw.machine_dependent:
                issues.append(issue("machine_dependent", where, f"{cap!r} depends on the machine; it needs an owner declaration or a probe, never known-workers data"))

    def check_basis(caps: list[str], basis: dict[str, CapabilityBasis], where: str) -> None:
        for cap, b in basis.items():
            w = f"{where}.capability_basis.{cap}"
            if cap not in caps:
                issues.append(issue("basis_unclaimed", w, f"a basis for {cap!r}, which is not claimed here"))
            if b.kind == "documented" and b.source is None:
                issues.append(issue("basis_incomplete", w, "a documented basis needs a source (url, retrieved)"))
            elif b.kind == "catalog" and CATALOG_FIELDS.get(b.litellm or "") != cap:
                issues.append(issue("basis_incomplete", w, f"a catalog basis names the LiteLLM field that shows {cap!r} ({', '.join(f for f, c in CATALOG_FIELDS.items() if c == cap) or 'none exists for it'})"))
            elif b.kind == "judgment" and not b.reason:
                issues.append(issue("basis_incomplete", w, "a judgment basis needs a one-line reason"))
        if require_basis:
            for cap in caps:
                if cap not in basis:
                    issues.append(issue("basis_missing", f"{where}.capabilities", f"capability {cap!r} has no basis (documented, catalog or judgment); omit it or give one"))

    def check_tier(tier: str | None, where: str) -> None:
        if tier is not None and tier not in vocab.tiers:
            issues.append(issue("unknown_tier", where, f"tier {tier!r} is not in {vocab.id} ({', '.join(vocab.tiers)})"))

    from .capability_states import TOOLING

    for pname, prov in kw.providers.items():
        if prov.base_url and prov.kind != "openai_compatible":
            issues.append(issue("base_url_kind", f"providers.{pname}.base_url", "only an openai_compatible provider has a base_url (its other kinds are reached through LiteLLM's own route)"))
        if prov.creators and prov.kind != "harness":
            issues.append(issue("creators_not_harness", f"providers.{pname}.creators", "only a harness provider names the creators it can run"))
        for cap in prov.tools:
            where = f"providers.{pname}.tools.{cap}"
            if prov.kind != "harness":
                issues.append(issue("tools_not_harness", where, "only a harness provider has a tool map"))
            elif cap not in TOOLING:
                issues.append(issue("not_tooling", where, f"{cap!r} is not a tooling capability ({', '.join(TOOLING)}); a tool map covers only those"))
            else:
                check_caps([cap], where)
    for mid, m in kw.models.items():
        where = f"models.{mid}"
        if not _is_model_id(mid):
            issues.append(issue("model_id", where, "a model_id is <creator>/<name>, lower case"))
        elif mid.split("/", 1)[0] != m.creator.lower():
            issues.append(issue("model_id", where, f"model_id must start with its creator, {m.creator.lower()}/"))
        check_caps(m.capabilities, f"{where}.capabilities")
        check_basis(m.capabilities, m.capability_basis, where)
        check_tier(m.tier, f"{where}.tier")
    seen: set[tuple[str, str, str | None]] = set()
    for i, r in enumerate(kw.routes):
        where = f"routes[{i}]"
        if r.provider not in kw.providers:
            issues.append(issue("unknown_provider", where, f"provider {r.provider!r} is not in providers"))
        if r.model_id is not None and r.model_id not in kw.models:
            issues.append(issue("unknown_model", where, f"model_id {r.model_id!r} is not in models"))
        if r.model_id is None and not r.creator:
            issues.append(issue("no_identity", where, "a route without model_id must name its creator"))
        if r.model_id is None and not r.alias:
            issues.append(issue("no_identity", where, "a route without model_id is a mutable alias or an unknown model: set alias: true"))
        if r.model_id is not None and r.creator and kw.models.get(r.model_id) and kw.models[r.model_id].creator != r.creator:
            issues.append(issue("creator_mismatch", where, f"creator {r.creator!r} differs from the model's {kw.models[r.model_id].creator!r}"))
        if r.supported and r.adapter not in adapters:
            issues.append(issue("unknown_adapter", where, f"supported route names adapter {r.adapter!r}, not in this runtime ({', '.join(sorted(adapters))}); mark it supported: false"))
        if r.supported and r.invocation is None and kw.providers.get(r.provider) and kw.providers[r.provider].kind != "harness":
            issues.append(issue("no_invocation", where, "only a harness route may leave invocation empty (the harness's default model)"))
        check_caps(r.capabilities, f"{where}.capabilities")
        check_basis(r.capabilities, r.capability_basis, where)
        check_tier(r.tier, f"{where}.tier")
        key = (r.provider, r.adapter, r.invocation)
        if key in seen:
            issues.append(issue("duplicate_route", where, f"another route has provider {r.provider}, adapter {r.adapter}, invocation {r.invocation}"))
        seen.add(key)
    return kw, issues


def _is_model_id(s: str) -> bool:
    import re

    return re.fullmatch(MODEL_ID, s) is not None


def load(vocab: Vocabulary, path: Path | None = None) -> KnownWorkers:
    """The shipped known-workers data, validated; ``KnownWorkersError`` lists every problem."""
    from .adapters import ADAPTERS

    path = path or default_path()
    try:
        raw: Any = load_yaml(path)
    except YamlError as e:
        raise KnownWorkersError([Issue(code="known_workers.yaml", where=str(path), message=str(e))]) from e
    kw, issues = validate(raw, vocab, set(ADAPTERS), source=path.name)
    if issues or kw is None:
        raise KnownWorkersError(issues)
    return kw


LOCAL_FILE = "known-workers.local.yaml"


def merge_overlay(vocab: Vocabulary, extra: Any, path: Path | None = None, *, where: str = LOCAL_FILE) -> KnownWorkers:
    """The shipped data plus an overlay document (already parsed), validated; ``KnownWorkersError`` lists every problem.

    The one validator for overlays (Decisions 0111, 0120): the loader, ``workers check-overlay`` and ``workers assess`` all call it.
    """
    from .adapters import ADAPTERS

    path = path or default_path()

    def problem(code: str, message: str) -> KnownWorkersError:
        return KnownWorkersError([Issue(code=f"known_workers.{code}", where=where, message=message)])

    if not isinstance(extra, dict) or extra.get("format") != FORMAT:
        raise problem("format", f"expected a mapping with format {FORMAT}")
    if set(extra) - {"format", "models", "routes"}:
        raise problem("sections", "an overlay may hold only models and routes")
    raw: Any = load_yaml(path)
    for mid, m in (extra.get("models") or {}).items():
        if mid in raw.get("models", {}):
            raise problem("replaces_shipped", f"{mid} is in the shipped data; an overlay adds models, it never edits one")
        raw.setdefault("models", {})[mid] = m
    for i, r in enumerate(extra.get("routes") or []):
        if isinstance(r, dict) and "verified" in r:
            raise problem("verified", f"routes[{i}] carries verified; only a live check sets it")
        raw.setdefault("routes", []).append(r)
    merged, issues = validate(raw, vocab, set(ADAPTERS), source=where)
    if issues or merged is None:
        raise KnownWorkersError(issues)
    # A model the overlay adds must show a basis for each capability it claims (as a research proposal does).
    _, basis_issues = validate({**raw, "models": {m: raw["models"][m] for m in (extra.get("models") or {})}, "routes": [], "providers": raw.get("providers", {})},
                               vocab, set(ADAPTERS), source=where, require_basis=True)
    if basis_issues:
        raise KnownWorkersError(basis_issues)
    return merged


def load_with_overlay(vocab: Vocabulary, home: Path, path: Path | None = None) -> KnownWorkers:
    """The shipped data plus the owner's machine-local overlay ``<home>/known-workers.local.yaml`` (Decision 0111).

    The overlay (the result of an owner-run assessment) adds ``models`` and
    ``routes`` only: it never replaces or edits a shipped model, never carries
    ``verified``, and every model it adds needs a basis for each capability.
    """
    shipped = load(vocab, path)
    overlay_path = Path(home) / LOCAL_FILE
    if not overlay_path.is_file():
        return shipped
    try:
        extra: Any = load_yaml(overlay_path)
    except YamlError as e:
        raise KnownWorkersError([Issue(code="known_workers.yaml", where=LOCAL_FILE, message=str(e))]) from e
    return merge_overlay(vocab, extra, path)
