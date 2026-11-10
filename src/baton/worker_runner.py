"""Child-process entrypoint for API workers (§6.3 ``litellm_api``).

``python -m baton.worker_runner --packet DIR --result DIR --model MODEL [--options JSON] [--context-tokens N]``

The runtime starts this under the profile's constructed environment (clean by
default, holding only the profile's resolved API key). It:

1. reads the packet (``manifest.json``, ``INSTRUCTIONS.md``, ``output_schema.json``,
   ``inputs/``) and builds the messages: the instructions, plus the text of
   every input not already inlined in them;
2. refuses inputs that cannot be inlined (§18 #1, decided: a hard error): any
   input that is not UTF-8 text, or a message over the inline budget
   (``context_tokens * 2`` bytes, roughly half the window; 256 KiB when the
   profile declares no ``context_tokens``). The runtime checks the same rule at
   dispatch, so this is a second line;
3. asks the model for one JSON reply (``status``, ``output``, ``artifacts`` as
   text by name, ``notes``, ``questions_for_human``), using a JSON-schema
   response format when the model supports one [VERIFY per model] and the
   prompt alone otherwise;
4. writes the artifacts, then ``result.json`` last. Intake judges the result;
   this runner never does.

Problems that are not the step's (authentication, network, provider errors,
unknown models, a missing ``litellm``) write **no** result: the runner prints one
line ``baton-worker: failure=<class> code=<code> message=<text>`` to stderr and
exits non-zero, and the runtime classifies the attempt from it (§8.8). A reply
that is not valid JSON is the step's problem: a ``failed`` result, retried.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

#: Inline budget when a profile declares no ``context_tokens``.
DEFAULT_INLINE_BUDGET = 256 * 1024
#: Bytes per token assumed when deriving the budget from ``context_tokens`` (half the window).
BUDGET_BYTES_PER_TOKEN = 2
#: Inputs ``packet.render_instructions`` already inlines (JSON up to this size).
INSTRUCTIONS_INLINE_LIMIT = 16 * 1024

EXT_BY_MEDIA = {"text/markdown": ".md", "application/json": ".json", "text/html": ".html", "text/csv": ".csv", "text/x-python": ".py"}

SYSTEM = """\
You are a worker in a Baton process run, reached through an API. The runtime handles all files for you:
ignore any instruction about reading or writing files, directories, result.json or packet hashes.
Every input is included below. Reply with ONE JSON object and nothing else:
{"status": "completed" | "blocked" | "failed",
 "output": <an object matching the output schema>,
 "artifacts": {"<declared artifact name>": "<full text of the artifact>"},
 "notes": "<short notes for the record>",
 "questions_for_human": [<only when status is blocked: {"id", "ask", "why", "best_guess"?, "options"?: [{"id", "label"}], "multi_select"?, "priority"?: "needed" | "helpful"}>]}
Use "blocked" with questions_for_human when only the owner can answer something, "failed" when you
cannot do the step. Ask in the owner's terms; offer a best guess for anything you can infer.
Never guess around a mismatch: report it."""


QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"}, "ask": {"type": "string"}, "why": {"type": "string"}, "best_guess": {"type": "string"},
        "options": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                                               "required": ["id", "label"], "additionalProperties": False}},
        "multi_select": {"type": "boolean"}, "priority": {"type": "string", "enum": ["needed", "helpful"]},
    },
    "required": ["id", "ask", "why"],
    "additionalProperties": False,
}


class InputError(Exception):
    """The packet's inputs cannot be given to an API model."""


def inline_budget(context_tokens: int | None) -> int:
    return context_tokens * BUDGET_BYTES_PER_TOKEN if context_tokens else DEFAULT_INLINE_BUDGET


