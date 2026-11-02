"""Secret detection and redaction for anything committed (§15.2).

``check`` scans ``.baton/`` with the patterns below (§13.5). Secret *values*
resolved at spawn time (``profiles.resolve_secret``) are registered here, so
``redact_text`` removes them from anything this process writes to the record,
whatever their shape.

**Sentinels.** Tests plant values starting with ``SENTINEL_PREFIX`` as fake
secrets; any sentinel found in the project tree is an error. Real secrets are
caught by the token patterns below, which describe common credential shapes
and never name a model vendor as a routing choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SENTINEL_PREFIX = "BATON-SENTINEL-"

#: (name, pattern). Names are printed; matched text never is.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("sentinel", re.compile(re.escape(SENTINEL_PREFIX).encode() + rb"[A-Za-z0-9_-]{6,}")),
    ("private key", re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("API key token (sk-...)", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}")),
    ("cloud access key id", re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("git host token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("chat workspace token", re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("cloud API key (AIza...)", re.compile(rb"\bAIza[0-9A-Za-z_-]{35}")),
)

REDACTED = "[REDACTED]"

#: Resolved secret values known to this process (never persisted).
_KNOWN: set[str] = set()


def register(value: str) -> None:
    """Remember a resolved secret value so ``redact_text`` removes it."""
    if value and len(value) >= 4:
        _KNOWN.add(value)


@dataclass(frozen=True)
class SecretHit:
    pattern: str
    offset: int


def scan_bytes(data: bytes) -> list[SecretHit]:
    """Every secret-like match, by pattern name and byte offset (never the matched text)."""
    hits = []
    for name, pat in SECRET_PATTERNS:
        for m in pat.finditer(data):
            hits.append(SecretHit(name, m.start()))
    return sorted(hits, key=lambda h: h.offset)


def redact_bytes(data: bytes, values: tuple[str, ...] = ()) -> bytes:
    """``redact_text`` for raw output (decoded as UTF-8 with replacement)."""
    return redact_text(data.decode("utf-8", errors="replace"), values).encode("utf-8")


def redact_text(text: str, values: tuple[str, ...] = ()) -> str:
    """Replace known secret values and secret-like tokens with ``[REDACTED]``."""
    for v in sorted({v for v in (*values, *_KNOWN) if v}, key=len, reverse=True):
        text = text.replace(v, REDACTED)
    raw = text.encode("utf-8")
    for _, pat in SECRET_PATTERNS:
        raw = pat.sub(REDACTED.encode(), raw)
    return raw.decode("utf-8")
