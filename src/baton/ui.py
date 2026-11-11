"""The optional local setup page (§13.9; Decisions 0121, 0122, 0125).

``baton ui`` serves a small JSON API and a static front end on a free port of
``127.0.0.1`` and exits after an idle timeout. It is a client over the one core:
every route calls the function the matching CLI command calls, and nothing here
holds state of its own. No runtime module imports this one.

Every request is checked for: the per-launch token (cookie or header, constant
time), the ``Host`` header (DNS rebinding), a same-origin ``Origin`` and, for
state changes, the ``X-Baton-UI`` header and a JSON body. No CORS header is ever
sent. A stored key is never in a response: responses are built from
``workers status``, which holds secret references only.
"""

from __future__ import annotations

import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from . import accounts
from . import prefs as prefs_mod
from . import data as data_mod
from . import diag

COOKIE = "baton_ui"
DEFAULT_IDLE = 900.0
UI_FILE = "ui.json"
#: The files the front end may serve, by URL path: nothing else on disk is ever reachable.
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
MAX_BODY = 64 * 1024


class UiError(Exception):
    """A refusal the page shows: an HTTP status, a code and a message in plain words."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


#: Tests replace discovery (it runs the harness CLIs); the page otherwise uses the real one.
_discover: Callable[..., Any] | None = None

Route = Callable[[Path, dict[str, Any], dict[str, str]], Any]


def assets_dir() -> Path | None:
    """The front-end files, or None when this install has none (the API still works)."""
    d = data_mod.path("ui")
    return d if (d / "index.html").is_file() else None


# --------------------------------------------------------------------------
# Routes: each calls the core function the CLI calls
# --------------------------------------------------------------------------


def _state(home: Path, _body: dict[str, Any], _args: dict[str, str]) -> Any:
    from . import known_workers as kw
    from . import resources, vocab

    try:
        out = resources.status(home) if _discover is None else resources.status(home, discover_fn=_discover)
        known = kw.load(vocab.load(vocab.DEFAULT))
    except Exception as e:  # noqa: BLE001 - the page shows the problem in words instead of a stack trace
        from .known_workers import KnownWorkersError
        from .resources import ResourcesError

        if isinstance(e, (ResourcesError, KnownWorkersError)):
            raise UiError(HTTPStatus.CONFLICT, "configuration.resources", str(e)) from e
        raise
    for d in out["detected"]:
        d["step"] = harness_step(d)
    out["models"] = _models(home, out)
    out["preferences"] = _prefs_core(lambda: prefs_mod.as_dict(prefs_mod.load(home)))
    for m in out["models"]:
        m["enabled"] = m["profile"] not in out["preferences"]["exclude"]
    out["accounts"] = {n: accounts.account_info(home, n) for n in out["declared"]}
    out["directory"] = {n: {"kind": p.kind, "display_name": p.display_name or n, "signup_url": p.signup_url, "base_url": p.base_url}
                        for n, p in sorted(known.providers.items()) if p.kind != "harness"}
    return out


def _models(home: Path, status: dict[str, Any]) -> list[dict[str, Any]]:
    """Every generated profile as one row: what the page's table shows (read from the files; no secrets are in them)."""
    from . import resources

    rows = []
    for name, (_path, body) in sorted(resources.read_generated_dir(home).items()):
        if not isinstance(body, dict):
            continue
        g = status["generated"].get(name, {})
        price = body.get("price") if isinstance(body.get("price"), dict) else None
        rows.append({
            "profile": name, "provider": body.get("provider"), "resource": body.get("resource"), "creator": body.get("creator"),
            "model_id": body.get("model_id"), "tier": body.get("tier"), "context_tokens": body.get("context_tokens"),
            "price": ({"free": bool(price.get("free")), "input": price.get("input"), "output": price.get("output")} if price else None),
            "subscription": (body.get("auth") or {}).get("mode") == "cli_login",
            "capabilities": g.get("capabilities", {}), "verified": g.get("verified"), "flag": g.get("flag"), "ownership": g.get("ownership"),
        })
    return rows


