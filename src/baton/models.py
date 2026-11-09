"""Pydantic models for Baton's formats.

The recipe models *are* the definition of ``baton-recipe/1``: the published
JSON Schema (``formats/``) is generated from them (§15.3). Rules a schema
cannot express (cross-references, files, vocabulary, neutrality) live in
``recipe.py``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Field, PrivateAttr, Tag, field_validator, model_validator

STEP_ID = r"^[a-z][a-z0-9_]*$"
RECIPE_ID = r"^[a-z][a-z0-9-]*$"

Tier = str  # checked against the vocabulary's tiers, not a fixed enum
Level = str  # checked against the recipe's declared complexity levels
Severity = Literal["critical", "high", "medium", "low"]
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------
# Issues (validation results)
# --------------------------------------------------------------------------


class Issue(BaseModel):
    """One validation problem. ``code`` is stable and machine-checkable."""

    code: str
    where: str = ""
    message: str
    severity: Literal["error", "warning"] = "error"

    def __str__(self) -> str:
        prefix = "ERROR" if self.severity == "error" else "WARNING"
        loc = f" {self.where}" if self.where else ""
        return f"{prefix}{loc}: [{self.code}] {self.message}"


# --------------------------------------------------------------------------
# Recipe format: baton-recipe/1
# --------------------------------------------------------------------------


class Requires(_Strict):
    capabilities: list[str] = Field(default_factory=list)
    tier: Tier | None = None
    min_context_tokens: int | None = Field(default=None, ge=1)


class Independence(_Strict):
    from_step: str
    level: Literal["different_profile", "different_model", "different_vendor"]


class Input(_Strict):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    from_: str = Field(alias="from")
    required: bool = True


class Publish(_Strict):
    to: str


class Artifact(_Strict):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    required: bool = True
    media_type: str | None = None
    publish: Publish | None = None


class Protect(_Strict):
    paths: list[str] = Field(min_length=1)
    on_violation: Literal["warn", "fail"] = "warn"


class _GateBase(_Strict):
    advisory: bool = False
    applies_to: list[Level] | None = None


class SchemaGate(_GateBase):
    type: Literal["schema"]


class ScriptGate(_GateBase):
    type: Literal["script"]
    run: str = Field(min_length=1)
    cwd: str | None = None
    timeout_s: int | None = Field(default=None, ge=1)


class ReviewGate(_GateBase):
    type: Literal["review"]
    reviewer_requires: Requires
    rubric: str
    independence: Independence | None = None
    block_on: list[Severity] | None = None


class FindingsGate(_GateBase):
    type: Literal["findings"]
    block_on: list[Severity] | None = None


class HumanGateLabels(_Strict):
    """A recipe's own plain-language labels for a human gate's options (§13.8)."""

    approve: str | None = Field(default=None, min_length=1)
    reject: str | None = Field(default=None, min_length=1)


class HumanGate(_GateBase):
    type: Literal["human"]
    prompt: str = Field(min_length=1)
    labels: HumanGateLabels | None = None


Gate = Annotated[
    Union[SchemaGate, ScriptGate, ReviewGate, FindingsGate, HumanGate],
    Field(discriminator="type"),
]
GATE_TYPES: tuple[str, ...] = ("schema", "script", "review", "findings", "human")
IMPLICIT_GATE_TYPES: tuple[str, ...] = ("provenance", "protected")


class Step(_Strict):
    """A leaf step: one unit of work done by one worker per attempt."""

    id: str = Field(pattern=STEP_ID)
    title: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    applies_to: list[Level] | None = None
    requires: Requires
    prompt: str
    inputs: list[Input] = Field(default_factory=list)
    output_schema: str | None = None  # recipe-relative path, or "baton:findings"
    artifacts: list[Artifact] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    workspace: Literal["none", "read", "write"] = "none"
    protect: list[str] | Protect | None = None
    effort: Literal["S", "M", "L"] | None = None
    effort_from: str | None = None
    independence: Independence | None = None
    doc_template: str | None = None

    @property
    def is_group(self) -> bool:
        return False

    def protect_paths(self) -> list[str]:
        if self.protect is None:
            return []
        return list(self.protect) if isinstance(self.protect, list) else list(self.protect.paths)


class Group(_Strict):
    """A step containing steps: a sub-process (§5.4)."""

    id: str = Field(pattern=STEP_ID)
    title: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    applies_to: list[Level] | None = None
    foreach: str | None = None
    foreach_if_source_skipped: Literal["once", "skip"] | None = None
    concurrency: int = Field(default=1, ge=1)
    repeat_until: str | None = None
    repeat_from: str | None = None
    max_iterations: int | None = None  # range checked by the loader for a specific error
    steps: list[AnyStep] = Field(min_length=1)

    @property
    def is_group(self) -> bool:
        return True


def _step_kind(value: Any) -> str | None:
    if isinstance(value, dict):
        return "group" if "steps" in value else "step"
    if isinstance(value, Group):
        return "group"
    if isinstance(value, Step):
        return "step"
    return None


AnyStep = Annotated[
    Union[Annotated[Step, Tag("step")], Annotated[Group, Tag("group")]],
    Discriminator(_step_kind),
]
Group.model_rebuild()


class RunInputs(_Strict):
    schema_: str = Field(alias="schema")


class Defaults(_Strict):
    max_attempts: int = Field(default=3, ge=1)


class Complexity(_Strict):
    levels: list[str] = Field(min_length=1)
    triage_step: str


class SmeRequirements(_Strict):
    project: Requires | None = None
    platform: Requires | None = None
    process: Requires | None = None


class ScopeNotFor(_Strict):
    """A near miss: a job this recipe is not for, and the recipe that is (§5.1)."""

    job: str = Field(min_length=1)
    use: str | None = Field(default=None, pattern=RECIPE_ID)


class Scope(_Strict):
    """What a recipe covers, in the owner's terms. Read by discovery, never by a run (§5.1; Decision 0105)."""

    covers: list[str] = Field(min_length=1)
    not_for: list[ScopeNotFor] = Field(default_factory=list)
    varies_by: list[str] = Field(default_factory=list)


