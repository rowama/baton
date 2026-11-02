"""Failure classification (§8.8): data-driven rules, in order.

Classes: ``configuration`` (owner, with the exact fix), ``platform`` (the
platform SME; incidents arrive in Phase 12), ``subject`` (the recipe's normal
path: retry, iterate, escalate) and ``unknown`` (nothing matched).

A worker that **ended without a result** is classified by, in order:

1. the API runner's failure line ``baton-worker: failure=<class> code=<code>
   message=<text>`` (the last one in the output);
2. the adapter's ``failure_signals`` (``pattern``, ``class``, ``code``);
3. the shipped rules (``classify/rules-1.yaml``): output patterns, then exit
   codes, then killing signals;
4. otherwise ``unknown`` with the last output line.

A **failed script gate** is classified by the rules' exit codes and signals
with ``scope: gate`` only (a gate command that cannot be found or run is the
platform's problem); anything else is ``subject``. Output patterns are not
applied to gates: a test suite may legitimately print "Permission denied".

Messages are redacted (§15.2) and cut to one line.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

from . import data
from .redact import redact_text

RULES_ID = "baton-classify-rules/1"
FAILURE_LINE = re.compile(r"baton-worker: failure=(\w+) code=(\w+) message=(.*)")
CLASSES = ("configuration", "platform", "subject", "unknown")


@functools.lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else data.path("classify") / "rules-1.yaml"
    raw = data.load_yaml(p) or {}
    if raw.get("id") != RULES_ID:
        raise ValueError(f"{p}: expected id {RULES_ID}, found {raw.get('id')!r}")
    for r in raw.get("patterns") or []:
        if r.get("class") not in CLASSES:
            raise ValueError(f"{p}: rule {r.get('code')!r} has unknown class {r.get('class')!r}")
        re.compile(r["pattern"])
    return raw


def _line_of(text: str, start: int, end: int) -> str:
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", end)
    return text[a : b if b >= 0 else len(text)].strip()


def _last_match(pattern: str, text: str) -> re.Match[str] | None:
    hit = None
    for hit in re.finditer(pattern, text):
        pass
    return hit


def _verdict(cls: str, code: str, message: str) -> dict[str, Any]:
    return {"class": cls, "code": code, "message": redact_text(message.strip())[:300]}


def _by_code(exit_code: int | None, scope: str, rules: dict[str, Any]) -> dict[str, Any] | None:
    if exit_code is None:
        return None
    candidates: list[tuple[dict, Any]] = [(rules.get("exit_codes") or {}, exit_code)]
    sig = -exit_code if exit_code < 0 else (exit_code - 128 if exit_code > 128 else None)
    if sig is not None:
        candidates.append((rules.get("signals") or {}, sig))
    for table, key in candidates:
        r = table.get(key) or table.get(str(key))
        if r and scope in (r.get("scope") or ["worker"]):
            return _verdict(r["class"], r["code"], r.get("message", f"exit {exit_code}"))
    return None


def classify_exit(exit_code: int | None, tail: bytes | str, signals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The class of a worker that exited without writing ``result.json``."""
    text = tail.decode("utf-8", errors="replace") if isinstance(tail, bytes) else tail
    m = _last_match(FAILURE_LINE.pattern, text)
    if m is not None:
        return _verdict(m.group(1), m.group(2), m.group(3))
    rules = load_rules()
    for sig in [*(s for s in signals or [] if "class" in s), *(rules.get("patterns") or [])]:
        hit = _last_match(sig["pattern"], text)
        if hit is not None:
            return _verdict(sig["class"], sig.get("code", "signal"), _line_of(text, hit.start(), hit.end()))
    by_code = _by_code(exit_code, "worker", rules)
    if by_code is not None:
        return by_code
    last = [ln for ln in text.splitlines() if ln.strip()][-1:] or [""]
    return _verdict("unknown", f"exit_{exit_code}", last[0])


def classify_gate(exit_code: int | None) -> dict[str, Any] | None:
    """A platform verdict for a failed script gate, or None (the step's own failure)."""
    return _by_code(exit_code, "gate", load_rules())


def supervisor_died() -> dict[str, Any]:
    return _verdict("platform", "supervisor_died", "the supervisor process ended before the worker's outcome was recorded")


def timed_out(seconds: float) -> dict[str, Any]:
    return _verdict("subject", "timeout", f"the worker did not finish within {seconds:.0f} s")
