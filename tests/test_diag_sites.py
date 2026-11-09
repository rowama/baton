"""Every recorded silent path finds its diagnostic (§8.3, change 2026-11-diagnostics, Decision 0094)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from baton import diag
from baton.engine import Api
from baton.project import init
from baton.store import Store, StoreError

from projectkit import make_home
from runkit import Clock, make_recipe

pytestmark = pytest.mark.not_slow("measured under 1 s")


def notes(code: str) -> list[dict[str, Any]]:
    return [r for day in diag._raw_days() for r in diag.read_records(day) if r["code"] == code]


class Boom:
    """A store, log or CAS whose every access fails."""

    def __init__(self, ids: tuple[str, ...] = ("r1",)):
        self.ids = ids

    def run_ids(self) -> list[str]:
        return list(self.ids)

    def run(self, rid: str) -> Any:
        raise StoreError("unreadable")

    def events(self) -> list[Any]:
        raise OSError("unreadable")

    def project_log(self) -> Any:
        return types.SimpleNamespace(events=lambda: [])

    cas = property(lambda self: types.SimpleNamespace(read=lambda sha: (_ for _ in ()).throw(StoreError("no blob"))))


# -- store cache --------------------------------------------------------------------------------------------


def test_cache_replays_say_why(tmp_path: Path) -> None:
    with Store(tmp_path) as s:
        rid = s.start_run({"recipe": "r", "title": "t"}).run_id
        s.run(rid).state()
        assert notes("cache.replay") == []  # a cache that matches the log is not a replay
        s._cache.clear()
        s.run(rid).state()
        s._cache.conn().execute("UPDATE runs SET log_size = 0")
        s._cache.conn().commit()
        s.run(rid).state()
        s._cache.conn().execute("UPDATE meta SET value = 'another-runtime'")
        s._cache.conn().commit()
        s._cache.close()
        s.run(rid).state()
    got = notes("cache.replay")
    assert [r["data"]["reason"] for r in got] == ["missing", "size_mismatch", "key_mismatch"]
    assert got[0]["run"] == rid and got[0]["project"] == str(tmp_path)


# -- routing -------------------------------------------------------------------------------------------------

from test_routing import routed  # noqa: E402,F401


@pytest.mark.slow
def test_worker_selected_carries_excluded_on_every_dispatch(routed) -> None:  # noqa: F811
    api, _root, run = routed
    api.dispatch(run, "draft", "carol")  # alice is strong and eligible too; weak lacks structured_output
    ev = [e for e in api.project.store.run(run).events() if e.type == "worker_selected"][-1]
    excluded = {x["profile"]: x["reasons"] for x in ev.data["excluded"]}
    assert "weak" in excluded and any("structured_output" in r for r in excluded["weak"])
    assert "carol" not in excluded


# -- the swallowed exceptions --------------------------------------------------------------------------------


def test_harness_version_failures_are_noted(tmp_path: Path) -> None:
    from baton.engine import harness_version

    adapter = types.SimpleNamespace(version_argv=lambda exe: [str(tmp_path / "no-such-binary")], parse_version=lambda out: out)
    assert harness_version(str(tmp_path / "missing"), adapter, {}) is None
    assert notes("harness.version_stat_failed")
    assert harness_version(sys.executable, adapter, {}) is None
    assert notes("harness.version_probe_failed")


def test_a_run_that_cannot_be_read_is_noted_where_it_vouches_for_nothing() -> None:
    from baton import permissions, sme

    assert permissions.verified_commits(Path("."), Boom()) == set()
    assert notes("permissions.run_unreadable")[0]["run"] == "r1"
    assert permissions._commit_sha(Boom(), "r2", {"output_sha256": "ab"}) is None
    assert notes("permissions.output_unreadable")[0]["run"] == "r2"
    sme.stats(Boom())
    assert [r["where"] for r in notes("sme.run_unreadable")] == ["sme:stats"]


def test_docs_unreadable_record(tmp_path: Path) -> None:
    from baton import docs

    ctx = types.SimpleNamespace(log=Boom())
    assert docs._cas_json(ctx, "ab" * 32) is None
    assert notes("docs.record_unreadable")


def test_unreadable_markers_are_noted(tmp_path: Path) -> None:
    from baton import supervisor

    d = supervisor.running_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "d_bad.json").write_text("{not json", encoding="utf-8")
    assert supervisor.markers(tmp_path) == []
    assert notes("supervisor.marker_unreadable")[0]["data"]["path"].endswith("d_bad.json")


def test_a_hooks_file_that_does_not_load_is_noted(monkeypatch: pytest.MonkeyPatch) -> None:
    from baton import supervisor

    def bad(project: Any) -> Any:
        raise supervisor.HookConfigError("bad hooks")

    monkeypatch.setattr(supervisor, "load_hooks", bad)
    assert supervisor.wake_path(object()) is None
    assert notes("hooks.config_invalid")


def test_broken_yaml_in_the_owners_files_is_noted(tmp_path: Path) -> None:
    from baton import resources
    from baton.project import MACHINE_PROFILES

    (tmp_path / MACHINE_PROFILES).write_text("a: [unclosed\n", encoding="utf-8")
    assert resources._owner_names(tmp_path) == set()
    assert resources.machine_claims(tmp_path) == {}
    assert [r["where"] for r in notes("resources.yaml_invalid")] == ["resources:_owner_names", "resources:machine_claims"]


def test_a_broken_keyring_is_noted(monkeypatch: pytest.MonkeyPatch) -> None:
    from baton import profiles

    def get_password(service: str, name: str) -> str:
        raise RuntimeError("no backend")

    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_password=get_password))
    assert profiles._keyring_get("tok") is None
    assert notes("profiles.keyring_failed")[0]["data"]["secret"] == "tok"


def test_framing_advice_that_cannot_read_profiles_is_noted() -> None:
    from baton import frame

    def profiles() -> Any:
        raise RuntimeError("bad profiles")

    api = types.SimpleNamespace(project=types.SimpleNamespace(profiles=profiles))
    assert frame._web_advice(api, [], 0) is None
    assert notes("frame.profiles_unreadable")


def test_sme_index_notes_profiles_and_runs_it_cannot_read() -> None:
    from baton import sme

    def profiles() -> Any:
        raise RuntimeError("bad profiles")

    project = types.SimpleNamespace(store=Boom(), profiles=profiles, vendored=lambda: [])
    src = types.SimpleNamespace(project=project, ctx=None)
    sme.index(src, "project", set())
    sme.index(src, "platform", set())
    assert notes("sme.run_unreadable") and notes("sme.profiles_unreadable")


# -- the engine ----------------------------------------------------------------------------------------------

CLI_PROFILES = """\
cli:
  adapter: codex
  vendor: zenith
  executable: no-such-cli-xyz
  path: { search: [nvm] }
  capabilities: [structured_output]