class Parent(_Strict):
    """The recipe this one was built from (§5.1; Decision 0103). No runtime effect."""

    id: str = Field(pattern=RECIPE_ID)
    version: int = Field(ge=1)


class Recipe(_Strict):
    id: str = Field(pattern=RECIPE_ID)
    version: int = Field(ge=1)
    format: str
    capabilities_vocab: str
    description: str | None = None
    scope: Scope | None = None
    parent: Parent | None = None  # null = built from scratch; absent = predates the field (see ``provenance``)
    run_inputs: RunInputs | None = None
    defaults: Defaults = Field(default_factory=Defaults)
    complexity: Complexity | None = None
    sme: SmeRequirements | None = None
    steps: list[AnyStep] = Field(min_length=1)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def provenance(self) -> Literal["parent", "scratch", "unrecorded"]:
        """Whether the recipe names a parent, was built from nothing (``parent: null``), or predates the field."""
        if "parent" not in self.model_fields_set:
            return "unrecorded"
        return "scratch" if self.parent is None else "parent"


# --------------------------------------------------------------------------
# Crosswalks: baton-crosswalk/1 (§11.3)
# --------------------------------------------------------------------------

CROSSWALK_FORMATS: tuple[str, ...] = ("baton-crosswalk/1",)


class CrosswalkMap(_Strict):
    """One rule: files matching ``match`` hold a step's artifact, output or gate evidence in the prior process."""

    match: str = Field(min_length=1)  # glob relative to the project root; each * / ** is a capture
    step: str = Field(pattern=r"^[a-z][a-z0-9-]*@[0-9]+/[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)?$")  # qualified step id (§5.8)
    artifact: str | None = None
    output: bool = False
    gate: int | None = Field(default=None, ge=0)
    work_item: str = Field(min_length=1)  # template over the captures, e.g. "{1}"
    item: str | None = None  # in a foreach group: the item's key in the prior process


class Crosswalk(_Strict):
    format: str
    id: str = Field(pattern=RECIPE_ID)
    prior_process: str = Field(min_length=1)
    description: str | None = None
    maps: list[CrosswalkMap] = Field(min_length=1)


# --------------------------------------------------------------------------
# Findings: the runtime-owned schema "baton:findings" (§9.2)
# --------------------------------------------------------------------------


class Finding(_Strict):
    id: str = Field(min_length=1)
    severity: Severity
    location: str = ""
    title: str = Field(min_length=1)
    detail: str = ""
    suggested_fix: str = ""


class Coverage(_Strict):
    complete: bool
    notes: str = ""


class Findings(_Strict):
    findings: list[Finding]
    coverage: Coverage


