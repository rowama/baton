"""Running worker child processes (§8.7).

Phase 5 runs a worker *attached*: ``run_child`` starts the adapter's command
in its own process group with the profile's constructed environment, waits up
to a time limit, kills the whole process tree on overrun, and writes the raw,
unredacted output to the machine-local log directory (``$BATON_HOME/logs/``),
never into the project. The detached per-dispatch supervisor, running markers,
heartbeats and completion hooks arrive with the async layer (Phase 7) and
build on this.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

#: Upper bound for an attached run until effort bands arrive (Phase 7): the S band.
DEFAULT_TIMEOUT_S = 45 * 60
#: How many trailing bytes of a child's output are kept for classification.
TAIL_BYTES = 4096


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate a child and everything it started."""
    if os.name == "posix":
        import signal

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:  # pragma: no cover - Windows path, exercised in Windows CI (§15.1)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()


@dataclass
class ChildResult:
    exit_code: int | None
    duration_s: float
    timed_out: bool
    log_path: Path
    tail: bytes  # last bytes of combined output; raw, for classification only

    def as_dict(self) -> dict:
        return {"exit_code": self.exit_code, "duration_s": self.duration_s, "timed_out": self.timed_out}


def run_child(argv: list[str], *, env: dict[str, str], cwd: Path, log_path: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> ChildResult:
    """Run ``argv`` to completion (or the time limit). Output goes to ``log_path`` only."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    kwargs: dict = {"start_new_session": True} if os.name == "posix" else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    timed_out = False
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **kwargs)
        except FileNotFoundError as e:
            log.write(f"baton: cannot start {argv[0]!r}: {e}\n".encode())
            return ChildResult(127, 0.0, False, log_path, f"executable_not_found: {argv[0]}".encode())
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
            proc.wait()
    data = log_path.read_bytes()
    return ChildResult(proc.returncode, round(time.monotonic() - started, 3), timed_out, log_path, data[-TAIL_BYTES:])
