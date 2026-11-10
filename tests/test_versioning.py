"""Phase 15 (§16): versioning: the launcher, `upgrade`, `migrate`, compatibility rules (§14).

Every format is at version 1, so newer runtimes are simulated with synthetic format
versions (``versionkit.synthetic``) and installed runtime versions with copies of this
source tree under another version number (``versionkit.fake_install``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from baton import __version__, launcher, versions
from baton.store import canonical_json, event_sha256

from conftest import FIT_CHECK, ROOT
from projectkit import GOOD_PROFILE, OWNER_PROFILE, VERDICT, FIT_INPUTS, Cli, git, make_git_project, make_home, packet_dir, setup_fit_check, write_result
from runkit import OBJ, make_recipe
from versionkit import baton, fake_install, launcher_env, synthetic


def _start(cli: Cli) -> str:
    return cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]


def _describe(cli: Cli, project: Path, run: str) -> None:
    cli.run("dispatch", run, "describe", "--worker", "owner")
    write_result(packet_dir(project, run, "describe", 1), GOOD_PROFILE)
    assert cli.run("submit", run, "describe")["outcome"] == "passed"


def _assess(cli: Cli, project: Path, run: str) -> dict:
    cli.run("dispatch", run, "assess", "--worker", "owner")
    write_result(packet_dir(project, run, "assess", 1), VERDICT)
    cli.run("submit", run, "assess", expect=4)
    return cli.run("decide", run, "assess", "approve", "--note", "Agreed.")


def _raw_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _files(project: Path) -> dict[str, bytes]:
    """Every file of the project except git internals and the (gitignored) cache."""
    return {p.relative_to(project).as_posix(): p.read_bytes() for p in sorted(project.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(project).parts[:1] and not p.relative_to(project).as_posix().startswith(".baton/cache/")}


def _commit_files(project: Path, rev: str = "HEAD") -> set[str]:
    return set(git(project, "show", "--name-only", "--format=", rev).split())


# ---------------------------------------------------------------------------
# Format versions (§14.2)
# ---------------------------------------------------------------------------


@pytest.mark.not_slow("measured under 1 s")
def test_the_readable_window_is_current_and_previous(monkeypatch):
    assert versions.classify("events", "baton-events/1") == "current"
    assert versions.classify("events", "baton-events/2") == "too_new"
    assert versions.classify("events", "baton-recipe/1") == "unknown"
    synthetic(monkeypatch, events=3)
    assert versions.readable_formats("events") == ("baton-events/2", "baton-events/3")
    assert [versions.classify("events", f"baton-events/{n}") for n in (1, 2, 3, 4)] == ["needs_migration", "readable", "current", "too_new"]
    assert versions.upcast("events", {"format": "baton-events/1", "x": 1}) == {"format": "baton-events/3", "x": 1}
    code, message = versions.format_problem("events", "baton-events/1", "event seq 1")
    assert code == "format.needs_migration" and "`baton migrate`" in message and "--dry-run" in message
    code, message = versions.format_problem("events", "baton-events/4", "event seq 1")
    assert code == "format.too_new" and "launcher" in message


@pytest.mark.slow
def test_an_old_run_continues_under_a_newer_runtime(tmp_path, monkeypatch):
    """A newer runtime reads the previous formats directly; its new events are written in its own."""
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    _describe(cli, project, run)
    synthetic(monkeypatch, events=2, lock=2, recipe=2)  # the next runtime: every format one version newer
    assert cli.run("status", run)["state"] == "active"
    assert _assess(cli, project, run)["run_completed"]
    formats = [e["format"] for e in _raw_events(project / ".baton" / "runs" / run / "events.jsonl")]
    assert formats[0] == "baton-events/1" and formats[-1] == "baton-events/2"
    assert set(formats) == {"baton-events/1", "baton-events/2"}  # one log, two versions (§8.2)
    assert cli.run("check")["ok"]
    assert cli.run("migrate", "--dry-run")["items"] == []  # nothing is below the window


@pytest.mark.slow
def test_an_unreadable_format_is_refused_with_the_migrate_hint_and_migrate_fixes_it(tmp_path, monkeypatch):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    _describe(cli, project, run)
    cli.run("platform-fact", "the runtime host is a laptop")
    log = project / ".baton" / "runs" / run / "events.jsonl"
    original = log.read_bytes()

    synthetic(monkeypatch, events=3, lock=3, recipe=3)  # two versions on: version 1 is out of the window
    refused = cli("status", run, expect=1).payload
    assert "baton migrate" in json.dumps(refused)
    codes = {i["code"] for i in cli("check", expect=1).payload["issues"] if i["severity"] == "error"}
    assert {"events.needs_migration", "lock.needs_migration", "format.needs_migration"} <= codes

    # --dry-run changes nothing.
    before, head = _files(project), git(project, "rev-parse", "HEAD")
    dry = cli.run("migrate", "--dry-run")
    assert dry["dry_run"] and not dry["migrated"]
    assert sorted(i["family"] for i in dry["items"]) == ["events", "events", "lock", "recipe"]  # run log + project log
    assert _files(project) == before and git(project, "rev-parse", "HEAD") == head and git(project, "status", "--porcelain") == ""

    out = cli.run("migrate")
    assert out["migrated"] and out["checkpoint"]["committed"]
    assert out["checkpoint"]["subject"].startswith("baton(migrate): 4 file(s) to current formats")
    assert _commit_files(project) == {
        ".baton/baton.lock", ".baton/recipes/fit-check@3.migrated.json", ".baton/project/events.jsonl",
        f".baton/runs/{run}/events.jsonl", f".baton/runs/{run}/events.migrated-{len(original.splitlines())}.jsonl",
        ".baton/project/events.migrated-2.jsonl",
    }
    # Earlier events are never rewritten: the log only grew, by one `migrated` record.
    assert log.read_bytes().startswith(original)
    last = _raw_events(log)[-1]
    assert last["type"] == "migrated" and last["format"] == "baton-events/3" and last["step_path"] is None
    assert last["data"]["from"] == ["baton-events/1"] and last["data"]["to"] == "baton-events/3"
    assert json.loads((project / ".baton" / "baton.lock").read_text())["format"] == "baton-lock/3"
    proj = _raw_events(project / ".baton" / "project" / "events.jsonl")
    assert {e["data"]["family"] for e in proj if e["type"] == "migrated"} == {"events", "lock", "recipe"}

    # The run reads again and continues; the vendored recipe keeps its pinned hash.
    assert cli.run("status", run)["state"] == "active"
    assert _assess(cli, project, run)["run_completed"]
    assert cli.run("check")["ok"]
    assert cli.run("migrate")["items"] == []

    # A tampered migrated copy is caught.
    copy = project / ".baton" / "runs" / run / f"events.migrated-{len(original.splitlines())}.jsonl"
    copy.write_bytes(copy.read_bytes().replace(b"Contract", b"Kontract"))
    assert "events.migration_mismatch" in {i["code"] for i in cli("check", expect=1).payload["issues"]}


@pytest.mark.slow
def test_a_newer_format_is_refused_naming_the_launcher(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    run = _start(cli)
    log = project / ".baton" / "runs" / run / "events.jsonl"
    last = _raw_events(log)[-1]
    ev = {**last, "format": "baton-events/2", "seq": last["seq"] + 1, "type": "lease_renewed", "prev_sha256": last["sha256"], "data": {}}
    ev.pop("sha256")
    ev["sha256"] = event_sha256(ev)
    with open(log, "a", encoding="utf-8", newline="\n") as f:
        f.write(canonical_json(ev) + "\n")
    issues = cli("check", expect=1).payload["issues"]
    assert any(i["code"] == "events.unknown_format" and "launcher" in i["message"] for i in issues)
    assert cli("migrate", "--dry-run", expect=1).payload["error"] == "migrate.unreadable"
    assert cli("upgrade", expect=1).payload["error"] == "upgrade.unreadable"  # no downgrade below what the project holds


# ---------------------------------------------------------------------------
# Vendoring compares step-id signatures (§5.8, §14.2)
# ---------------------------------------------------------------------------


def _toy(root: Path, version: int, *, check: bool = True, draft_schema: str = "a.json") -> Path:
    steps = [{"id": "draft", "output_schema": f"schemas/{draft_schema}"}]
    if check:
        steps.append({"id": "check", "depends_on": ["draft"], "output_schema": "schemas/a.json"})
    return make_recipe(root, steps, schemas={"a.json": OBJ, "b.json": {"type": "object", "required": ["x"]}}, version=version)


@pytest.mark.slow
def test_vendoring_a_changed_or_reused_step_id_needs_the_owner(tmp_path, monkeypatch):
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project))
    lock_path = project / ".baton" / "baton.lock"

    assert cli.run("vendor", str(_toy(tmp_path / "v1", 1)))["flags"] == []
    assert cli.run("vendor", str(_toy(tmp_path / "v2", 2, check=False)))["flags"] == []  # retiring an id is fine

    # Version 3 brings back the id version 2 retired.
    before = lock_path.read_bytes()
    out = cli.run("vendor", str(_toy(tmp_path / "v3", 3)), expect=4)
    assert out["needs_owner"] and not out["changed"]
    assert out["flags"] == [{"code": "retired_id_reused", "step": "check", "present_in": [1], "retired_in": [2]}]
    assert lock_path.read_bytes() == before and not (project / ".baton" / "recipes" / "toy@3").exists()
    assert cli("vendor", str(tmp_path / "v3"), "--approved", expect=1).payload["error"] == "vendor.note"

    monkeypatch.setenv("BATON_OWNER_EXIT", "0")  # decision 0057: the same refusal exits 0, needs_owner kept
    assert cli.run("vendor", str(tmp_path / "v3"), expect=0)["needs_owner"] is True
    monkeypatch.delenv("BATON_OWNER_EXIT")

    out = cli.run("vendor", str(tmp_path / "v3"), "--approved", "--note", "Reusing check is fine: same role.")
    assert out["changed"] and out["decision_id"]
    decision = next(e for e in _raw_events(project / ".baton" / "project" / "events.jsonl") if e["type"] == "human_decision")
    assert decision["actor"] == "human" and decision["data"]["kind"] == "vendor" and decision["data"]["note"] == "Reusing check is fine: same role."
    entry = json.loads(lock_path.read_text())["recipes"]["toy@3"]
    assert entry["decision"]["decision_id"] == out["decision_id"] and entry["decision"]["flags"][0]["code"] == "retired_id_reused"

    # Version 4 keeps `draft` but changes its output schema.
    out = cli.run("vendor", str(_toy(tmp_path / "v4", 4, draft_schema="b.json")), expect=4)
    assert out["flags"] == [{"code": "signature_changed", "step": "draft", "versions": [1, 2, 3], "changed": ["output_schema_sha256"]}]


# ---------------------------------------------------------------------------
# upgrade (§14.3)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_upgrade_pins_this_runtime_and_revendors_the_skills_only(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    lock_path = project / ".baton" / "baton.lock"
    lock = json.loads(lock_path.read_text())
    lock["runtime"] = "0.0.9"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    skill = project / ".agents" / "skills" / "baton-director" / "SKILL.md"
    skill.write_text("an edited copy\n", encoding="utf-8")
    git(project, "commit", "-qam", "older runtime")

    out = cli.run("upgrade")
    assert (out["previous"], out["runtime"]) == ("0.0.9", __version__)
    assert out["skills"]["replaced"] == [".agents/skills/baton-director/SKILL.md"]
    assert out["checkpoint"]["subject"] == f"baton(project): upgrade runtime 0.0.9 -> {__version__}"
    assert _commit_files(project) == {".baton/baton.lock", ".agents/skills/baton-director/SKILL.md"}
    assert skill.read_bytes() == (ROOT / "skills" / "baton-director" / "SKILL.md").read_bytes()
    assert json.loads(lock_path.read_text())["formats"] == versions.current_formats()
    assert git(project, "status", "--porcelain") == ""
    assert not cli.run("upgrade")["changed"]
    assert cli("upgrade", "--to", "9.9.9", expect=1).payload["error"] == "upgrade.wrong_runtime"


# ---------------------------------------------------------------------------
# The launcher (§14.1)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_the_launcher_picks_the_version_to_run(tmp_path):
    assert launcher.parse_argv(["--project", "p", "--director=d", "status", "r1", "--json"]) == {"project": "p", "command": "status", "to": None}
    assert launcher.parse_argv(["--project=p", "upgrade", "--to", "0.2.0"])["to"] == "0.2.0"
    assert launcher.parse_argv(["upgrade", "--to=0.3.0"])["to"] == "0.3.0"
    assert launcher.parse_argv(["--version"])["command"] is None

    project = make_git_project(tmp_path / "proj")
    Cli(project, make_home(tmp_path / "home")).run("init", str(project))
    lock_path = project / ".baton" / "baton.lock"
    lock = json.loads(lock_path.read_text())
    lock["runtime"] = "0.2.0"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    (project / "sub").mkdir()
    assert launcher.wanted_version(["status", "r1"], {}, project / "sub") == "0.2.0"
    assert launcher.wanted_version(["status", "r1"], {"BATON_PROJECT": str(project)}, tmp_path) == "0.2.0"
    assert launcher.wanted_version(["--project", str(project), "status"], {}, tmp_path) == "0.2.0"
    assert launcher.wanted_version(["status"], {"BATON_VERSION": "0.3.0"}, project) == "0.3.0"
    assert launcher.wanted_version(["upgrade"], {}, project) == __version__
    assert launcher.wanted_version(["upgrade", "--to", "0.3.0"], {}, project) == "0.3.0"
    assert launcher.wanted_version(["init", "."], {}, project) == __version__
    assert launcher.wanted_version(["status"], {}, tmp_path) == __version__  # no project


@pytest.mark.not_slow("measured under 1 s")
def test_launcher_refuses_a_runtime_that_is_not_the_version_it_launched(tmp_path):
    proc = baton(tmp_path, launcher_env(tmp_path / "home", BATON_LAUNCHED="9.9.9"), "--version", expect=1, as_json=False)
    assert "launcher started Baton 9.9.9" in proc.stderr


@pytest.mark.slow
def test_launcher_without_uv_names_the_install_command(tmp_path):
    env = launcher_env(tmp_path / "home", BATON_VERSION="0.2.0", PATH=str(tmp_path / "empty"))
    out = baton(tmp_path, env, "board", expect=1)
    assert out["error"] == "launcher.no_uv" and "https://docs.astral.sh/uv/" in out["message"]


FAKE_UV = """\
import json, os, sys
from pathlib import Path
sys.path.insert(0, {tests!r})
log = Path(os.environ["FAKE_UV_LOG"])
with log.open("a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1] == "venv":
    from versionkit import fake_install
    vdir = Path(sys.argv[-1])
    fake_install(vdir.parent.parent, vdir.name)
"""


@pytest.mark.skipif(os.name == "nt", reason="the fake uv is a script with a shebang")
@pytest.mark.slow
def test_launcher_installs_a_missing_version_with_uv(tmp_path):
    home = make_home(tmp_path / "home")
    (home / "launcher.yaml").write_text("source: 'git+https://example.invalid/baton@v{version}'\nextras: [mcp]\n", encoding="utf-8")
    uv = tmp_path / "bin" / "uv"
    uv.parent.mkdir()
    uv.write_text(f"#!{sys.executable}\n" + FAKE_UV.format(tests=str(ROOT / "tests")), encoding="utf-8")
    uv.chmod(0o755)
    calls = tmp_path / "uv.jsonl"
    env = launcher_env(home, BATON_VERSION="0.4.0", BATON_UV=str(uv), FAKE_UV_LOG=str(calls))
    proc = baton(tmp_path, env, "--version", as_json=False)
    assert proc.stdout.strip() == "0.4.0" and "installing Baton 0.4.0" in proc.stderr
    vdir = home / "versions" / "0.4.0"
    args = [json.loads(line) for line in calls.read_text().splitlines()]
    assert args == [["venv", "--quiet", str(vdir)],
                    ["pip", "install", "--quiet", "--python", str(launcher.python_in(vdir)), "baton[mcp] @ git+https://example.invalid/baton@v0.4.0"]]
    assert launcher.installed(vdir)
    assert baton(tmp_path, env, "--version", as_json=False).stdout.strip() == "0.4.0"
    assert len(calls.read_text().splitlines()) == 2  # installed once


@pytest.mark.skipif(os.environ.get("BATON_LIVE") != "1", reason="live: builds this tree with the real uv (BATON_LIVE=1)")
@pytest.mark.not_slow("measured under 1 s")
def test_launcher_installs_with_the_real_uv(tmp_path):
    """The [VERIFY] for uv: a tagged git repo of this tree at version 0.5.0, installed by the launcher."""
    if shutil.which("uv") is None and not (Path.home() / ".local" / "bin" / "uv").exists():
        pytest.skip("uv is not installed")
    repo = tmp_path / "src-repo"
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "*.egg-info", ".pytest_cache", "Claude outputs"))
    init = repo / "src" / "baton" / "__init__.py"
    init.write_text(init.read_text().replace('__version__ = "0.1.0"', '__version__ = "0.5.0"'))
    make_git_project(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "0.5.0")
    git(repo, "tag", "v0.5.0")
    home = make_home(tmp_path / "home")
    (home / "launcher.yaml").write_text(f"source: 'git+{repo.as_uri()}@v{{version}}'\n", encoding="utf-8")
    env = launcher_env(home, BATON_VERSION="0.5.0", PATH=os.environ["PATH"] + os.pathsep + str(Path.home() / ".local" / "bin"))
    proc = baton(tmp_path, env, "--version", as_json=False)
    assert proc.stdout.strip() == "0.5.0", proc.stderr


# ---------------------------------------------------------------------------
# Two worktrees, two runtimes; the trial workflow (§14.3)
# ---------------------------------------------------------------------------


def _by_hand(cwd: Path, env: dict, run: str, step: str, output: dict, *, expect: int = 0) -> dict:
    d = baton(cwd, env, "dispatch", run, step, "--worker", "owner")
    write_result(Path(d["packet"]), output)
    return baton(cwd, env, "submit", run, step, expect=expect)


@pytest.mark.slow
def test_two_worktrees_run_two_runtime_versions_and_the_trial_merges(tmp_path):
    home = make_home(tmp_path / "home", OWNER_PROFILE)
    fake_install(home, "0.2.0")
    main = make_git_project(tmp_path / "proj")
    env = launcher_env(home)
    baton(main, env, "init", ".")
    baton(main, env, "vendor", str(FIT_CHECK))
    git(main, "add", "-A")
    git(main, "commit", "-qm", "Adopt Baton")

    # main: a run under the pinned 0.1.0, left half done.
    old = baton(main, env, "start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    assert _by_hand(main, env, old, "describe", GOOD_PROFILE)["outcome"] == "passed"

    # The trial worktree (§14.3 steps 1-2): upgrade there runs under 0.2.0.
    trial = tmp_path / "proj-trial"
    git(main, "worktree", "add", "-q", str(trial), "-b", "baton-trial")
    up = baton(trial, env, "upgrade", "--to", "0.2.0")
    assert (up["previous"], up["runtime"]) == (__version__, "0.2.0") and up["checkpoint"]["committed"]
    assert git(trial, "status", "--porcelain") == ""

    # Side by side on one machine: each worktree runs its own pinned version.
    assert baton(main, env, "--version", as_json=False).stdout.strip() == __version__
    assert baton(trial, env, "--version", as_json=False).stdout.strip() == "0.2.0"
    new = baton(trial, env, "start", "fit-check", "--inputs", json.dumps({**FIT_INPUTS, "title": "Trial item"}))["run_id"]
    d_main = baton(main, env, "dispatch", old, "assess", "--worker", "owner")  # interleaved
    assert _by_hand(trial, env, new, "describe", GOOD_PROFILE)["outcome"] == "passed"
    write_result(Path(d_main["packet"]), VERDICT)
    assert baton(main, env, "submit", old, "assess", expect=4)["outcome"] == "needs_human"
    _by_hand(trial, env, new, "assess", VERDICT, expect=4)
    assert baton(trial, env, "decide", new, "assess", "approve", "--note", "Trial looks good.")["run_completed"]

    def runtime(root: Path, run: str) -> str:
        return _raw_events(root / ".baton" / "runs" / run / "events.jsonl")[0]["data"]["runtime"]

    assert runtime(main, old) == __version__ and runtime(trial, new) == "0.2.0"

    # Adopt (§14.3 step 4): the trial branch merges cleanly (the old run's files waiting on the owner
    # are untouched by it); main now runs 0.2.0.
    merged = subprocess.run(["git", "-C", str(main), "merge", "--no-edit", "-q", "baton-trial"], capture_output=True, text=True)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert baton(main, env, "--version", as_json=False).stdout.strip() == "0.2.0"

    # The old run, started under 0.1.0, continues and completes under 0.2.0.
    done = baton(main, env, "decide", old, "assess", "approve", "--note", "Agreed.")
    assert done["run_completed"]
    assert {e["type"] for e in _raw_events(main / ".baton" / "runs" / new / "events.jsonl")} >= {"run_completed"}
    assert baton(main, env, "check")["ok"]
    assert baton(main, env, "board")["runs"] == []
