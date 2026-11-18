"""Interaction requests (``baton-interaction/1``): everything Baton asks the owner, as data (Decisions 0169, 0170).

A request is built from a pending owner act, never stored: every pending
decision ``status`` and ``board`` list (``engine.pending_decisions``), each
blocked step's questions among them. It says what is asked, the shape of the
answer, what to show for context and the choices with their effects; it says
nothing about how it is drawn and carries no script. Any client renders it in
its own way (the Director in conversation, an answer file, a page); every
answer comes back through ``answer``, which records it through the same path as
``decide`` would, stamped with the request's id and the renderer (``via``).

**Ids** (Decision 0170, item 10). A request's id is derived from the run, the
ref, the kind, the sequence number of the event that opened or last changed the
act, and what the request asks (its prompt, reasons, questions, signals,
choices, and for a file the owner may edit, its current hash). So it is stable
while nothing about the ask changes, and changes when anything does; an answer
to an old id is refused as stale (``interaction.stale``).

Call-time confirmations that return ``needs_owner`` (push, permissions,
vendoring, policy, the notes offer, bind, attest) are not requests: they have
no pending state, and the Director asks for them at the moment (item 9).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from typing import Any, Iterator

from jsonschema import Draft202012Validator

from .packet import EngineError

FORMAT = "baton-interaction/1"

#: The renderer an answer names when none is given: the Director, in conversation.
DEFAULT_VIA = "conversation"

#: The words recorded when a renderer other than conversation gives no note (Decision 0170, item 1).
CONFIRMED_IN = "confirmed in {via}"

#: A short title per kind of request, in the owner's terms. The message is the pending decision's own prompt.
TITLES: dict[str, str] = {
    "gate": "Your approval is needed",
    "triage": "Is this the right size for the work?",
    "protected": "A change to files that are protected",
    "frame": "Which parts to start",
    "escalation": "Some work stopped and needs you",
    "blocked": "Questions for you",
    "wait_expired": "Something being waited for did not happen in time",
    "iteration_limit": "A repeated piece of work has not settled",
    "baseline": "The starting picture of your project",
    "skip_notice": "Something was skipped outside the process",
    "rating_signal": "The work may need re-sizing",
    "publish_conflict": "A file is already where the work wants to write",
    "drift": "A delivered file was changed afterwards",
}

_VOLATILE = ("request_id", "web_advice", "incident")


# ---------------------------------------------------------------------------
# Kinds and ids
# ---------------------------------------------------------------------------


def kind_of(ctx: Any, p: dict[str, Any]) -> str:
    """The request kind of a pending decision: the label kind of its options (``labels.yaml``)."""
    k = p.get("kind")
    if k == "gate":
        opened = ctx.record().last("human_gate_opened", p["ref"], p.get("attempt"))
        gate = opened.data.get("gate") if opened else None
        return {"triage": "triage", "protected": "protected", "select": "frame"}.get(gate, "gate") if isinstance(gate, str) else "gate"
    if k == "escalation":
        return {"blocked": "blocked", "wait_expired": "wait_expired"}.get(p.get("reason") or "", "escalation")
    return str(k)


def _opened_seq(ctx: Any, p: dict[str, Any]) -> int | None:
    """The sequence number of the event that opened or last changed the act, where one event does."""
    k, ref = p.get("kind"), p.get("ref")
    if k == "gate":
        ev = ctx.record().last("human_gate_opened", ref, p.get("attempt"))
    elif k == "escalation":
        ev = ctx.record().last("step_escalated", ref)
    elif k == "iteration_limit":
        ev = next((e for e in reversed(ctx.log.events()) if e.type == "iteration_limit_reached" and e.step_path == ref), None)
    elif k == "rating_signal":
        seqs = [s.get("seq") for s in p.get("signals") or [] if isinstance(s.get("seq"), int)]
        return max(seqs) if seqs else None
    elif k == "skip_notice":
        return int(str(ref).split(":", 1)[1])
    else:
        return None
    return ev.seq if ev is not None else None


def _file_sha(ctx: Any, p: dict[str, Any]) -> str | None:
    """The current hash of a file the owner may edit while the act is pending (the adoption baseline)."""
    if p.get("kind") != "baseline" or not p.get("path"):
        return None
    f = ctx.store.root / p["path"]
    return hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else None


def _asked(p: dict[str, Any]) -> dict[str, Any]:
    """What a pending decision asks, without what is computed from elsewhere (``next``, advice, incidents)."""
    out = {k: v for k, v in p.items() if k not in _VOLATILE}
    out["options"] = [{k: v for k, v in o.items() if k != "next"} for o in p.get("options") or []]
    return out


def request_id(ctx: Any, p: dict[str, Any]) -> str:
    """The request id of a pending decision (Decision 0170, item 10)."""
    basis = [ctx.run_id, p.get("ref"), kind_of(ctx, p), _opened_seq(ctx, p), _file_sha(ctx, p), _asked(p)]
    raw = json.dumps(basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "ir_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def stamp(ctx: Any, pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give each pending decision its ``request_id`` (``status``, ``board`` and every mutating call's ``pending_decisions``)."""
    for p in pending:
        p["request_id"] = request_id(ctx, p)
    return pending


