"""Phase 10: work items (L5, §8.9).

Two runs of different recipes progress independently in one repo; two
write-mode steps from different runs are serialized by the workspace lock and
its queue (the releasing process starts the next one); checkpoint commits never
include another run's files; ``revise`` on a design marks only that run's
dependents stale, and a stale step can be confirmed by the owner without
rerunning. Plus ``board``, ``cancel``, ``limits.active_runs``.
"""

from __future__ import annotations

import pytest

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import yaml

from baton import locks
from conftest import FIT_CHECK
from projectkit import FIT_INPUTS, GOOD_PROFILE, VERDICT, Cli, git, make_git_project, make_home, packet_dir, write_result
from runkit import make_recipe

WORKER = Path(__file__).resolve().parent / "fakes" / "scripted_worker.py"
CAPS = ["human_judgment", "structured_output", "long_form_writing", "technical_reasoning", "file_write", "repo_workspace", "workspace_read"]
OBJ = {"type": "object"}


def _cmdline(argv: list[str]) -> str:
    return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)


def _until(cond, timeout: float = 30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def _profiles(tmp: Path, behavior: Path, hook_log: Path | None = None) -> str:
    owner = f"owner:\n  adapter: manual\n  vendor: human\n  person: owner\n  capabilities: {json.dumps(CAPS)}\n  tier: strong\n"
    bot = (
        f"bot:\n  adapter: command\n  vendor: other\n"
        f"  command: {json.dumps(_cmdline([sys.executable, str(WORKER), '{packet}', '{result}', str(behavior)]))}\n"
        f"  capabilities: {json.dumps(CAPS[1:])}\n  tier: strong\n"
    )
    return owner + bot


def _toy(root: Path, write: bool = False) -> Path:
    """design -> build -> docs, plus an independent `other` (the §16 Phase 10 revise case).

    With ``write``, ``build`` is a write-mode workspace step.
    """
    build: dict = {"id": "build", "depends_on": ["design"], "output_schema": "schemas/out.json",
                   "inputs": [{"name": "design", "from": "steps.design.output", "required": True}]}
    if write:
        build["workspace"] = "write"
    return make_recipe(
        root,
        [
            {"id": "design", "output_schema": "schemas/out.json"},
            build,
            {"id": "docs", "depends_on": ["build"], "output_schema": "schemas/out.json",
             "inputs": [{"name": "build", "from": "steps.build.output", "required": True}]},
            {"id": "other", "output_schema": "schemas/out.json"},
        ],
        schemas={"out.json": OBJ},
        run_inputs={"type": "object", "properties": {"title": {"type": "string"}}},
    )


class Project:
    def __init__(self, tmp_path: Path, *, write: bool = False, hooks: bool = False, config: dict | None = None):
        self.tmp = tmp_path
        self.behavior = tmp_path / "behavior.json"
        self.behave("good")
        self.hook_log = tmp_path / "hooks.jsonl"
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home", _profiles(tmp_path, self.behavior))
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project))
        self.cli.run("vendor", str(FIT_CHECK))
        self.cli.run("vendor", str(_toy(tmp_path / "toy", write=write)))
        py = self.project / ".baton" / "project.yaml"
        cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
        if hooks:
            hook = tmp_path / "hook.py"
            hook.write_text(
                "import json, os, sys\n"
                "with open(sys.argv[1], 'a', encoding='utf-8') as f:\n"
                "    f.write(json.dumps({k: v for k, v in os.environ.items() if k.startswith('BATON_')}) + '\\n')\n",
                encoding="utf-8",
            )
            cfg["hooks"] = {"on_complete": _cmdline([sys.executable, str(hook), str(self.hook_log)])}
        cfg.update(config or {})
        py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")

    def behave(self, mode: str, **kw: object) -> None:
        self.behavior.write_text(json.dumps({"mode": mode, "output": {}, **kw}), encoding="utf-8")

    def toy(self, title: str) -> str:
        return self.cli.run("start", "toy", "--inputs", json.dumps({"title": title}))["run_id"]

    def by_hand(self, run: str, step: str, output: object = None) -> dict:
        """Dispatch to the owner, write the result, submit."""
        d = self.cli.run("dispatch", run, step, "--worker", "owner")
        write_result(packet_dir(self.project, run, step, d["attempt"]), {} if output is None else output)
        return self.cli("submit", run, step, expect=None).payload

    def events(self, run: str) -> list[dict]:
        p = self.project / ".baton" / "runs" / run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def types(self, run: str, step: str) -> list[str]:
        return [e["type"] for e in self.events(run) if e["step_path"] == step and not e["type"].startswith("completion_hook_")]

    def state(self, run: str, step: str) -> str:
        return self.cli.run("status", run, expect=None)["steps"][step]["state"]

    def hooks(self) -> list[dict]:
        return [json.loads(x) for x in self.hook_log.read_text(encoding="utf-8").splitlines()] if self.hook_log.exists() else []


