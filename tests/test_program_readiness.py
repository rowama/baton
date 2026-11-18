"""2026-11-tool-steps Slice 3: readiness, approval and setup (§5.9; Decisions 0156, 0159).

The owner approves a recipe's programs when vendoring it, in plain words; a program
not ready on this machine is reported by check, doctor, start and eligible, and
refused at dispatch; ``baton programs setup`` builds environments ahead of use.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from projectkit import Cli, git, make_git_project, make_home

PROGRAM_DEMO = ROOT / "tests" / "fixtures" / "recipes" / "program-demo"


def _copy(tmp_path: Path, *, version: int = 1, program: dict | None = None, script: str | None = None) -> Path:
    src = tmp_path / "src" / f"program-demo-{version}"
    shutil.copytree(PROGRAM_DEMO, src)
    p = src / "recipe.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data["version"] = version
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    if program:
        tp = src / "programs" / "backtest" / "program.yaml"
        t = yaml.safe_load(tp.read_text(encoding="utf-8"))
        for k, v in program.items():
            t[k] = {**t[k], **v} if isinstance(v, dict) else v
        tp.write_text(yaml.safe_dump(t, sort_keys=False), encoding="utf-8")
    if script is not None:
        (src / "programs" / "backtest" / "backtest.py").write_text(script, encoding="utf-8")
    return src


def _project(tmp_path: Path) -> Cli:
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project), "--bare")
    return cli


def _vendor(cli: Cli, src: Path) -> None:
    cli.run("vendor", str(src), "--approved", "--note", "Yes.")
    git(cli.project, "add", "-A")
    git(cli.project, "commit", "-qm", "vendor")


# -- the owner approves programs with the recipe ----------------------------------------


@pytest.mark.not_slow("in-process CLI calls; finds a Python with uv once")
def test_vendoring_a_recipe_with_programs_needs_the_owner_and_says_what_each_does(tmp_path):
    cli = _project(tmp_path)
    src = _copy(tmp_path, program={"reach": {"network": True, "secrets": ["PRICE_FEED_TOKEN"]}})
    res = cli("vendor", str(src), expect=4)
    out = res.payload
    assert out["needs_owner"] and "brings programs" in out["message"]
    (flag,) = out["flags"]
    assert flag["code"] == "program" and flag["program"] == "backtest" and flag["changed"] is False
    assert flag["does"].startswith("Runs a moving-average strategy")
    assert flag["needs"] == "Python >=3.11, nothing else"
    assert flag["touches"] == "does not open your project's files; uses the internet; is given PRICE_FEED_TOKEN"
    text = Cli(cli.project, cli.home)
    from typer.testing import CliRunner

    from baton.cli import app

    plain = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_PROJECT": str(cli.project)}).invoke(app, ["vendor", str(src)])
    assert "program 'backtest': Runs a moving-average strategy" in plain.stdout and "uses the internet" in plain.stdout
    assert text  # the plain listing is the owner's view

    out = cli.run("vendor", str(src), "--approved", "--note", "Yes, the backtest script may run.")
    assert out["changed"] and out["decision_id"]
    lock = json.loads((cli.project / ".baton" / "baton.lock").read_text(encoding="utf-8"))
    entry = lock["recipes"]["program-demo@1"]
    assert set(entry["programs"]) == {"backtest"} and entry["decision"]["flags"][0]["code"] == "program"


@pytest.mark.not_slow("in-process CLI calls")
def test_an_unchanged_program_is_not_asked_about_again_and_a_changed_one_is(tmp_path):
    cli = _project(tmp_path)
    _vendor(cli, _copy(tmp_path, version=1))
    out = cli.run("vendor", str(_copy(tmp_path, version=2)))  # same program files: no question
    assert out["changed"] and not out["needs_owner"] and out["flags"] == []
    out = cli("vendor", str(_copy(tmp_path, version=3, script="print('new')\n")), expect=4).payload
    assert [f["code"] for f in out["flags"]] == ["program"] and out["flags"][0]["changed"] is True


@pytest.mark.not_slow("in-process CLI calls")
def test_a_recipe_without_programs_vendors_as_before(tmp_path):
    from conftest import FIT_CHECK

    cli = _project(tmp_path)
    out = cli.run("vendor", str(FIT_CHECK))
    assert out["changed"] and out["flags"] == []
    lock = json.loads((cli.project / ".baton" / "baton.lock").read_text(encoding="utf-8"))
    assert all("programs" not in e for e in lock["recipes"].values())


# -- not ready is said early ---------------------------------------------------------


@pytest.mark.not_slow("in-process CLI calls; uv finds no Python")
def test_a_program_not_ready_is_reported_by_check_doctor_start_and_eligible_and_refused(tmp_path):
    cli = _project(tmp_path)
    _vendor(cli, _copy(tmp_path, program={"runtime": {"version": ">=3.99"}}))

    issues = cli("check", expect=None).payload["issues"]
    (issue,) = [i for i in issues if i["code"] == "program.not_ready"]
    assert issue["severity"] == "warning" and "Python >=3.99" in issue["message"] and "backtest" in issue["message"]

    doc = cli("doctor", expect=None).payload
    assert any("program backtest of program-demo@1 is not ready" in w for w in doc["warnings"])
    assert doc["programs"][0]["ready"] is False

    started = cli.run("start", "program-demo", "--inputs", json.dumps({"title": "t", "goal": "g"}))
    assert started["programs_not_ready"][0]["program"] == "backtest" and started["programs_not_ready"][0]["steps"] == ["backtest"]
    assert any("not ready on this machine" in w for w in started["warnings"])
    run = started["run_id"]

    # eligible on a step not yet ready to run reports, and dispatch refuses.
    el = cli.run("eligible", run, "backtest")
    assert el["eligible"] == [] and el["excluded"][0]["profile"] == "program:backtest"
    res = cli("dispatch", run, "backtest", "--worker", "program:backtest", expect=None)
    assert res.exit_code != 0


@pytest.mark.not_slow("in-process CLI calls")
def test_a_missing_secret_makes_a_program_not_ready(tmp_path, monkeypatch):
    monkeypatch.delenv("BATON_SECRET_PRICE_FEED_TOKEN", raising=False)
    cli = _project(tmp_path)
    _vendor(cli, _copy(tmp_path, program={"reach": {"secrets": ["PRICE_FEED_TOKEN"]}}))
    doc = cli("doctor", expect=None).payload
    (t,) = doc["programs"]
    assert not t["ready"] and "BATON_SECRET_PRICE_FEED_TOKEN" in t["reasons"][0]
    monkeypatch.setenv("BATON_SECRET_PRICE_FEED_TOKEN", "x")
    (t,) = cli("doctor", expect=None).payload["programs"]
    assert t["ready"] and "built at first use" in t["note"]


# -- baton programs setup ---------------------------------------------------------------


@pytest.mark.slow
def test_programs_setup_builds_then_reuses(tmp_path):
    cli = _project(tmp_path)
    _vendor(cli, _copy(tmp_path))
    first = cli.run("programs", "setup")
    (t,) = first["programs"]
    assert t["status"] == "built" and (cli.home / "programs" / t["env_id"] / "env.json").is_file()
    (again,) = cli.run("programs", "setup")["programs"]
    assert again["status"] == "reused" and again["env_id"] == t["env_id"]
    (d,) = cli("doctor", expect=None).payload["programs"]
    assert d["ready"] and d["env_id"] == t["env_id"] and "note" not in d


@pytest.mark.not_slow("in-process CLI call; uv finds no Python")
def test_programs_setup_reports_a_program_it_cannot_build(tmp_path):
    cli = _project(tmp_path)
    _vendor(cli, _copy(tmp_path, program={"runtime": {"version": ">=3.99"}}))
    res = cli("programs", "setup", expect=1)
    (t,) = res.payload["programs"]
    assert t["status"] == "failed" and t["code"] == "program.no_runtime"


@pytest.mark.not_slow("in-process CLI call")
def test_programs_setup_with_no_programs(tmp_path):
    cli = _project(tmp_path)
    assert cli.run("programs", "setup")["programs"] == []
