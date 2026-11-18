"""The ``program`` adapter (§6.3): a script a recipe ships, run with no model (§5.9).

A program step has no worker profile on the machine: the runtime makes one in
memory for the step's program (``program:<id>``, ``engine.program_profile``), with the
program's folder, its environment's ``bin`` folder and its entry command in
``options``, and only the secrets the program names in ``auth.env``. The child is
``python -m baton.program_runner``, as ``litellm_api`` runs ``worker_runner``; it
speaks the packet protocol so the program never has to.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..models import WorkerProfile
from ..profiles import SetupError

#: Prefix of the in-memory profile name of a program: ``program:<id>``.
PROFILE_PREFIX = "program:"


class ProgramAdapter:
    name = "program"
    #: Starts the runtime's own interpreter, which finds the entry command in the program's environment.
    needs_executable = False
    #: A program can write anywhere it can reach, so read and none steps get the tree check (§6.3).
    touches_files = True
    config_home_var: str | None = None
    failure_signals: list[dict[str, Any]] = [
        {"pattern": r"baton-worker: failure=(\w+) code=(\w+)", "class_from": 1},
    ]

    def check_profile(self, profile: WorkerProfile) -> None:
        missing = [k for k in ("program", "program_dir", "bin_dir", "entry") if k not in profile.options]
        if missing:
            raise SetupError("configuration.not_a_program", f"a program profile is made by the runtime for a program step; this one lacks {', '.join(missing)}", "configuration")

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str) -> list[str] | None:
        self.check_profile(profile)
        o = profile.options
        argv = [sys.executable, "-m", "baton.program_runner", "--packet", str(packet_dir), "--result", str(result_dir),
                "--program-dir", str(o["program_dir"]), "--bin-dir", str(o["bin_dir"]), "--entry", json.dumps(o["entry"])]
        if workspace is not None and mode != "none":
            argv += ["--workspace", str(workspace)]
        if profile.auth.env:  # names only: the runner masks their values in the notes it records
            argv += ["--secret-names", json.dumps(sorted(profile.auth.env))]
        if o.get("wait"):  # a waiting step's check reports met (§5.9; Decision 0165)
            argv.append("--wait")
        return argv

    def preflight(self, profile: WorkerProfile, packet_dir: Path) -> list[str]:
        return []

    def postprocess(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, proc_result: Any) -> None:
        return None

    def handoff(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path) -> str:
        return f"program {profile.options.get('program')} from the recipe; the runtime runs it and takes in the result."
