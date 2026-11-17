"""Child-process entrypoint for tool steps (§6.3 ``tool``; Decisions 0154, 0158, 0159).

``python -m baton.tool_runner --packet DIR --result DIR --tool-dir DIR --bin-dir DIR --entry JSON [--workspace DIR] [--secret-names JSON]``

The runtime starts this under the tool's constructed environment (clean: only
the secrets the tool names, a minimal PATH). The tool never sees the packet
protocol. This runner:

1. writes ``inputs.json`` from the packet: one object keyed by input name, a
   JSON input as its value, any other input as ``{"path", "media_type"}``
   (an input given more than once, a ``many`` role, as a list in order);
2. makes a fresh, empty scratch folder (the tool's working directory) and an
   empty output folder, outside the repository;
3. runs the entry command, with ``{input}``, ``{output}``, ``{tool}`` and
   ``{workspace}`` filled in and its first word found in the environment's
   ``bin`` folder only; no shell runs it;
4. turns ``output.json`` and the declared artifacts into ``result.json``:
   exit 0 with a JSON object in ``output.json`` and no undeclared file is
   ``completed``; anything else is ``failed``, with the reason and the last
   lines of the tool's error output in ``notes`` (the values of the secrets
   it names masked, since notes enter the record). A tool cannot return
   ``blocked`` or ask questions. Intake and the gates judge the result.
5. ends anything the tool left running once it has exited, and fails the
   result naming it (``run_contained``; Decision 0164, item 6): a tool
   keeps no service running (Decision 0155, item 4).

A problem that is not the step's (the command is not in the environment)
writes no result: one line ``baton-worker: failure=platform code=<code>
message=<text>`` on stderr and a non-zero exit, as ``worker_runner`` does (§8.8).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

#: Lines of the tool's error output kept in a failed result's notes.
TAIL_LINES = 20


def _platform_failure(code: str, message: str) -> int:
    print(f"baton-worker: failure=platform code={code} message={message}", file=sys.stderr)
    return 3


def inputs_document(packet_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """The inputs file's content (Decision 0159, item 2)."""
    out: dict[str, Any] = {}
    many: set[str] = set()
    for entry in sorted(manifest.get("inputs", []), key=lambda e: (e["name"], e.get("index") or 0)):
        path = (packet_dir / entry["path"]).resolve()
        media = entry.get("media_type")
        if media == "application/json" or (media is None and path.suffix == ".json"):
            value: Any = json.loads(path.read_text(encoding="utf-8"))
        else:
            value = {"path": str(path), "media_type": media}
        name = entry["name"]
        if entry.get("index") is not None:
            many.add(name)
            out.setdefault(name, []).append(value)
        elif name in out:
            out[name] = [*(out[name] if name in many else [out[name]]), value]
            many.add(name)
        else:
            out[name] = value
    return out


def fill(entry: list[str], values: dict[str, str]) -> list[str]:
    out = []
    for word in entry:
        for key, value in values.items():
            word = word.replace("{" + key + "}", value)
        out.append(word)
    return out


def collect(out_dir: Path, manifest: dict[str, Any]) -> tuple[dict[str, Path], list[str]]:
    """Declared artifacts found in the output folder, and why the folder is wrong (Decision 0159, item 4)."""
    declared = [a["name"] for a in manifest.get("required_artifacts", []) + manifest.get("optional_artifacts", [])]
    found: dict[str, Path] = {}
    problems: list[str] = []
    for p in sorted(out_dir.iterdir()):
        if p.name == "output.json":
            continue
        name = p.name if p.name in declared else (p.name.split(".", 1)[0] if p.name.split(".", 1)[0] in declared else None)
        if p.is_dir() or name is None:
            problems.append(f"the tool left {p.name!r}, which is not output.json or a declared artifact ({', '.join(declared) or 'none declared'})")
        elif name in found:
            problems.append(f"the tool left two files for artifact {name!r}: {found[name].name!r} and {p.name!r}")
        else:
            found[name] = p
    return found, problems