#: A harness's exact steps (Decision 0123 leaves starting a login to the owner, 2026-11-10). The install commands are the
#: tools' npm packages and are not run by Baton. [VERIFY against each tool's current install page before relying on one.]
HARNESS_STEPS = {
    "claude_code": {"name": "Claude Code", "install": "npm install -g @anthropic-ai/claude-code", "login": "claude auth login",
                    "docs": "https://docs.claude.com/en/docs/claude-code/setup"},
    "codex": {"name": "Codex", "install": "npm install -g @openai/codex", "login": "codex login", "docs": "https://github.com/openai/codex"},
}


def platform_name() -> str:
    import platform

    if os.name == "nt":
        return "windows"
    if "microsoft" in platform.uname().release.lower():
        return "wsl"
    return "macos" if sys.platform == "darwin" else "linux"


def harness_step(det: dict[str, Any], system: str | None = None) -> dict[str, Any]:
    """What the owner does next for one detected harness: nothing, log in, or install (the page shows the command with a copy button)."""
    system = system or platform_name()
    info = HARNESS_STEPS.get(det.get("provider", ""))
    where = {"windows": "Open PowerShell", "macos": "Open Terminal", "linux": "Open a terminal", "wsl": "Open your Linux (WSL) terminal"}[system]
    if det.get("usable") or info is None:
        return {"kind": "ready"}
    if det.get("found"):
        return {"kind": "login", "command": info["login"], "text": f"{where} and run this, then sign in with your {info['name']} account:"}
    return {"kind": "install", "command": info["install"], "docs": info["docs"], "needs": "Node.js",
            "text": f"{where} and run this (it needs Node.js), then come back and sign in:"}


def _text(body: dict[str, Any], field: str, *, required: bool = True) -> str | None:
    v = body.get(field)
    if v is None or v == "":
        if required:
            raise UiError(HTTPStatus.BAD_REQUEST, "ui.body", f"{field} is missing")
        return None
    if not isinstance(v, str):
        raise UiError(HTTPStatus.BAD_REQUEST, "ui.body", f"{field} must be text")
    return v


def _core(fn: Callable[[], Any]) -> Any:
    """Run a core function; its plain-words refusals become the page's."""
    from .known_workers import KnownWorkersError
    from .resources import ResourcesError

    try:
        return fn()
    except accounts.AccountError as e:
        raise UiError(HTTPStatus.UNPROCESSABLE_ENTITY, e.code, e.message) from e
    except (ResourcesError, KnownWorkersError) as e:
        raise UiError(HTTPStatus.CONFLICT, "configuration.resources", str(e)) from e


def _connect(home: Path, body: dict[str, Any], _args: dict[str, str]) -> Any:
    """``baton workers connect``: the key is read here and goes only to the check and the store."""
    return _core(lambda: accounts.connect(home, _text(body, "provider") or "", _text(body, "key", required=False),
                                          name=_text(body, "name", required=False), base_url=_text(body, "base_url", required=False)))


def _replace_key(home: Path, body: dict[str, Any], args: dict[str, str]) -> Any:
    from . import resources

    def run() -> Any:
        _d, _s, res = resources._inputs(home)
        r = res.workers().get(args["name"])
        if r is None:
            raise accounts.AccountError("accounts.unknown", f"no account named {args['name']!r}")
        return accounts.connect(home, r.provider, _text(body, "key"), name=args["name"])

    return _core(run)


def _disconnect(home: Path, body: dict[str, Any], args: dict[str, str]) -> Any:
    return _core(lambda: accounts.disconnect(home, args["name"], forget_key=body.get("forget_key") is True))


def _prefs_core(fn: Callable[[], Any]) -> Any:
    from . import prefs
    from .routing import PreferencesError

    try:
        return fn()
    except PreferencesError as e:
        raise UiError(HTTPStatus.UNPROCESSABLE_ENTITY, "configuration.preferences", str(e)) from e


def _get_prefs(home: Path, _body: dict[str, Any], _args: dict[str, str]) -> Any:
    from . import prefs

    return _prefs_core(lambda: prefs.as_dict(prefs.load(home)))


