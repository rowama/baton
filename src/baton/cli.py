"""The ``baton`` command line (§13.1). Exit codes: 0 ok, 1 problem, 2 usage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import __version__, engine
from .recipe import RecipeError, render_plan

EXIT_OK, EXIT_PROBLEM, EXIT_USAGE = 0, 1, 2

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Baton process runtime.")


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        Optional[bool], typer.Option("--version", callback=_version, is_eager=True, help="Print the runtime version.")
    ] = None,
) -> None:
    pass


def _emit(payload: dict, as_json: bool, text: str) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(text, nl=False)


@app.command()
def plan(
    recipe: Annotated[Path, typer.Argument(help="Recipe directory (containing recipe.yaml).")],
    level: Annotated[Optional[str], typer.Option(help="Show only this complexity level.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Validate a recipe and print its per-level step and gate table."""
    try:
        result = engine.plan(recipe, level=level)
    except RecipeError as e:
        errors = [i for i in e.issues if i.severity == "error"]
        _emit(
            {"ok": False, "issues": [i.model_dump() for i in e.issues]},
            as_json,
            "".join(f"{i}\n" for i in errors),
        )
        raise typer.Exit(EXIT_PROBLEM)
    except ValueError as e:
        _emit({"ok": False, "error": str(e)}, as_json, f"ERROR: {e}\n")
        raise typer.Exit(EXIT_USAGE)
    if not as_json:
        for w in result.warnings:
            typer.echo(str(w), err=True)
    _emit({"ok": True, "plan": result.model_dump(mode="json")}, as_json, render_plan(result))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
