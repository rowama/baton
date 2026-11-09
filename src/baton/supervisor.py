"""Running workers: the per-dispatch supervisor, running markers, hooks (§8.7).

**No daemon.** ``dispatch`` starts one small supervisor per process worker,
detached from the caller (POSIX: a new session; Windows: a detached process
group, breaking away from the caller's job when allowed), so a Director's shell or session ending does not affect
it. The supervisor:

1. writes the **running marker** ``.baton/cache/running/<dispatch_id>.json``
   (host, supervisor and worker PIDs, step path, attempt, started, deadline,
   heartbeat every 30 s);
2. snapshots the working tree for ``read`` / ``none`` steps (§6.3), kept next
   to the marker so a later reconciliation can still compare;
3. starts the worker in its own process group with the profile's constructed
   environment (received on stdin, never written to disk), output only to the
   machine-local log ``$BATON_HOME/logs/<run>/<step_path>/attempt-<n>.log``;
4. enforces the deadline: when it passes and ``effort.extend_once`` is on, it
   records ``deadline_extended``, fires the hook with outcome ``overdue`` and
   extends by one band; at the next deadline it terminates the process tree
   (``step_timed_out``, classified, retried while attempts remain);
5. runs intake when the worker exits (under the run's file lock; no lease is
   needed, the supervisor is the runtime finishing work a Director started),
   fires the completion hooks, records them, writes records, makes the
   checkpoint commit, and removes the marker.

**Liveness** (``liveness``) reads a marker against the processes on this
host; ``engine.Api.reconcile`` applies the table in §8.7.

**Hooks** fire after intake on every outcome: project-level (non-secret)
hooks from ``project.yaml`` and machine-level hooks from
``$BATON_HOME/hooks.yaml``, which may reference ``secret:<name>`` (substituted
at execution, shell-quoted, never logged). Both fire when both are configured.
A hook is a shell command line, run with the caller's environment plus
``BATON_RUN_ID``, ``BATON_STEP_PATH``, ``BATON_OUTCOME``,
``BATON_CLASSIFICATION``, ``BATON_DISPATCH_ID``, ``BATON_REPO``,
``BATON_RECORD`` and ``BATON_STEP_STATE``. ``BATON_OUTCOME`` is one of
``passed``, ``gate_failed``, ``needs_human``, ``timed_out``, ``failed`` (the
worker ended without a result) and ``overdue``. Which hook: a ``platform``
classification uses ``on_platform_failure``; a step now waiting on the owner
(human gate or escalation) uses ``on_needs_human``; each falls back to
``on_complete`` (§18 #11: no SME is invoked otherwise). Hook failures are
recorded and never change outcomes.

``run_child`` runs a child *attached* (doctor's auth queries, no-op rounds and
gate preflight).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: Upper bound for attached children that have no effort band (doctor).
DEFAULT_TIMEOUT_S = 45 * 60
#: How many trailing bytes of a child's output are kept for classification.
TAIL_BYTES = 4096
HEARTBEAT_S = float(os.environ.get("BATON_SUPERVISOR_HEARTBEAT_S") or 30)
POLL_S = 0.2
HOOK_TIMEOUT_S = 60
#: How long ``dispatch`` waits for the supervisor to report the worker started.
START_TIMEOUT_S = 60
HOOK_NAMES = ("on_complete", "on_needs_human", "on_platform_failure")
OUTCOMES = ("passed", "gate_failed", "needs_human", "timed_out", "failed", "overdue")


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------


def _new_group_kwargs() -> dict[str, Any]:
    """Start a child as the leader of its own process group, without a console window on Windows."""
    if os.name == "posix":
        return {"start_new_session": True}
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags}


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate a child and everything it started."""
    kill_tree_pid(proc.pid)
    if os.name != "posix":  # pragma: no cover - Windows
        proc.kill()


def kill_tree_pid(pid: int) -> None:
    """Terminate the process group led by ``pid`` (workers are started as group leaders)."""
    if os.name == "posix":
        import signal

        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    else:  # pragma: no cover - Windows path, exercised in Windows CI (§15.1)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def pid_alive(pid: int | None) -> bool:
    """Whether ``pid`` is a live process on this host (a zombie child counts as dead)."""
    if not pid:
        return False
    if os.name == "posix":
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)  # reap it if it is our own exited child
            if done == pid:
                return False
        except ChildProcessError:
            pass
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: it exists, owned by someone else
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


