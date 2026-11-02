"""The packet builder (§7.1, §8.6): the critical module.

The runtime, not the Director, decides what a worker receives. ``build_packet``
resolves every declared input from the run's record, refuses with
``HandoffError`` (listing *all* missing inputs, writing nothing) when a
required one is unresolvable, and writes a read-only, content-hashed packet::

    runs/<run_id>/steps/<step_path>/attempt-<n>/packet/
        manifest.json  INSTRUCTIONS.md  output_schema.json  inputs/<name>.<ext>
    runs/<run_id>/steps/<step_path>/attempt-<n>/result/       (empty, for the worker)

**Provenance.** Step outputs and artifacts are resolved only from hashes the
runtime recorded in ``step_passed`` (written by intake) and read from the run's
CAS, never from published copies or from files a Director placed anywhere.

**packet_sha256** (``packet_digest``)::

    sha256( "baton-packet/1\\n"
            + canonical_json(manifest with packet_sha256 = null) + "\\n"
            + for each packet file except manifest.json, sorted by POSIX path:
                  "<path>\\0<sha256 of its bytes>\\n" )

``canonical_json`` is the event-log encoding (sorted keys, no whitespace,
UTF-8). The manifest carries no clock reading other than ``deadline``, which
the caller supplies, so the same state and profile give the same hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import refs, versions
from .data import read_text
from .models import Event, FindingsGate, Group, HumanGate, ReviewGate, ScriptGate, Step, WorkerProfile
from .recipe import FINDINGS_SCHEMA_REF, LoadedRecipe
from .routing import requirement_gaps
from .state import SATISFIES_DEPS
from .store import RunLog, Store, StoreError, canonical_json, ensure_dir

PROTOCOL = "baton-packet/1"
#: JSON inputs up to this size are inlined in INSTRUCTIONS.md; larger ones are referenced by path.
INLINE_LIMIT = 16 * 1024
JSON_DUMP = dict(indent=2, sort_keys=True, ensure_ascii=False)


class HandoffError(Exception):
    """Required inputs could not be resolved. ``missing`` lists every one, as (name, ref, reason)."""

    def __init__(self, step_path: str, missing: list[tuple[str, str, str]]):
        self.step_path = step_path
        self.missing = missing
        lines = "; ".join(f"{n} (from {r}): {why}" for n, r, why in missing)
        super().__init__(f"{step_path}: cannot build packet; missing required inputs: {lines}")


class EngineError(Exception):
    """A request the runtime refuses. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Run context and record
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    """One run, with the recipe it is pinned to and the project's variables.

    ``project`` holds the non-secret project configuration used for template
    variables (``project.*``, ``paths.*``); ``project.yaml`` loading arrives with
    the core CLI (Phase 4).
    """

    store: Store
    run_id: str
    recipe: LoadedRecipe
    project: dict[str, Any] = field(default_factory=dict)

    @property
    def log(self) -> RunLog:
        return self.store.run(self.run_id)

    @property
    def run_dir(self) -> Path:
        return self.store.run_dir(self.run_id)

    def attempt_dir(self, step_path: str, attempt: int) -> Path:
        return self.run_dir / "steps" / PurePosixPath(step_path) / f"attempt-{attempt}"

    def record(self) -> RunRecord:
        return RunRecord(self.log.events())


