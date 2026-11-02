"""Gate-preflight probe (§13.4): ``python -m baton.probe --marker <file> --nonce <n> -- <command>``.

``doctor`` asks a write-capable harness worker to run this exact command
under its own write-mode args. The probe runs ``<command>`` through the shell
in the current directory and then writes ``{"nonce", "exit_code"}`` to the
marker. A missing marker afterwards means the worker's permission mode or
sandbox kept the command from running at all; a different exit code than
the runtime's own run means the sandbox changed its outcome. Either would
make the step's script gates fail, so it is caught before a real run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="baton.probe")
    ap.add_argument("--marker", required=True)
    ap.add_argument("--nonce", required=True)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    ns = ap.parse_args(argv)
    words = ns.command[1:] if ns.command[:1] == ["--"] else ns.command
    command = " ".join(words)
    code = subprocess.run(command, shell=True).returncode
    marker = Path(ns.marker)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"nonce": ns.nonce, "exit_code": code}), encoding="utf-8")
    return code


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    sys.exit(main())
