"""2026-11-waiting-steps Slice 1: a step waits as state (§5.9, §8.1, §8.7; Decisions 0154 item 5, 0165).

A tool step with ``wait`` runs its check at dispatch. Not met, the step is
``waiting`` with a deadline and no process; ``baton waits check`` runs the
check again, takes the result in when it is met, counts failed checks, and at
the deadline hands the step to the owner. The end-to-end tests build a real
tool environment and run real checks, so they are ``slow``; the rules are quick.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from baton import labels, locks, state as sm, waits
from baton.engine import Api
from baton.models import duration_seconds
from baton.state import IllegalTransition, RunState
from baton.supervisor import now as utc_now, parse

from conftest import ROOT
from projectkit import Cli, git, make_git_project, make_home, packet_dir, write_result

TOOL_DEMO = ROOT / "tests" / "fixtures" / "recipes" / "tool-demo"
PARAMS = {"window": 3, "reason": "short swings"}

# The check: met when the flag file says "yes", crashes on "crash", else not met.
CHECK = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("--output") + 1])
flag = Path(FLAG)
mode = flag.read_text(encoding="utf-8").strip() if flag.exists() else "no"
if mode == "crash":
    print("ConnectionError: the price feed is down", file=sys.stderr)
    sys.exit(2)
if mode == "yes":
    (out / "trades.csv").write_text("day,side,price\n", encoding="utf-8")
    (out / "output.json").write_text(json.dumps({"met": True, "trades": 0, "return_pct": 0.0}), encoding="utf-8")
elif mode == "nomet":
    (out / "output.json").write_text(json.dumps({"trades": 0, "return_pct": 0.0}), encoding="utf-8")
else:
    (out / "output.json").write_text(json.dumps({"met": False}), encoding="utf-8")
'''

HOOK = """\
import json, os, sys
rec = {k: v for k, v in os.environ.items() if k.startswith("BATON_")}
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\\n")
"""


class Setup:
    """tool-demo with its backtest step made a waiting step whose check reads a flag file."""

    def __init__(self, tmp_path: Path, *, wait: dict | None = None, waits_max: str | None = None):
        self.tmp = tmp_path
        self.flag = tmp_path / "flag.txt"
        src = tmp_path / "src" / "tool-demo"
        shutil.copytree(TOOL_DEMO, src)
        (src / "tools" / "backtest" / "backtest.py").write_text(f"FLAG = {str(self.flag)!r}\n" + CHECK, encoding="utf-8")
        rp = src / "recipe.yaml"
        data = yaml.safe_load(rp.read_text(encoding="utf-8"))
        next(s for s in data["steps"] if s["id"] == "backtest")["wait"] = wait or {"until": "14d", "every": "30m"}
        rp.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home")
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project), "--bare")
        self.cli.run("vendor", str(src), "--approved", "--note", "Yes, use the price check.")
        self.hook_log = tmp_path / "hooks.jsonl"
        (tmp_path / "hook.py").write_text(HOOK, encoding="utf-8")
        py = self.project / ".baton" / "project.yaml"
        cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
        cfg["hooks"] = {"on_complete": f'"{sys.executable}" "{tmp_path / "hook.py"}" "{self.hook_log}"'}
        if waits_max:
            cfg["waits"] = {"max": waits_max}
        py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")
        self.run = self.cli.run("start", "tool-demo", "--inputs", json.dumps({"title": "MA test", "goal": "catch short swings"}))["run_id"]
        self.cli.run("dispatch", self.run, "parameters", "--worker", "owner")
        write_result(packet_dir(self.project, self.run, "parameters", 1), PARAMS)
        self.cli.run("submit", self.run, "parameters")

    def flag_to(self, mode: str) -> None:
        self.flag.write_text(mode, encoding="utf-8")

    def dispatch(self, expect: int | None = None) -> dict:
        return self.cli("dispatch", self.run, "backtest", "--worker", "tool:backtest", "--wait", expect=expect).payload

    def check(self, *, later: timedelta | None = None) -> dict:
        if later is None:
            return self.cli.run("waits", "check")
        api = Api.open(self.project, director_id="alice@host1", home=self.home, clock=lambda: utc_now() + later)
        try:
            return api.waits_check()
        finally:
            api.close()

    def events(self) -> list[dict]:
        p = self.project / ".baton" / "runs" / self.run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def types(self, step: str = "backtest") -> list[str]:
        return [e["type"] for e in self.events() if e["step_path"] == step]

    def last(self, etype: str, step: str = "backtest") -> dict:
        return [e for e in self.events() if e["type"] == etype and e["step_path"] == step][-1]

    def status(self) -> dict:
        return self.cli("status", self.run, expect=None).payload  # exits 4 while the owner is needed

    def state(self, step: str = "backtest") -> str:
        return self.status()["steps"][step]["state"]

    def hooks(self) -> list[dict]:
        if not self.hook_log.is_file():
            return []
        return [json.loads(line) for line in self.hook_log.read_text(encoding="utf-8").splitlines()]


# -- end to end ------------------------------------------------------------------


@pytest.mark.slow
def test_a_condition_met_at_dispatch_goes_on_as_any_tool_step(tmp_path):
    s = Setup(tmp_path)
    s.flag_to("yes")
    out = s.dispatch()
    assert out["outcome"] == "passed"
    assert "wait_started" not in s.types()
    assert s.last("step_passed")["type"] == "step_passed"
    assert "report" in s.status()["ready"]


@pytest.mark.slow
def test_not_met_the_step_waits_with_no_process_and_a_later_check_takes_it_in(tmp_path):
    s = Setup(tmp_path)
    out = s.dispatch()
    assert out["outcome"] == "waiting"
    started = s.last("wait_started")["data"]
    assert started["until"] == "14d" and started["every"] == "30m" and started["on_expire"] == "escalate" and "cut_to" not in started
    assert abs((parse(started["deadline"]) - utc_now()) - timedelta(days=14)) < timedelta(minutes=5)
    assert "result_submitted" not in s.types()
    assert list((s.project / ".baton" / "cache" / "running").glob("*.json")) == []  # no process stays running
    assert s.hooks()[-1]["BATON_OUTCOME"] == "waiting" and s.hooks()[-1]["BATON_STEP_STATE"] == "waiting"
    assert s.state() == "waiting"

    # Reconciliation leaves it alone (criterion 3).
    assert s.cli.run("resume", s.run)["reconciled"] == []
    assert s.cli.run("wait", s.run)["results"] == []
    assert s.state() == "waiting"

    # A routine check that finds nothing records nothing in the log (criterion 10).
    n = len(s.events())
    checked = s.check()["checked"]
    assert [c["result"] for c in checked] == ["not_met"]
    assert len(s.events()) == n
    assert waits.entry(s.project / ".baton", s.run, "backtest", 1)["last_checked"] == checked[0]["last_checked"]

    s.flag_to("yes")
    checked = s.check()["checked"]
    assert [(c["result"], c["outcome"]) for c in checked] == [("met", "passed")]
    types = s.types()
    assert types.index("wait_met") < types.index("result_submitted") < types.index("step_passed")
    assert s.state() == "passed" and "report" in s.status()["ready"]
    assert s.hooks()[-1]["BATON_OUTCOME"] == "passed"
    assert waits.entry(s.project / ".baton", s.run, "backtest", 1) == {}
    assert not (s.project / ".baton" / "runs" / s.run / "steps" / "backtest" / "attempt-1" / "check").exists()
    assert s.check()["checked"] == []


@pytest.mark.slow
def test_at_the_deadline_the_owner_decides_and_retry_waits_another_period(tmp_path):
    s = Setup(tmp_path, wait={"until": "2d"})
    s.dispatch()
    out = s.check(later=timedelta(days=3))["checked"]
    assert [c["result"] for c in out] == ["expired"]
    assert [t for t in s.types() if not t.startswith("completion_hook")][-2:] == ["wait_expired", "step_escalated"]
    assert s.last("step_escalated")["data"]["reason"] == "wait_expired"
    assert s.hooks()[-1]["BATON_OUTCOME"] == "needs_human"
    (pending,) = s.status()["pending_decisions"]
    assert pending["reason"] == "wait_expired" and labels.decision_names(pending["options"]) == ["retry", "abandon"]
    s.cli("decide", s.run, "backtest", "skip", "--note", "go on", expect=None)
    assert s.state() == "escalated"

    s.cli("decide", s.run, "backtest", "retry", "--note", "Keep waiting.", expect=None)
    out = s.dispatch()
    assert out["outcome"] == "waiting" and out["attempt"] == 2
    assert parse(s.last("wait_started")["data"]["deadline"]) > utc_now() + timedelta(days=1)


@pytest.mark.slow
def test_an_optional_wait_may_be_skipped_at_its_deadline_and_the_work_goes_on(tmp_path):
    s = Setup(tmp_path, wait={"until": "1h", "on_expire": "skip"})
    s.dispatch()
    s.check(later=timedelta(hours=2))
    (pending,) = s.status()["pending_decisions"]
    assert labels.decision_names(pending["options"]) == ["retry", "skip", "abandon"]
    out = s.cli("decide", s.run, "backtest", "skip", "--note", "Go on with what we have.", expect=None).payload
    assert out["outcome"] == "skipped"
    assert s.last("step_skipped")["data"] == {"cause": "wait_expired"}
    assert s.state() == "skipped"


@pytest.mark.slow
def test_failed_checks_are_counted_and_the_third_in_a_row_goes_to_the_owner(tmp_path):
    s = Setup(tmp_path)
    s.dispatch()
    s.flag_to("crash")
    n = len(s.events())
    first = s.check()["checked"][0]
    assert first["result"] == "check_failed" and first["failures"] == 1 and "exited with code 2" in first["reasons"][0]
    assert len(s.events()) == n  # counted outside the log
    s.flag_to("no")
    assert s.check()["checked"][0]["result"] == "not_met"  # a good check resets the count
    s.flag_to("crash")
    assert [s.check()["checked"][0].get("failures") for _ in range(2)] == [1, 2]
    third = s.check()["checked"][0]
    assert third["result"] == "escalated" and third["outcome"] == "escalated"
    esc = s.last("step_escalated")["data"]
    assert esc["reason"] == "wait_check_failed" and esc["failures"] == 3 and "price feed is down" in esc["reasons"][0]
    assert s.hooks()[-1]["BATON_OUTCOME"] == "failed"


@pytest.mark.slow
def test_a_check_without_met_is_a_failed_check(tmp_path):
    s = Setup(tmp_path)
    s.dispatch()
    s.flag_to("nomet")
    out = s.check()["checked"][0]
    assert out["result"] == "check_failed" and "met: true or false" in out["reasons"][0]


@pytest.mark.slow
def test_a_longer_wait_than_the_project_allows_is_cut_to_it(tmp_path):
    s = Setup(tmp_path, wait={"until": "60d"}, waits_max="1d")
    s.dispatch()
    started = s.last("wait_started")["data"]
    assert started["until"] == "60d" and started["cut_to"] == "1d"
    assert abs((parse(started["deadline"]) - utc_now()) - timedelta(days=1)) < timedelta(minutes=5)


@pytest.mark.slow
def test_two_checks_never_overlap(tmp_path):
    s = Setup(tmp_path)
    s.dispatch()
    with waits.check_lock(s.project / ".baton") as taken:
        assert taken
        assert s.check() == {"busy": True, "checked": []}
    assert s.check()["checked"][0]["result"] == "not_met"


# -- the rules -------------------------------------------------------------------


def _waiting(rs: RunState | None = None) -> RunState:
    rs = rs or _started()
    for etype in ("step_ready", "dispatched", "step_running", "wait_started"):
        rs.apply({"type": etype, "step_path": "w", "attempt": sm.attempt_for(rs.step("w"), etype)})
    return rs


def _started() -> RunState:
    rs = RunState("r_test")
    rs.apply({"type": "run_started", "data": {"max_attempts": 1}})
    return rs


def _ap(rs: RunState, etype: str, **data: object) -> None:
    rs.apply({"type": etype, "step_path": "w", "attempt": sm.attempt_for(rs.step("w"), etype), "data": data})


@pytest.mark.not_slow("folds a few events")
def test_a_waiting_step_holds_its_attempt():
    rs = _waiting()
    assert rs.step("w").state == "waiting" and rs.step("w").attempt == 1
    for etype in ("wait_met", "wait_expired"):
        _ap(rs, etype)
        assert rs.step("w").state == "waiting"
    with pytest.raises(IllegalTransition):
        rs.apply({"type": "wait_met", "step_path": "w", "attempt": 2})


@pytest.mark.not_slow("folds a few events")
def test_a_waiting_step_is_submitted_or_escalated_only():
    rs = _waiting()
    _ap(rs, "result_submitted")
    assert rs.step("w").state == "submitted"
    rs = _waiting()
    _ap(rs, "step_escalated")
    assert rs.step("w").state == "escalated"
    for etype in ("step_timed_out", "attempt_orphaned", "step_ready", "step_passed", "step_skipped"):
        with pytest.raises(IllegalTransition):
            _ap(_waiting(), etype)


@pytest.mark.not_slow("folds a few events")
def test_wait_records_are_legal_only_while_waiting():
    rs = _started()
    _ap(rs, "step_ready")
    for etype in ("wait_met", "wait_expired", "wait_started"):
        with pytest.raises(IllegalTransition):
            _ap(rs, etype)


@pytest.mark.not_slow("folds a few events")
def test_only_an_expired_wait_is_skipped_from_escalated():
    rs = _waiting()
    _ap(rs, "step_escalated")
    with pytest.raises(IllegalTransition) as e:
        _ap(rs, "step_skipped", cause="retriage")
    assert e.value.code == "state.not_a_wait"
    _ap(rs, "step_skipped", cause="wait_expired")
    assert rs.step("w").state == "skipped" and "skipped" in sm.SATISFIES_DEPS


@pytest.mark.not_slow("arithmetic")
def test_durations_take_days():
    assert duration_seconds("14d") == 14 * 86400 and duration_seconds("30m") == 1800


def _codes(make_recipe, step: dict) -> set[str]:
    from baton.recipe import RecipeError, load_recipe

    sid = step.pop("_id", "backtest")
    root = make_recipe(lambda d, _p: next(s for s in d["steps"] if s["id"] == sid).update(step), source=TOOL_DEMO)
    try:
        load_recipe(root)
    except RecipeError as e:
        return {i.code for i in e.issues}
    return set()


@pytest.mark.not_slow("loads one recipe")
def test_a_tool_step_may_wait(make_recipe):
    assert _codes(make_recipe, {"wait": {"until": "14d", "every": "30m", "on_expire": "skip"}}) == set()


@pytest.mark.not_slow("loads one recipe")
@pytest.mark.parametrize("step,code", [
    ({"_id": "parameters", "wait": {"until": "1d"}}, "step.wait_needs_tool"),
    ({"wait": {"until": "soon"}}, "step.bad_wait_duration"),
    ({"wait": {"until": "1d", "every": "0m"}}, "step.bad_wait_duration"),
])
def test_bad_waits_are_rejected(make_recipe, step, code):
    assert code in _codes(make_recipe, step)


@pytest.mark.not_slow("loads one recipe")
def test_a_waiting_step_may_not_write(make_recipe):
    def edit(d: dict, _p: Path) -> None:
        next(s for s in d["steps"] if s["id"] == "backtest").update({"wait": {"until": "1d"}, "workspace": "write"})

    from baton.recipe import RecipeError, load_recipe

    root = make_recipe(edit, source=TOOL_DEMO)
    with pytest.raises(RecipeError) as e:
        load_recipe(root)
    assert "step.wait_workspace_write" in {i.code for i in e.value.issues}


@pytest.mark.not_slow("validates one document")
def test_a_waiting_step_conforms_to_the_published_schema():
    from jsonschema import Draft202012Validator

    from baton.data import path as data_path

    schema = json.loads((data_path("formats") / "baton-recipe-1.schema.json").read_text(encoding="utf-8"))
    raw = yaml.safe_load((TOOL_DEMO / "recipe.yaml").read_text(encoding="utf-8"))
    next(s for s in raw["steps"] if s["id"] == "backtest")["wait"] = {"until": "14d", "every": "30m", "on_expire": "skip"}
    assert not [e.message for e in Draft202012Validator(schema).iter_errors(raw)]


@pytest.mark.not_slow("reads the labels")
def test_the_expired_wait_options_are_labelled():
    opts = labels.options("wait_expired", ("retry", "skip", "abandon"))
    assert [o["label"] for o in opts] == ["Keep waiting", "Go on without it", "Stop waiting and set this aside"]


@pytest.mark.not_slow("a few small files")
def test_the_check_cache_keeps_one_entry_per_waiting_attempt(tmp_path):
    baton = tmp_path / ".baton"
    (baton / "runs" / "r_1").mkdir(parents=True)
    assert waits.entry(baton, "r_1", "w", 1) == {}
    waits.update(baton, "r_1", "w", 1, last_checked="t1", failures=1)
    assert waits.update(baton, "r_1", "w", 1, failures=2) == {"last_checked": "t1", "failures": 2}
    waits.update(baton, "r_gone", "w", 1, failures=1)  # a run that no longer exists is dropped
    assert set(waits.read(baton)) == {"r_1/w#1"}
    waits.forget(baton, "r_1", "w", 1)
    assert waits.read(baton) == {}


@pytest.mark.not_slow("takes a file lock twice")
def test_a_held_check_lock_is_reported_busy(tmp_path):
    with locks.try_file_lock(tmp_path / "x.lock") as first:
        assert first
        with locks.try_file_lock(tmp_path / "x.lock") as second:
            assert not second
    with locks.try_file_lock(tmp_path / "x.lock") as again:
        assert again
