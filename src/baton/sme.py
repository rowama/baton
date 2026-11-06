"""Experts: consultation, the platform area and process feedback (§12).

An SME is a worker profile consulted by **subject** (``project``, ``platform``,
``process``), outside the step graph. The Director names references; the
runtime resolves them into a hashed packet with neutral provenance labels and
an index of everything else on record (titles only). Answers are recorded but
are never referenceable by steps; they reach the work only through
``promote_sme`` with the owner's words.

Where a consultation lives::

    runs/<run_id>/sme/<c_id>/turn-<n>/{packet,result}/    (with a run; events in the run log)
    project/sme/<c_id>/turn-<n>/{packet,result}/          (without; events in the project log)
    .../<c_id>/handoff.md                                 (a handoff prompt, §18 #17)

Answers and the experts' artifacts are stored in the run's CAS, or in
``project/cas/`` for project-level consultations. Everything written here is
redacted (§15.2); transcripts are kept in full (§18 #13).

**Modes** (§18 #17). ``relay`` is the formal mode: each turn is a dispatch
(asynchronous, supervised) whose answer is recorded. ``handoff`` renders one
copy-and-paste prompt (the same instructions, material and earlier turns) for
the owner to continue with the expert elsewhere; it is refused when the expert
relies on capabilities a pasted prompt cannot carry (``NO_HANDOFF``) unless
the expert is a black box (``command`` adapter). Nothing returns from a
handoff except through promotion.

**People.** An SME is never a ``manual`` worker. A person is consulted
through a proxy SME: the consultation names them (``contact``), the proxy
drafts what the owner sends (artifacts) and reports what it waits for
(``awaiting``); the person's reply comes back as an attachment to the next
turn. Proxies draft; they never send.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .data import read_text
from .models import Event, Requires, WorkerProfile
from .redact import redact_text
from .store import CAS, EventLog, canonical_json, ensure_dir, format_ts

SUBJECTS = ("project", "platform", "process")
MODES = ("relay", "handoff")
CONSULTATION_ID = re.compile(r"^c_[0-9a-f]{8}$")
#: Capabilities a pasted prompt cannot carry: an expert relying on any of them
#: answers by working on this machine (§18 #17).
NO_HANDOFF = ("shell", "code_exec", "workspace_read", "repo_workspace", "file_write")
FEEDBACK_KINDS = ("friction", "skipped_step", "waste", "confusing")
PROMOTE_TARGETS = ("decision", "fact", "lesson", "proposal", "revision")
LOG_TAIL = 64 * 1024
TEXT_INLINE = 16 * 1024

SUBJECT_ROLE = {
    "project": "the subject matter of this project's work (its domain)",
    "platform": "the development and deployment infrastructure: hosts, CLIs, authentication, networks, deployment",
    "process": "Baton and the recipe this project follows: how the process works and how it could work better",
}

ANSWER_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "baton:sme-answer/1",
    "type": "object",
    "required": ["answer", "confidence", "sources_used", "requested_refs", "suggests_retriage"],
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "confidence": {"enum": ["low", "medium", "high"]},
        "sources_used": {"type": "array", "items": {"type": "string"}},
        "requested_refs": {"type": "array", "items": {"type": "string"}},
        "suggests_retriage": {"type": "boolean"},
        "awaiting": {
            "type": "object",
            "required": ["who", "what"],
            "additionalProperties": False,
            "properties": {"who": {"type": "string", "minLength": 1}, "what": {"type": "string", "minLength": 1}},
        },
    },
}


class SmeError(Exception):
    """A consultation request the runtime refuses. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# References (§12.1): names the Director selects, allowed per subject
# ---------------------------------------------------------------------------

#: kind -> (subjects that may use it, needs the consultation's run, syntax)
REF_KINDS: dict[str, tuple[frozenset[str], bool, str]] = {
    "step": (frozenset({"project", "process"}), True, "step:<step_path>"),
    "record": (frozenset({"project", "process"}), True, "record:<step_path>"),
    "summary": (frozenset({"project", "process"}), True, "summary"),
    "project": (frozenset({"project"}), False, "project:<file>"),
    "facts": (frozenset({"platform"}), False, "facts"),
    "incident": (frozenset({"platform"}), False, "incident:<id>"),
    "log": (frozenset({"platform"}), False, "log:<run_id>:<step_path>[@<attempt>]"),
    "profile": (frozenset({"platform"}), False, "profile:<name>"),
    "doctor": (frozenset({"platform"}), False, "doctor"),
    "events": (frozenset({"process"}), True, "events"),
    "feedback": (frozenset({"process"}), False, "feedback"),
    "stats": (frozenset({"process"}), False, "stats"),
    "lessons": (frozenset({"process"}), False, "lessons"),
    "recipe": (frozenset({"process"}), False, "recipe[:<id>@<version>]"),
}
_ARG_KINDS = {"step", "record", "project", "incident", "log", "profile"}


def parse_ref(raw: str) -> tuple[str, str | None]:
    kind, sep, arg = raw.partition(":")
    if kind not in REF_KINDS:
        raise SmeError("sme.bad_ref", f"{raw!r} is not an expert reference (known: {', '.join(v[2] for v in REF_KINDS.values())})")
    if kind in _ARG_KINDS and not arg:
        raise SmeError("sme.bad_ref", f"{raw!r} needs an argument: {REF_KINDS[kind][2]}")
    if kind not in _ARG_KINDS and kind != "recipe" and sep:
        raise SmeError("sme.bad_ref", f"{raw!r} takes no argument: {REF_KINDS[kind][2]}")
    return kind, (arg or None)