@dataclass
class ChildResult:
    exit_code: int | None
    duration_s: float
    timed_out: bool
    log_path: Path
    tail: bytes  # last bytes of combined output; raw, for classification only

    def as_dict(self) -> dict:
        return {"exit_code": self.exit_code, "duration_s": self.duration_s, "timed_out": self.timed_out}


def _tail(log_path: Path) -> bytes:
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL_BYTES))
            return f.read()
    except OSError:
        return b""


def run_child(argv: list[str] | str, *, env: dict[str, str], cwd: Path, log_path: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> ChildResult:
    """Run ``argv`` attached to completion (or the time limit). Output goes to ``log_path`` only."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **_new_group_kwargs())
        except FileNotFoundError as e:
            first = argv[0] if isinstance(argv, list) else argv
            log.write(f"baton: cannot start {first!r}: {e}\n".encode())
            return ChildResult(127, 0.0, False, log_path, f"executable_not_found: {first}".encode())
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
            proc.wait()
    return ChildResult(proc.returncode, round(time.monotonic() - started, 3), timed_out, log_path, _tail(log_path))


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def fmt(dt: datetime) -> str:
    """Event-log timestamp format (microseconds, UTC)."""
    from .store import format_ts

    return format_ts(dt)


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Running markers
# ---------------------------------------------------------------------------


def running_dir(baton_dir: Path) -> Path:
    return baton_dir / "cache" / "running"


def marker_path(baton_dir: Path, dispatch_id: str) -> Path:
    return running_dir(baton_dir) / f"{dispatch_id}.json"


def tree_path(baton_dir: Path, dispatch_id: str) -> Path:
    return running_dir(baton_dir) / f"{dispatch_id}.tree.json"


def read_marker(baton_dir: Path, dispatch_id: str) -> dict[str, Any] | None:
    try:
        return json.loads(marker_path(baton_dir, dispatch_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _while_open_elsewhere(change: Any) -> None:
    """Run ``change``, retrying for up to about 2 s while Windows refuses it because another process has the file open.

    On Windows a file that another handle has open cannot be replaced or deleted (``PermissionError``). Readers of
    the marker (``await_start`` polls it, reconciliation reads it) hold it only for a moment (§15.1).
    """
    for delay in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0):
        try:
            return change()
        except PermissionError:
            if os.name != "nt":
                raise
            time.sleep(delay)
    change()


def write_marker(baton_dir: Path, marker: dict[str, Any]) -> None:
    p = marker_path(baton_dir, marker["dispatch_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(marker, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    _while_open_elsewhere(lambda: os.replace(tmp, p))


def remove_marker(baton_dir: Path, dispatch_id: str) -> None:
    for p in (marker_path(baton_dir, dispatch_id), tree_path(baton_dir, dispatch_id)):
        try:
            _while_open_elsewhere(p.unlink)
        except FileNotFoundError:
            pass


def markers(baton_dir: Path) -> list[dict[str, Any]]:
    d = running_dir(baton_dir)
    out = []
    for p in sorted(d.glob("d_*.json")) if d.is_dir() else []:
        if p.name.endswith(".tree.json"):
            continue
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


@dataclass
class Liveness:
    """One marker read against this host's processes (§8.7 table)."""

    marker: dict[str, Any] | None
    supervisor_alive: bool
    worker_alive: bool
    elsewhere: bool  # written by another host: cannot be judged here
    overdue: bool

    def as_dict(self) -> dict[str, Any]:
        m = self.marker or {}
        return {
            "marker": self.marker is not None, "supervisor_alive": self.supervisor_alive, "worker_alive": self.worker_alive,
            "elsewhere": self.elsewhere, "overdue": self.overdue, "deadline": m.get("deadline"),
            "heartbeat": m.get("heartbeat"), "extended": m.get("extended", False),
        }


def liveness(baton_dir: Path, dispatch_id: str | None) -> Liveness:
    m = read_marker(baton_dir, dispatch_id) if dispatch_id else None
    if m is None:
        return Liveness(None, False, False, False, False)
    if m.get("host") != socket.gethostname():
        return Liveness(m, False, False, True, False)
    sup = pid_alive(m.get("supervisor_pid"))
    wk = pid_alive(m.get("worker_pid")) if isinstance(m.get("worker_pid"), int) else False
    overdue = bool(m.get("deadline")) and now() > parse(m["deadline"])
    return Liveness(m, sup, wk, False, overdue)


# ---------------------------------------------------------------------------
# Spawning the supervisor
# ---------------------------------------------------------------------------


def _detached(argv: list[str], **kw: Any) -> subprocess.Popen:
    """Start a process that outlives its caller.

    POSIX: a new session (no controlling terminal, its own process group).
    Windows: a detached process in its own group, asking to break away from
    the caller's job object so closing the caller's console or job does not
    end it; when the job forbids breaking away (access denied), it starts
    without that flag and survives as long as the job does.
    """
    if os.name == "posix":
        return subprocess.Popen(argv, start_new_session=True, close_fds=True, **kw)
    base = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
    try:
        return subprocess.Popen(argv, creationflags=base | breakaway, close_fds=True, **kw)
    except PermissionError:
        return subprocess.Popen(argv, creationflags=base, close_fds=True, **kw)


def spawn(spec: dict[str, Any], supervisor_log: Path) -> subprocess.Popen:
    """Start ``python -m baton.supervisor`` detached and hand it ``spec`` on stdin.

    ``spec`` carries the worker's environment (it may hold resolved secrets),
    so it travels through a pipe and is never written to disk.
    """
    supervisor_log.parent.mkdir(parents=True, exist_ok=True)
    with open(supervisor_log, "ab") as log:
        proc = _detached([sys.executable, "-m", "baton.supervisor"], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, cwd=spec["root"])
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(spec).encode("utf-8"))
    proc.stdin.close()
    return proc


