"""2026-11-builder-step-design Slice 1: tools ship worked examples, and `baton tools test` runs them (§5.9, §13.1; Decision 0162).

An example is `tools/<id>/examples/<name>/` with `input.json`, `inputs/<input>.<ext>`,
`expected.json` and `expected/<artifact>.<ext>`. The loader checks it and hashes it
with the recipe; `baton tools test` runs the tool on it as a dispatch would and
names the first difference. Running tools spawns processes, so those tests are `slow`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baton.cli import app
from baton.recipe import load_recipe, validate_recipe
from baton.tool_test import bytes_difference, first_difference

from conftest import ROOT

RECONCILE = ROOT / "examples" / "recipes" / "spreadsheet-reconcile"
TOOL_DEMO = ROOT / "tests" / "fixtures" / "recipes" / "tool-demo"
EXAMPLE = "tools/csv_diff/examples/price-change"


def _copy(tmp_path: Path, src: Path = RECONCILE) -> Path:
    dst = tmp_path / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def _codes(root: Path) -> list[tuple[str, str]]:
    _loaded, issues = validate_recipe(root)
    return [(i.code, i.where) for i in issues if i.severity == "error"]


def _tools_test(tmp_path: Path, package: Path, *args: str) -> tuple[int, dict]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    res = CliRunner(env={"BATON_HOME": str(home)}).invoke(app, ["tools", "test", str(package), *args, "--json"])
    return res.exit_code, json.loads(res.stdout)


# -- the loader ------------------------------------------------------------


@pytest.mark.not_slow("loads a recipe")
def test_the_shipped_tool_has_an_example_with_file_inputs_and_an_artifact():
    tool = load_recipe(RECONCILE).tools["csv_diff"]
    [ex] = tool.examples
    assert ex.name == "price-change" and ex.values == {"key": "id"}
    assert sorted(ex.files) == ["after", "before"] and sorted(ex.artifacts) == ["differences"]
    assert ex.expected["added"] == 1 and ex.workspace is None


@pytest.mark.not_slow("loads a recipe")
def test_examples_are_hashed_with_the_tool_and_the_recipe(tmp_path):
    root = _copy(tmp_path)
    before = load_recipe(root)
    (root / EXAMPLE / "expected.json").write_text('{"added": 2}', encoding="utf-8")
    after = load_recipe(root)
    assert after.sha256 != before.sha256 and after.tools["csv_diff"].sha256 != before.tools["csv_diff"].sha256


@pytest.mark.not_slow("loads a recipe")
def test_a_tool_without_examples_loads():
    assert load_recipe(TOOL_DEMO).tools["backtest"].examples == []


@pytest.mark.not_slow("loads a recipe")
@pytest.mark.parametrize("change,where", [
    (lambda ex: (ex / "expected.json").unlink(), f"{EXAMPLE}/expected.json"),
    (lambda ex: (ex / "expected.json").write_text("[1]", encoding="utf-8"), f"{EXAMPLE}/expected.json"),
    (lambda ex: (ex / "input.json").write_text("{not json", encoding="utf-8"), f"{EXAMPLE}/input.json"),
    (lambda ex: (ex / "input.json").write_text('{"key": "id", "before": "x"}', encoding="utf-8"), f"{EXAMPLE}/inputs/before.csv"),
    (lambda ex: (ex / "expected" / "differences.txt").write_text("x", encoding="utf-8"), f"{EXAMPLE}/expected/differences.txt"),
    (lambda ex: (ex / "notes.md").write_text("x", encoding="utf-8"), f"{EXAMPLE}/notes.md"),
    (lambda ex: (ex / "inputs" / "nested").mkdir(), f"{EXAMPLE}/inputs/nested"),
    (lambda ex: ex.rename(ex.parent / "Price Change"), "tools/csv_diff/examples/Price Change"),
    (lambda ex: (ex.parent / "stray.json").write_text("{}", encoding="utf-8"), "tools/csv_diff/examples/stray.json"),
])
def test_a_malformed_example_is_refused_where_it_is(tmp_path, change, where):
    root = _copy(tmp_path)
    change(root / EXAMPLE)
    assert ("tool.bad_example", where) in _codes(root)


# -- comparing -------------------------------------------------------------


def test_the_first_json_difference_is_named_by_its_path():
    assert first_difference({"a": 1, "b": [1, 2]}, {"a": 1, "b": [1, 2]}, "output") == ""
    assert first_difference({"a": 1}, {"a": 1.0}, "output") == ""
    assert first_difference({"a": {"b": [1, 2]}}, {"a": {"b": [1, 3]}}, "output") == "output.a.b[1]: expected 2, the tool gave 3"
    assert first_difference({"a": 1}, {"a": True}, "output") == "output.a: expected 1, the tool gave true"
    assert first_difference({"a": 1}, {}, "output") == "output.a: expected 1, the tool gave none"
    assert first_difference({}, {"z": "x"}, "output") == 'output.z: not expected, the tool gave "x"'
    assert first_difference([1], [1, 2], "output") == "output: expected 1 items, the tool gave 2"


def test_the_first_byte_difference_is_a_line_for_text():
    assert bytes_difference(b"a\nb\n", b"a\nb\n") == ""
    assert bytes_difference(b"a\nb\n", b"a\nc\n") == "line 2: expected 'b\\n', the tool wrote 'c\\n'"
    assert bytes_difference(b"a\r\n", b"a\n") == "line 1: expected 'a\\r\\n', the tool wrote 'a\\n'"
    assert bytes_difference(b"a\n", b"a\nb\n") == "expected 1 lines, the tool wrote 2"
    assert bytes_difference(b"\xff\x00", b"\xff\x01") == "differs from byte 1 (expected 2 bytes, the tool wrote 2)"


# -- baton tools test --------------------------------------------------------


@pytest.mark.slow
def test_the_shipped_tool_passes_its_example(tmp_path):
    code, out = _tools_test(tmp_path, RECONCILE, "--require-examples")
    assert code == 0 and out["ok"]
    assert out["tools"] == [{"tool": "csv_diff", "ok": True, "examples": [{"example": "price-change", "ok": True}]}]


@pytest.mark.slow
def test_a_different_artifact_or_output_fails_naming_the_tool_example_and_difference(tmp_path):
    root = _copy(tmp_path)
    csv = root / EXAMPLE / "expected" / "differences.csv"
    csv.write_bytes(csv.read_bytes().replace(b"1.10", b"1.20"))
    code, out = _tools_test(tmp_path, root)
    assert code == 1 and not out["ok"]
    [ex] = out["tools"][0]["examples"]
    assert ex["example"] == "price-change" and ex["difference"].startswith("artifact 'differences': line 4: expected")
    exp = root / EXAMPLE / "expected.json"
    exp.write_text(exp.read_text(encoding="utf-8").replace('"removed": 1', '"removed": 2'), encoding="utf-8")
    code, out = _tools_test(tmp_path, root)
    assert code == 1 and out["tools"][0]["examples"][0]["difference"] == "output.removed: expected 2, the tool gave 1"


@pytest.mark.slow
def test_a_tool_that_fails_or_leaves_an_unexpected_file_fails_the_example(tmp_path):
    root = _copy(tmp_path)
    (root / EXAMPLE / "input.json").write_text('{"key": "sku"}', encoding="utf-8")
    code, out = _tools_test(tmp_path, root)
    assert code == 1 and "has no column 'sku'" in out["tools"][0]["examples"][0]["difference"]
    (root / EXAMPLE / "input.json").write_text('{"key": "id"}', encoding="utf-8")
    shutil.rmtree(root / EXAMPLE / "expected")  # the tool still writes differences.csv, now undeclared
    code, out = _tools_test(tmp_path, root)
    assert code == 1 and "'differences.csv', which is not output.json or a declared artifact" in out["tools"][0]["examples"][0]["difference"]


@pytest.mark.slow
def test_a_tool_with_no_examples_fails_only_when_examples_are_required(tmp_path):
    code, out = _tools_test(tmp_path, TOOL_DEMO)
    assert code == 0 and out["tools"] == [{"tool": "backtest", "ok": True, "examples": []}]
    code, out = _tools_test(tmp_path, TOOL_DEMO, "--require-examples")
    assert code == 1 and "has no examples" in out["tools"][0]["problem"]


@pytest.mark.slow
def test_a_package_that_does_not_load_is_refused(tmp_path):
    root = _copy(tmp_path)
    (root / EXAMPLE / "expected.json").unlink()
    home = tmp_path / "home"
    home.mkdir()
    res = CliRunner(env={"BATON_HOME": str(home)}).invoke(app, ["tools", "test", str(root)])
    assert res.exit_code != 0 and "tool.bad_example" in res.output