# ---------------------------------------------------------------------------
# Concurrent runs, board, checkpoints
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_two_runs_of_different_recipes_progress_independently(tmp_path):
    p = Project(tmp_path)
    fit = p.cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    toy = p.toy("Widget")
    assert fit != toy

    # Interleave work on both runs.
    p.by_hand(fit, "describe", GOOD_PROFILE)
    p.by_hand(toy, "design", {"v": 1})
    p.by_hand(toy, "other")
    p.by_hand(fit, "assess", VERDICT)  # fit-check now waits on its human gate
    p.by_hand(toy, "build")

    board = p.cli("board", expect=4).payload  # one run owes an owner decision
    runs = {r["run_id"]: r for r in board["runs"]}
    assert set(runs) == {fit, toy}
    assert runs[toy]["recipe"] == "toy@1" and runs[fit]["recipe"] == "fit-check@3"
    assert runs[toy]["position"] == {"done": 3, "total": 4, "current": ["docs"]}
    assert runs[toy]["ready"] == ["docs"] and not runs[toy]["needs_owner"]
    assert runs[fit]["needs_owner"] and runs[fit]["pending_decisions"][0]["ref"] == "assess"
    assert runs[fit]["lease"]["yours"]
    needs = p.cli("board", "--needs-me", expect=4).payload
    assert [r["run_id"] for r in needs["runs"]] == [fit]

    # Each run's log holds only its own steps; finishing one leaves the other where it was.
    assert {e["step_path"] for e in p.events(fit) if e["step_path"]} <= {"describe", "assess"}
    assert {e["step_path"] for e in p.events(toy) if e["step_path"]} <= {"design", "build", "docs", "other"}
    p.cli.run("decide", fit, "assess", "approve", "--note", "Go ahead.")
    assert p.cli.run("status", fit)["state"] == "completed"
    assert p.cli.run("status", toy)["steps"]["docs"]["state"] == "ready"
    board = p.cli.run("board")
    assert [r["run_id"] for r in board["runs"]] == [toy]  # terminal runs leave the board
    assert p.cli("board", "--needs-me").payload["runs"] == []
    p.by_hand(toy, "docs")
    assert p.cli.run("status", toy)["state"] == "completed"
    assert p.cli.run("board")["runs"] == []


