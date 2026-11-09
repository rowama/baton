"""The ``baton`` command line (§13.1).

Every command takes ``--json`` for machine-readable output. Exit codes
(§13.1): 0 ok, 1 problem, 2 usage, 3 lease held elsewhere, 4 finished and the
owner is needed now (a success path, not a failure). ``BATON_OWNER_EXIT=0``
makes that case exit 0 instead, ``needs_owner: true`` still in the JSON, for
harnesses that treat any non-zero exit as failure (decision 0057).

Global options (or environment): ``--project`` / ``BATON_PROJECT`` (default:
the nearest directory with ``.baton/project.yaml``), ``--director`` /
``BATON_DIRECTOR`` (the identity leases are held under; default
``<user>@<host>``). Machine-local files are read from ``BATON_HOME``
(default ``~/.baton``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import typer

from . import __version__, engine
from .locks import LeaseHeld
from .packet import EngineError, HandoffError
from .recipe import RecipeError, render_plan
from .store import StoreError

EXIT_OK, EXIT_PROBLEM, EXIT_USAGE, EXIT_LEASE, EXIT_OWNER = 0, 1, 2, 3, 4
OWNER_EXIT_VAR = "BATON_OWNER_EXIT"

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Baton process runtime.")

JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]
WaitOpt = Annotated[bool, typer.Option("--wait", help="Block until the worker finishes and its result is recorded.")]


class _Opts:
    project: Optional[Path] = None
    director: Optional[str] = None


_opts = _Opts()


def _route(e: dict) -> str:
    """``adapter, creator[, model_id][ via provider]`` for an eligibility line (§8.4)."""
    out = f"{e['adapter']}, {e.get('creator', e.get('vendor'))}"
    if e.get("model_id"):
        out += f", {e['model_id']}"
    if e.get("provider"):
        out += f" via {e['provider']}"
    return out


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


def error_payload(e: BaseException) -> tuple[int, dict[str, Any]] | None:
    """(exit code, error payload) for a refusal any interface reports the same way; None for a bug."""
    if isinstance(e, LeaseHeld):
        extra: dict[str, Any] = {"lease": e.lease.__dict__}
        if getattr(e, "status", None):
            extra["status"] = e.status  # type: ignore[attr-defined]
        return EXIT_LEASE, {"error": e.code, "message": str(e), **extra}
    if isinstance(e, engine.IntegrityError):
        return EXIT_PROBLEM, {"error": e.code, "message": str(e), "issues": [i.model_dump() for i in e.issues]}
    if isinstance(e, HandoffError):
        missing = [{"name": n, "from": r, "reason": why} for n, r, why in e.missing]
        return EXIT_PROBLEM, {"error": "handoff.missing_inputs", "message": str(e), "missing": missing}
    if isinstance(e, EngineError):
        return EXIT_PROBLEM, {"error": e.code, "message": str(e)}
    if isinstance(e, RecipeError):
        return EXIT_PROBLEM, {"error": "recipe.invalid", "message": str(e), "issues": [i.model_dump() for i in e.issues]}
    if isinstance(e, StoreError):
        return EXIT_PROBLEM, {"error": "store.error", "message": str(e), "issues": [i.model_dump() for i in e.issues]}
    return None


def _owner_exit() -> int:
    """The exit code for "finished, the owner is needed": 4, or 0 under ``BATON_OWNER_EXIT=0`` (decision 0057)."""
    raw = os.environ.get(OWNER_EXIT_VAR, "").strip()
    if raw in ("", "4"):
        return EXIT_OWNER
    if raw == "0":
        return EXIT_OK
    raise ValueError(f"{OWNER_EXIT_VAR} must be 0 or 4, got {raw!r}")


def _call(as_json: bool, fn: Callable[[], Any]) -> Any:
    """Run an API call, mapping refusals to exit codes. A bad ``BATON_OWNER_EXIT`` is refused before any work."""
    try:
        _owner_exit()
    except ValueError as e:
        _fail(as_json, EXIT_USAGE, "usage.owner_exit", str(e))
    try:
        return fn()
    except (LeaseHeld, EngineError, RecipeError, StoreError) as e:
        mapped = error_payload(e)
        assert mapped is not None
        code, payload = mapped
        if not as_json and isinstance(e, engine.IntegrityError):
            for i in e.issues:
                typer.echo(f"ERROR {i.where}: {i.message}", err=True)
        _fail(as_json, code, payload.pop("error"), payload.pop("message"), **payload)


def _checkpoint_note(payload: dict) -> None:
    cp = payload.get("checkpoint")
    if cp and not cp["committed"] and cp["reason"] not in ("nothing to commit", "checkpoint commits are off in project.yaml"):
        typer.echo(f"WARNING: checkpoint not committed: {cp['reason']}", err=True)


def _read_answers(p: Path, as_json: bool) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        _fail(as_json, EXIT_USAGE, "answers.unreadable", f"cannot read answers file {p}: {e}")


def _names(opts: list) -> list[str]:
    return [o.get("command") or o["decision"] if isinstance(o, dict) else str(o) for o in opts]


def _pending_lines(payload: dict) -> list[str]:
    lines = []
    for p in payload.get("pending_decisions") or []:
        if p["kind"] == "gate":
            lines.append(f"Owner decision owed on {p['ref']} (attempt {p['attempt']}): {p['prompt']}  [{' | '.join(_names(p['options']))}]")
        elif p["kind"] == "baseline":
            lines.append(f"Owner decision owed: {p['prompt']}  [{p['options'][0].get('command') or p['options'][0]['decision']}]")
        elif p["kind"] == "skip_notice":
            lines.append(f"Owner notice {p['ref']}: {p['prompt']}  [acknowledge]")
        elif p["kind"] in ("publish_conflict", "drift"):
            lines.append(f"Owner decision owed on {p['ref']}: {p['prompt']}  [{' | '.join(_names(p['options']))}]")
        else:
            why = "; ".join(p.get("reasons") or [f"{q['id']}: {q['ask']}" for q in p.get("questions") or []]) or p.get("reason") or ""
            inc = f" (waits on platform incident {p['incident']})" if p.get("incident") else ""
            lines.append(f"Escalated {p['ref']} ({p.get('reason')}){inc}: {why}  [{' | '.join(_names(p['options']))}]")
    return lines


def _done(payload: dict, as_json: bool, text: str, code: int | None = None) -> None:
    _emit({"ok": True, **payload}, as_json, text)
    if not as_json:
        _checkpoint_note(payload)
    if code is None:
        try:
            code = _owner_exit() if payload.get("needs_owner") else EXIT_OK
        except ValueError:  # expected: the comment says it: a command without an owner-exit option keeps the default (_call refused it before any work; a command without one keeps the default)
            code = EXIT_OWNER
    raise typer.Exit(code)


# ---------------------------------------------------------------------------
# Setup and recipes
# ---------------------------------------------------------------------------


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Project root (default: current directory).")] = Path("."),
    bare: Annotated[bool, typer.Option("--bare", help="Vendor no starter recipes (fit-check is vendored by default).")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Create .baton/ with defaults in a project (and the starter recipes, unless --bare). Existing files are kept."""
    out = _call(as_json, lambda: engine.Api.init(path, bare=bare))
    lines = [f"Initialized Baton in {out['root']}"] + [f"  created {c}" for c in out["created"]] + [f"  note: {n}" for n in out["notes"]]
    _done(out, as_json, "\n".join(lines))


