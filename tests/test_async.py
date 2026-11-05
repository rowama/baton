"""Phase 7: the async layer (§8.7, §8.8).

A dispatch survives its caller's shell; hooks fire for every outcome; each
liveness row of the running-marker table is reproduced; an overdue S step is
extended once, then terminated and classified; with no hook that would wake
the Director, eligible gives the owner's notice and dispatch warns, with or
without --wait; classification is data-driven.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from baton import classify, supervisor
from baton.engine import Api
from baton.redact import SENTINEL_PREFIX
from baton.state import IllegalTransition, StepState, next_step_state
from conftest import FIT_CHECK
from projectkit import FIT_INPUTS, GOOD_PROFILE, OWNER_PROFILE, VERDICT, Cli, git, make_git_project, make_home

WORKER = Path(__file__).resolve().parent / "fakes" / "scripted_worker.py"
FIT_CAPS = ["structured_output", "long_form_writing", "technical_reasoning"]
HOOK = """\
import json, os, sys
rec = {k: v for k, v in os.environ.items() if k.startswith("BATON_")}
rec["argv"] = sys.argv[2:]
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\\n")
sys.exit(int(os.environ.get("HOOK_EXIT", "0")))
"""


class Setup:
    def __init__(self, tmp_path: Path, *, effort: str | None = None, effort_cfg: dict | None = None, hooks: dict | None = None,
                 machine_hooks: dict | None = None, script_gate: str | None = None):
        src = tmp_path / "fit-check"
        shutil.copytree(FIT_CHECK, src)
        rf = src / "recipe.yaml"
        data = yaml.safe_load(rf.read_text(encoding="utf-8"))
        describe = data["steps"][0]
        if effort:
            describe["effort"] = effort
        if script_gate:
            describe["gates"].append({"type": "script", "run": script_gate})
        rf.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        self.tmp = tmp_path
        self.behavior = tmp_path / "behavior.json"
        self.behave("good", output=GOOD_PROFILE)
        self.hook_log = tmp_path / "hooks.jsonl"
        self.hook_py = tmp_path / "hook.py"
        self.hook_py.write_text(HOOK, encoding="utf-8")
        bot = (
            f"bot:\n  adapter: command\n  vendor: other\n"
            f"  command: {json.dumps(_cmdline([sys.executable, str(WORKER), '{packet}', '{result}', str(self.behavior)]))}\n"
            f"  capabilities: {json.dumps(FIT_CAPS)}\n  tier: strong\n"
        )
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home", OWNER_PROFILE + bot)
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project), "--bare")  # vendors its own edited fit-check
        self.cli.run("vendor", str(src))
        py = self.project / ".baton" / "project.yaml"
        cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
        cfg["effort"] = {**cfg["effort"], **(effort_cfg or {})}
        cfg["hooks"] = {k: self.hook_cmd(v) for k, v in (hooks or {}).items()}
        py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        if machine_hooks:
            (self.home / "hooks.yaml").write_text(yaml.safe_dump({"hooks": {k: self.hook_cmd(v) for k, v in machine_hooks.items()}}), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")
        self.run = self.cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]

    def hook_cmd(self, tag: str) -> str:
        return _cmdline([sys.executable, str(self.hook_py), str(self.hook_log)]) + f" {tag}"

    def behave(self, mode: str, **kw: object) -> None:
        self.behavior.write_text(json.dumps({"mode": mode, **kw}), encoding="utf-8")

    @property
    def baton(self) -> Path:
        return self.project / ".baton"

    def events(self) -> list[dict]:
        p = self.baton / "runs" / self.run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def types(self, step: str = "describe") -> list[str]:
        return [e["type"] for e in self.events() if e["step_path"] == step and not e["type"].startswith("completion_hook_")]

    def hooks(self) -> list[dict]:
        if not self.hook_log.exists():
            return []
        return [json.loads(line) for line in self.hook_log.read_text(encoding="utf-8").splitlines()]

    def marker(self, dispatch_id: str) -> dict | None:
        p = self.baton / "cache" / "running" / f"{dispatch_id}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def api(self) -> Api:
        return Api.open(self.project, director_id="alice@host1", home=self.home)


def _until(cond, timeout: float = 30.0, every: float = 0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(every)
    raise AssertionError("condition not met in time")


def _cmdline(argv: list[str]) -> str:
    """A command line for the platform shell (``/bin/sh`` or ``cmd.exe``)."""
    import shlex

    return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)


def _dead(pid: int) -> bool:
    return not supervisor.pid_alive(pid)


def _kill(pid: int | None) -> None:
    """Kill a worker and everything it started."""
    if pid:
        supervisor.kill_tree_pid(pid)


def _kill_one(pid: int) -> None:
    """Kill one process (the supervisor), not its children."""
    if os.name == "posix":
        os.kill(pid, signal.SIGKILL)
    else:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


# ---------------------------------------------------------------------------
# Dispatch returns once started; the supervisor finishes the work
# ---------------------------------------------------------------------------


def test_dispatch_returns_once_started_and_the_supervisor_finishes(tmp_path):
    s = Setup(tmp_path, hooks={"on_complete": "done"})
    gate = tmp_path / "go"
    s.behave("gate", gate=str(gate), output=GOOD_PROFILE)
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot")
    assert "outcome" not in d and d["worker_pid"] and d["supervisor_pid"] and d["effort"] == "M", d
    m = s.marker(d["dispatch_id"])
    assert m["worker_pid"] == d["worker_pid"] and m["step_path"] == "describe" and m["deadline"] == d["deadline"]
    st = s.cli.run("status", s.run)
    live = st["running"][0]["liveness"]
    assert live["marker"] and live["supervisor_alive"] and live["worker_alive"] and not live["overdue"]
    gate.touch()
    w = s.cli.run("wait", s.run, "--dispatch", d["dispatch_id"])
    assert w["results"][0]["outcome"] == "passed" and w["results"][0]["worker_exit"]["exit_code"] == 0, w
    assert s.marker(d["dispatch_id"]) is None
    assert s.cli.run("status", s.run)["steps"]["describe"]["state"] == "passed"
    assert "describe passed" in git(s.project, "log", "-1", "--format=%s")
    assert git(s.project, "status", "--porcelain", ".baton/runs") == ""  # hook events committed with the checkpoint
    assert [h["BATON_OUTCOME"] for h in s.hooks()] == ["passed"]
    disp = next(e for e in s.events() if e["type"] == "dispatched")
    assert disp["data"]["effort"] == "M" and disp["data"]["effort_source"] == "default" and disp["data"]["deadline"] == d["deadline"]
    manifest = json.loads((s.baton / "runs" / s.run / "steps" / "describe" / "attempt-1" / "packet" / "manifest.json").read_text())
    assert manifest["deadline"] == d["deadline"] and manifest["effort"] == "M"


def test_dispatch_survives_its_callers_shell_exiting(tmp_path):
    """The Director's shell and everything it started end; the dispatched work does not.

    POSIX: SIGKILL to the caller's whole session. Windows: the caller runs in a
    kill-on-close job object (what terminals and CI runners use), which is closed.
    """
    s = Setup(tmp_path)
    gate = tmp_path / "go"
    s.behave("gate", gate=str(gate), output=GOOD_PROFILE)
    out = tmp_path / "dispatch.json"
    env = {**os.environ, "BATON_HOME": str(s.home), "BATON_DIRECTOR": "alice@host1", "BATON_PROJECT": str(s.project)}
    if os.name == "posix":
        shell = subprocess.Popen(
            ["/bin/sh", "-c", f"{sys.executable} -m baton dispatch {s.run} describe --worker bot --json > {out}; sleep 600"],
            env=env, start_new_session=True,
        )
        d = _until(lambda: out.exists() and out.stat().st_size and json.loads(out.read_text()), 60)
        os.killpg(shell.pid, signal.SIGKILL)
        shell.wait()
    else:
        caller = (
            "import subprocess, sys, time; sys.stdin.readline(); "
            f"f = open({str(out)!r}, 'w'); "
            f"subprocess.run([sys.executable, '-m', 'baton', 'dispatch', {s.run!r}, 'describe', '--worker', 'bot', '--json'], stdout=f); "
            "f.close(); time.sleep(600)"
        )
        shell = subprocess.Popen([sys.executable, "-c", caller], env=env, stdin=subprocess.PIPE)
        job = _WinJob()
        job.assign(shell)  # before it starts anything: it waits for a line on stdin
        shell.stdin.write(b"go\n")
        shell.stdin.flush()
        d = _until(lambda: out.exists() and out.stat().st_size and json.loads(out.read_text()), 60)
        if job.contains(d["supervisor_pid"]):
            job.close()
            pytest.skip("this environment's job objects forbid breaking away; the supervisor lives only as long as the caller's job")
        job.close()  # kill-on-close: the caller and everything still in the job
        shell.wait(timeout=30)
    assert not _dead(d["supervisor_pid"]) and not _dead(d["worker_pid"])
    gate.touch()
    w = s.cli.run("wait", s.run, "--timeout", "60")
    assert w["results"][0]["outcome"] == "passed" and not w["timed_out"], w
    assert s.types()[-1] == "step_passed"


class _WinJob:
    """A kill-on-close Windows job object that allows breaking away (ctypes)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ct, self.wt = ctypes, wintypes
        k = self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.OpenProcess.restype = wintypes.HANDLE
        self.h = k.CreateJobObjectW(None, None)

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class EXT(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = EXT()
        info.Basic.LimitFlags = 0x2000 | 0x0800  # KILL_ON_JOB_CLOSE | BREAKAWAY_OK
        assert k.SetInformationJobObject(wintypes.HANDLE(self.h), 9, ctypes.byref(info), ctypes.sizeof(info))

    def _proc(self, pid: int):
        return self.k.OpenProcess(0x1000 | 0x0100 | 0x0001, False, pid)  # query | set quota | terminate

    def assign(self, proc: subprocess.Popen) -> None:
        h = self._proc(proc.pid)
        assert self.k.AssignProcessToJobObject(self.wt.HANDLE(self.h), self.wt.HANDLE(h)), self.ct.get_last_error()
        self.k.CloseHandle(self.wt.HANDLE(h))

    def contains(self, pid: int) -> bool:
        h = self._proc(pid)
        res = self.wt.BOOL()
        self.k.IsProcessInJob(self.wt.HANDLE(h), self.wt.HANDLE(self.h), self.ct.byref(res))
        self.k.CloseHandle(self.wt.HANDLE(h))
        return bool(res.value)

    def close(self) -> None:
        if self.h:
            self.k.CloseHandle(self.wt.HANDLE(self.h))
            self.h = None


def test_dispatch_with_wait_blocks_until_recorded(tmp_path):
    s = Setup(tmp_path, hooks={"on_complete": "c"})
    res = s.cli("dispatch", s.run, "describe", "--worker", "bot", "--wait")
    assert res.payload["outcome"] == "passed" and res.payload["warnings"] == []


# ---------------------------------------------------------------------------
# Hooks fire for every outcome
# ---------------------------------------------------------------------------


def test_hooks_fire_for_passed_gate_failed_needs_human_timed_out_and_crashed(tmp_path):
    # 5 s: long enough for any worker to start under load, short enough for the hang to time out.
    s = Setup(tmp_path, hooks={"on_complete": "complete"}, effort_cfg={"bands": {"M": "5s"}, "extend_once": False})
    bot = ("dispatch", s.run, "describe", "--worker", "bot", "--wait")

    s.behave("bad")
    assert s.cli(*bot, expect=1).payload["outcome"] == "retry"  # gate failed
    s.behave("crash")
    assert s.cli(*bot, expect=4).payload["outcome"] == "escalated"  # crashed: no result
    s.cli.run("decide", s.run, "describe", "retry", "--note", "try again")
    s.behave("hang")
    assert s.cli(*bot, expect=1).payload["outcome"] == "retry"  # timed out after the 5 s band
    s.behave("good", output=GOOD_PROFILE)
    assert s.cli.run(*bot)["outcome"] == "passed"
    s.behave("good", output=VERDICT)
    assert s.cli(*("dispatch", s.run, "assess", "--worker", "bot", "--wait"), expect=4).payload["outcome"] == "needs_human"

    got = [(h["BATON_STEP_PATH"], h["BATON_OUTCOME"]) for h in s.hooks()]
    assert got == [
        ("describe", "gate_failed"), ("describe", "failed"), ("describe", "timed_out"), ("describe", "passed"), ("assess", "needs_human"),
    ]
    crashed = s.hooks()[1]
    assert crashed["BATON_CLASSIFICATION"] == "unknown" and crashed["BATON_STEP_STATE"] == "escalated"
    assert all(h["BATON_RUN_ID"] == s.run and h["BATON_REPO"] == str(s.project) and h["BATON_DISPATCH_ID"].startswith("d_") for h in s.hooks())
    assert Path(s.hooks()[3]["BATON_RECORD"]).is_file()
    fired = [e for e in s.events() if e["type"] == "completion_hook_fired"]
    assert [e["data"]["outcome"] for e in fired] == ["gate_failed", "failed", "timed_out", "passed", "needs_human"]
    assert all(e["data"]["hook"] == "on_complete" and e["data"]["source"] == "project" and "command" not in e["data"] for e in fired)


def test_hook_choice_and_failure_never_change_outcomes(tmp_path):
    s = Setup(tmp_path, hooks={"on_complete": "complete", "on_needs_human": "human"})
    s.behave("good", output=GOOD_PROFILE)
    s.cli.run("dispatch", s.run, "describe", "--worker", "bot", "--wait")
    s.behave("good", output=VERDICT)
    os.environ["HOOK_EXIT"] = "7"
    try:
        d = s.cli("dispatch", s.run, "assess", "--worker", "bot", "--wait", expect=4).payload
    finally:
        del os.environ["HOOK_EXIT"]
    assert d["outcome"] == "needs_human"
    assert [h["argv"] for h in s.hooks()] == [["complete"], ["human"]]
    failed = [e for e in s.events() if e["type"] == "completion_hook_failed"]
    assert len(failed) == 1 and failed[0]["data"]["hook"] == "on_needs_human" and failed[0]["data"]["exit_code"] == 7
    assert s.cli("status", s.run, expect=4).payload["steps"]["assess"]["state"] == "awaiting_human"


def test_machine_hook_secret_is_substituted_and_never_recorded(tmp_path):
    secret = SENTINEL_PREFIX + "wakeurl123456"
    s = Setup(tmp_path, machine_hooks={"on_complete": "secret:wake"})
    (s.home / "secrets").mkdir()
    (s.home / "secrets" / "wake").write_text(secret, encoding="utf-8")
    s.cli.run("dispatch", s.run, "describe", "--worker", "bot", "--wait")
    assert s.hooks()[0]["argv"] == [secret]
    fired = [e for e in s.events() if e["type"] == "completion_hook_fired"]
    assert fired and fired[0]["data"]["source"] == "machine"
    git(s.project, "add", "-A")
    git(s.project, "commit", "-qm", "all", "--allow-empty")
    tracked = subprocess.run(["git", "-C", str(s.project), "grep", "-l", secret], capture_output=True, text=True).stdout
    assert tracked == ""
    assert s.cli("check").exit_code == 0


def test_platform_failure_uses_on_platform_failure(tmp_path):
    s = Setup(tmp_path, hooks={"on_complete": "complete", "on_platform_failure": "platform"}, script_gate="baton-no-such-command-xyz")
    s.behave("good", output=GOOD_PROFILE)
    d = s.cli("dispatch", s.run, "describe", "--worker", "bot", "--wait", expect=4).payload
    assert d["outcome"] == "escalated" and any("executable_not_found" in r for r in d["reasons"]), d
    cls = [e for e in s.events() if e["type"] == "failure_classified"][-1]["data"]
    assert cls["class"] == "platform" and cls["code"] == "executable_not_found" and cls["gate"] == 1
    assert [h["argv"] for h in s.hooks()] == [["platform"]] and s.hooks()[0]["BATON_CLASSIFICATION"] == "platform"


# ---------------------------------------------------------------------------
# The running-marker table (§8.7), row by row
# ---------------------------------------------------------------------------


def test_marker_present_process_alive_is_running_and_overdue_past_deadline(tmp_path):
    s = Setup(tmp_path)
    s.behave("hang")
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot")
    api = s.api()
    try:
        assert api.reconcile(s.run) == [{"step_path": "describe", "attempt": 1, "dispatch_id": d["dispatch_id"], "action": "running", "overdue": False, "deadline": d["deadline"]}]
        # The supervisor holds its real deadline (2 h, the M band) in memory; the marker
        # is what reconciliation reads, so backdating it shows a live, overdue worker.
        m = s.marker(d["dispatch_id"])
        m["deadline"] = "2000-01-01T00:00:00.000000Z"
        (s.baton / "cache" / "running" / f"{d['dispatch_id']}.json").write_text(json.dumps(m))
        acts = api.reconcile(s.run)
        assert acts[0]["action"] == "running" and acts[0]["overdue"] is True
        assert s.cli.run("status", s.run)["running"][0]["liveness"]["overdue"] is True
        assert s.types()[-1] == "step_running"
    finally:
        _kill(d["worker_pid"])
        _kill_one(d["supervisor_pid"])
        api.close()


def test_marker_present_process_dead_result_written_finishes_intake(tmp_path):
    s = Setup(tmp_path, hooks={"on_complete": "x"})
    s.behave("result_then_hang", output=GOOD_PROFILE)
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot")
    _until(lambda: (s.baton / "runs" / s.run / "steps" / "describe" / "attempt-1" / "result" / "result.json").exists())
    _kill_one(d["supervisor_pid"])  # the supervisor dies; the worker lingers
    _until(lambda: _dead(d["supervisor_pid"]))
    r = s.cli.run("resume", s.run)
    assert {"step_path": "describe", "attempt": 1, "dispatch_id": d["dispatch_id"], "action": "intake", "outcome": "passed"} in r["reconciled"]
    assert s.types()[-1] == "step_passed" and "attempt_orphaned" not in s.types()
    assert _until(lambda: _dead(d["worker_pid"]), 10)  # the unsupervised worker is stopped
    assert s.marker(d["dispatch_id"]) is None
    assert [h["BATON_OUTCOME"] for h in s.hooks()] == ["passed"]


def test_marker_present_process_dead_no_result_is_orphaned_and_classified(tmp_path):
    s = Setup(tmp_path)
    s.behave("hang")
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot")
    _kill_one(d["supervisor_pid"])
    _until(lambda: _dead(d["supervisor_pid"]))
    r = s.cli("resume", s.run, expect=4).payload
    assert r["reconciled"][0]["action"] == "orphaned"
    assert s.types()[-3:] == ["attempt_orphaned", "failure_classified", "step_escalated"]
    cls = [e for e in s.events() if e["type"] == "failure_classified"][-1]["data"]
    assert cls == {"class": "platform", "code": "supervisor_died", "message": cls["message"]}
    assert _until(lambda: _dead(d["worker_pid"]), 10)
    assert s.marker(d["dispatch_id"]) is None
    assert r["pending_decisions"][0]["reason"] == "platform"


def test_marker_absent_after_intake_is_finished(tmp_path):
    s = Setup(tmp_path)
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot", "--wait")
    assert d["outcome"] == "passed" and s.marker(d["dispatch_id"]) is None
    before = s.events()
    r = s.cli.run("resume", s.run)
    assert r["reconciled"] == [] and r["running"] == []
    assert [e["type"] for e in s.events()[len(before):] if e["step_path"]] == []


def test_running_attempt_without_any_marker_counts_as_a_dead_supervisor(tmp_path):
    s = Setup(tmp_path)
    s.behave("hang")
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot")
    _kill_one(d["supervisor_pid"])
    _kill(d["worker_pid"])
    _until(lambda: _dead(d["supervisor_pid"]))
    (s.baton / "cache" / "running" / f"{d['dispatch_id']}.json").unlink()
    s.cli("resume", s.run, expect=4)
    assert s.types()[-3:] == ["attempt_orphaned", "failure_classified", "step_escalated"]


# ---------------------------------------------------------------------------
# Effort bands: extend once, then terminate and classify
# ---------------------------------------------------------------------------


def test_overdue_s_step_is_extended_once_then_terminated_and_classified(tmp_path):
    s = Setup(tmp_path, effort="S", effort_cfg={"bands": {"S": "1s"}, "extend_once": True}, hooks={"on_complete": "c"})
    s.behave("hang")
    t0 = time.monotonic()
    d = s.cli("dispatch", s.run, "describe", "--worker", "bot", "--wait", expect=1).payload
    assert time.monotonic() - t0 >= 2.0
    assert d["outcome"] == "retry" and d["effort"] == "S", d
    types = s.types()
    i = types.index("deadline_extended")
    assert types[i:] == ["deadline_extended", "step_timed_out", "failure_classified", "step_ready"]
    assert types.count("deadline_extended") == 1
    ext = next(e for e in s.events() if e["type"] == "deadline_extended")["data"]
    assert ext["previous_deadline"] == d["deadline"] and ext["deadline"] > d["deadline"] and ext["band"] == "S"
    cls = [e for e in s.events() if e["type"] == "failure_classified"][-1]["data"]
    assert cls["class"] == "subject" and cls["code"] == "timeout"
    assert [h["BATON_OUTCOME"] for h in s.hooks()] == ["overdue", "timed_out"]
    assert s.cli.run("status", s.run)["steps"]["describe"]["state"] == "ready"


def test_manual_workers_get_an_informational_deadline_and_no_supervisor(tmp_path):
    s = Setup(tmp_path, effort="L")
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "owner")
    assert d["effort"] == "L" and d["deadline"] and "supervisor_pid" not in d and "outcome" not in d
    assert not (s.baton / "cache" / "running").exists() or not list((s.baton / "cache" / "running").iterdir())


