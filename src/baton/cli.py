"""The ``baton`` command line (§13.1).

Every command takes ``--json`` for machine-readable output. Exit codes:
0 ok, 1 problem, 2 usage, 3 lease held elsewhere, 4 needs an owner decision.

Global options (or environment): ``--project`` / ``BATON_PROJECT`` (default:
the nearest directory with ``.baton/project.yaml``), ``--director`` /
``BATON_DIRECTOR`` (the identity leases are held under; default
``<user>@<host>``). Machine-local files are read from ``BATON_HOME``
(default ``~/.baton``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import typer

from . import __version__, engine
from .locks import LeaseHeld
from .packet import EngineError, HandoffError
from .recipe import RecipeError, render_plan
from .store import StoreError

EXIT_OK, EXIT_PROBLEM, EXIT_USAGE, EXIT_LEASE, EXIT_OWNER = 0, 1, 2, 3, 4

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Baton process runtime.")

JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]


class _Opts:
    project: Optional[Path] = None
    director: Optional[str] = None


_opts = _Opts()


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        Optional[bool], typer.Option("--version", callback=_version, is_eager=True, help="Print the runtime version.")
    ] = None,
    project: Annotated[Optional[Path], typer.Option("--project", envvar="BATON_PROJECT", help="Project root.")] = None,
    director: Annotated[Optional[str], typer.Option("--director", envvar="BATON_DIRECTOR", help="Director identity for leases.")] = None,
) -> None:
    _opts.project = project
    _opts.director = director


# ---------------------------------------------------------------------------
# Output and errors
# ---------------------------------------------------------------------------


def _emit(payload: dict, as_json: bool, text: str) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    elif text:
        typer.echo(text, nl=not text.endswith("\n"))


def _fail(as_json: bool, code: int, error: str, message: str, **extra: Any) -> None:
    _emit({"ok": False, "error": error, "message": message, **extra}, as_json, "")
    if not as_json:
        typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(code)


def _api() -> engine.Api:
    return engine.Api.open(_opts.project, director_id=_opts.director)


def _call(as_json: bool, fn: Callable[[], Any]) -> Any:
    """Run an API call, mapping refusals to exit codes."""
    try:
        return fn()
    except LeaseHeld as e:
        extra = {"lease": e.lease.__dict__}
        if getattr(e, "status", None):
            extra["status"] = e.status  # type: ignore[attr-defined]
        _fail(as_json, EXIT_LEASE, e.code, str(e), **extra)
    except engine.IntegrityError as e:
        if not as_json:
            for i in e.issues:
                typer.echo(f"ERROR {i.where}: {i.message}", err=True)
        _fail(as_json, EXIT_PROBLEM, e.code, str(e), issues=[i.model_dump() for i in e.issues])
    except HandoffError as e:
        missing = [{"name": n, "from": r, "reason": why} for n, r, why in e.missing]
        _fail(as_json, EXIT_PROBLEM, "handoff.missing_inputs", str(e), missing=missing)
    except EngineError as e:
        _fail(as_json, EXIT_PROBLEM, e.code, str(e))
    except RecipeError as e:
        _fail(as_json, EXIT_PROBLEM, "recipe.invalid", str(e), issues=[i.model_dump() for i in e.issues])
    except StoreError as e:
        _fail(as_json, EXIT_PROBLEM, "store.error", str(e), issues=[i.model_dump() for i in e.issues])


def _checkpoint_note(payload: dict) -> None:
    cp = payload.get("checkpoint")
    if cp and not cp["committed"] and cp["reason"] not in ("nothing to commit", "checkpoint commits are off in project.yaml"):
        typer.echo(f"WARNING: checkpoint not committed: {cp['reason']}", err=True)


def _pending_lines(payload: dict) -> list[str]:
    lines = []
    for p in payload.get("pending_decisions") or []:
        if p["kind"] == "gate":
            lines.append(f"Owner decision owed on {p['ref']} (attempt {p['attempt']}): {p['prompt']}  [{' | '.join(p['options'])}]")
        else:
            why = "; ".join(p.get("reasons") or p.get("questions") or []) or p.get("reason") or ""
            lines.append(f"Escalated {p['ref']} ({p.get('reason')}): {why}  [{' | '.join(p['options'])}]")
    return lines


def _done(payload: dict, as_json: bool, text: str, code: int | None = None) -> None:
    _emit({"ok": True, **payload}, as_json, text)
    if not as_json:
        _checkpoint_note(payload)
    if code is None:
        code = EXIT_OWNER if payload.get("needs_owner") else EXIT_OK
    raise typer.Exit(code)


# ---------------------------------------------------------------------------
# Setup and recipes
# ---------------------------------------------------------------------------


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Project root (default: current directory).")] = Path("."),
    as_json: JsonOpt = False,
) -> None:
    """Create .baton/ with defaults in a project. Existing files are kept."""
    out = _call(as_json, lambda: engine.Api.init(path))
    lines = [f"Initialized Baton in {out['root']}"] + [f"  created {c}" for c in out["created"]] + [f"  note: {n}" for n in out["notes"]]
    _done(out, as_json, "\n".join(lines))


@app.command()
def vendor(recipe_dir: Annotated[Path, typer.Argument(help="Recipe package directory.")], as_json: JsonOpt = False) -> None:
    """Vendor a recipe into .baton/recipes/ and pin it in baton.lock."""
    out = _call(as_json, lambda: _api().vendor(recipe_dir))
    text = f"Vendored {out['recipe']} ({out['sha256'][:12]})" if out["changed"] else f"{out['recipe']} is already vendored"
    _done(out, as_json, text)


@app.command()
def recipes(as_json: JsonOpt = False) -> None:
    """List vendored recipes."""
    out = _call(as_json, lambda: _api().recipes())
    lines = [f"{r['recipe']}  {r.get('description') or ''}" if r["ok"] else f"{r['recipe']}  ERROR: {r['error']}" for r in out["recipes"]]
    _done(out, as_json, "\n".join(lines) or "No recipes vendored.", EXIT_OK if all(r["ok"] for r in out["recipes"]) else EXIT_PROBLEM)


@app.command()
def plan(
    recipe: Annotated[str, typer.Argument(help="Recipe directory, or a vendored recipe (id or id@version).")],
    level: Annotated[Optional[str], typer.Option(help="Show only this complexity level.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Validate a recipe and print its per-level step and gate table."""
    try:
        result = engine.plan(recipe, level=level) if Path(recipe).is_dir() else _api().plan(recipe, level=level)
    except RecipeError as e:
        errors = [i for i in e.issues if i.severity == "error"]
        _emit({"ok": False, "issues": [i.model_dump() for i in e.issues]}, as_json, "".join(f"{i}\n" for i in errors))
        raise typer.Exit(EXIT_PROBLEM)
    except EngineError as e:
        _fail(as_json, EXIT_PROBLEM, e.code, str(e))
    except ValueError as e:
        _emit({"ok": False, "error": str(e)}, as_json, f"ERROR: {e}\n")
        raise typer.Exit(EXIT_USAGE)
    if not as_json:
        for w in result.warnings:
            typer.echo(str(w), err=True)
    _emit({"ok": True, "plan": result.model_dump(mode="json")}, as_json, render_plan(result))


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _parse_inputs(raw: str, as_json: bool) -> dict:
    try:
        text = Path(raw[1:]).read_text(encoding="utf-8-sig") if raw.startswith("@") else raw
        value = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        _fail(as_json, EXIT_USAGE, "usage.inputs", f"--inputs must be JSON or @file.json: {e}")
    if not isinstance(value, dict):
        _fail(as_json, EXIT_USAGE, "usage.inputs", "--inputs must be a JSON object")
    return value


