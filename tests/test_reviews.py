"""Reviews (L4, §9): review gates, findings and dispositions, waivers, protected files, independence.

Phase 9 acceptance: a rejection without valid evidence is refused;
``accepted-risk`` without an owner decision is refused; a waiver unblocks
exactly one occurrence; protected-path changes are caught in ``warn`` and
``fail`` modes; a same-vendor code review is refused unless waived; a
partial-coverage review shows as partial. Also: ``type: review`` gates run as
runtime-made review steps, and a worker's ``fixed`` / ``rejected`` is
provisional until the next review confirms it (§18 #12).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import test_groups as tg
from baton import engine, reviews
from baton.engine import Api
from baton.models import WorkerProfile
from baton.packet import EngineError
from baton.project import init
from baton.store import Store

from projectkit import make_home, packet_dir, write_result
from runkit import Clock, make_recipe
from runkit import write_result as play

PROFILES = """\
alice:
  adapter: manual
  vendor: acme
  capabilities: [structured_output, technical_reasoning, workspace_read, repo_workspace, file_write]
  tier: strong
carol:
  adapter: manual
  vendor: zenith
  capabilities: [structured_output, technical_reasoning, workspace_read, repo_workspace, file_write]
  tier: strong
"""
OBJ = {"type": "object"}
HIGH = {"findings": [{"id": "F1", "severity": "high", "location": "src/auth.py:2", "title": "token never expires"}], "coverage": {"complete": True}}
CLEAN = {"findings": [], "coverage": {"complete": True}}
PARTIAL_HIGH = {**HIGH, "coverage": {"complete": False, "notes": "could not run socket tests"}}
WRITER = WorkerProfile(
    adapter="manual", vendor="acme", capabilities=["structured_output", "repo_workspace", "file_write", "workspace_read"], tier="strong",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _project(tmp_path: Path, steps: list[dict], **top: Any) -> tuple[Api, Path, str]:
    recipe = make_recipe(tmp_path / "toy", steps, schemas={"out.json": OBJ}, **top)
    (recipe / "prompts" / "rubric.md").write_text("Review the design for security problems.\n", encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    (root / "src").mkdir()
    (root / "src" / "auth.py").write_text("def login():\n    return token\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_auth.py").write_text("def test_token_expires():\n    assert True\n", encoding="utf-8")
    home = make_home(tmp_path / "home", PROFILES)
    api = Api.open(root, director_id="alice@host1", home=home, clock=Clock())
    api.vendor(recipe)
    run = api.start("toy", {"title": "Reviews"})["run_id"]
    return api, root, run


REVIEWED_DESIGN = {
    "id": "design",
    "output_schema": "schemas/out.json",
    "gates": [
        {"type": "schema"},
        {
            "type": "review",
            "block_on": ["critical", "high"],
            "reviewer_requires": {"capabilities": ["structured_output", "technical_reasoning"], "tier": "strong"},
            "independence": {"from_step": "design", "level": "different_vendor"},
            "rubric": "prompts/rubric.md",
        },
    ],
}


@pytest.fixture
def reviewed(tmp_path):
    return _project(tmp_path, [dict(REVIEWED_DESIGN), {"id": "build", "depends_on": ["design"], "output_schema": "schemas/out.json"}], defaults={"max_attempts": 5})


def do(api: Api, root: Path, run: str, step: str, worker: str, output: Any, **extra: Any) -> dict:
    d = api.dispatch(run, step, worker)
    write_result(packet_dir(root, run, step, d["attempt"]), output, **extra)
    return api.submit(run, step)


def manifest(root: Path, run: str, step: str, n: int) -> dict:
    return json.loads((packet_dir(root, run, step, n) / "manifest.json").read_text(encoding="utf-8"))


def instructions(root: Path, run: str, step: str, n: int) -> str:
    return (packet_dir(root, run, step, n) / "INSTRUCTIONS.md").read_text(encoding="utf-8")


def events(api: Api, run: str, etype: str) -> list[Any]:
    return [e for e in api._ctx(run).log.events() if e.type == etype]


# ---------------------------------------------------------------------------
# Review gates (§9.1)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_review_gate_runs_as_a_review_step_with_an_independent_reviewer(reviewed):
    api, root, run = reviewed
    out = do(api, root, run, "design", "alice", {"plan": "sessions"})
    assert out["outcome"] == "needs_review"
    assert out["ready"] == ["design~review"]
    st = api.status(run)
    assert st["steps"]["design"]["state"] == "verifying"
    assert "design~review" in st["ready"]

    # The reviewer must be independent of design's worker (different vendor).
    el = api.eligible(run, "design~review")
    assert [e["profile"] for e in el["eligible"]] == ["carol"]
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "design~review", "alice")
    assert e.value.code == "routing.ineligible" and "independence" in str(e.value)

    d = api.dispatch(run, "design~review", "carol")
    m = manifest(root, run, "design~review", d["attempt"])
    assert any(i["name"] == "reviewed_output" for i in m["inputs"])
    assert m["prior_findings"] is None
    text = instructions(root, run, "design~review", d["attempt"])
    assert "Review the design for security problems." in text and "This is the first review" in text
    assert '"plan": "sessions"' in text  # the result under review is inlined

    write_result(packet_dir(root, run, "design~review", d["attempt"]), CLEAN)
    out = api.submit(run, "design~review")
    st = api.status(run)
    assert st["steps"]["design"]["state"] == "passed"
    assert st["steps"]["design~review"]["state"] == "passed"
    assert "build" in st["ready"]
    rec = [e.data for e in events(api, run, "findings_recorded")]
    assert rec[0]["review"] == "design~review" and rec[0]["reviewer"] == "carol" and rec[0]["line"] == "design#1"


@pytest.mark.slow
def test_failed_review_retries_the_step_and_reviews_each_attempt(reviewed):
    api, root, run = reviewed
    do(api, root, run, "design", "alice", {"v": 1})
    out = do(api, root, run, "design~review", "carol", PARTIAL_HIGH)
    assert out["outcome"] == "retry" and out["step_path"] == "design"
    assert out["reasons"] == ["open high finding F1: token never expires (src/auth.py:2)"]
    # Partial coverage shows as partial in the record.
    rec = api.record(run, "design")
    assert "**partial** coverage" in rec and "could not run socket tests" in rec
    assert "`F1` high **open**" in rec

    # Attempt 2's packet carries the open finding, so the worker can address it.
    d = api.dispatch(run, "design", "alice")
    pf = manifest(root, run, "design", d["attempt"])["prior_feedback"]
    assert pf["findings"][0]["id"] == "F1" and pf["findings"][0]["step"] == "design"
    text = instructions(root, run, "design", d["attempt"])
    assert "## Dispositions" in text and "`F1` (high)" in text
    write_result(packet_dir(root, run, "design", d["attempt"]), {"v": 2},
                 dispositions=[{"step": "design", "finding": "F1", "disposition": "fixed", "evidence": "src/auth.py:2"}])
    assert api.submit(run, "design")["outcome"] == "needs_review"
    claim = events(api, run, "finding_dispositioned")[-1].data
    assert claim["disposition"] == "fixed" and claim["by"] == "worker" and claim["provisional"] is True

    # The second review sees the claim; it still sees the problem, so the finding reopens.
    d = api.dispatch(run, "design~review", "carol")
    prior = manifest(root, run, "design~review", d["attempt"])["prior_findings"]
    assert prior["findings"][0]["disposition"]["disposition"] == "fixed"
    assert "marked **fixed** by worker: src/auth.py:2" in instructions(root, run, "design~review", d["attempt"])
    write_result(packet_dir(root, run, "design~review", d["attempt"]), HIGH)
    out = api.submit(run, "design~review")
    assert out["outcome"] == "retry"
    assert "reported again after it was marked fixed" in out["reasons"][0]

    # Third time: the reviewer no longer reports F1 — the fix is confirmed.
    do(api, root, run, "design", "alice", {"v": 3},
       dispositions=[{"step": "design", "finding": "F1", "disposition": "fixed", "evidence": "src/auth.py:1"}])
    out = do(api, root, run, "design~review", "carol", CLEAN)
    assert api.status(run)["steps"]["design"]["state"] == "passed"
    last = events(api, run, "findings_recorded")[-1].data
    assert last["resolved"] == [{"id": "F1", "severity": "high", "title": "token never expires", "disposition": "fixed", "confirmed": True}]


@pytest.mark.slow
def test_abandoning_an_escalated_review_fails_the_reviewed_steps_gate(tmp_path):
    api, root, run = _project(tmp_path, [dict(REVIEWED_DESIGN)], defaults={"max_attempts": 1})
    do(api, root, run, "design", "alice", {})
    out = do(api, root, run, "design~review", "carol", {"not": "findings"})
    assert out["outcome"] == "escalated"  # the reviewer's result was rejected and its budget used
    assert [p["ref"] for p in api.status(run)["pending_decisions"]] == ["design~review"]
    out = api.decide(run, "design~review", "abandon", "this reviewer cannot do it")
    assert out["step_path"] == "design" and out["outcome"] == "escalated"
    st = api.status(run)
    assert st["steps"]["design"]["state"] == "escalated"
    assert [p["ref"] for p in st["pending_decisions"]] == ["design"]  # the stale review decision is gone


# ---------------------------------------------------------------------------
# Dispositions and evidence (§9.2, §18 #12)
# ---------------------------------------------------------------------------


def _failed_once(api: Api, root: Path, run: str) -> None:
    do(api, root, run, "design", "alice", {"v": 1})
    assert do(api, root, run, "design~review", "carol", HIGH)["outcome"] == "retry"


@pytest.mark.slow
def test_rejection_without_valid_evidence_is_refused(reviewed):
    api, root, run = reviewed
    _failed_once(api, root, run)
    # From a worker: the whole result is rejected, with the reason.
    d = api.dispatch(run, "design", "alice")
    write_result(packet_dir(root, run, "design", d["attempt"]), {"v": 2},
                 dispositions=[{"step": "design", "finding": "F1", "disposition": "rejected", "evidence": "src/auth.py:40"}])
    out = api.submit(run, "design")
    assert out["outcome"] == "retry"
    assert any("src/auth.py has 2 lines in the working tree; line 40 does not exist" in r for r in out["reasons"])
    assert not events(api, run, "finding_dispositioned")
    d = api.dispatch(run, "design", "alice")
    write_result(packet_dir(root, run, "design", d["attempt"]), {"v": 2},
                 dispositions=[{"step": "design", "finding": "F1", "disposition": "rejected"}])
    assert any("rejected needs evidence" in r for r in api.submit(run, "design")["reasons"])
    d = api.dispatch(run, "design", "alice")
    write_result(packet_dir(root, run, "design", d["attempt"]), {"v": 2},
                 dispositions=[{"step": "design", "finding": "F9", "disposition": "rejected", "evidence": "src/auth.py:1"}])
    assert any("no finding 'F9'" in r for r in api.submit(run, "design")["reasons"])

    # From the Director: the call is refused.
    for bad in (None, "src/missing.py:1", "tests/test_auth.py::test_nothing_like_it", "because I said so"):
        with pytest.raises(EngineError) as e:
            api.disposition(run, "design", "F1", "rejected", bad)
        assert e.value.code == "disposition.bad_evidence"
    out = api.disposition(run, "design", "F1", "rejected", "tests/test_auth.py::test_token_expires")
    assert out["outcome"] == "recorded"
    d = events(api, run, "finding_dispositioned")[-1].data
    assert d["by"] == "director" and d["disposition"] == "rejected"
    # A worker cannot accept a risk.
    dd = api.dispatch(run, "design", "alice")
    write_result(packet_dir(root, run, "design", dd["attempt"]), {"v": 3},
                 dispositions=[{"step": "design", "finding": "F1", "disposition": "accepted-risk"}])
    assert any("dispositions.0.disposition" in r for r in api.submit(run, "design")["reasons"])


@pytest.mark.slow
def test_accepted_risk_needs_the_owners_decision_and_carries_forward(reviewed):
    api, root, run = reviewed
    _failed_once(api, root, run)
    for evidence in (None, "d999", "the owner said so"):
        with pytest.raises(EngineError) as e:
            api.disposition(run, "design", "F1", "accepted-risk", evidence)
        assert e.value.code == "disposition.needs_owner_decision"
    out = api.decide(run, "design#F1", "accept-risk", "Tokens are short-lived behind the gateway; accept for now.")
    assert out["outcome"] == "recorded"
    dec = events(api, run, "human_decision")[-1]
    assert dec.data["kind"] == "finding" and dec.data["note"].startswith("Tokens are short-lived")
    disp = events(api, run, "finding_dispositioned")[-1].data
    assert disp["disposition"] == "accepted-risk" and disp["decision_id"] == dec.data["decision_id"] and disp["by"] == "owner"
    # The Director may also cite that decision.
    assert api.disposition(run, "design", "F1", "accepted-risk", dec.data["decision_id"])["outcome"] == "recorded"
    # A decision about another finding does not count.
    with pytest.raises(EngineError):
        api.decide(run, "design#F7", "accept-risk", "x")

    # Next review re-reports F1: it is an accepted risk, not open; the gate passes.
    do(api, root, run, "design", "alice", {"v": 2})
    do(api, root, run, "design~review", "carol", HIGH)
    assert api.status(run)["steps"]["design"]["state"] == "passed"
    row = events(api, run, "findings_recorded")[-1].data["findings"][0]
    assert row["status"] == "accepted-risk" and row["carried"] is True


@pytest.mark.slow
def test_a_superseded_evaluation_cannot_be_dispositioned(reviewed):
    api, root, run = reviewed
    _failed_once(api, root, run)
    do(api, root, run, "design", "alice", {"v": 2})
    assert do(api, root, run, "design~review", "carol", HIGH)["outcome"] == "retry"
    # The latest evaluation is on design too, so F1 resolves to it.
    assert api.disposition(run, "design", "F1", "fixed", "src/auth.py:1")["outcome"] == "recorded"
    with pytest.raises(EngineError) as e:
        api.disposition(run, "design", "F1", "maybe", "src/auth.py:1")
    assert e.value.code == "disposition.bad_value"


@pytest.mark.not_slow("measured under 1 s")
def test_rejected_evidence_is_checked_at_the_reviewed_commit(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    g("init", "-q", "-b", "main")
    g("config", "user.email", "o@example.com")
    g("config", "user.name", "O")
    (root / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "first")
    reviewed_commit = g("rev-parse", "HEAD")
    (root / "a.py").write_text("one\n", encoding="utf-8")
    (root / "b.py").write_text("new\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "second")
    head = g("rev-parse", "HEAD")
    check = lambda d, ev: reviews.check_evidence(root, d, ev, reviewed_commit=reviewed_commit, head=head)  # noqa: E731
    assert check("rejected", "a.py:3") == []  # existed when reviewed
    assert check("rejected", "b.py:1") == [f"b.py does not exist at commit {reviewed_commit[:12]}"]
    assert check("fixed", head[:10]) == []
    assert check("fixed", "deadbeef00") == ["commit deadbeef00 does not exist in this repository"]
    assert check("fixed", "a.py:3") == ["a.py has 1 lines at commit " + head[:12] + "; line 3 does not exist"]
    assert check("fixed", "a.py:1") == []


# ---------------------------------------------------------------------------
# Waivers (§9.3)
# ---------------------------------------------------------------------------

SCRIPTED = [
    {"id": "draft", "output_schema": "schemas/out.json"},
    {"id": "build", "depends_on": ["draft"], "output_schema": "schemas/out.json", "gates": [{"type": "schema"}, {"type": "script", "run": "exit 1"}]},
    {"id": "ship", "depends_on": ["build"], "output_schema": "schemas/out.json"},
]


@pytest.mark.slow
def test_a_waiver_unblocks_exactly_one_occurrence(tmp_path):
    api, root, run = _project(tmp_path, [dict(s) for s in SCRIPTED], defaults={"max_attempts": 3})
    do(api, root, run, "draft", "alice", {})
    with pytest.raises(EngineError) as e:
        api.waive(run, "build", "script", "   ")
    assert e.value.code == "waive.reason_required"
    with pytest.raises(EngineError) as e:
        api.waive(run, "build", "human", "x")
    assert e.value.code == "waive.unknown_gate"
    with pytest.raises(EngineError) as e:
        api.waive(run, "build", "0", "x")
    assert e.value.code == "waive.not_waivable"

    out = api.waive(run, "build", "script", "The CI runner is down today; accept this build once.")
    assert out["outcome"] == "waiver_pending"
    with pytest.raises(EngineError) as e:
        api.waive(run, "build", "1", "again")
    assert e.value.code == "waive.already_pending"
    out = do(api, root, run, "build", "alice", {})
    assert out["outcome"] == "passed"
    gp = [e.data for e in events(api, run, "gate_passed") if e.step_path == "build" and e.data.get("gate") == 1]
    assert gp[-1]["waived"] is True and gp[-1]["waiver_seq"] == events(api, run, "gate_waived")[-1].seq
    assert "**waived**" in api.record(run, "build")
    assert "The CI runner is down today" in api.record(run, "build")

    # The next occurrence is evaluated normally.
    api.revise(run, "build", "rebuild with the new flags")
    assert do(api, root, run, "build", "alice", {})["outcome"] == "retry"


@pytest.mark.slow
def test_a_waiver_covers_the_failed_occurrence_an_escalated_step_holds(tmp_path):
    api, root, run = _project(tmp_path, [dict(s) for s in SCRIPTED], defaults={"max_attempts": 1})
    do(api, root, run, "draft", "alice", {})
    assert do(api, root, run, "build", "alice", {})["outcome"] == "escalated"
    out = api.waive(run, "build", "script", "Known flaky check; accept this build.")
    assert out["outcome"] == "passed" and out["ready"] == ["ship"]
    w = events(api, run, "gate_waived")[-1].data
    assert w["scope"] == "held" and w["attempt"] == 1


@pytest.mark.not_slow("measured under 1 s")
def test_waiving_a_judge_at_its_iteration_limit_accepts_the_work_as_is(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx = engine.start(store, engine.load_recipe(tg.slice_recipe(tmp_path / "loop", max_iterations=1)), {}, run_id="r_w")
        tg.run_step(ctx, "plan", {"slices": [{"title": "Login"}]})
        inst = tg.expansions(ctx)[0]["items"][0]["id"]
        base = f"slices/{inst}"
        tg.run_step(ctx, f"{base}/i1/implement", {"done": True})
        out = tg.run_step(ctx, f"{base}/i1/review", tg.HIGH)[1]
        assert out.outcome == "iteration_limit"
        assert [p["kind"] for p in engine.pending_decisions(ctx)] == ["iteration_limit"]
        out = engine.waive(ctx, f"{base}/i1/review", "findings", "Accept the slice as is; F1 is tracked separately.")
        assert out.outcome == "waived" and f"{base}/i1/accept" in out.ready
        assert engine.pending_decisions(ctx) == []
        tg.run_step(ctx, f"{base}/i1/accept", {"ok": True})
        assert tg.view_of(ctx).instance_state(ctx.recipe.recipe.steps[1], "slices", inst) == "passed"


@pytest.mark.not_slow("measured under 1 s")
def test_a_worker_disposition_in_a_loop_reaches_the_next_review(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        (tmp_path / "project" / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "project" / "src" / "auth.py").write_text("x = 1\n", encoding="utf-8")
        ctx = engine.start(store, engine.load_recipe(tg.slice_recipe(tmp_path / "loop", max_iterations=3)), {}, run_id="r_l")
        tg.run_step(ctx, "plan", {"slices": [{"title": "Login"}]})
        base = f"slices/{tg.expansions(ctx)[0]['items'][0]['id']}"
        tg.run_step(ctx, f"{base}/i1/implement", {"done": True})
        tg.run_step(ctx, f"{base}/i1/review", tg.HIGH)
        p = tg.begin(ctx, f"{base}/i2/implement")
        assert "## Dispositions" in (p.dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        play(p, {"done": True}, dispositions=[{"step": "review", "finding": "F1", "disposition": "fixed", "evidence": "src/auth.py:1"}])
        assert engine.submit(ctx, f"{base}/i2/implement").outcome == "passed"
        claim = [e for e in ctx.log.events() if e.type == "finding_dispositioned"][-1]
        assert claim.data["line"] == f"{base}/review#0" and claim.step_path == f"{base}/i1/review"
        rp = tg.begin(ctx, f"{base}/i2/review")
        prior = rp.manifest["prior_findings"]
        assert {f["id"]: f.get("disposition", {}).get("disposition") for f in prior["findings"]} == {"F1": "fixed", "F2": None}
        play(rp, {"findings": [{"id": "F2", "severity": "low", "title": "naming"}], "coverage": {"complete": True}})
        assert engine.submit(ctx, f"{base}/i2/review").outcome == "passed"
        rec = [e for e in ctx.log.events() if e.type == "findings_recorded"][-1].data
        assert rec["resolved"][0]["id"] == "F1" and rec["resolved"][0]["confirmed"] is True


# ---------------------------------------------------------------------------
# Independence (§8.4, §9.3)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_same_vendor_code_review_is_refused_unless_waived(tmp_path):
    api, root, run = _project(
        tmp_path,
        [
            {"id": "implement", "output_schema": "schemas/out.json"},
            {
                "id": "code_review", "depends_on": ["implement"], "output_schema": "baton:findings",
                "independence": {"from_step": "implement", "level": "different_vendor"},
                "gates": [{"type": "findings", "block_on": ["high"]}],
            },
        ],
        defaults={"max_attempts": 3},
    )
    do(api, root, run, "implement", "alice", {})
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "code_review", "alice")
    assert e.value.code == "routing.ineligible"
    api.waive(run, "code_review", "independence", "Only one vendor is available this week; allow one self-review.")
    el = api.eligible(run, "code_review")
    alice = next(x for x in el["eligible"] if x["profile"] == "alice")
    assert any("waived for one dispatch" in r for r in alice["reasons"])
    d = api.dispatch(run, "code_review", "alice")
    disp = [e for e in events(api, run, "dispatched") if e.step_path == "code_review"][-1].data
    assert disp["waiver_seq"] == events(api, run, "gate_waived")[-1].seq
    # The waiver is used: the retry is refused again.
    write_result(packet_dir(root, run, "code_review", d["attempt"]), {"not": "findings"})
    assert api.submit(run, "code_review")["outcome"] == "retry"
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "code_review", "alice")
    assert e.value.code == "routing.ineligible"


# ---------------------------------------------------------------------------
# Protected files (§9.4)
# ---------------------------------------------------------------------------


def _protected_ctx(store: Store, tmp_path: Path, protect: Any):
    rec = make_recipe(tmp_path / "prot", [
        {"id": "implement", "workspace": "write", "protect": protect, "output_schema": "schemas/out.json",
         "requires": {"capabilities": ["structured_output", "repo_workspace"]}},
    ], schemas={"out.json": OBJ}, defaults={"max_attempts": 3})
    spec = store.root / "tests" / "acceptance" / "specs"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "login.feature").write_text("Scenario: login\n", encoding="utf-8")
    return engine.start(store, engine.load_recipe(rec), {}, run_id="r_p"), spec / "login.feature"


@pytest.mark.parametrize("mode", ["warn", "fail"])
@pytest.mark.not_slow("measured under 1 s")
def test_protected_path_changes_are_caught(tmp_path, mode):
    globs = ["tests/acceptance/specs/**"]
    protect = globs if mode == "warn" else {"paths": globs, "on_violation": "fail"}
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, spec = _protected_ctx(store, tmp_path, protect)
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        spec.write_text("Scenario: login (weakened)\n", encoding="utf-8")
        play(p, {"commit_sha": "abc"})
        out = engine.submit(ctx, "implement")
        mod = [e for e in ctx.log.events() if e.type == "protected_path_modified"]
        assert mod[-1].data == {"changed": ["tests/acceptance/specs/login.feature"], "mode": mode}
        if mode == "fail":
            assert out.outcome == "retry" and "protected paths were modified" in out.reasons[0]
            return
        assert out.outcome == "needs_human"
        assert engine.pending_decisions(ctx)[0]["prompt"].startswith("implement modified protected paths")
        out = engine.decide(ctx, "implement", "reject", "Never weaken the acceptance specs.")
        assert out.outcome == "retry" and "Never weaken" in out.reasons[0]
        # Unchanged this time (the owner reverted): passes; then a change the owner approves.
        spec.write_text("Scenario: login\n", encoding="utf-8")
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        (spec.parent / "logout.feature").write_text("Scenario: logout\n", encoding="utf-8")
        play(p, {})
        assert engine.submit(ctx, "implement").outcome == "needs_human"
        assert engine.decide(ctx, "implement", "approve", "The new spec is agreed.").outcome == "passed"


@pytest.mark.not_slow("measured under 1 s")
def test_a_protected_waiver_lets_one_change_through(tmp_path):
    with Store(tmp_path / "project", clock=Clock()) as store:
        ctx, spec = _protected_ctx(store, tmp_path, {"paths": ["tests/acceptance/specs/**"], "on_violation": "fail"})
        assert engine.waive(ctx, "implement", "protected", "The spec had a typo; one fix is agreed.").outcome == "waiver_pending"
        p = engine.begin_attempt(ctx, "implement", "w", WRITER)
        spec.write_text("Scenario: log in\n", encoding="utf-8")
        play(p, {})
        assert engine.submit(ctx, "implement").outcome == "passed"


@pytest.mark.not_slow("measured under 1 s")
def test_protect_globs_match_paths():
    assert reviews.matches("tests/acceptance/specs/a/b.feature", ["tests/acceptance/specs/**"])
    assert not reviews.matches("tests/unit/x.py", ["tests/acceptance/specs/**"])
    assert reviews.matches("docs/x.md", ["**/*.md"]) and reviews.matches("x.md", ["**/*.md"])
    assert not reviews.matches("docs/a/x.md", ["docs/*.md"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_cli_disposition_decide_and_waive(reviewed, tmp_path):
    from projectkit import Cli

    api, root, run = reviewed
    _failed_once(api, root, run)
    cli = Cli(root, tmp_path / "home")
    st = cli.run("status", run)
    assert st["findings"][0]["line"] == "design#1" and st["findings"][0]["blocking"] == ["F1"]
    out = cli.run("disposition", run, "design", "F1", "rejected", "--evidence", "src/auth.py:1")
    assert out["outcome"] == "recorded"
    bad = cli("disposition", run, "design", "F1", "rejected", "--evidence", "src/auth.py:9", expect=1).payload
    assert bad["error"] == "disposition.bad_evidence"
    assert cli.run("decide", run, "design#F1", "accept-risk", "--note", "Accepted by the owner.")["outcome"] == "recorded"
    out = cli.run("waive", run, "design", "review", "--reason", "One release without this review.")
    assert out["outcome"] == "waiver_pending"
    assert cli.run("status", run)["findings"] == []  # F1 is now an accepted risk


@pytest.mark.slow
def test_a_director_closed_finding_reopens_when_the_next_review_reports_it(reviewed):
    api, root, run = reviewed
    _failed_once(api, root, run)
    api.disposition(run, "design", "F1", "rejected", "src/auth.py:1")
    assert api.status(run)["findings"] == []  # closed on the Director's evidence
    do(api, root, run, "design", "alice", {"v": 2})
    out = do(api, root, run, "design~review", "carol", HIGH)
    assert out["outcome"] == "retry" and "after it was marked rejected" in out["reasons"][0]
    assert api.status(run)["findings"][0]["blocking"] == ["F1"]