def envelope(manifest: dict[str, Any], status: str, output: Any, artifacts: list[dict[str, str]], notes: str) -> dict[str, Any]:
    return {
        "protocol": manifest["protocol"], "packet_sha256": manifest["packet_sha256"], "status": status,
        "output": output, "artifacts": artifacts, "notes": notes, "questions_for_human": [], "process_feedback": [],
    }


def write(result_dir: Path, env: dict[str, Any]) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    tmp = result_dir / "result.json.tmp"
    tmp.write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, result_dir / "result.json")


def _tail(text: str, secrets: list[str]) -> str:
    from .redact import REDACTED

    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, REDACTED)
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-TAIL_LINES:])


def run(packet_dir: Path, result_dir: Path, tool_dir: Path, bin_dir: Path, entry: list[str], workspace: str | None,
        secret_names: list[str] | None = None) -> int:
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    command = shutil.which(entry[0], path=str(bin_dir))
    if command is None:
        return _platform_failure("tool_command_missing", f"{entry[0]!r} is not in the tool's environment ({bin_dir})")
    base = Path(tempfile.mkdtemp(prefix="baton-tool-"))
    try:
        scratch, out_dir, inputs = base / "work", base / "output", base / "inputs.json"
        scratch.mkdir()
        out_dir.mkdir()
        inputs.write_text(json.dumps(inputs_document(packet_dir, manifest), ensure_ascii=False, indent=2), encoding="utf-8")
        values = {"input": str(inputs), "output": str(out_dir), "tool": str(tool_dir)}
        if workspace:
            values["workspace"] = workspace
        argv = [command, *fill(entry[1:], values)]
        env = {k: v for k, v in os.environ.items() if not k.startswith("BATON_") and k not in ("PYTHONHOME", "PYTHONPATH")}
        env["PATH"] = os.pathsep.join([str(bin_dir), env.get("PATH", "")]).rstrip(os.pathsep)
        env["VIRTUAL_ENV"] = str(bin_dir.parent)
        returncode, stdout, stderr, left = run_contained(argv, scratch, env, base)
        sys.stdout.write(stdout)  # into the attempt's log
        sys.stderr.write(stderr)
        if left:
            write(result_dir, envelope(manifest, "failed", None, [],
                                       f"the tool left a process running after it finished ({', '.join(left)}); it was stopped. "
                                       "A tool keeps no service running: everything it starts must end before it does"))
            return 0
        if returncode != 0:
            tail = _tail(stderr, [os.environ[n] for n in secret_names or [] if os.environ.get(n)])
            write(result_dir, envelope(manifest, "failed", None, [], f"the tool exited with code {returncode}" + (f":\n{tail}" if tail else "")))
            return 0
        try:
            output = json.loads((out_dir / "output.json").read_text(encoding="utf-8"))
        except FileNotFoundError:  # expected: a tool that wrote no output.json; the result says so
            output, why = None, "the tool finished without writing output.json"
        except (ValueError, UnicodeDecodeError) as e:
            output, why = None, f"output.json is not valid JSON ({e})"
        else:
            why = "" if isinstance(output, dict) else "output.json must hold a JSON object"
        found, problems = collect(out_dir, manifest)
        if why or problems:
            write(result_dir, envelope(manifest, "failed", None, [], "; ".join([w for w in [why] if w] + problems)))
            return 0
        listed = []
        (result_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        for name, path in sorted(found.items()):
            shutil.copyfile(path, result_dir / "artifacts" / path.name)
            listed.append({"name": name, "path": f"artifacts/{path.name}"})
        write(result_dir, envelope(manifest, "completed", output, listed, ""))
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def run_contained(argv: list[str], cwd: Path, env: dict[str, str], base: Path) -> tuple[int, str, str, list[str]]:
    """Run the tool and wait for it; then end anything it left running (Decision 0164, item 6).

    Returns the exit code, its output and error output, and a description of
    each process still running when the tool itself had exited (empty when
    none). The tool runs in its own process group on POSIX and in a job object
    on Windows, so what it starts can be found and ended. Its output goes to
    files, not pipes, so a process left holding them cannot stall the runner.
    A process that leaves the group on purpose (``setsid``) is not found.
    """
    out_path, err_path = base / "stdout.txt", base / "stderr.txt"
    with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
        if os.name == "posix":
            proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL,
                                    start_new_session=True)
            proc.wait()
            left = _posix_leftovers(proc.pid)
        else:  # pragma: no cover - Windows path, exercised in Windows CI (§15.1)
            job = _WinJob()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00000004  # CREATE_SUSPENDED: in the job before it runs
            proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL,
                                    creationflags=flags)
            job.assign_and_resume(proc)
            proc.wait()
            left = job.leftovers()
            job.close()
    read = lambda p: p.read_bytes().decode("utf-8", errors="replace")  # noqa: E731
    return proc.returncode, read(out_path), read(err_path), left


