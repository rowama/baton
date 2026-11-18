"""2026-11-tool-steps Slice 4: the shipped spreadsheet-reconcile recipe (§5.7, §5.9; Decision 0160).

Its program compares two CSV tables on a key column with no model; a worker then
explains the differences and the owner accepts the report.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json

import pytest

from baton.project import catalog
from baton.recipe import load_recipe

from conftest import ROOT
from projectkit import Cli, git, make_git_project, make_home, packet_dir, write_result

RECIPE = ROOT / "examples" / "recipes" / "spreadsheet-reconcile"
BEFORE = "id,name,price\n1,apple,1.00\n2,pear,2.00\n3,plum,3.00\n"
AFTER = "id,name,price,stock\n1,apple,1.10\n3,plum,3.00\n4,fig,4.00\n"


def _program():
    spec = importlib.util.spec_from_file_location("csv_diff", RECIPE / "programs" / "csv_diff" / "csv_diff.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.mark.not_slow("loads a recipe")
def test_the_recipe_is_in_the_catalog_with_its_program():
    loaded = catalog()["spreadsheet-reconcile"]
    assert set(loaded.programs) == {"csv_diff"} and loaded.programs["csv_diff"].requirements == []
    assert load_recipe(RECIPE).recipe.steps[0].program == "csv_diff"


@pytest.mark.not_slow("runs the program's functions in process")
def test_the_comparison(tmp_path):
    m = _program()
    (tmp_path / "b.csv").write_text(BEFORE, encoding="utf-8")
    (tmp_path / "a.csv").write_text(AFTER, encoding="utf-8")
    out, diffs = m.compare(m.read(str(tmp_path / "b.csv"), "id", "earlier"), m.read(str(tmp_path / "a.csv"), "id", "later"), "id")
    assert out == {"key": "id", "rows_before": 3, "rows_after": 3, "added": 1, "removed": 1, "changed": 1, "unchanged": 1,
                   "columns_added": ["stock"], "columns_removed": [], "changed_by_column": {"price": 1}}
    assert diffs == [["added", "4", "", "", ""], ["removed", "2", "", "", ""], ["changed", "1", "price", "1.00", "1.10"]]


@pytest.mark.not_slow("runs the program's functions in process")
@pytest.mark.parametrize("text,why", [
    ("name,price\napple,1\n", "has no column 'id'"),
    ("id,name\n1,a\n1,b\n", "'id' '1' twice"),
    ("id,name\n,a\n", "empty 'id'"),
])
def test_a_table_the_key_cannot_identify_is_refused_plainly(tmp_path, text, why):
    m = _program()
    (tmp_path / "t.csv").write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        m.read(str(tmp_path / "t.csv"), "id", "earlier")
    assert why in str(e.value)


@pytest.mark.slow
def test_a_reconciliation_end_to_end(tmp_path):
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project), "--bare")
    needs = cli("vendor", "spreadsheet-reconcile", "--note", "Yes, compare our price lists.", expect=4).payload
    assert [f["program"] for f in needs["flags"]] == ["csv_diff"] and needs["flags"][0]["touches"].startswith("does not open your project's files")
    cli.run("vendor", "spreadsheet-reconcile", "--approved", "--note", "Yes, the comparison program may run.")
    (project / "prices").mkdir()
    (project / "prices" / "march.csv").write_text(BEFORE, encoding="utf-8")
    (project / "prices" / "april.csv").write_text(AFTER, encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "price lists")
    cli.run("attest", "prices/march.csv", "--note", "March's list.")
    cli.run("attest", "prices/april.csv", "--note", "April's list.")
    run = cli.run("start", "spreadsheet-reconcile", "--inputs", json.dumps({"title": "Prices", "key": "id"}),
                  "--bind", "before=prices/march.csv", "--bind", "after=prices/april.csv", "--note", "Compare March with April.")["run_id"]

    out = cli("dispatch", run, "compare", "--worker", "program:csv_diff", "--wait", expect=None).payload
    assert out["outcome"] == "passed", out
    rdir = project / ".baton" / "runs" / run / "steps" / "compare" / "attempt-1" / "result"
    result = json.loads((rdir / "result.json").read_text(encoding="utf-8"))
    assert result["output"]["added"] == 1 and result["output"]["changed"] == 1 and result["output"]["columns_added"] == ["stock"]
    rows = list(csv.reader(io.StringIO((rdir / "artifacts" / "differences.csv").read_text(encoding="utf-8"))))
    assert rows[0] == ["change", "key", "column", "before", "after"] and ["changed", "1", "price", "1.00", "1.10"] in rows

    cli.run("dispatch", run, "explain", "--worker", "owner")
    pdir = packet_dir(project, run, "explain", 1)
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    assert {i["name"] for i in manifest["inputs"]} == {"counts", "differences"}
    write_result(pdir, {"summary": "One price rose, a pear was dropped and figs were added.", "highlights": ["id 1: apple price 1.00 to 1.10"]},
                 artifacts=[{"name": "report", "path": "artifacts/report.md"}])
    (pdir.parent / "result" / "artifacts").mkdir(parents=True, exist_ok=True)
    (pdir.parent / "result" / "artifacts" / "report.md").write_text("# What changed\n", encoding="utf-8")
    assert cli("submit", run, "explain", expect=4).payload  # the owner accepts the report


@pytest.mark.slow
def test_choosing_its_part_in_framing_approves_its_program_after_describing_it(tmp_path):
    from baton.engine import Api

    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project))
    (project / "prices").mkdir()
    (project / "prices" / "march.csv").write_text(BEFORE, encoding="utf-8")
    (project / "prices" / "april.csv").write_text(AFTER, encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "start")
    cli.run("attest", "prices/march.csv", "--note", "March's list.")
    cli.run("attest", "prices/april.csv", "--note", "April's list.")
    fr = cli.run("frame", "--note", "I want to know what changed in our price list.")["framing"]
    d = cli.run("dispatch", fr, "frame", "--worker", "owner")
    write_result(packet_dir(project, fr, "frame", d["attempt"]), {
        "goal": "Know what changed in the price list.",
        "parts": [{"id": "compare", "label": "Compare the two price lists", "description": "March against April.", "kind": "project",
                   "proposal": {"recipe": "spreadsheet-reconcile", "inputs": {"title": "Prices", "key": "id"}},
                   "bind": {"before": ["prices/march.csv"], "after": ["prices/april.csv"]},
                   "reasons": ["Two versions of one table"]}],
        "assumptions": [],
    })
    sub = cli("submit", fr, "frame", expect=None).payload
    assert sub["outcome"] == "needs_human", sub.get("reasons")
    (pd,) = cli("status", fr, expect=None).payload["pending_decisions"]
    nxt = {o["decision"]: o for o in pd["options"]}["select"]["next"][0]["next"]
    assert "it brings a program that runs on this computer (csv_diff): Compares two CSV tables" in nxt
    assert "does not use the internet" in nxt

    sel = cli.run("decide", fr, "frame", "select", "--items", "compare", "--note", "Yes, compare them; the program may run.")
    assert [r["recipe"] for r in sel["runs"]] == ["spreadsheet-reconcile@1"]
    lock = json.loads((project / ".baton" / "baton.lock").read_text(encoding="utf-8"))
    assert set(lock["recipes"]["spreadsheet-reconcile@1"]["programs"]) == {"csv_diff"}
    api = Api.open(project, director_id="alice@host1", home=cli.home)
    (dec,) = [e.data for e in api.project.store.project_log().events()
              if e.type == "human_decision" and e.data.get("kind") == "vendor" and e.data.get("recipe") == "spreadsheet-reconcile@1"]
    assert dec["via"] == fr and dec["note"] == "Yes, compare them; the program may run." and dec["flags"][0]["program"] == "csv_diff"