# ---------------------------------------------------------------------------
# Building a request
# ---------------------------------------------------------------------------


def _text(cid: str, label: str, text: str) -> dict[str, Any]:
    return {"id": cid, "kind": "text", "label": label, "text": text}


def _context(p: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    reasons = [str(r) for r in p.get("reasons") or [] if str(r).strip()]
    if reasons:
        out.append(_text("reasons", "Why", "\n".join(reasons)))
    if p.get("signals"):
        out.append({"id": "signals", "kind": "table", "label": "What was suggested", "columns": ["from", "suggests", "because"],
                    "rows": [[s.get("step_path"), s.get("suggested"), s.get("reason")] for s in p["signals"]]})
    if p.get("path"):
        out.append(_text("path", "File", str(p["path"])))
    return out


def questions_schema(questions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """A blocked step's questions as an answer schema and its prefill (best guesses).

    One field per question, named by its id: a string, or for a multi-select question a list of strings. A
    question's options are suggestions (``examples``); the owner's answer may differ, as in conversation.
    """
    props: dict[str, Any] = {}
    prefill: dict[str, Any] = {}
    for q in questions:
        labels = [str(o.get("label")) for o in q.get("options") or [] if o.get("label")]
        if q.get("multi_select"):
            f: dict[str, Any] = {"type": "array", "items": {"type": "string", "minLength": 1, **({"examples": labels} if labels else {})}, "minItems": 1}
        else:
            f = {"type": "string", "minLength": 1, **({"examples": labels} if labels else {})}
        f["title"] = q.get("ask") or q["id"]
        if q.get("why"):
            f["description"] = q["why"]
        props[q["id"]] = f
        if q.get("best_guess"):
            prefill[q["id"]] = [q["best_guess"]] if q.get("multi_select") else q["best_guess"]
    required = [q["id"] for q in questions if q.get("priority", "needed") == "needed"]
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}, prefill


def _choice_answer(api: Any, ctx: Any, p: dict[str, Any], kind: str, decision: str) -> dict[str, Any] | None:
    """The fields a choice needs besides itself, as ``{schema, prefill, renderable}``, or ``None``."""
    if kind == "blocked" and decision == "retry" and p.get("questions"):
        schema, prefill = questions_schema(p["questions"])
        return {"schema": schema, "prefill": prefill, "renderable": True}
    if kind == "frame" and decision == "select":
        from .frame import frame_output

        parts = frame_output(ctx, p["attempt"]).get("parts") or []
        ids = [q.get("id") for q in parts]
        return {"schema": {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {
            "items": {"type": "array", "uniqueItems": True, "title": "Parts to include",
                      "items": {"type": "string", "oneOf": [{"const": q.get("id"), "title": q.get("label") or q.get("id")} for q in parts]
                                if ids else {"enum": []}}}}},
                "prefill": {"items": []}, "renderable": True}
    if kind == "publish_conflict" and decision == "alternate":
        return {"schema": {"type": "object", "additionalProperties": False, "properties": {
            "path": {"type": "string", "minLength": 1, "title": "Where to save the new one",
                     "description": "A path in the project; left out, a name next to the existing file is chosen"}}},
                "prefill": {}, "renderable": True}
    return None


def build(api: Any, ctx: Any, p: dict[str, Any]) -> dict[str, Any]:
    """The full request for one pending decision (with its ``request_id``)."""
    kind = kind_of(ctx, p)
    choices = []
    for o in p.get("options") or []:
        c = {k: o[k] for k in ("decision", "label", "effect", "next") if k in o}
        ans = _choice_answer(api, ctx, p, kind, o["decision"])
        if ans is not None:
            c["answer"] = ans
        choices.append(c)
    return {
        "format": FORMAT,
        "id": p.get("request_id") or request_id(ctx, p),
        "run": ctx.run_id,
        "ref": p.get("ref"),
        "step_path": p.get("step_path"),
        **({"attempt": p["attempt"]} if p.get("attempt") is not None else {}),
        "kind": kind,
        "title": TITLES.get(kind, "Your decision is needed"),
        "message": p.get("prompt") or "; ".join(str(r) for r in p.get("reasons") or []) or TITLES.get(kind, ""),
        "context": _context(p),
        "choices": choices,
        "hints": {},
        "extensions": {},
        "needs_confirmation": True,
    }


def summary(req: dict[str, Any]) -> dict[str, Any]:
    """A request in a listing."""
    return {k: req[k] for k in ("id", "run", "ref", "kind", "title", "message") if k in req}


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def answering(request: str, via: str) -> Iterator[None]:
    """Stamp every ``human_decision`` recorded inside with ``request_id`` and ``via`` (§8.2)."""
    from . import store

    token = store.DECISION_STAMP.set({"request_id": request, "via": via})
    try:
        yield
    finally:
        store.DECISION_STAMP.reset(token)


def words_for(note: str, via: str) -> str:
    """The owner's words to record: the note, or a fixed phrase naming the renderer (Decision 0170, item 1).

    In conversation the Director always has the owner's own words, so a note is required there.
    """
    if note.strip():
        return note
    if via == DEFAULT_VIA:
        raise EngineError("answer.note_required", "--note is required: the owner's words, including their confirmation")
    return CONFIRMED_IN.format(via=via)


def check_values(schema: dict[str, Any], values: Any, *, partial: bool = False) -> None:
    """Check an answer's values against the choice's or request's schema; raises ``answer.invalid``."""
    if partial:
        schema = {**schema, "required": []}
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '(answer)'}: {e.message}"
              for e in Draft202012Validator(schema).iter_errors(values)]
    if errors:
        raise EngineError("answer.invalid", "the answer does not fit the request: " + "; ".join(errors))


