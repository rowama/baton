"""The ``litellm_api`` adapter (§6.3): an API model, called from a child process.

The child is ``python -m baton.worker_runner`` under the profile's constructed
environment (``clean`` by default: only the resolved API key, a minimal PATH
and the ``BATON_*`` directories). The runner calls the model through
``litellm``, then writes artifacts and ``result.json`` itself. ``options`` in
the profile are passed to ``litellm.completion`` as keyword arguments (e.g.
``base_url``, ``temperature``); they are non-secret by rule (§6.1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..models import WorkerProfile
from ..profiles import SetupError


class LitellmApiAdapter:
    name = "litellm_api"
    #: Starts the runtime's own interpreter: no executable to resolve.
    needs_executable = False
    #: Cannot change the working tree, so no before/after tree check.
    touches_files = False
    config_home_var: str | None = None
    failure_signals: list[dict[str, Any]] = [
        {"pattern": r"baton-worker: failure=(\w+) code=(\w+)", "class_from": 1},
    ]

    def check_profile(self, profile: WorkerProfile) -> None:
        if not profile.model:
            raise SetupError("configuration.no_model", "a litellm_api profile needs `model` (e.g. \"<provider>/<model>\")", "configuration")

    def base_argv(self, profile: WorkerProfile) -> list[str]:
        argv = [sys.executable, "-m", "baton.worker_runner", "--model", str(profile.model)]
        if profile.options:
            argv += ["--options", json.dumps(profile.options, sort_keys=True)]
        if profile.context_tokens:
            argv += ["--context-tokens", str(profile.context_tokens)]
        return argv

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str) -> list[str] | None:
        self.check_profile(profile)
        return self.base_argv(profile) + ["--packet", str(packet_dir), "--result", str(result_dir)]

    def noop_command(self, profile: WorkerProfile) -> list[str]:
        self.check_profile(profile)
        return self.base_argv(profile) + ["--noop"]

    def preflight(self, profile: WorkerProfile, packet_dir: Path) -> list[str]:
        """Problems that make this packet impossible for this worker (§18 #1: inputs too large)."""
        from ..worker_runner import InputError, build_messages

        try:
            build_messages(packet_dir, profile.context_tokens)
        except InputError as e:
            return [str(e)]
        return []

    def postprocess(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, proc_result: Any) -> None:
        return None

    def handoff(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path) -> str:
        return f"API model {profile.model} via litellm; the runtime runs it and takes in the result."