# ---------------------------------------------------------------------------
# No hook: the warning
# ---------------------------------------------------------------------------


def _text(s: Setup, *args: str):
    from typer.testing import CliRunner

    from baton.cli import app

    runner = CliRunner(env={"BATON_HOME": str(s.home), "BATON_DIRECTOR": "alice@host1", "BATON_PROJECT": str(s.project)})
    return runner.invoke(app, list(args))


def test_wake_path_is_a_hook_that_fires_for_a_step_waiting_on_the_owner(tmp_path):
    s = Setup(tmp_path, hooks={"on_platform_failure": "p"})
    assert supervisor.wake_path(s.api().project) is None  # only on_platform_failure: nothing fires for needs_human
    for hooks, machine, want in (({"on_needs_human": "n"}, None, "on_needs_human"), ({"on_complete": "c"}, None, "on_complete"),
                                 ({"on_platform_failure": "p"}, {"on_complete": "c"}, "on_complete")):
        t = Setup(tmp_path / want / str(bool(machine)), hooks=hooks, machine_hooks=machine)
        assert supervisor.wake_path(t.api().project) == want
    (s.home / "hooks.yaml").write_text("hooks: [not, a, mapping]\n", encoding="utf-8")
    assert supervisor.wake_path(s.api().project) is None  # a machine file that does not load fires nothing


