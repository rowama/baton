"""Worker adapters (§6.3). Adapters start workers; they never interpret results (intake does)."""

from __future__ import annotations

from ..packet import EngineError
from .base import WorkerAdapter
from .manual import ManualAdapter

#: Adapters this runtime can run. API and harness adapters arrive with Phases 5 and 6.
ADAPTERS: dict[str, WorkerAdapter] = {"manual": ManualAdapter()}


def get(name: str) -> WorkerAdapter:
    try:
        return ADAPTERS[name]
    except KeyError:
        raise EngineError(
            "adapter.unsupported", f"adapter {name!r} is not available in this runtime (available: {', '.join(sorted(ADAPTERS))})"
        ) from None


__all__ = ["ADAPTERS", "WorkerAdapter", "get"]
