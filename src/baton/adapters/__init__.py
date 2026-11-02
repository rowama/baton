"""Worker adapters (§6.3). Adapters start workers; they never interpret results (intake does)."""

from __future__ import annotations

from ..packet import EngineError
from .base import WorkerAdapter
from .harness import ClaudeCodeAdapter, CodexAdapter, CommandAdapter
from .litellm_api import LitellmApiAdapter
from .manual import ManualAdapter

#: Adapters this runtime can run.
ADAPTERS: dict[str, WorkerAdapter] = {
    "manual": ManualAdapter(),
    "litellm_api": LitellmApiAdapter(),
    "claude_code": ClaudeCodeAdapter(),
    "codex": CodexAdapter(),
    "command": CommandAdapter(),
}


def get(name: str) -> WorkerAdapter:
    try:
        return ADAPTERS[name]
    except KeyError:
        raise EngineError(
            "adapter.unsupported", f"adapter {name!r} is not available in this runtime (available: {', '.join(sorted(ADAPTERS))})"
        ) from None


__all__ = ["ADAPTERS", "WorkerAdapter", "get"]