def build_messages(packet_dir: Path, context_tokens: int | None = None) -> list[dict[str, str]]:
    """System and user messages for a packet. Raises ``InputError`` (§18 #1: hard error)."""
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    parts = [(packet_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")]
    problems = []
    extra = []
    for item in manifest.get("inputs", []):
        path = packet_dir / item["path"]
        data = path.read_bytes()
        if item.get("kind") == "json" and len(data) <= INSTRUCTIONS_INLINE_LIMIT:
            continue  # already inlined in INSTRUCTIONS.md
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"input {item['name']!r} ({item['path']}) is not UTF-8 text")
            continue
        extra.append(f"### Contents of `{item['path']}` (input `{item['name']}`)\n\n````\n{text.rstrip()}\n````\n")
    if extra:
        parts.append("## Input file contents\n\n" + "\n".join(extra))
    user = "\n".join(parts)
    budget = inline_budget(context_tokens)
    size = len(SYSTEM.encode()) + len(user.encode())
    if size > budget:
        problems.append(f"the packet needs {size} bytes inlined; this profile's budget is {budget} bytes")
    if problems:
        raise InputError("; ".join(problems) + ". Choose a worker that reads files (a harness or manual profile).")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _hoisted(schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The output schema without root keywords, and its definitions to hoist to the wrapper root."""
    body = {k: v for k, v in schema.items() if k not in ("$schema", "$id", "$defs", "definitions")}
    defs = {k: schema[k] for k in ("$defs", "definitions") if k in schema}
    return body, defs


def reply_schema(output_schema: dict[str, Any], artifact_names: list[str]) -> dict[str, Any]:
    body, defs = _hoisted(output_schema)
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["completed", "blocked", "failed"]},
            "output": body,
            "artifacts": {"type": "object", "properties": {n: {"type": "string"} for n in artifact_names}, "additionalProperties": False},
            "notes": {"type": "string"},
            "questions_for_human": {"type": "array", "items": QUESTION_SCHEMA},
        },
        "required": ["status", "output"],
        "additionalProperties": False,
        **defs,
    }


def parse_reply(text: str) -> dict[str, Any] | None:
    """The JSON object in a model reply: the whole text, a fenced block, or the outermost braces."""
    candidates = [text.strip()]
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    if m:
        candidates.append(m.group(1))
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{") : text.rindex("}") + 1])
    for c in candidates:
        try:
            value = json.loads(c)
        except json.JSONDecodeError:  # expected: not every brace pair is JSON: try the next candidate
            continue
        if isinstance(value, dict):
            return value
    return None


def write_result(packet_dir: Path, result_dir: Path, reply: dict[str, Any] | None, raw_notes: str = "") -> dict[str, Any]:
    """Write artifacts, then ``result.json`` last. Returns the envelope."""
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    media = {a["name"]: a.get("media_type") for a in manifest.get("required_artifacts", []) + manifest.get("optional_artifacts", [])}
    result_dir.mkdir(parents=True, exist_ok=True)
    if reply is None:
        envelope = {
            "protocol": manifest["protocol"], "packet_sha256": manifest["packet_sha256"], "status": "failed",
            "output": None, "artifacts": [], "notes": raw_notes or "the model's reply was not a JSON object",
            "questions_for_human": [], "process_feedback": [],
        }
    else:
        listed = []
        arts = reply.get("artifacts") or {}
        if isinstance(arts, dict):
            (result_dir / "artifacts").mkdir(exist_ok=True)
            for name, content in arts.items():
                if not isinstance(content, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", str(name)):
                    continue
                fname = f"{name}{EXT_BY_MEDIA.get(media.get(name) or '', '.txt')}"
                (result_dir / "artifacts" / fname).write_text(content, encoding="utf-8")
                listed.append({"name": name, "path": f"artifacts/{fname}"})
        status = reply.get("status") if reply.get("status") in ("completed", "blocked", "failed") else "failed"
        questions = reply.get("questions_for_human")
        envelope = {
            "protocol": manifest["protocol"], "packet_sha256": manifest["packet_sha256"], "status": status,
            "output": reply.get("output"), "artifacts": listed, "notes": str(reply.get("notes") or ""),
            "questions_for_human": [q if isinstance(q, dict) else str(q) for q in questions] if isinstance(questions, list) else [],
            "process_feedback": [],
        }
    tmp = result_dir / "result.json.tmp"
    tmp.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, result_dir / "result.json")
    return envelope


# ---------------------------------------------------------------------------
# The model call
# ---------------------------------------------------------------------------


class WorkerFailure(Exception):
    """A failure that is not the step's: reported to the runtime, no result written."""

    def __init__(self, failure_class: str, code: str, message: str):
        super().__init__(message)
        self.failure_class = failure_class
        self.code = code


def classify_exception(e: BaseException) -> WorkerFailure:
    """Map a provider exception to a failure class (§8.8) by its type name."""
    names = {c.__name__ for c in type(e).__mro__}
    if names & {"AuthenticationError", "PermissionDeniedError"}:
        return WorkerFailure("platform", "auth_failed", str(e))
    if names & {"NotFoundError", "BadRequestError", "UnsupportedParamsError"}:
        return WorkerFailure("configuration", "bad_request", str(e))
    if "RateLimitError" in names:  # a free route's daily limit or a provider's rate limit: this route is out for now (0114)
        return WorkerFailure("platform", "quota_exhausted", str(e))
    if names & {"APIConnectionError", "Timeout", "ServiceUnavailableError", "InternalServerError", "APIError"}:
        return WorkerFailure("platform", "provider_unavailable", str(e))
    return WorkerFailure("unknown", type(e).__name__, str(e))


Completion = Callable[..., Any]


def call_model(complete: Completion, model: str, messages: list[dict[str, str]], schema: dict[str, Any], options: dict[str, Any], structured: bool) -> str:
    kwargs = dict(options)
    if structured:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "baton_result", "schema": schema, "strict": False}}
    else:
        messages = [messages[0], {"role": "user", "content": messages[1]["content"] + "\n\n## Reply schema\n\n```json\n" + json.dumps(schema, indent=2) + "\n```\n"}]
    try:
        resp = complete(model=model, messages=messages, **kwargs)
    except Exception as e:  # noqa: BLE001 - classified, never swallowed
        raise classify_exception(e) from e
    try:
        return resp.choices[0].message.content or ""
    except (AttributeError, IndexError, KeyError, TypeError) as e:
        raise WorkerFailure("unknown", "bad_response", f"unexpected response shape: {e}") from e


