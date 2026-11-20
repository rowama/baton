"""2026-11-tool-steps Slice 2: a program step runs (§5.9, §6.3; Decisions 0156, 0158, 0159).

A program step is dispatched to its program (no routing), runs in an environment
built by uv from its lock, under the supervisor like any process worker, and
its result is taken in and gated like any step's. The end-to-end tests run
real processes and are ``slow``; the runner's and the state's own rules are quick.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from baton.engine import Api
from baton.routing import WorkerIdentity, same_at
from baton.state import RunState
from baton.program_runner import collect, fill, inputs_document

from conftest import ROOT
from projectkit import Cli, git, make_git_project, make_home, packet_dir, write_result

PROGRAM_DEMO = ROOT / "tests" / "fixtures" / "recipes" / "program-demo"
PARAMS = {"window": 3, "reason": "short swings"}

PROBE = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
inp, out = Path(args[args.index("--input") + 1]), Path(args[args.index("--output") + 1])
mode = os.environ.get("PROBE_MODE", "")
data = json.loads(inp.read_text(encoding="utf-8"))
probe = {"argv": args, "cwd": os.getcwd(), "cwd_entries": os.listdir("."), "env": sorted(os.environ),
         "secret": os.environ.get("PRICE_FEED_TOKEN"), "inputs": data, "python": sys.executable}
(out / "trades.csv").write_text(json.dumps(probe), encoding="utf-8")
if "workspace" in args[-1:] or "--repo" in args:
    Path(args[args.index("--repo") + 1], "stray.txt").write_text("x", encoding="utf-8")
(out / "output.json").write_text(json.dumps({"trades": 0, "return_pct": 0.0}), encoding="utf-8")
'''

FAILS = r'''
import sys
print("loading prices", file=sys.stderr)
print("ValueError: window must be positive", file=sys.stderr)
sys.exit(2)
'''

EXTRA = r'''
import json, sys
from pathlib import Path
out = Path(sys.argv[sys.argv.index("--output") + 1])
(out / "output.json").write_text(json.dumps({"trades": 0, "return_pct": 0.0}), encoding="utf-8")
(out / "trades.csv").write_text("day,side,price\n", encoding="utf-8")
(out / "debug.log").write_text("left behind\n", encoding="utf-8")
'''


class Setup:
    """A git project with a (possibly edited) program-demo vendored, and the owner as a manual worker."""

    def __init__(self, tmp_path: Path, *, script: str | None = None, program: dict | None = None, step: dict | None = None):
        src = tmp_path / "src" / "program-demo"
        shutil.copytree(PROGRAM_DEMO, src)
        if script is not None:
            (src / "programs" / "backtest" / "backtest.py").write_text(script, encoding="utf-8")
        if program:
            p = src / "programs" / "backtest" / "program.yaml"
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            for k, v in program.items():
                data[k] = {**data[k], **v} if isinstance(v, dict) else v
            p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        if step:
            p = src / "recipe.yaml"
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            next(s for s in data["steps"] if s["id"] == "backtest").update(step)
            p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home")
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project), "--bare")
        self.cli.run("vendor", str(src), "--approved", "--note", "Yes, use the backtest script.")  # programs need the owner (§5.9)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")
        self.run = self.cli.run("start", "program-demo", "--inputs", json.dumps({"title": "MA test", "goal": "catch short swings"}))["run_id"]

    def parameters(self) -> None:
        self.cli.run("dispatch", self.run, "parameters", "--worker", "owner")
        write_result(packet_dir(self.project, self.run, "parameters", 1), PARAMS)
        self.cli.run("submit", self.run, "parameters")

    def backtest(self, expect: int | None = None):  # an escalation exits 4 (the owner is needed)
        return self.cli("dispatch", self.run, "backtest", "--worker", "program:backtest", "--wait", expect=expect)

    def events(self) -> list[dict]:
        p = self.project / ".baton" / "runs" / self.run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def last(self, etype: str, step: str = "backtest") -> dict:
        return [e for e in self.events() if e["type"] == etype and e["step_path"] == step][-1]

    def artifact(self, name: str, attempt: int = 1) -> str:
        rdir = self.project / ".baton" / "runs" / self.run / "steps" / "backtest" / f"attempt-{attempt}" / "result" / "artifacts"
        (f,) = [p for p in rdir.iterdir() if p.name.split(".")[0] == name]
        return f.read_text(encoding="utf-8")

    def incidents(self) -> list[dict]:
        api = Api.open(self.project, director_id="alice@host1", home=self.home)
        return [e.data for e in api.project.store.project_log().events() if e.type == "platform_incident_opened"]


# -- end to end -----------------------------------------------------------------


@pytest.mark.slow
def test_a_program_step_runs_and_feeds_the_next_step(tmp_path):
    s = Setup(tmp_path)
    s.parameters()
    eligible = s.cli.run("eligible", s.run, "backtest")
    assert [e["profile"] for e in eligible["eligible"]] == ["program:backtest"] and eligible["excluded"] == []

    out = s.backtest().payload
    assert out["outcome"] == "passed" and out["adapter"] == "program"

    d = s.last("dispatched")["data"]
    program = d["program"]
    assert program["id"] == "backtest" and program["runtime"] == {"kind": "python", "version": ">=3.11"}
    assert len(program["sha256"]) == 64 and len(program["lock_sha256"]) == 64 and program["python_version"].startswith("3.")
    assert program["env_id"] == f"{program['lock_sha256']}-py{'.'.join(program['python_version'].split('.')[:2])}"
    assert program["reach"] == {"workspace": "none", "network": False, "secrets": []}
    assert d["effort"] == "S" and d["effort_source"] == "program default"
    assert (s.home / "programs" / program["env_id"] / "env.json").is_file()

    passed = s.last("step_passed")
    assert passed["type"] == "step_passed"
    assert s.artifact("trades").startswith("day,side,price")

    # The next step's packet holds the program's output and artifact.
    s.cli.run("dispatch", s.run, "report", "--worker", "owner")
    manifest = json.loads((packet_dir(s.project, s.run, "report", 1) / "manifest.json").read_text(encoding="utf-8"))
    assert {i["name"] for i in manifest["inputs"]} == {"result", "trades"}
    assert "program" not in manifest  # only program packets carry the key


@pytest.mark.slow
def test_a_program_gets_only_what_it_declares(tmp_path, monkeypatch):
    monkeypatch.setenv("BATON_SECRET_PRICE_FEED_TOKEN", "s3cret-value")
    monkeypatch.setenv("UNRELATED_SECRET", "leak")
    s = Setup(tmp_path, script=PROBE, program={"reach": {"secrets": ["PRICE_FEED_TOKEN"]}})
    s.parameters()
    assert s.backtest().payload["outcome"] == "passed"
    probe = json.loads(s.artifact("trades"))
    assert probe["secret"] == "s3cret-value"
    assert "UNRELATED_SECRET" not in probe["env"] and not [n for n in probe["env"] if n.startswith("BATON_")]
    assert probe["cwd_entries"] == []  # a fresh, empty scratch folder (Decision 0158)
    assert Path(probe["cwd"]).resolve() != (s.project / ".baton").resolve() and "programs" not in Path(probe["cwd"]).parts[-2:]
    assert probe["inputs"] == {"parameters": PARAMS}  # values, never on the command line (Decision 0159)
    assert not any("short swings" in a for a in probe["argv"])
    assert Path(probe["python"]).is_relative_to(s.home / "programs")
    d = s.last("dispatched")["data"]
    assert d["env"]["secret_names"] == ["PRICE_FEED_TOKEN"] and "s3cret-value" not in json.dumps(s.events())


@pytest.mark.slow
@pytest.mark.parametrize("attempts", [1, 2])
def test_a_failing_program_escalates_with_its_error_regardless_of_attempt_budget(tmp_path, attempts):
    s = Setup(tmp_path, script=FAILS, step={"max_attempts": attempts})
    s.parameters()
    out = s.backtest().payload
    assert out["outcome"] == "escalated"
    assert s.last("step_escalated")["data"]["reason"] == "worker_failed"
    notes = json.dumps(s.events())
    assert "exited with code 2" in notes and "window must be positive" in notes
    assert [e["attempt"] for e in s.events() if e["type"] == "dispatched" and e["step_path"] == "backtest"] == [1]


@pytest.mark.slow
def test_a_recipe_may_raise_a_programs_attempts(tmp_path):
    # A completed result that fails its schema still uses the recipe's retry budget.
    s = Setup(tmp_path, script=PROBE.replace('"trades": 0', '"trades": "invalid"'), step={"max_attempts": 2})
    s.parameters()
    assert s.backtest().payload["outcome"] == "retry"
    assert s.backtest().payload["outcome"] == "escalated"


@pytest.mark.slow
def test_an_undeclared_output_file_fails_the_attempt(tmp_path):
    s = Setup(tmp_path, script=EXTRA)
    s.parameters()
    assert s.backtest().payload["outcome"] == "escalated"
    assert "'debug.log'" in json.dumps(s.events())


@pytest.mark.slow
def test_no_fitting_python_is_a_platform_failure_and_nothing_is_dispatched(tmp_path):
    s = Setup(tmp_path, program={"runtime": {"version": ">=3.99"}})
    s.parameters()
    res = s.backtest(expect=None)
    assert res.exit_code != 0 and res.payload["error"] == "program.no_runtime", res.payload
    assert "never downloads" in res.payload["message"]
    assert not [e for e in s.events() if e["type"] == "dispatched" and e["step_path"] == "backtest"]
    assert s.cli.run("status", s.run)  # the run is still readable
    (inc,) = s.incidents()
    assert inc["class"] == "platform" and inc["code"] == "no_runtime" and inc["step_path"] == "backtest"


@pytest.mark.slow
def test_a_missing_secret_refuses_the_dispatch(tmp_path, monkeypatch):
    monkeypatch.delenv("BATON_SECRET_PRICE_FEED_TOKEN", raising=False)
    s = Setup(tmp_path, program={"reach": {"secrets": ["PRICE_FEED_TOKEN"]}})
    s.parameters()
    res = s.backtest(expect=None)
    assert res.exit_code != 0 and "PRICE_FEED_TOKEN" in res.payload["message"]
    assert not [e for e in s.events() if e["type"] == "dispatched" and e["step_path"] == "backtest"]


@pytest.mark.slow
def test_a_program_that_changes_the_workspace_beyond_its_reach_is_caught(tmp_path):
    s = Setup(
        tmp_path, script=PROBE, step={"workspace": "read"},
        program={"reach": {"workspace": "read"}, "entry": ["python", "{program}/backtest.py", "--input", "{input}", "--output", "{output}", "--repo", "{workspace}"]},
    )
    s.parameters()
    assert s.backtest().payload["outcome"] == "escalated"
    assert s.last("step_escalated")["data"]["reason"] == "workspace_modified"


@pytest.mark.slow
def test_the_environment_is_reused_while_the_lock_is_unchanged(tmp_path):
    a = Setup(tmp_path / "a")
    a.parameters()
    a.backtest()
    env_id = a.last("dispatched")["data"]["program"]["env_id"]
    built = (a.home / "programs" / env_id / "env.json").stat().st_mtime_ns
    b = Cli(a.project, a.home)
    run2 = b.run("start", "program-demo", "--inputs", json.dumps({"title": "again", "goal": "again"}))["run_id"]
    b.run("dispatch", run2, "parameters", "--worker", "owner")
    write_result(packet_dir(a.project, run2, "parameters", 1), PARAMS)
    b.run("submit", run2, "parameters")
    b.run("dispatch", run2, "backtest", "--worker", "program:backtest", "--wait")
    assert (a.home / "programs" / env_id / "env.json").stat().st_mtime_ns == built


@pytest.mark.slow
def test_a_worker_cannot_take_a_program_step_nor_a_program_a_worker_step(tmp_path):
    s = Setup(tmp_path)
    s.parameters()
    res = s.cli("dispatch", s.run, "backtest", "--worker", "owner", expect=None)
    assert res.exit_code != 0 and res.payload["error"] == "routing.ineligible" and "program:backtest" in res.payload["message"]
    res = s.cli("dispatch", s.run, "report", "--worker", "program:backtest", expect=None)
    assert res.exit_code != 0 and res.payload["error"] == "configuration.unknown_profile"


@pytest.mark.slow
def test_runs_without_programs_record_no_program_limits(tmp_path):
    from projectkit import setup_fit_check

    cli, project = setup_fit_check(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps({"title": "x", "idea": "y"}))["run_id"]
    first = json.loads((project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["type"] == "run_started" and "step_max_attempts" not in first["data"]


# -- the runner's and the state's own rules -------------------------------------------


@pytest.mark.not_slow("reads and writes a few files")
def test_inputs_document_gives_values_and_file_references(tmp_path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "parameters.json").write_text(json.dumps(PARAMS), encoding="utf-8")
    (tmp_path / "inputs" / "prices.csv").write_text("1,2\n", encoding="utf-8")
    (tmp_path / "inputs" / "d1.md").write_text("one", encoding="utf-8")
    (tmp_path / "inputs" / "d0.md").write_text("zero", encoding="utf-8")
    manifest = {"inputs": [
        {"name": "parameters", "path": "inputs/parameters.json", "media_type": "application/json"},
        {"name": "prices", "path": "inputs/prices.csv", "media_type": "text/csv"},
        {"name": "docs", "path": "inputs/d1.md", "media_type": "text/markdown", "index": 1},
        {"name": "docs", "path": "inputs/d0.md", "media_type": "text/markdown", "index": 0},
    ]}
    doc = inputs_document(tmp_path, manifest)
    assert doc["parameters"] == PARAMS
    assert doc["prices"] == {"path": str((tmp_path / "inputs" / "prices.csv").resolve()), "media_type": "text/csv"}
    assert [Path(d["path"]).name for d in doc["docs"]] == ["d0.md", "d1.md"]


@pytest.mark.not_slow("lists a folder")
def test_collect_takes_declared_artifacts_and_names_anything_else(tmp_path):
    manifest = {"required_artifacts": [{"name": "trades"}], "optional_artifacts": [{"name": "chart"}]}
    (tmp_path / "output.json").write_text("{}", encoding="utf-8")
    (tmp_path / "trades.csv").write_text("x", encoding="utf-8")
    found, problems = collect(tmp_path, manifest)
    assert list(found) == ["trades"] and problems == []
    (tmp_path / "trades.json").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    _, problems = collect(tmp_path, manifest)
    assert len(problems) == 3 and any("two files for artifact 'trades'" in p for p in problems)


@pytest.mark.not_slow("string work")
def test_fill_replaces_only_the_placeholders():
    assert fill(["{program}/a.py", "--x", "{input}", "{nope}"], {"program": "/t", "input": "/i"}) == ["/t/a.py", "--x", "/i", "{nope}"]


@pytest.mark.not_slow("folds three events")
def test_a_program_step_has_its_own_attempt_limit():
    rs = RunState("r")
    rs.apply({"type": "run_started", "data": {"max_attempts": 3, "step_max_attempts": {"backtest": 1}}})
    assert rs.limit_for("backtest") == 1 and rs.limit_for("report") == 3
    assert rs.limit_for("slices/x1/i1/backtest") == 1 and rs.limit_for("backtest~review") == 3


@pytest.mark.not_slow("compares two records")
def test_a_program_and_a_worker_are_always_independent():
    program = WorkerIdentity("program:backtest", "program", adapter="program")
    worker = WorkerIdentity("bot", "program", adapter="command")  # even a worker whose creator is called "program"
    for level in ("different_profile", "different_vendor", "different_model"):
        assert not same_at(level, program, worker) and not same_at(level, worker, program)
    assert same_at("different_vendor", program, WorkerIdentity("program:other", "program", adapter="program"))


LEAKS = r'''
import os, sys
print("token is " + os.environ["PRICE_FEED_TOKEN"], file=sys.stderr)
sys.exit(1)
'''


@pytest.mark.slow
def test_a_secret_in_a_programs_error_output_is_never_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("BATON_SECRET_PRICE_FEED_TOKEN", "s3cret-value")
    s = Setup(tmp_path, script=LEAKS, program={"reach": {"secrets": ["PRICE_FEED_TOKEN"]}})
    s.parameters()
    assert s.backtest().payload["outcome"] == "escalated"
    recorded = json.dumps(s.events())
    assert "token is" in recorded and "s3cret-value" not in recorded


@pytest.mark.slow
def test_a_failed_build_is_a_platform_failure_and_leaves_no_environment(tmp_path, monkeypatch):
    from baton import program_env
    from baton.recipe import load_recipe

    src = tmp_path / "program-demo"
    shutil.copytree(PROGRAM_DEMO, src)
    (src / "programs" / "backtest" / "requirements.lock").write_text(
        "no-such-package-for-baton==1.0.0 --hash=sha256:" + "0" * 64 + "\n", encoding="utf-8")
    monkeypatch.setenv("UV_OFFLINE", "1")  # nothing can be fetched: the install fails quickly
    program = load_recipe(src).programs["backtest"]
    with pytest.raises(program_env.ProgramSetupError) as e:
        program_env.ensure(program, tmp_path / "home")
    assert e.value.code == "program.build_failed" and e.value.failure_class == "platform" and "install its dependencies" in str(e.value)
    assert not list((tmp_path / "home" / "programs").glob("*/env.json"))  # an unfinished build is never reused


@pytest.mark.slow
def test_a_program_steps_human_gate_waits_for_the_owner(tmp_path):
    s = Setup(tmp_path, step={"gates": [{"type": "schema"}, {"type": "human", "prompt": "Accept these results?"}]})
    s.parameters()
    assert s.backtest().payload["outcome"] == "needs_human"
    out = s.cli("decide", s.run, "backtest", "approve", "--note", "Looks right.", expect=None).payload
    assert s.last("step_passed")["type"] == "step_passed", out
