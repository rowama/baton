"""`baton diag`, the doctor warning and the platform SME's evidence (§13.1, §13.2, §13.4, §12.3; change 2026-11-diagnostics)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from baton import diag

from projectkit import setup_fit_check

pytestmark = pytest.mark.not_slow("measured under 1 s")


def put_counts(home: Path, day: str, counts: dict[str, int]) -> None:
    d = home / "diag" / "counts"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{day}.json").write_text(json.dumps({"day": day, "counts": {"/p": counts}}))


def history(home: Path, recent: dict[str, int], before: dict[str, int] | None = None) -> None:
    start = datetime(2026, 9, 1)
    for i in range(37):
        put_counts(home, (start + timedelta(days=i)).strftime("%Y-%m-%d"), recent if i >= 30 else (before or {}))


def test_diag_with_nothing_recorded_says_so_and_exits_zero(tmp_path: Path) -> None:
    cli, _ = setup_fit_check(tmp_path)
    out = cli.run("diag")
    assert out["codes"] == [] and out["unusual"] == [] and out["usage_days"] == 0
    assert out["worker_logs"] == {"bytes": 0, "files": 0, "oldest_age_days": None}


@pytest.mark.slow
def test_diag_lists_counts_against_the_baseline_with_unusual_first(tmp_path: Path) -> None:
    cli, _ = setup_fit_check(tmp_path)
    history(cli.home, {"a.steady": 2, "b.rising": 6}, {"a.steady": 2, "b.rising": 1})
    out = cli.run("diag")
    assert [r["code"] for r in out["codes"]] == ["b.rising", "a.steady"]
    assert out["codes"][0]["unusual"] and out["codes"][0]["baseline_per_day"] == 1.0
    assert [r["code"] for r in cli.run("diag", "--code", "a.")["codes"]] == ["a.steady"]
    assert cli.run("diag", "--since", "2")["usage_days"] == 2


@pytest.mark.slow
def test_diag_records_shows_raw_records_newest_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli, _ = setup_fit_check(tmp_path)
    monkeypatch.setenv("BATON_HOME", str(cli.home))
    diag.reset()
    diag.note("x.one", "t:t", run="r1", n=1)
    diag.note("x.two", "t:t", run="r1", n=2)
    out = cli.run("diag", "--records", "--run", "r1")
    assert [r["code"] for r in out["records"]] == ["x.one", "x.two"]


@pytest.mark.slow
def test_doctor_is_one_line_when_healthy_and_warns_once_when_unusual(tmp_path: Path) -> None:
    cli, _ = setup_fit_check(tmp_path)
    healthy = cli.run("doctor", "--no-run")
    assert healthy["ok"] and not any(w.startswith("diagnostics:") for w in healthy["warnings"]) and "diag_unusual" not in healthy
    assert healthy["worker_logs"]["files"] == 0
    history(cli.home, {"cache.replay": 6}, {"cache.replay": 1})
    out = cli.run("doctor", "--no-run")
    assert [w for w in out["warnings"] if w.startswith("diagnostics:")] == ["diagnostics: 1 unusual condition(s); see baton diag"]
    assert out["diag_unusual"] == [{"code": "cache.replay", "last_7d": 42, "baseline_per_day": 1.0}]


@pytest.mark.slow
def test_detect_leaves_the_diagnostics_warning_out(tmp_path: Path) -> None:
    cli, _ = setup_fit_check(tmp_path)
    history(cli.home, {"cache.replay": 6}, {"cache.replay": 1})
    assert cli.run("doctor", "--no-run")["warnings"]
    out = cli.run("detect")
    assert not any("diagnostics:" in w for w in out.get("warnings", []))


@pytest.mark.slow
def test_the_platform_sme_gets_the_incident_run_step_and_attempt_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baton import sme
    from baton.engine import Api

    cli, project = setup_fit_check(tmp_path)
    monkeypatch.setenv("BATON_HOME", str(cli.home))
    diag.reset()
    diag.note("harness.version_probe_failed", "engine:x", run="r9", step_path="a", attempt=1, exe="/x")
    diag.note("harness.version_probe_failed", "engine:x", run="r9", step_path="a", attempt=2)
    diag.note("other.thing", "engine:x", run="r10", step_path="a", attempt=1)
    api = Api.open(project, director_id="alice@host1", home=cli.home)
    inc = api._open_incident({"run": "r9", "step_path": "a", "attempt": 1, "class": "platform", "code": "x", "message": "m", "worker": "owner"})
    src = sme.Sources(api.project, None) if hasattr(sme, "Sources") else None
    items = sme.resolve(src, f"incident:{inc}", "platform")
    ev = [i for i in items if i.filename.endswith("-diagnostics.jsonl")]
    assert len(ev) == 1
    recs = [json.loads(line) for line in ev[0].content.decode().splitlines()]
    assert [(r["run"], r["attempt"]) for r in recs] == [("r9", 1)]  # this run, step and attempt only