@app.command()
def detect(as_json: JsonOpt = False) -> None:
    """The project's situation, each active run's situation and machine readiness. One line when healthy."""
    from .adopt import detect as run_detect

    out = _call(as_json, lambda: run_detect(_opts.project, director=_director()))
    lines = [out["line"]] if out["ok"] else [f"PROBLEM {p}" for p in out["problems"]]
    lines += _blocking_lines(out)
    lines += [f"WARNING {w}" for w in out["warnings"]]
    _emit(out, as_json, "\n".join(lines))
    raise typer.Exit(EXIT_OK if out["ok"] else EXIT_PROBLEM)


def _blocking_lines(out: dict) -> list[str]:
    """A blocking problem's owner message and options (material for the Director, §13.8)."""
    b = out.get("blocking")
    if not b:
        return []
    return ["", b["message"], "", "Options: " + " | ".join(o["label"] for o in b["options"])]


def _director() -> Any:
    from .locks import Director

    return Director.current(_opts.director)


def _adoption_text(out: dict) -> str:
    lines = [f"Adoption {out['adoption']} of {out['recipe']}" + (f" (crosswalk {out['crosswalk']})" if out.get("crosswalk") else "") + f": {out['state']}"]
    lines.append(f"  research: {out['research']}")
    for key, r in out["runs"].items():
        lines.append(f"  {key}: run {r['run_id']} ({r['title']}), triage {r['triage'] or '-'}")
    for g in out.get("gaps") or []:
        lines.append(f"  gap: {g}")
    if out.get("baseline"):
        lines.append(f"  baseline proposal: {out['baseline']}")
    lines.append(f"Next: {out['next']}")
    return "\n".join(lines)