@pytest.mark.parametrize(("seconds", "want"), [(60, "about a minute"), (45 * 60, "about 45 minutes"), (3600, "about 1 hour"),
                                               (90 * 60, "about 90 minutes"), (7200, "about 2 hours"), (2.5 * 3600, "about 2.5 hours")])
def test_wake_durations_are_plain_words(seconds, want):
    assert supervisor.duration_text(seconds) == want


def test_eligible_reports_the_wake_path_and_the_owners_notice_from_the_band(tmp_path):
    s = Setup(tmp_path, effort="L")
    wake = s.cli.run("eligible", s.run, "describe")["wake"]
    assert wake == {"configured": False, "expected": "4h", "notice": (
        "I might not notice when this part finishes. It can take up to about 4 hours (a little longer if it runs over). "
        "If you haven't heard from me by then, ask me to check on it.")}
    for word in ("step", "dispatch", "hook", "worker", "Baton", "packet"):
        assert word not in wake["notice"]
    text = _text(s, "eligible", s.run, "describe")
    assert "Before ending your turn, tell the owner" in text.stdout and wake["notice"] in text.stdout

    s2 = Setup(tmp_path / "once-off", effort_cfg={"bands": {"M": "45m"}, "extend_once": False})
    wake2 = s2.cli.run("eligible", s2.run, "describe")["wake"]
    assert wake2["expected"] == "45m" and "about 45 minutes." in wake2["notice"] and "runs over" not in wake2["notice"]

    s3 = Setup(tmp_path / "hooked", hooks={"on_needs_human": "n"})
    assert s3.cli.run("eligible", s3.run, "describe")["wake"] == {"configured": True, "hook": "on_needs_human"}
    assert "tell the owner" not in _text(s3, "eligible", s3.run, "describe").stdout


