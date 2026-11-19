"""Approved file sets (§9.4; change 2026-11-builder-context-and-locks, Slice 2; Decision 0173).

A human gate's ``locks`` record the matching files when the owner approves it;
every later step of the run is bound: a change made by a step is caught at its
intake (``warn`` waits on the owner, ``fail`` fails the gate), a change made
outside any step refuses the next dispatch until the owner accepts it or the
files are restored. Revising the gate's step releases the lock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from baton import engine, file_locks
from baton.models import WorkerProfile
from baton.packet import EngineError
from baton.recipe import build_plan, load_recipe
from baton.store import Store

from runkit import Clock, make_recipe
from runkit import write_result as play

OBJ = {"type": "object"}
WRITER = WorkerProfile(
    adapter="manual", vendor="acme", capabilities=["structured_output", "repo_workspace", "file_write", "workspace_read"], tier="strong",
)


def _recipe(tmp_path: Path, locks: Any, *, spec_extra: dict | None = None) -> Path:
    return make_recipe(tmp_path / "rec", [
        {"id": "spec", "workspace": "write", "output_schema": "schemas/out.json",
         "requires": {"capabilities": ["structured_output", "repo_workspace"]},
         "gates": [{"type": "human", "prompt": "Are these the acceptance specs?", "locks": locks}], **(spec_extra or {})},
        {"id": "implement", "depends_on": ["spec"], "workspace": "write", "output_schema": "schemas/out.json",
         "requires": {"capabilities": ["structured_output", "repo_workspace"]}},
        {"id": "document", "depends_on": ["implement"], "output_schema": "schemas/out.json"},
    ], schemas={"out.json": OBJ}, defaults={"max_attempts": 3})


def _approved(store: Store, tmp_path: Path, locks: Any = ("specs/**",)):
    """A run whose `spec` step wrote two specs and the owner approved them."""
    rec = _recipe(tmp_path, list(locks) if isinstance(locks, tuple) else locks)
    ctx = engine.start(store, engine.load_recipe(rec), {}, run_id="r_lock")
    specs = store.root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    p = engine.begin_attempt(ctx, "spec", "w", WRITER)
    (specs / "login.feature").write_text("Scenario: login\n", encoding="utf-8")
    (specs / "logout.feature").write_text("Scenario: logout\n", encoding="utf-8")
    play(p, {})
    assert engine.submit(ctx, "spec").outcome == "needs_human"
    assert engine.decide(ctx, "spec", "approve", "Yes, those are the specs.").outcome == "passed"
    return ctx, specs


def _locked(ctx) -> list[Any]:
    return [e for e in ctx.log.events() if e.type == "files_locked"]


def test_the_owners_approval_records_the_set_with_its_hashes(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path)
        (ev,) = _locked(ctx)
        assert ev.step_path == "spec" and ev.data["gate"] == 0 and ev.data["globs"] == ["specs/**"] and ev.data["mode"] == "warn"
        assert ev.data["cause"] == "approved" and ev.data["decision_id"].startswith("d") and ev.data["key"] == "toy@1/spec#0"
        assert [p["path"] for p in ev.data["paths"]] == ["specs/login.feature", "specs/logout.feature"]
        assert all(len(p["sha256"]) == 64 for p in ev.data["paths"])
        # A later step dispatched is bound by it, and an unchanged set passes the implicit gate.
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        disp = ctx.record().last("dispatched", "implement", 1)
        assert disp.data["locks"] == [{"key": "toy@1/spec#0", "seq": ev.seq}]
        play(p, {})
        assert engine.submit(ctx, "implement").outcome == "passed"
        locked_gate = [e for e in ctx.log.events() if e.type == "gate_passed" and e.data.get("gate") == "locked"]
        assert [e.step_path for e in locked_gate] == ["implement"]


@pytest.mark.parametrize("change", ["edited", "added", "deleted"])
def test_a_change_a_later_step_makes_waits_on_the_owner_and_keeping_it_records_the_set_again(tmp_path, change):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path)
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        target = {"edited": specs / "login.feature", "added": specs / "signup.feature", "deleted": specs / "logout.feature"}[change]
        if change == "deleted":
            target.unlink()
        else:
            target.write_text("Scenario: weakened\n", encoding="utf-8")
        play(p, {})
        out = engine.submit(ctx, "implement")
        assert out.outcome == "needs_human" and "changed files you approved at spec" in out.reasons[0]
        (mod,) = [e for e in ctx.log.events() if e.type == "locked_path_modified"]
        want = {"edited": "specs/login.feature", "added": "specs/signup.feature (added)", "deleted": "specs/logout.feature (deleted)"}[change]
        assert mod.data["mode"] == "warn" and mod.data["locks"][0]["changed"] == [want] and mod.data["locks"][0]["ref"] == "lock:spec#0"
        (pd,) = engine.pending_decisions(ctx)  # the gate on the step; no separate lock decision while its own check holds it
        assert pd["kind"] == "gate" and [o["decision"] for o in pd["options"]] == ["approve", "reject"]
        assert engine.decide(ctx, "implement", "approve", "The spec change is agreed.").outcome == "passed"
        again = _locked(ctx)[-1]
        assert again.data["cause"] == "change_approved" and again.step_path == "spec"
        assert ("specs/logout.feature" in [p["path"] for p in again.data["paths"]]) == (change != "deleted")
        # The next step starts: the set as kept is the approved set now.
        engine.begin_attempt(ctx, "document", "w", WRITER)


def test_rejecting_the_change_fails_the_attempt_and_the_retry_waits_until_the_files_are_restored(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path)
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        (specs / "login.feature").write_text("Scenario: weakened\n", encoding="utf-8")
        play(p, {})
        assert engine.submit(ctx, "implement").outcome == "needs_human"
        out = engine.decide(ctx, "implement", "reject", "Never weaken the specs.")
        assert out.outcome == "retry" and "did not accept the change to approved files" in out.reasons[0]
        with pytest.raises(EngineError) as e:
            engine.begin_attempt(ctx, "implement", "w", WRITER)
        assert e.value.code == "dispatch.locked_files_changed" and "specs/login.feature" in str(e.value)
        (specs / "login.feature").write_text("Scenario: login\n", encoding="utf-8")  # restored
        engine.begin_attempt(ctx, "implement", "w", WRITER)


@pytest.mark.parametrize("change", ["edited", "added", "deleted"])
def test_in_fail_mode_a_change_fails_the_gate(tmp_path, change):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path, {"paths": ["specs/**"], "on_violation": "fail"})
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        if change == "deleted":
            (specs / "logout.feature").unlink()
        else:
            (specs / ("login.feature" if change == "edited" else "signup.feature")).write_text("x\n", encoding="utf-8")
        play(p, {})
        out = engine.submit(ctx, "implement")
        assert out.outcome == "retry" and "files approved at spec were modified" in out.reasons[0]
        failed = [e for e in ctx.log.events() if e.type == "gate_failed" and e.data.get("gate") == "locked"]
        assert len(failed) == 1 and failed[0].data["locks"][0]["mode"] == "fail"


@pytest.mark.parametrize("change", ["edited", "added", "deleted"])
def test_a_change_made_outside_any_step_refuses_the_next_dispatch_until_the_owner_accepts_it(tmp_path, change):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path, {"paths": ["specs/**"], "on_violation": "fail"})  # fail mode never fails an attempt here
        if change == "deleted":
            (specs / "logout.feature").unlink()
        else:
            (specs / ("login.feature" if change == "edited" else "signup.feature")).write_text("x\n", encoding="utf-8")
        with pytest.raises(EngineError) as e:
            engine.begin_attempt(ctx, "implement", "w", WRITER)
        assert e.value.code == "dispatch.locked_files_changed" and "decide lock:spec#0 accept" in str(e.value)
        assert not [ev for ev in ctx.log.events() if ev.step_path == "implement" and ev.type == "dispatched"]  # nothing written
        (pd,) = engine.pending_decisions(ctx)
        assert pd["kind"] == "locked_change" and pd["ref"] == "lock:spec#0" and [o["decision"] for o in pd["options"]] == ["accept"]
        assert pd["prompt"].startswith("Files you approved at spec were changed outside the process")
        with pytest.raises(EngineError) as e:
            engine.decide(ctx, "lock:spec#0", "reject")
        assert e.value.code == "decide.bad_decision"
        engine.decide(ctx, "lock:spec#0", "accept", "I fixed a typo in the spec.")
        dec = [ev for ev in ctx.log.events() if ev.type == "human_decision" and ev.data.get("kind") == "locked_change"]
        assert dec[-1].data["note"] == "I fixed a typo in the spec." and _locked(ctx)[-1].data["cause"] == "change_accepted"
        assert _locked(ctx)[-1].data["decision_id"] == dec[-1].data["decision_id"]
        assert engine.pending_decisions(ctx) == []
        engine.begin_attempt(ctx, "implement", "w", WRITER)


def test_accepting_keeps_only_the_changed_files_as_they_are_now(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path)
        (specs / "login.feature").write_text("Scenario: log in\n", encoding="utf-8")
        engine.decide(ctx, "lock:spec#0", "accept", "Agreed.")
        lk = file_locks.find(ctx.log.events(), "lock:spec#0")
        assert lk is not None and file_locks.differences(store.root, lk) == []


def test_revising_the_step_releases_the_lock_and_approving_again_records_a_new_set(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, specs = _approved(store, tmp_path)
        engine.revise(ctx, "spec", "The owner wants a password-reset spec too.")
        assert file_locks.live(ctx.log.events()) == {}
        p = engine.begin_attempt(ctx, "spec", "w", WRITER)  # no lock binds it, though the files will change
        (specs / "reset.feature").write_text("Scenario: reset\n", encoding="utf-8")
        play(p, {})
        assert engine.submit(ctx, "spec").outcome == "needs_human"
        engine.decide(ctx, "spec", "approve", "Yes, with the reset spec.")
        locks = file_locks.live(ctx.log.events())
        assert list(locks) == ["toy@1/spec#0"] and "specs/reset.feature" in locks["toy@1/spec#0"].files
        assert len(locks["toy@1/spec#0"].history) == 1  # a fresh set: the released one is not its history


@pytest.mark.slow
def test_status_explain_and_the_step_record_show_the_locks(tmp_path):
    from baton import docs
    from baton.cli import _status_text
    from baton.engine import Api
    from baton.project import init

    from projectkit import make_home, packet_dir, write_result
    from test_reviews import PROFILES

    rec = _recipe(tmp_path, ["specs/**"])
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    api = Api.open(root, director_id="alice@host1", home=make_home(tmp_path / "home", PROFILES), clock=Clock())
    api.vendor(rec)
    run = api.start("toy", {"title": "Login"})["run_id"]
    assert "locks" not in api.status(run)  # nothing locked yet: status unchanged
    d = api.dispatch(run, "spec", "alice")
    (root / "specs").mkdir()
    (root / "specs" / "login.feature").write_text("Scenario: login\n", encoding="utf-8")
    write_result(packet_dir(root, run, "spec", d["attempt"]), {})
    api.submit(run, "spec")
    api.decide(run, "spec", "approve", "Yes, those are the specs.")
    (root / "specs" / "login.feature").write_text("changed\n", encoding="utf-8")
    st = api.status(run)
    (row,) = st["locks"]
    assert row["ref"] == "lock:spec#0" and row["files"] == 1 and row["changed"] == ["specs/login.feature"] and row["decision_id"]
    assert [p["kind"] for p in st["pending_decisions"]] == ["locked_change"]
    text = _status_text(st)
    assert "approved files locked by spec (gate 0, decision " in text and "changed: specs/login.feature" in text
    assert "Owner decision owed on lock:spec#0" in text
    ex = api.explain(run)
    assert ex["locks"] == st["locks"]
    assert "Locked: the 1 file(s) matching specs/**, approved at spec" in ex["text"] and "Changed since: specs/login.feature" in ex["text"]
    record = docs.step_record(api._ctx(run), "spec")
    assert "Files locked by the owner's approval" in record and "1 file(s) matching specs/** (warn)" in record


def test_a_lock_cannot_be_waived(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, _ = _approved(store, tmp_path)
        with pytest.raises(EngineError) as e:
            engine.waive(ctx, "implement", "locked", "Let it through.")
        assert e.value.code == "waive.not_waivable"


def test_publishing_over_a_locked_file_is_a_publish_conflict(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        rec = make_recipe(tmp_path / "rec", [
            {"id": "spec", "workspace": "write", "output_schema": "schemas/out.json",
             "requires": {"capabilities": ["structured_output", "repo_workspace"]},
             "gates": [{"type": "human", "prompt": "Approve?", "locks": ["specs/**"]}]},
            {"id": "notes", "depends_on": ["spec"], "output_schema": "schemas/out.json",
             "artifacts": [{"name": "doc", "required": True, "media_type": "text/markdown", "publish": {"to": "specs/login.feature"}}]},
            {"id": "after", "depends_on": ["notes"], "output_schema": "schemas/out.json"},
        ], schemas={"out.json": OBJ})
        ctx = engine.start(store, engine.load_recipe(rec), {}, run_id="r_pub")
        (store.root / "specs").mkdir()
        p = engine.begin_attempt(ctx, "spec", "w", WRITER)
        (store.root / "specs" / "login.feature").write_text("Scenario: login\n", encoding="utf-8")
        play(p, {})
        engine.submit(ctx, "spec")
        engine.decide(ctx, "spec", "approve", "Yes.")
        p = engine.begin_attempt(ctx, "notes", "w", WRITER)
        play(p, {}, artifacts={"doc": ("doc.md", b"Overwritten\n")})
        assert engine.submit(ctx, "notes").outcome == "passed"
        assert (store.root / "specs" / "login.feature").read_text(encoding="utf-8") == "Scenario: login\n"
        conflict = [d for d in engine.pending_decisions(ctx) if d["kind"] == "publish_conflict"]
        assert len(conflict) == 1 and "one of the files you approved at spec" in conflict[0]["reasons"][0]
        engine.decide(ctx, conflict[0]["ref"], "overwrite", "Yes, replace it.")
        # The owner decided that publish: the set includes it as written.
        lk = file_locks.find(ctx.log.events(), "lock:spec#0")
        assert lk is not None and file_locks.differences(store.root, lk) == []
        assert (store.root / "specs" / "login.feature").read_text(encoding="utf-8") == "Overwritten\n"
        engine.begin_attempt(ctx, "after", "w", WRITER)


def test_the_lock_globs_are_checked_and_shown_in_the_plan(tmp_path):
    ok = load_recipe(_recipe(tmp_path / "a", {"paths": ["specs/**"], "on_violation": "fail"}))
    assert not [i for i in ok.warnings if i.code.startswith("gate.")]
    (g,) = build_plan(ok).levels[0].steps[0].gates
    assert "approval locks specs/**, fail" in g.note
    from baton.recipe import RecipeError

    for bad in (["../outside/**"], ["/etc/**"], [".baton/**"], ["C:/x"]):
        with pytest.raises(RecipeError) as e:
            load_recipe(_recipe(tmp_path / f"b{abs(hash(bad[0]))}", bad))
        assert "gate.lock_path" in str(e.value) or any(i.code == "gate.lock_path" for i in getattr(e.value, "issues", []))


def test_a_recipe_without_locks_records_nothing_new(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        rec = make_recipe(tmp_path / "rec", [
            {"id": "a", "output_schema": "schemas/out.json", "gates": [{"type": "human", "prompt": "OK?"}]},
            {"id": "b", "depends_on": ["a"], "output_schema": "schemas/out.json"},
        ], schemas={"out.json": OBJ})
        ctx = engine.start(store, engine.load_recipe(rec), {}, run_id="r_none")
        p = engine.begin_attempt(ctx, "a", "w", WRITER)
        play(p, {})
        engine.submit(ctx, "a")
        engine.decide(ctx, "a", "approve", "Yes.")
        p = engine.begin_attempt(ctx, "b", "w", WRITER)
        play(p, {})
        engine.submit(ctx, "b")
        types = {e.type for e in ctx.log.events()}
        assert not types & {"files_locked", "locked_path_modified"}
        assert not any(e.data.get("gate") == "locked" for e in ctx.log.events() if e.type == "gate_passed")
        assert "locks" not in (ctx.record().last("dispatched", "b", 1).data)
