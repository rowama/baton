"""The ``tool`` adapter (§6.3): a script a recipe ships, run with no model (§5.9).

A tool step has no worker profile on the machine: the runtime makes one in
memory for the step's tool (``tool:<id>``, ``engine.tool_profile``), with the
tool's folder, its environment's ``bin`` folder and its entry command in
``options``, and only the secrets the tool names in ``auth.env``. The child is
``python -m baton.tool_runner``, as ``litellm_api`` runs ``worker_runner``; it
speaks the packet protocol so the tool never has to.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..models import WorkerProfile
from ..profiles import SetupError

#: Prefix of the in-memory profile name of a tool: ``tool:<id>``.
PROFILE_PREFIX = "tool:"


class ToolAdapter:
    name = "tool"
    #: Starts the runtime's own interpreter, which finds the entry command in the tool's environment.
    needs_executable = False
    #: A tool can write anywhere it can reach, so read and none steps get the tree check (§6.3).
    touches_files = True
    config_home_var: str | None = None
    failure_signals: list[dict[str, Any]] = [
        {"pattern": r"baton-worker: failure=(\w+) code=(\w+)", "class_from": 1},
    ]

    def check_profile(self, profile: WorkerProfile) -> None:
        missing = [k for k in ("tool", "tool_dir", "bin_dir", "entry") if k not in profile.options]
        if missing:
            raise SetupError("configuration.not_a_tool", f"a tool profile is made by the runtime for a tool step; this one lacks {', '.join(missing)}", "configuration")

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str) -> list[str] | None:
        self.check_profile(profile)
        o = profile.options
        argv = [sys.executable, "-m", "baton.tool_runner", "--packet", str(packet_dir), "--result", str(result_dir),
                "--tool-dir", str(o["tool_dir"]), "--bin-dir", str(o["bin_dir"]), "--entry", json.dumps(o["entry"])]
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
        return f"tool {profile.options.get('tool')} from the recipe; the runtime runs it and takes in the result."