def _put_prefs(home: Path, body: dict[str, Any], _args: dict[str, str]) -> Any:
    """``baton workers prefs``: cheapest or most-verified first, and per-capability preferred models."""
    from . import prefs

    cheapest = body.get("cheapest_first")
    if cheapest is not None and not isinstance(cheapest, bool):
        raise UiError(HTTPStatus.BAD_REQUEST, "ui.body", "cheapest_first must be true or false")
    by_cap = body.get("prefer_by_capability") or {}
    if not isinstance(by_cap, dict) or not all(isinstance(v, list) and all(isinstance(n, str) for n in v) for v in by_cap.values()):
        raise UiError(HTTPStatus.BAD_REQUEST, "ui.body", "prefer_by_capability maps a capability to a list of workers")
    return _prefs_core(lambda: prefs.update(home, cheapest_first=cheapest, prefer=by_cap or None))


def _set_enabled(home: Path, body: dict[str, Any], args: dict[str, str]) -> Any:
    """``baton workers prefs --exclude|--include``: one model on or off for routing."""
    from . import prefs

    on = body.get("enabled")
    if not isinstance(on, bool):
        raise UiError(HTTPStatus.BAD_REQUEST, "ui.body", "enabled must be true or false")
    name = args["profile"]
    return _prefs_core(lambda: prefs.update(home, **({"include": [name]} if on else {"exclude": [name]})))


def _verify(home: Path, _body: dict[str, Any], args: dict[str, str]) -> Any:
    """``baton workers setup --verify <profile>``: the one live check."""
    from . import resources

    out = _core(lambda: resources.setup(home, verify=[args["profile"]]))
    return {"verified": out["verified"], "failed": out["failed"]}


def _quit(_home: Path, _body: dict[str, Any], _args: dict[str, str]) -> Any:
    raise _Quit


class _Quit(Exception):
    pass


#: (method, path) -> route. Later slices add the account, model and preference routes.
ROUTES: dict[tuple[str, str], Route] = {
    ("GET", "/api/state"): _state,
    ("POST", "/api/accounts"): _connect,
    ("POST", "/api/accounts/<name>/key"): _replace_key,
    ("DELETE", "/api/accounts/<name>"): _disconnect,
    ("GET", "/api/preferences"): _get_prefs,
    ("PUT", "/api/preferences"): _put_prefs,
    ("POST", "/api/models/<profile>/enabled"): _set_enabled,
    ("POST", "/api/models/<profile>/verify"): _verify,
    ("POST", "/api/quit"): _quit,
}


# --------------------------------------------------------------------------
# The server
# --------------------------------------------------------------------------


@dataclass
class Launch:
    url: str
    port: int
    token: str


