"""Known-workers data (``defaults/known-workers.yaml``, ``baton-known-workers/1``; Decision 0080).

Shared, read-only knowledge about models and the routes that reach them,
shipped with the runtime beside the adapters. The worker resource manager
(§6.4) turns it into profiles; nothing else reads it, and independence
(§8.4) never does: it uses the identity recorded at dispatch.

Three sections:

* ``models``, keyed by ``model_id`` (0075): creator, intrinsic capabilities,
  tier, context size, category, sources and research date.
* ``providers``: how access is obtained (``direct_api``, ``intermediary``,
  ``harness``, ``local``), with sources.
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


class KnownModel(_Strict):
    creator: str
    category: str = "llm"
    capabilities: list[str] = Field(default_factory=list)
    tier: str | None = None
    context_tokens: int | None = Field(default=None, ge=1)
    sources: list[Source] = Field(min_length=1)
    researched: dt.date
    retired: bool = False


class KnownProvider(_Strict):
    kind: Literal["direct_api", "intermediary", "harness", "local"]
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


def validate(raw: object, vocab: Vocabulary, adapters: set[str], source: str = FILE) -> tuple[KnownWorkers | None, list[Issue]]:
    """Schema, vocabulary, adapters, identity consistency and provenance (0080)."""
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

    def check_tier(tier: str | None, where: str) -> None:
        if tier is not None and tier not in vocab.tiers:
            issues.append(issue("unknown_tier", where, f"tier {tier!r} is not in {vocab.id} ({', '.join(vocab.tiers)})"))

    for mid, m in kw.models.items():
        where = f"models.{mid}"
        if not _is_model_id(mid):
            issues.append(issue("model_id", where, "a model_id is <creator>/<name>, lower case"))
        elif mid.split("/", 1)[0] != m.creator.lower():
            issues.append(issue("model_id", where, f"model_id must start with its creator, {m.creator.lower()}/"))
        check_caps(m.capabilities, f"{where}.capabilities")
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