class RunRecord:
    """Queries over a run's events. The events are the only source of truth."""

    def __init__(self, events: list[Event]):
        self.events = events

    @property
    def started(self) -> dict[str, Any]:
        return self.events[0].data if self.events and self.events[0].type == "run_started" else {}

    def level(self) -> str | None:
        """The complexity level, once set (§5.5)."""
        level = None
        for ev in self.events:
            if ev.type in ("complexity_set", "retriage_applied") and "level" in ev.data:
                level = ev.data["level"]
        return level

    def last(self, etype: str, step_path: str | None = None, attempt: int | None = None) -> Event | None:
        for ev in reversed(self.events):
            if ev.type == etype and (step_path is None or ev.step_path == step_path) and (attempt is None or ev.attempt == attempt):
                return ev
        return None

    def attempt_events(self, step_path: str, attempt: int) -> list[Event]:
        return [e for e in self.events if e.step_path == step_path and e.attempt == attempt]

    def registered(self, step_path: str) -> dict[str, Any] | None:
        """Output and artifact hashes intake recorded for the step's current result."""
        for ev in reversed(self.events):
            if ev.step_path != step_path:
                continue
            if ev.type in ("step_passed", "step_imported"):
                return ev.data
            if ev.type in ("step_revised", "step_stale"):
                return None
        return None

    def decision(self, decision_id: str) -> Event | None:
        for ev in reversed(self.events):
            if ev.type == "human_decision" and ev.data.get("decision_id") == decision_id:
                return ev
        return None


def node_for(recipe: LoadedRecipe, step_path: str) -> Step | Group | None:
    """The recipe node for a top-level step path. Paths inside groups arrive with Phase 8."""
    if "/" in step_path:
        return None
    return next((n for n in recipe.recipe.steps if n.id == step_path), None)


def gate_included(gate: Any, level: str | None) -> bool:
    """A gate with ``applies_to`` runs only at those levels; before triage sets a level, it runs."""
    return gate.applies_to is None or level is None or level in gate.applies_to


def profile_sha256(profile: WorkerProfile) -> str:
    """Hash of the profile's non-secret fields: ``auth.env`` keeps variable names only."""
    body = profile.model_dump(mode="json", exclude_none=True)
    auth = body.get("auth") or {}
    if "env" in auth:
        auth["env"] = sorted(auth["env"])
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


@dataclass
class _Resolved:
    name: str
    ref: str
    kind: str  # "json" | "file"
    filename: str
    content: bytes
    media_type: str | None = None
    inline: Any = None  # the JSON value, when kind == "json"


class _Unresolvable(Exception):
    pass


class _NotApplicable(Exception):
    pass


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, **JSON_DUMP) + "\n").encode("utf-8")


def _walk(value: Any, path: tuple[str, ...], ref: str) -> Any:
    for seg in path:
        if isinstance(value, dict) and seg in value:
            value = value[seg]
        elif isinstance(value, list) and seg.isdigit() and int(seg) < len(value):
            value = value[int(seg)]
        else:
            raise _Unresolvable(f"no {seg!r} in the value at {ref}")
    return value


def _source(ctx: RunContext, record: RunRecord, step_id: str) -> dict[str, Any]:
    state = ctx.log.state().step(step_id).state
    if state == "skipped":
        raise _NotApplicable(f"step {step_id} is skipped at this run's level")
    reg = record.registered(step_id)
    if state not in SATISFIES_DEPS or reg is None:
        raise _Unresolvable(f"step {step_id} has no accepted result (it is {state})")
    return reg


