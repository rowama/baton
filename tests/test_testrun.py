"""tools/testrun.py quick: what the quick gate selects, and its fallbacks (§17.1; change 2026-11-fast-tests)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import testrun  # noqa: E402
from projectkit import git, make_git_project  # noqa: E402


def test_python_changes_are_selected_by_testmon():
    p = testrun.plan(["src/baton/redact.py", "tests/test_state.py"], have_data=True, have_base=True)
    assert p.mode == "affected" and not p.docs_test
    (cmd,) = p.commands()
    assert "--testmon-forceselect" in cmd and cmd[cmd.index("-m", 2) + 1] == "not slow"


def test_no_testmon_data_runs_every_quick_test():
    p = testrun.plan(["src/baton/redact.py"], have_data=False, have_base=True)
    assert p.mode == "all" and "--testmon-noselect" in p.commands()[0] and "not slow" in p.commands()[0]


def test_no_recorded_base_runs_every_quick_test():
    assert testrun.plan(["src/baton/redact.py"], have_data=True, have_base=False).mode == "all"


@pytest.mark.parametrize("path", ["defaults/known-workers.yaml", "vocab/capabilities.yaml", "pyproject.toml",
                                  "builtin/x/recipe.yaml", "tests/fakes/fake.sh", "README.md", "AGENTS.md"])
def test_a_changed_non_python_file_outside_docs_runs_every_quick_test(path):
    p = testrun.plan(["docs/README.md", "src/baton/redact.py", path], have_data=True, have_base=True)
    assert p.mode == "all" and path in p.reason


def test_a_docs_only_change_runs_the_docs_test_alone():
    p = testrun.plan(["docs/design/testing.md", "docs/changes/REGISTER.md"], have_data=True, have_base=True)
    assert p.mode == "docs"
    (cmd,) = p.commands()
    assert cmd[-1] == "tests/test_docs.py" and "--testmon-forceselect" not in cmd


def test_docs_beside_python_changes_add_the_docs_test():
    p = testrun.plan(["docs/design/testing.md", "src/baton/redact.py"], have_data=True, have_base=True)
    assert p.mode == "affected" and p.docs_test
    assert [c[-1] for c in p.commands()][-1] == "tests/test_docs.py" and len(p.commands()) == 2


def test_changed_files_see_commits_since_the_base_the_working_tree_and_untracked_files(tmp_path):
    root = make_git_project(tmp_path / "r")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "one")
    assert testrun.read_base(root) is None
    testrun.write_base(root)
    base = testrun.read_base(root)
    assert base and testrun.changed_files(root, base) == []
    (root / "b.txt").write_text("changed\n", encoding="utf-8")  # a non-.py change, committed after the base
    git(root, "commit", "-qam", "two")
    (root / "a.py").write_text("x = 2\n", encoding="utf-8")  # unstaged
    (root / "docs").mkdir()
    (root / "docs" / "n.md").write_text("n\n", encoding="utf-8")  # untracked
    assert testrun.changed_files(root, base) == ["a.py", "b.txt", "docs/n.md"]
    p = testrun.plan(testrun.changed_files(root, base), have_data=True, have_base=True)
    assert p.mode == "all" and "b.txt" in p.reason  # the committed non-.py change is not forgotten


def test_a_recorded_base_that_no_longer_exists_is_ignored(tmp_path):
    root = make_git_project(tmp_path / "r")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "one")
    testrun._base_file(root).write_text("0" * 40 + "\n", encoding="utf-8")
    assert testrun.read_base(root) is None


def test_dry_run_prints_the_plan_and_runs_nothing(tmp_path, capsys):
    root = make_git_project(tmp_path / "r")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "one")
    assert testrun.quick(root, dry_run=True) == 0
    out = capsys.readouterr().out
    assert "quick gate: all (no testmon data yet)" in out and "--testmon-noselect" in out
    assert testrun.read_base(root) is None  # a dry run records nothing


# --- the ledger and the background full run -------------------------------------------------------------------

import os  # noqa: E402
import shutil  # noqa: E402

FAKES = Path(__file__).parent / "fakes"


def fixture_repo(tmp_path, body="def test_ok():\n    assert True\n", extra=None):
    root = make_git_project(tmp_path / "fx")
    (root / "tests").mkdir()
    (root / "tests" / "test_fx.py").write_text(body, encoding="utf-8")
    for name, src in (extra or {}).items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest) if isinstance(src, Path) else dest.write_text(src, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fx")
    return root, git(root, "rev-parse", "HEAD").strip()


def run_to_end(root, sha, **kw):
    rec = testrun.start(root, sha, workers=1, use_venv=False, **kw)
    assert rec["state"] == "running" and rec["pid"]
    return testrun.wait_for(root, sha, timeout=120, poll=0.2)


@pytest.mark.slow
def test_a_green_run_is_recorded_per_sha_and_cleans_up_its_worktree(tmp_path):
    root, sha = fixture_repo(tmp_path)
    rec = run_to_end(root, sha)
    assert rec["passed"] is True and rec["failed"] == [] and rec["sha"] == sha and rec["wall_s"] is not None
    assert rec["tree"] == git(root, "rev-parse", "HEAD^{tree}").strip() and rec["finished"] and rec["python"] and rec["os"]
    assert testrun.state_of(rec) == "green"
    ok, msg = testrun.require_green(root, sha)
    assert ok, msg
    assert not list(testrun.ledger_dir(root).glob("wt-*"))  # the worktree is gone
    assert len(git(root, "worktree", "list").strip().splitlines()) == 1
    again = testrun.start(root, sha, workers=1, use_venv=False)  # a green run is not started again
    assert again["finished"] == rec["finished"]
    assert testrun.status(root)[0].startswith(sha[:12] + "  GREEN")


@pytest.mark.slow
def test_a_red_run_names_the_failing_tests_and_require_green_refuses(tmp_path):
    root, sha = fixture_repo(tmp_path, body="def test_ok():\n    assert True\n\ndef test_bad():\n    assert False\n")
    rec = run_to_end(root, sha)
    assert rec["passed"] is False and rec["failed"] == ["tests/test_fx.py::test_bad"]
    ok, msg = testrun.require_green(root, sha)
    assert not ok and "red" in msg and "test_bad" in msg
    assert testrun.status(root, red_only=True) == [sha]


def test_require_green_refuses_a_missing_running_or_lost_record_a_mismatch_and_a_dirty_tree(tmp_path):
    root, sha = fixture_repo(tmp_path)
    assert testrun.require_green(root, sha)[0] is False  # no record
    rec = {"sha": sha, "tree": "t", "state": "running", "started": "2026-11-08T00:00:00+00:00", "pid": os.getpid(),
           "failed": [], "passed": None}
    testrun.write_record(root, rec)
    ok, msg = testrun.require_green(root, sha)
    assert not ok and "running" in msg
    testrun.write_record(root, {**rec, "pid": 2**22 + 12345})  # no such process
    ok, msg = testrun.require_green(root, sha)
    assert not ok and "lost" in msg
    testrun.write_record(root, {**rec, "state": "finished", "passed": True, "finished": "x", "wall_s": 1.0})
    assert testrun.require_green(root, sha)[0] is True
    (root / "tests" / "test_fx.py").write_text("changed\n", encoding="utf-8")  # HEAD with a dirty tree
    ok, msg = testrun.require_green(root, sha)
    assert not ok and "uncommitted" in msg
    git(root, "commit", "-qam", "next")  # a different SHA has no record
    new = git(root, "rev-parse", "HEAD").strip()
    assert testrun.require_green(root, new)[0] is False
    assert testrun.require_green(root, sha)[0] is True  # an older SHA's green does not need a clean tree


def test_an_error_record_is_not_green(tmp_path):
    root, sha = fixture_repo(tmp_path)
    testrun.write_record(root, {"sha": sha, "state": "error", "passed": False, "failed": [], "error": "boom"})
    ok, msg = testrun.require_green(root, sha)
    assert not ok and "error" in msg
    assert testrun.status(root, red_only=True) == [sha]


@pytest.mark.slow
def test_the_background_run_tests_the_worktrees_own_source_even_in_children(tmp_path):
    stub = "__all__ = []\n"
    root, sha = fixture_repo(tmp_path, extra={"src/baton/__init__.py": stub, "tests/test_where.py": FAKES / "testrun_where.py"})
    rec = testrun.start(root, sha, workers=1, use_venv=True)
    rec = testrun.wait_for(root, sha, timeout=180, poll=0.5)
    assert rec["passed"] is True, rec


@pytest.mark.slow
def test_the_run_venv_reads_the_pth_files_of_the_environment_it_borrows(tmp_path):
    # pywin32's shape: a .pth in site-packages puts its modules' own folder on sys.path (Windows: pywintypes)
    site = tmp_path / "site-packages"
    (site / "win32" / "lib").mkdir(parents=True)
    (site / "win32" / "lib" / "nested_mod.py").write_text("X = 1\n", encoding="utf-8")
    (site / "nested.pth").write_text("win32\lib\n" if os.name == "nt" else "win32/lib\n", encoding="utf-8")
    root, sha = fixture_repo(tmp_path)
    python = testrun._make_run_env(root, deps=[str(site)])
    import subprocess

    done = subprocess.run([str(python), "-c", "import nested_mod"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
