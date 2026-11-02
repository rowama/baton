"""The ``manual`` adapter (§6.3): a person does the step and the Director submits the result.

Nothing is started. ``dispatch`` prints where the packet is and where the
result goes; the step stays ``running`` until ``baton submit``. Used for
humans and physical-world work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import WorkerProfile


class ManualAdapter:
    name = "manual"
    needs_executable = False
    #: Cannot change the working tree, so no before/after tree check.
    touches_files = False
    config_home_var: str | None = None
    failure_signals: list[dict[str, Any]] = []

    def check_profile(self, profile: WorkerProfile) -> None:
        return None

    def preflight(self, profile: WorkerProfile, packet_dir: Path) -> list[str]:
        return []

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str) -> list[str] | None:
        return None

    def postprocess(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, proc_result: Any) -> None:
        return None

    def handoff(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path) -> str:
        who = profile.person or "the worker"
        return (
            f"For {who}: read {packet_dir / 'INSTRUCTIONS.md'} and follow it exactly. "
            f"Write artifacts under {result_dir / 'artifacts'}/, then {result_dir / 'result.json'} last."
        )