def test_a_step_only_a_person_can_do_gets_no_notice(tmp_path):
    s = Setup(tmp_path)
    (s.baton / "preferences.yaml").write_text("exclude: [bot]\n", encoding="utf-8")
    out = s.cli.run("eligible", s.run, "describe")
    assert [e["adapter"] for e in out["eligible"]] == ["manual"]
    assert out["wake"] == {"configured": False}
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "owner")
    assert d["warnings"] == []  # the Director hands the result in itself


def test_dispatch_warns_with_no_wake_path_with_or_without_wait(tmp_path):
    s = Setup(tmp_path)
    res = _text(s, "dispatch", s.run, "describe", "--worker", "bot")
    assert res.exit_code == 0, res.stdout
    assert "WARNING: no completion hook would wake you when this needs the owner" in res.stderr
    assert "wake.notice" in res.stderr and "baton wait" in res.stdout
    s.api().wait(s.run, timeout=60)

    s2 = Setup(tmp_path / "waiting")
    d = s2.cli.run("dispatch", s2.run, "describe", "--worker", "bot", "--wait")
    assert d["outcome"] and any(w.startswith(supervisor.NO_WAKE_WARNING) for w in d["warnings"]), d

    s3 = Setup(tmp_path / "platform-only", hooks={"on_platform_failure": "p"})
    res3 = _text(s3, "dispatch", s3.run, "describe", "--worker", "bot", "--wait")
    assert f"WARNING: {supervisor.NO_WAKE_WARNING}" in res3.stderr, (res3.stdout, res3.stderr)

    s4 = Setup(tmp_path / "hooked", hooks={"on_complete": "c"})
    res4 = _text(s4, "dispatch", s4.run, "describe", "--worker", "bot")
    assert res4.exit_code == 0 and "WARNING" not in res4.stderr
    s4.api().wait(s4.run, timeout=60)


