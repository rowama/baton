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

from . import groups, refs, reviews, versions
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
    """The recipe node for a step or group path (``<group>/<instance>/i<n>/<step>`` inside groups)."""
    loc = groups.locate(recipe, step_path)
    return loc.node if loc is not None else None


def view_of(ctx: RunContext) -> groups.View:
    """The run's group view (§8.5), derived from its events."""
    log = ctx.log
    return groups.View(ctx.recipe, log.events(), log.state(), log.cas)


def revision_of(record: RunRecord, step_path: str) -> tuple[Event, Event] | None:
    """``(step_revised, the result it superseded)`` while a revision of the step is not yet accepted."""
    revised = None
    for ev in reversed(record.events):
        if ev.step_path != step_path:
            continue
        if revised is None:
            if ev.type in ("step_passed", "step_imported"):
                return None
            if ev.type == "step_revised":
                revised = ev
        elif ev.type in ("step_passed", "step_imported"):
            return revised, ev
    return None


def gate_included(gate: Any, level: str | None) -> bool:
    """A gate with ``applies_to`` runs only at those levels; before triage sets a level, it runs."""
    return gate.applies_to is None or level is None or level in gate.applies_to


def profile_sha256(profile: WorkerProfile) -> str:
    """Hash of the profile's non-secret fields: ``auth.env`` keeps variable names only.

    Empty ``options`` are left out, so adding that field kept earlier hashes.
    """
    body = profile.model_dump(mode="json", exclude_none=True)
    if not body.get("options"):
        body.pop("options", None)
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
    revision: dict[str, Any] | None = None  # a human revision given in place of the recorded artifact (§10.5)


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


def _artifact(ctx: RunContext, name: str, raw: str, reg: dict[str, Any], source: str, artifact: str | None) -> _Resolved:
    art = (reg.get("artifacts") or {}).get(artifact)
    if art is None:
        raise _Unresolvable(f"step {source} registered no artifact {artifact!r}")
    suffix = PurePosixPath(art.get("filename", "")).suffix
    return _Resolved(name, raw, "file", f"{name}{suffix}", ctx.log.cas.read(art["sha256"]), art.get("media_type"))


def _resolve(
    ctx: RunContext, record: RunRecord, name: str, raw: str, loc: groups.Located | None = None, view: groups.View | None = None
) -> _Resolved:
    """Resolve one reference for the step at ``loc`` (needed for ``item`` and ``group.*``)."""
    ref = refs.parse(raw)
    cas = ctx.log.cas
    if ref.kind in refs.GROUP_ONLY or ref.kind == "group_outputs":
        view = view or view_of(ctx)
        if ref.kind != "group_outputs" and (loc is None or loc.frame is None):
            raise _Unresolvable(f"{raw} is only available inside a group")
    if ref.kind == "item":
        assert view is not None and loc is not None
        try:
            value = _walk(view.item_value(loc), ref.path, raw)
        except LookupError as e:
            raise _Unresolvable(str(e)) from e
    elif ref.kind in ("sibling_output", "sibling_artifact"):
        assert loc is not None and loc.frame is not None
        sib = groups.child_path(loc.frame, ref.step or "")
        reg = _source(ctx, record, sib)
        if ref.kind == "sibling_artifact":
            return _artifact(ctx, name, raw, reg, sib, ref.name)
        value = _walk(json.loads(cas.read(reg["output_sha256"])), ref.path, raw)
    elif ref.kind == "previous_findings":
        assert view is not None and loc is not None
        try:
            value = view.previous_findings(loc)
        except LookupError as e:
            raise _Unresolvable(str(e)) from e
        if value is None:
            raise _NotApplicable("this is the first iteration")
    elif ref.kind == "group_outputs":
        assert view is not None
        node = groups.locate(ctx.recipe, ref.step or "")
        state = view.state(ref.step or "")
        if state == "skipped":
            raise _NotApplicable(f"group {ref.step} is skipped")
        if node is None or not isinstance(node.node, Group) or state != "passed":
            raise _Unresolvable(f"group {ref.step} has not passed (it is {state})")
        value = view.group_outputs(node.node, ref.step or "")
    elif ref.kind == "run_input":
        sha = record.started.get("inputs_sha256")
        values = json.loads(cas.read(sha)) if sha else {}
        if ref.name not in values:
            raise _Unresolvable(f"run input {ref.name!r} was not given")
        value = values[ref.name]
    elif ref.kind == "step_output":
        reg = _source(ctx, record, ref.step)
        value = _walk(json.loads(cas.read(reg["output_sha256"])), ref.path, raw)
    elif ref.kind == "step_artifact":
        resolved = _artifact(ctx, name, raw, _source(ctx, record, ref.step), ref.step or "", ref.name)
        if loc is not None:
            from .publish import revision_for_dependent

            rev = revision_for_dependent(record.events, ref.step or "", ref.name or "", loc.path)
            if rev is not None:  # the owner chose to feed a not-yet-started dependent their revision (§10.5)
                return _revision(ctx, name, raw, rev, resolved.filename)
        return resolved
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
    elif ref.kind == "research":
        ev = record.last("research_recorded")
        if ev is None or not ev.data.get("research_sha256"):
            raise _NotApplicable("this run was not started by an adoption")
        value = json.loads(cas.read(ev.data["research_sha256"]))
    elif ref.kind == "human_revision":
        from .publish import latest_revision

        _source(ctx, record, ref.step)
        rev = latest_revision(record.events, ref.step or "", ref.name or "")
        if rev is None:
            raise _NotApplicable(f"no human revision of {ref.step}.{ref.name} has been ingested")
        reg = record.registered(ref.step or "") or {}
        art = (reg.get("artifacts") or {}).get(ref.name) or {}
        return _revision(ctx, name, raw, rev, f"{name}{PurePosixPath(art.get('filename', '') or rev.data.get('path') or '').suffix}")
    else:  # pragma: no cover - every reference kind is handled above
        raise _Unresolvable(f"{ref.kind} references are not supported by this runtime")
    return _Resolved(name, raw, "json", f"{name}.json", _json_bytes(value), "application/json", value)


