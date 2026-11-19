"""Capability checks run once (§6.4; change 2026-11-model-assessment, slice 1; Decisions 0175, 0176, 0177)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from baton import capability_check as cc
from baton import capability_states as cs
from baton import cli, listings, resources, vocab
from baton import worker_runner as wr

TODAY = dt.date(2026, 11, 18)

pytestmark = pytest.mark.not_slow("in-process, with a fake runner")


def listing(*models):
    return {"data": [{"id": m, "canonical_slug": m, "context_length": 32000, "pricing": {"prompt": p, "completion": p},
                      "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}, "supported_parameters": params}
                     for m, p, params in models]}


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    resources.declare(h, "or", provider="openrouter", credential="secret:or_key")
    raw = listing(("acme/small:free", "0", ["response_format"]), ("acme/big", "0.000002", ["response_format", "tools"]))
    listings.refresh(h, "openrouter", fetch=lambda url: raw, today=TODAY)
    resources.setup(h, today=TODAY, discover_fn=lambda hh, d: {})
    return h


def answer(task: cc.Task) -> dict:
    """A reply that passes ``task``, built from its graders (for the fake runner)."""
    out: dict = {}
    for g in task.grade:
        if g["type"] == "equals":
            out[g["field"]] = g["value"]
    if task.capability == "long_form_writing":
        field = task.grade[0]["field"]
        if task.id == "lf-sections":
            body = " ".join(["word"] * 100)
            out[field] = "\n".join(f"## Part {i}\n{body}\nbudget volunteers schedule" for i in range(4))
        elif task.id == "lf-steps":
            out[field] = "\n".join(f"{i}. Do step {i}." for i in range(1, 6))
        else:
            out[field] = "In 1998 the mill on the River Wend reopened."
    return {"status": "completed", "output": out}


def fake_runner(fail: set[str] = frozenset(), error: set[str] = frozenset(), calls: list | None = None):
    def run(home, name, profile, task):
        if calls is not None:
            calls.append((name, task.id))
        if task.id in error:
            return cc.TaskOutcome(task, error="platform (provider_unavailable): no answer", seconds=1.0)
        env = {"status": "completed", "output": {}} if task.id in fail else answer(task)
        log = [{"tool": t} for t in ("list_files", "read_file", "finish")]
        reasons = cc.grade(task, env, log)
        return cc.TaskOutcome(task, not reasons, reasons, None, 2.0, {"calls": 1, "input_tokens": 500, "output_tokens": 50,
                                                                        "cost_usd": 0.0001, "seconds": 2.0})
    return run


# ---------------------------------------------------------------------------
# The shipped set
# ---------------------------------------------------------------------------


def test_the_shipped_set_is_valid_versioned_and_covers_five_capabilities():
    s = cc.load_set()
    assert s.version >= 1
    assert set(s.capabilities()) == {"structured_output", "tool_use", "workspace_read", "long_form_writing", "technical_reasoning"}
    assert "vision" not in s.capabilities()  # Decision 0177, item 1
    for cap in s.capabilities():
        assert 3 <= len(s.for_capability(cap)) <= 5, cap  # Decision 0176, item 2
    words = vocab.load(vocab.DEFAULT).capabilities
    assert all(c in words for c in s.capabilities())


def test_every_shipped_task_passes_its_own_right_answer():
    for t in cc.load_set().tasks:
        log = [{"tool": x} for x in ("list_files", "read_file", "finish")]
        assert cc.grade(t, answer(t), log) == [], t.id


@pytest.mark.parametrize("edit, fragment", [
    (lambda r: r.update(format="x/1"), "expected format"),
    (lambda r: r.update(version=0), "version must be"),
    (lambda r: r["checks"].update(teleport=[{"id": "x", "prompt": "p", "output_schema": {}, "grade": [{"type": "schema"}]}]), "not a capability"),
    (lambda r: r["checks"]["tool_use"][0].update(id=r["checks"]["tool_use"][1]["id"]), "used twice"),
    (lambda r: r["checks"]["tool_use"][0]["grade"].append({"type": "vibes"}), "is not one of"),
    (lambda r: r["checks"]["tool_use"][0].update(tools=["shell"]), "not runner tools"),
    (lambda r: r["checks"]["tool_use"][0].update(workspace={"../x": "y"}), "relative paths"),
    (lambda r: r["checks"]["long_form_writing"][0]["grade"].append({"type": "words"}), "needs a field"),
])
def test_an_invalid_set_is_refused_naming_the_problem(edit, fragment):
    raw = yaml.safe_load(cc.set_path().read_text(encoding="utf-8"))
    edit(raw)
    with pytest.raises(cc.CheckError) as e:
        cc.parse(raw, "set.yaml", vocab.load(vocab.DEFAULT).capabilities)
    assert fragment in str(e.value)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def task(*grade, schema=None) -> cc.Task:
    return cc.Task("x", "t", "p", schema or {"type": "object"}, tuple(grade))


def test_graders_pass_and_fail_by_code():
    ok = {"status": "completed", "output": {"a": " Heron ", "n": "7", "doc": "## One\nbudget words here\n## Two\n1. a\n2. b"}}
    assert cc.grade(task({"type": "equals", "field": "a", "value": "heron"}), ok, None) == []          # case and spaces ignored
    assert cc.grade(task({"type": "equals", "field": "n", "value": 7}), ok, None) == []                # "7" is 7
    assert cc.grade(task({"type": "equals", "field": "a", "value": "crane"}), ok, None)
    assert cc.grade(task({"type": "contains_all", "field": "doc", "values": ["BUDGET"]}), ok, None) == []
    assert cc.grade(task({"type": "contains_all", "field": "doc", "values": ["schedule"]}), ok, None) == ["doc lacks schedule"]
    assert cc.grade(task({"type": "excludes", "field": "doc", "values": ["word"]}), ok, None) == []    # whole words only
    assert cc.grade(task({"type": "excludes", "field": "doc", "values": ["words"]}), ok, None)
    assert cc.grade(task({"type": "headings", "field": "doc", "count": 2}), ok, None) == []
    assert cc.grade(task({"type": "headings", "field": "doc", "count": 3}), ok, None)
    assert cc.grade(task({"type": "numbered", "field": "doc", "count": 2}), ok, None) == []
    assert cc.grade(task({"type": "words", "field": "doc", "max": 5}), ok, None)
    assert cc.grade(task({"type": "schema"}, schema={"type": "object", "required": ["zzz"]}), ok, None)
    # a tool log is graded only when the route keeps one
    t = task({"type": "tool_called", "tool": "read_file"})
    assert cc.grade(t, ok, None) == [] and cc.grade(t, ok, []) == ["no successful read_file call"]
    assert cc.grade(t, ok, [{"tool": "read_file", "refused": "no"}]) == ["no successful read_file call"]
    assert cc.grade(t, {"status": "failed", "output": None, "notes": "gave up"}, None) == ["the result's status is 'failed': gave up"]
    assert cc.grade(t, None, None) == ["no result was written"]


# ---------------------------------------------------------------------------
# Planning, estimates, results and the track record
# ---------------------------------------------------------------------------


def test_the_estimate_comes_first_and_nothing_runs_without_asking(home):
    calls = []
    out = cc.check(home, ["or-acme-big", "or-acme-small-free"], run=False, runner=fake_runner(calls=calls), today=TODAY)
    assert calls == [] and out["results"] == []
    rows = {r["profile"]: r for r in out["estimate"]["profiles"]}
    assert rows["or-acme-small-free"]["cost_usd"] == 0.0 and rows["or-acme-big"]["cost_usd"] > 0
    assert out["estimate"]["cost_usd"] == rows["or-acme-big"]["cost_usd"]
    # an unjudged listing model is checked for what a check may add (0176, item 3), never technical_reasoning
    assert rows["or-acme-big"]["capabilities"] == ["structured_output", "tool_use", "workspace_read"]
    assert rows["or-acme-small-free"]["adding"] == ["tool_use"] and "technical_reasoning" not in rows["or-acme-small-free"]["capabilities"]


def test_passes_verify_failures_mark_absent_and_errors_record_nothing(home):
    out = cc.check(home, ["or-acme-big"], runner=fake_runner(fail={"tu-sum"}, error={"wr-rows"}), today=TODAY)
    r = out["results"][0]
    assert r["verified"] == ["structured_output"] and r["absent"] == ["tool_use"] and r["not_checked"] == ["workspace_read"]
    st = cs.load(home)["or-acme-big"]
    assert st["structured_output"].state == "verified" and st["structured_output"].by == "check" and st["structured_output"].set_version == 1
    assert st["tool_use"].state == "absent" and "tu-sum" in st["tool_use"].evidence
    assert "workspace_read" not in st  # it could not run: nothing is recorded
    assert r["by_capability"]["workspace_read"]["error"].startswith("platform (provider_unavailable)")
    rec = cc.load_record(home)["or-acme-big"]["checks"]
    assert rec["complete"] is False and rec["cost_usd"] == pytest.approx(0.0001 * (len(r["tasks"]) - 1))  # the task that could not run cost nothing known and rec["seconds"] > 0
    # an incomplete check is due again
    assert cc.plan(home, cc.load_set(), ["or-acme-big"])[0]


def test_a_checked_model_is_skipped_until_asked_again_or_the_set_changes(home, tmp_path):
    cc.check(home, ["or-acme-big"], runner=fake_runner(), today=TODAY)
    again = cc.check(home, ["or-acme-big"], runner=fake_runner(), today=TODAY)
    assert again["results"] == [] and "already checked on 2026-11-18" in again["skipped"][0]["reason"]
    assert cc.check(home, ["or-acme-big"], again=True, runner=fake_runner(), today=TODAY)["results"]
    raw = yaml.safe_load(cc.set_path().read_text(encoding="utf-8"))
    raw["version"] += 1
    newer = tmp_path / "set.yaml"
    newer.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert cc.check(home, ["or-acme-big"], runner=fake_runner(), today=TODAY, set_file=newer)["results"]


def test_an_alias_route_is_always_checked_again(home):
    path = home / "workers" / "or-acme-big.yaml"
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    body.pop("model_id")
    planned, _ = cc.plan(home, cc.load_set(), None)
    cc.check(home, ["or-acme-big"], runner=fake_runner(), today=TODAY)
    monkey = dict(body, generated=body["generated"])
    path.write_text(yaml.safe_dump(monkey), encoding="utf-8")  # now an alias (no model_id), and edited: still a generated file
    assert cc.check(home, ["or-acme-big"], runner=fake_runner(), today=TODAY)["results"]


def test_a_passed_check_adds_tool_use_to_an_unjudged_model_through_setup(home):
    before = yaml.safe_load((home / "workers" / "or-acme-small-free.yaml").read_text(encoding="utf-8"))
    assert "tool_use" not in before["capabilities"]
    out = cc.check(home, ["or-acme-small-free"], runner=fake_runner(), today=TODAY,
                   resetup=lambda h: resources.setup(h, today=TODAY, discover_fn=lambda hh, d: {}))
    assert out["results"][0]["added"] == ["tool_use"] and "or-acme-small-free" in out["setup"]["refreshed"]
    after = yaml.safe_load((home / "workers" / "or-acme-small-free.yaml").read_text(encoding="utf-8"))
    assert "tool_use" in after["capabilities"] and "technical_reasoning" not in after["capabilities"]
    assert cs.load(home)["or-acme-small-free"]["tool_use"].state == "verified"


def test_a_failed_addition_is_never_added_and_an_owner_absent_is_not_argued_with(home):
    cc.check(home, ["or-acme-small-free"], runner=fake_runner(fail={"tu-find"}), today=TODAY, resetup=lambda h: {})
    assert cc.added(home) == {}
    cs.declare(home, "or-acme-big", ["structured_output", "tool_use"], absent=["tool_use"])
    planned, _ = cc.plan(home, cc.load_set(), ["or-acme-big"], again=True)
    assert "tool_use" not in planned[0].capabilities


def test_filters_choose_free_models_or_one_provider_and_unknown_names_are_said(home):
    planned, _ = cc.plan(home, cc.load_set(), None, free=True)
    assert [p.name for p in planned] == ["or-acme-small-free"]
    by_or = cc.plan(home, cc.load_set(), None, provider="or")[0]  # researched routes through the account too
    assert {"or-acme-big", "or-acme-small-free"} <= {p.name for p in by_or} and all(p.body["resource"] == "or" for p in by_or)
    assert cc.plan(home, cc.load_set(), None, provider="elsewhere")[0] == []
    _, skipped = cc.plan(home, cc.load_set(), ["nope"])
    assert "not a model Baton set up" in skipped[0]["reason"]


def test_workers_status_and_the_page_rows_show_the_last_check(home):
    cc.check(home, ["or-acme-big"], runner=fake_runner(), today=TODAY)
    g = resources.status(home, discover_fn=lambda h, d: {})["generated"]["or-acme-big"]
    assert g["capability_check"]["date"] == "2026-11-18" and g["capability_check"]["results"]["tool_use"] == "verified"
    from baton import ui

    rows = ui._models(home, resources.status(home, discover_fn=lambda h, d: {}))
    assert next(r for r in rows if r["profile"] == "or-acme-big")["capability_check"]["set_version"] == 1


def test_the_command_shows_the_estimate_and_runs_only_with_yes(home, monkeypatch):
    monkeypatch.setenv("BATON_HOME", str(home))
    calls = []
    real = cc.check
    monkeypatch.setattr(cc, "check", lambda h, *a, **kw: real(h, *a, runner=fake_runner(calls=calls), today=TODAY, **kw))
    r = CliRunner().invoke(cli.app, ["workers", "check"])
    assert r.exit_code != 0 and "name the workers to check" in r.output
    r = CliRunner().invoke(cli.app, ["workers", "check", "or-acme-big"])
    assert r.exit_code == 0 and "about $" in r.output and "Add --yes" in r.output and calls == []
    r = CliRunner().invoke(cli.app, ["workers", "check", "or-acme-big", "--yes", "--json"])
    out = json.loads(r.output)
    assert out["ran"] is True and out["results"][0]["verified"] == ["structured_output", "tool_use", "workspace_read"] and calls
    r = CliRunner().invoke(cli.app, ["workers", "status"])
    assert "checked 2026-11-18 (set 1)" in r.output


def test_the_page_route_estimates_then_runs(home, monkeypatch):
    from baton import ui

    real = cc.check
    monkeypatch.setattr(cc, "check", lambda h, *a, **kw: real(h, *a, runner=fake_runner(), today=TODAY, **kw))
    est = ui._check(home, {"profiles": ["or-acme-big"]}, {})
    assert est["results"] == [] and est["estimate"]["tasks"] > 0
    ran = ui._check(home, {"profiles": ["or-acme-big"], "run": True}, {})
    assert ran["results"][0]["verified"]
    with pytest.raises(ui.UiError):
        ui._check(home, {"profiles": []}, {})


# ---------------------------------------------------------------------------
# The runner's usage record (Decision 0177, item 2)
# ---------------------------------------------------------------------------


def test_the_meter_counts_tokens_cost_and_time_of_every_call(tmp_path):
    def complete(**kw):
        r = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30))
        r._hidden_params = {"response_cost": 0.002}
        return r

    m = wr.Meter(complete)
    m(model="x", messages=[])
    m(model="x", messages=[])
    assert m.as_dict()["calls"] == 2 and m.input_tokens == 240 and m.output_tokens == 60 and m.cost_usd == pytest.approx(0.004)
    unknown = wr.Meter(lambda **kw: SimpleNamespace(usage=None), cost_of=lambda r: 1 / 0)
    unknown()
    assert unknown.cost_usd is None and unknown.calls == 1
    wr.write_usage(tmp_path / "attempt", m)
    assert json.loads((tmp_path / "attempt" / "usage.json").read_text())["output_tokens"] == 60


def test_a_check_state_survives_a_schema_pass_and_resets_with_the_harness_version(tmp_path):
    cs.record(tmp_path, "codex", "structured_output", "verified", by="check", evidence="e", today=TODAY, harness_version="1", set_version=1)
    cs.schema_gate(tmp_path, "codex", False)
    cs.schema_gate(tmp_path, "codex", True)
    assert cs.load(tmp_path)["codex"]["structured_output"].set_version == 1
    assert cs.reset_on_version(tmp_path, "codex", "2") == ["structured_output"]


def test_a_task_packet_is_what_the_adapters_read(tmp_path):
    t = next(x for x in cc.load_set().tasks if x.id == "tu-find")
    packet, result, ws = cc.write_packet(tmp_path / "api", t, api=True)
    m = json.loads((packet / "manifest.json").read_text())
    assert m["tools"] == ["list_files", "read_file"] and m["workspace"] == "read" and (ws / "notes" / "tuesday.txt").is_file()
    assert wr.build_messages(packet)[1]["content"].startswith("# A capability check")
    packet, _r, _w = cc.write_packet(tmp_path / "harness", t, api=False)
    assert "tools" not in json.loads((packet / "manifest.json").read_text()) and "result.json" in (packet / "INSTRUCTIONS.md").read_text()


def test_a_rate_limited_route_waits_retries_and_then_stops_hammering(home):
    calls, waits = [], []
    limited = {"so-classify": 1}  # limited once, then fine

    def run(h, name, profile, t):
        calls.append(t.id)
        if limited.get(t.id, 0) > 0:
            limited[t.id] -= 1
            return cc.TaskOutcome(t, error="platform (quota_exhausted): rate-limited upstream")
        if t.id == "tu-find":
            return cc.TaskOutcome(t, error="platform (quota_exhausted): rate-limited upstream")
        return fake_runner()(h, name, profile, t)

    out = cc.check(home, ["or-acme-big"], runner=run, today=TODAY, sleep=waits.append)
    r = out["results"][0]
    assert calls.count("so-classify") == 2 and calls.count("tu-find") == 1 + cc.RATE_RETRIES
    assert waits == [cc.RATE_WAIT_S, cc.RATE_WAIT_S, 2 * cc.RATE_WAIT_S]
    assert r["verified"] == ["structured_output"] and r["not_checked"] == ["tool_use", "workspace_read"]
    assert "wr-port" not in calls  # the tasks after a route stayed limited are not run
    assert r["by_capability"]["workspace_read"]["error"].startswith("not run: the route stayed rate-limited")
