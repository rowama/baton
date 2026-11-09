"""Intake and gates (§8.10, §9.1): rejection with reasons, provenance, script and human gates."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from baton import engine, labels
from baton.packet import EngineError
from baton.store import Store

from conftest import FIT_CHECK
from runkit import PROFILE_OUT, VERDICT_OUT, WRITER, Clock, artifact_recipe, make_recipe, start, write_result

PY = shlex.quote(sys.executable) if os.name == "posix" else subprocess.list2cmdline([sys.executable])  # for the platform shell


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "project", clock=Clock()) as s:
        yield s


def types(ctx, step: str) -> list[str]:
    return [e.type for e in ctx.log.events() if e.step_path == step]


def state(ctx, step: str) -> str:
    return ctx.log.state().step(step).state


def attempt(ctx, step: str, output, **kw):
    p = engine.begin_attempt(ctx, step, "owner", WRITER)
    write_result(p, output, **kw)
    return p, engine.submit(ctx, step)


# -- the happy path -----------------------------------------------------------


@pytest.mark.not_slow("measured under 1 s")
def test_fit_check_through_human_gate(store):
    ctx = start(store, FIT_CHECK)
    _, out = attempt(ctx, "describe", PROFILE_OUT)
    assert (out.outcome, out.ready) == ("passed", ["assess"])
    assert types(ctx, "describe") == [
        "step_ready", "worker_selected", "packet_built", "dispatched", "step_running", "result_submitted",
        "verification_started", "gate_passed", "gate_passed", "step_passed",
    ]
    gates = [e.data for e in ctx.log.events() if e.type == "gate_passed" and e.step_path == "describe"]
    assert [g["type"] for g in gates] == ["provenance", "schema"]

    _, out = attempt(ctx, "assess", VERDICT_OUT)
    assert out.outcome == "needs_human" and state(ctx, "assess") == "awaiting_human"
    assert engine.pending_decisions(ctx) == [
        {"ref": "assess", "step_path": "assess", "attempt": 1, "kind": "gate",
         "prompt": "Accept this verdict and its suggested next step?", "options": labels.options("gate", ["approve", "reject"], {"approve": "That verdict sounds right", "reject": "I don't think that's right"})}
    ]
    out = engine.decide(ctx, "assess", "approve", "Agreed — go ahead.")
    assert out.outcome == "passed" and out.run_completed
    decision = ctx.record().last("human_decision")
    assert (decision.actor, decision.data["note"]) == ("human", "Agreed — go ahead.")
    assert ctx.log.state().state == "completed"


@pytest.mark.not_slow("measured under 1 s")
def test_registered_output_is_what_downstream_sees(store):
    ctx = start(store, FIT_CHECK)
    attempt(ctx, "describe", PROFILE_OUT)
    reg = ctx.record().registered("describe")
    assert json.loads(ctx.log.cas.read(reg["output_sha256"])) == PROFILE_OUT


# -- rejections ---------------------------------------------------------------


@pytest.mark.not_slow("measured under 1 s")
def test_hash_mismatch_rejected_and_fed_back(store):
    ctx = start(store, FIT_CHECK)
    _, out = attempt(ctx, "describe", PROFILE_OUT, packet_sha256="0" * 64)
    assert out.outcome == "retry"
    assert out.reasons == ["packet_sha256 does not match this attempt's packet"]
    rejected = ctx.record().last("result_rejected", "describe", 1)
    assert rejected.data["reasons"] == out.reasons
    assert state(ctx, "describe") == "ready"
    p2 = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    assert p2.attempt == 2
    assert p2.manifest["prior_feedback"] == {"attempt": 1, "reasons": out.reasons}
    assert "packet_sha256 does not match" in (p2.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    write_result(p2, PROFILE_OUT)
    assert engine.submit(ctx, "describe").outcome == "passed"


@pytest.mark.not_slow("measured under 1 s")
def test_schema_failure_rejected_with_reasons(store):
    ctx = start(store, FIT_CHECK)
    bad = {"summary": "x", "occurrence": {**PROFILE_OUT["occurrence"], "judgment": "extreme"}, "surprise": 1}
    _, out = attempt(ctx, "describe", bad)
    assert out.outcome == "retry"
    assert any("occurrence/judgment" in r and "extreme" in r for r in out.reasons)
    assert any("surprise" in r for r in out.reasons)
    assert ctx.record().registered("describe") is None  # nothing downstream can consume


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda r: r.update(protocol="baton-packet/9"), "protocol is 'baton-packet/9'"),
        (lambda r: r.update(status="done"), "result.json status"),
        (lambda r: r.update(extra=True), "result.json extra"),
        (lambda r: r.pop("packet_sha256"), "result.json packet_sha256"),
    ],
)
@pytest.mark.not_slow("measured under 1 s")
def test_envelope_problems_rejected(store, mutate, expected):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    result = write_result(p, PROFILE_OUT)
    mutate(result)
    (p.result_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    out = engine.submit(ctx, "describe")
    assert out.outcome == "retry" and any(expected in r for r in out.reasons), out.reasons


@pytest.mark.not_slow("measured under 1 s")
def test_missing_and_unparsable_result(store):
    ctx = start(store, FIT_CHECK)
    engine.begin_attempt(ctx, "describe", "owner", WRITER)
    out = engine.submit(ctx, "describe")
    assert out.reasons == ["result/result.json is missing"]
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    (p.result_dir / "result.json").write_text("{not json", encoding="utf-8")
    assert "not valid JSON" in engine.submit(ctx, "describe").reasons[0]


@pytest.mark.not_slow("measured under 1 s")
def test_modified_packet_rejected(store):
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    target = p.dir / "inputs" / "idea.json"
    os.chmod(p.dir / "inputs", 0o755)
    os.chmod(target, 0o644)
    target.write_text('"a different idea"\n', encoding="utf-8")
    write_result(p, PROFILE_OUT)
    out = engine.submit(ctx, "describe")
    assert out.outcome == "retry" and "the packet was modified after it was built" in out.reasons


@pytest.mark.not_slow("measured under 1 s")
def test_attempts_exhausted_escalates(store):
    ctx = start(store, FIT_CHECK)  # fit-check: defaults.max_attempts = 3
    for n in (1, 2):
        assert attempt(ctx, "describe", {"bad": n})[1].outcome == "retry"
    _, out = attempt(ctx, "describe", {"bad": 3})
    assert out.outcome == "escalated" and state(ctx, "describe") == "escalated"
    assert ctx.record().last("step_escalated", "describe").data["reason"] == "attempts_exhausted"


@pytest.mark.not_slow("measured under 1 s")
def test_blocked_escalates_with_questions(store):
    ctx = start(store, FIT_CHECK)
    _, out = attempt(ctx, "describe", None, status="blocked", questions_for_human=["How often does it happen?"])
    assert out.outcome == "escalated"
    esc = ctx.record().last("step_escalated", "describe")
    assert esc.data["reason"] == "blocked"
    assert esc.data["questions"] == [{"id": "q1", "ask": "How often does it happen?", "why": "", "options": [],
                                      "multi_select": False, "priority": "needed"}]


@pytest.mark.not_slow("measured under 1 s")
def test_worker_failed_is_retried(store):
    ctx = start(store, FIT_CHECK)
    _, out = attempt(ctx, "describe", None, status="failed", notes="could not reach the owner")
    assert out.outcome == "retry" and "could not reach the owner" in out.reasons[0]


@pytest.mark.not_slow("measured under 1 s")
def test_submit_requires_a_running_attempt(store):
    """A Director that writes a result without a dispatched attempt cannot get it accepted."""
    ctx = start(store, FIT_CHECK)
    with pytest.raises(EngineError) as ei:
        engine.submit(ctx, "describe")
    assert ei.value.code == "engine.not_running"


# -- provenance ---------------------------------------------------------------


@pytest.fixture
def art(store, tmp_path):
    return start(store, artifact_recipe(tmp_path / "r"), {})


@pytest.mark.not_slow("measured under 1 s")
def test_artifacts_registered_through_intake(art):
    _, out = attempt(art, "draft", {}, artifacts={"doc": ("doc.md", b"# Doc\n")})
    assert out.outcome == "passed"
    reg = art.record().registered("draft")["artifacts"]["doc"]
    assert art.log.cas.read(reg["sha256"]) == b"# Doc\n"
    assert (reg["filename"], reg["media_type"]) == ("doc.md", "text/markdown")


@pytest.mark.not_slow("measured under 1 s")
def test_unlisted_file_is_not_registered(art):
    p = engine.begin_attempt(art, "draft", "owner", WRITER)
    (p.result_dir / "artifacts" / "doc.md").write_bytes(b"# Doc\n")  # present, but not listed
    write_result(p, {})
    out = engine.submit(art, "draft")
    assert out.reasons == ["required artifact 'doc' is missing"]


@pytest.mark.parametrize(
    "listing, expected",
    [
        ([{"name": "doc", "path": "artifacts/doc.md"}, {"name": "secret", "path": "artifacts/doc.md"}], "not declared"),
        ([{"name": "doc", "path": "artifacts/doc.md"}, {"name": "doc", "path": "artifacts/doc.md"}], "more than once"),
        ([{"name": "doc", "path": "../packet/manifest.json"}], "inside the result directory"),
        ([{"name": "doc", "path": "artifacts/nope.md"}], "does not exist"),
    ],
)
@pytest.mark.not_slow("measured under 1 s")
def test_artifact_listing_problems(art, listing, expected):
    p = engine.begin_attempt(art, "draft", "owner", WRITER)
    result = write_result(p, {}, artifacts={"doc": ("doc.md", b"# Doc\n")})
    result["artifacts"] = listing
    (p.result_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    out = engine.submit(art, "draft")
    assert out.outcome == "retry" and any(expected in r for r in out.reasons), out.reasons


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
@pytest.mark.not_slow("measured under 1 s")
def test_symlinked_artifact_rejected(art, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"# Not from the worker\n")
    p = engine.begin_attempt(art, "draft", "owner", WRITER)
    (p.result_dir / "artifacts" / "doc.md").symlink_to(outside)
    write_result(p, {})
    result = json.loads((p.result_dir / "result.json").read_text(encoding="utf-8"))
    result["artifacts"] = [{"name": "doc", "path": "artifacts/doc.md"}]
    (p.result_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    out = engine.submit(art, "draft")
    assert any("is a link" in r for r in out.reasons)


@pytest.mark.not_slow("measured under 1 s")
def test_planted_blob_never_satisfies_downstream(art):
    """A blob in CAS without intake behind it is not an accepted result."""
    art.log.cas.put(b"# Planted by someone\n")
    _, out = attempt(art, "draft", {})  # no artifact listed
    assert out.outcome == "retry"
    assert state(art, "use") == "blocked_on_deps"
    with pytest.raises(EngineError):
        engine.begin_attempt(art, "use", "owner", WRITER)


# -- script gates -------------------------------------------------------------


def script_recipe(root: Path, run: str, **gate) -> Path:
    return make_recipe(
        root,
        [{"id": "work", "output_schema": "schemas/out.json", "gates": [{"type": "schema"}, {"type": "script", "run": run, **gate}]}],
        schemas={"out.json": {"type": "object"}},
    )


@pytest.mark.not_slow("measured under 1 s")
def test_script_gate_pass(store, tmp_path):
    ctx = start(store, script_recipe(tmp_path / "r", f"{PY} -c \"print('ok')\""), {})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "passed"
    g = ctx.record().last("gate_passed", "work")
    assert g.data["type"] == "script" and g.data["exit_code"] == 0
    assert ctx.log.cas.read(g.data["output_sha256"]).strip() == b"ok"


@pytest.mark.not_slow("measured under 1 s")
def test_script_gate_failure_feeds_back_output(store, tmp_path):
    cmd = f"{PY} -c \"import sys; print('2 tests failed'); sys.exit(3)\""
    ctx = start(store, script_recipe(tmp_path / "r", cmd), {})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "retry"
    assert out.reasons[0].endswith("exited 3") and "2 tests failed" in out.reasons[1]
    p2 = engine.begin_attempt(ctx, "work", "owner", WRITER)
    assert "2 tests failed" in "".join(p2.manifest["prior_feedback"]["reasons"])


@pytest.mark.not_slow("measured under 1 s")
def test_script_gate_runs_in_project_with_reduced_env(store, tmp_path, monkeypatch):
    monkeypatch.setenv("BATON_TEST_LEAK", "should-not-pass")
    cmd = f"{PY} -c \"import os; print(os.getcwd()); print(os.environ.get('BATON_TEST_LEAK')); print(os.environ['BATON_STEP_PATH'])\""
    ctx = start(store, script_recipe(tmp_path / "r", cmd), {})
    attempt(ctx, "work", {})
    lines = ctx.log.cas.read(ctx.record().last("gate_passed", "work").data["output_sha256"]).decode().split()
    assert Path(lines[0]).resolve() == store.root.resolve()
    assert lines[1:] == ["None", "work"]


@pytest.mark.slow
def test_script_gate_timeout(store, tmp_path):
    ctx = start(store, script_recipe(tmp_path / "r", f"{PY} -c \"import time; time.sleep(30)\"", timeout_s=1), {})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "retry" and "did not finish within 1 s" in out.reasons[0]
    assert ctx.record().last("gate_failed", "work").data["timed_out"] is True


@pytest.mark.not_slow("measured under 1 s")
def test_script_gate_template_variables(store, tmp_path):
    rec = script_recipe(tmp_path / "r", "{{ project.test_command }}")
    ctx = start(store, rec, {}, project={"project": {"test_command": f"{PY} -c \"print('templated')\""}})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "passed"


@pytest.mark.not_slow("measured under 1 s")
def test_script_gate_undefined_variable_escalates(store, tmp_path):
    ctx = start(store, script_recipe(tmp_path / "r", "{{ project.test_command }}"), {})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "escalated"
    assert ctx.record().last("step_escalated", "work").data["reason"] == "configuration"


@pytest.mark.not_slow("measured under 1 s")
def test_advisory_script_gate_never_blocks(store, tmp_path):
    ctx = start(store, script_recipe(tmp_path / "r", f"{PY} -c \"raise SystemExit(1)\"", advisory=True), {})
    _, out = attempt(ctx, "work", {})
    assert out.outcome == "passed"
    assert ctx.record().last("gate_failed", "work").data["advisory"] is True


# -- human gates --------------------------------------------------------------


@pytest.mark.not_slow("measured under 1 s")
def test_human_gate_blocks_until_decided(store):
    ctx = start(store, FIT_CHECK)
    attempt(ctx, "describe", PROFILE_OUT)
    attempt(ctx, "assess", VERDICT_OUT)
    assert state(ctx, "assess") == "awaiting_human"
    assert ctx.log.state().state == "active"
    with pytest.raises(EngineError):
        engine.submit(ctx, "assess")
    with pytest.raises(EngineError):
        engine.begin_attempt(ctx, "assess", "owner", WRITER)
    assert engine.refresh(ctx) == [] and ctx.log.state().state == "active"
    with pytest.raises(EngineError) as ei:
        engine.decide(ctx, "describe", "approve")
    assert ei.value.code == "decide.nothing_pending"
    with pytest.raises(EngineError) as ei:
        engine.decide(ctx, "assess", "maybe")
    assert ei.value.code == "decide.bad_decision"
    assert state(ctx, "assess") == "awaiting_human"


@pytest.mark.not_slow("measured under 1 s")
def test_human_rejection_retries_with_the_owners_words(store):
    ctx = start(store, FIT_CHECK)
    attempt(ctx, "describe", PROFILE_OUT)
    attempt(ctx, "assess", VERDICT_OUT)
    out = engine.decide(ctx, "assess", "reject", "The duration row is missing.")
    assert out.outcome == "retry" and state(ctx, "assess") == "ready"
    p2 = engine.begin_attempt(ctx, "assess", "owner", WRITER)
    assert p2.manifest["prior_feedback"]["reasons"] == ["the owner did not approve: The duration row is missing."]
    write_result(p2, VERDICT_OUT)
    assert engine.submit(ctx, "assess").outcome == "needs_human"
    assert engine.decide(ctx, "assess", "approve").run_completed


@pytest.mark.not_slow("measured under 1 s")
def test_gates_after_a_human_gate_run_after_approval(store, tmp_path):
    rec = make_recipe(
        tmp_path / "r",
        [
            {
                "id": "work",
                "output_schema": "schemas/out.json",
                "gates": [{"type": "human", "prompt": "OK?"}, {"type": "script", "run": f"{PY} -c \"raise SystemExit(2)\""}],
            }
        ],
        schemas={"out.json": {"type": "object"}},
    )
    ctx = start(store, rec, {})
    assert attempt(ctx, "work", {})[1].outcome == "needs_human"
    out = engine.decide(ctx, "work", "approve")
    assert out.outcome == "retry" and out.reasons[0].endswith("exited 2")
