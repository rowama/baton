"""Event logs, hash chains, CAS and the cache (§8.3)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from baton import state as sm
from baton.state import IllegalTransition
from baton.store import CAS, ConcurrentAppend, Store, StoreError, canonical_json, event_sha256

HAPPY = ["step_ready", "worker_selected", "packet_built", "dispatched", "step_running",
         "result_submitted", "verification_started", "gate_passed", "step_passed"]


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path, clock=Clock()) as s:
        yield s


def advance(log, path: str, events: list[str]) -> None:
    for etype in events:
        log.append(etype, step_path=path, attempt=sm.attempt_for(log.state().step(path), etype))


def sample_run(store: Store, max_attempts: int | None = 3):
    log = store.start_run({"title": "Add login", "recipe": "fit-check@4", "max_attempts": max_attempts}, run_id="r_20261101_ab12")
    advance(log, "describe", HAPPY)
    advance(log, "assess", ["step_ready", "dispatched", "step_running", "result_submitted", "verification_started",
                            "gate_failed", "step_ready", "dispatched"])
    log.append("human_decision", actor="human", data={"ref": "x", "decision": "approve", "note": "ünïcode ✓"})
    return log


def lines(log) -> list[str]:
    return log.path.read_text(encoding="utf-8").splitlines()


def rewrite(log, new_lines: list[str]) -> None:
    log.path.write_text("".join(l + "\n" for l in new_lines), encoding="utf-8")


# -- appending and the chain --------------------------------------------------


def test_events_are_canonical_chained_lines(store):
    log = sample_run(store)
    raw = lines(log)
    prev = None
    for i, line in enumerate(raw, start=1):
        obj = json.loads(line)
        assert canonical_json(obj) == line
        assert obj["seq"] == i and obj["prev_sha256"] == prev
        assert obj["format"] == "baton-events/1" and obj["run_id"] == "r_20261101_ab12"
        assert event_sha256(obj) == obj["sha256"]
        prev = obj["sha256"]
    assert log.verify() == []
    assert log.path.read_bytes().endswith(b"\n") and b"\r" not in log.path.read_bytes()


def test_status(store):
    sample_run(store)
    st_ = store.status("r_20261101_ab12")
    assert st_.state == "active"
    assert st_.steps["describe"].state == "passed" and st_.steps["describe"].attempt == 1
    assert st_.steps["assess"].state == "dispatched" and st_.steps["assess"].attempt == 2


def test_illegal_append_raises_and_writes_nothing(store):
    log = sample_run(store)
    before = log.path.read_bytes()
    with pytest.raises(IllegalTransition):
        log.append("step_passed", step_path="describe", attempt=1)  # already passed
    with pytest.raises(IllegalTransition):
        log.append("dispatched", step_path="assess", attempt=5)
    with pytest.raises(StoreError):
        log.append("platform_fact_recorded")  # project-log type
    with pytest.raises(StoreError):
        log.append("made_up_event")
    with pytest.raises(StoreError):
        log.append("human_decision", data={"x": object()})  # not JSON
    with pytest.raises(ValueError):
        log.append("human_decision", actor="someone")  # actor grammar
    assert log.path.read_bytes() == before
    assert log.verify() == []


def test_start_run_refuses_existing_and_bad_ids(store):
    store.start_run({}, run_id="r_1")
    with pytest.raises(StoreError):
        store.start_run({}, run_id="r_1")
    with pytest.raises(ValueError):
        store.start_run({}, run_id="../escape")


def test_generated_run_id(store):
    log = store.start_run({})
    assert log.run_id.startswith("r_20261101_") and len(log.run_id) == len("r_20261101_ab12")
    assert store.run_ids() == [log.run_id]


def test_unknown_run(store):
    with pytest.raises(StoreError):
        store.run("r_nope")


def test_append_refuses_if_log_changed_underneath(store, monkeypatch):
    log = sample_run(store)
    real = store._state

    def stale_state(l):
        rs, size = real(l)
        with open(l.path, "ab") as f:  # another writer slips in
            f.write(b"")
        return rs, size - 1

    monkeypatch.setattr(store, "_state", stale_state)
    with pytest.raises(ConcurrentAppend):
        log.append("lease_renewed")


# -- tamper detection ----------------------------------------------------------


def _edit(line: str, **changes) -> str:
    obj = json.loads(line)
    obj.update(changes)
    return canonical_json(obj)


@pytest.mark.parametrize("where", [0, 5, -1])
def test_tampered_event_fails_the_chain_check(store, where):
    log = sample_run(store)
    raw = lines(log)
    raw[where] = _edit(raw[where], ts="2020-01-01T00:00:00.000000Z")
    rewrite(log, raw)
    assert [i.code for i in log.verify()] == ["events.hash_mismatch"]


def test_rehashed_tamper_breaks_the_next_link(store):
    log = sample_run(store)
    raw = lines(log)
    obj = json.loads(raw[3])
    obj["data"] = {"forged": True}
    obj["sha256"] = event_sha256(obj)
    raw[3] = canonical_json(obj)
    rewrite(log, raw)
    assert [i.code for i in log.verify()] == ["events.chain_broken"]


def test_deleted_reordered_and_truncated_lines(store):
    log = sample_run(store)
    raw = lines(log)
    rewrite(log, raw[:4] + raw[5:])
    assert log.verify()[0].code == "events.chain_broken"
    rewrite(log, raw[:4] + [raw[5], raw[4]] + raw[6:])
    assert log.verify()[0].code == "events.chain_broken"
    log.path.write_bytes(("\n".join(raw)).encode()[:-10])
    assert log.verify()[0].code == "events.truncated"
    rewrite(log, raw[:3] + ["{not json"] + raw[3:])
    assert log.verify()[0].code == "events.unparsable"


def test_well_formed_but_impossible_sequence_is_caught(store):
    """A chain-valid log written by something other than the store."""
    log = sample_run(store)
    raw = lines(log)
    last = json.loads(raw[-1])
    forged = {k: v for k, v in last.items() if k != "sha256"}
    forged.update(seq=last["seq"] + 1, prev_sha256=last["sha256"], type="step_passed", step_path="describe", attempt=1, data={})
    forged["sha256"] = event_sha256(forged)
    rewrite(log, raw + [canonical_json(forged)])
    assert [i.code for i in log.verify()] == ["events.impossible_state"]


def test_tampered_log_refuses_appends(store):
    log = sample_run(store)
    raw = lines(log)
    raw[2] = _edit(raw[2], actor="human")
    rewrite(log, raw)
    before = log.path.read_bytes()
    with pytest.raises(StoreError) as e:
        log.append("lease_renewed")
    assert e.value.issues[0].code == "events.hash_mismatch"
    assert log.path.read_bytes() == before


def test_bom_is_tolerated(store):
    log = sample_run(store)
    log.path.write_bytes(b"\xef\xbb\xbf" + log.path.read_bytes())
    assert log.verify() == []


# -- cache --------------------------------------------------------------------


def test_deleting_the_cache_and_rebuilding_gives_identical_status(store, tmp_path):
    sample_run(store)
    other = store.start_run({"title": "Other"}, run_id="r_20261101_cd34")
    advance(other, "triage", HAPPY)
    other.append("step_skipped", step_path="design")
    before = {rid: store.status(rid) for rid in store.run_ids()}
    store.close()
    store.cache_path.unlink()
    with Store(tmp_path) as fresh:
        assert {rid: fresh.status(rid) for rid in fresh.run_ids()} == before
        assert fresh.rebuild() == []
        assert {rid: fresh.status(rid) for rid in fresh.run_ids()} == before


@pytest.mark.skipif(os.name == "nt", reason="Windows refuses to delete an open file; the cache can only be deleted between processes there")
def test_cache_deleted_while_open(store):
    sample_run(store)
    before = store.status("r_20261101_ab12")
    store.cache_path.unlink()
    assert store.status("r_20261101_ab12") == before


def test_events_win_over_a_stale_cache(store):
    """Another clone's appends (same chain) arrive via git; the cache is behind."""
    log = sample_run(store)
    snapshot = log.path.read_bytes()
    log.append("step_running", step_path="assess", attempt=2)
    grown = log.path.read_bytes()
    log.path.write_bytes(snapshot)
    store.rebuild()  # cache now describes the shorter log
    log.path.write_bytes(grown)
    assert store.status("r_20261101_ab12").steps["assess"].state == "running"


