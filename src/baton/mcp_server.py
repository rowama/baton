"""The MCP server (§13.2): the Director API (§13.1) as MCP tools.

One tool per API call, with the CLI's names (``-`` becomes ``_``) and
arguments. Every call opens the project afresh and closes it, exactly like one
CLI invocation: the server holds no state, so stopping it loses nothing and
work it dispatched carries on under its supervisors (§8.7).

Results are the same JSON the CLI prints with ``--json`` (plus ``ok: true``).
A refusal is a tool error whose text is that JSON with ``ok: false``, ``error``,
``message`` and ``exit_code`` (the CLI's exit code: 1 problem, 3 lease held
elsewhere). ``needs_owner: true`` in a result is the CLI's exit code 4.

Transports:

* **stdio** (``baton mcp``): the harness starts it as a child process for its
  session and talks over stdin/stdout.
* **HTTP** (``baton mcp --http``): streamable HTTP for a Director without a
  shell, started and stopped by the owner in the foreground, never detached or
  restarted by Baton. It binds a loopback address only (no TLS yet: remote
  access goes through a TLS proxy or tunnel of the owner's choice) and requires
  ``Authorization: Bearer <token>``, the token coming from the machine-local
  ``~/.baton/mcp.yaml`` (``token: secret:<name>``, resolved like profile
  secrets, §6.1). Without a token it refuses to start.

The Director's identity is ``--director`` / ``BATON_DIRECTOR`` of the server
process (default ``<user>@<host>``), its harness ``BATON_HARNESS``.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
from pathlib import Path
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, engine
from .packet import EngineError

INSTRUCTIONS = (
    "Baton's Director API. You coordinate: never do step work, never write packets, results or "
    "anything under .baton/, never answer subject or platform questions yourself (ask_sme). "
    "Record only the owner's actual words. Follow the baton-director skill and .baton/communication.md."
)


class Tools:
    """The tool functions, bound to one project root and Director identity."""

    def __init__(self, project: str | Path | None, director: str | None):
        self.project = project
        self.director = director

    def call(self, fn: Callable[[engine.Api], Any]) -> dict[str, Any]:
        from .cli import error_payload

        try:
            api = engine.Api.open(self.project, director_id=self.director)
        except Exception as e:  # noqa: BLE001 - mapped below
            self._raise(e, error_payload)
        try:
            out = fn(api)
        except Exception as e:  # noqa: BLE001
            self._raise(e, error_payload)
        finally:
            api.close()
        if isinstance(out, dict):
            return {"ok": True, **out}
        return {"ok": True, "result": out}

    @staticmethod
    def _raise(e: Exception, error_payload: Callable[[BaseException], Any]) -> None:
        mapped = error_payload(e)
        if mapped is None:
            raise e
        code, payload = mapped
        raise ToolError(json.dumps({"ok": False, "exit_code": code, **payload}, ensure_ascii=False, default=str)) from e


def build_server(project: str | Path | None = None, director: str | None = None) -> MCPServer:
    t = Tools(project, director)
    server = MCPServer(name="baton", version=__version__, instructions=INSTRUCTIONS, log_level="WARNING")

    def tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        server.add_tool(fn, name=fn.__name__, description=(fn.__doc__ or "").strip())
        return fn

    # -- situation ---------------------------------------------------------

    @tool
    def detect() -> dict[str, Any]:
        """The project's situation, each active run's situation and machine readiness."""
        from .adopt import detect as run_detect
        from .locks import Director

        return t.call(lambda api: run_detect(t.project, director=Director.current(t.director)))

    @tool
    def doctor(profile: str | None = None, no_run: bool = False) -> dict[str, Any]:
        """Machine readiness: lockfile, worker profiles (env, executables, no-op runs unless no_run), uncovered steps."""
        return t.call(lambda api: api.doctor(profile, run_noop=not no_run))

    @tool
    def diag(since: str | None = None, code: str | None = None, run: str | None = None, records: bool = False, limit: int = 200) -> dict[str, Any]:
        """What Baton has been working around on this machine: counts per diagnostic code next to the usual rate, unusual first. since: a number of usage days or a YYYY-MM-DD date."""
        return t.call(lambda api: api.diag(since, code, run, records, limit))

    @tool
    def ui(idle_timeout: float | None = None) -> dict[str, Any]:
        """Start the optional local setup page (or find the running one) and return its link. Tell the owner to open it to connect accounts and choose models; it closes itself when idle."""
        return t.call(lambda api: api.ui(True, idle_timeout))

    @tool
    def workers_status() -> dict[str, Any]:
        """This machine's workers: discovered harnesses, declared resources, generated profiles, setup state. Changes nothing."""
        return t.call(lambda api: api.workers_status())

    @tool
    def workers_setup(verify: list[str] | None = None) -> dict[str, Any]:
        """Generate profiles from what this machine has and the owner declared. verify: profiles to live-check ([] = all; costs quota)."""
        return t.call(lambda api: api.workers_setup(verify))

    @tool
    def workers_declare(name: str | None = None, provider: str | None = None, credential: str | None = None, base_url: str | None = None,
                        models: list[str] | None = None, capabilities: list[str] | None = None, note: str | None = None,
                        remove: bool = False, nothing_more: bool | None = None, profile: str | None = None,
                        likely: list[str] | None = None, absent: list[str] | None = None) -> dict[str, Any]:
        """Add, change or remove a worker resource (credential only as secret:<name>), or record that there is nothing more to add.
        Or, with profile (and nothing else): reset its capabilities to likely, or declare them absent, on the owner's instruction only."""
        if profile is not None:
            return t.call(lambda api: api.workers_declare(profile=profile, likely=likely, absent=absent))
        return t.call(lambda api: api.workers_declare(name, provider=provider, credential=credential, base_url=base_url, models=models,
                                                      capabilities=capabilities, note=note, remove=remove, nothing_more=nothing_more))

    @tool
    def check(strict: bool = False) -> dict[str, Any]:
        """Repository consistency (hash chains, CAS, lockfile, secrets, drift); ok is false when any error is found."""
        from .check import check as run_check

        def body(api: engine.Api) -> dict[str, Any]:
            issues = run_check(api.project.root, strict=strict)
            return {"clean": not any(i.severity == "error" for i in issues), "issues": [i.model_dump() for i in issues]}

        return t.call(body)

    @tool
    def board(needs_me: bool = False) -> dict[str, Any]:
        """Every non-terminal run: position, running and queued work, owner decisions owed, lease holders, open incidents."""
        return t.call(lambda api: api.board(needs_me=needs_me))

    @tool
    def recipes() -> dict[str, Any]:
        """Vendored recipes."""
        return t.call(lambda api: api.recipes())

    @tool
    def plan(recipe: str, level: str | None = None) -> dict[str, Any]:
        """A vendored recipe's per-level step and gate table."""
        return t.call(lambda api: {"plan": api.plan(recipe, level=level).model_dump(mode="json")})

    # -- runs ----------------------------------------------------------------

    @tool
    def start(recipe: str | None = None, inputs: dict[str, Any] | None = None, title: str | None = None,
              from_plan: str | None = None) -> dict[str, Any]:
        """Start a run (a work item) of a vendored recipe with its run inputs, or a process plan's part as proposed (from_plan); claims its lease."""
        return t.call(lambda api: api.start(recipe, inputs, title=title, from_plan=from_plan))

    @tool
    def status(run: str) -> dict[str, Any]:
        """Where a run is: ready and running steps, owner decisions owed, findings, drift, lease."""
        return t.call(lambda api: api.status(run))

    @tool
    def explain(run: str) -> dict[str, Any]:
        """Process facts only: done, current position, what remains at this level and what other levels would change."""
        return t.call(lambda api: api.explain(run))

    @tool
    def eligible(run: str, step: str) -> dict[str, Any]:
        """Workers that may do a step, in preference order, with every exclusion's reasons."""
        return t.call(lambda api: api.eligible(run, step))

    @tool
    def dispatch(run: str, step: str, worker: str, wait: bool = False) -> dict[str, Any]:
        """Build the step's packet and start the worker (one from `eligible`); returns once it started, or with wait when recorded."""
        return t.call(lambda api: api.dispatch(run, step, worker, wait=wait))

    @tool
    def retry(run: str, step: str, worker: str | None = None, guidance: str | None = None, wait: bool = False) -> dict[str, Any]:
        """A new attempt of a step whose previous attempt was not accepted; guidance is additive only."""
        return t.call(lambda api: api.retry(run, step, worker, guidance, wait=wait))

    @tool
    def cancel(run: str, step: str) -> dict[str, Any]:
        """Withdraw a dispatch queued for the working tree."""
        return t.call(lambda api: api.cancel(run, step))

    @tool
    def wait(run: str, dispatch: str | None = None, timeout: float | None = None) -> dict[str, Any]:
        """Block until dispatched work finishes and is recorded (dispatch: one dispatch id; default all of the run's)."""
        return t.call(lambda api: api.wait(run, dispatch, timeout))

    @tool
    def submit(run: str, step: str, result: str | None = None) -> dict[str, Any]:
        """Hand in a manual or external worker's result directory (default: the attempt's result/); intake and gates run now."""
        return t.call(lambda api: api.submit(run, step, result))

    @tool
    def decide(run: str, ref: str, decision: str, note: str = "", path: str | None = None,
               answers: list[dict[str, Any]] | str | None = None, partial: bool = False, items: list[str] | None = None) -> dict[str, Any]:
        """Record the owner's decision verbatim (note = the owner's words). ref: a step awaiting the owner, an instance path,
        <step>#<finding>, skip:<seq>, publish:<step>.<artifact> or drift:<step>.<artifact>. answers (retry of a blocked
        step): the owner's confirmed answers [{id, answer, owner_words}], or the path of a JSON file holding them;
        partial: a deliberately partial set. items (select, a framing run's frame gate): the chosen part ids."""

        def body(api: Any) -> dict[str, Any]:
            parsed: Any = answers
            if isinstance(answers, str):
                try:
                    parsed = json.loads(Path(answers).read_text(encoding="utf-8-sig"))
                except (OSError, ValueError) as e:
                    raise EngineError("answers.unreadable", f"cannot read answers file {answers}: {e}") from e
            return api.decide(run, ref, decision, note, path=path, answers=parsed, partial=partial, items=items)

        return t.call(body)

    @tool
    def waive(run: str, step: str, gate: str, reason: str) -> dict[str, Any]:
        """Waive one gate occurrence; reason is the owner's decision, verbatim (only with the owner's approval)."""
        return t.call(lambda api: api.waive(run, step, gate, reason))

    @tool
    def disposition(run: str, step: str, finding: str, value: str, evidence: str | None = None) -> dict[str, Any]:
        """Record a finding's disposition (fixed | rejected | accepted-risk) with its evidence."""
        return t.call(lambda api: api.disposition(run, step, finding, value, evidence))

    @tool
    def revise(run: str, step: str, reason: str) -> dict[str, Any]:
        """Correct an earlier step of this run (only with the owner's approval): new attempt, dependents become stale."""
        return t.call(lambda api: api.revise(run, step, reason))

    @tool
    def retriage(run: str, reason: str) -> dict[str, Any]:
        """Rerun triage; the new level waits on the owner and applies only to work not yet started."""
        return t.call(lambda api: api.retriage(run, reason))

    @tool
    def ingest_revision(run: str, step: str, artifact: str, note: str, feed: str = "revision_inputs") -> dict[str, Any]:
        """Accept an edited published file as a human revision; note is the owner's words."""
        return t.call(lambda api: api.ingest_revision(run, step, artifact, note, feed=feed))

    @tool
    def abandon(run: str, reason: str) -> dict[str, Any]:
        """Abandon a run."""
        return t.call(lambda api: api.abandon(run, reason))

    # -- continuity and records -------------------------------------------------

    @tool
    def resume(run: str) -> dict[str, Any]:
        """Verify a run, rebuild its cache, reconcile in-flight work and claim its lease."""
        return t.call(lambda api: api.resume(run))

    @tool
    def lease(run: str, action: str, reason: str | None = None) -> dict[str, Any]:
        """Claim, release or take over (only with the owner's approval; reason required) a run's lease."""
        return t.call(lambda api: api.lease(run, action.replace("-", "_"), reason))

    @tool
    def record(run: str, step: str) -> dict[str, Any]:
        """A step's record (markdown)."""
        return t.call(lambda api: {"record": api.record(run, step)})

    @tool
    def summary(run: str) -> dict[str, Any]:
        """The run summary (markdown)."""
        return t.call(lambda api: {"summary": api.summary(run)})

    @tool
    def trace(run: str, limit: int = 20) -> dict[str, Any]:
        """The run's recent events, one line each (limit 0: all)."""
        return t.call(lambda api: {"events": api.trace(run, limit or None)})

    # -- experts, platform, feedback -------------------------------------------------

    @tool
    def ask_sme(subject: str, question: str, refs: list[str] | None = None, run: str | None = None, mode: str = "relay",
                worker: str | None = None, contact: str | None = None, wait: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """Consult an expert by subject (project | platform | process); choose refs by name; the runtime assembles the packet."""
        return t.call(lambda api: api.ask_sme(subject, question, refs or [], run_id=run, mode=mode, worker=worker, contact=contact,
                                              wait=wait, timeout=timeout))

    @tool
    def sme_followup(consultation: str, question: str | None = None, refs: list[str] | None = None, attach: list[str] | None = None,
                     worker: str | None = None, wait: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """The next turn of a consultation: a question, more refs, or files the owner supplies."""
        return t.call(lambda api: api.sme_followup(consultation, question, refs or [], attach or [], worker=worker, wait=wait, timeout=timeout))

    @tool
    def sme(consultation: str, wait: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """A consultation: its turns, the expert's answers and artifacts, and what it waits for."""
        return t.call(lambda api: api.sme_status(consultation, wait=wait, timeout=timeout))

    @tool
    def sme_handoff(consultation: str) -> dict[str, Any]:
        """The runtime-made copy-and-paste prompt to continue with the expert directly (give it to the owner unchanged)."""
        return t.call(lambda api: api.sme_handoff(consultation))

    @tool
    def sme_eligible(subject: str, run: str | None = None) -> dict[str, Any]:
        """Profiles that may answer as this subject's expert, in order."""
        return t.call(lambda api: api.sme_eligible(subject, run))

    @tool
    def promote_sme(consultation: str, target: str, note: str, text: str | None = None, turn: int | None = None,
                    artifact: str | None = None, from_artifact: str | None = None, feed: str = "revision_inputs") -> dict[str, Any]:
        """Bring an expert's answer into the work (decision | fact | lesson | proposal | revision); note is the owner's agreement."""
        return t.call(lambda api: api.promote_sme(consultation, target, note, text=text, turn=turn, artifact=artifact,
                                                  from_artifact=from_artifact, feed=feed))

    @tool
    def platform_fact(text: str, source: str = "owner") -> dict[str, Any]:
        """Record a durable platform fact."""
        return t.call(lambda api: api.platform_fact(text, source))

    @tool
    def platform_incident(action: str = "list", incident: str | None = None, fix: str | None = None) -> dict[str, Any]:
        """Platform incidents: list, show, or resolve with the fix (readies the escalated step once)."""
        return t.call(lambda api: api.platform_incident(action, incident, fix))

    @tool
    def note(text: str | None = None, keep_file: str | None = None, note: str | None = None) -> dict[str, Any]:
        """Keep a note the owner asked for, verbatim, in the project's notes file; keep_file (yes | no) with note records their answer to the one-time offer."""
        return t.call(lambda api: api.note(text, keep_file=keep_file, note=note))

    @tool
    def feedback(kind: str, text: str, run: str | None = None, step: str | None = None, gate: str | None = None,
                 informed_owner: bool = False) -> dict[str, Any]:
        """Record process feedback (friction | skipped_step | waste | confusing)."""
        return t.call(lambda api: api.feedback(kind, text, run, step, gate, informed_owner))

    # -- adoption, setup, permissions -------------------------------------------------

    @tool
    def adopt(recipe: str, crosswalk: str | None = None, scope: list[str] | None = None) -> dict[str, Any]:
        """Adopt this project with a vendored recipe: start the adoption run, or show the active one."""
        return t.call(lambda api: api.adopt(recipe, crosswalk=crosswalk, scope=scope or None))

    @tool
    def frame(note: str = "") -> dict[str, Any]:
        """Frame the owner's goal (note = their words, verbatim) into pieces of work they choose from: start the
        framing run, or show the one awaiting its decision."""
        return t.call(lambda api: api.frame(note))

    @tool
    def establish_baseline(adoption: str, note: str) -> dict[str, Any]:
        """Apply the reviewed baseline proposal: the owner's one adoption decision, in their words."""
        return t.call(lambda api: api.establish_baseline(adoption, note))

    @tool
    def vendor(recipe_dir: str, approved: bool = False, note: str | None = None) -> dict[str, Any]:
        """Vendor a recipe package directory into .baton/recipes/ and pin it; changed or reused step ids → needs_owner."""
        return t.call(lambda api: api.vendor(recipe_dir, approved=approved, note=note))

    @tool
    def upgrade(to: str | None = None) -> dict[str, Any]:
        """Pin this runtime's version in baton.lock and re-vendor the skills (another version: run the CLI launcher)."""
        return t.call(lambda api: api.upgrade(to))

    @tool
    def migrate(dry_run: bool = False) -> dict[str, Any]:
        """Bring stored files below the readable format window to the current formats; dry_run changes nothing."""
        return t.call(lambda api: api.migrate(dry_run=dry_run))

    @tool
    def push(approved: bool = False, note: str | None = None) -> dict[str, Any]:
        """Push the current branch under permissions.push; ask → needs_owner: repeat with approved and the owner's words."""
        return t.call(lambda api: api.push(approved=approved, note=note))

    @tool
    def permission(action: str, detail: str | None = None, approved: bool = False, note: str | None = None) -> dict[str, Any]:
        """Check and record an action taken outside the runtime (tag | merge | deploy | force_push): allow, ask or deny."""
        return t.call(lambda api: api.permission(action.replace("-", "_"), detail, approved=approved, note=note))

    return server


def serve_stdio(project: str | Path | None = None, director: str | None = None) -> None:
    build_server(project, director).run("stdio")


# ---------------------------------------------------------------------------
# HTTP (owner-started, loopback only, bearer token)
# ---------------------------------------------------------------------------


def http_token(home: str | Path | None = None) -> str:
    """The bearer token from ``~/.baton/mcp.yaml`` (``token: secret:<name>``). Raises EngineError when absent."""
    from .data import YamlError, load_yaml
    from .profiles import SetupError, resolve_secret
    from .project import machine_home

    path = Path(home) if home else machine_home()
    cfg_file = path / "mcp.yaml"
    if not cfg_file.is_file():
        raise EngineError("configuration.mcp_token", f"MCP over HTTP needs a bearer token: write {cfg_file} with `token: secret:<name>` "
                                                     "and store the secret (BATON_SECRET_<NAME>, the keyring or ~/.baton/secrets/<name>)")
    try:
        cfg = load_yaml(cfg_file) or {}
    except YamlError as e:
        raise EngineError("configuration.mcp_token", f"{cfg_file}: {e}") from e
    ref = cfg.get("token") if isinstance(cfg, dict) else None
    if not isinstance(ref, str) or not ref.startswith("secret:") or len(ref) <= len("secret:"):
        raise EngineError("configuration.mcp_token", f"{cfg_file}: `token` must be a secret reference, `secret:<name>`")
    try:
        token = resolve_secret(ref[len("secret:"):], home=path)
    except SetupError as e:
        raise EngineError("configuration.mcp_token", str(e)) from e
    if len(token) < 16:
        raise EngineError("configuration.mcp_token", "the MCP bearer token must be at least 16 characters")
    return token


def check_loopback(host: str) -> None:
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:  # expected: not an IP address, so not loopback: refused just below
        pass
    raise EngineError("mcp.not_loopback", f"--host {host} is not a loopback address; without TLS the bearer token would cross the network "
                                          "in the clear. Bind 127.0.0.1 and reach it through a TLS proxy or tunnel")


class BearerAuth:
    """ASGI middleware: every HTTP request must carry ``Authorization: Bearer <token>``."""

    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            got = headers.get(b"authorization", b"")
            ok = got.startswith(b"Bearer ") and hmac.compare_digest(got[len(b"Bearer "):].strip(), self.token)
            if not ok:
                body = json.dumps({"error": "unauthorized", "message": "a valid bearer token is required"}).encode("utf-8")
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def http_app(project: str | Path | None, director: str | None, token: str, host: str = "127.0.0.1") -> Any:
    check_loopback(host)
    return BearerAuth(build_server(project, director).streamable_http_app(host=host), token)


def serve_http(project: str | Path | None = None, director: str | None = None, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    check_loopback(host)
    app = http_app(project, director, http_token(), host)
    uvicorn.run(app, host=host, port=port, log_level="warning")