def test_doctor_warns_with_no_wake_path_and_reports_a_problem_for_a_detached_lease(tmp_path):
    s = Setup(tmp_path)
    rep = s.cli("doctor", "--no-run", expect=None).payload
    assert any(w.startswith("no completion hook would wake a Director") for w in rep["warnings"]), rep["warnings"]
    assert not [p for p in rep["problems"] if "would wake" in p]
    det = s.cli("detect", expect=None).payload  # the routine check stays quiet for an attached Director (decision 0061)
    assert not [x for x in det["problems"] + det["warnings"] if "would wake" in x], det

    api = s.api()
    api.lease(s.run, "release")
    Api.open(s.project, director_id="alice@host1", harness="claude-web", home=s.home).lease(s.run, "claim")
    rep = s.cli("doctor", "--no-run", expect=None).payload
    probs = [p for p in rep["problems"] if "would wake" in p]
    assert probs and s.run in probs[0] and "claude-web" in probs[0], rep["problems"]
    assert not [w for w in rep["warnings"] if "would wake" in w]
    det = s.cli("detect", expect=None).payload
    assert any("would wake" in p and "claude-web" in p for p in det["problems"]), det

    s2 = Setup(tmp_path / "hooked", hooks={"on_needs_human": "n"})
    rep2 = s2.cli("doctor", "--no-run", expect=None).payload
    assert not [x for x in rep2["problems"] + rep2["warnings"] if "would wake" in x]


