"""Environments for tools (§6.3; Decisions 0156, 0158, 0159).

An environment is a virtual environment built by ``uv`` from a tool's lock
file, in ``<home>/tools/<lock sha256>-py<major>.<minor>/``, reused by every
project and tool with the same lock and Python. uv never downloads a Python:
a machine with none that fits the tool's ``runtime.version`` cannot run it.

Layout of one environment::

    <id>/venv/       the virtual environment
    <id>/env.json    written last: what was built, from what (its presence means complete)
    <id>.lock        held while building

Every problem here is the machine's, not the step's: ``ToolSetupError`` is a
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

from .tools import LoadedTool

ENV_FILE = "env.json"
BUILD_TIMEOUT_S = 600


class ToolSetupError(Exception):
    """A tool's environment cannot be found or built on this machine (platform)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.failure_class = "platform"


@dataclass(frozen=True)
class ToolEnv:
    id: str
    dir: Path
    python: Path  # the environment's interpreter
    bin_dir: Path  # where entry[0] is looked up
    python_version: str  # exact, e.g. "3.12.7"
    built: bool  # True when this call built it

    def describe(self) -> dict[str, Any]:
        """What ``dispatched`` records about the environment (criterion 7)."""
        return {"env_id": self.id, "python_version": self.python_version}


def tools_home(home: Path) -> Path:
    return home / "tools"


def uv_executable() -> str:
    found = shutil.which("uv")
    if not found:
        raise ToolSetupError("tool.no_uv", "uv is not installed on this machine; Baton builds a tool's environment with it (install uv, then try again)")
    return found


def _bin(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def _run(argv: list[str], *, timeout: int = BUILD_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("VIRTUAL_ENV", "UV_PYTHON"))}
    env["UV_NO_PROGRESS"] = "1"
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(Path.home()))


def find_python(tool: LoadedTool, uv: str) -> tuple[Path, str]:
    """A Python on this machine that fits the tool (never downloaded), and its exact version."""
    spec = tool.spec.runtime.version
    argv = [uv, "python", "find", "--no-python-downloads", "--system", "--no-project"]
    if spec:
        argv.append(spec)
    try:
        proc = _run(argv, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ToolSetupError("tool.no_runtime", f"could not look for a Python for tool {tool.id!r}: {e}") from e
    if proc.returncode != 0 or not proc.stdout.strip():
        want = f"Python {spec}" if spec else "a Python 3"
        raise ToolSetupError(
            "tool.no_runtime",
            f"tool {tool.id!r} needs {want}, and none is installed on this machine (Baton never downloads one): install it, then try again",
        )
    python = Path(proc.stdout.strip().splitlines()[-1])
    return python, _python_version(python)


def _python_version(python: Path) -> str:
    try:
        proc = _run([str(python), "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"], timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ToolSetupError("tool.no_runtime", f"{python} did not start: {e}") from e
    if proc.returncode != 0:
        raise ToolSetupError("tool.no_runtime", f"{python} did not start: {proc.stderr.strip()[-300:]}")
    return proc.stdout.strip()


def env_id(tool: LoadedTool, python_version: str) -> str:
    major_minor = ".".join(python_version.split(".")[:2])
    return f"{tool.lock_sha256}-py{major_minor}"


def existing(tool: LoadedTool, home: Path, python_version: str) -> ToolEnv | None:
    """The tool's environment for this Python when it is complete, else None."""
    eid = env_id(tool, python_version)
    d = tools_home(home) / eid
    info = _read_info(d)
    if info is None:
        return None
    python = Path(info["python"])
    if not python.is_file():
        return None
    return ToolEnv(eid, d, python, _bin(d / "venv"), info.get("python_version", python_version), False)


def _read_info(d: Path) -> dict[str, Any] | None:
    try:
        info = json.loads((d / ENV_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: no env.json yet, or one left by an unfinished build; it is rebuilt
        return None
    return info if isinstance(info, dict) and info.get("python") else None


def ensure(tool: LoadedTool, home: Path) -> ToolEnv:
    """The tool's environment, built from its lock if this machine has none yet (Decision 0159, item 3)."""
    from . import locks

    uv = uv_executable()
    base_python, version = find_python(tool, uv)
    found = existing(tool, home, version)
    if found is not None:
        return found
    eid = env_id(tool, version)
    root = tools_home(home)
    root.mkdir(parents=True, exist_ok=True)
    d = root / eid
    with locks.file_lock(root / f"{eid}.lock"):
        found = existing(tool, home, version)  # another process built it while we waited
        if found is not None:
            return found
        if d.exists():
            shutil.rmtree(d)  # an earlier build that did not finish
        venv = d / "venv"
        _step(tool, [uv, "venv", "--no-python-downloads", "--no-project", "--quiet", "--python", str(base_python), str(venv)], "create its environment")
        python = _bin(venv) / ("python.exe" if os.name == "nt" else "python")
        if tool.requirements:
            lock = tool.root / tool.spec.dependencies.lock
            _step(
                tool,
                [uv, "pip", "install", "--no-python-downloads", "--require-hashes", "--quiet", "--python", str(python), "-r", str(lock)],
                "install its dependencies",
            )
        info = {
            "env_id": eid,
            "tool": tool.id,
            "lock_sha256": tool.lock_sha256,
            "python": str(python),
            "python_version": version,
            "base_python": str(base_python),
            "requirements": [f"{r.name}=={r.version}" for r in tool.requirements],
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "built_by": sys.executable,
        }
        tmp = d / f"{ENV_FILE}.tmp"
        tmp.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, d / ENV_FILE)
    return ToolEnv(eid, d, python, _bin(venv), version, True)


def _step(tool: LoadedTool, argv: list[str], what: str) -> None:
    try:
        proc = _run(argv)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ToolSetupError("tool.build_failed", f"could not {what} for tool {tool.id!r}: {e}") from e
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-8:])
        raise ToolSetupError("tool.build_failed", f"could not {what} for tool {tool.id!r}: {tail}")
