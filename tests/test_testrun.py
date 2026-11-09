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