def _resolve(ctx: RunContext, record: RunRecord, name: str, raw: str) -> _Resolved:
    ref = refs.parse(raw)
    cas = ctx.log.cas
    if ref.kind == "run_input":
        sha = record.started.get("inputs_sha256")
        values = json.loads(cas.read(sha)) if sha else {}
        if ref.name not in values:
            raise _Unresolvable(f"run input {ref.name!r} was not given")
        value = values[ref.name]
    elif ref.kind == "step_output":
        reg = _source(ctx, record, ref.step)
        value = _walk(json.loads(cas.read(reg["output_sha256"])), ref.path, raw)
    elif ref.kind == "step_artifact":
        reg = _source(ctx, record, ref.step)
        art = (reg.get("artifacts") or {}).get(ref.name)
        if art is None:
            raise _Unresolvable(f"step {ref.step} registered no artifact {ref.name!r}")
        suffix = PurePosixPath(art.get("filename", "")).suffix
        return _Resolved(name, raw, "file", f"{name}{suffix}", cas.read(art["sha256"]), art.get("media_type"))
    elif ref.kind == "static":
        rel = PurePosixPath(ref.name)
        full = ctx.recipe.root / "static" / rel
        if rel.is_absolute() or ".." in rel.parts or not full.is_file():
            raise _Unresolvable(f"recipe has no static file {ref.name!r}")
        return _Resolved(name, raw, "file", rel.name, full.read_bytes())
    elif ref.kind == "human":
        ev = record.decision(ref.name)
        if ev is None:
            raise _Unresolvable(f"no recorded decision {ref.name!r}")
        value = {k: ev.data.get(k) for k in ("decision_id", "decision", "note")}
    elif ref.kind == "platform":
        facts = ctx.store.baton / "platform" / "facts.md"
        if not facts.is_file():
            raise _Unresolvable("the project has no platform facts")
        return _Resolved(name, raw, "file", f"{name}.md", facts.read_bytes(), "text/markdown")
    else:
        # item, group.*, human_revision.*, research.*: arrive with their layers.
        raise _Unresolvable(f"{ref.kind} references are not supported by this runtime yet")
    return _Resolved(name, raw, "json", f"{name}.json", _json_bytes(value), "application/json", value)


def resolve_inputs(ctx: RunContext, step: Step, record: RunRecord) -> tuple[list[_Resolved], list[dict[str, str]]]:
    """(resolved inputs, not-applicable entries) or raise ``HandoffError`` listing all missing."""
    resolved: list[_Resolved] = []
    not_applicable: list[dict[str, str]] = []
    missing: list[tuple[str, str, str]] = []
    for inp in step.inputs:
        try:
            resolved.append(_resolve(ctx, record, inp.name, inp.from_))
        except _NotApplicable as e:
            not_applicable.append({"name": inp.name, "from": inp.from_, "reason": str(e)})
        except (_Unresolvable, StoreError) as e:
            if inp.required:
                missing.append((inp.name, inp.from_, str(e)))
    if missing:
        raise HandoffError(step.id, missing)
    return resolved, not_applicable


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def exit_criteria(step: Step, level: str | None) -> list[str]:
    """What "done" means for this step, rendered from its output contract and gates."""
    out = ["Write result/result.json (status, output, artifacts), echoing packet_sha256 from manifest.json."]
    if step.output_schema:
        out.append("`output` validates against output_schema.json.")
    for a in step.artifacts:
        if a.required:
            mt = f" ({a.media_type})" if a.media_type else ""
            out.append(f"Artifact `{a.name}`{mt} is written under result/artifacts/ and listed in `artifacts`.")
    for g in step.gates:
        if not gate_included(g, level):
            continue
        adv = " (advisory)" if g.advisory else ""
        if isinstance(g, ScriptGate):
            out.append(f"The check `{g.run}` exits 0{adv}.")
        elif isinstance(g, HumanGate):
            out.append(f"The owner approves{adv}: {g.prompt}")
        elif isinstance(g, (ReviewGate, FindingsGate)):
            sev = ", ".join(g.block_on or []) or "any blocking"
            out.append(f"An independent review leaves no open {sev} findings{adv}.")
    return out


