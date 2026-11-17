"""Tools a recipe ships (§5.9; Decisions 0154, 0156, 0158).

A tool is a script in ``tools/<id>/`` of a recipe package, described by
``tool.yaml``, with its dependencies pinned in a lock file. This module holds
what the loader needs to check a tool without running it: the lock-file parser,
the entry placeholders, the runtime-version check, the tool's worked
examples (``examples/<name>/``; Decision 0162) and an engineered tool's
contract (``contract.json``; Decision 0164). Environments are built in
``tool_env``, tools run in ``tool_runner`` and examples are run by ``tool_test``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .models import ToolSpec

TOOLS_DIR = "tools"
TOOL_FILE = "tool.yaml"
EXAMPLES_DIR = "examples"
#: An example's files (Decision 0162, items 5 and 10).
EXAMPLE_INPUT, EXAMPLE_INPUTS, EXAMPLE_EXPECTED, EXAMPLE_ARTIFACTS, EXAMPLE_WORKSPACE = (
    "input.json", "inputs", "expected.json", "expected", "workspace")
#: Where an engineered tool's example came from (Decision 0164, item 4).
EXAMPLE_ABOUT = "about.json"
EXAMPLE_SOURCES = ("owner", "drafted")
#: An engineered tool's contract, written by recipe builder's ``generate`` (Decision 0164).
CONTRACT_FILE = "contract.json"
_CONTRACT_KEYS = {"kind": True, "does": True, "input_schema": True, "output_schema": True, "reach": True,
                  "packages": True, "budget_reason": True, "size_reason": False}
_EXAMPLE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
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
class Example:
    """One worked example of a tool: the inputs it is given and the result it must give (Decision 0162)."""

    name: str
    root: Path  # tools/<id>/examples/<name>/
    values: dict[str, Any]  # input.json: the JSON inputs
    files: dict[str, Path]  # inputs/<input name>.<ext>: the file inputs
    expected: dict[str, Any]  # expected.json: output.json must equal it
    artifacts: dict[str, Path]  # expected/<artifact>.<ext>: compared byte for byte
    workspace: Path | None = None  # workspace/: copied as the workspace of a tool that reaches it
    about: dict[str, Any] | None = None  # about.json: {source, awkward, from} (Decision 0164)


@dataclass
class LoadedTool:
    """A checked tool: its declaration, its folder and the hashes that pin it."""

    spec: ToolSpec
    root: Path  # tools/<id>/ inside the recipe package
    sha256: str  # over every file in the tool's folder, as the recipe hash is (§5.9)
    lock_sha256: str
    requirements: list[LockedRequirement] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    contract: dict[str, Any] | None = None  # contract.json: an engineered tool (Decision 0164)
    built: bool = True  # False: an engineered tool whose entry file is not written yet

    @property
    def engineered(self) -> bool:
        return self.contract is not None

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


def artifact_name(filename: str) -> str:
    """The artifact a file is for: ``differences.csv`` and ``differences`` are both ``differences``."""
    return filename.split(".", 1)[0]


def load_examples(tool_root: Path) -> tuple[list[Example], list[tuple[str, str, str]]]:
    """A tool's examples, and the problems with them as ``(code, where, message)``.

    ``where`` is relative to the tool's folder. No ``examples/`` folder is no
    examples, not a problem (``baton tools test --require-examples`` says so).
    """
    base = tool_root / EXAMPLES_DIR
    if not base.is_dir():
        return [], []
    examples: list[Example] = []
    problems: list[tuple[str, str, str]] = []

    def bad(where: str, message: str) -> None:
        problems.append(("tool.bad_example", where, message))

    for d in sorted(base.iterdir()):
        where = f"{EXAMPLES_DIR}/{d.name}"
        if not d.is_dir():
            bad(where, "an example is a folder (examples/<name>/ holding input.json and expected.json)")
            continue
        if not _EXAMPLE_NAME.match(d.name):
            bad(where, f"{d.name!r} is not an example name (lower-case letters, digits, '-' and '_')")
            continue
        n_before = len(problems)
        known = {EXAMPLE_INPUT, EXAMPLE_INPUTS, EXAMPLE_EXPECTED, EXAMPLE_ARTIFACTS, EXAMPLE_WORKSPACE, EXAMPLE_ABOUT}
        for extra in sorted(p.name for p in d.iterdir() if p.name not in known):
            bad(f"{where}/{extra}", "not part of an example (input.json, inputs/, expected.json, expected/, workspace/, about.json)")
        about = _about(d / EXAMPLE_ABOUT, f"{where}/{EXAMPLE_ABOUT}", bad)
        values = _json_object(d / EXAMPLE_INPUT, f"{where}/{EXAMPLE_INPUT}", bad, required=False)
        expected = _json_object(d / EXAMPLE_EXPECTED, f"{where}/{EXAMPLE_EXPECTED}", bad, required=True)
        files = _named_files(d / EXAMPLE_INPUTS, f"{where}/{EXAMPLE_INPUTS}", "input", bad)
        for name in sorted(set(files) & set(values or {})):
            bad(f"{where}/{EXAMPLE_INPUTS}/{files[name].name}", f"input {name!r} is given both here and in {EXAMPLE_INPUT}")
        artifacts = _named_files(d / EXAMPLE_ARTIFACTS, f"{where}/{EXAMPLE_ARTIFACTS}", "artifact", bad)
        ws = d / EXAMPLE_WORKSPACE
        if ws.exists() and not ws.is_dir():
            bad(f"{where}/{EXAMPLE_WORKSPACE}", "workspace/ must be a folder")
        if len(problems) == n_before and values is not None and expected is not None:
            examples.append(Example(d.name, d, values, files, expected, artifacts, ws if ws.is_dir() else None, about))
    return examples, problems


def _json_object(path: Path, where: str, bad: Any, *, required: bool) -> dict[str, Any] | None:
    if not path.is_file():
        if required:
            bad(where, f"missing: the example needs {path.name}")
            return None
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError, OSError) as e:
        bad(where, f"not valid JSON ({e})")
        return None
    if not isinstance(value, dict):
        bad(where, "must hold a JSON object")
        return None
    return value


def _named_files(folder: Path, where: str, what: str, bad: Any) -> dict[str, Path]:
    """Files named ``<name>`` or ``<name>.<ext>``, one per name."""
    out: dict[str, Path] = {}
    if not folder.exists():
        return out
    if not folder.is_dir():
        bad(where, f"{folder.name}/ must be a folder")
        return out
    for p in sorted(folder.iterdir()):
        name = artifact_name(p.name)
        if p.is_dir():
            bad(f"{where}/{p.name}", f"one file per {what}, named {what} or {what}.<ext>; not a folder")
        elif name in out:
            bad(f"{where}/{p.name}", f"two files for {what} {name!r}: {out[name].name!r} and {p.name!r}")
        else:
            out[name] = p
    return out


def _about(path: Path, where: str, bad: Any) -> dict[str, Any] | None:
    """An example's ``about.json``: ``{source: owner | drafted, awkward: bool, from: {<file in the example>: <project path>}}``.

    ``from`` names, for each file copied from the owner's documents, the
    project document it was copied from, so ``baton tools examples`` can prove
    the copy (Decision 0164, item 4). No file is no record, not a problem.
    """
    if not path.exists():
        return None
    value = _json_object(path, where, bad, required=True)
    if value is None:
        return None
    for key in sorted(set(value) - {"source", "awkward", "from"}):
        bad(where, f"unknown key {key!r} (source, awkward, from)")
    if value.get("source") not in EXAMPLE_SOURCES:
        bad(where, f"`source` must be one of {list(EXAMPLE_SOURCES)}")
    if not isinstance(value.get("awkward", False), bool):
        bad(where, "`awkward` must be true or false")
    copied = value.get("from", {})
    if not isinstance(copied, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in copied.items()):
        bad(where, "`from` must map each copied file (such as inputs/export.csv) to the project path it was copied from")
    else:
        for rel in copied:
            parts = PurePosixPath(rel).parts
            if not (rel == EXAMPLE_EXPECTED or (len(parts) == 2 and parts[0] in (EXAMPLE_INPUTS, EXAMPLE_ARTIFACTS))) or ".." in parts:
                bad(where, f"`from` key {rel!r} must be expected.json, inputs/<file> or expected/<file>")
            elif not (path.parent / rel).is_file():
                bad(where, f"`from` names {rel!r}, which is not in the example")
    return value


def load_contract(tool_root: Path) -> tuple[dict[str, Any] | None, list[tuple[str, str, str]]]:
    """An engineered tool's ``contract.json`` and the problems with it as ``(code, where, message)``.

    No file is a simple tool (Decision 0162), not a problem. The contract is
    the design's: what the tool does, its schemas, what it may touch, every
    package it needs with the reason, and why it is within the tool budget
    (Decision 0155, item 4); ``size_reason`` when it is over the size cap.
    """
    path = tool_root / CONTRACT_FILE
    if not path.exists():
        return None, []
    problems: list[tuple[str, str, str]] = []

    def bad(where: str, message: str) -> None:
        problems.append(("tool.bad_contract", where, message))

    value = _json_object(path, CONTRACT_FILE, bad, required=True)
    if value is None:
        return None, problems
    for key in sorted(set(value) - set(_CONTRACT_KEYS)):
        bad(f"{CONTRACT_FILE}:{key}", f"unknown key {key!r}")
    for key in sorted(k for k, req in _CONTRACT_KEYS.items() if req and k not in value):
        bad(f"{CONTRACT_FILE}:{key}", f"required key {key!r} is missing")
    if "kind" in value and value["kind"] != "engineered":
        bad(f"{CONTRACT_FILE}:kind", "`kind` must be 'engineered' (a simple tool has no contract file)")
    for key in ("does", "budget_reason", "size_reason"):
        if key in value and not (isinstance(value[key], str) and value[key].strip()):
            bad(f"{CONTRACT_FILE}:{key}", f"`{key}` must be a non-empty string")
    for key in ("input_schema", "output_schema", "reach"):
        if key in value and not isinstance(value[key], dict):
            bad(f"{CONTRACT_FILE}:{key}", f"`{key}` must be an object")
    pkgs = value.get("packages", [])
    if not isinstance(pkgs, list) or not all(
        isinstance(p, dict) and set(p) == {"name", "why"} and all(isinstance(p[k], str) and p[k].strip() for k in p) for p in pkgs
    ):
        bad(f"{CONTRACT_FILE}:packages", "`packages` must list each package as {name, why}")
    return (None if problems else value), problems