# --------------------------------------------------------------------------
# Results: what a worker returns (§7.2, baton-packet/1)
# --------------------------------------------------------------------------


class ResultArtifact(_Strict):
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)  # relative to the result directory


class ResultDisposition(_Strict):
    """A worker's claim about an earlier finding (§9.2, §18 #12): provisional until a review confirms it."""

    step: str = Field(min_length=1)  # the step (id or path) whose review recorded the finding
    finding: str = Field(min_length=1)
    disposition: Literal["fixed", "rejected"]
    evidence: str = ""


class QuestionOption(_Strict):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class Question(_Strict):
    """One structured question for the owner (§7.2): material for the Director's conversation."""

    id: str = Field(min_length=1)
    ask: str = Field(min_length=1)
    why: str = ""
    best_guess: str | None = None
    options: list[QuestionOption] = Field(default_factory=list)
    multi_select: bool = False
    priority: Literal["needed", "helpful"] = "needed"


def normalize_questions(raw: Any) -> list[dict[str, Any]]:
    """Normalize ``questions_for_human`` (§7.2): a bare string becomes ``{id: q<n>, ask, why: ""}``.

    Raises ``ValueError`` for an entry that is neither a string nor a valid question, or for
    duplicated ids. Also used to read questions recorded before Phase 17 (plain strings).
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("questions_for_human must be a list")
    out: list[dict[str, Any]] = []
    for n, q in enumerate(raw, start=1):
        if isinstance(q, str):
            if not q.strip():
                raise ValueError(f"question {n} is an empty string")
            out.append({"id": f"q{n}", "ask": q, "why": "", "options": [], "multi_select": False, "priority": "needed"})
        elif isinstance(q, dict):
            out.append(Question.model_validate(q).model_dump(exclude_none=True))
        else:
            raise ValueError(f"question {n} is neither a string nor a question object")
    ids = [q["id"] for q in out]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"question ids are not unique: {', '.join(dupes)}")
    for q in out:
        opt_ids = [o["id"] for o in q.get("options", [])]
        if len(set(opt_ids)) != len(opt_ids):
            raise ValueError(f"question {q['id']}: option ids are not unique")
    return out


def recorded_questions(raw: Any) -> list[dict[str, Any]]:
    """Questions as recorded in an event, normalized; tolerant of anything malformed (never raises)."""
    try:
        return normalize_questions(raw)
    except (ValueError, TypeError):
        return [{"id": f"q{n}", "ask": str(q), "why": ""} for n, q in enumerate(raw or [], start=1)]


class Result(_Strict):
    protocol: str
    packet_sha256: str
    status: Literal["completed", "blocked", "failed"]
    output: Any = None
    artifacts: list[ResultArtifact] = Field(default_factory=list)
    notes: str = ""
    questions_for_human: list[dict[str, Any]] = Field(default_factory=list)
    process_feedback: list[Any] = Field(default_factory=list)
    dispositions: list[ResultDisposition] = Field(default_factory=list)

    @field_validator("questions_for_human", mode="before")
    @classmethod
    def _normalize_questions(cls, v: Any) -> list[dict[str, Any]]:
        return normalize_questions(v)


# --------------------------------------------------------------------------
# Worker profiles (§6.1) and routing preferences (§8.4)
# --------------------------------------------------------------------------


class ProfileAuth(_Strict):
    mode: Literal["api_key", "cli_login", "none"]
    env: dict[str, str] = Field(default_factory=dict)
    config_home: str | None = None


class ProfilePath(_Strict):
    search: list[str] = Field(default_factory=list)
    prepend: list[str] = Field(default_factory=list)


class ProfileArgs(_Strict):
    """Adapter args per workspace mode (§6.1). ``None`` keeps the adapter's built-in default for that mode."""

    write: list[str] | None = None
    read: list[str] | None = None
    none: list[str] | None = None


#: A canonical model identity (0075): ``<creator>/<name>``, lower case.
MODEL_ID = r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:@+-]*$"


