"""Tools a recipe ships (§5.9; Decisions 0154, 0156, 0158).

A tool is a script in ``tools/<id>/`` of a recipe package, described by
``tool.yaml``, with its dependencies pinned in a lock file. This module holds
what the loader needs to check a tool without running it: the lock-file parser,
the entry placeholders and the runtime-version check. Building environments
and running tools come later (2026-11-tool-steps, Slices 2 and 3).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import ToolSpec

TOOLS_DIR = "tools"
TOOL_FILE = "tool.yaml"
RUNTIME_KINDS = ("python",)  # Decision 0156, item 2
#: The only words Baton fills into an entry command: the inputs file, the
#: output directory, the tool's own folder (Decision 0158) and the workspace.
PLACEHOLDERS = frozenset({"input", "output", "tool", "workspace"})
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_COMMAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")  # a bare name, found in the tool's environment
_SPEC = re.compile(r"^\s*(~=|==|!=|<=|>=|<|>)\s*\d+(\.\d+)*(\.\*)?\s*$")
_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?:\[[A-Za-z0-9._,\s-]*\])?"
    r"\s*==\s*(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*)\s*(?:;\s*(?P<marker>.+?))?\s*$"
)
_HASH = re.compile(r"--hash[=\s]+(\S+)")
SHA256_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    hashes: tuple[str, ...]
    marker: str | None = None


@dataclass
class LockProblem:
    code: str
    line: int  # 1-based, the first physical line of the entry
    message: str


@dataclass
class LoadedTool:
    """A checked tool: its declaration, its folder and the hashes that pin it."""

    spec: ToolSpec
    root: Path  # tools/<id>/ inside the recipe package
    sha256: str  # over every file in the tool's folder, as the recipe hash is (§5.9)
    lock_sha256: str
    requirements: list[LockedRequirement] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.spec.id


def placeholders(word: str) -> list[str]:
    """The ``{name}`` placeholders in one word of an entry command."""
    return _PLACEHOLDER.findall(word)


def is_bare_command(word: str) -> bool:
    return bool(_COMMAND.match(word))


def valid_version_spec(spec: str) -> bool:
    """A comma-separated list of version clauses, e.g. ``>=3.11`` or ``>=3.11,<3.14``."""
    parts = spec.split(",")
    return bool(parts) and all(_SPEC.match(p) for p in parts)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_lock(text: str) -> tuple[list[LockedRequirement], list[LockProblem]]:
    """Read a requirements file with exact versions and hashes (``uv pip compile --generate-hashes``).

    Every entry must be ``name==version`` (optionally with extras and an
    environment marker) and carry at least one ``--hash=sha256:...``. Options
    (``-e``, ``-r``, ``--index-url``, ...) and direct URLs are refused, so the
    lock alone says exactly what is installed. An empty lock is a tool that
    needs only the standard library.
    """
    reqs: list[LockedRequirement] = []
    problems: list[LockProblem] = []
    for start, entry in _logical_lines(text):
        hashes = tuple(_HASH.findall(entry))
        spec = _HASH.sub(" ", entry).strip()
        if not spec and hashes:
            problems.append(LockProblem("tool.lock_option", start, "a --hash with no requirement"))
            continue
        if spec.startswith("-"):
            problems.append(
                LockProblem("tool.lock_option", start, f"{spec.split()[0]!r}: only pinned requirements with hashes may appear in a tool's lock")
            )
            continue
        m = _REQUIREMENT.match(spec)
        if m is None:
            problems.append(
                LockProblem("tool.unpinned_dependency", start, f"{spec!r} is not pinned to one exact version (name==version)")
            )
            continue
        if not hashes:
            problems.append(LockProblem("tool.unhashed_dependency", start, f"{m['name']}=={m['version']} has no --hash"))
            continue
        bad = [h for h in hashes if not SHA256_HASH.match(h)]
        if bad:
            problems.append(LockProblem("tool.unhashed_dependency", start, f"{m['name']}: hash {bad[0]!r} is not sha256:<64 hex digits>"))
            continue
        reqs.append(LockedRequirement(m["name"], m["version"], hashes, m["marker"]))
    return reqs, problems


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Physical lines joined across trailing backslashes, comments removed, blanks dropped."""
    out: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 0
    for i, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not buf:
            start = i
        cont = line.rstrip().endswith("\\")
        buf.append(line.rstrip()[:-1] if cont else line)
        if not cont:
            joined = " ".join(b.strip() for b in buf).strip()
            if joined:
                out.append((start, joined))
            buf = []
    if buf:
        joined = " ".join(b.strip() for b in buf).strip()
        if joined:
            out.append((start, joined))
    return out


def _strip_comment(line: str) -> str:
    # pip's rule: '#' starts a comment at the start of a line or after whitespace.
    m = re.search(r"(^|\s)#", line)
    return line[: m.start()] if m else line
