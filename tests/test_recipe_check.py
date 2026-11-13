"""``baton recipe check`` (§5.3; Decision 0108): the ledger and instance-leak rules, as code."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baton import recipe_check
from baton.cli import app

runner = CliRunner()


def entry(eid="E1", **kw):
    return {"id": eid, "statement": "Every bed needs a soil check", "kind": "requirement", "scope": "class",
            "status": "confirmed", "basis": "owner", "owner_words": "check the soil first", **kw}


def package(tmp_path: Path, prompt="Check the soil, then plan the planting.", static="") -> Path:
    root = tmp_path / "pkg"
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "static").mkdir(exist_ok=True)
    (root / "prompts" / "plan.md").write_text(prompt, encoding="utf-8")
    (root / "static" / "notes.md").write_text(static, encoding="utf-8")
    return root


def write(tmp_path: Path, ledger) -> Path:
    f = tmp_path / "ledger.json"
    f.write_text(json.dumps(ledger), encoding="utf-8")
    return f


def test_a_clean_ledger_and_package_pass(tmp_path):
    ledger = write(tmp_path, {"ledger": [entry(), entry("E2", status="researched", owner_words=None),
                                         entry("E3", scope="instance", statement="The bed is 3 m by 1 m, in full sun")]})
    assert recipe_check.check(package(tmp_path), ledger) == []


def test_an_open_entry_is_a_problem(tmp_path):
    problems = recipe_check.check(package(tmp_path), write(tmp_path, [entry("E7", status="open")]))
    assert problems == ["ledger entry E7: is still open; resolve it, or have the owner exclude it, before generating"]


def test_a_confirmed_entry_needs_the_owners_words(tmp_path):
    for words in (None, "", "   "):
        e = entry("E4")
        e["owner_words"] = words
        assert recipe_check.check(package(tmp_path), write(tmp_path, [e])) == ["ledger entry E4: is confirmed but carries no `owner_words`"]
    e = entry("E5")
    del e["owner_words"]
    assert len(recipe_check.check(package(tmp_path), write(tmp_path, [e]))) == 1


def test_an_instance_fact_in_a_prompt_or_static_file_is_a_leak(tmp_path):
    fact = "The bed is 3 m by 1 m, in full sun"
    ledger = write(tmp_path, [entry("E9", scope="instance", statement=fact)])
    leaky = package(tmp_path, prompt="Remember: the  BED is 3 m by 1 m,\nin full sun. Plan for it.")
    assert recipe_check.check(leaky, ledger) == [
        "prompts/plan.md: holds the text of instance entry E9; a fact about this one job belongs in a run input, not in the recipe"
    ]
    (leaky / "prompts" / "plan.md").write_text("Plan from the run's inputs.", encoding="utf-8")
    (leaky / "static" / "notes.md").write_text(fact, encoding="utf-8")
    assert [p.split(":")[0] for p in recipe_check.check(leaky, ledger)] == ["static/notes.md"]


def test_a_class_fact_may_appear_and_a_short_instance_value_is_not_searched(tmp_path):
    ledger = write(tmp_path, [entry("E1", statement="Every bed needs a soil check"), entry("E2", scope="instance", statement="sunny", status="researched", owner_words=None)])
    pkg = package(tmp_path, prompt="Every bed needs a soil check. Note it is sunny.")
    assert recipe_check.check(pkg, ledger) == []


def test_malformed_input_is_an_error_not_a_pass(tmp_path):
    pkg = package(tmp_path)
    assert "is not valid JSON" in recipe_check.check(pkg, _raw(tmp_path, "{nope"))[0]
    assert "cannot be read" in recipe_check.check(pkg, tmp_path / "missing.json")[0]
    assert recipe_check.check(pkg, write(tmp_path, {"foo": 1}))[0].startswith("ledger: expected a list")
    bad = recipe_check.check(pkg, write(tmp_path, [{"id": "X", "statement": "s", "scope": "kind", "status": "maybe"}, "str"]))
    assert any("`scope` must be one of" in p for p in bad) and any("`status` must be one of" in p for p in bad)
    assert any("must be an object" in p for p in bad)
    assert recipe_check.check(tmp_path / "nothing", write(tmp_path, []))[0].endswith("is not a recipe folder")
    dup = recipe_check.check(pkg, write(tmp_path, [entry("E1"), entry("E1")]))
    assert dup == ["ledger entry E1: duplicate id"]


def _raw(tmp_path, text):
    f = tmp_path / "raw.json"
    f.write_text(text, encoding="utf-8")
    return f


def test_the_command_exits_zero_or_one_and_prints_one_line_per_problem(tmp_path):
    pkg = package(tmp_path)
    ok = runner.invoke(app, ["recipe", "check", str(pkg), "--ledger", str(write(tmp_path, [entry()]))])
    assert ok.exit_code == 0 and ok.output == ""
    bad = runner.invoke(app, ["recipe", "check", str(pkg), "--ledger", str(write(tmp_path, [entry("E7", status="open")]))])
    assert bad.exit_code == 1 and bad.output.startswith("ERROR ledger entry E7: is still open")
    js = runner.invoke(app, ["recipe", "check", str(pkg), "--ledger", str(write(tmp_path, [entry("E7", status="open")])), "--json"])
    assert json.loads(js.output)["ok"] is False and len(json.loads(js.output)["problems"]) == 1


def test_the_command_has_no_mcp_tool():
    """A gate helper, not a Director call (Decision 0108)."""
    pytest.importorskip("mcp")
    from baton import mcp_server

    names = {t for t in dir(mcp_server) if "recipe_check" in t}
    assert not names


# -- discovery records (Decision 0141) ----------------------------------------------------------


def decided(**kw):
    return {"id": "D1", "question": "Printed guide or app?", "target_status": "example", "timing": "before_design",
            "timing_reason": "Different deliverables", "status": "decided",
            "comparison": {"criteria": ["no software to maintain"], "uncertainty": "",
                           "options": [{"name": "A printed guide", "kind": "manual_procedure", "requires_of_development": "layout and a proof check",
                                        "tradeoffs": "no reminders", "sources": [{"title": "A gardening handbook", "read_on": "2026-11-13"}]}],
                           "recommendation": "A printed guide"},
            "decision": {"ledger_id": "E9"}, **kw}


def owner_choice(**kw):
    return entry("E9", **{"kind": "decision", "statement": "The plan is a printed guide", "owner_words": "A printed guide, yes", **kw})


def with_discovery(tmp_path, *records, ledger=None):
    return write(tmp_path, {"ledger": ledger if ledger is not None else [owner_choice()], "discovery": list(records)})


def test_a_decided_choice_with_the_owners_confirmed_decision_passes(tmp_path):
    assert recipe_check.check(package(tmp_path), with_discovery(tmp_path, decided()), require_discovery=True) == []


def test_discovery_cannot_be_dropped_when_required(tmp_path):
    pkg = package(tmp_path)
    for f in (write(tmp_path, [entry()]), write(tmp_path, {"ledger": [entry()]})):
        assert recipe_check.check(pkg, f, require_discovery=True)[0].startswith("discovery: the ledger file must be an object")
        assert recipe_check.check(pkg, f) == []  # an older builder's ledger is still valid
    assert "at least one record" in recipe_check.check(pkg, with_discovery(tmp_path, ledger=[entry()]), require_discovery=True)[0]


def test_a_not_needed_or_settled_record_needs_only_its_reason(tmp_path):
    rec = {"id": "D0", "question": "Any choice?", "target_status": "none", "timing": "not_needed", "timing_reason": "One usual way", "status": "closed"}
    assert recipe_check.check(package(tmp_path), with_discovery(tmp_path, rec, ledger=[entry()]), require_discovery=True) == []
    bad = recipe_check.check(package(tmp_path), with_discovery(tmp_path, {**rec, "timing_reason": " ", "target_status": "maybe"}, ledger=[entry()]))
    assert any("`timing_reason`" in p for p in bad) and any("`target_status`" in p for p in bad)


def test_a_recommendation_alone_is_not_the_owners_choice(tmp_path):
    pkg = package(tmp_path)
    for rec, ledger, text in (
        (decided(status="researched"), [owner_choice()], "is still `researched`"),
        (decided(), [owner_choice(status="researched", owner_words=None)], "must be a confirmed `decision`"),
        (decided(), [entry("E9", kind="requirement", owner_words="yes")], "must be a confirmed `decision`"),
        (decided(decision={"ledger_id": "E404"}), [owner_choice()], "names no ledger entry"),
        (decided(decision=None), [owner_choice()], "names no ledger entry"),
    ):
        problems = recipe_check.check(pkg, with_discovery(tmp_path, rec, ledger=ledger))
        assert any(text in p for p in problems), (text, problems)


def test_a_comparison_needs_options_dated_sources_or_stated_uncertainty_and_a_recommendation(tmp_path):
    pkg = package(tmp_path)
    ok = decided()
    no_source = decided()
    no_source["comparison"]["options"][0]["sources"] = []
    assert any("cites no source" in p for p in recipe_check.check(pkg, with_discovery(tmp_path, no_source)))
    no_source["comparison"]["uncertainty"] = "No current source could be reached"
    assert recipe_check.check(pkg, with_discovery(tmp_path, no_source)) == []
    undated = decided()
    undated["comparison"]["options"][0]["sources"] = [{"title": "A handbook"}]
    assert any("the date it was read" in p for p in recipe_check.check(pkg, with_discovery(tmp_path, undated)))
    bare = decided()
    bare["comparison"].update(options=[], recommendation="")
    problems = recipe_check.check(pkg, with_discovery(tmp_path, bare))
    assert any("no option" in p for p in problems) and any("no recommendation" in p for p in problems)
    assert recipe_check.check(pkg, with_discovery(tmp_path, ok)) == []


RECIPE = """id: x
version: 1
steps:
  - id: research_options
    requires: {{ capabilities: [structured_output, {cap}] }}
  - id: decide
    gates: [ {{ type: {gate} }} ]
    inputs: [ {{ name: findings, from: steps.research_options.output, required: {req} }} ]
  - id: build
    depends_on: [decide]
    inputs: [ {{ name: choice, from: steps.decide.output.choice, required: true }} ]
