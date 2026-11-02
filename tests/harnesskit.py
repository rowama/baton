"""Helpers for harness-adapter tests: install the fake ``claude`` / ``codex`` CLIs and write their profiles."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

FAKE = Path(__file__).resolve().parent / "fakes" / "fake_harness.py"


def install_fake(bin_dir: Path, name: str, outputs: dict | None = None) -> Path:
    """An executable ``bin_dir/<name>`` running the fake under this interpreter."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / name
    exe.write_text(f"#!{sys.executable}\n" + FAKE.read_text(encoding="utf-8"), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    set_outputs(bin_dir, outputs or {})
    return exe


def set_outputs(bin_dir: Path, outputs: dict) -> None:
    (bin_dir / "outputs.json").write_text(json.dumps(outputs), encoding="utf-8")


def calls(bin_dir: Path) -> list[dict]:
    f = bin_dir / "calls.jsonl"
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def nvm_dir(home: Path) -> Path:
    """A fake nvm layout (``$NVM_DIR/versions/node/<v>/bin``) under ``home``."""
    return home / ".nvm" / "versions" / "node" / "v22.1.0" / "bin"


def harness_profile(
    name: str, adapter: str, vendor: str, *, executable: str, capabilities: list[str], auth: str = "{ mode: cli_login }", **extra: object
) -> str:
    lines = [
        f"{name}:",
        f"  adapter: {adapter}",
        f"  vendor: {vendor}",
        f"  executable: {executable}",
        f"  capabilities: {json.dumps(capabilities)}",
        "  tier: strong",
        "  context_tokens: 200000",
        f"  auth: {auth}",
    ]
    lines += [f"  {k}: {json.dumps(v)}" for k, v in extra.items()]
    return "\n".join(lines) + "\n"


def env_without(*names: str) -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in names}