def _revision(ctx: RunContext, name: str, raw: str, rev: Any, filename: str) -> _Resolved:
    d = rev.data
    info = {"step_path": rev.step_path, "artifact": d.get("artifact"), "revision": d.get("revision"), "source": d.get("source")}
    return _Resolved(name, raw, "file", filename, ctx.log.cas.read(d["sha256"]), None, None, info)


def resolve_inputs(
    ctx: RunContext, step: Step, record: RunRecord, step_path: str | None = None, view: groups.View | None = None
) -> tuple[list[_Resolved], list[dict[str, str]]]:
    """(resolved inputs, not-applicable entries) or raise ``HandoffError`` listing all missing."""
    resolved: list[_Resolved] = []
    not_applicable: list[dict[str, str]] = []
    missing: list[tuple[str, str, str]] = []
    step_path = step_path or step.id
    loc = groups.locate(ctx.recipe, step_path)
    for inp in step.inputs:
        try:
            resolved.append(_resolve(ctx, record, inp.name, inp.from_, loc, view))
        except _NotApplicable as e:
            not_applicable.append({"name": inp.name, "from": inp.from_, "reason": str(e)})
        except (_Unresolvable, StoreError) as e:
            if inp.required:
                missing.append((inp.name, inp.from_, str(e)))
    if missing:
        raise HandoffError(step_path, missing)
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
            # The runtime asks the owner after intake; a worker must not block on it (seen live: it did).
            out.append(f"Afterwards the owner is asked{adv} (by the runtime, not by you; do not report `blocked` for it): {g.prompt}")
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
        if r.revision is not None:
            by = "an expert's answer the owner promoted" if r.revision.get("source") == "sme" else "the owner's edit of the published file"
            lines += [f"This is revision {r.revision['revision']} of `{r.revision['artifact']}` from `{r.revision['step_path']}`: {by}, ingested by the owner.", ""]
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
        if pf["reasons"] or pf.get("guidance"):
            lines += ["## Feedback on the previous attempt", ""]
        if pf["reasons"]:
            lines += [f"Attempt {pf['attempt']} was not accepted:", ""]
            lines += [f"- {r}" for r in pf["reasons"]]
            lines.append("")
        if pf.get("guidance"):
            lines += ["Additional guidance for this attempt:", "", pf["guidance"], ""]
        if pf["reasons"] or pf.get("guidance"):
            lines += ["Address every point above in this attempt.", ""]
        rev = pf.get("revision")
        if rev:
            lines += ["## Revision", "", f"This step is being revised. The reason: {rev['reason']}", ""]
            lines += [f"Your previous accepted result is in `{rev['output']}`" + (
                " (artifacts: " + ", ".join(f"`{a['path']}`" for a in rev["artifacts"]) + ")" if rev["artifacts"] else ""
            ) + ". Start from it and change only what the reason calls for.", ""]
            if rev.get("items"):
                lines += [
                    f"Items under `{rev['items']}` carry their current `id`. Echo the `id` of every item you keep "
                    "(changed or not); leave out items to drop; give new items no `id`.",
                    "",
                ]
    disposable = bool((manifest["prior_feedback"] or {}).get("findings")) or any(
        i.get("from") == "group.previous_iteration.findings" for i in manifest["inputs"]
    )
    pf_find = (manifest["prior_feedback"] or {}).get("findings")
    if pf_find:
        lines += ["Open findings of that attempt's review:", ""]
        lines += [f"- `{f['id']}` ({f.get('severity')}): {f.get('title')}" + (f" at `{f['location']}`" if f.get("location") else "") for f in pf_find]
        lines.append("")
    if disposable:
        lines += [
            "## Dispositions",
            "",
            "For each earlier finding you fixed or believe is wrong, you may add an entry to `dispositions` in",
            "`result.json`: `{\"step\": <the step that recorded it>, \"finding\": <its id>, \"disposition\": \"fixed\" | \"rejected\",",
            "\"evidence\": ...}`. `fixed` needs a commit SHA or `file:line`; `rejected` needs a `file:line` that exists at the",
            "reviewed commit, or a test reference `path::name`. Evidence is checked; a disposition is only a claim until",
            "the next review confirms it (a finding reported again stays open). Present evidence so that someone without",
            "subject expertise can check it.",
            "",
        ]
    prior = manifest.get("prior_findings")
    if "prior_findings" in manifest:
        lines += ["## Earlier findings", ""]
        if prior and prior.get("findings"):
            lines += [
                f"An earlier review of this work ({prior['evaluated_at']}, attempt {prior['attempt']}) reported the findings below.",
                "Reuse a finding's `id` when you still see the problem, even if it is marked fixed or rejected; leave out a",
                "finding that is resolved. Check each disposition's evidence yourself. Give new findings new ids.",
                "",
            ]
            for f in prior["findings"]:
                d = f.get("disposition") or {}
                claim = f" — marked **{d['disposition']}**" + (f" by {d.get('by')}" if d.get("by") else "") + (f": {d['evidence']}" if d.get("evidence") else "") if d else ""
                lines.append(f"- `{f['id']}` ({f.get('severity')}, {f.get('status')}): {f.get('title')}" + (f" at `{f['location']}`" if f.get("location") else "") + claim)
            lines.append("")
        else:
            lines += ["This is the first review of this work.", ""]
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
                **({"dispositions": [{"step": "<step>", "finding": "<id>", "disposition": "fixed | rejected", "evidence": "<commit | file:line | path::test>"}]} if disposable else {}),
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
        return "not a step of the recipe (inside a group, a step path is <group>/<instance>/i<n>/<step>)"
    if isinstance(node, Group):
        return "a group is not dispatched itself; dispatch the steps of its instances"
    return None


