"""Environments for programs (§6.3; Decisions 0156, 0158, 0159).

An environment is a virtual environment built by ``uv`` from a program's lock
file, in ``<home>/programs/<lock sha256>-py<major>.<minor>/``, reused by every
project and program with the same lock and Python. uv never downloads a Python:
a machine with none that fits the program's ``runtime.version`` cannot run it.

Layout of one environment::

    <id>/venv/       the virtual environment
    <id>/env.json    written last: what was built, from what (its presence means complete)
    <id>.lock        held while building

Every problem here is the machine's, not the step's: ``ProgramSetupError`` is a
platform failure with a plain reason (2026-11-tool-steps criterion 5).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .programs import LoadedProgram

ENV_FILE = "env.json"
BUILD_TIMEOUT_S = 600


class ProgramSetupError(Exception):
    """A program's environment cannot be found or built on this machine (platform)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.failure_class = "platform"


@dataclass(frozen=True)
class ProgramEnv:
    id: str
    dir: Path
    python: Path  # the environment's interpreter
    bin_dir: Path  # where entry[0] is looked up
    python_version: str  # exact, e.g. "3.12.7"
    built: bool  # True when this call built it

    def describe(self) -> dict[str, Any]:
        """What ``dispatched`` records about the environment (criterion 7)."""
        return {"env_id": self.id, "python_version": self.python_version}


def programs_home(home: Path) -> Path:
    return home / "programs"


def uv_executable() -> str:
    found = shutil.which("uv")
    if not found:
        raise ProgramSetupError("program.no_uv", "uv is not installed on this machine; Baton builds a program's environment with it (install uv, then try again)")
    return found


def _bin(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def _run(argv: list[str], *, timeout: int = BUILD_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("VIRTUAL_ENV", "UV_PYTHON"))}
    env["UV_NO_PROGRESS"] = "1"
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(Path.home()))


def find_python(program: LoadedProgram, uv: str) -> tuple[Path, str]:
    """A Python on this machine that fits the program (never downloaded), and its exact version."""
    spec = program.spec.runtime.version
    argv = [uv, "python", "find", "--no-python-downloads", "--system", "--no-project"]
    if spec:
        argv.append(spec)
    try:
        proc = _run(argv, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ProgramSetupError("program.no_runtime", f"could not look for a Python for program {program.id!r}: {e}") from e
    if proc.returncode != 0 or not proc.stdout.strip():
        want = f"Python {spec}" if spec else "a Python 3"
        raise ProgramSetupError(
            "program.no_runtime",
            f"program {program.id!r} needs {want}, and none is installed on this machine (Baton never downloads one): install it, then try again",
        )
    python = Path(proc.stdout.strip().splitlines()[-1])
    return python, _python_version(python)


def _python_version(python: Path) -> str:
    try:
        proc = _run([str(python), "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"], timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ProgramSetupError("program.no_runtime", f"{python} did not start: {e}") from e
    if proc.returncode != 0:
        raise ProgramSetupError("program.no_runtime", f"{python} did not start: {proc.stderr.strip()[-300:]}")
    return proc.stdout.strip()


def env_id(program: LoadedProgram, python_version: str) -> str:
    major_minor = ".".join(python_version.split(".")[:2])
    return f"{program.lock_sha256}-py{major_minor}"


def existing(program: LoadedProgram, home: Path, python_version: str) -> ProgramEnv | None:
    """The program's environment for this Python when it is complete, else None."""
    eid = env_id(program, python_version)
    d = programs_home(home) / eid
    info = _read_info(d)
    if info is None:
        return None
    python = Path(info["python"])
    if not python.is_file():
        return None
    return ProgramEnv(eid, d, python, _bin(d / "venv"), info.get("python_version", python_version), False)


def _read_info(d: Path) -> dict[str, Any] | None:
    try:
        info = json.loads((d / ENV_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: no env.json yet, or one left by an unfinished build; it is rebuilt
        return None
    return info if isinstance(info, dict) and info.get("python") else None


def ensure(program: LoadedProgram, home: Path) -> ProgramEnv:
    """The program's environment, built from its lock if this machine has none yet (Decision 0159, item 3)."""
    from . import locks

    uv = uv_executable()
    base_python, version = find_python(program, uv)
    found = existing(program, home, version)
    if found is not None:
        return found
    eid = env_id(program, version)
    root = programs_home(home)
    root.mkdir(parents=True, exist_ok=True)
    d = root / eid
    with locks.file_lock(root / f"{eid}.lock"):
        found = existing(program, home, version)  # another process built it while we waited
        if found is not None:
            return found
        if d.exists():
            shutil.rmtree(d)  # an earlier build that did not finish
        venv = d / "venv"
        _step(program, [uv, "venv", "--no-python-downloads", "--no-project", "--quiet", "--python", str(base_python), str(venv)], "create its environment")
        python = _bin(venv) / ("python.exe" if os.name == "nt" else "python")
        if program.requirements:
            lock = program.root / program.spec.dependencies.lock
            _step(
                program,
                [uv, "pip", "install", "--no-python-downloads", "--require-hashes", "--quiet", "--python", str(python), "-r", str(lock)],
                "install its dependencies",
            )
        info = {
            "env_id": eid,
            "program": program.id,
            "lock_sha256": program.lock_sha256,
            "python": str(python),
            "python_version": version,
            "base_python": str(base_python),
            "requirements": [f"{r.name}=={r.version}" for r in program.requirements],
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "built_by": sys.executable,
        }
        tmp = d / f"{ENV_FILE}.tmp"
        tmp.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, d / ENV_FILE)
    return ProgramEnv(eid, d, python, _bin(venv), version, True)


def _step(program: LoadedProgram, argv: list[str], what: str) -> None:
    try:
        proc = _run(argv)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ProgramSetupError("program.build_failed", f"could not {what} for program {program.id!r}: {e}") from e
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-8:])
        raise ProgramSetupError("program.build_failed", f"could not {what} for program {program.id!r}: {tail}")


# ---------------------------------------------------------------------------
# Readiness and the owner's summary (2026-11-tool-steps criteria 6, 10)
# ---------------------------------------------------------------------------


@dataclass
class Readiness:
    """Is this program ready on this machine, and if not, why (one answer for check, doctor, start, eligible)."""

    program: str
    ready: bool
    reasons: list[str]  # why not ready: what to install or set
    env: ProgramEnv | None = None  # the built environment, when there is one
    note: str = ""  # e.g. that the environment is built at first use

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"program": self.program, "ready": self.ready, "reasons": list(self.reasons)}
        if self.env is not None:
            out["env_id"] = self.env.id
        if self.note:
            out["note"] = self.note
        return out


