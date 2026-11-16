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
        proc = subprocess.run(argv, cwd=str(scratch), env=env, capture_output=True, text=True, errors="replace")
        sys.stdout.write(proc.stdout)  # into the attempt's log
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            tail = _tail(proc.stderr, [os.environ[n] for n in secret_names or [] if os.environ.get(n)])
            write(result_dir, envelope(manifest, "failed", None, [], f"the tool exited with code {proc.returncode}" + (f":\n{tail}" if tail else "")))
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