@app.command()
def adopt(
    recipe: Annotated[str, typer.Argument(help="Recipe ref (vendored) or recipe directory (vendored first).")],
    crosswalk: Annotated[Optional[str], typer.Option("--crosswalk", help="A crosswalk shipped with the recipe (by name) or a crosswalk file.")] = None,
    scope: Annotated[Optional[list[str]], typer.Option("--scope", help="Limit research to this path (repeatable).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Adopt this project: start the adoption run (research, then triage per work item, then one baseline decision), or show its progress."""
    from .project import find_root

    root = _opts.project or Path.cwd()
    try:
        find_root(root)
    except EngineError:
        engine.Api.init(root, agents_md=False)  # adoption starts with init when .baton/ is missing (§11.1); the baseline proposes AGENTS.md
    out = _call(as_json, lambda: _api().adopt(recipe, crosswalk=crosswalk, scope=scope or None))
    _done(out, as_json, _adoption_text(out))


def _frame_text(out: dict) -> str:
    lines = [f"Framing {out['framing']}: {out['state']}" + (" (started)" if out.get("started") else "")]
    if out.get("goal"):
        lines.append(f"  goal: {out['goal']}")
    for p in out.get("parts") or []:
        prop = p.get("proposal") or {}
        how = prop.get("recipe") or ("fit-check" if "fit_check" in prop else "?")
        lines.append(f"  part {p['id']}: {p['label']} [{p['kind']}; {how}]")
    for r in out.get("runs") or []:
        lines.append(f"  started {r['run']} ({r['recipe']}) for {r['part']}")
    for g in out.get("gaps") or []:
        lines.append(f"  gap {g['part']}: {g['reason']}")
    lines.append(f"  next: {out['next']}")
    return "\n".join(lines)


@app.command()
def frame(
    note: Annotated[Optional[str], typer.Option("--note", help="The owner's goal, in their own words (recorded verbatim).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Frame a goal into pieces of work the owner chooses from: start the framing run, or show the one awaiting its decision."""
    out = _call(as_json, lambda: _api().frame(note or ""))
    _done(out, as_json, _frame_text(out))


@app.command("establish-baseline")
def establish_baseline(
    adoption: Annotated[str, typer.Argument(help="The adoption run id.")],
    note: Annotated[str, typer.Option("--note", help="The owner's decision, in their words (recorded verbatim).")],
    as_json: JsonOpt = False,
) -> None:
    """Apply the reviewed baseline: the owner's one adoption decision."""
    out = _call(as_json, lambda: _api().establish_baseline(adoption, note))
    lines = [f"Baseline of {adoption} established ({out['decision_id']})."]
    for key, r in out["runs"].items():
        lines.append(f"  {key}: run {r['run_id']} {r['state']}" + (f"; ready: {', '.join(r['ready'])}" if r["ready"] else ""))
    _done(out, as_json, "\n".join(lines))


def _flag_text(f: dict) -> str:
    if f["code"] == "signature_changed":
        return f"step id {f['step']!r} keeps its id but changes {', '.join(f['changed'])} (vs version {', '.join(map(str, f['versions']))})"
    return f"step id {f['step']!r} was retired in version {', '.join(map(str, f['retired_in']))} and is reused"


@app.command()
def vendor(
    recipe_dir: Annotated[Path, typer.Argument(help="Recipe package directory.")],
    approved: Annotated[bool, typer.Option("--approved", help="The owner approved the flagged step-id changes.")] = False,
    note: Annotated[Optional[str], typer.Option("--note", help="With --approved: the owner's words, recorded verbatim.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Vendor a recipe into .baton/recipes/ and pin it in baton.lock (changed or reused step ids need the owner: exit 4)."""
    out = _call(as_json, lambda: _api().vendor(recipe_dir, approved=approved, note=note))
    if out["needs_owner"]:
        text = "\n".join([out["message"], *(f"  - {_flag_text(f)}" for f in out["flags"])])
    elif out["changed"]:
        text = f"Vendored {out['recipe']} ({out['sha256'][:12]})" + (f"; owner decision {out['decision_id']}" if out.get("decision_id") else "")
    else:
        text = f"{out['recipe']} is already vendored"
    _done(out, as_json, text)


@app.command()
def upgrade(
    to: Annotated[Optional[str], typer.Option("--to", help="Runtime version (default: the launcher's own).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Pin a runtime version in baton.lock and re-vendor the skills; nothing else changes (§14.3)."""
    out = _call(as_json, lambda: _api().upgrade(to))
    if not out["changed"]:
        text = f"Already on Baton {out['runtime']}"
    else:
        replaced = out["skills"]["replaced"] + out["skills"]["created"]
        text = f"Upgraded {out['previous']} -> {out['runtime']}" + (f"; skills re-vendored: {', '.join(replaced)}" if replaced else "")
    if out.get("message"):
        text += f"\nNOTE: {out['message']}"
    _done(out, as_json, text)


@app.command()
def migrate(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be migrated; change nothing.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Bring stored files in formats this runtime no longer reads directly to the current formats (§14.2)."""
    out = _call(as_json, lambda: _api().migrate(dry_run=dry_run))
    if not out["items"]:
        text = out.get("message", "nothing to migrate")
    else:
        verb = "Would migrate" if dry_run else "Migrated"
        text = "\n".join([f"{verb} {len(out['items'])} file(s):",
                           *(f"  - {i.get('log') or i.get('recipe') or i['path']}: {', '.join(i['from'])} -> {i['to']} ({i['path']})" for i in out["items"])])
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
    for gid, g in (s.get("groups") or {}).items() if s["state"] != "completed" else ():  # quiet when done (§13.1)
        lines.append(f"  {gid}: {g['summary']}")
    for r in s["running"]:
        lines.append(f"  {r['step_path']}#{r['attempt']}: packet {r['packet']}; result goes in {r['result']}")
    for q in s.get("queued") or []:
        lines.append(f"  {q['step_path']}: queued for the working tree (position {q['position']}, worker {q['worker']})")
    for st in s.get("stale") or []:
        how = "dispatch it to re-run, or the owner may `decide ... confirm`" if st["runnable"] else st.get("waiting", "")
        lines.append(f"  {st['step_path']}: stale ({st.get('cause')}{', revised ' + st['revised'] if st.get('revised') else ''}); {how}")
    if s.get("awaiting_baseline"):
        lines.append(f"  waiting for the baseline of adoption {s['adoption']['run']} (only triage runs until then)")
    lines += _pending_lines(s)
    return "\n".join(lines)


@app.command()
def board(
    needs_me: Annotated[bool, typer.Option("--needs-me", help="Only runs waiting on an owner decision.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Every non-terminal run: position, running and queued work, owner decisions owed, lease holder."""
    out = _call(as_json, lambda: _api().board(needs_me=needs_me))
    lines = []
    for r in out["runs"]:
        if "error" in r:
            lines.append(f"{r['run_id']}: ERROR {r['error']}")
            continue
        pos = r["position"]
        bits = [f"{r['run_id']} {r['title'] or ''} [{r['recipe']}{', ' + r['level'] if r.get('level') else ''}]".replace("  ", " "),
                f"{pos['done']}/{pos['total']} done"]
        if r["running"]:
            bits.append("running: " + ", ".join(f"{x['step_path']} ({x['profile']})" for x in r["running"]))
        if r["queued"]:
            bits.append("queued: " + ", ".join(q["step_path"] for q in r["queued"]))
        if r["ready"]:
            bits.append("ready: " + ", ".join(r["ready"]))
        lease = r.get("lease")
        if lease:
            bits.append("lease: " + ("you" if lease["yours"] else lease["director_id"]) + (" (expired)" if lease["expired"] else ""))
        lines.append(" · ".join(bits))
        lines += [f"  {g}: {summary}" for g, summary in r["groups"].items()]
        lines += ["  " + line for line in _pending_lines(r)]
    if not out["runs"]:
        lines.append("No runs need you." if needs_me else "No active runs.")
    for i in out.get("incidents") or []:
        lines.append(f"Open platform incident {i['id']}: {i['class']}/{i['code']} on {i['step_path']} of {i['run']}")
    ws = out["workspace"]
    if ws["holder"]:
        lines.append(f"Working tree: held by {ws['holder']['step_path']} of {ws['holder']['run_id']}" + (f"; {ws['queued']} queued" if ws["queued"] else ""))
    _done(out, as_json, "\n".join(lines))


@app.command()
def start(
    recipe: Annotated[Optional[str], typer.Argument(help="Vendored recipe (id or id@version).")] = None,
    inputs: Annotated[Optional[str], typer.Option("--inputs", help="Run inputs: a JSON object, or @file.json.")] = None,
    title: Annotated[Optional[str], typer.Option(help="Work item title (default: inputs.title).")] = None,
    from_plan: Annotated[Optional[str], typer.Option("--from-plan", help="A part of a process plan (<part> or <framing run>/<part>), started as proposed.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Start a run (a work item) and claim its lease."""
    values = _parse_inputs(inputs, as_json) if inputs is not None else None
    out = _call(as_json, lambda: _api().start(recipe, values, title=title, from_plan=from_plan))
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
    wait: WaitOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Build the step's packet and hand it to the worker; returns once it has started (or, with --wait, finished)."""
    out = _call(as_json, lambda: _api().dispatch(run, step, worker, wait=wait))
    _dispatched(out, as_json)


def _warn(out: dict, as_json: bool) -> None:
    """Text mode: each warning on stderr, so it shows however stdout is captured (JSON keeps them in ``warnings``)."""
    if not as_json:
        for w in out.get("warnings") or []:
            typer.echo(f"WARNING: {w}", err=True)


def _wake_lines(wake: dict | None) -> list[str]:
    if not wake or wake.get("configured") or not wake.get("notice"):
        return []
    return ["No completion hook would wake you when this needs the owner. Before ending your turn, tell the owner:",
            f"   {wake['notice']}"]


def _dispatched(out: dict, as_json: bool) -> None:
    _warn(out, as_json)
    if out.get("queued"):
        started = out.get("started_from_queue")
        if started and started.get("started"):
            _done(out, as_json, f"{out['step_path']}: the working tree was free; started from the queue [{started['dispatch_id']}]")
        h = out.get("holder")
        behind = f"behind {h['step_path']} of {h['run_id']}" if h else "behind earlier requests"
        _done(out, as_json, f"Queued {out['step_path']} for the working tree ({behind}; position {out['position']}) [{out['queue_id']}]\n"
                            f"It starts by itself when the tree is free. Withdraw: baton cancel {out['run_id']} {out['step_path']}")
    head = f"Dispatched {out['step_path']} attempt {out['attempt']} to {out['worker']} ({out['adapter']}) [{out['dispatch_id']}]"
    if "outcome" not in out and out["adapter"] == "manual":  # a person does the work
        _done(out, as_json, f"{head}\n{out['handoff']}\nThen: baton submit {out['run_id']} {out['step_path']}")
    if "outcome" not in out:  # running under its supervisor
        _done(out, as_json, f"{head}\nRunning until {out['deadline']} (effort {out['effort']}); log: {out.get('log')}\nThen: baton wait {out['run_id']} --dispatch {out['dispatch_id']}")
    code = EXIT_PROBLEM if out["outcome"] == "retry" and not out["needs_owner"] else None
    _done(out, as_json, f"{head}\n{_outcome_text(out)}", code)


@app.command()
def cancel(run: Annotated[str, typer.Argument(help="Run id.")], step: Annotated[str, typer.Argument(help="Step path.")], as_json: JsonOpt = False) -> None:
    """Withdraw a dispatch queued for the working tree."""
    out = _call(as_json, lambda: _api().cancel(run, step))
    _done(out, as_json, f"Withdrew the queued dispatch of {step} [{out['queue_id']}]")


@app.command()
def eligible(run: Annotated[str, typer.Argument(help="Run id.")], step: Annotated[str, typer.Argument(help="Step path.")], as_json: JsonOpt = False) -> None:
    """Workers that may do a step, in preference order, with every exclusion's reasons."""
    out = _call(as_json, lambda: _api().eligible(run, step))
    lines = [f"{i}. {e['profile']} ({_route(e)}): {'; '.join(e['reasons'])}" for i, e in enumerate(out["eligible"], 1)]
    if not lines:
        lines.append(f"No eligible worker for {step}." + (" The step is escalated." if out["escalated"] else ""))
    lines += [f"   excluded {e['profile']}: {'; '.join(e['reasons'])}" for e in out["excluded"]]
    lines += _wake_lines(out.get("wake"))
    lines += _pending_lines(out)
    _done(out, as_json, "\n".join(lines))


@app.command()
def retry(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path.")],
    worker: Annotated[Optional[str], typer.Option("--worker", help="Worker profile (default: the previous attempt's).")] = None,
    guidance: Annotated[Optional[str], typer.Option("--guidance", help="Additive guidance for the new attempt.")] = None,
    wait: WaitOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Start a new attempt of a step whose previous attempt was not accepted."""
    out = _call(as_json, lambda: _api().retry(run, step, worker, guidance, wait=wait))
    _dispatched(out, as_json)


def _outcome_text(out: dict) -> str:
    o = out["outcome"]
    head = {
        "passed": f"{out['step_path']} passed (attempt {out['attempt']})",
        "needs_human": f"{out['step_path']} is waiting for the owner",
        "retry": f"{out['step_path']} attempt {out['attempt']} was not accepted; the step is ready for another attempt",
        "escalated": f"{out['step_path']} escalated",
        "next_iteration": f"{out['step_path']}: the iteration's work is not done; the next iteration starts",
        "iteration_limit": f"{out['step_path']}: the work is not done at the iteration limit; the owner decides",
        "revised": f"{out['step_path']} is ready for a revised attempt",
        "needs_review": f"{out['step_path']} is waiting for its review",
        "recorded": f"{out['step_path']}: recorded",
        "waived": f"{out['step_path']}: the failed gate is waived; the work goes on",
        "waiver_pending": f"{out['step_path']}: waiver recorded",
        "abandoned": f"{out['step_path']} abandoned",
        "running": f"{out['step_path']} is still running",
        "confirmed": f"{out['step_path']} confirmed unchanged by the owner; its earlier result stands",
        "retriage_requested": f"{out['step_path']} is ready to re-triage; the new level then waits on the owner",
        "retriage_rejected": f"{out['step_path']}: the owner kept the current level; the earlier triage result stands",
    }[o]
    lines = [head] + [f"  - {r.splitlines()[0]}" for r in out["reasons"] if o != "needs_human"]
    if out["ready"]:
        lines.append("Ready: " + ", ".join(out["ready"]))
    if out["run_completed"]:
        lines.append(f"Run {out['run_id']} completed.")
    lines += _pending_lines(out)
    return "\n".join(lines)


@app.command("wait")
def wait_cmd(
    run: Annotated[str, typer.Argument(help="Run id.")],
    dispatch_id: Annotated[Optional[str], typer.Option("--dispatch", help="Dispatch id (default: all running work of the run).")] = None,
    timeout: Annotated[Optional[float], typer.Option("--timeout", help="Give up after this many seconds (exit 1).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Block until dispatched work finishes and is recorded (for attached Directors)."""
    out = _call(as_json, lambda: _api().wait(run, dispatch_id, timeout))
    lines = []
    for r in out["results"]:
        lines.append(_outcome_text({**r, "run_id": run, "pending_decisions": []}) if r["outcome"] != "running" else f"{r['step_path']} attempt {r['attempt']} is still running")
    for d in out["waiting_for_submit"]:
        lines.append(f"{d} is done by a person: waiting for `baton submit`")
    if not out["results"] and not out["waiting_for_submit"]:
        lines.append(f"Nothing is running in {run}.")
    lines += _pending_lines(out)
    if out["timed_out"]:
        _done(out, as_json, "\n".join(lines + ["Timed out waiting."]), EXIT_PROBLEM)
    _done(out, as_json, "\n".join(lines))


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
    ref: Annotated[str, typer.Argument(help="What is being decided: the step path awaiting the owner, an instance path at its iteration limit, <step>#<finding>, skip:<seq>, publish:<step>.<artifact> or drift:<step>.<artifact>.")],
    decision: Annotated[str, typer.Argument(help="approve | reject (gates); retry | abandon (escalations); accept-risk (a finding); confirm (a runnable stale step); acknowledge (a skip notice); overwrite | keep | alternate (a publish conflict); leave (drift).")],
    note: Annotated[str, typer.Option("--note", help="The owner's words, recorded verbatim.")] = "",
    path: Annotated[Optional[str], typer.Option("--path", help="alternate: the project path to publish at instead.")] = None,
    answers: Annotated[Optional[Path], typer.Option("--answers", help="retry of a blocked step: a JSON file [{id, answer, owner_words}] of the owner's confirmed answers (keep it outside .baton/).")] = None,
    partial: Annotated[bool, typer.Option("--partial", help="With --answers: record a deliberately partial set (a needed question left open).")] = False,
    items: Annotated[Optional[str], typer.Option("--items", help="select (a framing run's frame gate): the chosen part ids, comma-separated; empty for none.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Record the owner's decision, verbatim."""
    parsed = _read_answers(answers, as_json) if answers is not None else None
    chosen = [i.strip() for i in items.split(",") if i.strip()] if items is not None else None
    out = _call(as_json, lambda: _api().decide(run, ref, decision, note, path=path, answers=parsed, partial=partial, items=chosen))
    if out.get("outcome") == "selected":
        lines = [f"Framing {out['framing']}: selected {', '.join(out['selected']) or 'nothing'} ({out['decision_id']}); {out['state']}"]
        lines += [f"  vendored {r}" for r in out["vendored"]]
        lines += [f"  started {r['run']} ({r['recipe']}) for {r['part']}" for r in out["runs"]]
        lines += [f"  gap {g['part']}: {g['reason']}" for g in out["gaps"]]
        _done(out, as_json, "\n".join(lines))
        return
    _done(out, as_json, _outcome_text(out))


@app.command()
def waive(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path.")],
    gate: Annotated[str, typer.Argument(help="Gate index, gate type (when the step has one), independence or protected.")],
    reason: Annotated[str, typer.Option("--reason", help="The owner's decision, recorded verbatim.")],
    as_json: JsonOpt = False,
) -> None:
    """Waive one gate occurrence (owner decision): the failed one the step holds, else the next."""
    out = _call(as_json, lambda: _api().waive(run, step, gate, reason))
    _done(out, as_json, _outcome_text({**out, "run_id": run}))


@app.command()
def disposition(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path whose review recorded the finding.")],
    finding: Annotated[str, typer.Argument(help="Finding id (or <gate>:<id>).")],
    value: Annotated[str, typer.Argument(help="fixed | rejected | accepted-risk")],
    evidence: Annotated[Optional[str], typer.Option("--evidence", help="fixed: commit or file:line; rejected: file:line or path::test; accepted-risk: the owner's decision id.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Record a finding's disposition; it takes effect at the next review of that finding."""
    out = _call(as_json, lambda: _api().disposition(run, step, finding, value, evidence))
    _done(out, as_json, _outcome_text({**out, "run_id": run}))


@app.command("ingest-revision")
def ingest_revision(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path whose published artifact was edited.")],
    artifact: Annotated[str, typer.Argument(help="Artifact name.")],
    note: Annotated[str, typer.Option("--note", help="The owner's decision, in their own words (recorded verbatim).")],
    feed: Annotated[str, typer.Option("--feed", help="revision_inputs (only human_revision.* inputs) | dependents (also not-yet-started dependents' artifact inputs).")] = "revision_inputs",
    as_json: JsonOpt = False,
) -> None:
    """Accept an edited published file as a human revision (§10.5)."""
    out = _call(as_json, lambda: _api().ingest_revision(run, step, artifact, note, feed=feed))
    stale = f"\nPossibly stale (passed before the revision): {', '.join(out['possibly_stale'])}" if out.get("possibly_stale") else ""
    _done(out, as_json, f"Ingested revision {out['revision']} of {artifact} ({step}) as {out['reference']}" + stale)


@app.command()
def revise(
    run: Annotated[str, typer.Argument(help="Run id.")],
    step: Annotated[str, typer.Argument(help="Step path of an accepted step to correct.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the step is being revised (recorded, given to the worker).")],
    as_json: JsonOpt = False,
) -> None:
    """Correct an earlier step of this run (owner-approved): new attempt, dependents become stale."""
    out = _call(as_json, lambda: _api().revise(run, step, reason))
    stale = f"\nStale: {', '.join(out['stale'])}" if out.get("stale") else ""
    _done(out, as_json, _outcome_text({**out, "run_id": run}) + stale)


@app.command()
def retriage(
    run: Annotated[str, typer.Argument(help="Run id.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the work's complexity should be assessed again (recorded, given to the worker).")],
    as_json: JsonOpt = False,
) -> None:
    """Rerun triage; the new level applies, once the owner approves it, only to work not yet started."""
    out = _call(as_json, lambda: _api().retriage(run, reason))
    _done(out, as_json, _outcome_text({**out, "run_id": run}))


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
def check(
    strict: Annotated[bool, typer.Option("--strict", help="Treat drift of published deliverables as an error.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Repository consistency for pre-commit and CI: one ERROR line per problem, exit 0 when clean."""
    from .check import check as run_check
    from .project import find_root

    root = _call(as_json, lambda: find_root(_opts.project))
    issues = run_check(root, strict=strict)
    errors = [i for i in issues if i.severity == "error"]
    if as_json:
        _emit({"ok": not errors, "issues": [i.model_dump() for i in issues]}, True, "")
    else:
        for i in issues:
            typer.echo(f"{'ERROR' if i.severity == 'error' else 'WARNING'} {i.where}: {i.message}")
    raise typer.Exit(EXIT_PROBLEM if errors else EXIT_OK)


@app.command()
def doctor(
    profile: Annotated[Optional[str], typer.Option("--profile", help="Check only this worker profile.")] = None,
    no_run: Annotated[bool, typer.Option("--no-run", help="Skip the no-op round trips (no model calls).")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Machine readiness: lockfile, profiles (env, executables, a no-op run each), uncovered steps. One line when healthy."""
    out = _call(as_json, lambda: _api().doctor(profile, run_noop=not no_run))
    lines = [out["line"]] if out["ok"] else [f"PROBLEM {p}" for p in out["problems"]]
    lines += _blocking_lines(out)
    lines += [f"WARNING {w}" for w in out["warnings"]]
    _emit({**out}, as_json, "\n".join(lines))
    raise typer.Exit(EXIT_OK if out["ok"] else EXIT_PROBLEM)


# ---------------------------------------------------------------------------
# Experts, the platform area and process feedback (§12)
# ---------------------------------------------------------------------------

RefOpt = Annotated[Optional[list[str]], typer.Option("--ref", help="A reference the expert gets, by name (repeatable); see `baton sme-eligible`.")]


def _sme_text(out: dict) -> str:
    lines = [f"Consultation {out['consultation']} ({out.get('subject')}" + (f", run {out['run_id']}" if out.get("run_id") else "") + f"): {out.get('state')}"]
    if out.get("contact"):
        lines.append(f"Consulting through a proxy: {out['contact']}")
    for t in out.get("turns") or []:
        lines.append(f"Turn {t['turn']} ({t.get('worker')}): {t['status']}" + (f" — {t['question']}" if t.get("question") else ""))
        a = t.get("answer")
        if a:
            lines.append(f"  Answer ({a['confidence']} confidence): {a['answer']}")
            if a.get("requested_refs"):
                lines.append("  Requests: " + ", ".join(a["requested_refs"]))
            if a.get("suggests_retriage"):
                lines.append("  The expert suggests re-triage.")
        for name, path in (t.get("artifacts") or {}).items():
            lines.append(f"  Artifact {name}: {path}")
        if t.get("awaiting"):
            lines.append(f"  Waiting on {t['awaiting']['who']}: {t['awaiting']['what']}")
        if t.get("reasons"):
            lines.append("  " + "; ".join(t["reasons"]))
    for h in out.get("handoffs") or []:
        lines.append(f"Handoff: {h['path']}")
    return "\n".join(lines)


def _sme_started(out: dict, as_json: bool) -> None:
    _warn(out, as_json)
    if "turns" in out:
        _done(out, as_json, _sme_text(out))
    _done(out, as_json, f"Asked the {out['subject']} expert ({out['worker']}): consultation {out['consultation']} turn {out['turn']}, due {out['deadline']}")


@app.command("ask-sme")
def ask_sme(
    subject: Annotated[str, typer.Argument(help="project | platform | process")],
    question: Annotated[str, typer.Argument(help="The question, as the owner asked it.")],
    ref: RefOpt = None,
    run: Annotated[Optional[str], typer.Option("--run", help="The run the question is about.")] = None,
    mode: Annotated[str, typer.Option("--mode", help="relay (dispatch and record an answer) | handoff (a prompt to paste elsewhere).")] = "relay",
    worker: Annotated[Optional[str], typer.Option("--worker", help="Expert profile (default: the first eligible).")] = None,
    contact: Annotated[Optional[str], typer.Option("--contact", help="A person consulted through the expert (name, role, how to reach them).")] = None,
    wait: WaitOpt = False,
    timeout: Annotated[Optional[float], typer.Option("--timeout", help="With --wait: seconds to wait at most.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Consult an expert by subject; the runtime assembles what it sees (§12.1)."""
    out = _call(as_json, lambda: _api().ask_sme(subject, question, ref or [], run_id=run, mode=mode, worker=worker, contact=contact, wait=wait, timeout=timeout))
    if out.get("mode") == "handoff":
        _done(out, as_json, out["handoff"] + f"\n\n(Saved to {out['path']}; consultation {out['consultation']}.)")
    _sme_started(out, as_json)


@app.command("sme-followup")
def sme_followup(
    consultation: Annotated[str, typer.Argument(help="Consultation id.")],
    question: Annotated[Optional[str], typer.Option("--question", help="A follow-up question.")] = None,
    ref: RefOpt = None,
    attach: Annotated[Optional[list[str]], typer.Option("--attach", help="A file the owner supplies, e.g. a person's reply (repeatable).")] = None,
    worker: Annotated[Optional[str], typer.Option("--worker", help="Expert profile (default: the previous turn's).")] = None,
    wait: WaitOpt = False,
    timeout: Annotated[Optional[float], typer.Option("--timeout", help="With --wait: seconds to wait at most.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """The next turn of a consultation: earlier turns plus new refs, a question or attachments."""
    out = _call(as_json, lambda: _api().sme_followup(consultation, question, ref or [], attach or [], worker=worker, wait=wait, timeout=timeout))
    _sme_started(out, as_json)


@app.command("sme")
def sme_cmd(
    consultation: Annotated[str, typer.Argument(help="Consultation id.")],
    wait: WaitOpt = False,
    timeout: Annotated[Optional[float], typer.Option("--timeout", help="With --wait: seconds to wait at most.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """A consultation: its turns, the expert's answers and artifacts, and what it waits for."""
    out = _call(as_json, lambda: _api().sme_status(consultation, wait=wait, timeout=timeout))
    _done(out, as_json, _sme_text(out))


@app.command("sme-handoff")
def sme_handoff(consultation: Annotated[str, typer.Argument(help="Consultation id.")], as_json: JsonOpt = False) -> None:
    """Print a copy-and-paste prompt to continue the consultation with the expert directly (refused when that cannot work)."""
    out = _call(as_json, lambda: _api().sme_handoff(consultation))
    _done(out, as_json, out["handoff"] + f"\n\n(Saved to {out['path']}.)")


@app.command("sme-eligible")
def sme_eligible(
    subject: Annotated[str, typer.Argument(help="project | platform | process")],
    run: Annotated[Optional[str], typer.Option("--run", help="The run (its recipe may set the expert's requirements).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Profiles that may answer as this subject's expert, in order."""
    out = _call(as_json, lambda: _api().sme_eligible(subject, run))
    lines = [f"{e['profile']} ({_route(e)}): {'; '.join(e['reasons'])}" for e in out["eligible"]] or ["No eligible profile."]
    lines += [f"  excluded {x['profile']}: {'; '.join(x['reasons'])}" for x in out["excluded"]]
    lines += _wake_lines(out.get("wake"))
    _done(out, as_json, "\n".join(lines))


@app.command("promote-sme")
def promote_sme(
    consultation: Annotated[str, typer.Argument(help="Consultation id.")],
    target: Annotated[str, typer.Argument(help="decision | fact | lesson | proposal | revision")],
    note: Annotated[str, typer.Option("--note", help="The owner's agreement, in their own words (recorded verbatim).")],
    text: Annotated[Optional[str], typer.Option("--text", help="What to promote, if not the answer as given.")] = None,
    turn: Annotated[Optional[int], typer.Option("--turn", help="Which turn's answer (default: the latest answered).")] = None,
    artifact: Annotated[Optional[str], typer.Option("--artifact", help="revision: the published artifact to revise, <step_path>.<name>.")] = None,
    from_artifact: Annotated[Optional[str], typer.Option("--from", help="revision: the expert's artifact to use as the content.")] = None,
    feed: Annotated[str, typer.Option("--feed", help="revision: revision_inputs | dependents.")] = "revision_inputs",
    as_json: JsonOpt = False,
) -> None:
    """Bring an expert's answer into the work, with the owner's agreement (§12.2)."""
    out = _call(as_json, lambda: _api().promote_sme(consultation, target, note, text=text, turn=turn, artifact=artifact, from_artifact=from_artifact, feed=feed))
    where = out.get("reference") or out.get("path") or out.get("entry") or ""
    _done(out, as_json, f"Promoted {consultation} as a {target}" + (f": {where}" if where else ""))


@app.command("platform-fact")
def platform_fact(
    text: Annotated[str, typer.Argument(help="The fact, e.g. 'codex is under nvm v22 on the runtime host'.")],
    source: Annotated[str, typer.Option("--source", help="Where it comes from.")] = "owner",
    as_json: JsonOpt = False,
) -> None:
    """Record a durable platform fact (.baton/platform/facts.md)."""
    out = _call(as_json, lambda: _api().platform_fact(text, source))
    _done(out, as_json, f"Recorded: {out['entry']}")


@app.command("platform-incident")
def platform_incident(
    action: Annotated[str, typer.Argument(help="list | show | resolve")] = "list",
    incident: Annotated[Optional[str], typer.Argument(help="Incident id (show, resolve).")] = None,
    fix: Annotated[Optional[str], typer.Option("--fix", help="With resolve: what was fixed.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Platform incidents: opened automatically for platform and unknown failures; resolving readies the step once."""
    out = _call(as_json, lambda: _api().platform_incident(action, incident, fix))
    if action == "list":
        text = "\n".join(f"{i['id']} [{i['status']}] {i.get('class')}/{i.get('code')} on {i.get('step_path')} of {i.get('run')}: {i.get('message')}"
                         for i in out["incidents"]) or "No platform incidents."
    elif action == "show":
        text = json.dumps(out["incident"], indent=2)
    else:
        text = f"Resolved {out['incident']}" + "".join(f"\n  {r['step_path']} of {r['run']} is ready again" if "not_readied" not in r
                                                      else f"\n  {r['step_path']} of {r['run']} not readied: {r['not_readied']}" for r in out["readied"])
    _done(out, as_json, text)


@app.command()
def note(
    text: Annotated[Optional[str], typer.Argument(help="The owner's words, verbatim.")] = None,
    keep_file: Annotated[Optional[str], typer.Option("--keep-file", help="The owner's answer to the notes-file offer: yes | no.")] = None,
    note_: Annotated[Optional[str], typer.Option("--note", help="With --keep-file: the owner's words.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Keep a note the owner asked for, word for word, in the project's notes file (offered once)."""
    out = _call(as_json, lambda: _api().note(text, keep_file=keep_file, note=note_))
    msg = {"offer": "No notes file yet: offer to keep one.", "declined": "The owner chose not to keep a notes file here.",
           "kept": f"Notes file: {out.get('path')}."}[out["notes"]]
    _done(out, as_json, msg + (f" Noted at {out['at']}." if out.get("recorded") else ""))


@app.command()
def feedback(
    kind: Annotated[str, typer.Argument(help="friction | skipped_step | waste | confusing")],
    text: Annotated[str, typer.Argument(help="What happened.")],
    run: Annotated[Optional[str], typer.Option("--run", help="The run it concerns.")] = None,
    step: Annotated[Optional[str], typer.Option("--step", help="The step it concerns.")] = None,
    gate: Annotated[Optional[str], typer.Option("--gate", help="skipped_step: the gate skipped (index or type).")] = None,
    informed_owner: Annotated[bool, typer.Option("--informed-owner", help="skipped_step: the owner was told at the time.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Record process feedback; a skipped blocking gate or approval is surfaced to the owner at once."""
    out = _call(as_json, lambda: _api().feedback(kind, text, run, step, gate, informed_owner))
    lines = [f"Recorded feedback (seq {out['seq']})."] + _pending_lines(out)
    _done(out, as_json, "\n".join(lines))


# ---------------------------------------------------------------------------
# The Director surface: explain, action permissions, MCP (§10.6, §13.2, §13.7)
# ---------------------------------------------------------------------------


@app.command()
def explain(run: Annotated[str, typer.Argument(help="Run id.")], as_json: JsonOpt = False) -> None:
    """Process facts only: what is done, where the run is, what remains at this level and what other levels would change."""
    out = _call(as_json, lambda: _api().explain(run))
    _done(out, as_json, out["text"])


ApprovedOpt = Annotated[bool, typer.Option("--approved", help="The owner approved this `ask` action (with --note).")]
NoteOpt = Annotated[Optional[str], typer.Option("--note", help="With --approved: the owner's words, recorded verbatim.")]


def _permit_text(out: dict, what: str) -> str:
    if not out["granted"]:
        return f"{what}: the owner's approval is needed ({out['action']}, rule ask).\n{out['message']}"
    how = f"approved by the owner ({out['decision_id']})" if out["permission"] == "approved" else "allowed"
    return f"{what}: {how}."


@app.command()
def push(approved: ApprovedOpt = False, note: NoteOpt = None, as_json: JsonOpt = False) -> None:
    """Push the current branch, if project.yaml permissions allow this kind of change (docs only, verified, other)."""
    out = _call(as_json, lambda: _api().push(approved=approved, note=note))
    if out.get("reason") == "nothing to push":
        _done(out, as_json, "Nothing to push.")
    text = _permit_text(out, f"Push of {len(out['commits'])} commit(s) to {out['remote']}/{out['branch']} [{out['category'].replace('_', '-')}]")
    if out.get("pushed"):
        text += "\nPushed."
    _done(out, as_json, text)


@app.command()
def permission(
    action: Annotated[str, typer.Argument(help="tag | merge | deploy | force_push")],
    detail: Annotated[Optional[str], typer.Option("--detail", help="What exactly will be done (recorded).")] = None,
    approved: ApprovedOpt = False,
    note: NoteOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Check (and record) an action the Director takes outside the runtime: allow, ask (exit 4) or deny (exit 1)."""
    out = _call(as_json, lambda: _api().permission(action.replace("-", "_"), detail, approved=approved, note=note))
    _done(out, as_json, _permit_text(out, action))


@app.command()
def mcp(
    http: Annotated[bool, typer.Option("--http", help="Serve streamable HTTP instead of stdio (needs a token in ~/.baton/mcp.yaml).")] = False,
    host: Annotated[str, typer.Option("--host", help="With --http: loopback address to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="With --http: port.")] = 8765,
) -> None:
    """Serve the Director API as MCP tools: over stdio (started by the harness), or over HTTP on loopback (started by the owner)."""
    try:
        from . import mcp_server
    except ImportError as e:
        _fail(False, EXIT_PROBLEM, "mcp.missing", f"the MCP server needs the optional extra: pip install 'baton[mcp]' ({e})")
    try:
        if http:
            mcp_server.serve_http(_opts.project, _opts.director, host=host, port=port)
        else:
            mcp_server.serve_stdio(_opts.project, _opts.director)
    except EngineError as e:
        _fail(False, EXIT_PROBLEM, e.code, str(e))


# ---------------------------------------------------------------------------
# The worker resource manager (§6.4, 0077): machine scope, no project needed
# ---------------------------------------------------------------------------

workers_app = typer.Typer(no_args_is_help=True, help="This machine's workers: what is found, declared and generated (§6.4).")
app.add_typer(workers_app, name="workers")


def _resources(as_json: bool, fn: Callable[[Path], Any]) -> Any:
    from .known_workers import KnownWorkersError
    from .project import machine_home
    from .resources import ResourcesError

    try:
        return fn(machine_home())
    except (ResourcesError, KnownWorkersError) as e:
        _fail(as_json, EXIT_PROBLEM, "configuration.resources", str(e))


@workers_app.command("status")
def workers_status(as_json: JsonOpt = False) -> None:
    """What is discovered, declared and generated, and whether setup is complete. Changes nothing."""
    from . import resources

    out = _resources(as_json, lambda h: resources.status(h))
    lines = [f"Machine setup: {'complete' if out['setup_complete'] else 'not done yet (`baton workers setup`)'}"]
    for d in out["detected"]:
        lines.append(f"found {d['provider']}: " + ("ready" if d["usable"] else d["problem"] or "not usable"))
    for n, r in out["declared"].items():
        lines.append(f"declared {n}: {r['provider']}")
    for n, g in out["generated"].items():
        state = "yours (edited, never changed)" if g["ownership"] != "untouched" else ("verified " + g["verified"]["date"] if g.get("verified") else "unverified")
        lines.append(f"profile {n}: {state}" + (f"; {g['flag']}" if g.get("flag") else ""))
        observed = {st: [c for c, s in g.get("capabilities", {}).items() if s == st] for st in ("verified", "absent")}
        if any(observed.values()):
            lines.append("  " + "; ".join(f"{st}: {', '.join(cs)}" for st, cs in observed.items() if cs))
    for n, caps in out.get("capability_states", {}).items():
        if n not in out["generated"]:
            lines.append(f"profile {n}: " + "; ".join(f"{c} {s['state']}" for c, s in caps.items()))
    if out["available_not_generated"]:
        lines.append("available, not set up yet: " + ", ".join(out["available_not_generated"]) + " (`baton workers setup`)")
    _emit(out, as_json, "\n".join(lines))


@workers_app.command("setup")
def workers_setup(
    verify: Annotated[Optional[list[str]], typer.Option("--verify", help="Live-check this profile (repeatable; costs one small model call each).")] = None,
    verify_all: Annotated[bool, typer.Option("--verify-all", help="Live-check every generated profile.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Generate profiles for what this machine has and the owner declared; new models appear only here."""
    from . import resources

    which = [] if verify_all else verify
    out = _resources(as_json, lambda h: resources.setup(h, verify=which))
    lines = [f"wrote {n}" for n in out["written"]] + [f"refreshed {n}" for n in out["refreshed"]] + [f"verified {n}" for n in out["verified"]]
    lines += [f"kept {k['profile']}: {k['reason']}" for k in out["kept"]]
    lines += [f"kept {n}: {why}" for n, why in out["not_offered"].items()]
    lines += [f"FAILED {f['profile']}: {f['reason']}" for f in out["failed"]]
    lines += [f"left alone {c['profile']}: {c['reason']}" for c in out["collisions"]]
    lines += [f"not available: {s['route']}: {s['reason']}" for s in out["skipped"]]
    lines += [f"not offered by {d['provider']} here: {c} (its --help does not show the flag; a newer version may add it)"
              for d in out["detected"] for c, ok in (d.get("tools") or {}).items() if not ok]
    _emit(out, as_json, "\n".join(lines) or "Nothing new.")
    raise typer.Exit(EXIT_PROBLEM if out["failed"] else EXIT_OK)


@workers_app.command("declare")
def workers_declare(
    name: Annotated[Optional[str], typer.Argument(help="The resource's name, e.g. openrouter-main.")] = None,
    provider: Annotated[Optional[str], typer.Option("--provider", help="Its provider, e.g. openrouter.")] = None,
    credential: Annotated[Optional[str], typer.Option("--credential", help="secret:<name> (never the key itself, §6.1).")] = None,
    base_url: Annotated[Optional[str], typer.Option("--base-url")] = None,
    model: Annotated[Optional[list[str]], typer.Option("--model", help="Limit to this model_id (repeatable).")] = None,
    capability: Annotated[Optional[list[str]], typer.Option("--capability", help="A machine-dependent capability it has here (repeatable).")] = None,
    note: Annotated[Optional[str], typer.Option("--note")] = None,
    remove: Annotated[bool, typer.Option("--remove", help="Remove this resource.")] = False,
    nothing_more: Annotated[Optional[bool], typer.Option("--nothing-more/--more", help="Record that there is nothing more to add (or undo that).")] = None,
    profile: Annotated[Optional[str], typer.Option("--profile", help="Set capability states on this profile instead (with --likely / --absent).")] = None,
    likely: Annotated[Optional[list[str]], typer.Option("--likely", help="Reset this capability to likely, so it is tried again (repeatable).")] = None,
    absent: Annotated[Optional[list[str]], typer.Option("--absent", help="Declare this capability absent on the profile (repeatable).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Add, change or remove a resource discovery cannot find, or say there is nothing more.
    With --profile: reset a capability to likely, or declare it absent (§6.1)."""
    from . import resources

    if profile is not None or likely or absent:
        if profile is None or not (likely or absent):
            _fail(as_json, EXIT_USAGE, "usage.declare", "capability states need --profile and at least one --likely or --absent")
        if name is not None or any(v not in (None, False) for v in (provider, credential, base_url, model, capability, note, nothing_more)) or remove:
            _fail(as_json, EXIT_USAGE, "usage.declare", "declare either a resource or capability states on a profile, not both")
        out = _resources(as_json, lambda h: resources.declare_capabilities(h, profile, likely=likely, absent=absent))
        text = [f"{c['capability']}: {c['from']} -> {c['to']}" + ("" if c["changed"] else " (unchanged)") for c in out["capability_states"]]
        _emit(out, as_json, "\n".join(text + [f"saved {out['path']}"]))
        return
    if name is None and nothing_more is None:
        _fail(as_json, EXIT_USAGE, "usage.declare", "name a resource, or pass --nothing-more")
    out = _resources(as_json, lambda h: resources.declare(h, name, provider=provider, credential=credential, base_url=base_url, models=model,
                                                          capabilities=capability, note=note, remove=remove, nothing_more=nothing_more))
    text = [f"{k}: {v}" for k, v in out.items() if k in ("declared", "removed", "nothing_more", "warning")]
    _emit(out, as_json, "\n".join(text + [f"saved {out['path']}"]))


def main() -> None:
    """The ``baton`` command: the launcher picks the runtime version first (§14.1)."""
    from . import launcher

    launcher.main()


if __name__ == "__main__":
    main()