def readiness(program: LoadedProgram, home: Path) -> Readiness:
    """Whether ``program`` can run here: uv and a fitting Python found, its named secrets stored.

    An environment not built yet does not make a program not ready: dispatch
    builds it (Decision 0159, item 3); ``baton programs setup`` builds it ahead.
    """
    from .profiles import secret_env_name, secret_places

    reasons: list[str] = []
    env = None
    note = ""
    try:
        uv = uv_executable()
        _python, version = find_python(program, uv)
        env = existing(program, home, version)
        if env is None:
            note = "its environment is built at first use, or now with `baton programs setup`"
    except ProgramSetupError as e:
        reasons.append(str(e))
    for name in program.spec.reach.secrets:
        if not secret_places(name, home):
            reasons.append(f"secret {name!r} is not stored: set {secret_env_name(name)}, or store it with the OS keyring or in {home / 'secrets' / name}")
    return Readiness(program.id, not reasons, reasons, env, note)


def describe(program: LoadedProgram) -> dict[str, str]:
    """A program in the owner's terms: what it does, what it needs installed, what it may touch (criterion 10)."""
    spec = program.spec
    python = f"Python {spec.runtime.version}" if spec.runtime.version else "Python 3"
    pkgs = [r.name for r in program.requirements]
    needs = python + (f" and {len(pkgs)} package{'s' if len(pkgs) != 1 else ''} ({', '.join(pkgs)}), installed by Baton from pinned versions" if pkgs else ", nothing else")
    ws = {"none": "does not open your project's files", "read": "reads your project's files but may not change them",
          "write": "may change your project's files"}[spec.reach.workspace]
    touch = [ws, "uses the internet" if spec.reach.network else "does not use the internet"]
    if spec.reach.secrets:
        touch.append(f"is given {', '.join(spec.reach.secrets)}")
    return {"program": program.id, "does": spec.description, "needs": needs, "touches": "; ".join(touch)}