def _status_text(s: dict) -> str:
    bits = [f"{s['run_id']} {s['recipe']} {s['state']}"]
    if s["ready"]:
        bits.append("ready: " + ", ".join(s["ready"]))
    if s["running"]:
        bits.append("running: " + ", ".join(f"{r['step_path']}#{r['attempt']} ({r['profile']})" for r in s["running"]))
    lease = s.get("lease")
    if lease and s["state"] == "active":
        who = "you" if lease["yours"] else lease["director_id"]
        bits.append(f"lease: {who} until {lease['expires_at']}" + (" (expired)" if lease["expired"] else ""))
    lines = [" · ".join(bits)]
    for r in s["running"]:
        lines.append(f"  {r['step_path']}#{r['attempt']}: packet {r['packet']}; result goes in {r['result']}")
    lines += _pending_lines(s)
    return "\n".join(lines)


@app.command()
def start(
    recipe: Annotated[str, typer.Argument(help="Vendored recipe (id or id@version).")],
    inputs: Annotated[str, typer.Option("--inputs", help="Run inputs: a JSON object, or @file.json.")] = "{}",
    title: Annotated[Optional[str], typer.Option(help="Work item title (default: inputs.title).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Start a run (a work item) and claim its lease."""
    values = _parse_inputs(inputs, as_json)
    out = _call(as_json, lambda: _api().start(recipe, values, title=title))
    _done(out, as_json, f"Started {out['run_id']}\n" + _status_text(out))


@app.command()
def status(run: Annotated[str, typer.Argument(help="Run id.")], as_json: JsonOpt = False) -> None:
    """Where a run is: ready and running steps, owner decisions owed, lease."""
    out = _call(as_json, lambda: _api().status(run))
    _done(out, as_json, _status_text(out))


@app.command()
def dispatch(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path.")],
    worker: Annotated[str, typer.Option("--worker", help="Worker profile name.")],
    as_json: JsonOpt = False,
) -> None:
    """Build the step's packet and hand it to the worker."""
    out = _call(as_json, lambda: _api().dispatch(run, step, worker))
    text = (
        f"Dispatched {out['step_path']} attempt {out['attempt']} to {out['worker']} ({out['adapter']}) [{out['dispatch_id']}]\n"
        f"{out['handoff']}\nThen: baton submit {out['run_id']} {out['step_path']}"
    )
    _done(out, as_json, text)


@app.command()
def retry(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path.")],
    worker: Annotated[Optional[str], typer.Option("--worker", help="Worker profile (default: the previous attempt's).")] = None,
    guidance: Annotated[Optional[str], typer.Option("--guidance", help="Additive guidance for the new attempt.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Start a new attempt of a step whose previous attempt was not accepted."""
    out = _call(as_json, lambda: _api().retry(run, step, worker, guidance))
    text = (
        f"Dispatched {out['step_path']} attempt {out['attempt']} to {out['worker']} ({out['adapter']}) [{out['dispatch_id']}]\n"
        f"{out['handoff']}\nThen: baton submit {out['run_id']} {out['step_path']}"
    )
    _done(out, as_json, text)


def _outcome_text(out: dict) -> str:
    o = out["outcome"]
    head = {
        "passed": f"{out['step_path']} passed (attempt {out['attempt']})",
        "needs_human": f"{out['step_path']} is waiting for the owner",
        "retry": f"{out['step_path']} attempt {out['attempt']} was not accepted; the step is ready for another attempt",
        "escalated": f"{out['step_path']} escalated",
        "abandoned": f"{out['step_path']} abandoned",
    }[o]
    lines = [head] + [f"  - {r.splitlines()[0]}" for r in out["reasons"] if o != "needs_human"]
    if out["ready"]:
        lines.append("Ready: " + ", ".join(out["ready"]))
    if out["run_completed"]:
        lines.append(f"Run {out['run_id']} completed.")
    lines += _pending_lines(out)
    return "\n".join(lines)


@app.command()
def submit(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path.")],
    result: Annotated[Optional[Path], typer.Option("--result", help="Result directory to copy in (default: the attempt's result/).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Hand in a manual or external worker's result: intake and gates run now."""
    out = _call(as_json, lambda: _api().submit(run, step, result))
    code = EXIT_PROBLEM if out["outcome"] == "retry" and not out["needs_owner"] else None
    _done(out, as_json, _outcome_text(out), code)


@app.command()
def decide(
    run: Annotated[str, typer.Argument(help="Run id.")],
    ref: Annotated[str, typer.Argument(help="What is being decided: the step path awaiting the owner.")],
    decision: Annotated[str, typer.Argument(help="approve | reject (gates); retry | abandon (escalations).")],
    note: Annotated[str, typer.Option("--note", help="The owner's words, recorded verbatim.")] = "",
    as_json: JsonOpt = False,
) -> None:
    """Record the owner's decision, verbatim."""
    out = _call(as_json, lambda: _api().decide(run, ref, decision, note))
    _done(out, as_json, _outcome_text(out))


@app.command()
def abandon(
    run: Annotated[str, typer.Argument(help="Run id.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the work item is abandoned.")],
    as_json: JsonOpt = False,
) -> None:
    """Abandon a run."""
    out = _call(as_json, lambda: _api().abandon(run, reason))
    _done(out, as_json, f"Run {run} abandoned.")


# ---------------------------------------------------------------------------
# Continuity
# ---------------------------------------------------------------------------


@app.command()
def resume(run: Annotated[str, typer.Argument(help="Run id.")], as_json: JsonOpt = False) -> None:
    """Verify a run, rebuild its cache, reconcile in-flight work and claim its lease."""
    out = _call(as_json, lambda: _api().resume(run))
    _done(out, as_json, _status_text(out))


@app.command()
def lease(
    run: Annotated[str, typer.Argument(help="Run id.")],
    action: Annotated[str, typer.Argument(help="claim | release | take-over")],
    reason: Annotated[Optional[str], typer.Option("--reason", help="Why (required for take-over).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Claim, release or take over a run's lease. Take over only with the owner's approval."""
    act = action.replace("-", "_")
    if act not in ("claim", "release", "take_over"):
        _fail(as_json, EXIT_USAGE, "usage.lease", "action must be claim, release or take-over")
    out = _call(as_json, lambda: _api().lease(run, act, reason))
    lease_info = out["lease"]
    text = f"Lease on {run}: " + (f"{lease_info['director_id']} until {lease_info['expires_at']}" if lease_info else "free")
    _done(out, as_json, text, EXIT_OK)


# ---------------------------------------------------------------------------
# Records and checks
# ---------------------------------------------------------------------------


@app.command()
def record(run: Annotated[str, typer.Argument(help="Run id.")], step: Annotated[str, typer.Argument(help="Step path.")], as_json: JsonOpt = False) -> None:
    """Print a step's record."""
    text = _call(as_json, lambda: _api().record(run, step))
    _done({"record": text}, as_json, text, EXIT_OK)


@app.command()
def summary(run: Annotated[str, typer.Argument(help="Run id.")], as_json: JsonOpt = False) -> None:
    """Print the run summary."""
    text = _call(as_json, lambda: _api().summary(run))
    _done({"summary": text}, as_json, text, EXIT_OK)


@app.command()
def trace(
    run: Annotated[str, typer.Argument(help="Run id.")],
    limit: Annotated[int, typer.Option(help="Show the last N events (0: all).")] = 20,
    as_json: JsonOpt = False,
) -> None:
    """Print the run's recent events, one line each."""
    lines = _call(as_json, lambda: _api().trace(run, limit or None))
    _done({"events": lines}, as_json, "\n".join(lines), EXIT_OK)


@app.command()
def check(as_json: JsonOpt = False) -> None:
    """Repository consistency for pre-commit and CI: one ERROR line per problem, exit 0 when clean."""
    from .check import check as run_check
    from .project import find_root

    root = _call(as_json, lambda: find_root(_opts.project))
    issues = run_check(root)
    errors = [i for i in issues if i.severity == "error"]
    if as_json:
        _emit({"ok": not errors, "issues": [i.model_dump() for i in issues]}, True, "")
    else:
        for i in issues:
            typer.echo(f"{'ERROR' if i.severity == 'error' else 'WARNING'} {i.where}: {i.message}")
    raise typer.Exit(EXIT_PROBLEM if errors else EXIT_OK)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