"""


@pytest.fixture
def api(tmp_path: Path):
    recipe = make_recipe(
        tmp_path / "toy",
        [{"id": "a", "requires": {"capabilities": ["structured_output"]}, "output_schema": "schemas/out.json"}],
        schemas={"out.json": {"type": "object"}},
    )
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    home = make_home(tmp_path / "home", CLI_PROFILES)
    a = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    a.vendor(recipe)
    a.run_id = a.start("toy", {"title": "T"})["run_id"]
    yield a
    a.close() if hasattr(a, "close") else None


def test_a_capability_version_check_skipped_for_a_profile_is_noted(api: Api) -> None:
    from baton import capability_states as cs

    cs.record(api.project.home, "cli", "structured_output", "verified", by="observed", evidence="seen", harness_version="1.0")
    api._current_profiles()
    got = notes("capability.version_check_skipped")
    assert got and got[0]["data"]["reason"] == "setup_error" and got[0]["data"]["profile"] == "cli"


def test_known_workers_that_do_not_load_are_noted(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from baton import known_workers

    def bad(vocab: Any) -> Any:
        raise known_workers.KnownWorkersError("bad data")

    monkeypatch.setattr(known_workers, "load", bad)
    assert api._known_workers() is None
    assert notes("known_workers.load_failed")


def test_an_unreadable_tree_record_is_noted(api: Api) -> None:
    from baton import supervisor

    p = supervisor.tree_path(api.project.baton, "d_x")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{broken", encoding="utf-8")
    assert api._reconcile_tree("d_x", {"workspace_mode": "read"}) == []
    assert notes("tool_evidence.tree_unreadable")[0]["data"]["dispatch_id"] == "d_x"


def test_an_unreadable_worker_log_is_noted(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baton import engine

    monkeypatch.setattr(engine, "_last_data", lambda *a, **k: {"tools": {"on": ["web_access"]}})
    child = types.SimpleNamespace(log_path=str(tmp_path / "missing.log"))
    ctx = api._ctx(api.run_id)
    assert api._observe_tools(ctx, "a", 1, "cli", child) == []
    assert notes("tool_evidence.log_unreadable")


def test_a_queued_dispatch_whose_run_is_gone_is_noted(api: Api) -> None:
    api._drop_queued({"run_id": "no-such-run", "step_path": "a", "queue_id": "q1"}, "gone", "x.y", fire=False)
    got = notes("queue.dequeue_run_unreadable")
    assert got and got[0]["run"] == "no-such-run"


def test_resolving_an_incident_whose_run_is_unreadable_is_noted(api: Api) -> None:
    inc = api._open_incident({"run": "no-such-run", "step_path": "a", "attempt": 1, "class": "platform", "code": "x", "message": "m", "worker": "cli"})
    out = api.platform_incident("resolve", inc, fix="fixed it")
    assert out["retried"] == [] if "retried" in out else True
    assert notes("incident.resolve_run_unreadable")[0]["run"] == "no-such-run"


# -- the audit -----------------------------------------------------------------------------------------------


def _silent(h: Any) -> bool:
    """A handler that leaves no trace: it neither re-raises, nor uses the exception, nor calls anything."""
    import ast

    nodes = list(ast.walk(ast.Module(body=h.body, type_ignores=[])))
    if any(isinstance(n, ast.Raise) for n in nodes):
        return False
    if h.name and any(isinstance(n, ast.Name) and n.id == h.name for n in nodes):
        return False
    return not any(isinstance(n, ast.Call) for n in nodes)


def test_every_swallowed_exception_is_noted_or_marked_expected_with_a_reason() -> None:
    import ast

    problems = []
    for path in sorted((Path(__file__).parents[1] / "src" / "baton").rglob("*.py")):
        if path.name == "diag.py":  # the channel cannot note its own failures; it counts them
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for n in ast.walk(ast.parse("\n".join(lines))):
            if isinstance(n, ast.ExceptHandler) and _silent(n):
                m = __import__("re").search(r"# expected: (\S.*)$", lines[n.lineno - 1])
                if not m:
                    problems.append(f"{path.name}:{n.lineno}: swallows {ast.unparse(n.type) if n.type else 'everything'} with no trace")
    assert not problems, "note it with diag.note(...) or say why it is expected (`# expected: <why>`):\n" + "\n".join(problems)
