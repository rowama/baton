"""Run a recipe's tools on their worked examples (§5.9; ``baton tools test``; Decision 0162).

Each example is run the way a tool step is dispatched: the tool's environment
(built if needed, as ``baton tools setup`` does), the tool's constructed
environment variables (``engine.tool_profile``), and ``python -m
baton.tool_runner`` on a packet made from the example, in a fresh scratch
folder. The packet holds the example's ``input.json`` values as JSON inputs
and its ``inputs/`` files as file inputs, so the runner writes the same inputs
file a run would (Decision 0159, item 2). The artifacts the example expects
are the ones the packet declares: any other file the tool leaves fails it, as
in a run (0159, item 4).

``output.json`` must equal ``expected.json`` as JSON (a number is not a
boolean, and ``1`` equals ``1.0``); each ``expected/<artifact>`` must equal the
artifact byte for byte. The report names the tool, the example and the first
difference. Nothing is recorded in any run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .documents import guess_media_type
from .packet import PROTOCOL
from .tools import Example, LoadedTool, artifact_name

#: How long one example may run.
EXAMPLE_TIMEOUT_S = 600


@dataclass
class ExampleOutcome:
    example: str
    ok: bool
    difference: str = ""  # the first difference, or why the tool did not finish

    def as_dict(self) -> dict[str, Any]:
        return {"example": self.example, "ok": self.ok, **({"difference": self.difference} if self.difference else {})}


@dataclass
class ToolOutcome:
    tool: str
    examples: list[ExampleOutcome] = field(default_factory=list)
    problem: str = ""  # the tool could not be tested at all (its environment, or no examples when required)

    @property
    def ok(self) -> bool:
        return not self.problem and all(e.ok for e in self.examples)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"tool": self.tool, "ok": self.ok, "examples": [e.as_dict() for e in self.examples]}
        if self.problem:
            out["problem"] = self.problem
        return out


def run_tool_examples(tools: dict[str, LoadedTool], home: Path, *, require_examples: bool = False) -> list[ToolOutcome]:
    from . import tool_env

    out: list[ToolOutcome] = []
    for tid, tool in sorted(tools.items()):
        result = ToolOutcome(tid)
        out.append(result)
        if not tool.examples:
            if require_examples:
                result.problem = f"tool {tid!r} has no examples (add tools/{tid}/examples/<name>/ with input.json and expected.json)"
            continue
        try:
            env = tool_env.ensure(tool, home)
        except tool_env.ToolSetupError as e:
            result.problem = str(e)
            continue
        for ex in tool.examples:
            result.examples.append(run_example(tool, ex, env, home))
    return out


def run_example(tool: LoadedTool, example: Example, env: Any, home: Path) -> ExampleOutcome:
    from .adapters.tool import ToolAdapter
    from .engine import tool_profile
    from .profiles import SetupError, build_env

    profile = tool_profile(tool, env)
    try:
        built = build_env(profile, home=home, resolve=False)
    except SetupError as e:
        return ExampleOutcome(example.name, False, f"could not run: {e}")
    base = Path(tempfile.mkdtemp(prefix="baton-tool-test-"))
    try:
        packet, result = base / "packet", base / "result"
        _write_packet(packet, example)
        workspace = None
        if tool.spec.reach.workspace != "none":
            workspace = base / "workspace"
            if example.workspace is not None:
                shutil.copytree(example.workspace, workspace)
            else:
                workspace.mkdir()
        argv = ToolAdapter().command(profile, packet, result, workspace, tool.spec.reach.workspace)
        assert argv is not None
        try:
            proc = subprocess.run(argv, env=built.env, cwd=str(base), capture_output=True, text=True,
                                  errors="replace", timeout=EXAMPLE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return ExampleOutcome(example.name, False, f"the tool did not finish within {EXAMPLE_TIMEOUT_S} s")
        try:
            res = json.loads((result / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
            return ExampleOutcome(example.name, False, "the tool could not be run" + (f": {tail}" if tail else ""))
        if res.get("status") != "completed":
            return ExampleOutcome(example.name, False, res.get("notes") or "the tool failed")
        diff = first_difference(example.expected, res.get("output"), "output")
        if diff:
            return ExampleOutcome(example.name, False, diff)
        produced = {a["name"]: result / a["path"] for a in res.get("artifacts", [])}
        for name, want in sorted(example.artifacts.items()):
            got = produced.get(name)
            if got is None:
                return ExampleOutcome(example.name, False, f"artifact {name!r}: expected {want.name}, the tool wrote none")
            diff = bytes_difference(want.read_bytes(), got.read_bytes())
            if diff:
                return ExampleOutcome(example.name, False, f"artifact {name!r}: {diff}")
        return ExampleOutcome(example.name, True)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _write_packet(packet: Path, example: Example) -> None:
    """A packet the runner reads as it reads a dispatched one: the inputs and the declared artifacts."""
    (packet / "inputs").mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    for name, value in sorted(example.values.items()):
        rel = f"inputs/{name}.json"
        (packet / rel).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        entries.append({"name": name, "path": rel, "media_type": "application/json"})
    for name, src in sorted(example.files.items()):
        rel = f"inputs/{src.name}"
        shutil.copyfile(src, packet / rel)
        entries.append({"name": name, "path": rel, "media_type": guess_media_type(src.name)})
    manifest = {
        "protocol": PROTOCOL, "packet_sha256": "example", "inputs": entries,
        "required_artifacts": [], "optional_artifacts": [{"name": artifact_name(n)} for n in sorted(example.artifacts)],
    }
    (packet / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def first_difference(expected: Any, actual: Any, where: str) -> str:
    """The first place ``actual`` differs from ``expected``, in plain words, or ``""``."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in expected:
            if k not in actual:
                return f"{where}.{k}: expected {_show(expected[k])}, the tool gave none"
            d = first_difference(expected[k], actual[k], f"{where}.{k}")
            if d:
                return d
        extra = [k for k in actual if k not in expected]
        return f"{where}.{extra[0]}: not expected, the tool gave {_show(actual[extra[0]])}" if extra else ""
    if isinstance(expected, list) and isinstance(actual, list):
        for i, (e, a) in enumerate(zip(expected, actual)):
            d = first_difference(e, a, f"{where}[{i}]")
            if d:
                return d
        if len(expected) != len(actual):
            return f"{where}: expected {len(expected)} items, the tool gave {len(actual)}"
        return ""
    if _kind(expected) != _kind(actual) or expected != actual:
        return f"{where}: expected {_show(expected)}, the tool gave {_show(actual)}"
    return ""


def _kind(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    return type(v).__name__


def _show(v: Any) -> str:
    text = json.dumps(v, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "..."


def bytes_difference(want: bytes, got: bytes) -> str:
    """Where two files first differ: the line, for text; the byte offset otherwise."""
    if want == got:
        return ""
    try:
        w, g = want.decode("utf-8").splitlines(keepends=True), got.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        n = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), min(len(want), len(got)))
        return f"differs from byte {n} (expected {len(want)} bytes, the tool wrote {len(got)})"
    for i, (a, b) in enumerate(zip(w, g), start=1):
        if a != b:
            return f"line {i}: expected {a!r}, the tool wrote {b!r}"
    if len(w) != len(g):
        return f"expected {len(w)} lines, the tool wrote {len(g)}"
    return "the files differ"