# ---------------------------------------------------------------------------
# Classification rules, state, config, doctor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exit_code", "tail", "signals", "want"),
    [
        (1, "write failed: No space left on device\n", None, ("platform", "disk_full")),
        (1, "curl: (6) Could not resolve host: api.example\n", None, ("platform", "network_dns")),
        (1, "Error: connect ECONNREFUSED 127.0.0.1:443\n", None, ("platform", "network")),
        (127, "", None, ("platform", "executable_not_found")),
        (-9, "", None, ("platform", "killed")),
        (137, "", None, ("platform", "killed")),
        (1, "boom\n", None, ("unknown", "exit_1")),
        (1, "Not logged in\n", [{"pattern": "Not logged in", "class": "platform", "code": "auth_failed"}], ("platform", "auth_failed")),
        (1, "No space left on device\nbaton-worker: failure=configuration code=bad_model message=x\n", None, ("configuration", "bad_model")),
    ],
)
def test_classification_rules(exit_code, tail, signals, want):
    got = classify.classify_exit(exit_code, tail.encode(), signals)
    assert (got["class"], got["code"]) == want


def test_gate_classification_uses_only_gate_scoped_rules():
    assert classify.classify_gate(127)["code"] == "executable_not_found"
    assert classify.classify_gate(126)["code"] == "not_executable"
    assert classify.classify_gate(9009)["code"] == "executable_not_found"
    cmd_msg = b"'pytest' is not recognized as an internal or external command,\r\noperable program or batch file.\r\n"
    assert classify.classify_gate(1, cmd_msg)["code"] == "executable_not_found"
    assert classify.classify_gate(1, b"test_perms: Permission denied\n2 failed\n") is None  # a failing test suite
    assert classify.classify_gate(1) is None
    assert classify.classify_gate(None) is None


