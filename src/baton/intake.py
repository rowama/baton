"""Intake: result validation and gates (§8.10, §9.1).

Intake *evaluates*; ``engine.py`` turns each evaluation into events. Nothing
here appends to a log.

``read_result`` checks, in order, and collects every problem it finds:

1. the packet is intact and is the one the runtime built for this attempt;
2. ``result.json`` exists, parses and matches the result envelope (§7.2);
3. ``protocol`` and the echoed ``packet_sha256`` match;
4. a ``completed`` result's ``output`` validates against the step's output
   schema (Draft 2020-12, format checks on);
5. **provenance:** every listed artifact is declared by the step, listed once,
   and is a regular file inside the result directory; it is ingested into the
   run's CAS. Every required artifact is present. Files not listed in
   ``result.json`` are never registered.

Gates that need work beyond the result run separately: ``script`` here, and
``human`` through the engine's decision call.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import jinja2
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .data import read_text
from .models import Result, ScriptGate, Step
from .packet import PROTOCOL, RunContext, output_schema_for, verify_packet
from .redact import redact_bytes
from .store import canonical_json
from .supervisor import kill_tree

#: Variables a script gate's command keeps from the runtime's environment.
#: Gates run under the runtime's own reduced environment, never a worker profile's.
GATE_ENV_ALLOW = ("PATH", "HOME", "USERPROFILE", "LANG", "LC_ALL", "TERM", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR")
FEEDBACK_TAIL_LINES = 40
DEFAULT_SCRIPT_TIMEOUT_S = 900


@dataclass
class Submission:
    """What intake made of one attempt's result directory."""

    result_sha256: str | None = None
    status: str | None = None
    output: Any = None
    output_sha256: str | None = None
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""
    questions: list[dict[str, Any]] = field(default_factory=list)
    process_feedback: list[Any] = field(default_factory=list)
    dispositions: list[Any] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    #: ``passed`` / ``failed`` when the step's output schema was checked; ``None`` when not (0087).
    output_schema: str | None = None

    def registered(self) -> dict[str, Any]:
        """The hashes downstream steps may consume once the step passes."""
        return {"output_sha256": self.output_sha256, "artifacts": self.artifacts}


def _schema_errors(schema: dict[str, Any], value: Any) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    out = []
    for err in sorted(validator.iter_errors(value), key=lambda e: list(map(str, e.absolute_path))):
        loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"output {loc}: {err.message}")
    return out


def read_result(ctx: RunContext, step: Step, result_dir: Path, packet_dir: Path, expected_packet_sha256: str) -> Submission:
    sub = Submission()
    recorded, problems = verify_packet(packet_dir)
    sub.problems += problems
    if recorded is not None and recorded != expected_packet_sha256:
        sub.problems.append("the packet on disk is not the one the runtime recorded for this attempt")

    rpath = result_dir / "result.json"
    if not rpath.is_file() or rpath.is_symlink():
        sub.problems.append("result/result.json is missing")
        return sub
    raw = rpath.read_bytes()
    sub.result_sha256 = ctx.log.cas.put(raw)
    try:
        obj = json.loads(read_text(rpath))
        result = Result.model_validate(obj)
    except json.JSONDecodeError as e:
        sub.problems.append(f"result.json is not valid JSON ({e})")
        return sub
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"]) or "(root)"
            sub.problems.append(f"result.json {loc}: {err['msg']}")
        return sub

    sub.status = result.status
    sub.notes = result.notes
    sub.questions = list(result.questions_for_human)
    sub.process_feedback = list(result.process_feedback)
    sub.dispositions = list(result.dispositions)
    if result.protocol != PROTOCOL:
        sub.problems.append(f"protocol is {result.protocol!r}; expected {PROTOCOL!r}")
    if result.packet_sha256 != expected_packet_sha256:
        sub.problems.append("packet_sha256 does not match this attempt's packet")
    if result.status != "completed":
        return sub

    if step.output_schema:
        errors = _schema_errors(output_schema_for(ctx.recipe, step), result.output)
        sub.problems += errors
        sub.output_schema = "failed" if errors else "passed"
    try:
        sub.output_sha256 = ctx.log.cas.put(canonical_json(result.output).encode("utf-8"))
    except (TypeError, ValueError) as e:  # pragma: no cover - json.loads only yields JSON values
        sub.problems.append(f"output is not JSON ({e})")
    sub.output = result.output
    _ingest_artifacts(ctx, step, result, result_dir, sub)
    return sub


