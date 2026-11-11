"""The local setup page: process, request checks, state, idle exit (§13.9; 0121, 0122)."""

from __future__ import annotations

import http.client
import json
import re
import threading
import time
from pathlib import Path

import pytest

from baton import resources, ui
from baton.resources import Detection

from test_resources import found, run_setup

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    resources.declare(h, "openrouter-main", provider="openrouter", credential="secret:or")
    run_setup(h, found("codex"))
    monkeypatch.setattr(ui, "_discover", found("codex"))
    return h


class Page:
    """A running server and a bare HTTP client: the real wire, with chosen headers."""

    def __init__(self, home: Path, **kw):
        self.server = ui.Server(home, **kw)
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()

    def req(self, method="GET", path="/", *, headers=None, body=None, cookie=True, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.server.port}"}
        if cookie:
            h["Cookie"] = f"{ui.COOKIE}={self.server.token}"
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body)
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r, raw

    def post(self, path, body=None, **kw):
        return self.req("POST", path, headers={"X-Baton-UI": "1"}, body=body if body is not None else {}, **kw)

    def close(self):
        self.server.quit()
        self.thread.join(timeout=10)


@pytest.fixture
def page(home):
    p = Page(home)
    yield p
    p.close()


@pytest.mark.not_slow("loopback requests only")
def test_state_lists_providers_models_and_what_is_connected(page):
    r, raw = page.req("GET", "/api/state")
    out = json.loads(raw)
    assert r.status == 200
    assert out["detected"][0]["provider"] == "claude_code" and "openrouter" in out["directory"]
    row = next(m for m in out["models"] if m["profile"] == "codex")
    assert row["subscription"] is True and "capabilities" in row
    assert "openrouter-main" in out["declared"]


@pytest.mark.not_slow("loopback requests only")
def test_the_launch_link_sets_a_cookie_and_leaves_the_address_bar(page):
    r, _ = page.req("GET", f"/?t={page.server.token}", cookie=False)
    assert r.status == 302 and r.getheader("Location") == "/"
    cookie = r.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    r, raw = page.req("GET", "/")
    assert r.status == 200 and b"Baton setup" in raw


@pytest.mark.not_slow("loopback requests only")
@pytest.mark.parametrize("kw, status, code", [
    ({"cookie": False}, 401, "ui.token"),
    ({"headers": {"Cookie": f"{ui.COOKIE}=wrong"}, "cookie": False}, 401, "ui.token"),
    ({"host": "evil.example:80"}, 403, "ui.host"),
    ({"host": "localhost"}, 403, "ui.host"),
    ({"headers": {"Origin": "http://evil.example"}}, 403, "ui.origin"),
])
def test_requests_that_are_not_the_owners_are_refused(page, kw, status, code):
    r, raw = page.req("GET", "/api/state", **kw)
    assert r.status == status and json.loads(raw)["error"] == code
    assert r.getheader("Access-Control-Allow-Origin") is None


@pytest.mark.not_slow("loopback requests only")
def test_a_wrong_launch_token_is_refused_and_header_token_works(page):
    r, _ = page.req("GET", "/?t=nope", cookie=False)
    assert r.status == 401
    r, _ = page.req("GET", "/api/state", cookie=False, headers={"X-Baton-Token": page.server.token})
    assert r.status == 200


@pytest.mark.not_slow("loopback requests only")
def test_changes_need_the_page_header_and_a_json_body_and_no_cors_is_answered(page):
    r, raw = page.req("POST", "/api/nothing", body={}, headers={})  # no X-Baton-UI
    assert r.status == 400 and json.loads(raw)["error"] == "ui.header"
    r, raw = page.req("POST", "/api/nothing", headers={"X-Baton-UI": "1", "Content-Type": "text/plain"}, body={})
    assert r.status == 400
    r, raw = page.post("/api/nothing")
    assert r.status == 404
    r, _ = page.req("OPTIONS", "/api/state", headers={"Origin": f"http://127.0.0.1:{page.server.port}"})
    assert r.status == 405 and r.getheader("Access-Control-Allow-Origin") is None
    assert "default-src 'self'" in r.getheader("Content-Security-Policy")


@pytest.mark.not_slow("loopback requests only")
def test_only_the_named_front_end_files_are_reachable(page):
    for path in ("/../../etc/passwd", "/%2e%2e/secret", "/workers.yaml", "/ui.json"):
        r, _ = page.req("GET", path)
        assert r.status == 404
    for path in ("/", "/app.js", "/app.css"):
        assert page.req("GET", path)[0].status == 200


@pytest.mark.not_slow("loopback requests only")
def test_the_api_works_without_front_end_files(home, tmp_path):
    p = Page(home, assets=tmp_path / "empty")
    try:
        assert p.req("GET", "/api/state")[0].status == 200
        r, raw = p.req("GET", "/")
        assert r.status == 404 and json.loads(raw)["error"] == "ui.no_front_end"
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_quit_ends_the_process_and_leaves_no_registration(home):
    p = Page(home)
    for _ in range(100):
        if (home / ui.UI_FILE).exists() and (home / ui.UI_FILE).stat().st_size:
            break
        time.sleep(0.05)
    assert json.loads((home / ui.UI_FILE).read_text(encoding="utf-8"))["port"] == p.server.port
    r, raw = p.post("/api/quit")
    assert r.status == 200
    p.thread.join(timeout=10)
    assert not p.thread.is_alive() and not (home / ui.UI_FILE).exists()