def await_start(baton_dir: Path, dispatch_id: str, proc: subprocess.Popen, timeout_s: float = START_TIMEOUT_S) -> dict[str, Any] | None:
    """Wait until the supervisor reports the worker started (or failed to); None if it died first."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        m = read_marker(baton_dir, dispatch_id)
        if m is not None and "worker_pid" in m:
            return m
        if proc.poll() is not None:
            return read_marker(baton_dir, dispatch_id)
        time.sleep(0.02)
    return None


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def load_hooks(project: Any) -> list[tuple[str, dict[str, str]]]:
    """``[(source, {hook_name: command})]`` for project and machine hooks that are configured."""
    from .data import YamlError, load_yaml
    from .models import HooksConfig

    out: list[tuple[str, dict[str, str]]] = []
    proj = {k: v for k, v in project.config.hooks.model_dump().items() if v}
    if proj:
        out.append(("project", proj))
    p = project.home / "hooks.yaml"
    if p.is_file():
        try:
            raw = load_yaml(p) or {}
            machine = HooksConfig.model_validate((raw or {}).get("hooks") or {}).model_dump()
        except (YamlError, ValueError, AttributeError) as e:
            raise HookConfigError(f"{p}: {e}") from e
        machine = {k: v for k, v in machine.items() if v}
        if machine:
            out.append(("machine", machine))
    return out


class HookConfigError(ValueError):
    pass


def wake_path(project: Any) -> str | None:
    """The hook that would wake a Director when a step ends waiting on the owner (§8.7), or None.

    That is the outcome a Director must not miss, so it is the test: a project
    whose only hook is ``on_platform_failure`` has no wake path. A machine
    ``hooks.yaml`` that does not load fires nothing (``fire_hooks``), so it is
    none either; ``doctor`` reports why.
    """
    try:
        configured = load_hooks(project)
    except HookConfigError:
        return None
    for _source, hooks in configured:
        name = choose_hook(hooks, "needs_human", None, needs_owner=True)
        if name is not None:
            return name
    return None


def duration_text(seconds: float) -> str:
    """``about 45 minutes``, ``about 2 hours``, ``about 2.5 hours``: plain words for the owner."""
    minutes = max(1, round(seconds / 60))
    if minutes == 1:
        return "about a minute"
    if minutes < 120 and minutes % 60:
        return f"about {minutes} minutes"
    hours = round(seconds / 1800) / 2
    return "about 1 hour" if hours == 1 else f"about {hours:g} hours"


def _compact(seconds: float) -> str:
    """``45m``, ``2h``, ``90s``: the band as ``project.yaml`` writes it."""
    if seconds % 3600 == 0:
        return f"{seconds / 3600:g}h"
    if seconds % 60 == 0:
        return f"{seconds / 60:g}m"
    return f"{seconds:g}s"


def wake_notice(seconds: float, extend_once: bool, what: str = "this part finishes") -> str:
    """The owner's notice before a dispatch nothing would wake the Director for (decision 0059). No Baton vocabulary."""
    over = " (a little longer if it runs over)" if extend_once else ""
    return (f"I might not notice when {what}. It can take up to {duration_text(seconds)}{over}. "
            "If you haven't heard from me by then, ask me to check on it.")