def test_corrupt_cache_values_are_overridden_by_rebuild(store):
    sample_run(store)
    before = store.status("r_20261101_ab12")
    c = store._cache.conn()
    with c:
        c.execute("UPDATE steps SET state='passed' WHERE step_path='assess'")
    assert store.status("r_20261101_ab12") != before  # the cache is trusted while sizes match...
    assert store.rebuild() == []
    assert store.status("r_20261101_ab12") == before  # ...and rebuild restores it from events


def test_rebuild_reports_broken_runs_and_keeps_others(store):
    good = sample_run(store)
    bad = store.start_run({}, run_id="r_bad")
    raw = lines(bad)
    raw[0] = _edit(raw[0], actor="human")
    rewrite(bad, raw)
    issues = store.rebuild()
    assert [i.code for i in issues] == ["events.hash_mismatch"]
    assert store.status(good.run_id).state == "active"


# -- property: any legal sequence rebuilds to the same state ------------------


@st.composite
def legal_runs(draw):
    paths = ["triage", "design", "slices/x7f3a9c2/i1/implement"]
    rs = sm.RunState("r")
    rs.apply({"type": "run_started", "data": {"max_attempts": 2}})
    script = []
    for _ in range(draw(st.integers(0, 40))):
        path = draw(st.sampled_from(paths))
        options = sm.allowed_events(rs.step(path))
        if not options:
            continue
        etype = draw(st.sampled_from(options))
        e = {"type": etype, "step_path": path, "attempt": sm.attempt_for(rs.step(path), etype)}
        try:
            rs.apply(e)
        except IllegalTransition:  # attempt budget
            continue
        script.append(e)
    return script


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(script=legal_runs())
def test_any_legal_sequence_rebuilds_to_the_same_state(tmp_path_factory, script):
    root = tmp_path_factory.mktemp("prop")
    with Store(root, clock=Clock()) as s:
        log = s.start_run({"max_attempts": 2}, run_id="r_p")
        for e in script:
            log.append(e["type"], step_path=e["step_path"], attempt=e["attempt"])
        live = s.status("r_p")
        assert log.verify() == []
        assert s.rebuild() == []
        assert s.status("r_p") == live