"""


def deferred(**kw):
    g = {"research_step": "research_options", "decision_step": "decide", "consumers": ["build"]}
    return {"id": "D2", "question": "Which tool does this job use?", "target_status": "none", "timing": "in_generated_recipe",
            "timing_reason": "One shape serves every tool", "status": "deferred", "generated": {**g, **kw}}


def recipe_package(tmp_path, cap="web_access", gate="human", req="true", extra=""):
    pkg = package(tmp_path)
    (pkg / "recipe.yaml").write_text(RECIPE.format(cap=cap, gate=gate, req=req) + extra, encoding="utf-8")
    return pkg


def test_a_deferred_choice_must_be_carried_by_research_decision_and_using_steps(tmp_path):
    f = with_discovery(tmp_path, deferred(), ledger=[entry()])
    assert recipe_check.check(recipe_package(tmp_path), f, require_discovery=True) == []
    for kw, text in (({"cap": "file_write"}, "must require `web_access`"), ({"gate": "schema"}, "needs a human gate"),
                     ({"req": "false"}, "must take the findings of `research_options`")):
        assert any(text in p for p in recipe_check.check(recipe_package(tmp_path, **kw), f)), text
    for kw, text in (({"consumers": []}, "no step is named"), ({"consumers": ["ghost"]}, "no consuming step `ghost`"),
                     ({"decision_step": "ghost"}, "no decision step `ghost`"), ({"research_step": "ghost"}, "no research step `ghost`")):
        g = with_discovery(tmp_path, deferred(**kw), ledger=[entry()])
        assert any(text in p for p in recipe_check.check(recipe_package(tmp_path), g)), text


def test_a_consumer_that_does_not_take_the_decision_never_gets_it(tmp_path):
    pkg = recipe_package(tmp_path, extra="  - id: other\n    depends_on: [decide]\n")
    f = with_discovery(tmp_path, deferred(consumers=["other"]), ledger=[entry()])
    assert any("step `other` must take the output of `decide`" in p for p in recipe_check.check(pkg, f))
    assert any("no `generated`" in p or "needs `generated`" in p for p in recipe_check.check(pkg, with_discovery(tmp_path, {**deferred(), "generated": None}, ledger=[entry()])))


def test_the_command_takes_require_discovery(tmp_path):
    pkg = package(tmp_path)
    f = write(tmp_path, [entry()])
    assert runner.invoke(app, ["recipe", "check", str(pkg), "--ledger", str(f)]).exit_code == 0
    r = runner.invoke(app, ["recipe", "check", str(pkg), "--ledger", str(f), "--require-discovery"])
    assert r.exit_code == 1 and "ERROR discovery:" in r.output