def wake_info(project: Any, seconds: float | None, extend_once: bool, *, what: str = "this part finishes") -> dict[str, Any]:
    """``wake`` for ``eligible`` / ``sme_eligible``: ``{configured, hook}``, or ``{configured: false, expected, notice}``.

    ``seconds`` is the work's effort band; None (every eligible worker is a
    person, decision 0060) gives no notice.
    """
    hook = wake_path(project)
    if hook is not None:
        return {"configured": True, "hook": hook}
    out: dict[str, Any] = {"configured": False}
    if seconds is not None:
        out["expected"] = _compact(seconds)
        out["notice"] = wake_notice(seconds, extend_once, what)
    return out


NO_WAKE_WARNING = ("no completion hook would wake you when this needs the owner; if you end your turn, "
                   "tell the owner first (`eligible` gives the words in wake.notice)")


def choose_hook(hooks: dict[str, str], outcome: str, classification: str | None, needs_owner: bool) -> str | None:
    """The hook name to run for this outcome, falling back to ``on_complete``."""
    if classification == "platform" and hooks.get("on_platform_failure"):
        return "on_platform_failure"
    if needs_owner and hooks.get("on_needs_human"):
        return "on_needs_human"
    return "on_complete" if hooks.get("on_complete") else None


_SECRET_TOKEN = re.compile(r"secret:([A-Za-z0-9_.-]+)")


def render_hook(command: str, source: str, home: Path) -> tuple[str, list[str]]:
    """Substitute ``secret:<name>`` (machine hooks only), shell-quoted; returns the command and secret values."""
    if source != "machine":
        return command, []
    from .profiles import resolve_secret

    values: list[str] = []

    def sub(m: re.Match[str]) -> str:
        v = resolve_secret(m.group(1), home)
        values.append(v)
        return shlex.quote(v) if os.name == "posix" else v

    return _SECRET_TOKEN.sub(sub, command), values


def run_hook(command: str, env: dict[str, str], cwd: Path, log_path: Path, timeout_s: float = HOOK_TIMEOUT_S) -> ChildResult:
    if os.name == "posix":
        shell: Any = ["/bin/sh", "-c", command]
    else:  # what subprocess's shell=True runs: the command line goes to cmd.exe verbatim
        shell = f'"{env.get("COMSPEC") or os.environ.get("COMSPEC", "cmd.exe")}" /d /s /c "{command}"'
    return run_child(shell, env=env, cwd=cwd, log_path=log_path, timeout_s=timeout_s)


