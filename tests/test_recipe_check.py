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
