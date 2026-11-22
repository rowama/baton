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
    "locked": "A change to files you approved",
    "locked_change": "Files you approved were changed",
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
    "person_step": "Your part of the work",
    "open_questions": "Choices to confirm",
}

#: The message of an ``open_questions`` request (Decision 0184).
OPEN_QUESTIONS_MESSAGE = ("While doing this part, the work made these choices on a best guess. Confirm or correct any of them; "
                          "nothing waits for your answers.")

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
        return {"triage": "triage", "protected": "protected", "locked": "locked", "select": "frame"}.get(gate, "gate") if isinstance(gate, str) else "gate"
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
    elif k == "open_questions":
        return p.get("seq")
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


def _open_asked(ctx: Any, p: dict[str, Any], kind: str) -> list[Any]:
    """The open questions a pending decision's choices offer (Decision 0184): part of what it asks, so a change to them
    gives a new id. Empty (and left out of the id) when there are none, so other ids are unchanged."""
    if not any(k == kind for k, _d in _WITH_OPEN_ANSWERS) or not p.get("ref"):
        return []
    from .questions import open_questions

    ref = p["ref"]
    return [[o["step_path"], o["seq"], [q["id"] for q in o["questions"]]] for o in open_questions(ctx.recipe, ctx.log.events())
            if o["step_path"] == ref or o["step_path"].startswith(ref + "/")]


def request_id(ctx: Any, p: dict[str, Any]) -> str:
    """The request id of a pending decision (Decision 0170, item 10)."""
    kind = kind_of(ctx, p)
    basis = [ctx.run_id, p.get("ref"), kind, _opened_seq(ctx, p), _file_sha(ctx, p), _asked(p)]
    open_ = _open_asked(ctx, p, kind)
    if open_:
        basis.append(open_)
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