def prior_feedback(
    record: RunRecord, step_path: str, attempt: int, guidance: str | None = None, revision: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Reasons the previous attempt was not accepted, from its events, plus any retry guidance.

    ``revision`` (§8.9) is the reason the step is being revised and where the
    previous accepted result is in the packet; it stays until a revised result
    is accepted.
    """
    if attempt < 1:
        return None
    if revision is not None:
        base = prior_feedback(record, step_path, attempt, guidance) or {"attempt": attempt, "reasons": []}
        return {**base, "revision": revision}
    reasons: list[str] = []
    findings: list[dict[str, Any]] = []
    for ev in record.attempt_events(step_path, attempt):
        if ev.type == "findings_recorded" and ev.data.get("blocking"):
            findings += [{"step": step_path, **f} for f in ev.data.get("findings") or [] if f.get("status") == "open"]
        if ev.type == "result_rejected" or (ev.type == "gate_failed" and not ev.data.get("advisory")):
            reasons += ev.data.get("reasons") or []
        elif ev.type == "step_escalated" and ev.data.get("questions"):
            reasons += [f"you asked the owner: {q}" for q in ev.data["questions"]]
        elif ev.type == "human_decision" and ev.data.get("kind") == "escalation" and ev.data.get("note"):
            reasons.append(f"the owner answered: {ev.data['note']}")
    out: dict[str, Any] = {"attempt": attempt, "reasons": reasons}
    if findings:
        out["findings"] = findings
    if guidance:
        out["guidance"] = guidance
        return out
    return out if reasons else None


def _reviewed_result(ctx: RunContext, record: RunRecord, review_path: str) -> list[_Resolved]:
    """The result under review (§9.1): the reviewed step's current attempt, as intake registered it."""
    ready = None
    for ev in reversed(record.events):
        if ev.type == "step_ready" and ev.step_path == review_path and "review_of" in ev.data:
            ready = ev
            break
    if ready is None:
        raise EngineError("packet.no_review_request", f"{review_path} was not readied for a review")
    ppath, pn = ready.data["review_of"], ready.data["attempt"]
    sub = record.last("result_submitted", ppath, pn)
    if sub is None:  # pragma: no cover - a review is readied only after intake
        raise EngineError("packet.no_review_request", f"{ppath} attempt {pn} has no submitted result")
    out = []
    if sub.data.get("output_sha256"):
        value = json.loads(ctx.log.cas.read(sub.data["output_sha256"]))
        out.append(_Resolved("reviewed_output", f"review.{ppath}.attempt-{pn}.output", "json", "reviewed_output.json", _json_bytes(value), "application/json", value))
    for aname, a in sorted((sub.data.get("artifacts") or {}).items()):
        suffix = PurePosixPath(a.get("filename", "")).suffix
        out.append(_Resolved(f"reviewed_{aname}", f"review.{ppath}.attempt-{pn}.artifacts.{aname}", "file", f"reviewed_{aname}{suffix}", ctx.log.cas.read(a["sha256"]), a.get("media_type")))
    return out


def _prior_findings(ctx: RunContext, record: RunRecord, node: Step, loc: groups.Located) -> dict[str, Any] | None:
    """The previous evaluation of the reviewer's line, with dispositions (what the reviewer re-checks)."""
    target = reviews.review_target(node)
    if target is not None:
        parent, gi = target
        split = reviews.split_review(loc.path)
        assert split is not None
        ploc = groups.locate(ctx.recipe, split[0])
        assert ploc is not None
        line = reviews.line_of(ploc, gi)
    else:
        idx = [i for i, g in enumerate(node.gates) if isinstance(g, FindingsGate)]
        if not idx:
            return None
        line = reviews.line_of(loc, idx[0])
    return reviews.prior_findings(record.events, line)


def build_packet(
    ctx: RunContext,
    step_path: str,
    profile_name: str,
    profile: WorkerProfile,
    *,
    deadline: str | None = None,
    guidance: str | None = None,
    effort: str | None = None,
) -> BuiltPacket:
    """Assemble and write the packet for the step's next attempt. Writes no events.

    ``effort`` is the resolved effort (``effort`` or ``effort_from``, §8.7);
    ``deadline`` is supplied by the caller (the manifest's only clock reading).

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
    if current.state not in ("ready", "stale"):
        raise EngineError("packet.not_ready", f"{step_path} is {current.state}, not ready")
    view = view_of(ctx)
    loc = groups.locate(loaded, step_path)
    assert loc is not None
    why_not = view.live_reason(step_path)
    if why_not:
        raise EngineError("packet.not_current", f"{step_path}: {why_not}")
    if not view.deps_met(node, loc.frame):
        unmet = [d for d in node.depends_on if view.state(groups.child_path(loc.frame, d)) not in SATISFIES_DEPS]
        raise EngineError("packet.deps_unmet", f"{step_path}: dependencies not satisfied: {', '.join(unmet)}")
    gaps = requirement_gaps(node.requires, node.workspace, profile, loaded.vocab)
    if gaps:
        raise EngineError("packet.ineligible_profile", f"{profile_name} cannot do {step_path}: {'; '.join(gaps)}")

    record = ctx.record()
    inputs, not_applicable = resolve_inputs(ctx, node, record, step_path, view)
    target = reviews.review_target(node)
    if target is not None:
        inputs += _reviewed_result(ctx, record, step_path)
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
        if r.revision is not None:
            entry["human_revision"] = r.revision
        entries.append(entry)
    files["output_schema.json"] = (json.dumps(schema, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    revision = None
    rev = revision_of(record, step_path)
    if rev is not None:
        revised, previous = rev
        prev_output = json.loads(ctx.log.cas.read(previous.data["output_sha256"])) if previous.data.get("output_sha256") else None
        prev_output = view.with_item_ids(loc, prev_output)
        files["previous/output.json"] = _json_bytes(prev_output)
        arts = []
        for aname, a in sorted((previous.data.get("artifacts") or {}).items()):
            rel = f"previous/artifacts/{aname}{PurePosixPath(a.get('filename', '')).suffix}"
            files[rel] = ctx.log.cas.read(a["sha256"])
            arts.append({"name": aname, "path": rel})
        revision = {"reason": revised.data.get("reason", ""), "attempt": previous.attempt, "output": "previous/output.json", "artifacts": arts}
        fed = view.fed_groups(loc)
        if len(fed) == 1 and fed[0][2]:
            revision["items"] = "output." + ".".join(fed[0][2])

    def art(a: Any) -> dict[str, Any]:
        return {"name": a.name, "media_type": a.media_type} if a.media_type else {"name": a.name}

    manifest: dict[str, Any] = {
        "protocol": PROTOCOL,
        "run_id": ctx.run_id,
        "recipe": loaded.recipe.ref,
        "recipe_sha256": loaded.sha256,
        "step_path": step_path,
        "attempt": attempt,
        "effort": effort or node.effort,
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
        "prior_feedback": prior_feedback(record, step_path, attempt - 1, guidance, revision),
        "packet_sha256": None,
    }
    if reviews.is_reviewer(node):
        manifest["prior_findings"] = _prior_findings(ctx, record, node, loc)
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