def render_instructions(step: Step, prompt: str, manifest: dict[str, Any], inputs: list[_Resolved], schema: dict[str, Any]) -> str:
    title = step.title or step.id
    lines = [
        f"# {title}",
        "",
        f"You are the worker for step `{manifest['step_path']}` (attempt {manifest['attempt']}) of a Baton run.",
        "Do this step's work only, as described below, and report through the result files.",
        "",
        "## Task",
        "",
        prompt.rstrip("\n"),
        "",
        "## Inputs",
        "",
    ]
    if not inputs and not manifest["not_applicable"]:
        lines += ["This step has no inputs.", ""]
    for r in inputs:
        lines.append(f"### `{r.name}`")
        lines.append("")
        lines.append(f"File: `inputs/{r.filename}`" + (f" ({r.media_type})" if r.media_type else ""))
        lines.append("")
        if r.kind == "json" and len(r.content) <= INLINE_LIMIT:
            lines += ["```json", r.content.decode("utf-8").rstrip("\n"), "```", ""]
        elif r.kind == "json":
            lines += [f"Too large to inline ({len(r.content)} bytes); read the file.", ""]
    for na in manifest["not_applicable"]:
        lines += [f"### `{na['name']}`", "", f"Not applicable: {na['reason']}.", ""]
    lines += ["## Done when", ""]
    lines += [f"- {c}" for c in manifest["exit_criteria"]]
    if manifest["deadline"]:
        lines.append(f"- Finished before {manifest['deadline']}.")
    lines.append("")
    if manifest["prior_feedback"]:
        pf = manifest["prior_feedback"]
        lines += ["## Feedback on the previous attempt", ""]
        if pf["reasons"]:
            lines += [f"Attempt {pf['attempt']} was not accepted:", ""]
            lines += [f"- {r}" for r in pf["reasons"]]
            lines.append("")
        if pf.get("guidance"):
            lines += ["Additional guidance for this attempt:", "", pf["guidance"], ""]
        lines += ["Address every point above in this attempt.", ""]
    lines += [
        "## Protocol",
        "",
        "- This directory is the packet. Do not modify anything in it.",
        "- Write results only to `../result/` (relative to this packet directory): artifacts under",
        "  `../result/artifacts/`, then `../result/result.json` **last**.",
    ]
    if manifest["workspace"] == "write":
        lines.append("- You may change the project working tree; record your commit as `commit_sha` in `output` if the schema asks.")
    elif manifest["workspace"] == "read":
        lines.append("- You may read the project working tree. Do not modify it.")
    else:
        lines.append("- Do not read or modify the project working tree.")
    if manifest["protected_paths"]:
        lines.append(f"- Never modify these paths: {', '.join(f'`{p}`' for p in manifest['protected_paths'])}.")
    lines += [
        "- `result.json` is a JSON object:",
        "",
        "```json",
        json.dumps(
            {
                "protocol": PROTOCOL,
                "packet_sha256": "<copy from manifest.json>",
                "status": "completed | blocked | failed",
                "output": "<an object matching output_schema.json>",
                "artifacts": [{"name": "<declared artifact name>", "path": "artifacts/<file>"}],
                "notes": "",
                "questions_for_human": [],
                "process_feedback": [],
            },
            indent=2,
        ),
        "```",
        "",
        "- Use `blocked` with `questions_for_human` when only the owner can answer something; `failed` when",
        "  you cannot do the step. Never guess or improvise around a mismatch: report it.",
        "- Report friction with the process itself in `process_feedback`.",
        "",
    ]
    declared = manifest["required_artifacts"] + manifest["optional_artifacts"]
    if declared:
        lines += ["## Artifacts", ""]
        for a in declared:
            req = "required" if a in manifest["required_artifacts"] else "optional"
            mt = f", {a['media_type']}" if a.get("media_type") else ""
            lines.append(f"- `{a['name']}` ({req}{mt})")
        lines.append("")
    lines += ["## Output schema", "", "Also in `output_schema.json`.", "", "```json", json.dumps(schema, indent=2, ensure_ascii=False), "```", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hashing and the packet directory
# ---------------------------------------------------------------------------


def packet_digest(manifest: dict[str, Any], files: dict[str, str]) -> str:
    """``packet_sha256``; ``files`` maps POSIX paths (excluding manifest.json) to their SHA-256."""
    body = dict(manifest, packet_sha256=None)
    h = hashlib.sha256()
    h.update(PROTOCOL.encode("utf-8") + b"\n")
    h.update(canonical_json(body).encode("utf-8") + b"\n")
    for rel in sorted(files):
        h.update(f"{rel}\0{files[rel]}\n".encode("utf-8"))
    return h.hexdigest()


def _tree(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() or p.is_symlink():
            rel = p.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "symlink"
    return out


def verify_packet(packet_dir: Path) -> tuple[str | None, list[str]]:
    """(packet_sha256 recorded in the manifest, problems). Empty problems: the packet is intact."""
    mpath = packet_dir / "manifest.json"
    if not mpath.is_file():
        return None, ["packet manifest.json is missing"]
    try:
        manifest = json.loads(read_text(mpath))
    except json.JSONDecodeError as e:
        return None, [f"packet manifest.json is not valid JSON ({e})"]
    recorded = manifest.get("packet_sha256")
    files = _tree(packet_dir)
    files.pop("manifest.json", None)
    problems = []
    if packet_digest(manifest, files) != recorded:
        problems.append("the packet was modified after it was built")
    return recorded, problems


def _make_read_only(root: Path) -> None:
    if os.name != "posix":
        for p in root.rglob("*"):
            if p.is_file():
                os.chmod(p, stat.S_IREAD)
        return
    for p in sorted(root.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        os.chmod(p, 0o444 if p.is_file() else 0o555)
    os.chmod(root, 0o555)


def _make_writable(root: Path) -> None:
    for p in [root, *root.rglob("*")]:
        try:
            os.chmod(p, 0o700 if p.is_dir() else 0o600)
        except OSError:
            pass


def remove_tree(root: Path) -> None:
    if root.exists():
        _make_writable(root)
        shutil.rmtree(root)


def _write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


@dataclass
class BuiltPacket:
    step_path: str
    attempt: int
    dir: Path
    result_dir: Path
    manifest: dict[str, Any]

    @property
    def sha256(self) -> str:
        return self.manifest["packet_sha256"]


def output_schema_for(loaded: LoadedRecipe, step: Step) -> dict[str, Any]:
    if step.output_schema == FINDINGS_SCHEMA_REF:
        return versions.findings_json_schema()
    if step.output_schema:
        return loaded.schemas[step.output_schema]
    return {"$schema": versions.DRAFT_2020_12}


def unsupported_reason(node: Step | Group | None) -> str | None:
    """Why this runtime cannot run the node yet, or ``None``."""
    if node is None:
        return "not a top-level step of the recipe (steps inside groups arrive with the groups layer)"
    if isinstance(node, Group):
        return "groups arrive with the groups layer"
    for g in node.gates:
        if isinstance(g, (ReviewGate, FindingsGate)):
            return f"{g.type} gates arrive with the reviews layer"
    return None


def prior_feedback(record: RunRecord, step_path: str, attempt: int, guidance: str | None = None) -> dict[str, Any] | None:
    """Reasons the previous attempt was not accepted, from its events, plus any retry guidance."""
    if attempt < 1:
        return None
    reasons: list[str] = []
    for ev in record.attempt_events(step_path, attempt):
        if ev.type == "result_rejected" or (ev.type == "gate_failed" and not ev.data.get("advisory")):
            reasons += ev.data.get("reasons") or []
        elif ev.type == "step_escalated" and ev.data.get("questions"):
            reasons += [f"you asked the owner: {q}" for q in ev.data["questions"]]
        elif ev.type == "human_decision" and ev.data.get("kind") == "escalation" and ev.data.get("note"):
            reasons.append(f"the owner answered: {ev.data['note']}")
    if guidance:
        return {"attempt": attempt, "reasons": reasons, "guidance": guidance}
    return {"attempt": attempt, "reasons": reasons} if reasons else None


def build_packet(
    ctx: RunContext,
    step_path: str,
    profile_name: str,
    profile: WorkerProfile,
    *,
    deadline: str | None = None,
    guidance: str | None = None,
) -> BuiltPacket:
    """Assemble and write the packet for the step's next attempt. Writes no events.

    ``guidance`` (a retry's additive note from the Director, §13.1) is added to
    ``prior_feedback``; it never replaces inputs or reasons.

    Raises ``EngineError`` (step not ready, unsupported, ineligible profile) or
    ``HandoffError`` (missing required inputs); in both cases nothing is written.
    """
    loaded = ctx.recipe
    node = node_for(loaded, step_path)
    why = unsupported_reason(node)
    if why:
        raise EngineError("packet.unsupported_step", f"{step_path}: {why}")
    assert isinstance(node, Step)
    rs = ctx.log.state()
    current = rs.step(step_path)
    if current.state != "ready":
        raise EngineError("packet.not_ready", f"{step_path} is {current.state}, not ready")
    unmet = [d for d in node.depends_on if rs.step(d).state not in SATISFIES_DEPS]
    if unmet:
        raise EngineError("packet.deps_unmet", f"{step_path}: dependencies not satisfied: {', '.join(unmet)}")
    gaps = requirement_gaps(node.requires, node.workspace, profile, loaded.vocab)
    if gaps:
        raise EngineError("packet.ineligible_profile", f"{profile_name} cannot do {step_path}: {'; '.join(gaps)}")

    record = ctx.record()
    inputs, not_applicable = resolve_inputs(ctx, node, record)
    attempt = current.attempt + 1
    level = record.level()
    schema = output_schema_for(loaded, node)
    prompt = read_text(loaded.root / node.prompt)

    files: dict[str, bytes] = {}
    entries = []
    for r in inputs:
        rel = f"inputs/{r.filename}"
        if rel in files:
            raise EngineError("packet.input_collision", f"{step_path}: two inputs write {rel}")
        files[rel] = r.content
        entry = {"name": r.name, "from": r.ref, "kind": r.kind, "path": rel, "sha256": hashlib.sha256(r.content).hexdigest()}
        if r.media_type:
            entry["media_type"] = r.media_type
        entries.append(entry)
    files["output_schema.json"] = (json.dumps(schema, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    def art(a: Any) -> dict[str, Any]:
        return {"name": a.name, "media_type": a.media_type} if a.media_type else {"name": a.name}

    manifest: dict[str, Any] = {
        "protocol": PROTOCOL,
        "run_id": ctx.run_id,
        "recipe": loaded.recipe.ref,
        "recipe_sha256": loaded.sha256,
        "step_path": step_path,
        "attempt": attempt,
        "effort": node.effort,
        "deadline": deadline,
        "workspace": node.workspace,
        "exit_criteria": exit_criteria(node, level),
        "protected_paths": node.protect_paths(),
        "worker_profile": profile_name,
        "worker_profile_sha256": profile_sha256(profile),
        "inputs": entries,
        "not_applicable": not_applicable,
        "required_artifacts": [art(a) for a in node.artifacts if a.required],
        "optional_artifacts": [art(a) for a in node.artifacts if not a.required],
        "prior_feedback": prior_feedback(record, step_path, attempt - 1, guidance),
        "packet_sha256": None,
    }
    files["INSTRUCTIONS.md"] = render_instructions(node, prompt, manifest, inputs, schema).encode("utf-8")
    manifest["packet_sha256"] = packet_digest(manifest, {k: hashlib.sha256(v).hexdigest() for k, v in files.items()})

    # Write: a temp directory renamed into place, then made read-only. An earlier
    # packet for the same (not yet dispatched) attempt is replaced.
    adir = ensure_dir(ctx.attempt_dir(step_path, attempt))
    tmp = adir / f".packet-{secrets.token_hex(6)}"
    try:
        for rel, content in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(content)
        _write_text(tmp / "manifest.json", json.dumps(manifest, **JSON_DUMP) + "\n")
        pdir, rdir = adir / "packet", adir / "result"
        remove_tree(pdir)
        remove_tree(rdir)
        os.replace(tmp, pdir)
    finally:
        remove_tree(tmp)
    _make_read_only(pdir)
    ensure_dir(rdir / "artifacts")
    return BuiltPacket(step_path, attempt, pdir, rdir, manifest)