def open_questions_schema(entries: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Open questions (Decision 0184) as an answer schema with nothing required, and its prefill; ``None`` when there are none.

    A question id that two asking steps both ask is left out: it is answered on its own step's request."""
    ids = [q["id"] for o in entries for q in o["questions"]]
    qs = [q for o in entries for q in o["questions"] if ids.count(q["id"]) == 1]
    if not qs:
        return None
    schema, prefill = questions_schema(qs)
    schema["required"] = []
    return schema, prefill


def open_questions_id(ctx: Any, entry: dict[str, Any]) -> str:
    """The request id of one asking step's open questions: its run, step, result and what is still asked."""
    basis = [ctx.run_id, entry["step_path"], "open_questions", entry["seq"], entry["questions"]]
    raw = json.dumps(basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "ir_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def build_open_questions(ctx: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """The request for one asking step's open questions (``kind: open_questions``): one choice, ``answer``, whose
    fields are the questions, none required, best guesses prefilled. Not a pending decision: nothing waits for it."""
    from . import labels

    schema, prefill = open_questions_schema([entry]) or ({"type": "object", "properties": {}, "required": [], "additionalProperties": False}, {})
    return {
        "format": FORMAT,
        "id": open_questions_id(ctx, entry),
        "run": ctx.run_id,
        "ref": entry["step_path"],
        "step_path": entry["step_path"],
        "attempt": entry["attempt"],
        "kind": "open_questions",
        "title": TITLES["open_questions"],
        "message": OPEN_QUESTIONS_MESSAGE,
        "context": [],
        "choices": [{**labels.option("open_questions", "answer"), "answer": {"schema": schema, "prefill": prefill, "renderable": True}}],
        "hints": {},
        "extensions": {},
        "needs_confirmation": True,
    }


#: Choices that may carry answers to the open questions under their ref (Decision 0184, item 3).
_WITH_OPEN_ANSWERS = {("iteration_limit", "retry"), ("escalation", "retry"), ("gate", "reject")}


def _choice_answer(api: Any, ctx: Any, p: dict[str, Any], kind: str, decision: str) -> dict[str, Any] | None:
    """The fields a choice needs besides itself, as ``{schema, prefill, renderable}``, or ``None``."""
    if kind == "blocked" and decision == "retry" and p.get("questions"):
        schema, prefill = questions_schema(p["questions"])
        return {"schema": schema, "prefill": prefill, "renderable": True}
    if (kind, decision) in _WITH_OPEN_ANSWERS and p.get("ref"):
        from .questions import open_questions

        ref = p["ref"]
        entries = [o for o in open_questions(ctx.recipe, ctx.log.events()) if o["step_path"] == ref or o["step_path"].startswith(ref + "/")]
        built = open_questions_schema(entries)
        if built is not None:
            return {"schema": built[0], "prefill": built[1], "renderable": True}
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
    extra_context, hints = gate_context(ctx, p) if kind == "gate" else ([], {})
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
        "context": _context(p) + extra_context,
        "choices": choices,
        "hints": hints,
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


ANSWER_KEYS = {"choice", "values", "words", "partial", "via", "artifacts"}


def parse_answer(answer: Any) -> dict[str, Any]:
    """An answer: ``{choice?, values?, words?, partial?, via?}``."""
    if not isinstance(answer, dict):
        raise EngineError("answer.invalid", "an answer is an object {choice, values, words, partial}")
    extra = sorted(set(answer) - ANSWER_KEYS)
    if extra:
        raise EngineError("answer.invalid", f"unknown keys in the answer: {', '.join(extra)}")
    if answer.get("artifacts") is not None and not (isinstance(answer["artifacts"], dict)
                                                    and all(v is None or (isinstance(v, str) and v) for v in answer["artifacts"].values())):
        raise EngineError("answer.invalid", "artifacts must map a file's name to its path")
    if answer.get("values") is not None and not isinstance(answer["values"], dict):
        raise EngineError("answer.invalid", "values must be an object of field values")
    if isinstance(answer.get("values"), dict):  # a field left empty in an answer file is not given
        answer = {**answer, "values": {k: v for k, v in answer["values"].items() if v is not None}}
    if isinstance(answer.get("artifacts"), dict):
        answer = {**answer, "artifacts": {k: v for k, v in answer["artifacts"].items() if v}}
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
                        "media_type": {"type": "string"},
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
            "files": {
                "type": "array",
                "description": "A person's step: the files it declares, given by path in the answer (artifacts: {name: path})",
                "items": {"type": "object", "required": ["name", "required"], "additionalProperties": False,
                          "properties": {"name": {"type": "string"}, "required": {"type": "boolean"}, "media_type": {"type": "string"}}},
            },
            "hints": {"type": "object"},
            "extensions": {"type": "object", "description": "extensions.<renderer kind>: ignored by every other renderer"},
            "needs_confirmation": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# The renderable subset of JSON Schema (Decision 0170, item 2)
# ---------------------------------------------------------------------------

_META = {"title", "description", "default", "examples", "$comment", "$schema", "$id"}
_STRING = _META | {"type", "enum", "const", "oneOf", "format", "minLength", "maxLength", "pattern"}
_NUMBER = _META | {"type", "enum", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
_BOOLEAN = _META | {"type"}
_ARRAY = _META | {"type", "items", "minItems", "maxItems", "uniqueItems"}
_OBJECT = _META | {"type", "properties", "required", "additionalProperties"}
_FORMATS = {"date", "date-time", "time", "email", "uri"}


def _choice_list(one_of: Any) -> bool:
    """``oneOf`` as labelled choices: ``[{const, title?}]``."""
    return isinstance(one_of, list) and bool(one_of) and all(
        isinstance(o, dict) and "const" in o and set(o) <= {"const", "title", "description"} for o in one_of)


def subset_problems(schema: Any, where: str = "(answer)", depth: int = 0) -> list[str]:
    """Where a schema leaves the renderable subset; empty when it is inside.

    Objects with named fields; strings (choices as ``enum`` or labelled ``oneOf`` consts, suggestions as
    ``examples``, a ``format``); numbers and integers with bounds; booleans; lists of choices; lists of objects (a
    table, whose cells are not lists or objects); nested objects (a group). No ``$ref``, conditions or computed
    fields; one type per field.
    """
    if not isinstance(schema, dict):
        return [f"{where}: not a schema object"]
    t = schema.get("type")
    if not isinstance(t, str):
        return [f"{where}: needs exactly one type"]
    allowed = {"string": _STRING, "number": _NUMBER, "integer": _NUMBER, "boolean": _BOOLEAN, "array": _ARRAY, "object": _OBJECT}.get(t)
    if allowed is None:
        return [f"{where}: type {t!r} is not renderable"]
    out = [f"{where}: {k!r} is outside the renderable subset" for k in sorted(set(schema) - allowed)]
    if t == "string":
        if "oneOf" in schema and not _choice_list(schema["oneOf"]):
            out.append(f"{where}: oneOf is only for labelled choices [{{const, title}}]")
        if "format" in schema and schema["format"] not in _FORMATS:
            out.append(f"{where}: format {schema['format']!r} is not renderable")
    elif t == "object":
        if schema.get("additionalProperties") not in (None, False):
            out.append(f"{where}: additionalProperties may only be false")
        props = schema.get("properties") or {}
        if not props:
            out.append(f"{where}: an object needs named fields")
        if depth >= 3:
            out.append(f"{where}: nested too deeply")
        for k, sub in props.items():
            out += subset_problems(sub, f"{where}.{k}" if where != "(answer)" else k, depth + 1)
    elif t == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            out.append(f"{where}: a list needs one items schema")
        elif items.get("type") == "object":  # a table: one row per item
            for k, cell in (items.get("properties") or {}).items():
                if isinstance(cell, dict) and cell.get("type") in ("object", "array"):
                    out.append(f"{where}[].{k}: a table's cells are not lists or groups")
            out += subset_problems(items, f"{where}[]", depth + 1)
        elif items.get("type") == "string" and ("enum" in items or "oneOf" in items or "examples" in items):
            out += subset_problems(items, f"{where}[]", depth + 1)  # several choices
        elif items.get("type") in ("string", "number", "integer"):
            out += subset_problems(items, f"{where}[]", depth + 1)
        else:
            out.append(f"{where}: a list holds choices, values or table rows")
    return out


def renderable(schema: Any) -> bool:
    return isinstance(schema, dict) and schema.get("type") == "object" and not subset_problems(schema)


# ---------------------------------------------------------------------------
# Hints (Decision 0170, items 3 and 8)
# ---------------------------------------------------------------------------

WIDGETS = ("radio", "dropdown", "checkboxes", "textarea", "table", "slider")
HINT_KEYS = {"order", "groups", "fields", "summary"}
FIELD_HINT_KEYS = {"widget", "help", "label"}


def _field_names(schema: Any, prefix: str = "") -> set[str]:
    """Every field a hint may name: top-level fields and, dotted, the fields of groups and table rows."""
    out: set[str] = set()
    if not isinstance(schema, dict):
        return out
    for k, sub in (schema.get("properties") or {}).items():
        name = f"{prefix}{k}"
        out.add(name)
        if isinstance(sub, dict) and sub.get("type") == "object":
            out |= _field_names(sub, f"{name}.")
        elif isinstance(sub, dict) and sub.get("type") == "array" and isinstance(sub.get("items"), dict):
            out |= _field_names(sub["items"], f"{name}.")
    return out


def hint_problems(hints: Any, schema: dict[str, Any] | None) -> list[str]:
    """Where a hints file is malformed or names a field the schema does not have; empty when it is good."""
    if not isinstance(hints, dict):
        return ["hints must be a mapping of order, groups, fields and summary"]
    out = [f"unknown hint {k!r} (the hints are {', '.join(sorted(HINT_KEYS))})" for k in sorted(set(hints) - HINT_KEYS)]
    names = _field_names(schema or {})

    def known(name: Any, where: str) -> None:
        if not isinstance(name, str) or name not in names:
            out.append(f"{where}: {name!r} is not a field of the output schema ({', '.join(sorted(names)) or 'none'})")

    for key in ("order", "summary"):
        if key in hints:
            if not isinstance(hints[key], list):
                out.append(f"{key} must be a list of field names")
            else:
                for n in hints[key]:
                    known(n, key)
    if "groups" in hints:
        if not isinstance(hints["groups"], list):
            out.append("groups must be a list of {title, fields}")
        for i, g in enumerate(hints.get("groups") or [] if isinstance(hints.get("groups"), list) else []):
            if not isinstance(g, dict) or set(g) != {"title", "fields"} or not isinstance(g.get("title"), str) or not isinstance(g.get("fields"), list):
                out.append(f"groups[{i}] must be {{title, fields}}")
                continue
            for n in g["fields"]:
                known(n, f"groups[{i}]")
    if "fields" in hints:
        if not isinstance(hints["fields"], dict):
            out.append("fields must map a field name to {widget, help, label}")
        else:
            for n, h in hints["fields"].items():
                known(n, f"fields.{n}")
                if not isinstance(h, dict):
                    out.append(f"fields.{n} must be {{widget, help, label}}")
                    continue
                out += [f"fields.{n}: unknown hint {k!r}" for k in sorted(set(h) - FIELD_HINT_KEYS)]
                if "widget" in h and h["widget"] not in WIDGETS:
                    out.append(f"fields.{n}.widget must be one of {', '.join(WIDGETS)}, got {h['widget']!r}")
                for k in ("help", "label"):
                    if k in h and not (isinstance(h[k], str) and h[k].strip()):
                        out.append(f"fields.{n}.{k} must be text")
    return out


def load_hints(path: Any) -> Any:
    """A hints file: YAML (or JSON, which YAML reads)."""
    from .data import load_yaml

    return load_yaml(path)


# ---------------------------------------------------------------------------
# A person's step (Decision 0170, items 2, 3, 8 and 11)
# ---------------------------------------------------------------------------

#: Text shown inline in a context item, at most; longer material is fetched through ``interaction(id, item)``.
INLINE_LIMIT = 4000


def person_steps(ctx: Any) -> list[tuple[str, int, int]]:
    """``(step path, attempt, seq of its dispatch)`` for each step a person is doing now (a ``manual`` dispatch)."""
    rs = ctx.log.state()
    last: dict[tuple[str, int], Any] = {}
    for e in ctx.log.events():
        if e.type == "dispatched":
            last[(e.step_path, e.attempt)] = e
    out = []
    for path, st in sorted(rs.steps.items()):
        ev = last.get((path, st.attempt))
        if st.state == "running" and ev is not None and ev.data.get("adapter") == "manual":
            out.append((path, st.attempt, ev.seq))
    return out


def _packet(ctx: Any, path: str, attempt: int) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    pdir = ctx.attempt_dir(path, attempt) / "packet"
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    sfile = pdir / "output_schema.json"
    schema = json.loads(sfile.read_text(encoding="utf-8")) if sfile.is_file() else {}
    return pdir, manifest, schema


def _hints_of(ctx: Any, interaction: Any) -> dict[str, Any]:
    return dict(ctx.recipe.hints.get(interaction.hints) or {}) if interaction is not None else {}


def _prefill(schema: dict[str, Any]) -> dict[str, Any]:
    return {k: v["default"] for k, v in (schema.get("properties") or {}).items() if isinstance(v, dict) and "default" in v}


def build_person_step(ctx: Any, path: str, attempt: int, seq: int) -> dict[str, Any]:
    """The request for a person's step: its output schema as the answer, its declared files, its instructions and inputs."""
    from .packet import node_for

    node = node_for(ctx.recipe, path)
    pdir, manifest, schema = _packet(ctx, path, attempt)
    context: list[dict[str, Any]] = []
    if (pdir / "INSTRUCTIONS.md").is_file():
        context.append({"id": "instructions", "kind": "document", "label": "What to do", "ref": "packet/INSTRUCTIONS.md",
                        "media_type": "text/markdown"})
    for i in manifest.get("inputs") or []:
        mt = i.get("media_type") or ""
        context.append({"id": f"input:{i['name']}", "kind": "image" if mt.startswith("image/") else "document",
                        "label": i["name"], "ref": f"packet/{i['path']}", **({"media_type": mt} if mt else {})})
    files = [{"name": a["name"], "required": req, **({"media_type": a["media_type"]} if a.get("media_type") else {})}
             for req, key in ((True, "required_artifacts"), (False, "optional_artifacts")) for a in manifest.get(key) or []]
    answer = {"schema": schema, "prefill": _prefill(schema), "renderable": renderable(schema)}
    asked = {"schema": schema, "files": files, "packet": manifest.get("packet_sha256")}
    raw = json.dumps([ctx.run_id, path, "person_step", seq, asked], sort_keys=True, separators=(",", ":"), default=str)
    title = getattr(node, "title", None) or path
    return {
        "format": FORMAT,
        "id": "ir_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20],
        "run": ctx.run_id, "ref": path, "step_path": path, "attempt": attempt, "kind": "person_step",
        "title": title,
        "message": f"Your part of the work: {title}. Fill in what it asks for" + (", and add the files it needs." if files else "."),
        "context": context, "choices": [], "answer": answer, "files": files,
        "hints": _hints_of(ctx, getattr(node, "interaction", None)), "extensions": {}, "needs_confirmation": True,
    }


def gate_context(ctx: Any, p: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """For a recipe's human gate: the gated step's output and files to show, and the gate's hints (§5.3)."""
    from .packet import node_for
    from .models import HumanGate

    opened = ctx.record().last("human_gate_opened", p["ref"], p.get("attempt"))
    gate = opened.data.get("gate") if opened else None
    if not isinstance(gate, int):
        return [], {}
    try:
        node = node_for(ctx.recipe, p["ref"])
        g = node.gates[gate]
    except (LookupError, AttributeError):  # expected: a gate the recipe no longer has at that index shows no output
        return [], {}
    items: list[dict[str, Any]] = []
    rdir = ctx.attempt_dir(p["ref"], p["attempt"]) / "result"
    if (rdir / "result.json").is_file():
        items.append({"id": "output", "kind": "document", "label": "What was produced", "ref": "output", "media_type": "application/json"})
        try:
            res = json.loads((rdir / "result.json").read_text(encoding="utf-8"))
        except ValueError:  # expected: an unreadable result was rejected at intake; there is nothing more to show
            res = {}
        for a in res.get("artifacts") or []:
            if isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("path"), str):
                img = a["path"].lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
                items.append({"id": f"file:{a['name']}", "kind": "image" if img else "document", "label": a["name"], "ref": f"result/{a['path']}"})
    return items, _hints_of(ctx, g.interaction) if isinstance(g, HumanGate) else {}


def fetch(ctx: Any, req: dict[str, Any], item: str) -> dict[str, Any]:
    """One context item's material, by the item's id in the request (never by a path from the caller)."""
    import mimetypes


    entry = next((c for c in req.get("context") or [] if c.get("id") == item), None)
    if entry is None:
        raise EngineError("interaction.unknown_item", f"request {req['id']} has no context item {item!r} "
                          f"(its items: {', '.join(c['id'] for c in req.get('context') or []) or 'none'})")
    if "ref" not in entry:
        return {**entry}
    adir = ctx.attempt_dir(req["ref"], req["attempt"])
    if entry["ref"] == "output":
        res = json.loads((adir / "result" / "result.json").read_text(encoding="utf-8"))
        text = json.dumps(res.get("output"), indent=2, ensure_ascii=False)
        return {**entry, "text": text, "size": len(text.encode("utf-8"))}
    f = (adir / entry["ref"]).resolve()
    if adir.resolve() not in f.parents or not f.is_file():
        raise EngineError("interaction.item_missing", f"{entry['ref']} of request {req['id']} is not there")
    out = {**entry, "path": str(f), "size": f.stat().st_size,
           "media_type": entry.get("media_type") or mimetypes.guess_type(f.name)[0] or "application/octet-stream"}
    if not out["media_type"].startswith("image/") and f.stat().st_size <= 1 << 20:
        try:
            out["text"] = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # expected: binary material is given by path only
            pass
    return out


def write_result(manifest: dict[str, Any], values: dict[str, Any], files: dict[str, str], declared: list[dict[str, Any]],
                 words: str, into: Any) -> None:
    """A person's answer as a result folder (``result.json`` and ``artifacts/``) that ``submit`` takes in (item 11)."""
    import shutil
    from pathlib import Path

    names = {d["name"] for d in declared}
    unknown = sorted(set(files) - names)
    if unknown:
        raise EngineError("answer.invalid", f"unknown file(s) {', '.join(unknown)}; the step's files are {', '.join(sorted(names)) or 'none'}")
    missing = [d["name"] for d in declared if d["required"] and d["name"] not in files]
    if missing:
        raise EngineError("answer.invalid", f"required file(s) not given: {', '.join(missing)} (--attach <name>=<path>)")
    arts = []
    (Path(into) / "artifacts").mkdir(parents=True, exist_ok=True)
    for name, src in sorted(files.items()):
        s = Path(src).expanduser()
        if not s.is_file():
            raise EngineError("answer.invalid", f"file for {name} not found: {src}")
        rel = f"artifacts/{name}{s.suffix}"
        shutil.copyfile(s, Path(into) / rel)
        arts.append({"name": name, "path": rel})
    result = {"protocol": manifest["protocol"], "packet_sha256": manifest["packet_sha256"], "status": "completed",
              "output": values, "artifacts": arts, "notes": words}
    (Path(into) / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# The answer file (a renderer with no new software; Decision 0170)
# ---------------------------------------------------------------------------


def _comment(text: str, indent: str = "") -> list[str]:
    return [f"{indent}# {line}".rstrip() for line in str(text).splitlines() or [""]]


def _field_lines(schema: dict[str, Any], prefill: dict[str, Any], hints: dict[str, Any]) -> list[str]:
    import yaml

    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    order = [n for n in hints.get("order") or [] if n in props] + [n for n in props if n not in (hints.get("order") or [])]
    fh = hints.get("fields") or {}
    out: list[str] = []
    for name in order:
        f = props[name] if isinstance(props[name], dict) else {}
        h = fh.get(name) or {}
        label = h.get("label") or f.get("title") or name
        about = [f"{label} ({'required' if name in required else 'optional'})"]
        if f.get("description"):
            about.append(str(f["description"]))
        if h.get("help"):
            about.append(str(h["help"]))
        choices = f.get("enum") or [o.get("const") for o in f.get("oneOf") or []]
        items = f.get("items") if isinstance(f.get("items"), dict) else {}
        choices = choices or items.get("enum") or [o.get("const") for o in items.get("oneOf") or []]
        if choices:
            about.append("One of: " + ", ".join(map(str, choices)) if f.get("type") != "array" else "Any of: " + ", ".join(map(str, choices)))
        sugg = f.get("examples") or items.get("examples")
        if sugg:
            about.append("Suggestions (you may write something else): " + "; ".join(map(str, sugg)))
        if f.get("type") == "array" and items.get("type") == "object":
            about.append("A list: one entry per row, each with " + ", ".join(items.get("properties") or {}))
        for a in about:
            out += _comment(a, "  ")
        value = prefill.get(name)
        dumped = yaml.safe_dump({name: value}, allow_unicode=True, default_flow_style=False, sort_keys=False).rstrip("\n")
        out += [f"  {line}" for line in dumped.splitlines()]
    return out


def answer_template(req: dict[str, Any]) -> str:
    """An answer file for ``req``: every field with its prefilled value and a comment from its label and help."""
    lines = _comment(f"Answer for: {req['title']} ({req['id']})") + _comment(req["message"])
    lines += ["#", f"# Fill this in, then: baton answer {req['id']} --file <this file> --note \"<the owner's words>\"",
              "# (or --via answer_file instead of --note when the owner filled it in themselves). Nothing is recorded until then.", ""]
    hints = req.get("hints") or {}
    if req.get("choices"):
        lines += ["# Choices:"]
        for c in req["choices"]:
            lines += _comment(f"  {c['decision']}: {c['label']}. {c['effect']}")
        lines += [f"choice:   # one of: {', '.join(c['decision'] for c in req['choices'])}", ""]
        with_fields = [c for c in req["choices"] if c.get("answer")]
        for c in with_fields:
            lines += _comment(f"values for {c['decision']}:")
            lines += ["values:"] + _field_lines(c["answer"]["schema"], c["answer"].get("prefill") or {}, hints) + [""]
            break  # one choice per request takes fields in this format's kinds; any other is named in its own comment
        for c in with_fields[1:]:
            lines += _comment(f"{c['decision']} takes: {', '.join(c['answer']['schema'].get('properties') or {})}")
    if req.get("answer"):
        if not req["answer"].get("renderable", True):
            lines += _comment("This part asks for more than a simple form can hold: write the values as the step's output, by hand.")
        lines += ["values:"] + _field_lines(req["answer"]["schema"], req["answer"].get("prefill") or {}, hints) + [""]
    if req.get("files"):
        lines += ["artifacts:"]
        for f in req["files"]:
            lines += _comment(f"{f['name']} ({'required' if f['required'] else 'optional'}"
                              + (f", {f['media_type']}" if f.get("media_type") else "") + "): the path of the file", "  ")
            lines.append(f"  {f['name']}:")
        lines.append("")
    return "\n".join(lines) + "\n"
