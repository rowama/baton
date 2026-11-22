"""A running marker that cannot be read for a moment never makes a live supervisor dead (§8.7, §15.1;
change 2026-11-marker-read-race). The end-to-end cases, with a real supervisor, are in ``test_async.py``."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import Any

import pytest

from baton import diag, supervisor

pytestmark = pytest.mark.not_slow("measured under 1 s")


def notes(code: str) -> list[dict[str, Any]]:
    return [r for day in diag._raw_days() for r in diag.read_records(day) if r["code"] == code]


@pytest.fixture(autouse=True)
def quick_settle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supervisor, "SETTLE_DELAYS_S", (0.001, 0.001, 0.001))


def _marker(baton_dir: Path, **extra: Any) -> Path:
    supervisor.write_marker(baton_dir, {"dispatch_id": "d_1", "host": supervisor.socket.gethostname(),
                                        "supervisor_pid": os.getpid(), **extra})
    return supervisor.marker_path(baton_dir, "d_1")


def _fail_reads(monkeypatch: pytest.MonkeyPatch, path: Path, times: int) -> list[int]:
    """Make the next ``times`` reads of ``path`` fail as a read during a replace does on a Windows drive under WSL."""
    real = Path.read_text
    seen = [0]

    def read_text(self: Path, *a: Any, **kw: Any) -> str:
        if self == path and seen[0] < times:
            seen[0] += 1
            raise OSError(errno.ENODATA, "No data available")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", read_text)
    return seen


def test_a_read_that_fails_once_is_retried_and_noted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _marker(tmp_path)
    _fail_reads(monkeypatch, path, 1)
    state, m = supervisor.settled_marker(tmp_path, "d_1")
    assert state == "present" and m is not None and m["supervisor_pid"] == os.getpid()
    lv = supervisor.liveness(tmp_path, "d_1")
    assert lv.supervisor_alive and not lv.dead
    rec = notes("supervisor.marker_unreadable")[0]["data"]
    assert rec["recovered"] is True and rec["looks"] == 2 and "No data available" in rec["error"]


def test_a_marker_that_stays_unreadable_is_never_judged_dead(tmp_path: Path) -> None:
    path = _marker(tmp_path)
    path.write_text("{half written", encoding="utf-8")
    assert supervisor.settled_marker(tmp_path, "d_1") == ("unreadable", None)
    lv = supervisor.liveness(tmp_path, "d_1")
    assert lv.unreadable and not lv.supervisor_alive and not lv.dead
    assert lv.as_dict()["unreadable"] is True and lv.as_dict()["marker"] is False
    rec = notes("supervisor.marker_unreadable")[-1]["data"]
    assert rec["recovered"] is False and rec["looks"] == len(supervisor.SETTLE_DELAYS_S) + 1


def test_an_absent_marker_is_absent_on_every_look_before_it_counts(tmp_path: Path) -> None:
    assert supervisor.settled_marker(tmp_path, "d_1") == ("absent", None)
    lv = supervisor.liveness(tmp_path, "d_1")
    assert lv.dead and not lv.unreadable
    assert notes("supervisor.marker_unreadable") == []


def test_a_marker_that_appears_between_looks_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Absent on the first look (a replace in progress), there on the second.
    looks = [0]
    real_sleep = supervisor.time.sleep

    def sleep(s: float) -> None:
        looks[0] += 1
        if looks[0] == 1:
            _marker(tmp_path)
        real_sleep(s)

    monkeypatch.setattr(supervisor.time, "sleep", sleep)
    state, m = supervisor.settled_marker(tmp_path, "d_1")
    assert state == "present" and m is not None


def test_a_marker_from_another_host_is_not_judged(tmp_path: Path) -> None:
    _marker(tmp_path, host="elsewhere.example")
    lv = supervisor.liveness(tmp_path, "d_1")
    assert lv.elsewhere and not lv.dead


def test_a_dead_supervisor_with_a_readable_marker_is_still_dead(tmp_path: Path) -> None:
    _marker(tmp_path, supervisor_pid=2**22 + 12345)  # no such process
    lv = supervisor.liveness(tmp_path, "d_1")
    assert lv.marker is not None and lv.dead


def test_polling_reads_stay_single_looks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # read_marker is for polling (dispatch's start, wait's loop): one look, no pause.
    path = _marker(tmp_path)
    seen = _fail_reads(monkeypatch, path, 1)
    assert supervisor.read_marker(tmp_path, "d_1") is None and seen[0] == 1
    assert json.loads(path.read_text(encoding="utf-8"))["dispatch_id"] == "d_1"


def test_an_unreadable_marker_is_judged_only_well_past_the_attempts_deadline() -> None:
    # A marker that never becomes readable again must not hold its attempt "running" for ever: once the deadline
    # (the last extension, else the dispatch's) is past by the grace, a live supervisor would have finished.
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from baton.engine import Api

    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    ts = supervisor.fmt
    grace = Api.UNREADABLE_GRACE

    def judged(deadline: datetime, extended: datetime | None = None) -> bool:
        events = [SimpleNamespace(type="deadline_extended", step_path="s", attempt=1, data={"deadline": ts(extended)})] if extended else []
        ctx = SimpleNamespace(log=SimpleNamespace(events=lambda: events, clock=lambda: now))
        return Api._unreadable_too_long(Api, ctx, "s", 1, {"deadline": ts(deadline)})  # type: ignore[arg-type]

    assert not judged(now + timedelta(hours=1))
    assert not judged(now - grace + timedelta(seconds=1))
    assert judged(now - grace - timedelta(seconds=1))
    assert not judged(now - timedelta(hours=1), extended=now + timedelta(minutes=30))  # extended: the new deadline counts
    assert not Api._unreadable_too_long(Api, SimpleNamespace(log=SimpleNamespace(events=lambda: [], clock=lambda: now)), "s", 1, {})  # type: ignore[arg-type]
