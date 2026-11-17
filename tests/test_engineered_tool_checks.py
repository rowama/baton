"""2026-11-builder-engineered-tools Slice 1: the checks an engineered tool must pass (§5.9, §13.1; Decisions 0155, 0164).

An engineered tool carries `contract.json`; its examples carry `about.json`
(where each came from). `baton tools test` gains `--tool`, `--repeat` and
`--allow-unbuilt`; `baton tools examples` checks there are enough examples and
that the owner's files were copied exactly; the tool runner ends anything a
tool leaves running; `baton recipe check` enforces the budget's mechanical rules.
Running tools spawns processes, so those tests are `slow`.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from baton.cli import app
from baton.example_check import bound_documents, check_examples
from baton.recipe import load_recipe, validate_recipe
from baton.recipe_check import TOOL_SIZE_CAP, budget_problems
from baton.tools import file_sha256

from conftest import ROOT

RECONCILE = ROOT / "examples" / "recipes" / "spreadsheet-reconcile"
TOOL = "tools/csv_diff"
FIRST = f"{TOOL}/examples/price-change"

CONTRACT = {
    "kind": "engineered",
    "does": "Compares two CSV tables on a key column and lists every difference.",
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"},
    "reach": {"workspace": "none", "network": False, "secrets": []},
    "packages": [],
    "budget_reason": "One command, two files in, one report out; nothing kept running.",
}


def engineered(tmp_path: Path, examples: int = 3, awkward: bool = True, about: dict | None = None) -> Path:
    """The reconcile recipe with csv_diff made an engineered tool, with ``examples`` copies of its example."""
    root = tmp_path / "pkg"
    shutil.copytree(RECONCILE, root, ignore=shutil.ignore_patterns("__pycache__"))
    (root / TOOL / "contract.json").write_text(json.dumps(CONTRACT), encoding="utf-8")
    src = root / FIRST
    names = ["price-change", "second", "third", "fourth"][:examples]
    for name in names[1:]:
        shutil.copytree(src, root / TOOL / "examples" / name)
    if examples == 0:
        shutil.rmtree(root / TOOL / "examples")
    for i, name in enumerate(names):
        data = about if about is not None else {"source": "drafted", "awkward": awkward and i == 0}
        (root / TOOL / "examples" / name / "about.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def _errors(root: Path) -> list[tuple[str, str]]:
    _loaded, issues = validate_recipe(root)
    return [(i.code, i.where) for i in issues if i.severity == "error"]


def _cli(tmp_path: Path, *args: str, env: dict | None = None) -> tuple[int, dict]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    res = CliRunner(env={"BATON_HOME": str(home), **(env or {})}).invoke(app, [*args, "--json"])
    return res.exit_code, json.loads(res.stdout)


# -- the contract and about.json ---------------------------------------------


@pytest.mark.not_slow("loads a recipe")
def test_an_engineered_tool_loads_with_its_contract_and_each_examples_origin(tmp_path):
    loaded = load_recipe(engineered(tmp_path))
    tool = loaded.tools["csv_diff"]
    assert tool.engineered and tool.built and tool.contract["kind"] == "engineered"
    assert [e.about["source"] for e in tool.examples] == ["drafted"] * 3
    assert not load_recipe(RECONCILE).tools["csv_diff"].engineered


@pytest.mark.not_slow("loads a recipe")
@pytest.mark.parametrize("change, code", [
    (lambda c: c.pop("budget_reason"), "tool.bad_contract"),
    (lambda c: c.update(kind="simple"), "tool.bad_contract"),
    (lambda c: c.update(packages=[{"name": "pandas"}]), "tool.bad_contract"),
    (lambda c: c.update(extra=1), "tool.bad_contract"),
])
def test_a_malformed_contract_is_refused(tmp_path, change, code):
    root = engineered(tmp_path)
    c = dict(CONTRACT)
    change(c)
    (root / TOOL / "contract.json").write_text(json.dumps(c), encoding="utf-8")
    assert any(k == code and w.startswith(f"{TOOL}/contract.json") for k, w in _errors(root))


@pytest.mark.not_slow("loads a recipe")
@pytest.mark.parametrize("about", [
    {"source": "someone"},
    {"source": "owner", "awkward": "yes"},
    {"source": "owner", "from": {"input.json": "examples/x.json"}},
    {"source": "owner", "from": {"inputs/missing.csv": "examples/x.csv"}},
    {"source": "owner", "colour": "red"},
])
def test_a_malformed_about_json_is_refused_where_it_is(tmp_path, about):
    root = engineered(tmp_path, about=about)
    assert (("tool.bad_example", f"{FIRST}/about.json")) in _errors(root)


@pytest.mark.not_slow("loads a recipe")
def test_an_engineered_tool_not_built_yet_loads_with_a_warning_and_cannot_be_vendored(tmp_path):
    root = engineered(tmp_path)
    (root / TOOL / "csv_diff.py").unlink()
    loaded, issues = validate_recipe(root)
    assert loaded is not None and not loaded.tools["csv_diff"].built
    assert [(i.code, i.severity) for i in issues if i.code == "tool.unbuilt"] == [("tool.unbuilt", "warning")]
    simple = tmp_path / "simple"
    shutil.copytree(RECONCILE, simple, ignore=shutil.ignore_patterns("__pycache__"))
    (simple / TOOL / "csv_diff.py").unlink()
    assert ("file.missing", "tools/csv_diff/tool.yaml:entry[1]") in _errors(simple)  # a simple tool is never unbuilt

    from baton.engine import EngineError
    from baton.project import vendor

    with pytest.raises(EngineError) as e:
        vendor(SimpleNamespace(recipes_dir=tmp_path / "r", lock=lambda: {}), root)
    assert e.value.code == "vendor.tool_unbuilt"


# -- baton tools examples -----------------------------------------------------


def _bound(root: Path, *copies: tuple[str, str]) -> dict[str, str]:
    return {src: file_sha256(root / FIRST / rel) for rel, src in copies}


@pytest.mark.not_slow("loads a recipe")
def test_three_drafted_examples_with_an_awkward_one_pass_and_are_listed_for_the_owner(tmp_path):
    [rep] = check_examples(load_recipe(engineered(tmp_path)).tools, None)
    assert rep.ok and rep.examples == 3 and rep.drafted == ["price-change", "second", "third"]


@pytest.mark.not_slow("loads a recipe")
def test_too_few_examples_or_none_awkward_fails(tmp_path):
    [rep] = check_examples(load_recipe(engineered(tmp_path / "a", examples=2)).tools, None)
    assert not rep.ok and "2 examples; at least 3 are needed" in rep.problems[0]
    [rep] = check_examples(load_recipe(engineered(tmp_path / "b", awkward=False)).tools, None)
    assert rep.problems == ['no example is marked awkward ("awkward": true in about.json)']


@pytest.mark.not_slow("loads a recipe")
def test_simple_tools_are_not_checked_unless_named(tmp_path):
    tools = load_recipe(RECONCILE).tools
    assert check_examples(tools, None) == []
    [rep] = check_examples(tools, None, only="csv_diff")
    assert "has no contract.json" in rep.problems[0]


@pytest.mark.not_slow("loads a recipe")
def test_the_owners_files_must_be_exact_copies_of_the_bound_documents(tmp_path):
    copies = {"inputs/before.csv": "examples/csv_diff/march/before.csv", "inputs/after.csv": "examples/csv_diff/march/after.csv",
              "expected/differences.csv": "examples/csv_diff/march/differences.csv"}
    root = engineered(tmp_path, about={"source": "owner", "awkward": True, "from": copies})
    tools = load_recipe(root).tools
    bound = _bound(root, *copies.items())
    [rep] = check_examples(tools, bound)
    assert rep.ok and rep.drafted == [] and rep.stated == ["price-change", "second", "third"]  # input.json and expected.json from words
    [rep] = check_examples(tools, None)
    assert "cannot prove expected/differences.csv is the owner's file" in rep.problems[0]
    del bound["examples/csv_diff/march/after.csv"]
    [rep] = check_examples(tools, bound)
    assert "inputs/after.csv names examples/csv_diff/march/after.csv, which is not a document bound to 'examples'" in rep.problems[0]
    bound = _bound(root, *copies.items())
    csv = root / TOOL / "examples" / "second" / "inputs" / "after.csv"
    csv.write_bytes(csv.read_bytes() + b"\n")
    [rep] = check_examples(load_recipe(root).tools, bound)
    assert rep.problems == ["example 'second': inputs/after.csv differs from the bound document "
                            "examples/csv_diff/march/after.csv; the owner's files are copied byte for byte"]


@pytest.mark.not_slow("loads a recipe")
def test_an_owners_file_not_listed_as_copied_fails(tmp_path):
    root = engineered(tmp_path, about={"source": "owner", "awkward": True, "from": {}})
    [rep] = check_examples(load_recipe(root).tools, {})
    assert any("inputs/before.csv is not listed in about.json `from`" in p for p in rep.problems)


@pytest.mark.not_slow("reads events")
def test_the_binding_is_the_runs_latest_for_the_role():
    ev = lambda role, docs: SimpleNamespace(type="project_input_bound", data={"role": role, "documents": docs})  # noqa: E731
    events = [ev("examples", [{"path": "a.csv", "sha256": "1"}]), ev("guide", [{"path": "g.md", "sha256": "2"}]),
              ev("examples", [{"path": "b\\c.csv", "sha256": "3"}])]
    assert bound_documents(events) == {"b/c.csv": "3"}
    assert bound_documents(events[1:2]) is None


@pytest.mark.not_slow("runs the CLI on a recipe")
def test_the_examples_command_reports_and_exits_by_the_result(tmp_path):
    code, out = _cli(tmp_path, "tools", "examples", str(engineered(tmp_path)))
    assert code == 0 and out["ok"] and out["tools"][0]["drafted"] == ["price-change", "second", "third"]
    code, out = _cli(tmp_path, "tools", "examples", str(engineered(tmp_path / "few", examples=1)))
    assert code == 1 and not out["ok"]
    code, out = _cli(tmp_path, "tools", "examples", str(RECONCILE), "--tool", "nope")
    assert code != 0 and out["error"] == "tools.unknown_tool"


# -- baton tools test --tool --repeat --allow-unbuilt -------------------------


@pytest.mark.slow
def test_an_unbuilt_tool_fails_unless_allowed_and_is_then_listed(tmp_path):
    root = engineered(tmp_path)
    (root / TOOL / "csv_diff.py").unlink()
    code, out = _cli(tmp_path, "tools", "test", str(root))
    assert code == 1 and "is not built yet" in out["tools"][0]["problem"]
    code, out = _cli(tmp_path, "tools", "test", str(root), "--allow-unbuilt")
    assert code == 0 and out["tools"] == [{"tool": "csv_diff", "ok": True, "examples": [], "unbuilt": True}]


@pytest.mark.slow
def test_one_tool_is_selected_and_each_example_runs_the_repeated_number_of_times(tmp_path):
    root = engineered(tmp_path)
    code, out = _cli(tmp_path, "tools", "test", str(root), "--tool", "csv_diff", "--repeat", "2")
    assert code == 0 and out["repeat"] == 2 and [e["example"] for e in out["tools"][0]["examples"]] == ["price-change", "second", "third"]
    code, out = _cli(tmp_path, "tools", "test", str(root), "--tool", "nope")
    assert code != 0 and out["error"] == "tools.unknown_tool"


FLAKY = '''
import json, sys
from pathlib import Path
count = Path(__file__).with_name("count")
n = int(count.read_text()) if count.exists() else 0
count.write_text(str(n + 1))
(Path(sys.argv[2]) / "output.json").write_text(json.dumps({"n": 1 if n % 2 == 0 else 2}))
'''


@pytest.mark.slow
def test_a_tool_that_gives_a_different_result_on_the_second_run_fails_naming_the_run(tmp_path):
    root = engineered(tmp_path, examples=1)
    (root / TOOL / "csv_diff.py").write_text(FLAKY, encoding="utf-8")
    ex = root / FIRST
    shutil.rmtree(ex / "expected")
    (ex / "expected.json").write_text('{"n": 1}', encoding="utf-8")
    code, out = _cli(tmp_path, "tools", "test", str(root))
    assert code == 0
    (root / TOOL / "count").unlink()
    code, out = _cli(tmp_path, "tools", "test", str(root), "--repeat", "2")
    assert code == 1
    assert out["tools"][0]["examples"][0]["difference"] == "run 2 of 2 gave a different result: output.n: expected 1, the tool gave 2"


# -- the tool runner ends what a tool leaves running --------------------------

LINGER = '''
import json, subprocess, sys
from pathlib import Path
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
(Path(sys.argv[2]) / "output.json").write_text(json.dumps({"n": 1}))
'''


@pytest.mark.slow
@pytest.mark.skipif(os.name != "posix", reason="the POSIX process group; Windows uses a job object (Windows CI)")
def test_a_tool_that_leaves_a_process_running_fails_and_the_process_is_ended(tmp_path):
    root = engineered(tmp_path, examples=1)
    (root / TOOL / "csv_diff.py").write_text(LINGER, encoding="utf-8")
    ex = root / FIRST
    shutil.rmtree(ex / "expected")
    (ex / "expected.json").write_text('{"n": 1}', encoding="utf-8")
    code, out = _cli(tmp_path, "tools", "test", str(root))
    diff = out["tools"][0]["examples"][0]["difference"]
    assert code == 1 and diff.startswith("the tool left a process running after it finished (python")
    assert "it was stopped" in diff


# -- baton recipe check: the budget -------------------------------------------


@pytest.mark.not_slow("reads a package")
def test_a_tool_within_the_budget_has_no_problem_and_simple_tools_are_not_checked(tmp_path):
    assert budget_problems(engineered(tmp_path)) == []
    assert budget_problems(RECONCILE) == []


@pytest.mark.not_slow("reads a package")
def test_reach_must_be_as_the_contract_declares(tmp_path):
    root = engineered(tmp_path)
    c = dict(CONTRACT, reach={"workspace": "read", "network": False, "secrets": []})
    (root / TOOL / "contract.json").write_text(json.dumps(c), encoding="utf-8")
    assert budget_problems(root) == ["tools/csv_diff: tool.yaml reach.workspace is 'none', but the contract declares 'read'"]


@pytest.mark.not_slow("reads a package")
def test_a_named_package_must_be_pinned_in_the_lock(tmp_path):
    root = engineered(tmp_path)
    c = dict(CONTRACT, packages=[{"name": "python_dateutil", "why": "parses the export's dates"}])
    (root / TOOL / "contract.json").write_text(json.dumps(c), encoding="utf-8")
    assert budget_problems(root) == ["tools/csv_diff: the contract names package 'python_dateutil', which is not pinned in requirements.lock"]
    (root / TOOL / "requirements.lock").write_text("python-dateutil==2.9.0 --hash=sha256:" + "0" * 64 + "\n", encoding="utf-8")
    assert budget_problems(root) == []


@pytest.mark.not_slow("reads a package")
def test_a_tool_over_the_size_cap_needs_a_reason_and_its_examples_and_tests_do_not_count(tmp_path):
    root = engineered(tmp_path)
    (root / TOOL / "helpers.py").write_text("x = 1\n" * TOOL_SIZE_CAP, encoding="utf-8")
    (root / TOOL / "tests").mkdir()
    (root / TOOL / "tests" / "test_it.py").write_text("y = 2\n" * 5000, encoding="utf-8")
    [problem] = budget_problems(root)
    assert problem.startswith(f"tools/csv_diff: {TOOL_SIZE_CAP + 89} lines of code, over the {TOOL_SIZE_CAP}-line cap")
    c = dict(CONTRACT, size_reason="The parser for the bank's export format is long but it is one job.")
    (root / TOOL / "contract.json").write_text(json.dumps(c), encoding="utf-8")
    assert budget_problems(root) == []


@pytest.mark.not_slow("runs the CLI on a package")
def test_recipe_check_reports_the_budget(tmp_path):
    root = engineered(tmp_path)
    (root / TOOL / "helpers.py").write_text("x = 1\n" * (TOOL_SIZE_CAP + 1), encoding="utf-8")
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"ledger": []}), encoding="utf-8")
    res = CliRunner().invoke(app, ["recipe", "check", str(root), "--ledger", str(ledger)])
    assert res.exit_code != 0 and "over the 600-line cap" in res.output