@pytest.mark.slow
def test_checkpoint_commits_never_include_another_runs_files(tmp_path):
    p = Project(tmp_path)
    a, b = p.toy("Alpha"), p.toy("Beta")
    # Run B has uncommitted files of its own: a packet built for an attempt in flight.
    p.cli.run("dispatch", b, "design", "--worker", "owner")
    b_dir = f".baton/runs/{b}/"
    assert any(line[3:].startswith(b_dir) for line in git(p.project, "status", "--porcelain", "-uall").splitlines())

    head = git(p.project, "rev-parse", "HEAD").strip()
    p.by_hand(a, "design")
    p.by_hand(a, "other")
    commits = git(p.project, "rev-list", f"{head}..HEAD").split()
    assert commits
    for sha in commits:
        files = [f for f in git(p.project, "show", "--name-only", "--format=", sha).splitlines() if f]
        assert files and all(f.startswith(f".baton/runs/{a}/") for f in files), files
        assert f"baton({a}):" in git(p.project, "log", "-1", "--format=%s", sha)
    # B's work is still uncommitted and intact.
    assert any(line[3:].startswith(b_dir) for line in git(p.project, "status", "--porcelain", "-uall").splitlines())
    write_result(packet_dir(p.project, b, "design", 1), {})
    p.cli.run("submit", b, "design")
    last = git(p.project, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert last and all(f.startswith(b_dir) for f in last if f)


@pytest.mark.slow
def test_active_runs_limit_refuses_a_new_run(tmp_path):
    p = Project(tmp_path, config={"limits": {"active_runs": 1}})
    p.toy("One")
    res = p.cli("start", "toy", "--inputs", json.dumps({"title": "Two"}), expect=1)
    assert res.payload["error"] == "limits.active_runs"


# ---------------------------------------------------------------------------
# The workspace lock and queue
# ---------------------------------------------------------------------------


def _ready_to_build(p: Project, title: str) -> str:
    run = p.toy(title)
    p.by_hand(run, "design", {"v": 1})
    return run


@pytest.mark.slow
def test_write_steps_from_two_runs_are_serialized(tmp_path):
    p = Project(tmp_path, write=True, hooks=True)
    a, b = _ready_to_build(p, "Alpha"), _ready_to_build(p, "Beta")
    gate = tmp_path / "go"
    p.behave("gate", gate=str(gate))

    da = p.cli.run("dispatch", a, "build", "--worker", "bot")
    assert da["workspace_lock"] and da["dispatch_id"]
    holder = locks.workspace_holder(p.project / ".baton")
    assert holder["run_id"] == a and holder["dispatch_id"] == da["dispatch_id"] and holder.get("supervisor_pid")
    # The scripted worker reads its behavior file once, when it starts: let A's worker start in `gate` mode before the
    # file is rewritten below (the dispatch returns when the supervisor is up, not the worker; under a loaded machine
    # the worker could read "good" and finish at once, leaving nothing for B to wait on).
    a_log = p.home / "logs" / a / "build" / "attempt-1.log"
    _until(lambda: a_log.exists() and "scripted worker: gate" in a_log.read_text(encoding="utf-8", errors="replace"))

    qb = p.cli.run("dispatch", b, "build", "--worker", "bot")
    assert qb["queued"] and qb["position"] == 1 and qb["holder"] == {"run_id": a, "step_path": "build", "dispatch_id": da["dispatch_id"]}
    assert "dispatched" not in p.types(b, "build") and p.types(b, "build")[-1] == "dispatch_queued"
    st = p.cli.run("status", b)
    assert st["steps"]["build"]["state"] == "ready" and [q["step_path"] for q in st["queued"]] == ["build"]
    board = p.cli.run("board")
    assert board["workspace"] == {"holder": {"run_id": a, "step_path": "build", "dispatch_id": da["dispatch_id"], "attempt": 1}, "queued": 1}
    # Asking again for the same step is refused; read and none steps never wait.
    assert p.cli("dispatch", b, "build", "--worker", "bot", expect=1).payload["error"] == "dispatch.already_queued"
    p.behave("good")
    out = p.cli.run("dispatch", b, "other", "--worker", "bot", "--wait")
    assert out["outcome"] == "passed"
    p.behave("gate", gate=str(gate))
    time.sleep(0.5)
    assert p.state(b, "build") == "ready"  # still waiting: A holds the tree

    gate.write_text("go", encoding="utf-8")
    # A's supervisor finishes intake, releases the tree and starts B's queued dispatch itself.
    _until(lambda: p.state(a, "build") == "passed" and p.state(b, "build") == "passed")
    ev_a, ev_b = p.events(a), p.events(b)
    a_passed = next(e for e in ev_a if e["type"] == "step_passed" and e["step_path"] == "build")
    b_disp = next(e for e in ev_b if e["type"] == "dispatched" and e["step_path"] == "build")
    deq = next(e for e in ev_b if e["type"] == "dispatch_dequeued")
    assert deq["data"]["started"] and deq["data"]["queue_id"] == qb["queue_id"] and deq["data"]["dispatch_id"] == b_disp["data"]["dispatch_id"]
    assert a_passed["ts"] <= b_disp["ts"]  # B started only after A's intake and gates
    assert b_disp["actor"] == "director:alice@host1"  # started as the Director who queued it
    _until(lambda: locks.workspace_holder(p.project / ".baton") is None)
    assert locks.read_queue(p.project / ".baton") == []
    _until(lambda: {h["BATON_RUN_ID"] for h in p.hooks() if h["BATON_STEP_PATH"] == "build" and h["BATON_OUTCOME"] == "passed"} == {a, b})


@pytest.mark.slow
def test_manual_write_step_holds_the_tree_until_submit(tmp_path):
    p = Project(tmp_path, write=True)
    a, b = _ready_to_build(p, "Alpha"), _ready_to_build(p, "Beta")
    da = p.cli.run("dispatch", a, "build", "--worker", "owner")
    assert locks.workspace_holder(p.project / ".baton")["manual"]
    qb = p.cli.run("dispatch", b, "build", "--worker", "owner")
    assert qb["queued"]
    write_result(packet_dir(p.project, a, "build", da["attempt"]), {})
    p.cli.run("submit", a, "build")
    # Submitting released the tree and started B's queued (manual) attempt.
    assert p.state(b, "build") == "running"
    holder = locks.workspace_holder(p.project / ".baton")
    assert holder["run_id"] == b and holder["manual"]
    write_result(packet_dir(p.project, b, "build", 1), {})
    p.cli.run("submit", b, "build")
    assert locks.workspace_holder(p.project / ".baton") is None


@pytest.mark.slow
def test_queued_dispatch_cancel_abandon_and_drop(tmp_path):
    p = Project(tmp_path, write=True, hooks=True)
    a, b, c = (_ready_to_build(p, t) for t in ("Alpha", "Beta", "Gamma"))
    da = p.cli.run("dispatch", a, "build", "--worker", "owner")

    # Withdrawn by the Director.
    qb = p.cli.run("dispatch", b, "build", "--worker", "owner")
    out = p.cli.run("cancel", b, "build")
    assert out["cancelled"] and locks.read_queue(p.project / ".baton") == []
    deq = [e for e in p.events(b) if e["type"] == "dispatch_dequeued"][-1]
    assert deq["data"] == {"queue_id": qb["queue_id"], "started": False, "reason": "withdrawn by the Director", "code": "cancelled"}
    assert p.cli("cancel", b, "build", expect=1).payload["error"] == "cancel.not_queued"

    # Dropped because its run was abandoned.
    p.cli.run("dispatch", b, "build", "--worker", "owner")
    p.cli.run("abandon", b, "--reason", "Not needed.")
    assert locks.read_queue(p.project / ".baton") == []
    assert [e["data"]["code"] for e in p.events(b) if e["type"] == "dispatch_dequeued"] == ["cancelled", "run_ended"]

    # Dropped at start because the worker is no longer on this machine: recorded, and the hook wakes the Director.
    qc = p.cli.run("dispatch", c, "build", "--worker", "bot")
    (p.home / "workers.yaml").write_text(_profiles(tmp_path, p.behavior).split("bot:")[0], encoding="utf-8")
    write_result(packet_dir(p.project, a, "build", da["attempt"]), {})
    p.cli.run("submit", a, "build")
    deq = [e for e in p.events(c) if e["type"] == "dispatch_dequeued"][-1]
    assert not deq["data"]["started"] and deq["data"]["queue_id"] == qc["queue_id"] and deq["data"]["code"] == "configuration.unknown_profile"
    assert p.state(c, "build") == "ready"
    assert any(h["BATON_RUN_ID"] == c and h["BATON_OUTCOME"] == "not_started" for h in p.hooks())
    assert locks.workspace_holder(p.project / ".baton") is None
    # The Director can dispatch it again; the tree is free.
    assert p.cli.run("dispatch", c, "build", "--worker", "owner").get("workspace_lock")


@pytest.mark.slow
def test_a_dead_holder_counts_as_released(tmp_path):
    p = Project(tmp_path, write=True)
    a = _ready_to_build(p, "Alpha")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    locks.take_workspace(p.project / ".baton", {"dispatch_id": "d_gone", "run_id": "r_other", "step_path": "build", "pid": dead.pid})
    assert locks.workspace_holder(p.project / ".baton") is None
    locks.take_workspace(p.project / ".baton", {"dispatch_id": "d_gone", "run_id": "r_other", "step_path": "build", "pid": dead.pid})
    out = p.cli.run("dispatch", a, "build", "--worker", "owner")
    assert out.get("workspace_lock") and locks.workspace_holder(p.project / ".baton")["run_id"] == a


# ---------------------------------------------------------------------------
# revise, stale steps, confirmation
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_revise_marks_only_that_runs_dependents_stale_and_a_stale_step_is_confirmed(tmp_path):
    p = Project(tmp_path)
    one, two = p.toy("One"), p.toy("Two")
    for run in (one, two):
        p.by_hand(run, "design", {"v": 1})
        p.by_hand(run, "build", {"built_from": 1})
    p.by_hand(one, "other")

    out = p.cli.run("revise", one, "design", "--reason", "Wrong units.")
    assert out["stale"] == ["build"]  # docs never ran; other does not depend on design
    st = p.cli.run("status", one)
    assert (st["steps"]["design"]["state"], st["steps"]["build"]["state"], st["steps"]["other"]["state"]) == ("ready", "stale", "passed")
    assert st["stale"] == [{"step_path": "build", "cause": "revised", "revised": "design", "runnable": False,
                            "waiting": "its dependencies are not satisfied again yet: design"}]
    assert p.cli.run("status", two)["steps"]["build"]["state"] == "passed"  # other runs are never affected
    assert not any(e["type"] in ("step_revised", "step_stale") for e in p.events(two))

    # Confirming waits until the dependencies have passed again.
    res = p.cli("decide", one, "build", "confirm", expect=1)
    assert res.payload["error"] == "decide.stale_not_runnable"
    p.by_hand(one, "design", {"v": 2})
    st = p.cli.run("status", one)
    assert st["steps"]["build"]["state"] == "stale" and "build" in st["ready"] and st["stale"][0]["runnable"]
    assert not st["needs_owner"]  # not an owner decision; the Director may simply re-run it
    assert p.cli("decide", one, "build", "approve", expect=1).payload["error"] == "decide.bad_decision"

    attempts_before = [e for e in p.events(one) if e["type"] == "dispatched" and e["step_path"] == "build"]
    out = p.cli.run("decide", one, "build", "confirm", "--note", "Units do not affect the build.")
    assert out["outcome"] == "confirmed"
    ev = p.events(one)
    assert [e for e in ev if e["type"] == "dispatched" and e["step_path"] == "build"] == attempts_before  # not rerun
    hd = [e for e in ev if e["type"] == "human_decision" and e["step_path"] == "build"][-1]
    assert hd["data"]["kind"] == "stale" and hd["data"]["note"] == "Units do not affect the build."
    passes = [e for e in ev if e["type"] == "step_passed" and e["step_path"] == "build"]
    assert passes[-1]["data"]["confirmed"]["decision_seq"] == hd["seq"]
    assert passes[-1]["data"]["output_sha256"] == passes[-2]["data"]["output_sha256"]
    assert "confirmed unchanged by the owner" in p.cli("record", one, "build").stdout

    # docs depends on the confirmed result: its packet gets the earlier build output.
    d = p.cli.run("dispatch", one, "docs", "--worker", "owner")
    manifest = json.loads((packet_dir(p.project, one, "docs", d["attempt"]) / "manifest.json").read_text(encoding="utf-8"))
    inp = next(i for i in manifest["inputs"] if i["name"] == "build")
    assert json.loads((packet_dir(p.project, one, "docs", d["attempt"]) / inp["path"]).read_text(encoding="utf-8")) == {"built_from": 1}
    write_result(packet_dir(p.project, one, "docs", d["attempt"]), {})
    p.cli.run("submit", one, "docs")
    assert p.cli.run("status", one)["state"] == "completed"


@pytest.mark.slow
def test_a_runnable_stale_step_reruns_when_dispatched(tmp_path):
    p = Project(tmp_path)
    run = p.toy("One")
    p.by_hand(run, "design", {"v": 1})
    p.by_hand(run, "build")
    p.by_hand(run, "docs")
    p.cli.run("revise", run, "design", "--reason", "Wrong units.")
    assert sorted(p.cli.run("status", run)["stale"][i]["step_path"] for i in range(2)) == ["build", "docs"]
    p.by_hand(run, "design", {"v": 2})
    out = p.cli.run("dispatch", run, "build", "--worker", "owner")
    assert out["attempt"] == 2
    ready = [e for e in p.events(run) if e["type"] == "step_ready" and e["step_path"] == "build"][-1]
    assert ready["data"] == {"rerun": True}
    pkt = packet_dir(p.project, run, "build", 2)
    manifest = json.loads((pkt / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prior_feedback"] is None
    assert json.loads((pkt / "inputs" / "design.json").read_text(encoding="utf-8")) == {"v": 2}
    # docs is still stale and waits for build again.
    assert p.cli.run("status", run)["stale"] == [{"step_path": "docs", "cause": "revised", "revised": "design", "runnable": False,
                                                  "waiting": "its dependencies are not satisfied again yet: build"}]