class WorkerProfile(_Strict):
    """One worker (§6.1). Identity and route are separate fields (Decision 0075):

    ``creator`` made the model (``different_vendor``); ``model_id`` is its
    canonical identity across routes (``different_model``; absent = unknown);
    ``provider`` is the access provider; ``model`` is the invocation
    identifier the adapter passes on; ``resource`` the machine resource.
    ``vendor`` is read as a legacy alias for ``creator``.
    """

    adapter: str
    creator: str
    model_id: str | None = Field(default=None, pattern=MODEL_ID)
    provider: str | None = None
    resource: str | None = None
    model: str | None = None
    person: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    tier: Tier | None = None
    context_tokens: int | None = Field(default=None, ge=1)
    auth: ProfileAuth = Field(default_factory=lambda: ProfileAuth(mode="none"))
    env_mode: Literal["clean", "allowlist", "inherit"] | None = None
    env_allow: list[str] = Field(default_factory=list)
    env_deny: list[str] = Field(default_factory=list)
    executable: str | None = None
    path: ProfilePath | None = None
    args: ProfileArgs | None = None
    isolation: Literal["none", "user", "container"] = "none"
    command: str | None = None  # for the `command` adapter
    #: Non-secret adapter options (e.g. ``base_url``, ``temperature`` for ``litellm_api``).
    options: dict[str, Any] = Field(default_factory=dict)
    #: Set only by ``baton workers setup`` (§6.4, 0079): ``by``, ``known_workers_sha256``,
    #: ``content_sha256``, ``availability``, ``verified``. Not part of the profile's hash.
    generated: dict[str, Any] | None = None
    #: Capability states recorded on this machine (0084), attached by ``Project.profiles``:
    #: capability -> ``CapabilityState``. Never read from or written to a profile file, never hashed.
    _capability_states: dict[str, Any] = PrivateAttr(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _legacy_vendor(cls, data: Any) -> Any:
        """``vendor`` (the field before 0075) is ``creator``; both, differing, is an error."""
        if isinstance(data, dict) and "vendor" in data:
            data = dict(data)
            vendor = data.pop("vendor")
            if "creator" in data and data["creator"] != vendor:
                raise ValueError(f"vendor {vendor!r} and creator {data['creator']!r} differ; vendor is the old name for creator, give only creator")
            data.setdefault("creator", vendor)
        return data

    @model_validator(mode="after")
    def _model_id_matches_creator(self) -> "WorkerProfile":
        if self.model_id is not None and self.model_id.split("/", 1)[0] != self.creator.lower():
            raise ValueError(f"model_id {self.model_id!r} must start with its creator, {self.creator.lower()}/")
        return self

    @property
    def vendor(self) -> str:
        """The legacy name for ``creator``."""
        return self.creator

    def capability_state(self, capability: str) -> str:
        """``likely`` (the default for a claimed capability), ``verified`` or ``absent`` (0084)."""
        st = self._capability_states.get(capability)
        return st.state if st is not None else "likely"

    def capability_record(self, capability: str) -> Any:
        return self._capability_states.get(capability)

    def with_capability_states(self, states: dict[str, Any]) -> "WorkerProfile":
        """A copy carrying the recorded states of the capabilities it claims."""
        out = self.model_copy()
        out._capability_states = {c: s for c, s in states.items() if c in self.capabilities}
        return out

    def canonical_model(self) -> str | None:
        """The canonical model identity: ``model_id``; for a ``manual`` profile, ``human/<person>`` (0075)."""
        if self.model_id is not None:
            return self.model_id
        if self.adapter == "manual" and self.person:
            return f"{self.creator.lower()}/{self.person.lower()}"
        return None


class PreferOrder(_Strict):
    by_step: dict[str, list[str]] = Field(default_factory=dict)
    by_capability: dict[str, list[str]] = Field(default_factory=dict)


class Preferences(_Strict):
    """``.baton/preferences.yaml``: reorder or exclude eligible profiles; never add one (§8.4)."""

    prefer: PreferOrder = Field(default_factory=PreferOrder)
    exclude: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Plan: the structured per-level step and gate table (§5.3, §15.3)
# --------------------------------------------------------------------------


class PlanGate(BaseModel):
    type: str
    blocking: bool
    included: bool
    implicit: bool = False
    note: str = ""


class PlanStep(BaseModel):
    path: str
    title: str
    kind: Literal["step", "group"]
    depth: int
    included: bool
    reason: str = ""  # why skipped
    requires: Requires | None = None
    workspace: str = "none"
    gates: list[PlanGate] = Field(default_factory=list)
    group: dict[str, Any] | None = None  # foreach / repeat details for groups


class PlanLevel(BaseModel):
    level: str | None  # None when the recipe declares no complexity scale
    steps: list[PlanStep]


class Plan(BaseModel):
    recipe: str
    format: str
    capabilities_vocab: str
    recipe_sha256: str
    description: str | None = None
    levels: list[PlanLevel]
    warnings: list[Issue] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Events: baton-events/1 (§8.2). One envelope for run and project logs.
# --------------------------------------------------------------------------

# Format versions live in versions.FAMILIES (§14.2).

#: Every event type, by area (§8.2). The single list.
EVENT_TYPES_BY_AREA: dict[str, tuple[str, ...]] = {
    "run": ("run_started", "run_completed", "run_abandoned"),
    "leases": ("lease_claimed", "lease_renewed", "lease_taken_over", "lease_released"),
    "steps": (
        "step_ready", "dispatch_queued", "dispatch_dequeued", "worker_selected", "packet_built", "dispatched", "step_running",
        "result_submitted", "verification_started", "result_rejected", "gate_passed",
        "gate_failed", "human_gate_opened", "step_passed", "step_escalated", "step_abandoned",
        "step_timed_out", "attempt_orphaned", "failure_classified", "deadline_extended",
    ),
    "tailoring": ("complexity_set", "step_skipped", "step_unskipped", "retriage_requested", "retriage_applied"),
    "groups": ("group_expanded", "iteration_started", "iteration_limit_reached"),
    "corrections": ("step_revised", "step_stale"),
    "reviews": ("findings_recorded", "finding_dispositioned", "gate_waived", "protected_path_modified"),
    "human": ("human_decision", "human_revision_ingested"),
    "deliverables": ("artifact_published", "drift_detected"),
    "adoption": ("situation_detected", "research_recorded", "step_imported", "baseline_established"),
    "framing": ("framing_selected", "framing_started_later"),
    "experts": ("sme_requested", "sme_answered", "sme_promoted"),
    "machinery": (
        "completion_hook_fired", "completion_hook_failed", "checkpoint_committed",
        "permission_used", "permission_requested", "migrated",
    ),
    "project_log": (
        "platform_fact_recorded", "platform_incident_opened", "platform_incident_resolved",
        "process_feedback", "step_skip_recorded", "note_recorded", "capability_observed",
    ),
}
EVENT_TYPES: frozenset[str] = frozenset(t for ts in EVENT_TYPES_BY_AREA.values() for t in ts)
#: Types a run log may hold: everything except project-log records.
RUN_EVENT_TYPES: frozenset[str] = EVENT_TYPES - frozenset(EVENT_TYPES_BY_AREA["project_log"])
#: Types the project log may hold: its own records, expert consultations outside
#: a run, machinery, and owner decisions on project actions (an ``ask`` permission, §13.7).
PROJECT_EVENT_TYPES: frozenset[str] = frozenset(
    EVENT_TYPES_BY_AREA["project_log"] + EVENT_TYPES_BY_AREA["experts"] + EVENT_TYPES_BY_AREA["machinery"] + ("human_decision",)
)

ACTOR = r"^(runtime|human|worker|director)(:[^\s]+)?$"
SHA256_HEX = r"^[0-9a-f]{64}$"


class Event(_Strict):
    """One line of an event log.

    ``sha256`` is the SHA-256 of the event's canonical JSON *without* the
    ``sha256`` key (sorted keys, no whitespace, UTF-8). ``prev_sha256`` is
    the previous event's ``sha256`` (``null`` on the first event). Together
    they make any edit, deletion, insertion or reordering detectable,
    including an edit to the last event.
    """

    format: str
    seq: int = Field(ge=1)
    ts: str
    run_id: str | None  # None in the project log
    step_path: str | None = None
    attempt: int | None = Field(default=None, ge=1)
    type: str
    actor: str = Field(pattern=ACTOR)
    data: dict[str, Any] = Field(default_factory=dict)
    prev_sha256: str | None = Field(default=None, pattern=SHA256_HEX)
    sha256: str = Field(pattern=SHA256_HEX)


class StepStatus(BaseModel):
    state: str
    attempt: int
    last_seq: int


class RunStatus(BaseModel):
    """Process state of one run, derived from its events (§8.3).

    Only steps that have had events are listed; any other step of the recipe
    is ``blocked_on_deps``.
    """

    run_id: str
    state: str
    last_seq: int
    last_sha256: str | None
    steps: dict[str, StepStatus]


# --------------------------------------------------------------------------
# Project configuration: .baton/project.yaml (§4.3, §10.4). Non-secret; the
# loader rejects any ``secret:`` reference (§15.2). Later layers add their
# keys here (hooks, permissions, limits, sme, effort bands).
# --------------------------------------------------------------------------


class LeaseConfig(_Strict):
    minutes: int = Field(default=60, ge=1)  # §18 #5: 1 h, renewed on activity


class CheckpointConfig(_Strict):
    commit: bool = True  # §18 #6: on, to the current branch


class LfsConfig(_Strict):
    threshold_mb: float = Field(default=5, gt=0)  # §18 #7: optional, 5 MB


EFFORTS: tuple[str, ...] = ("S", "M", "L")


def duration_seconds(value: str | int | float) -> float:
    """``"45m"``, ``"2h"``, ``"90s"`` or a bare number of seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    import re

    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(s|m|h)?\s*$", value)
    if not m:
        raise ValueError(f"not a duration: {value!r} (use e.g. 90s, 45m, 2h)")
    return float(m.group(1)) * {"s": 1, "m": 60, "h": 3600, None: 1}[m.group(2)]


class EffortConfig(_Strict):
    """Effort bands (§8.7; §18 #9): the time a worker gets per declared effort."""

    bands: dict[Literal["S", "M", "L"], str | float] = Field(default_factory=dict, validate_default=True)
    extend_once: bool = True
    default: Literal["S", "M", "L"] = "M"  # steps that declare no effort

    @field_validator("bands")
    @classmethod
    def _bands(cls, v: dict[str, str | float]) -> dict[str, str | float]:
        out: dict[str, str | float] = {"S": "45m", "M": "2h", "L": "4h", **v}
        for k, d in out.items():
            if duration_seconds(d) <= 0:
                raise ValueError(f"effort band {k} must be positive")
        return out

    def seconds(self, effort: str) -> float:
        return duration_seconds(self.bands[effort])  # type: ignore[index]


class HooksConfig(_Strict):
    """Completion hooks (§8.7). Shell command lines; empty means not configured."""

    on_complete: str = ""
    on_needs_human: str = ""
    on_platform_failure: str = ""


class LimitsConfig(_Strict):
    active_runs: int | None = Field(default=None, ge=1)  # §8.9: `start` refuses beyond this many active runs


Rule = Literal["allow", "ask", "deny"]

#: Paths a "docs only" change may touch (§13.7). ``.baton/project/**`` holds project
#: checkpoints' records, which a push of only Baton's own records also carries.
DEFAULT_DOCS_ONLY_GLOBS: tuple[str, ...] = (
    "docs/**", "**/*.md", ".baton/runs/**", ".baton/project/**", ".baton/platform/**", ".baton/process/**",
)


class PushRules(_Strict):
    """``permissions.push`` (§13.7): one rule per kind of change being pushed."""

    docs_only: Rule = "allow"        # every changed path matches docs_only_globs
    after_verified: Rule = "allow"   # every other commit is a checkpoint or a passed step's commit_sha
    other: Rule = "ask"


class PermissionsConfig(_Strict):
    """Action permissions (§13.7): what the runtime and the Director may do to the repo and its remotes."""

    push: PushRules = Field(default_factory=PushRules)
    tag: Rule = "ask"
    force_push: Rule = "deny"
    merge: Rule = "deny"
    deploy: Rule = "deny"


class SmeSubjectConfig(_Strict):
    """``project.yaml`` ``sme.<subject>`` (§12.1): profiles tried first for this subject."""

    preferred_profiles: list[str] = Field(default_factory=list)


class ProjectConfig(_Strict):
    paths: dict[str, str] = Field(default_factory=dict)
    project: dict[str, Any] = Field(default_factory=dict)
    run_slug: str = "{{ run.inputs.title | slugify }}"
    leases: LeaseConfig = Field(default_factory=LeaseConfig)
    checkpoints: CheckpointConfig = Field(default_factory=CheckpointConfig)
    lfs: LfsConfig = Field(default_factory=LfsConfig)
    contacts: dict[str, str] = Field(default_factory=dict)
    effort: EffortConfig = Field(default_factory=EffortConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    sme: dict[Literal["project", "platform", "process"], SmeSubjectConfig] = Field(default_factory=dict)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    docs_only_globs: list[str] = Field(default_factory=lambda: list(DEFAULT_DOCS_ONLY_GLOBS))
