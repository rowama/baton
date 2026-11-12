"""Check the commands in the manual's ``baton`` examples against the real CLI (§13.10)."""

from __future__ import annotations

import shlex
from typing import Any



def _group(cli: Any = None) -> Any:
    if cli is not None:
        return cli
    import typer.main

    from . import cli as cli_mod

    return typer.main.get_command(cli_mod.app)


def commands(cli: Any = None) -> set[str]:
    """The top-level command names (a group such as ``workers`` counts once)."""
    return set(_group(cli).commands)


def check_example(block: list[str], cli: Any = None) -> list[str]:
    root = _group(cli)
    problems = []
    for raw in block:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0]
        try:
            words = shlex.split(line)
        except ValueError:
            problems.append(f"cannot read the example line {line!r}")
            continue
        if not words or words[0] != "baton":
            problems.append(f"an example line starts with 'baton': {line!r}")
            continue
        cmd: Any = root
        i = 1
        while i < len(words) and hasattr(cmd, "commands") and not words[i].startswith("-"):
            sub = cmd.commands.get(words[i])
            if sub is None:
                problems.append(f"'baton {' '.join(words[1:i + 1])}' is not a command")
                cmd = None  # type: ignore[assignment]
                break
            cmd, i = sub, i + 1
        if cmd is None:
            continue
        known = {o for p in cmd.params for o in getattr(p, "opts", []) + getattr(p, "secondary_opts", [])} | set(root.params and [o for p in root.params for o in getattr(p, "opts", [])])
        known |= {"--help"}
        for w in words[i:]:
            if w.startswith("--") and w.split("=")[0] not in known:
                problems.append(f"'{w}' is not an option of 'baton {' '.join(words[1:i])}'")
    return problems