class Server:
    """One launch: a token, a loopback socket and an idle clock."""

    def __init__(self, home: Path, *, port: int = 0, idle_timeout: float = DEFAULT_IDLE, assets: Path | None = None,
                 routes: dict[tuple[str, str], Route] | None = None) -> None:
        self.home = Path(home)
        self.token = secrets.token_urlsafe(32)
        self.idle_timeout = idle_timeout
        self.assets = assets if assets is not None else assets_dir()
        self.routes = routes if routes is not None else ROUTES
        self.last_request = time.monotonic()
        self._lock = threading.Lock()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.launch = Launch(url=f"http://127.0.0.1:{self.port}/?t={self.token}", port=self.port, token=self.token)

    # -- lifecycle ---------------------------------------------------------

    def touch(self) -> None:
        with self._lock:
            self.last_request = time.monotonic()

    def idle_for(self) -> float:
        with self._lock:
            return time.monotonic() - self.last_request

    def serve(self, *, announce: Callable[[Launch], None] | None = None) -> str:
        """Serve until the owner quits or the idle timeout passes; return which. Leaves nothing behind."""
        why = {"v": "quit"}
        stop = threading.Event()

        def watch() -> None:
            while not stop.wait(min(0.2, max(self.idle_timeout / 4, 0.02))):
                if self.idle_for() >= self.idle_timeout:
                    why["v"] = "idle"
                    self.httpd.shutdown()
                    return

        self.write_registration()
        t = threading.Thread(target=watch, daemon=True)
        t.start()
        try:
            if announce:
                announce(self.launch)
            self.httpd.serve_forever(poll_interval=0.1)
        finally:
            stop.set()
            self.httpd.server_close()
            self.remove_registration()
        return why["v"]

    def quit(self) -> None:
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    def write_registration(self) -> None:
        path = self.home / UI_FILE
        self.home.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"url": self.launch.url, "port": self.port, "pid": os.getpid(), "started": time.time()})
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)

    def remove_registration(self) -> None:
        try:
            doc = json.loads((self.home / UI_FILE).read_text(encoding="utf-8"))
            if doc.get("pid") == os.getpid():
                (self.home / UI_FILE).unlink()
        except (OSError, ValueError):  # expected: already gone or unreadable: nothing of ours to remove
            pass

    # -- requests ----------------------------------------------------------

    def _handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "baton-ui"
            sys_version = ""

            def log_message(self, *a: Any) -> None:  # request lines and bodies are never logged (a key may be in one)
                return

            def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload: Any, extra: dict[str, str] | None = None) -> None:
                self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"), "application/json", extra)

            def _refuse(self, status: int, code: str, message: str) -> None:
                self._json(status, {"ok": False, "error": code, "message": message})

            def _allowed_hosts(self) -> set[str]:
                return {f"127.0.0.1:{server.port}", f"localhost:{server.port}"}

            def _token_ok(self) -> bool:
                cookie = ""
                for part in (self.headers.get("Cookie") or "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == COOKIE:
                        cookie = v
                given = self.headers.get("X-Baton-Token") or cookie
                return bool(given) and secrets.compare_digest(given.encode(), server.token.encode())

            def _handle(self, method: str) -> None:
                if (self.headers.get("Host") or "").lower() not in self._allowed_hosts():
                    return self._refuse(HTTPStatus.FORBIDDEN, "ui.host", "This page only answers on its own local address.")
                origin = self.headers.get("Origin")
                if origin is not None and origin.lower() not in {f"http://{h}" for h in self._allowed_hosts()}:
                    return self._refuse(HTTPStatus.FORBIDDEN, "ui.origin", "Requests from other pages are refused.")
                if method == "OPTIONS":
                    return self._refuse(HTTPStatus.METHOD_NOT_ALLOWED, "ui.method", "No cross-origin access.")
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                if method == "GET" and url.path == "/" and "t" in query:
                    if not secrets.compare_digest(query["t"][0].encode(), server.token.encode()):
                        return self._refuse(HTTPStatus.UNAUTHORIZED, "ui.token", "That link is not valid. Start the page again.")
                    server.touch()
                    return self._send(HTTPStatus.FOUND, b"", "text/plain", {
                        "Location": "/", "Set-Cookie": f"{COOKIE}={server.token}; HttpOnly; SameSite=Strict; Path=/"})
                if not self._token_ok():
                    return self._refuse(HTTPStatus.UNAUTHORIZED, "ui.token", "Open the page with the link Baton gave you.")
                server.touch()
                if method != "GET":
                    if self.headers.get("X-Baton-UI") != "1" or "application/json" not in (self.headers.get("Content-Type") or ""):
                        return self._refuse(HTTPStatus.BAD_REQUEST, "ui.header", "Changes must come from the page itself.")
                if method == "GET" and url.path in STATIC:
                    return self._static(url.path)
                return self._route(method, url.path)

            def _static(self, path: str) -> None:
                name, ctype = STATIC[path]
                if server.assets is None or not (server.assets / name).is_file():
                    return self._refuse(HTTPStatus.NOT_FOUND, "ui.no_front_end", "This install has no page files; the API still works.")
                self._send(HTTPStatus.OK, (server.assets / name).read_bytes(), ctype)

            def _route(self, method: str, path: str) -> None:
                route, args = None, {}
                for (m, pattern), fn in server.routes.items():
                    if m != method:
                        continue
                    got = _match(pattern, path)
                    if got is not None:
                        route, args = fn, got
                        break
                if route is None:
                    return self._refuse(HTTPStatus.NOT_FOUND, "ui.not_found", "No such page action.")
                body: dict[str, Any] = {}
                if method != "GET":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > MAX_BODY:
                        return self._refuse(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "ui.too_large", "That request is too large.")
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                        if not isinstance(body, dict):
                            raise ValueError
                    except ValueError:
                        return self._refuse(HTTPStatus.BAD_REQUEST, "ui.body", "The request body must be a JSON object.")
                try:
                    out = route(server.home, body, args)
                except _Quit:
                    self._json(HTTPStatus.OK, {"ok": True, "quit": True})
                    return server.quit()
                except UiError as e:
                    return self._refuse(e.status, e.code, e.message)
                except Exception as e:  # noqa: BLE001 - a bug in a route must not reveal request contents or stop the page
                    diag.note("ui.route_failed", "ui:_route", error=type(e).__name__, route=f"{method} {path}")
                    return self._refuse(HTTPStatus.INTERNAL_SERVER_ERROR, "ui.failed", "Something went wrong; see `baton diag`.")
                self._json(HTTPStatus.OK, out)

            def do_GET(self) -> None:  # noqa: N802
                self._handle("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._handle("POST")

            def do_PUT(self) -> None:  # noqa: N802
                self._handle("PUT")

            def do_DELETE(self) -> None:  # noqa: N802
                self._handle("DELETE")

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._handle("OPTIONS")

        return Handler


def _match(pattern: str, path: str) -> dict[str, str] | None:
    """``/api/accounts/<name>/key`` against a path: the ``<x>`` segments are captured."""
    a, b = pattern.strip("/").split("/"), path.strip("/").split("/")
    if len(a) != len(b):
        return None
    out: dict[str, str] = {}
    for p, s in zip(a, b):
        if p.startswith("<") and p.endswith(">"):
            if not s:
                return None
            out[p[1:-1]] = s
        elif p != s:
            return None
    return out


# --------------------------------------------------------------------------
# Starting it: in the foreground (the CLI) or detached (the Director's action)
# --------------------------------------------------------------------------


def running(home: Path) -> dict[str, Any] | None:
    """The page this machine is already serving, from ``ui.json``, if its process is alive."""
    from .supervisor import pid_alive

    try:
        doc = json.loads((Path(home) / UI_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: no page is running
        return None
    return doc if isinstance(doc, dict) and pid_alive(doc.get("pid")) else None


def open_browser(url: str) -> bool:
    """Open the owner's browser; under WSL ask the Windows side to (its browser is the owner's)."""
    import platform
    import shutil
    import webbrowser

    if "microsoft" in platform.uname().release.lower() and os.name == "posix":
        # explorer.exe is not tried: given a link it can open a File Explorer window instead of the default browser.
        for exe in ("wslview", "powershell.exe", "cmd.exe"):
            found = shutil.which(exe)
            if found:
                argv = {"wslview": [found, url],
                        "powershell.exe": [found, "-NoProfile", "-Command", f"Start-Process '{url}'"]}.get(
                    exe, [found, "/c", "start", "", url.replace("&", "^&")])
                try:
                    subprocess.run(argv, capture_output=True, timeout=15, check=False)
                    return True
                except (OSError, subprocess.SubprocessError):  # expected: try the next opener
                    continue
    try:
        return bool(webbrowser.open(url))
    except webbrowser.Error:  # expected: no browser here; the owner gets the link in words
        return False


def stop(home: Path) -> dict[str, Any]:
    """Close the page this machine is serving (``baton ui --stop``): ends its process and clears ``ui.json``."""
    import signal

    live = running(home)
    if not live:
        return {"stopped": False, "reason": "no setup page is running"}
    try:
        os.kill(int(live["pid"]), signal.SIGTERM)
    except OSError:  # expected: it ended on its own between the check and the signal
        pass
    try:
        (Path(home) / UI_FILE).unlink()
    except OSError:  # expected: the page already removed its own file
        pass
    return {"stopped": True, "pid": live["pid"]}


def start_detached(home: Path, *, idle_timeout: float = DEFAULT_IDLE, wait: float = 15.0) -> dict[str, Any]:
    """The Director's ``ui``: the running page, or one started detached; returns its URL (§13.9)."""
    from .supervisor import _detached

    home = Path(home)
    live = running(home)
    if live:
        return {"url": live["url"], "pid": live["pid"], "started": False, "idle_timeout": None}
    argv = [sys.executable, "-m", "baton", "ui", "--no-open", "--idle-timeout", str(idle_timeout)]
    env = {**os.environ, "BATON_HOME": str(home)}
    proc = _detached(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        live = running(home)
        if live:
            return {"url": live["url"], "pid": live["pid"], "started": True, "idle_timeout": idle_timeout}
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    raise RuntimeError("the setup page did not start; run `baton ui` in a terminal to see why")