ANSWER_KEYS = {"choice", "values", "words", "partial", "via"}


def parse_answer(answer: Any) -> dict[str, Any]:
    """An answer: ``{choice?, values?, words?, partial?, via?}``."""
    if not isinstance(answer, dict):
        raise EngineError("answer.invalid", "an answer is an object {choice, values, words, partial}")
    extra = sorted(set(answer) - ANSWER_KEYS)
    if extra:
        raise EngineError("answer.invalid", f"unknown keys in the answer: {', '.join(extra)}")
    if answer.get("values") is not None and not isinstance(answer["values"], dict):
        raise EngineError("answer.invalid", "values must be an object of field values")
    if answer.get("words") is not None and not (isinstance(answer["words"], dict)
                                                and all(isinstance(v, str) for v in answer["words"].values())):
        raise EngineError("answer.invalid", "words must map a field to the owner's words for it")
    return answer


# ---------------------------------------------------------------------------
# The format (formats/baton-interaction-1.schema.json)
# ---------------------------------------------------------------------------

_ANSWER_SPEC = {
    "type": "object",
    "description": "The fields an answer gives: a JSON Schema in the renderable subset, its prefilled values, and whether it is in the subset",
    "required": ["schema", "prefill", "renderable"],
    "properties": {"schema": {"type": "object"}, "prefill": {"type": "object"}, "renderable": {"type": "boolean"}},
    "additionalProperties": False,
}


def json_schema() -> dict[str, Any]:
    """``baton-interaction/1``: one request (Decisions 0169, 0170)."""
    from .versions import DRAFT_2020_12

    return {
        "$schema": DRAFT_2020_12,
        "title": FORMAT,
        "type": "object",
        "required": ["format", "id", "run", "ref", "kind", "title", "message", "context", "choices", "hints", "extensions",
                     "needs_confirmation"],
        "properties": {
            "format": {"const": FORMAT},
            "id": {"type": "string", "pattern": "^ir_[0-9a-f]{20}$"},
            "run": {"type": "string", "minLength": 1},
            "ref": {"type": "string", "minLength": 1, "description": "What is decided: as decide names it"},
            "step_path": {"type": ["string", "null"]},
            "attempt": {"type": "integer", "minimum": 1},
            "kind": {"type": "string", "description": "The kind of ask, as defaults/labels.yaml keys it, or person_step"},
            "title": {"type": "string", "minLength": 1},
            "message": {"type": "string"},
            "context": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "kind", "label"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "kind": {"enum": ["text", "table", "document", "image"]},
                        "label": {"type": "string"},
                        "text": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {"type": "array", "items": {"type": "array"}},
                        "ref": {"type": "string", "description": "Fetched through interaction(id, item)"},
                    },
                },
            },
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["decision", "label", "effect"],
                    "properties": {
                        "decision": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                        "effect": {"type": "string"},
                        "next": {},
                        "answer": _ANSWER_SPEC,
                    },
                    "additionalProperties": False,
                },
            },
            "answer": _ANSWER_SPEC,
            "hints": {"type": "object"},
            "extensions": {"type": "object", "description": "extensions.<renderer kind>: ignored by every other renderer"},
            "needs_confirmation": {"type": "boolean"},
        },
        "additionalProperties": False,
    }