def _posix_leftovers(pgid: int) -> list[str]:
    """Processes still in the tool's group, named where the system says (Linux ``/proc``), then killed."""
    import signal

    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):  # expected: the group is empty, so nothing was left
        return []
    left = []
    proc_dir = Path("/proc")
    if proc_dir.is_dir():
        for d in proc_dir.iterdir():
            if not d.name.isdigit():
                continue
            try:
                stat = (d / "stat").read_text()
            except OSError:  # expected: the process ended while we looked
                continue
            name, rest = stat[stat.index("(") + 1:stat.rindex(")")], stat[stat.rindex(")") + 2:].split()
            if len(rest) > 2 and rest[0] != "Z" and int(rest[2]) == pgid:
                left.append(f"{name} (pid {d.name})")
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):  # expected: it ended on its own meanwhile
        pass
    if proc_dir.is_dir():
        return sorted(left)  # only zombies awaiting their reaper: nothing is running
    return [f"process group {pgid}"]


class _WinJob:  # pragma: no cover - Windows path, exercised in Windows CI (§15.1)
    """A Windows job object holding the tool and everything it starts."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k.CreateJobObjectW.restype = wintypes.HANDLE
        self._k.OpenThread.restype = wintypes.HANDLE
        self.handle = self._k.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")

    def assign_and_resume(self, proc: subprocess.Popen) -> None:
        import ctypes

        if not self._k.AssignProcessToJobObject(self.handle, int(proc._handle)):  # type: ignore[attr-defined]
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        self._resume(proc.pid)

    def _resume(self, pid: int) -> None:
        """Resume the suspended main thread of ``pid`` (a Toolhelp snapshot of threads)."""
        import ctypes
        from ctypes import wintypes

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                        ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                        ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

        self._k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snap = self._k.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(THREADENTRY32)
        ok = self._k.Thread32First(snap, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                th = self._k.OpenThread(0x0002, False, entry.th32ThreadID)  # THREAD_SUSPEND_RESUME
                if th:
                    self._k.ResumeThread(th)
                    self._k.CloseHandle(th)
            ok = self._k.Thread32Next(snap, ctypes.byref(entry))
        self._k.CloseHandle(snap)

    def leftovers(self) -> list[str]:
        import ctypes
        from ctypes import wintypes

        class BASIC(ctypes.Structure):
            _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                        ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                        ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                        ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

        info = BASIC()
        self._k.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None)
        if info.ActiveProcesses == 0:
            return []
        self._k.TerminateJobObject(self.handle, 1)
        return [f"{info.ActiveProcesses} process{'es' if info.ActiveProcesses != 1 else ''} it started"]

    def close(self) -> None:
        self._k.CloseHandle(self.handle)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="baton.tool_runner")
    ap.add_argument("--packet", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--tool-dir", required=True)
    ap.add_argument("--bin-dir", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--workspace")
    ap.add_argument("--secret-names", default="[]")
    a = ap.parse_args(argv)
    return run(Path(a.packet), Path(a.result), Path(a.tool_dir), Path(a.bin_dir), json.loads(a.entry), a.workspace, json.loads(a.secret_names))


if __name__ == "__main__":
    sys.exit(main())