def test_classification_messages_are_redacted():
    got = classify.classify_exit(1, f"Could not resolve host {SENTINEL_PREFIX}abcdefgh\n".encode())
    assert SENTINEL_PREFIX not in got["message"]


def test_rules_file_is_versioned():
    assert classify.load_rules()["id"] == "baton-classify-rules/1"


def test_deadline_extended_only_while_running():
    assert next_step_state(StepState("running", 1), "deadline_extended", 1, 3).state == "running"
    for frm in ("ready", "verifying", "passed", "timed_out"):
        with pytest.raises(IllegalTransition):
            next_step_state(StepState(frm, 1), "deadline_extended", 1, 3)


def test_effort_config_validation(tmp_path):
    from baton.project import load_config

    p = tmp_path / "project.yaml"
    p.write_text("effort: { bands: { S: soon } }\n", encoding="utf-8")
    cfg, issues = load_config(p)
    assert cfg is None and issues and "not a duration" in issues[0].message
    p.write_text("effort: { bands: { S: 90s }, default: L }\n", encoding="utf-8")
    cfg, issues = load_config(p)
    assert not issues and cfg.effort.seconds("S") == 90 and cfg.effort.seconds("M") == 7200 and cfg.effort.default == "L"
    p.write_text("hooks: { on_complete: 'curl secret:x' }\n", encoding="utf-8")
    assert load_config(p)[1][0].code == "project.secret_reference"