def check_ref(raw: str, subject: str, has_run: bool) -> tuple[str, str | None]:
    kind, arg = parse_ref(raw)
    subjects, needs_run, syntax = REF_KINDS[kind]
    if subject not in subjects:
        allowed = ", ".join(v[2] for v in REF_KINDS.values() if subject in v[0])
        raise SmeError("sme.ref_not_allowed", f"{raw!r} is not in a {subject} expert's scope (allowed: {allowed})")
    if needs_run and not has_run:
        raise SmeError("sme.ref_needs_run", f"{raw!r} names a run's record; consult with --run <run_id>")
    return kind, arg


@dataclass
class Item:
    """One piece of material in a packet, with its neutral provenance label."""

    ref: str
    label: str
    filename: str
    content: bytes
    media_type: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def text(self) -> str | None:
        try:
            return self.content.decode("utf-8")
        except UnicodeDecodeError:
            return None


def _slug(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_")[:80] or "ref"


def _redacted(data: bytes) -> bytes:
    try:
        return redact_text(data.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return data


def _json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


@dataclass
class Sources:
    """What references resolve against: the project, and the consultation's run when there is one."""

    project: Any  # project.Project
    ctx: Any = None  # packet.RunContext | None

    @property
    def baton(self) -> Path:
        return self.project.baton


def resolve(src: Sources, raw: str, subject: str) -> list[Item]:
    """The material for one reference (refused when it is outside the subject's scope)."""
    from . import docs
    from .packet import node_for

    kind, arg = check_ref(raw, subject, src.ctx is not None)
    ctx = src.ctx
    if kind == "step":
        assert arg is not None
        events = ctx.log.events()
        reg = ctx.record().registered(arg)
        if reg is None:
            raise SmeError("sme.ref_unresolvable", f"{raw}: step {arg} has no accepted result in run {ctx.run_id}")
        last = next(e for e in reversed(events) if e.step_path == arg and e.type in ("step_passed", "step_imported"))
        node = node_for(ctx.recipe, arg)
        title = getattr(node, "title", None) or arg.rsplit("/", 1)[-1]
        label = f"{title}, imported from prior process" if last.type == "step_imported" else f"accepted {title}, attempt {last.attempt}"
        out = []
        if reg.get("output_sha256"):
            out.append(Item(raw, f"{label}: output", f"{_slug(raw)}-output.json", _redacted(ctx.log.cas.read(reg["output_sha256"])), "application/json"))
        for name, a in sorted((reg.get("artifacts") or {}).items()):
            suffix = PurePosixPath(a.get("filename", "")).suffix
            out.append(Item(raw, f"{label}: artifact {name}", f"{_slug(raw)}-{_slug(name)}{suffix}", _redacted(ctx.log.cas.read(a["sha256"])), a.get("media_type")))
        return out
    if kind == "record":
        assert arg is not None
        if arg not in ctx.log.state().steps:
            raise SmeError("sme.ref_unresolvable", f"{raw}: run {ctx.run_id} has no step {arg}")
        return [Item(raw, f"step record of {arg} (derived from the run's events)", f"{_slug(raw)}.md", _redacted(docs.step_record(ctx, arg).encode()), "text/markdown")]
    if kind == "summary":
        return [Item(raw, f"run summary of {ctx.run_id} (derived from the run's events)", "summary.md", _redacted(docs.summary(ctx).encode()), "text/markdown")]
    if kind == "events":
        return [Item(raw, f"event log of run {ctx.run_id}", "events.jsonl", _redacted(ctx.log.path.read_bytes()), "application/jsonl")]
    if kind == "project":
        assert arg is not None
        rel = PurePosixPath(arg.replace("\\", "/"))
        root = src.project.root.resolve()
        full = (root / rel).resolve()
        if rel.is_absolute() or ".." in rel.parts or not full.is_relative_to(root) or (rel.parts and rel.parts[0] in (".git", ".baton")):
            raise SmeError("sme.ref_unresolvable", f"{raw}: must be a file inside the project, outside .git and .baton")
        if not full.is_file():
            raise SmeError("sme.ref_unresolvable", f"{raw}: no such file in the project")
        return [Item(raw, f"project file {rel.as_posix()} (working tree)", f"{_slug(raw)}", _redacted(full.read_bytes()))]
    if kind == "facts":
        p = src.baton / "platform" / "facts.md"
        content = p.read_bytes() if p.is_file() else b"No platform facts are recorded yet.\n"
        return [Item(raw, "the project's platform facts", "facts.md", _redacted(content), "text/markdown")]
    if kind == "incident":
        inc = incidents(src.project.store.project_log().events()).get(arg or "")
        if inc is None:
            raise SmeError("sme.ref_unresolvable", f"{raw}: no incident {arg}")
        return [Item(raw, f"platform incident {arg} ({inc['status']})", f"{_slug(raw)}.json", _redacted(_json(inc)), "application/json")]
    if kind == "log":
        assert arg is not None
        run_id, _, rest = arg.partition(":")
        path, _, n = rest.partition("@")
        if not run_id or not path or (n and not n.isdigit()):
            raise SmeError("sme.bad_ref", f"{raw!r}: expected {REF_KINDS['log'][2]}")
        attempt = int(n) if n else _latest_attempt(src, run_id, path)
        f = src.project.home / "logs" / run_id / PurePosixPath(path) / f"attempt-{attempt}.log"
        if not f.is_file():
            raise SmeError("sme.ref_unresolvable", f"{raw}: no worker log on this machine ({f})")
        data = f.read_bytes()
        cut = len(data) > LOG_TAIL
        label = f"worker output of {path} attempt {attempt} in run {run_id} (redacted" + (", last 64 KiB)" if cut else ")")
        return [Item(raw, label, f"{_slug(raw)}.log", _redacted(data[-LOG_TAIL:]), "text/plain")]
    if kind == "profile":
        profiles = src.project.profiles()
        if arg not in profiles:
            raise SmeError("sme.ref_unresolvable", f"{raw}: no worker profile {arg!r} on this machine")
        return [Item(raw, f"worker profile {arg} (non-secret fields)", f"{_slug(raw)}.json", _redacted(_json(public_profile(profiles[arg]))), "application/json")]
    if kind == "doctor":
        from .doctor import doctor

        report = doctor(src.project, run_noop=False)
        return [Item(raw, "doctor report for this machine (no no-op runs)", "doctor.json", _redacted(_json(report)), "application/json")]
    if kind == "feedback":
        fb = [dict(e.data, seq=e.seq, ts=e.ts, actor=e.actor) for e in src.project.store.project_log().events() if e.type == "process_feedback"]
        return [Item(raw, "process feedback recorded in this project", "feedback.json", _redacted(_json(fb)), "application/json")]
    if kind == "stats":
        return [Item(raw, "process statistics of this project (derived from every run's events)", "stats.json", _json(stats(src.project.store)), "application/json")]
    if kind == "lessons":
        p = src.baton / "process" / "lessons.md"
        content = p.read_bytes() if p.is_file() else b"No process lessons are recorded yet.\n"
        return [Item(raw, "the project's process lessons", "lessons.md", _redacted(content), "text/markdown")]
    if kind == "recipe":
        if arg:
            try:
                loaded = src.project.recipe(arg)
            except Exception as e:
                raise SmeError("sme.ref_unresolvable", f"{raw}: {e}") from e
        elif ctx is not None:
            loaded = ctx.recipe
        else:
            raise SmeError("sme.ref_needs_run", f"{raw!r}: name the recipe (recipe:<id>@<version>) or consult with --run")
        return [Item(raw, f"recipe {loaded.recipe.ref} (recipe.yaml)", f"{_slug(raw)}.yaml", (loaded.root / "recipe.yaml").read_bytes(), "application/yaml")]
    raise AssertionError(kind)  # pragma: no cover


def _latest_attempt(src: Sources, run_id: str, path: str) -> int:
    try:
        log = src.project.store.run(run_id)
    except Exception as e:
        raise SmeError("sme.ref_unresolvable", f"no run {run_id}") from e
    n = log.state().step(path).attempt
    if n < 1:
        raise SmeError("sme.ref_unresolvable", f"{path} in run {run_id} has no attempt")
    return n


def public_profile(profile: WorkerProfile) -> dict[str, Any]:
    """A profile without secret values: ``auth.env`` keeps variable names only."""
    body = profile.model_dump(mode="json", exclude_none=True)
    auth = body.get("auth") or {}
    if "env" in auth:
        auth["env"] = sorted(auth["env"])
    return body


def automatic(src: Sources, subject: str) -> list[str]:
    """References every packet of this subject carries: for platform, the facts and each open incident with its log."""
    if subject != "platform":
        return []
    out = ["facts"]
    for inc in incidents(src.project.store.project_log().events()).values():
        if inc["status"] != "open":
            continue
        out.append(f"incident:{inc['id']}")
        out += [r for r in inc.get("refs") or [] if r.startswith("log:") and _log_exists(src, r)]
    return out


def _log_exists(src: Sources, raw: str) -> bool:
    try:
        resolve(src, raw, "platform")
    except SmeError:
        return False
    return True


def index(src: Sources, subject: str, used: set[str]) -> list[dict[str, str]]:
    """Everything else on record that this subject may ask for, by title only."""
    out: list[dict[str, str]] = []
    ctx = src.ctx

    def add(ref: str, title: str) -> None:
        if ref not in used:
            out.append({"ref": ref, "title": title})

    if ctx is not None and subject in ("project", "process"):
        from .packet import node_for

        for path, st in sorted(ctx.log.state().steps.items()):
            node = node_for(ctx.recipe, path)
            title = getattr(node, "title", None) or path.rsplit("/", 1)[-1]
            if ctx.record().registered(path) is not None:
                add(f"step:{path}", f"{title} ({st.state})")
            add(f"record:{path}", f"record of {title} ({st.state})")
        add("summary", f"run summary of {ctx.run_id}")
    if subject == "process":
        if ctx is not None:
            add("events", f"event log of run {ctx.run_id}")
            add("recipe", f"recipe {ctx.recipe.recipe.ref}")
        for ref in src.project.vendored():
            add(f"recipe:{ref}", f"vendored recipe {ref}")
        add("feedback", "process feedback recorded in this project")
        add("stats", "process statistics of this project")
        add("lessons", "the project's process lessons")
    if subject == "project" and ctx is None:
        for rid in src.project.store.run_ids():
            try:
                started = src.project.store.run(rid).events()[0].data
            except Exception:
                continue
            out.append({"ref": f"run:{rid}", "title": f"{started.get('title') or rid} (consult with --run {rid} to select its records)"})
    if subject == "platform":
        add("facts", "the project's platform facts")
        add("doctor", "doctor report for this machine")
        for inc in incidents(src.project.store.project_log().events()).values():
            add(f"incident:{inc['id']}", f"{inc.get('class')}/{inc.get('code')} on {inc.get('step_path')} of {inc.get('run')} ({inc['status']})")
        try:
            names = sorted(src.project.profiles())
        except Exception:
            names = []
        for name in names:
            add(f"profile:{name}", f"worker profile {name}")
        if ctx is not None:
            for path, st in sorted(ctx.log.state().steps.items()):
                for n in range(1, st.attempt + 1):
                    if (src.project.home / "logs" / ctx.run_id / PurePosixPath(path) / f"attempt-{n}.log").is_file():
                        add(f"log:{ctx.run_id}:{path}@{n}", f"worker output of {path} attempt {n}")
    return out


def assemble(src: Sources, subject: str, refs: list[str]) -> tuple[list[Item], list[str]]:
    """(material, references included automatically). Refuses, listing every problem, when any reference fails."""
    items: list[Item] = []
    problems: list[str] = []
    auto = [r for r in automatic(src, subject) if r not in refs]
    seen: set[str] = set()
    for raw in [*refs, *auto]:
        if raw in seen:
            continue
        seen.add(raw)
        try:
            items += resolve(src, raw, subject)
        except SmeError as e:
            problems.append(str(e))
    if problems:
        raise SmeError("sme.refs", "cannot assemble the expert packet: " + "; ".join(problems))
    names: set[str] = set()
    for i, it in enumerate(items):
        base = it.filename
        while it.filename in names:
            it.filename = f"{i}-{base}"
        names.add(it.filename)
    return items, auto


# ---------------------------------------------------------------------------
# Routing (§12.1): recipe sme.<subject>, else the vocabulary defaults;
# project.yaml sme.<subject>.preferred_profiles first
# ---------------------------------------------------------------------------


def requirements(subject: str, recipe: Any, vocab: Any) -> Requires:
    if recipe is not None and recipe.recipe.sme is not None and getattr(recipe.recipe.sme, subject) is not None:
        return getattr(recipe.recipe.sme, subject)
    return vocab.sme_defaults.get(subject) or Requires()


def workspace_mode(req: Requires) -> str:
    return "read" if "workspace_read" in req.capabilities else "none"


def eligible(subject: str, req: Requires, profiles: dict[str, WorkerProfile], vocab: Any, preferred: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from .routing import requirement_gaps, route_summary

    kept: dict[str, dict[str, Any]] = {}
    excluded = []
    for name in sorted(profiles):
        p = profiles[name]
        reasons = requirement_gaps(req, workspace_mode(req), p, vocab)
        if p.adapter == "manual":
            reasons = ["a person is never consulted directly; consult a proxy expert with --contact"]
        if reasons:
            excluded.append({"profile": name, "reasons": reasons})
        else:
            kept[name] = {**route_summary(name, p), "reasons": [f"meets the {subject} expert requirements"]}
    order = [n for n in preferred if n in kept]
    for n in order:
        kept[n]["reasons"].append(f"preferred for {subject} in project.yaml")
    order += [n for n in kept if n not in order]
    return [kept[n] for n in order], excluded


def handoff_refusal(req: Requires, adapter: str | None) -> str | None:
    """Why a pastable handoff is impossible for this expert, or None (§18 #17)."""
    if adapter == "command":
        return None  # a black box: Baton cannot tell what it relies on
    needed = set(req.capabilities) | ({"workspace_read"} if workspace_mode(req) == "read" else set())
    caps = [c for c in NO_HANDOFF if c in needed]
    if not caps:
        return None
    return (
        f"A pastable handoff is impossible: this expert relies on {', '.join(caps)} to answer, "
        "which means working on this machine, not from a pasted prompt. Continue in relay mode."
    )


# ---------------------------------------------------------------------------
# The consultation record
# ---------------------------------------------------------------------------


def new_id() -> str:
    return f"c_{secrets.token_hex(4)}"


@dataclass
class Where:
    """Where one consultation's events, files and blobs live."""

    run_id: str | None
    dir: Path
    log: EventLog
    cas: CAS


def where(project: Any, c_id: str, run_id: str | None) -> Where:
    store = project.store
    if run_id is not None:
        log = store.run(run_id)
        return Where(run_id, store.run_dir(run_id) / "sme" / c_id, log, log.cas)
    return Where(None, project.baton / "project" / "sme" / c_id, store.project_log(), CAS(project.baton / "project" / "cas"))


def locate(project: Any, c_id: str) -> Where:
    if not CONSULTATION_ID.match(c_id or ""):
        raise SmeError("sme.unknown", f"{c_id!r} is not a consultation id (c_xxxxxxxx)")
    store = project.store
    for e in store.project_log().events():
        if e.type == "sme_requested" and e.data.get("consultation") == c_id:
            return where(project, c_id, None)
    for rid in store.run_ids():
        for e in store.run(rid).events():
            if e.type == "sme_requested" and e.data.get("consultation") == c_id:
                return where(project, c_id, rid)
    raise SmeError("sme.unknown", f"no consultation {c_id}")


def consultation(events: list[Event], c_id: str) -> dict[str, Any]:
    """The consultation's turns, handoffs and promotions, from its events."""
    out: dict[str, Any] = {"consultation": c_id, "turns": [], "handoffs": [], "promotions": []}
    turns: dict[int, dict[str, Any]] = {}
    for e in events:
        d = e.data
        if d.get("consultation") != c_id:
            continue
        if e.type == "sme_requested":
            for k in ("subject", "run", "contact"):
                if k in d and k not in out:
                    out[k] = d[k]
            if d.get("mode") == "handoff":
                out["handoffs"].append({"seq": e.seq, "ts": e.ts, "path": d.get("path"), "sha256": d.get("handoff_sha256")})
            else:
                turns[d["turn"]] = {"turn": d["turn"], "requested": d, "requested_seq": e.seq, "requested_ts": e.ts, "answer": None}
        elif e.type == "sme_answered" and d.get("turn") in turns:
            turns[d["turn"]]["answer"] = dict(d, seq=e.seq, ts=e.ts)
        elif e.type == "sme_promoted":
            out["promotions"].append(dict(d, seq=e.seq, ts=e.ts))
    out["turns"] = [turns[k] for k in sorted(turns)]
    last = out["turns"][-1] if out["turns"] else None
    if last is None:
        out["state"] = "handed_off" if out["handoffs"] else "new"
    elif last["answer"] is None:
        out["state"] = "waiting_on_expert"
    elif last["answer"].get("awaiting"):
        out["state"] = "awaiting_reply"
    else:
        out["state"] = last["answer"]["status"]
    return out


# ---------------------------------------------------------------------------
# Packets
# ---------------------------------------------------------------------------


def turn_dir(w: Where, turn: int) -> Path:
    return w.dir / f"turn-{turn}"


def prior_items(w: Where, cons: dict[str, Any], upto: int) -> list[Item]:
    """Earlier turns: each question, answer, the expert's artifacts and the owner's attachments."""
    items: list[Item] = []
    for t in cons["turns"]:
        n = t["turn"]
        if n >= upto:
            break
        req = t["requested"]
        ans = t["answer"] or {"status": "no answer recorded"}
        summary = {"turn": n, "question": req.get("question"), "status": ans.get("status")}
        if ans.get("answer_sha256"):
            summary["answer"] = json.loads(w.cas.read(ans["answer_sha256"]))
        if ans.get("reasons"):
            summary["reasons"] = ans["reasons"]
        items.append(Item(f"turn:{n}", f"turn {n}: the question and the expert's answer", f"turn-{n}.json", _json(summary), "application/json"))
        for a in req.get("attachments") or []:
            p = turn_dir(w, n) / "packet" / a["path"]
            if p.is_file():
                items.append(Item(f"turn:{n}", a["label"], f"turn-{n}-{PurePosixPath(a['path']).name}", p.read_bytes(), a.get("media_type")))
        for name, a in sorted((ans.get("artifacts") or {}).items()):
            items.append(Item(f"turn:{n}", f"turn {n}: the expert's artifact {name}", f"turn-{n}-{_slug(name)}{PurePosixPath(a.get('filename', '')).suffix}", w.cas.read(a["sha256"]), a.get("media_type")))
    return items


def attachments(paths: list[str | Path], contact: str | None, root: Path) -> list[Item]:
    """Files the owner supplies (e.g. a person's reply), kept verbatim (redacted) with their hashes."""
    out = []
    for i, raw in enumerate(paths, start=1):
        p = Path(raw)
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.is_file():
            raise SmeError("sme.attachment", f"no file {raw}")
        label = "supplied by the owner" + (f"; the reply of {contact}" if contact else "")
        out.append(Item(f"attachment:{i}", f"attachment {p.name}, {label}", f"attachment-{i}-{_slug(p.name)}", _redacted(p.read_bytes())))
    return out


def render_instructions(manifest: dict[str, Any], items: dict[str, list[Item]], idx: list[dict[str, str]]) -> str:
    subject = manifest["subject"]
    lines = [
        f"# Expert consultation ({subject})",
        "",
        f"You are consulted as an expert on {SUBJECT_ROLE[subject]}.",
        f"This is turn {manifest['turn']} of consultation `{manifest['consultation']}`"
        + (f" about run `{manifest['run_id']}`." if manifest["run_id"] else " (project-level)."),
        "Answer the question from the material below. Do not do any step's work and do not change anything.",
        "",
        "## Question",
        "",
        manifest["question"] or "(No new question: this turn brings new material; continue the consultation with it.)",
        "",
    ]
    if manifest.get("contact"):
        lines += [
            "## Consulting a person",
            "",
            f"The owner needs input from a person: {manifest['contact']}. You cannot reach them, and you must never send",
            "anything on the owner's behalf. Prepare what the owner needs for the exchange (for example a draft email, a",
            "letter, or a talking-points sheet) as artifacts under `../result/artifacts/`, list them in `artifacts`, and set",
            "`awaiting` to who you are waiting on and what. The person's reply arrives in a later turn as an attachment",
            "supplied by the owner; treat it as their words, quote it faithfully, and say what it settles and what it does not.",
            "If you have your own access through which you can read their reply, include the reply verbatim as an artifact.",
            "",
        ]
    lines += ["## Material", "", "Each file is under `inputs/` with its provenance and SHA-256 (also in `manifest.json`).", ""]
    for group, title in (("prior", "Earlier turns"), ("attachments", "Attachments"), ("selected", "Selected for you"), ("auto", "Included automatically")):
        if not items.get(group):
            continue
        lines += [f"### {title}", ""]
        for it in items[group]:
            lines.append(f"- `inputs/{it.filename}`: {it.label} (`{it.ref}`, sha256 {it.sha256[:12]})")
            txt = it.text()
            if group == "prior" and txt is not None and len(it.content) <= TEXT_INLINE:
                lines += ["", "```", txt.rstrip("\n"), "```"]
        lines.append("")
    lines += [
        "## Everything else on record",
        "",
        "Titles only. If you need any of these to answer well, list its `ref` in `requested_refs`; the Director may",
        "include it in a follow-up.",
        "",
    ]
    lines += [f"- `{e['ref']}`: {e['title']}" for e in idx] or ["Nothing else."]
    lines += [
        "",
        "## Rules",
        "",
        "- Answer only from the material and your expertise; say plainly what the material does not show.",
        "- List the refs you relied on in `sources_used`. Never ask for or repeat secrets.",
        "- Set `suggests_retriage` to true only if the work's complexity looks misjudged.",
        "- This directory is the packet; do not modify it. Write artifacts under `../result/artifacts/`, then",
        "  `../result/result.json` **last**:",
        "",
        "```json",
        json.dumps(
            {
                "protocol": "baton-packet/1",
                "packet_sha256": "<copy from manifest.json>",
                "status": "completed | failed",
                "output": {"answer": "...", "confidence": "low | medium | high", "sources_used": [], "requested_refs": [], "suggests_retriage": False},
                "artifacts": [{"name": "<a name you choose>", "path": "artifacts/<file>"}],
                "notes": "",
            },
            indent=2,
        ),
        "```",
        "",
        "## Output schema",
        "",
        "```json",
        json.dumps(ANSWER_SCHEMA, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


@dataclass
class BuiltSme:
    dir: Path
    result_dir: Path
    manifest: dict[str, Any]
    entries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return self.manifest["packet_sha256"]


def build_packet(
    w: Where, *, consultation_id: str, turn: int, subject: str, question: str | None, contact: str | None,
    groups: dict[str, list[Item]], idx: list[dict[str, str]], worker: str, profile: WorkerProfile, deadline: str, workspace: str,
    recipe: str | None,
) -> BuiltSme:
    from .packet import _make_read_only, packet_digest, profile_sha256, remove_tree

    files: dict[str, bytes] = {}
    entries = []
    for group in ("prior", "attachments", "selected", "auto"):
        for it in groups.get(group) or []:
            rel = f"inputs/{it.filename}"
            files[rel] = it.content
            e = {"ref": it.ref, "label": it.label, "group": group, "path": rel, "sha256": it.sha256}
            if it.media_type:
                e["media_type"] = it.media_type
            entries.append(e)
    files["output_schema.json"] = _json(ANSWER_SCHEMA)
    files["index.json"] = _json(idx)
    manifest: dict[str, Any] = {
        "protocol": "baton-packet/1",
        "kind": "sme",
        "consultation": consultation_id,
        "turn": turn,
        "subject": subject,
        "run_id": w.run_id,
        "recipe": recipe,
        "question": question,
        "contact": contact,
        "workspace": workspace,
        "deadline": deadline,
        "worker_profile": worker,
        "worker_profile_sha256": profile_sha256(profile),
        "inputs": entries,
        "index": "index.json",
        "packet_sha256": None,
    }
    files["INSTRUCTIONS.md"] = render_instructions(manifest, groups, idx).encode("utf-8")
    manifest["packet_sha256"] = packet_digest(manifest, {k: hashlib.sha256(v).hexdigest() for k, v in files.items()})
    tdir = ensure_dir(turn_dir(w, turn))
    pdir, rdir = tdir / "packet", tdir / "result"
    remove_tree(pdir)
    remove_tree(rdir)
    for rel, content in files.items():
        (pdir / rel).parent.mkdir(parents=True, exist_ok=True)
        (pdir / rel).write_bytes(content)
    (pdir / "manifest.json").write_bytes(_json(manifest))
    _make_read_only(pdir)
    ensure_dir(rdir / "artifacts")
    return BuiltSme(pdir, rdir, manifest, entries)


# ---------------------------------------------------------------------------
# Intake of an answer
# ---------------------------------------------------------------------------


def intake(w: Where, turn: int, packet_sha256: str) -> dict[str, Any]:
    """``sme_answered`` data for a result the expert wrote (redacted in place first)."""
    from jsonschema import Draft202012Validator, FormatChecker

    rdir = turn_dir(w, turn) / "result"
    for p in sorted(rdir.rglob("*")):
        if p.is_file():
            red = _redacted(p.read_bytes())
            if red != p.read_bytes():
                p.write_bytes(red)
    reasons: list[str] = []
    try:
        result = json.loads(read_text(rdir / "result.json"))
    except (OSError, ValueError) as e:
        return {"status": "rejected", "reasons": [f"result.json is not readable JSON ({e})"]}
    if not isinstance(result, dict):
        return {"status": "rejected", "reasons": ["result.json is not a JSON object"]}
    if result.get("protocol") != "baton-packet/1":
        reasons.append(f"protocol must be baton-packet/1, got {result.get('protocol')!r}")
    if result.get("packet_sha256") != packet_sha256:
        reasons.append("packet_sha256 does not match this turn's packet")
    status = result.get("status")
    if status not in ("completed", "failed", "blocked"):
        reasons.append(f"status must be completed, failed or blocked, got {status!r}")
    output = result.get("output")
    if status == "completed":
        errs = sorted(Draft202012Validator(ANSWER_SCHEMA, format_checker=FormatChecker()).iter_errors(output), key=lambda e: list(e.path))
        reasons += [f"output{''.join(f'[{p!r}]' for p in e.path)}: {e.message}" for e in errs]
    arts: dict[str, Any] = {}
    for a in result.get("artifacts") or []:
        if not isinstance(a, dict) or not isinstance(a.get("name"), str) or not isinstance(a.get("path"), str):
            reasons.append(f"artifact entry {a!r} needs a name and a path")
            continue
        rel = PurePosixPath(a["path"])
        p = rdir / rel
        if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] != "artifacts" or not p.is_file():
            reasons.append(f"artifact {a['name']}: {a['path']} is not a file under artifacts/")
            continue
        if a["name"] in arts:
            reasons.append(f"artifact {a['name']} is listed twice")
            continue
        arts[a["name"]] = {"sha256": w.cas.put_file(p), "filename": rel.name, "path": f"result/{rel.as_posix()}"}
    if reasons:
        return {"status": "rejected", "reasons": reasons}
    data: dict[str, Any] = {"result_sha256": w.cas.put_file(rdir / "result.json")}
    if arts:
        data["artifacts"] = arts
    if status != "completed":
        notes = result.get("notes") or ""
        qs = result.get("questions_for_human") or []
        qs = [q.get("ask", str(q)) if isinstance(q, dict) else str(q) for q in qs]
        return {**data, "status": status, "reasons": [str(x) for x in ([notes] if notes else []) + list(qs)] or [f"the expert reported {status}"]}
    data.update(
        status="answered",
        answer_sha256=w.cas.put(canonical_json(output).encode("utf-8")),
        confidence=output["confidence"],
        suggests_retriage=output["suggests_retriage"],
        sources_used=output["sources_used"],
        requested_refs=output["requested_refs"],
    )
    if output.get("awaiting"):
        data["awaiting"] = output["awaiting"]
    return data


# ---------------------------------------------------------------------------
# Handoff (§18 #17)
# ---------------------------------------------------------------------------


def render_handoff(cons: dict[str, Any], subject: str, contact: str | None, items: list[Item], prior: list[Item]) -> str:
    lines = [
        f"# Briefing: {subject} expert",
        "",
        f"You are an expert on {SUBJECT_ROLE[subject]}. The project's owner will now talk with you directly.",
        "Everything you know about the project is below; it was assembled by the project's process runtime, with the",
        "provenance of each item. Answer from this material and your expertise, say plainly what it does not show, and",
        "never ask for secrets. Nothing you say changes the project's work unless the owner later records it there.",
        "",
    ]
    if contact:
        lines += [
            f"The owner needs input from a person: {contact}. Help the owner prepare for that exchange (drafts, talking",
            "points) and make sense of the replies the owner brings back. Never claim to have contacted anyone.",
            "",
        ]
    questions = [t["requested"].get("question") for t in cons["turns"] if t["requested"].get("question")]
    if questions:
        lines += ["## Questions so far", ""] + [f"- {q}" for q in questions] + [""]
    for title, group in (("Earlier exchange", prior), ("Material", items)):
        if not group:
            continue
        lines += [f"## {title}", ""]
        for it in group:
            lines += [f"### {it.label}", "", f"(`{it.ref}`, sha256 {it.sha256[:12]})", ""]
            txt = it.text()
            if txt is None:
                lines += [f"(binary file, {len(it.content)} bytes; not included)", ""]
            else:
                lines += ["```", txt.rstrip("\n"), "```", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The platform area (§12.3) and process records (§12.4)
# ---------------------------------------------------------------------------


def project_append(project: Any, etype: str, data: dict[str, Any], *, actor: str = "runtime") -> Event:
    from .locks import project_lock

    with project_lock(project.baton):
        return project.store.project_log().append(etype, actor=actor, data=data)


def incidents(events: list[Event]) -> dict[str, dict[str, Any]]:
    """Platform incidents from the project log, by id, with their status."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.type == "platform_incident_opened":
            out[e.data["incident"]] = {"id": e.data["incident"], **e.data, "opened_ts": e.ts, "opened_seq": e.seq, "status": "open"}
        elif e.type == "platform_incident_resolved" and e.data.get("incident") in out:
            inc = out[e.data["incident"]]
            inc.update(status="resolved", fix=e.data.get("fix"), resolved_ts=e.ts, resolved_by=e.actor, retried=e.data.get("retried", []))
    return out


def incident_for(events: list[Event], run_id: str, step_path: str, attempt: int | None) -> dict[str, Any] | None:
    for inc in incidents(events).values():
        if inc.get("run") == run_id and inc.get("step_path") == step_path and inc.get("attempt") == attempt:
            return inc
    return None


def _date(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")


FACTS_HEADER = "# Platform facts\n\nDurable infrastructure knowledge (§12.3): one entry per fact, with its source and date.\n\n"
LESSONS_HEADER = "# Process lessons\n\nProject-level lessons (§12.4): \"when X, do Y, because Z\", with origin and confirmation count.\n\n"


def _append_entry(path: Path, header: str, line: str) -> None:
    ensure_dir(path.parent)
    text = read_text(path) if path.is_file() else header
    if not text.endswith("\n"):
        text += "\n"
    path.write_bytes((text + line + "\n").encode("utf-8"))


def add_fact(baton: Path, text: str, source: str, when: datetime, *, observed: bool = False) -> str:
    entry = f"- {_date(when)} · {redact_text(' '.join(text.split()))} _(source: {source}" + ("; observed" if observed else "") + ")_"
    _append_entry(baton / "platform" / "facts.md", FACTS_HEADER, entry)
    return entry


def fact_known(baton: Path, text: str) -> bool:
    p = baton / "platform" / "facts.md"
    return p.is_file() and " ".join(text.split()) in read_text(p)


def add_lesson(baton: Path, text: str, origin: str, when: datetime) -> str:
    entry = f"- {redact_text(' '.join(text.split()))} _(origin: {origin}, {_date(when)}; confirmations: 1)_"
    _append_entry(baton / "process" / "lessons.md", LESSONS_HEADER, entry)
    return entry


def write_proposal(baton: Path, c_id: str, turn: int, text: str, note: str, subject: str, when: datetime) -> Path:
    p = baton / "process" / "proposals" / f"{c_id}-turn-{turn}.md"
    ensure_dir(p.parent)
    body = [
        f"# Process proposal from consultation {c_id} (turn {turn})",
        "",
        f"Subject: {subject}. Promoted {format_ts(when)} with the owner's agreement: \"{redact_text(note)}\"",
        "",
        "A recipe or configuration change is applied by the recipe's maintainer as a new recipe version and re-vendored;",
        "the runtime never edits a vendored recipe in place.",
        "",
        "## Proposal",
        "",
        redact_text(text).rstrip("\n"),
        "",
    ]
    p.write_bytes("\n".join(body).encode("utf-8"))
    return p


# ---------------------------------------------------------------------------
# Statistics (§9.2, §12.4), keyed by qualified step id (§5.8)
# ---------------------------------------------------------------------------

_ITER = re.compile(r"^i\d+$")


def qualified(recipe_ref: str, step_path: str) -> str:
    """``<recipe>@<v>/<step_path>`` with instance ids and iterations dropped (``slices/x7f3/i2/implement`` -> ``slices/implement``)."""
    parts = step_path.split("/")
    out: list[str] = []
    i = 0
    while i < len(parts):
        out.append(parts[i])
        i += 3 if i + 2 < len(parts) and _ITER.match(parts[i + 2]) else 1
    return f"{recipe_ref}/{'/'.join(out)}"


def stats(store: Any) -> dict[str, Any]:
    """Attempts, outcomes, failure classes, time per step, iterations and review statistics across every run."""
    steps: dict[str, dict[str, Any]] = {}
    reviews: dict[str, dict[str, Any]] = {}
    iterations: dict[str, list[int]] = {}

    def step(q: str) -> dict[str, Any]:
        return steps.setdefault(q, {"runs": set(), "attempts": 0, "passed": 0, "rejected": 0, "gate_failures": 0, "timeouts": 0,
                                    "escalations": {}, "failure_classes": {}, "durations_s": []})

    for rid in store.run_ids():
        try:
            events = store.run(rid).events()
        except Exception:
            continue
        if not events or events[0].type != "run_started":
            continue
        recipe = events[0].data.get("recipe") or "?"
        dispatched: dict[tuple[str, int], tuple[datetime, str]] = {}
        evals: dict[str, list[dict[str, Any]]] = {}
        inst_iters: dict[str, int] = {}
        for e in events:
            if e.type == "iteration_started" and e.step_path:
                inst_iters[e.step_path] = max(inst_iters.get(e.step_path, 0), int(e.data.get("iteration") or 0))
            if not e.step_path or e.type not in (
                "dispatched", "step_passed", "result_rejected", "gate_failed", "step_timed_out", "step_escalated",
                "failure_classified", "result_submitted", "findings_recorded", "finding_dispositioned",
            ):
                continue
            q = qualified(recipe, e.step_path)
            s = step(q)
            s["runs"].add(rid)
            if e.type == "dispatched":
                s["attempts"] += 1
                dispatched[(e.step_path, e.attempt or 0)] = (datetime.fromisoformat(e.ts.replace("Z", "+00:00")), e.data.get("profile") or "?")
            elif e.type == "result_submitted":
                d = dispatched.get((e.step_path, e.attempt or 0))
                if d:
                    s["durations_s"].append((datetime.fromisoformat(e.ts.replace("Z", "+00:00")) - d[0]).total_seconds())
            elif e.type == "step_passed" and not e.data.get("confirmed"):
                s["passed"] += 1
            elif e.type == "result_rejected":
                s["rejected"] += 1
            elif e.type == "gate_failed" and not e.data.get("advisory"):
                s["gate_failures"] += 1
            elif e.type == "step_timed_out":
                s["timeouts"] += 1
            elif e.type == "step_escalated":
                r = e.data.get("reason") or "?"
                s["escalations"][r] = s["escalations"].get(r, 0) + 1
            elif e.type == "failure_classified":
                c = e.data.get("class") or "?"
                s["failure_classes"][c] = s["failure_classes"].get(c, 0) + 1
            elif e.type == "findings_recorded":
                reviewer = e.data.get("reviewer") or dispatched.get((e.step_path, e.attempt or 0), (None, "?"))[1]
                key = f"{reviewer} @ {qualified(recipe, e.data.get('line', e.step_path).split('#')[0])}#{e.data.get('line', '#').split('#')[-1]}"
                r = reviews.setdefault(key, {"reviewer": reviewer, "line": qualified(recipe, e.data.get("line", e.step_path).split("#")[0]),
                                             "evaluations": 0, "by_severity": {}, "dispositions": {}, "iterations_to_clean": []})
                r["evaluations"] += 1
                for f in e.data.get("findings") or []:
                    if f.get("status") == "open" and not f.get("carried"):
                        sev = f.get("severity") or "?"
                        r["by_severity"][sev] = r["by_severity"].get(sev, 0) + 1
                evals.setdefault(e.data.get("line") or e.step_path, []).append({"key": key, "blocking": bool(e.data.get("blocking"))})
            elif e.type == "finding_dispositioned":
                line = e.data.get("line") or ""
                ks = [x["key"] for x in evals.get(line, [])]
                if ks:
                    disp = e.data.get("disposition") or "?"
                    rd = reviews[ks[-1]]["dispositions"]
                    rd[disp] = rd.get(disp, 0) + 1
        for line, ev in evals.items():
            for i, x in enumerate(ev, start=1):
                if not x["blocking"]:
                    reviews[x["key"]]["iterations_to_clean"].append(i)
                    break
        for inst, n in inst_iters.items():
            iterations.setdefault(qualified(recipe, inst + "/i1/x").rsplit("/", 1)[0], []).append(n)
    out_steps = {}
    for q, s in sorted(steps.items()):
        d = s.pop("durations_s")
        out_steps[q] = {**s, "runs": len(s["runs"]), "mean_duration_s": round(sum(d) / len(d), 3) if d else None, "max_duration_s": max(d) if d else None}
    return {
        "steps": out_steps,
        "iterations": {g: {"instances": len(v), "mean": round(sum(v) / len(v), 3), "max": max(v)} for g, v in sorted(iterations.items())},
        "reviews": dict(sorted(reviews.items())),
    }
