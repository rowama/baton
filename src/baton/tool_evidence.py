"""Tool evidence from a harness's event stream (§6.3; Decision 0085).

A harness worker's raw output is its machine-readable event stream (Claude
Code ``--output-format stream-json``, ``codex exec --json``), one JSON object
per line, saved as the attempt's log. Intake never reads it: the result is
still ``result.json``. This module only scans it for evidence that a tool was
called, succeeded, or was denied, so a tooling capability can be recorded
``verified`` or ``absent`` (0084).

``scan(text, names)`` takes the tool or event names a tool map lists for one
capability (``evidence``) and returns ``"used"``, ``"denied"`` or ``None``
(nothing either way: the step did not use the tool, or the stream could not
be read). It understands:

* Claude Code: ``assistant`` messages with ``tool_use`` blocks (``name``,
  ``id``); ``user`` messages with ``tool_result`` blocks (``tool_use_id``,
  ``is_error``); the final ``result`` event's ``permission_denials``
  (``tool_name``). A tool use whose result is an error that mentions
  permission is a denial; one with a successful result is a use.
* Codex: events whose item or message ``type`` is one of ``names`` (e.g.
  ``web_search``), completed (``item.completed``, ``*_end``) or begun.

Unparseable lines are skipped: the stream is evidence, never a protocol.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

DENIAL = re.compile(r"(?i)permission|not allowed|haven't granted|has not been granted|denied|disabled|not available")


def _events(text: str) -> Iterable[dict[str, Any]]:
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:  # expected: a line that is not JSON is not an event
            continue
        if isinstance(ev, dict):
            yield ev


def _blocks(ev: dict[str, Any]) -> list[dict[str, Any]]:
    msg = ev.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _result_text(block: dict[str, Any]) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return ""


def scan(text: str, names: Iterable[str]) -> tuple[str | None, str]:
    """``(verdict, evidence)``: verdict ``used``, ``denied`` or ``None``; evidence in a few plain words."""
    wanted = {n.lower() for n in names}
    if not wanted:
        return None, ""
    uses: dict[str, str] = {}  # tool_use id -> name
    used: list[str] = []
    denied: list[str] = []
    for ev in _events(text):
        etype = str(ev.get("type", ""))
        # Claude Code stream-json.
        for b in _blocks(ev):
            if b.get("type") == "tool_use" and str(b.get("name", "")).lower() in wanted:
                uses[str(b.get("id"))] = str(b.get("name"))
            elif b.get("type") == "tool_result" and str(b.get("tool_use_id")) in uses:
                name = uses[str(b.get("tool_use_id"))]
                if b.get("is_error"):
                    if DENIAL.search(_result_text(b)):
                        denied.append(name)
                else:
                    used.append(name)
        for d in ev.get("permission_denials") or []:
            name = str(d.get("tool_name", "")) if isinstance(d, dict) else str(d)
            if name.lower() in wanted:
                denied.append(name)
        # Codex --json: {"type": "item.completed", "item": {"type": "web_search", ...}} or {"msg": {"type": "web_search_end"}}.
        for inner in (ev.get("item"), ev.get("msg")):
            if isinstance(inner, dict):
                itype = str(inner.get("type", "")).lower()
                base = re.sub(r"_(begin|end)$", "", itype)
                if base in wanted and (etype in ("item.completed", "") or itype.endswith("_end")):
                    if inner.get("status") in ("failed", "declined") or inner.get("error"):
                        denied.append(base)
                    else:
                        used.append(base)
        if etype.lower() in wanted:
            used.append(etype)
    if used:
        return "used", f"{used[0]} call succeeded"
    if denied:
        return "denied", f"{denied[0]} was denied or unavailable"
    return None, ""