def run(
    packet_dir: Path,
    result_dir: Path,
    model: str,
    options: dict[str, Any],
    context_tokens: int | None,
    *,
    complete: Completion,
    supports_schema: Callable[[str], bool] = lambda m: False,
) -> dict[str, Any]:
    """Do one attempt. Raises ``WorkerFailure`` for failures that are not the step's."""
    try:
        messages = build_messages(packet_dir, context_tokens)
    except InputError as e:
        return write_result(packet_dir, result_dir, None, f"inputs cannot be sent to an API model: {e}")
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    output_schema = json.loads((packet_dir / "output_schema.json").read_text(encoding="utf-8"))
    names = [a["name"] for a in manifest.get("required_artifacts", []) + manifest.get("optional_artifacts", [])]
    schema = reply_schema(output_schema, names)
    text = call_model(complete, model, messages, schema, options, supports_schema(model))
    reply = parse_reply(text)
    return write_result(packet_dir, result_dir, reply, "" if reply is not None else "the model's reply was not a JSON object")


def noop(model: str, options: dict[str, Any], complete: Completion) -> str:
    """A minimal round trip for ``doctor``: the model must answer ``{"ok": true}``."""
    messages = [{"role": "user", "content": 'Reply with exactly this JSON and nothing else: {"ok": true}'}]
    try:
        resp = complete(model=model, messages=messages, **options)
        text = resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        raise classify_exception(e) from e
    reply = parse_reply(text)
    if not reply or reply.get("ok") is not True:
        raise WorkerFailure("unknown", "noop_mismatch", "the model did not return {\"ok\": true}")
    return text


def _report(f: WorkerFailure) -> int:
    from .redact import redact_text

    secrets = tuple(v for k, v in os.environ.items() if k not in ("PATH", "HOME") and len(v) >= 12)
    msg = redact_text(" ".join(str(f).split()), secrets)[:500]
    print(f"baton-worker: failure={f.failure_class} code={f.code} message={msg}", file=sys.stderr)
    return {"platform": 3, "configuration": 4}.get(f.failure_class, 1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="baton.worker_runner")
    ap.add_argument("--packet", type=Path)
    ap.add_argument("--result", type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--options", default="{}")
    ap.add_argument("--context-tokens", type=int, default=None)
    ap.add_argument("--noop", action="store_true", help="doctor's round trip; needs no packet")
    args = ap.parse_args(argv)
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # never fetch the remote model map
    try:
        import litellm  # optional dependency: pip install 'baton[api]'
    except ImportError:
        return _report(WorkerFailure("platform", "litellm_missing", "litellm is not installed for this runtime (install baton[api])"))
    options = json.loads(args.options)
    try:
        if args.noop:
            noop(args.model, options, litellm.completion)
            print("baton-worker: noop ok")
            return 0

        def supports(m: str) -> bool:
            try:
                return bool(litellm.supports_response_schema(model=m))
            except Exception:  # expected: unknown model: fall back to the prompt; this is a standalone worker process and imports nothing from the runtime (noqa: BLE001 - unknown model: fall back to the prompt)
                return False

        env = run(args.packet, args.result, args.model, options, args.context_tokens, complete=litellm.completion, supports_schema=supports)
    except WorkerFailure as f:
        return _report(f)
    print(f"baton-worker: result written (status {env['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