def test_doctor_checks_supervisor_and_hooks(tmp_path):
    s = Setup(tmp_path, hooks={"on_complete": "c"})
    rep = s.cli("doctor", "--no-run", expect=None).payload
    assert not [p for p in rep["problems"] if "supervisor" in p or "hook" in p], rep["problems"]
    (s.home / "hooks.yaml").write_text("hooks:\n  on_complete: 'no-such-wake-tool secret:nowhere'\n  on_needs_human: 'no-such-wake-tool now'\n", encoding="utf-8")
    rep = s.cli("doctor", "--no-run", expect=None).payload
    probs = [p for p in rep["problems"] if "hook" in p]
    assert any("on_complete" in p and "nowhere" in p for p in probs), probs
    assert any("on_needs_human" in p and "not found on PATH" in p for p in probs), probs


# ---------------------------------------------------------------------------
# Exit codes: 4 is "finished, the owner is needed"; BATON_OWNER_EXIT=0 (decision 0057)
# ---------------------------------------------------------------------------


def test_owner_exit_zero_makes_owner_needed_exit_0_and_keeps_needs_owner(tmp_path, monkeypatch):
    s = Setup(tmp_path)
    s.cli.run("dispatch", s.run, "describe", "--worker", "bot", "--wait")
    s.behave("good", output=VERDICT)
    monkeypatch.setenv("BATON_OWNER_EXIT", "0")
    d = s.cli("dispatch", s.run, "assess", "--worker", "bot", "--wait", expect=0).payload
    assert d["outcome"] == "needs_human" and d["needs_owner"] is True
    for args in (("wait", s.run), ("status", s.run), ("resume", s.run), ("board",)):
        assert s.cli(*args, expect=0).payload["needs_owner"] is True, args
    monkeypatch.setenv("BATON_OWNER_EXIT", "4")
    assert s.cli("status", s.run, expect=4).payload["needs_owner"] is True
    monkeypatch.delenv("BATON_OWNER_EXIT")
    assert s.cli("wait", s.run, expect=4).payload["needs_owner"] is True  # the default stays 4


def test_a_bad_owner_exit_value_is_a_usage_error_before_any_work(tmp_path, monkeypatch):
    s = Setup(tmp_path)
    before = len(s.events())
    monkeypatch.setenv("BATON_OWNER_EXIT", "1")
    res = s.cli("dispatch", s.run, "describe", "--worker", "bot", "--wait", expect=2)
    assert res.payload["error"] == "usage.owner_exit" and "must be 0 or 4" in res.payload["message"]
    assert len(s.events()) == before  # nothing was dispatched
    text = _text(s, "status", s.run)
    assert text.exit_code == 2 and "BATON_OWNER_EXIT must be 0 or 4" in text.stderr


@pytest.mark.parametrize(("value", "want"), [(None, 4), ("4", 4), ("0", 0), ("", 4)])
def test_every_owner_needed_exit_goes_through_one_place(value, want, monkeypatch, capsys):
    """``cli._done`` is the only owner-needed exit (``decide`` and every other command use it)."""
    import typer

    from baton import cli

    if value is None:
        monkeypatch.delenv("BATON_OWNER_EXIT", raising=False)
    else:
        monkeypatch.setenv("BATON_OWNER_EXIT", value)
    for payload, code in (({"needs_owner": True}, want), ({"needs_owner": False}, 0)):
        with pytest.raises(typer.Exit) as e:
            cli._done(payload, True, "")
        assert e.value.exit_code == code
    capsys.readouterr()