@pytest.mark.not_slow("idle timeout of a fraction of a second")
def test_the_page_closes_itself_after_the_idle_timeout(home):
    server = ui.Server(home, idle_timeout=0.4)
    t0 = time.monotonic()
    assert server.serve() == "idle"
    assert time.monotonic() - t0 < 10 and not (home / ui.UI_FILE).exists()
    with pytest.raises(OSError):
        http.client.HTTPConnection("127.0.0.1", server.port, timeout=1).request("GET", "/")


@pytest.mark.not_slow("loopback requests only")
def test_a_request_keeps_the_page_open(home):
    p = Page(home, idle_timeout=2.0)
    try:
        for _ in range(6):
            time.sleep(0.5)
            assert p.req("GET", "/api/state")[0].status == 200
        assert p.thread.is_alive()
    finally:
        p.close()


@pytest.mark.not_slow("loopback requests only")
def test_the_registration_file_is_private_and_binds_loopback_only(home):
    p = Page(home)
    try:
        time.sleep(0.3)
        path = home / ui.UI_FILE
        assert (path.stat().st_mode & 0o077) == 0 or __import__("os").name != "posix"
        assert p.server.httpd.server_address[0] == "127.0.0.1"
        assert ui.running(home)["url"] == p.server.launch.url
    finally:
        p.close()


@pytest.mark.not_slow("reads source files")
def test_no_runtime_module_imports_the_page_and_the_front_end_ships_as_data():
    importers = []
    for f in sorted((ROOT / "src" / "baton").glob("*.py")):
        if f.name == "ui.py":
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.search(r"^\s*(from \. import .*\bui\b|from \.ui import|import baton\.ui|from baton import .*\bui\b)", line):
                importers.append((f.name, line.startswith(" ")))
    # Only the two entry points (the CLI command, the Director's call) import it, and only inside a function.
    assert {n for n, _ in importers} <= {"cli.py", "engine.py"} and all(inside for _, inside in importers)
    assert '"ui" = "baton/_data/ui"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and "style=" not in html  # the CSP allows neither


@pytest.mark.slow
def test_a_director_can_start_it_detached_and_gets_the_same_page_back(home):
    out = ui.start_detached(home, idle_timeout=60)
    try:
        assert out["started"] and out["url"].startswith("http://127.0.0.1:") and "?t=" in out["url"]
        again = ui.start_detached(home, idle_timeout=60)
        assert not again["started"] and again["url"] == out["url"]
    finally:
        import os
        import signal

        os.kill(out["pid"], signal.SIGTERM) if os.name == "posix" else None


@pytest.mark.not_slow("pure function")
@pytest.mark.parametrize("system, where", [("windows", "PowerShell"), ("macos", "Terminal"), ("linux", "terminal"), ("wsl", "WSL")])
def test_each_harness_gets_the_step_for_this_platform(system, where):
    ready = ui.harness_step({"provider": "codex", "found": True, "usable": True}, system)
    login = ui.harness_step({"provider": "claude_code", "found": True, "usable": False}, system)
    install = ui.harness_step({"provider": "codex", "found": False, "usable": False}, system)
    assert ready == {"kind": "ready"}
    assert login["kind"] == "login" and login["command"] == "claude auth login" and where in login["text"]
    assert install["kind"] == "install" and install["command"].startswith("npm install -g ") and where in install["text"]
    assert ui.harness_step({"provider": "unknown_cli", "found": False, "usable": False}, system) == {"kind": "ready"}


@pytest.mark.not_slow("loopback requests only")
def test_the_state_carries_the_steps_and_a_return_to_the_page_rechecks(home, monkeypatch):  # noqa: F811
    p = Page(home)
    try:
        state = json.loads(p.req("GET", "/api/state")[1])
        assert {d["provider"]: d["step"]["kind"] for d in state["detected"]} == {"claude_code": "install", "codex": "ready"}
        # The owner installs and logs in elsewhere, comes back: the next read finds it (nothing is cached).
        monkeypatch.setattr(ui, "_discover", found("codex", "claude_code"))
        again = json.loads(p.req("GET", "/api/state")[1])
        assert {d["provider"]: d["step"]["kind"] for d in again["detected"]} == {"claude_code": "ready", "codex": "ready"}
    finally:
        p.close()
    assert "visibilitychange" in (ROOT / "ui" / "app.js").read_text(encoding="utf-8")


@pytest.mark.not_slow("reads source files")
def test_the_director_is_told_to_use_the_page_not_to_take_a_key():
    skill = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    assert "Never take a key in conversation" in skill and "Call `ui`" in skill
    design = (ROOT / "docs" / "design" / "director-interface.md").read_text(encoding="utf-8")
    assert "Call `ui` and give them the link" in design


def test_stop_ends_the_registered_page_and_clears_its_file(tmp_path, monkeypatch):
    import json
    import os
    import signal

    from baton import ui

    (tmp_path / ui.UI_FILE).write_text(json.dumps({"pid": os.getpid(), "url": "http://127.0.0.1:1/"}))
    sent = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)) if sig == signal.SIGTERM else None)
    monkeypatch.setattr("baton.supervisor.pid_alive", lambda pid: True)
    assert ui.stop(tmp_path)["stopped"] is True
    assert sent == [(os.getpid(), signal.SIGTERM)] and not (tmp_path / ui.UI_FILE).exists()
    assert ui.stop(tmp_path)["stopped"] is False
