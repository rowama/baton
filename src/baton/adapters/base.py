"""The adapter protocol (§6.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..models import WorkerProfile


class WorkerAdapter(Protocol):
    name: str
    #: Patterns for failure classification (§8.8, Phase 7).
    failure_signals: list[dict[str, Any]]

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str) -> list[str] | None:
        """The child process to start, or None when no process runs (a person does the work)."""
        ...

    def postprocess(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, proc_result: Any) -> None: ...

    def handoff(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path) -> str:
        """What to tell whoever does the work, printed by ``dispatch``."""
        ...
