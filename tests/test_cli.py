from __future__ import annotations

import json

from typer.testing import CliRunner

from baton.cli import app

from conftest import FIT_CHECK, SOFTWARE_FEATURE, step

runner = CliRunner()


def test_plan_ok():
    result = runner.invoke(app, ["plan", str(SOFTWARE_FEATURE)])
    assert result.exit_code == 0
    assert "Level: major" in result.output


def test_plan_json():
    result = runner.invoke(app, ["plan", str(FIT_CHECK), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] and payload["plan"]["recipe"] == "fit-check@1"


def test_plan_invalid_recipe_exit_1(make_recipe):
    root = make_recipe(lambda r, _: step(r, "triage")["requires"].update(model="x"))
    result = runner.invoke(app, ["plan", str(root), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert not payload["ok"]
    assert payload["issues"][0]["code"] == "neutrality.forbidden_key"


def test_usage_errors_exit_2():
    assert runner.invoke(app, ["plan"]).exit_code == 2
    assert runner.invoke(app, ["plan", str(SOFTWARE_FEATURE), "--level", "huge"]).exit_code == 2
