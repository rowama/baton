"""Run a recipe's programs on their worked examples (§5.9; ``baton programs test``; Decision 0162).

Each example is run the way a program step is dispatched: the program's environment
(built if needed, as ``baton programs setup`` does), the program's constructed
environment variables (``engine.program_profile``), and ``python -m
baton.program_runner`` on a packet made from the example, in a fresh scratch
folder. The packet holds the example's ``input.json`` values as JSON inputs
and its ``inputs/`` files as file inputs, so the runner writes the same inputs
file a run would (Decision 0159, item 2). The artifacts the example expects
are the ones the packet declares: any other file the program leaves fails it, as
in a run (0159, item 4).

``output.json`` must equal ``expected.json`` as JSON (a number is not a
boolean, and ``1`` equals ``1.0``); each ``expected/<artifact>`` must equal the
artifact byte for byte. The report names the program, the example and the first
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
from .programs import Example, LoadedProgram, artifact_name

#: How long one example may run.
EXAMPLE_TIMEOUT_S = 600


@dataclass
class ExampleOutcome:
    example: str
    ok: bool
    difference: str = ""  # the first difference, or why the program did not finish

    def as_dict(self) -> dict[str, Any]:
        return {"example": self.example, "ok": self.ok, **({"difference": self.difference} if self.difference else {})}


@dataclass
class ProgramOutcome:
    program: str
    examples: list[ExampleOutcome] = field(default_factory=list)
    problem: str = ""  # the program could not be tested at all (its environment, or no examples when required)
    unbuilt: bool = False  # an engineered program not built yet, skipped with --allow-unbuilt (Decision 0164)

    @property
    def ok(self) -> bool:
        return not self.problem and all(e.ok for e in self.examples)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"program": self.program, "ok": self.ok, "examples": [e.as_dict() for e in self.examples]}
        if self.problem:
            out["problem"] = self.problem
        if self.unbuilt:
            out["unbuilt"] = True
        return out


def run_program_examples(programs: dict[str, LoadedProgram], home: Path, *, require_examples: bool = False,
                      only: str | None = None, repeat: int = 1, allow_unbuilt: bool = False) -> list[ProgramOutcome]:
    """Each program's outcome on its examples: every program, or ``only`` that one.

    ``repeat`` runs each example that many times, and every run must give the
    expected result, so the runs agree with each other (Decision 0164, item 10). An engineered program not built yet fails, or with
    ``allow_unbuilt`` is listed as not built and skipped.
    """
    from . import program_env

    if only is not None and only not in programs:
        raise KeyError(only)
    out: list[ProgramOutcome] = []
    for tid, program in sorted(programs.items()):
        if only is not None and tid != only:
            continue
        result = ProgramOutcome(tid)
        out.append(result)
        if not program.built:
            result.unbuilt = True
            if not allow_unbuilt:
                result.problem = f"program {tid!r} is not built yet: its entry file is not written"
            continue
        if not program.examples:
            if require_examples:
                result.problem = f"program {tid!r} has no examples (add programs/{tid}/examples/<name>/ with input.json and expected.json)"
            continue
        try:
            env = program_env.ensure(program, home)
        except program_env.ProgramSetupError as e:
            result.problem = str(e)
            continue
        for ex in program.examples:
            result.examples.append(run_example(program, ex, env, home, repeat=repeat))
    return out


def run_example(program: LoadedProgram, example: Example, env: Any, home: Path, *, repeat: int = 1) -> ExampleOutcome:
    """Run one example ``repeat`` times; the first failure, naming the run when it is not the first.

    Every run is compared with the expected result, so runs that pass agree
    with each other: ``output.json`` as JSON, artifacts byte for byte.
    """
    for n in range(1, max(1, repeat) + 1):
        outcome = _run_once(program, example, env, home)
        if not outcome.ok:
            if n > 1:
                outcome.difference = f"run {n} of {repeat} gave a different result: {outcome.difference}"
            return outcome
    return ExampleOutcome(example.name, True)


def _run_once(program: LoadedProgram, example: Example, env: Any, home: Path) -> ExampleOutcome:
    from .adapters.program import ProgramAdapter
    from .engine import program_profile
    from .profiles import SetupError, build_env

    profile = program_profile(program, env)
    try:
        built = build_env(profile, home=home, resolve=False)
    except SetupError as e:
        return ExampleOutcome(example.name, False, f"could not run: {e}")
    base = Path(tempfile.mkdtemp(prefix="baton-program-test-"))
    try:
        packet, result = base / "packet", base / "result"
        _write_packet(packet, example)
        workspace = None
        if program.spec.reach.workspace != "none":
            workspace = base / "workspace"
            if example.workspace is not None:
                shutil.copytree(example.workspace, workspace)
            else:
                workspace.mkdir()
        argv = ProgramAdapter().command(profile, packet, result, workspace, program.spec.reach.workspace)
        assert argv is not None
        try:
            proc = subprocess.run(argv, env=built.env, cwd=str(base), capture_output=True, text=True,
                                  errors="replace", timeout=EXAMPLE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return ExampleOutcome(example.name, False, f"the program did not finish within {EXAMPLE_TIMEOUT_S} s")
        try:
            res = json.loads((result / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
            return ExampleOutcome(example.name, False, "the program could not be run" + (f": {tail}" if tail else ""))
        if res.get("status") != "completed":
            return ExampleOutcome(example.name, False, res.get("notes") or "the program failed")
        diff = first_difference(example.expected, res.get("output"), "output")
        if diff:
            return ExampleOutcome(example.name, False, diff)
        produced = {a["name"]: result / a["path"] for a in res.get("artifacts", [])}
        for name, want in sorted(example.artifacts.items()):
            got = produced.get(name)
            if got is None:
                return ExampleOutcome(example.name, False, f"artifact {name!r}: expected {want.name}, the program wrote none")
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
                return f"{where}.{k}: expected {_show(expected[k])}, the program gave none"
            d = first_difference(expected[k], actual[k], f"{where}.{k}")
            if d:
                return d
        extra = [k for k in actual if k not in expected]
        return f"{where}.{extra[0]}: not expected, the program gave {_show(actual[extra[0]])}" if extra else ""
    if isinstance(expected, list) and isinstance(actual, list):
        for i, (e, a) in enumerate(zip(expected, actual)):
            d = first_difference(e, a, f"{where}[{i}]")
            if d:
                return d
        if len(expected) != len(actual):
            return f"{where}: expected {len(expected)} items, the program gave {len(actual)}"
        return ""
    if _kind(expected) != _kind(actual) or expected != actual:
        return f"{where}: expected {_show(expected)}, the program gave {_show(actual)}"
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
        return f"differs from byte {n} (expected {len(want)} bytes, the program wrote {len(got)})"
    for i, (a, b) in enumerate(zip(w, g), start=1):
        if a != b:
            return f"line {i}: expected {a!r}, the program wrote {b!r}"
    if len(w) != len(g):
        return f"expected {len(w)} lines, the program wrote {len(g)}"
    return "the files differ"
