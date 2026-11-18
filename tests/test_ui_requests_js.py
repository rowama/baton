"""The request page's generic renderer, its pure parts (ui/requests.js; §13.9; Decisions 0170, 0171).

Fields in the hints' order with their labels and help; groups where their first field falls; the control each field of
the subset gets; tables whose rows the prefill fixes; validation in plain words before Confirm; empty fields left out;
the confirmation's rows from the summary hint.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.slow, pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's script")]

SCHEMA = {
    "type": "object", "required": ["kind", "amount"], "additionalProperties": False,
    "properties": {
        "note": {"type": "string", "maxLength": 2000, "description": "Anything else"},
        "kind": {"type": "string", "oneOf": [{"const": "a", "title": "Apples"}, {"const": "b", "title": "Pears"}]},
        "amount": {"type": "integer", "minimum": 1, "maximum": 10},
        "when": {"type": "string", "format": "date"},
        "ok": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string", "enum": ["x", "y"]}, "uniqueItems": True},
        "names": {"type": "array", "items": {"type": "string"}},
        "address": {"type": "object", "properties": {"city": {"type": "string"}}},
        "matches": {"type": "array", "items": {"type": "object", "properties": {"line": {"type": "string"}, "item": {"type": "string", "enum": ["i1", "i2"]}}, "required": ["item"]}},
    },
}
HINTS = {"order": ["amount", "kind"], "groups": [{"title": "Where", "fields": ["when", "address"]}],
         "fields": {"kind": {"label": "Fruit", "help": "Pick one"}, "note": {"widget": "textarea"}}, "summary": ["kind", "amount"]}


def run(*calls) -> list:
    out = subprocess.run(["node", str(ROOT / "tests" / "ui_requests_check.mjs"), str(ROOT / "ui" / "requests.js")],
                         input=json.dumps(list(calls)), capture_output=True, text=True, timeout=20, check=True)
    return json.loads(out.stdout)


def test_fields_follow_the_hints_order_labels_and_help_and_each_gets_its_control():
    (fields,) = run(["fieldsOf", SCHEMA, HINTS, ""])
    assert [f["name"] for f in fields] == ["amount", "kind", "note", "when", "ok", "tags", "names", "address", "matches"]
    kind = fields[1]
    assert kind["label"] == "Fruit" and kind["help"] == "Pick one" and kind["required"] is True
    assert {f["name"]: f["kind"] for f in fields} == {
        "amount": "number", "kind": "choice", "note": "textarea", "when": "date", "ok": "boolean", "tags": "multi",
        "names": "list", "address": "group", "matches": "table"}
    assert next(f for f in fields if f["name"] == "note")["label"] == "Note"  # no title: the name, readable


def test_groups_are_placed_where_their_first_field_falls():
    (fields,) = run(["fieldsOf", SCHEMA, HINTS, ""])
    (parts,) = run(["layout", fields, HINTS])
    assert [(p["title"], [f["name"] for f in p["fields"]]) for p in parts] == [
        (None, ["amount", "kind", "note"]), ("Where", ["when", "address"]), (None, ["ok", "tags", "names", "matches"])]


def test_nested_fields_take_dotted_hints():
    hints = {"fields": {"matches.item": {"label": "Pays for"}}, "order": ["matches.item"]}
    (cols,) = run(["fieldsOf", SCHEMA["properties"]["matches"]["items"], hints, "matches."])
    assert [(c["name"], c["label"], c["path"]) for c in cols] == [("item", "Pays for", "matches.item"), ("line", "Line", "matches.line")]


def test_validation_speaks_plainly_and_runs_through_groups_and_tables():
    good = {"kind": "a", "amount": 3, "tags": ["x"], "matches": [{"line": "L1", "item": "i1"}]}
    bad = {"kind": "z", "amount": 11, "when": "next week", "tags": ["x", "x"], "matches": [{"line": "L1"}]}
    ok, problems, missing = run(["validate", SCHEMA, good, "", True, None, HINTS], ["validate", SCHEMA, bad, "", True, None, HINTS],
                                ["validate", SCHEMA, {}, "", True, None, HINTS])
    assert ok == []
    assert [(p["path"], p["message"]) for p in problems] == [
        ("amount", "Amount must be at most 10."), ("kind", "Fruit must be one of the choices."), ("when", "When must be a date."),
        ("tags", "Tags has the same entry twice."), ("matches[0].item", "Item in row 1 is needed.")]
    assert [p["message"] for p in missing] == ["Amount is needed.", "Fruit is needed."]
    (optional,) = run(["validate", {"type": "object", "properties": {"path": {"type": "string"}}}, {}, "", True, None, {}])
    assert optional == []  # a form of optional fields may be left empty


def test_empty_fields_are_not_given():
    (out,) = run(["clean", {"a": "", "b": None, "c": [], "d": {"e": ""}, "f": 0, "g": False, "h": [{"x": "", "y": 1}]}])
    assert out == {"f": 0, "g": False, "h": [{"y": 1}]}


def test_the_confirmation_shows_the_summary_fields_with_their_labels():
    (rows,) = run(["summaryRows", SCHEMA, HINTS, {"kind": "a", "amount": 2, "note": "x"}])
    assert [(r["label"], r["value"]) for r in rows] == [("Fruit", "a"), ("Amount", 2)]
    shown = run(["display", SCHEMA["properties"]["kind"], "a"], ["display", SCHEMA["properties"]["ok"], False],
                ["display", SCHEMA["properties"]["tags"], ["x", "y"]], ["display", SCHEMA["properties"]["note"], ""])
    assert shown == ["Apples", "No", "x, y", "—"]


def test_a_tables_rows_are_fixed_by_the_prefill_and_its_cells_name_the_row():
    fixed, open_ = run(["tableRows", SCHEMA["properties"]["matches"], [{"line": "Widget A"}, {"line": "Widget B"}]],
                       ["tableRows", SCHEMA["properties"]["matches"], None])
    assert fixed["fixed"] is True and fixed["rows"] == [{"line": "Widget A"}, {"line": "Widget B"}] and fixed["givenKeys"] == [["line"], ["line"]]
    assert open_ == {"fixed": False, "rows": [], "givenKeys": []}
