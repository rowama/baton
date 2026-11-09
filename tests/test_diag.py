"""The diagnostic channel (§8.3, change 2026-11-diagnostics, Decision 0094): writer, retention and rollup."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from baton import diag

pytestmark = pytest.mark.not_slow("measured under 1 s")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BATON_HOME", str(tmp_path / "home"))
    diag.reset()
    return tmp_path / "home"


def at(monkeypatch: pytest.MonkeyPatch, day: str, hour: int = 12) -> None:
    t = datetime.strptime(day, "%Y-%m-%d").replace(hour=hour, tzinfo=timezone.utc)
    monkeypatch.setattr(diag, "_now", lambda: t)


def records(home: Path, day: str) -> list[dict]:
    out = []
    for f in sorted((home / "diag" / "raw" / day).glob("*.jsonl")):
        out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    return out


def seed(home: Path, day: str, code: str = "x.y", n: int = 1, size: int = 0, project: str = "") -> None:
    d = home / "diag" / "raw" / day
    d.mkdir(parents=True, exist_ok=True)
    pad = "p" * size
    with open(d / "1-seed.jsonl", "a", encoding="utf-8") as f:
        for _ in range(n):
            f.write(json.dumps({"ts": f"{day}T00:00:00.000Z", "code": code, "where": "t:t", "pid": 1, "project": project, "data": {"pad": pad}, "count": 1}) + "\n")


def test_note_writes_a_record_with_context_in_a_per_process_file(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at(monkeypatch, "2026-11-09")
    diag.note("cache.replay", "store:_state", reason="missing", project="/p", run="r1", step_path="a/b", attempt=2)
    (rec,) = records(home, "2026-11-09")
    assert rec["code"] == "cache.replay" and rec["where"] == "store:_state" and rec["pid"] == os.getpid()
    assert (rec["project"], rec["run"], rec["step_path"], rec["attempt"]) == ("/p", "r1", "a/b", 2)
    assert rec["data"] == {"reason": "missing"} and rec["ts"].startswith("2026-11-09T12:00:00")
    (f,) = (home / "diag" / "raw" / "2026-11-09").iterdir()
    assert f.name.startswith(f"{os.getpid()}-") and f.suffix == ".jsonl"


def test_note_never_raises_when_the_home_is_unwritable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    monkeypatch.setenv("BATON_HOME", str(blocker / "sub"))
    diag.reset()
    diag.note("a.b", "t:t", x=1)
    assert diag.failures() == 1


def test_note_never_raises_on_a_full_disk_or_odd_data(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(diag, "_append", full)
    diag.note("a.b", "t:t")
    assert diag.failures() == 1
    monkeypatch.undo()
    monkeypatch.setenv("BATON_HOME", str(home))

    class Odd:
        def __str__(self) -> str:
            raise RuntimeError("no str")

    diag.note("a.b", "t:t", odd=Odd(), path=Path("/x"))
    assert diag.failures() >= 1  # the unprintable value is swallowed too


def test_strings_are_redacted_before_they_are_written(home: Path) -> None:
    secret = "sk-ant-api03-" + "A1b2C3d4" * 6
    diag.note("a.b", "t:t", error=f"boom {secret}", nested={"k": [f"x {secret}"]}, path=Path("/ok"))
    text = "".join(f.read_text(encoding="utf-8") for f in (home / "diag").rglob("*.jsonl"))
    assert secret not in text and "[REDACTED]" in text and "/ok" in text


@pytest.mark.slow
def test_concurrent_processes_write_their_own_files_and_lose_nothing(home: Path) -> None:
    code = "from baton import diag\nfor i in range(50): diag.note('c.p', 't:t', i=i)\n"
    env = {**os.environ, "BATON_HOME": str(home)}
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env) for _ in range(4)]
    assert [p.wait() for p in procs] == [0] * 4
    day = diag._today()
    assert len(list((home / "diag" / "raw" / day).glob("*.jsonl"))) == 4
    assert len(records(home, day)) == 200


def test_burst_suppression_keeps_counts_exact(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at(monkeypatch, "2026-11-09")
    (home).mkdir(parents=True)
    (home / "diag.yaml").write_text("burst: 5\n")
    diag.reset()
    for _ in range(250):
        diag.note("storm", "t:t")
    diag.flush()
    recs = records(home, "2026-11-09")
    assert len(recs) < 20
    assert sum(r["count"] for r in recs) == 250
    assert sum(1 for r in recs if "suppressed" not in r) == 5
    assert diag.daily_counts()["2026-11-09"][""]["storm"] == 250


def test_rollup_is_idempotent_and_counts_per_project_and_code(home: Path) -> None:
    seed(home, "2026-11-01", "a.b", 3, project="/p1")
    seed(home, "2026-11-01", "c.d", 2, project="/p2")
    diag.rollup("2026-11-01")
    first = (home / "diag" / "counts" / "2026-11-01.json").read_bytes()
    diag.rollup("2026-11-01")
    assert (home / "diag" / "counts" / "2026-11-01.json").read_bytes() == first
    assert json.loads(first)["counts"] == {"/p1": {"a.b": 3}, "/p2": {"c.d": 2}}


def test_maintenance_rolls_up_then_prunes_by_usage_days_and_keeps_today(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (home).mkdir(parents=True)
    (home / "diag.yaml").write_text("raw_days: 3\n")
    for d in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"):
        seed(home, d, n=2)
    # A long idle gap: today is a month later, and no old day ages out merely for being old.
    seed(home, "2026-11-09", n=1)
    diag.maintain("2026-11-09")
    kept = sorted(p.name for p in (home / "diag" / "raw").iterdir())
    assert kept == ["2026-10-04", "2026-10-05", "2026-11-09"]
    rolled = sorted(p.stem for p in (home / "diag" / "counts").glob("*.json"))
    assert rolled == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]
    assert diag.daily_counts()["2026-10-01"][""]["x.y"] == 2  # detail gone, counts kept


def test_idle_calendar_days_do_not_age_records_out(home: Path) -> None:
    (home).mkdir(parents=True)
    (home / "diag.yaml").write_text("raw_days: 14\n")
    seed(home, "2026-01-01", n=1)
    seed(home, "2026-06-01", n=1)
    diag.maintain("2026-06-01")
    assert (home / "diag" / "raw" / "2026-01-01").exists()


def test_maintenance_prunes_by_size_oldest_first_and_never_the_current_day(home: Path) -> None:
    (home).mkdir(parents=True)
    (home / "diag.yaml").write_text("raw_max_bytes: 3000\n")
    for d in ("2026-11-05", "2026-11-06", "2026-11-07"):
        seed(home, d, size=1500)
    seed(home, "2026-11-08", size=4000)  # today alone is over the limit
    diag.maintain("2026-11-08")
    assert [p.name for p in (home / "diag" / "raw").iterdir()] == ["2026-11-08"]
    assert len(list((home / "diag" / "counts").glob("*.json"))) == 3


def test_counts_older_than_count_days_are_pruned(home: Path) -> None:
    (home).mkdir(parents=True)
    (home / "diag.yaml").write_text("count_days: 2\n")
    for d in ("2026-10-01", "2026-10-02", "2026-10-03"):
        seed(home, d)
    diag.maintain("2026-11-09")
    assert sorted(p.stem for p in (home / "diag" / "counts").glob("*.json")) == ["2026-10-02", "2026-10-03"]


def test_maintenance_runs_once_per_utc_day_by_exclusive_create(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(diag, "maintain", lambda day=None: calls.append(day))
    at(monkeypatch, "2026-11-09")
    diag.note("a.b", "t:t")
    diag.note("a.b", "t:t")
    assert calls == ["2026-11-09"] and (home / "diag" / ".maintained-2026-11-09").exists()
    at(monkeypatch, "2026-11-10")
    diag.note("a.b", "t:t")
    assert calls == ["2026-11-09", "2026-11-10"]
    assert not (home / "diag" / ".maintained-2026-11-09").exists()


def test_a_failing_maintenance_is_noted_once_and_never_raised(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(day=None):
        raise OSError("disk on fire")

    monkeypatch.setattr(diag, "maintain", boom)
    at(monkeypatch, "2026-11-09")
    diag.note("a.b", "t:t")
    diag.note("a.b", "t:t")
    failed = [r for r in records(home, "2026-11-09") if r["code"] == "diag.maintenance_failed"]
    assert len(failed) == 1 and "disk on fire" in failed[0]["data"]["error"]


def test_timestamps_are_utc_days(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    t = datetime(2026, 11, 9, 23, 59, 59, tzinfo=timezone(timedelta(hours=-5))).astimezone(timezone.utc)
    monkeypatch.setattr(diag, "_now", lambda: t)
    diag.note("a.b", "t:t")
    assert (home / "diag" / "raw" / "2026-11-10").is_dir()