def _ingest_artifacts(ctx: RunContext, step: Step, result: Result, result_dir: Path, sub: Submission) -> None:
    declared = {a.name: a for a in step.artifacts}
    root = result_dir.resolve()
    for item in result.artifacts:
        if item.name not in declared:
            sub.problems.append(f"artifact {item.name!r} is not declared by this step")
            continue
        if item.name in sub.artifacts:
            sub.problems.append(f"artifact {item.name!r} is listed more than once")
            continue
        rel = PurePosixPath(item.path.replace("\\", "/"))
        target = result_dir / rel
        if rel.is_absolute() or ".." in rel.parts:
            sub.problems.append(f"artifact {item.name!r}: path {item.path!r} must be inside the result directory")
            continue
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            sub.problems.append(f"artifact {item.name!r}: {item.path!r} is a link; artifacts must be regular files in the result directory")
            continue
        if not target.is_file():
            sub.problems.append(f"artifact {item.name!r}: {item.path!r} does not exist")
            continue
        sha = ctx.log.cas.put_file(target)
        entry: dict[str, Any] = {"sha256": sha, "filename": rel.name}
        if declared[item.name].media_type:
            entry["media_type"] = declared[item.name].media_type
        sub.artifacts[item.name] = entry
    for name, a in declared.items():
        if a.required and name not in sub.artifacts and not any(i.name == name for i in result.artifacts):
            sub.problems.append(f"required artifact {name!r} is missing")


# ---------------------------------------------------------------------------
# Script gates
# ---------------------------------------------------------------------------


@dataclass
class GateOutcome:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    configuration_error: bool = False  # retrying cannot help; the owner must fix configuration


def _gate_env(ctx: RunContext, step_path: str) -> dict[str, str]:
    env = {k: os.environ[k] for k in GATE_ENV_ALLOW if k in os.environ}
    env.update({"BATON_RUN_ID": ctx.run_id, "BATON_STEP_PATH": step_path})
    return env


def render_command(ctx: RunContext, template: str) -> str:
    """Substitute ``project.*``, ``paths.*`` and ``run.*`` in a gate command. Undefined names raise."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False, keep_trailing_newline=False)
    variables = {
        "project": ctx.project.get("project", {}),
        "paths": ctx.project.get("paths", {}),
        "run": {"id": ctx.run_id},
    }
    return env.from_string(template).render(**variables)


def run_script_gate(ctx: RunContext, gate: ScriptGate, step_path: str) -> GateOutcome:
    """Run the command in the project root (or ``cwd`` inside it) under a reduced environment."""
    try:
        command = render_command(ctx, gate.run)
    except jinja2.TemplateError as e:
        return GateOutcome(False, [f"script gate command {gate.run!r} cannot be rendered: {e}"], {"command": gate.run}, True)
    root = ctx.store.root.resolve()
    cwd = (root / gate.cwd).resolve() if gate.cwd else root
    if not cwd.is_relative_to(root) or not cwd.is_dir():
        return GateOutcome(False, [f"script gate cwd {gate.cwd!r} is not a directory inside the project"], {"command": command}, True)
    timeout = gate.timeout_s or DEFAULT_SCRIPT_TIMEOUT_S
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        env=_gate_env(ctx, step_path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_tree(proc)
        out, _ = proc.communicate()
    duration = round(time.monotonic() - started, 3)
    # Output enters the run's record, so it is redacted first (§15.2).
    out = redact_bytes(out or b"")
    output_sha = ctx.log.cas.put(out)
    data = {"command": command, "exit_code": proc.returncode, "duration_s": duration, "output_sha256": output_sha}
    if timed_out:
        data["timed_out"] = True
        return GateOutcome(False, [f"`{command}` did not finish within {timeout} s"] + _tail(out), data)
    if proc.returncode != 0:
        return GateOutcome(False, [f"`{command}` exited {proc.returncode}"] + _tail(out), data)
    return GateOutcome(True, [], data)


def _tail(out: bytes | None) -> list[str]:
    text = (out or b"").decode("utf-8", errors="replace").rstrip()
    if not text:
        return []
    lines = text.splitlines()[-FEEDBACK_TAIL_LINES:]
    return ["output (last lines):\n" + "\n".join(lines)]