# -- project log --------------------------------------------------------------


def test_project_log(store):
    plog = store.project_log()
    plog.append("platform_fact_recorded", data={"fact": "codex under nvm v22", "source": "observed"})
    plog.append("process_feedback", actor="director:abc", data={"kind": "friction", "text": "…"})
    evs = plog.events()
    assert [e.seq for e in evs] == [1, 2] and evs[0].run_id is None
    assert evs[1].prev_sha256 == evs[0].sha256
    assert plog.verify() == []
    with pytest.raises(StoreError):
        plog.append("step_ready", step_path="x")  # run-log type
    raw = lines(plog)
    raw[1] = _edit(raw[1], data={})
    rewrite(plog, raw)
    assert [i.code for i in store.verify()] == ["events.hash_mismatch"]


# -- CAS ----------------------------------------------------------------------


def test_cas_round_trip_and_dedup(tmp_path):
    cas = CAS(tmp_path / "cas")
    sha = cas.put(b"hello")
    assert sha == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert cas.path(sha) == tmp_path / "cas" / "2c" / sha
    assert cas.put(b"hello") == sha and cas.read(sha) == b"hello"
    src = tmp_path / "big.bin"
    src.write_bytes(os.urandom(3 * (1 << 20) + 7))
    sha2 = cas.put_file(src)
    assert cas.read(sha2) == src.read_bytes()
    assert cas.verify({sha, sha2}) == []
    assert not any(p.name.startswith(".tmp-") for p in (tmp_path / "cas").rglob("*"))


def test_cas_blobs_are_read_only(tmp_path):
    cas = CAS(tmp_path / "cas")
    p = cas.path(cas.put(b"x"))
    if os.name == "posix":
        assert not (p.stat().st_mode & 0o222)


def test_cas_detects_corruption_missing_and_strays(tmp_path):
    cas = CAS(tmp_path / "cas")
    sha = cas.put(b"original")
    p = cas.path(sha)
    os.chmod(p, 0o644)
    p.write_bytes(b"tampered")
    (tmp_path / "cas" / "zz").mkdir()
    (tmp_path / "cas" / "zz" / "junk").write_bytes(b"")
    missing = "0" * 64
    codes = sorted(i.code for i in cas.verify({sha, missing}))
    assert codes == ["cas.corrupt", "cas.missing", "cas.stray_file"]
    with pytest.raises(StoreError):
        cas.read(sha)
    with pytest.raises(StoreError):
        cas.read(missing)
    with pytest.raises(ValueError):
        cas.path("../etc/passwd")


def test_store_verify_covers_run_cas(store):
    log = sample_run(store)
    sha = log.cas.put(b"artifact")
    assert store.verify() == []
    p = log.cas.path(sha)
    os.chmod(p, 0o644)
    p.write_bytes(b"changed")
    assert [i.code for i in store.verify()] == ["cas.corrupt"]