def fire_hooks(project: Any, info: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the configured hooks for one outcome. Returns event data, one per hook run (never the command)."""
    from .profiles import SetupError
    from .redact import redact_text

    results: list[dict[str, Any]] = []
    try:
        configured = load_hooks(project)
    except HookConfigError as e:
        return [{"hook": None, "source": "machine", "outcome": info["outcome"], "ok": False, "error": redact_text(str(e))[:300]}]
    env = dict(os.environ)
    env.update(
        {
            "BATON_RUN_ID": info["run_id"], "BATON_STEP_PATH": info["step_path"], "BATON_OUTCOME": info["outcome"],
            "BATON_CLASSIFICATION": info.get("classification") or "", "BATON_DISPATCH_ID": info.get("dispatch_id") or "",
            "BATON_REPO": str(project.root), "BATON_RECORD": info.get("record") or "", "BATON_STEP_STATE": info.get("step_state") or "",
            "BATON_INCIDENT": info.get("incident") or "",
        }
    )
    for source, hooks in configured:
        name = choose_hook(hooks, info["outcome"], info.get("classification"), info.get("needs_owner", False))
        if name is None:
            continue
        base = {"hook": name, "source": source, "outcome": info["outcome"], "dispatch_id": info.get("dispatch_id")}
        try:
            command, _values = render_hook(hooks[name], source, project.home)
        except SetupError as e:
            results.append({**base, "ok": False, "error": redact_text(str(e))[:300]})
            continue
        log = project.home / "logs" / (info["run_id"] or "project") / "hooks" / f"{info.get('dispatch_id') or 'x'}-{info['outcome']}-{source}.log"
        child = run_hook(command, env, project.root, log)
        ok = child.exit_code == 0 and not child.timed_out
        data = {**base, "ok": ok, "exit_code": child.exit_code, "duration_s": child.duration_s}
        if child.timed_out:
            data["timed_out"] = True
        if not ok:
            last = [ln for ln in child.tail.decode("utf-8", "replace").splitlines() if ln.strip()][-1:] or [""]
            data["message"] = redact_text(last[0])[:300]
        results.append(data)
    return results


# ---------------------------------------------------------------------------
# The supervisor process
# ---------------------------------------------------------------------------


def supervise(spec: dict[str, Any]) -> int:
    """Body of ``python -m baton.supervisor``: run one dispatched worker to its recorded end."""
    from . import gitops
    from .engine import Api
    from .redact import register

    for name in spec.get("secret_names") or []:
        if name in spec["env"]:
            register(spec["env"][name])
    root = Path(spec["root"])
    baton_dir = root / ".baton"
    did = spec["dispatch_id"]
    deadline = parse(spec["deadline"])
    marker: dict[str, Any] = {
        "dispatch_id": did, "run_id": spec["run_id"], "step_path": spec["step_path"], "attempt": spec["attempt"],
        "host": socket.gethostname(), "supervisor_pid": os.getpid(), "started": fmt(now()),
        "deadline": spec["deadline"], "extended": False, "heartbeat": fmt(now()), "log": spec["log_path"],
    }
    write_marker(baton_dir, marker)

    before = None
    if spec.get("check_tree"):
        before = gitops.tree_snapshot(root, spec.get("exclude") or [])
        if before is not None:
            tree_path(baton_dir, did).write_text(json.dumps({"head": before.head, "files": before.files}), encoding="utf-8")

    log_path = Path(spec["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = None
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(
                spec["argv"], cwd=spec["cwd"], env=spec["env"], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                **_new_group_kwargs(),
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            log.write(f"baton: cannot start {spec['argv'][0]!r}: {e}\n".encode())
    marker["worker_pid"] = proc.pid if proc is not None else None
    write_marker(baton_dir, marker)

    api = Api.open(root, director_id=spec.get("director"), home=spec["home"])
    timed_out = False
    if proc is None:
        child = ChildResult(127, 0.0, False, log_path, f"executable_not_found: {spec['argv'][0]}".encode())
    else:
        last_beat = time.monotonic()
        while True:
            if proc.poll() is not None:
                break
            if now() >= deadline:
                if spec.get("extend_once") and not marker["extended"]:
                    previous = fmt(deadline)
                    deadline = deadline + timedelta(seconds=spec["band_s"])
                    marker.update(extended=True, deadline=fmt(deadline))
                    write_marker(baton_dir, marker)
                    if not spec.get("sme"):
                        api.overdue(spec["run_id"], spec["step_path"], spec["attempt"], did, previous, fmt(deadline), spec.get("effort"))
                else:
                    timed_out = True
                    kill_tree(proc)
                    proc.wait()
                    break
            if time.monotonic() - last_beat >= HEARTBEAT_S:
                marker["heartbeat"] = fmt(now())
                write_marker(baton_dir, marker)
                last_beat = time.monotonic()
            time.sleep(POLL_S)
        child = ChildResult(proc.returncode, round(time.monotonic() - started, 3), timed_out, log_path, _tail(log_path))

    changes: list[str] = []
    if before is not None:
        changes = gitops.tree_changes(before, gitops.tree_snapshot(root, spec.get("exclude") or []), root)
    if spec.get("sme"):
        api.sme_complete(spec, child, changes)  # an expert consultation turn (§12.1)
    else:
        api.complete(spec["run_id"], spec["step_path"], spec["attempt"], did, child=child, workspace_changes=changes, adapter=spec["adapter"], worker=spec["worker"])
    remove_marker(baton_dir, did)
    api.close()
    return 0


def selftest_spawn(out_file: Path) -> subprocess.Popen:
    """Start a detached supervisor that only writes its PID and session to ``out_file`` (doctor)."""
    return _detached(
        [sys.executable, "-m", "baton.supervisor", "--selftest", str(out_file)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main() -> int:  # pragma: no cover - exercised through subprocesses
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        info = {"pid": os.getpid(), "sid": os.getsid(0) if os.name == "posix" else None}
        Path(sys.argv[2]).write_text(json.dumps(info), encoding="utf-8")
        return 0
    spec = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    try:
        return supervise(spec)
    except Exception:
        import traceback

        traceback.print_exc()  # to the supervisor log (machine-local)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
