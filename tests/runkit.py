"""Helpers for driving runs in tests: profiles, a scripted fake worker, small recipes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from baton import engine
from baton.models import WorkerProfile
from baton.packet import BuiltPacket, RunContext
from baton.recipe import load_recipe
from baton.store import Store

WRITER = WorkerProfile(
    adapter="manual",
    vendor="human",
    person="owner",
    capabilities=["structured_output", "long_form_writing", "technical_reasoning", "file_write"],
    tier="strong",
    context_tokens=200000,
)


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


def write_result(
    packet: BuiltPacket,
    output: Any = None,
    *,
    status: str = "completed",
    artifacts: dict[str, tuple[str, bytes]] | None = None,
    **overrides: Any,
) -> dict:
    """Play the worker: write artifacts, then result.json (last), echoing the packet hash."""
    listed = []
    for name, (filename, content) in (artifacts or {}).items():
        p = packet.result_dir / "artifacts" / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        listed.append({"name": name, "path": f"artifacts/{filename}"})
    result = {
        "protocol": "baton-packet/1",
        "packet_sha256": packet.sha256,
        "status": status,
        "output": output,
        "artifacts": listed,
        "notes": "",
        "questions_for_human": [],
        "process_feedback": [],
    }
    result.update(overrides)
    (packet.result_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return result


PROFILE_OUT = {
    "summary": "Vendor contract review",
    "scope": {"kind": "executing_a_process", "statement": "Review each vendor contract before signing."},
    "work": {
        "frequency": "a few per month",
        "judgment": "high",
        "dependent_reasoning": "high",
        "handoffs": True,
        "duration": "two days",
        "participants": ["legal agent", "owner"],
        "human_signoffs": True,
        "record_value": "benefit",
        "latency_sensitive": False,
        "live_integration": False,
        "bulk_processing": False,
    },
}
VERDICT_OUT = {
    "verdict": "fits", "assessed_work": "Reviewing vendor contracts",
    "reasons": [{"row": "recurrence", "leans": "baton", "basis": "stated", "reason": "a few per month"}],
    "next_step": "Author a contract-review recipe.",
}
FIT_INPUTS = {"title": "Contract review", "idea": "Review each vendor contract before signing."}


def start(store: Store, recipe_dir: Path, inputs: dict | None = None, **kw: Any) -> RunContext:
    return engine.start(store, load_recipe(recipe_dir), FIT_INPUTS if inputs is None else inputs, run_id="r_20261101_ab12", **kw)


def make_recipe(root: Path, steps: list[dict], *, schemas: dict[str, dict] | None = None, run_inputs: dict | None = None, **top: Any) -> Path:
    """Write a minimal recipe package: every step's prompt and schema files are created."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "schemas").mkdir(exist_ok=True)
    for name, schema in (schemas or {}).items():
        (root / "schemas" / name).write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}), encoding="utf-8")
    doc: dict[str, Any] = {"id": "toy", "version": 1, "format": "baton-recipe/1", "capabilities_vocab": "baton-capabilities/1", **top}
    if run_inputs is not None:
        (root / "schemas" / "run_inputs.json").write_text(
            json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **run_inputs}), encoding="utf-8"
        )
        doc["run_inputs"] = {"schema": "schemas/run_inputs.json"}
    for s in steps:
        s.setdefault("requires", {"capabilities": ["structured_output"]})
        s.setdefault("prompt", f"prompts/{s['id']}.md")
        (root / s["prompt"]).write_text(f"Do the {s['id']} step.\n", encoding="utf-8")
    doc["steps"] = steps
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


OBJ = {"type": "object"}


def artifact_recipe(root: Path, **draft: Any) -> Path:
    """draft (artifact `doc`, required) -> use (consumes steps.draft.artifacts.doc)."""
    return make_recipe(
        root,
        [
            {
                "id": "draft",
                "output_schema": "schemas/out.json",
                "artifacts": [{"name": "doc", "required": True, "media_type": "text/markdown"}, {"name": "extra", "required": False}],
                "gates": [{"type": "schema"}],
                **draft,
            },
            {
                "id": "use",
                "depends_on": ["draft"],
                "output_schema": "schemas/out.json",
                "inputs": [{"name": "doc", "from": "steps.draft.artifacts.doc", "required": True}],
            },
        ],
        schemas={"out.json": OBJ},
    )
