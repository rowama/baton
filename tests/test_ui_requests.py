"""Interaction requests on the local page (§13.9; Decisions 0169, 0170, 0171).

- A project is known to the machine's one page by its lasting name (``project.name``, else its folder's): kept across
  restarts, taken back by a folder that moved, ``-2`` for a second live project of the same name.
- The request routes call the same functions as ``interactions``, ``interaction`` and ``answer``; an answer is recorded
  with ``via: local_page`` as the owner's own, needing no Director's lease; a changed request is refused as stale.
- Pages and their launch link keep the path; context items are served by id, never with a path on disk.
- ``ui(request)`` gives the Director the request's page, and refuses a request that is not open.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from baton import engine, ui
from baton.project import init, project_name

from test_conversation import fresh, status
from test_interactions import _gate, events
from test_ui import Page


def _project(where: Path, name: str | None = None) -> Path:
    where.mkdir(parents=True)
    init(where, agents_md=False)
    if name is not None:
        f = where / ".baton" / "project.yaml"
        f.write_text(f.read_text(encoding="utf-8").replace(f"name: {json.dumps(where.name)}", f"name: {json.dumps(name)}"), encoding="utf-8")
    return where


# --------------------------------------------------------------------------
# The project's name and the registry
# --------------------------------------------------------------------------


@pytest.mark.not_slow("files only")
def test_init_writes_the_folders_name_and_a_project_without_one_uses_its_folder(tmp_path):
    p = _project(tmp_path / "My Books")
    assert yaml.safe_load((p / ".baton" / "project.yaml").read_text(encoding="utf-8"))["project"] == {"name": "My Books"}
    assert project_name(p) == "my-books"
    _project(tmp_path / "other", name="Household accounts")
    assert project_name(tmp_path / "other") == "household-accounts"
    f = p / ".baton" / "project.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace('project: { name: "My Books" }', "project: {}"), encoding="utf-8")
    assert project_name(p) == "my-books"


@pytest.mark.not_slow("files only")
def test_a_project_keeps_its_name_and_a_second_of_the_same_name_gets_a_suffix(tmp_path):
    home = tmp_path / "home"
    a = _project(tmp_path / "a" / "books")
    b = _project(tmp_path / "b" / "books")
    assert ui.register_project(home, a) == "books"
    assert ui.register_project(home, b) == "books-2"
    assert ui.register_project(home, a) == "books" and ui.register_project(home, b) == "books-2"  # lasting
    assert ui.project_root(home, "books-2") == b.resolve()
    assert oct((home / ui.PROJECTS_FILE).stat().st_mode & 0o777) == "0o600"


@pytest.mark.not_slow("files only")
def test_a_moved_folder_takes_its_name_back_and_a_renamed_project_lets_its_old_name_go(tmp_path):
    home = tmp_path / "home"
    old = _project(tmp_path / "old" / "books")
    assert ui.register_project(home, old) == "books"
    new = tmp_path / "new" / "books"
    new.parent.mkdir()
    old.rename(new)
    assert ui.register_project(home, new) == "books"
    assert ui.project_root(home, "books") == new.resolve()
    f = new / ".baton" / "project.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace('name: "books"', 'name: "ledgers"'), encoding="utf-8")
    assert ui.register_project(home, new) == "ledgers"
    assert "books" not in ui._read_projects(home)


@pytest.mark.not_slow("files only")
def test_an_address_names_a_project_never_a_path(tmp_path):
    home = tmp_path / "home"
    p = _project(tmp_path / "books")
    ui.register_project(home, p)
    with pytest.raises(ui.UiError) as e:
        ui.project_root(home, "..")
    assert e.value.code == "ui.unknown_project"
    import shutil

    shutil.rmtree(p / ".baton")
    with pytest.raises(ui.UiError) as e:
        ui.project_root(home, "books")
    assert e.value.code == "ui.project_gone"


@pytest.mark.not_slow("pure function")
def test_a_request_url_keeps_the_launch_token():
    assert ui.request_url("http://127.0.0.1:47474/?t=abc", "books", "ir_1") == "http://127.0.0.1:47474/p/books/requests/ir_1?t=abc"
    assert ui.request_url("http://127.0.0.1:47474/?t=abc", "books") == "http://127.0.0.1:47474/p/books/requests?t=abc"


# --------------------------------------------------------------------------
# Routes over a real project
# --------------------------------------------------------------------------


@pytest.fixture
def served(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)  # alice@host1 holds the run's lease
    name = ui.register_project(cli.home, project)
    page = Page(cli.home)
    yield cli, project, run, name, page
    page.close()


def test_the_page_lists_reads_and_answers_a_request_as_the_owner(served):
    cli, project, run, name, page = served
    rid = status(cli, run)["pending_decisions"][0]["request_id"]

    r, raw = page.req("GET", "/api/projects")
    assert r.status == 200 and json.loads(raw)["projects"] == [{"name": name, "folder": str(project.resolve()), "gone": False, "open": 1}]
    r, raw = page.req("GET", f"/api/p/{name}/interactions")
    assert [q["id"] for q in json.loads(raw)["requests"]] == [rid]
    r, raw = page.req("GET", f"/api/p/{name}/interactions/{rid}")
    req = json.loads(raw)
    assert r.status == 200 and req["id"] == rid and req["format"] == "baton-interaction/1" and req["project"] == name

    r, raw = page.post(f"/api/p/{name}/interactions/{rid}/answer", {"choice": "approve", "note": "Looks right to me."})
    out = json.loads(raw)
    assert r.status == 200, out
    assert out["via"] == "local_page" and out["request_id"] == rid
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["via"] == "local_page" and dec["data"]["recorded_by"] == "owner" and dec["data"]["note"] == "Looks right to me."
    claims = {e["data"]["director_id"] for e in events(project, run) if e["type"].startswith("lease_") and "director_id" in e["data"]}
    assert claims == {"alice@host1"}  # the page took no lease from the Director

    r, raw = page.post(f"/api/p/{name}/interactions/{rid}/answer", {"choice": "approve"})
    assert r.status == 409 and json.loads(raw)["error"] == "interaction.stale"


def test_without_a_note_the_page_records_its_fixed_phrase_and_bad_answers_are_refused(served):
    cli, project, run, name, page = served
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    r, raw = page.post(f"/api/p/{name}/interactions/{rid}/answer", {"choice": "maybe"})
    assert r.status == 422 and json.loads(raw)["error"] == "answer.invalid"
    r, raw = page.post(f"/api/p/{name}/interactions/{rid}/answer", {"choice": "approve", "artifacts": {"x": "/etc/passwd"}})
    assert r.status == 400 and json.loads(raw)["error"] == "ui.body"  # files come only through the page's own upload
    r, raw = page.post(f"/api/p/{name}/interactions/{rid}/answer", {"choice": "approve"})
    assert r.status == 200
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["note"] == "confirmed in local_page"


def test_request_pages_are_the_shell_and_their_launch_link_keeps_the_path(served):
    cli, project, run, name, page = served
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    r, _ = page.req("GET", f"/p/{name}/requests/{rid}?t={page.server.token}", cookie=False)
    assert r.status == 302 and r.getheader("Location") == f"/p/{name}/requests/{rid}" and "HttpOnly" in r.getheader("Set-Cookie")
    for path in (f"/p/{name}/requests", f"/p/{name}/requests/{rid}"):
        r, raw = page.req("GET", path)
        assert r.status == 200 and b"<title>Baton</title>" in raw
    for path in (f"/p/{name}", f"/p/{name}/requests/{rid}/x", f"/api/p/{name}/interactions"):
        assert page.req("GET", path, cookie=False)[0].status == 401
    assert page.req("GET", "/api/p/nothing/interactions")[0].status == 404


def test_a_context_item_is_served_by_id_without_its_path(served):
    cli, project, run, name, page = served
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    req = json.loads(page.req("GET", f"/api/p/{name}/interactions/{rid}")[1])
    for item in req["context"]:
        r, raw = page.req("GET", f"/api/p/{name}/interactions/{rid}/context/{item['id']}")
        assert r.status == 200 and "path" not in json.loads(raw)
    r, raw = page.req("GET", f"/api/p/{name}/interactions/{rid}/context/..%2f..%2fetc")
    assert r.status == 422 and json.loads(raw)["error"] == "interaction.unknown_item"


def test_the_directors_ui_call_gives_the_requests_page(served, monkeypatch):
    cli, project, run, name, page = served
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    monkeypatch.setattr(ui, "start_detached", lambda home, **kw: {"url": f"http://127.0.0.1:{page.server.port}/?t={page.server.token}",
                                                                 "pid": 1, "started": False})
    api = engine.Api.open(project, director_id="alice@host1", home=cli.home)
    try:
        out = api.ui(True, None, rid)
        assert out["url"] == f"http://127.0.0.1:{page.server.port}/p/{name}/requests/{rid}?t={page.server.token}"
        assert out["requests_url"].endswith(f"/p/{name}/requests?t={page.server.token}") and out["project"] == name
        plain = api.ui(True, None)
        assert plain["url"] == f"http://127.0.0.1:{page.server.port}/?t={page.server.token}"  # the setup page, as before
        with pytest.raises(engine.EngineError) as e:
            api.ui(True, None, "ir_00000000000000000000")
        assert e.value.code == "interaction.stale"
    finally:
        api.close()
