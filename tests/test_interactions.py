"""Interaction requests (``baton-interaction/1``; Decisions 0169, 0170).

- Every pending decision is a request with an id that ``status`` and ``board`` give; ``interactions`` lists them
  and ``interaction`` returns one, valid against the published format.
- ``answer`` records a choice as ``decide`` would, stamped with ``request_id`` and ``via``; the owner's words are the
  note, or a fixed phrase naming a renderer other than conversation.
- A blocked step's questions are the fields of its ``retry`` choice; framing's ``select`` takes its parts.
- A request's id changes whenever what it asks changes; an answer to an old id is refused as stale.
- A person's step is a request built from its output schema, files and hints; answered with values and files, it
  is taken in as ``submit`` would. Gates show what was produced. The renderable subset, hints checked at load, and
  the answer file written by ``answer --template``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from baton import engine, interactions
from baton.data import path as data_path

from projectkit import FIT_INPUTS, GOOD_PROFILE, Cli
from test_conversation import QUESTIONS, fresh, frame_output, manual, status, _frame
from runkit import make_recipe, write_result
from test_tailoring_axes import WRITER, ctx, rated, signal, store  # noqa: F401 (fixtures)

pytestmark = pytest.mark.slow

SCHEMA = json.loads((data_path("formats") / "baton-interaction-1.schema.json").read_text(encoding="utf-8"))


def valid(req: dict) -> dict:
    errors = [e.message for e in Draft202012Validator(SCHEMA).iter_errors({k: v for k, v in req.items() if k != "ok"})]
    assert not errors, errors
    return req


def events(project: Path, run: str) -> list[dict]:
    lines = (project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _gate(cli: Cli, project: Path) -> str:
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", GOOD_PROFILE)
    out = manual(cli, project, run, "assess", {"verdict": "fits", "assessed_work": "Reviewing vendor contracts",
                                               "reasons": [{"row": "recurrence", "leans": "baton", "basis": "stated", "reason": "few"}],
                                               "next_step": "Author a recipe."})
    assert out["needs_owner"]
    return run


def test_published_format_is_a_valid_schema():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["title"] == interactions.FORMAT == "baton-interaction/1"


def test_a_gate_is_a_request_listed_read_and_answered(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)
    (pd,) = status(cli, run)["pending_decisions"]
    rid = pd["request_id"]
    assert rid.startswith("ir_")
    board = cli("board", expect=None).payload
    assert [p["request_id"] for r in board["runs"] for p in r["pending_decisions"]] == [rid]

    listed = cli("interactions", expect=4).payload
    assert [(r["id"], r["run"], r["ref"], r["kind"]) for r in listed["requests"]] == [(rid, run, "assess", "gate")]
    assert cli("interactions", "--run", run, expect=4).payload["requests"] == listed["requests"]

    req = valid(cli.run("interaction", rid))
    assert req["format"] == "baton-interaction/1" and req["id"] == rid and req["message"] == pd["prompt"]
    assert [(c["decision"], c["label"]) for c in req["choices"]] == [(o["decision"], o["label"]) for o in pd["options"]]
    assert req["needs_confirmation"] is True and req["hints"] == {} and req["extensions"] == {}

    out = cli.run("answer", rid, "--choice", "approve", "--note", "That verdict is right. Yes.")
    assert out["request_id"] == rid and out["via"] == "conversation" and out["outcome"] == "passed"
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["decision"] == "approve" and dec["data"]["note"] == "That verdict is right. Yes."
    assert dec["data"]["request_id"] == rid and dec["data"]["via"] == "conversation"

    again = cli.run("answer", rid, "--choice", "approve", "--note", "yes", expect=1)
    assert again["error"] == "interaction.stale"
    assert cli.run("interaction", rid, expect=1)["error"] == "interaction.stale"


def test_decide_still_works_and_is_not_stamped(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)
    cli.run("decide", run, "assess", "approve", "--note", "yes")
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert "request_id" not in dec["data"] and "via" not in dec["data"]


def test_conversation_needs_the_owners_words_and_another_renderer_may_record_a_fixed_phrase(tmp_path):
    cli, project = fresh(tmp_path)
    run = _gate(cli, project)
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    assert cli.run("answer", rid, "--choice", "approve", expect=1)["error"] == "answer.note_required"
    assert cli.run("answer", rid, "--choice", "maybe", "--note", "x", expect=1)["error"] == "answer.invalid"
    assert not [e for e in events(project, run) if e["type"] == "human_decision"]  # nothing recorded
    out = cli.run("answer", rid, "--choice", "reject", "--via", "local page")
    assert out["via"] == "local page"
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["note"] == "confirmed in local page" and dec["data"]["via"] == "local page"


def test_the_owners_own_answer_needs_no_directors_lease(tmp_path):
    """Decision 0171, item 7: an answer through a renderer other than conversation is the owner's, recorded under the
    run lock without taking or renewing the Director's lease; in conversation the lease still rules."""
    from projectkit import Cli as _Cli

    cli, project = fresh(tmp_path)
    run = _gate(cli, project)  # alice@host1 holds the run's lease
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    page = _Cli(project, cli.home, director="baton-ui@host1")
    assert page.run("answer", rid, "--choice", "approve", "--note", "Yes.", expect=3)["error"].startswith("lease")
    out = page.run("answer", rid, "--choice", "approve", "--via", "local_page")
    assert out["via"] == "local_page"
    evs = events(project, run)
    dec = [e for e in evs if e["type"] == "human_decision"][-1]
    assert dec["data"]["recorded_by"] == "owner" and dec["data"]["note"] == "confirmed in local_page"
    claims = [e["data"]["director_id"] for e in evs if e["type"] in ("lease_claimed", "lease_renewed", "lease_taken_over")]
    assert set(claims) == {"alice@host1"}


def test_a_blocked_steps_questions_are_the_fields_of_its_retry(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    (pd,) = status(cli, run)["pending_decisions"]
    req = valid(cli.run("interaction", pd["request_id"]))
    assert req["kind"] == "blocked" and req["title"] == interactions.TITLES["blocked"]
    retry, abandon = req["choices"]
    assert "answer" not in abandon
    spec = retry["answer"]
    assert spec["renderable"] and list(spec["schema"]["properties"]) == ["site", "permits", "hours"]
    assert spec["schema"]["required"] == ["site", "permits"]
    site = spec["schema"]["properties"]["site"]
    assert site["title"] == QUESTIONS[0]["ask"] and site["description"] == QUESTIONS[0]["why"]
    assert site["examples"] == ["One machine", "Several"]  # suggestions: the answer may differ
    assert spec["prefill"] == {"site": "One machine per site at first"}

    bad = tmp_path / "bad.yaml"
    bad.write_text("choice: retry\nvalues:\n  site: One each\n", encoding="utf-8")
    out = cli.run("answer", pd["request_id"], "--file", str(bad), "--note", "x", expect=1)
    assert out["error"] == "answer.invalid" and "permits" in out["message"]

    good = tmp_path / "answer.yaml"
    good.write_text("choice: retry\nvalues:\n  site: Two at the big site\n  permits: I do them myself\n"
                    "words:\n  site: \"Two at the big one, actually. Yes.\"\n", encoding="utf-8")
    out = cli.run("answer", pd["request_id"], "--file", str(good), "--note", "Yes, go ahead with those.")
    assert out["outcome"] == "retry"
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["kind"] == "answers" and dec["data"]["request_id"] == pd["request_id"]
    assert dec["data"]["answers"] == [
        {"id": "site", "answer": "Two at the big site", "owner_words": "Two at the big one, actually. Yes."},
        {"id": "permits", "answer": "I do them myself", "owner_words": "Yes, go ahead with those."},
    ]


def test_a_partial_answer_must_say_so(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"choice": "retry", "values": {"site": "One"}, "partial": True}), encoding="utf-8")
    cli.run("answer", rid, "--file", str(f), "--note", "Only that for now. Yes.")
    dec = [e for e in events(project, run) if e["type"] == "human_decision"][-1]
    assert dec["data"]["partial"] is True and [a["id"] for a in dec["data"]["answers"]] == ["site"]


def test_framing_select_takes_its_parts_from_the_answer(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    (pd,) = status(cli, fr)["pending_decisions"]
    req = valid(cli.run("interaction", pd["request_id"]))
    assert req["kind"] == "frame"
    sel = req["choices"][0]
    assert sel["decision"] == "select" and sel["next"]  # what choosing it triggers, as status gives it
    parts = sel["answer"]["schema"]["properties"]["items"]["items"]["oneOf"]
    assert [p["const"] for p in parts] == ["setup", "kiosk", "signage", "running"]
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"choice": "select", "values": {"items": ["setup", "nope"]}}), encoding="utf-8")
    assert cli.run("answer", pd["request_id"], "--file", str(f), "--note", "x", expect=1)["error"] == "answer.invalid"
    f.write_text(json.dumps({"choice": "select", "values": {"items": ["setup"]}}), encoding="utf-8")
    out = cli.run("answer", pd["request_id"], "--file", str(f), "--note", "Just the setup for now. Yes.")
    assert out["selected"] == ["setup"] and out["request_id"] == pd["request_id"]
    dec = next(e for e in events(project, fr) if e["type"] == "human_decision")
    assert dec["data"]["kind"] == "frame" and dec["data"]["request_id"] == pd["request_id"]


# -- ids change with what is asked (Decision 0170, item 10) ---------------------


def test_a_signal_joining_a_pending_rating_decision_changes_its_id(ctx):
    rated(ctx, discovery="low", assurance="medium")
    signal(ctx, "build", "assurance", "high", "the change reaches the tenant boundary")
    (first,) = [p for p in engine.pending_decisions(ctx) if p["kind"] == "rating_signal"]
    rid = interactions.request_id(ctx, first)
    assert rid == interactions.request_id(ctx, dict(first))  # stable while nothing changes
    p = engine.begin_attempt(ctx, "verify", "owner", WRITER)  # a failed attempt: the run stays active
    write_result(p, {}, status="failed", rating_signal={"axis": "assurance", "suggested": "high", "reason": "and it changes the audit log"})
    assert engine.submit(ctx, "verify").outcome == "escalated"
    (second,) = [p for p in engine.pending_decisions(ctx) if p["kind"] == "rating_signal"]
    assert second["ref"] == first["ref"] and interactions.request_id(ctx, second) != rid


def test_what_is_computed_elsewhere_does_not_change_the_id(ctx):
    rated(ctx, discovery="low", assurance="medium")
    signal(ctx, "build", "assurance", "high", "why")
    (p,) = [p for p in engine.pending_decisions(ctx) if p["kind"] == "rating_signal"]
    rid = interactions.request_id(ctx, p)
    annotated = {**p, "web_advice": {"x": 1}, "options": [{**o, "next": "something"} for o in p["options"]]}
    assert interactions.request_id(ctx, annotated) == rid
    changed = {**p, "prompt": p["prompt"] + " (reworded)"}
    assert interactions.request_id(ctx, changed) != rid


def test_a_step_blocked_again_is_a_new_request(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    old = status(cli, run)["pending_decisions"][0]["request_id"]
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"choice": "retry", "values": {"site": "One", "permits": "Me"}}), encoding="utf-8")
    cli.run("answer", old, "--file", str(f), "--note", "Yes.")
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    new = status(cli, run)["pending_decisions"][0]["request_id"]
    assert new != old
    out = cli.run("answer", old, "--file", str(f), "--note", "Yes.", expect=1)
    assert out["error"] == "interaction.stale" and new in out["message"]  # the open one is named


# -- Slice 2: a person's step, hints and the answer file -------------------------------


MATCH_SCHEMA = {
    "type": "object", "required": ["matches"], "additionalProperties": False,
    "properties": {
        "matches": {"type": "array", "title": "Receipt lines", "items": {
            "type": "object", "required": ["line", "item"], "additionalProperties": False,
            "properties": {"line": {"type": "string"}, "item": {"type": "string", "enum": ["i1", "i2"]}}}},
        "checked": {"type": "boolean", "title": "Checked against the photo", "default": True},
    },
}
HINTS = {"order": ["checked", "matches"], "fields": {"matches": {"widget": "table", "help": "One row per receipt line"}},
         "summary": ["matches"]}


def person_recipe(root: Path, *, hints=HINTS, schema=MATCH_SCHEMA) -> Path:
    r = make_recipe(root, [{
        "id": "match", "title": "Match the receipt to the items",
        "requires": {"capabilities": ["human_judgment"]},
        "output_schema": "schemas/match.json",
        "artifacts": [{"name": "photo", "required": True}],
        "interaction": {"hints": "hints/match.yaml"},
        "gates": [{"type": "human", "prompt": "Is the matching right?", "interaction": {"hints": "hints/match.yaml"}}],
    }], schemas={"match.json": schema}, run_inputs={"type": "object", "properties": {"title": {"type": "string"}}})
    (r / "hints").mkdir(exist_ok=True)
    (r / "hints" / "match.yaml").write_text(yaml.safe_dump(hints), encoding="utf-8")
    return r


def person_run(tmp_path: Path, **kw) -> tuple[Cli, Path, str]:
    cli, project = fresh(tmp_path, bare=True)
    cli.run("vendor", str(person_recipe(tmp_path / "toy", **kw)))
    run = cli.run("start", "toy", "--inputs", json.dumps({"title": "Receipts"}))["run_id"]
    cli.run("dispatch", run, "match", "--worker", "owner")
    return cli, project, run



def test_a_persons_step_is_a_request_with_its_schema_files_and_hints(tmp_path):
    cli, project, run = person_run(tmp_path)
    st = status(cli, run)
    assert st["pending_decisions"] == []  # nothing about the step changes: it is work being done, not a decision
    rid = st["running"][0]["request_id"]
    listed = cli("interactions", expect=4).payload["requests"]
    assert [(r["id"], r["kind"], r["ref"]) for r in listed] == [(rid, "person_step", "match")]
    req = valid(cli.run("interaction", rid))
    assert req["title"] == "Match the receipt to the items" and req["choices"] == []
    assert req["answer"]["schema"] == {"$schema": "https://json-schema.org/draft/2020-12/schema", **MATCH_SCHEMA}
    assert req["answer"]["renderable"] is True and req["answer"]["prefill"] == {"checked": True}
    assert req["files"] == [{"name": "photo", "required": True}]
    assert req["hints"] == HINTS
    item = cli.run("interaction", rid, "--item", "instructions")
    assert "Do the match step." in item["text"] and item["path"].endswith("INSTRUCTIONS.md")
    assert cli.run("interaction", rid, "--item", "../../etc", expect=1)["error"] == "interaction.unknown_item"


def test_a_persons_step_is_answered_with_values_and_files(tmp_path):
    cli, project, run = person_run(tmp_path)
    rid = status(cli, run)["running"][0]["request_id"]
    photo = tmp_path / "receipt.jpg"
    photo.write_bytes(b"\xff\xd8 not really a jpeg")
    f = tmp_path / "a.yaml"
    f.write_text(yaml.safe_dump({"values": {"matches": [{"line": "Widget A", "item": "i1"}]}}), encoding="utf-8")
    out = cli.run("answer", rid, "--file", str(f), "--note", "x", expect=1)
    assert out["error"] == "answer.invalid" and "photo" in out["message"]  # the required file
    f.write_text(yaml.safe_dump({"values": {"matches": [{"line": "Widget A", "item": "i9"}]}}), encoding="utf-8")
    assert cli.run("answer", rid, "--file", str(f), "--attach", f"photo={photo}", "--note", "x", expect=1)["error"] == "answer.invalid"
    f.write_text(yaml.safe_dump({"values": {"matches": [{"line": "Widget A", "item": "i1"}], "checked": True}}), encoding="utf-8")
    out = cli("answer", rid, "--file", str(f), "--attach", f"photo={photo}", "--via", "answer_file", expect=4).payload
    assert out["outcome"] == "needs_human" and out["request_id"] == rid and out["via"] == "answer_file"
    ev = events(project, run)
    sub = next(e for e in ev if e["type"] == "result_submitted")
    assert sub["data"]["request_id"] == rid and sub["data"]["via"] == "answer_file"
    res = json.loads(next(project.glob(f".baton/runs/{run}/**/result/result.json")).read_text(encoding="utf-8"))
    assert res["output"] == {"matches": [{"line": "Widget A", "item": "i1"}], "checked": True}
    assert res["artifacts"] == [{"name": "photo", "path": "artifacts/photo.jpg"}] and res["notes"] == "confirmed in answer_file"
    assert cli.run("answer", rid, "--file", str(f), "--attach", f"photo={photo}", "--note", "x", expect=1)["error"] == "interaction.stale"

    # The human gate that follows shows what was produced, with the gate's hints.
    (gate,) = status(cli, run)["pending_decisions"]
    greq = valid(cli.run("interaction", gate["request_id"]))
    assert greq["hints"] == HINTS
    ids = [c["id"] for c in greq["context"]]
    assert ids == ["output", "file:photo"]
    out_item = cli.run("interaction", gate["request_id"], "--item", "output")
    assert json.loads(out_item["text"])["matches"][0]["item"] == "i1"
    assert cli.run("interaction", gate["request_id"], "--item", "file:photo")["path"].endswith("photo.jpg")


def test_submit_still_works_for_a_persons_step(tmp_path):
    cli, project, run = person_run(tmp_path)
    pdir = next(project.glob(f".baton/runs/{run}/**/packet"))
    from projectkit import write_result as play

    play(pdir, {"matches": []})
    rdir = pdir.parent / "result"
    (rdir / "artifacts").mkdir(parents=True, exist_ok=True)
    (rdir / "artifacts" / "p.jpg").write_bytes(b"x")
    res = json.loads((rdir / "result.json").read_text(encoding="utf-8"))
    (rdir / "result.json").write_text(json.dumps({**res, "artifacts": [{"name": "photo", "path": "artifacts/p.jpg"}]}), encoding="utf-8")
    cli("submit", run, "match", expect=4)
    sub = next(e for e in events(project, run) if e["type"] == "result_submitted")
    assert "request_id" not in sub["data"]


def test_the_answer_template_holds_every_field_with_its_prefill_and_comments(tmp_path):
    cli, project, run = person_run(tmp_path)
    rid = status(cli, run)["running"][0]["request_id"]
    target = tmp_path / "answer.yaml"
    out = cli.run("answer", rid, "--template", "--out", str(target))
    assert out["template"] == str(target)
    text = target.read_text(encoding="utf-8")
    assert "# Answer for: Match the receipt to the items" in text
    assert text.index("checked: true") < text.index("matches:")  # the hints' order
    assert "# One row per receipt line" in text and "# photo (required): the path of the file" in text
    assert not [e for e in events(project, run) if e["type"] == "result_submitted"]  # nothing recorded
    assert cli.run("answer", rid, "--template", "--out", str(target), expect=2)["error"] == "answer.template_exists"
    doc = yaml.safe_load(text)
    photo = tmp_path / "p.png"
    photo.write_bytes(b"png")
    doc["values"]["matches"] = [{"line": "Widget A", "item": "i2"}]
    doc["artifacts"]["photo"] = str(photo)
    target.write_text(yaml.safe_dump(doc), encoding="utf-8")
    out = cli("answer", rid, "--file", str(target), "--note", "Widget A pays for item 2. Yes.", expect=4).payload
    assert out["outcome"] == "needs_human"


def test_the_blocked_template_prefills_best_guesses(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    rid = status(cli, run)["pending_decisions"][0]["request_id"]
    target = tmp_path / "t.yaml"
    cli.run("answer", rid, "--template", "--out", str(target))
    doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert doc["choice"] is None and doc["values"] == {"site": "One machine per site at first", "permits": None, "hours": None}
    assert "Suggestions (you may write something else): One machine; Several" in target.read_text(encoding="utf-8")


def test_a_schema_outside_the_subset_is_marked_not_renderable(tmp_path):
    odd = {"type": "object", "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}}
    cli, project, run = person_run(tmp_path, hints={}, schema=odd)
    rid = status(cli, run)["running"][0]["request_id"]
    assert cli.run("interaction", rid)["answer"]["renderable"] is False


@pytest.mark.parametrize("schema, ok", [
    ({"type": "object", "properties": {"a": {"type": "string", "enum": ["x"]}, "b": {"type": "integer", "minimum": 0}}}, True),
    ({"type": "object", "properties": {"d": {"type": "string", "format": "date"}, "t": {"type": "boolean"}}}, True),
    ({"type": "object", "properties": {"c": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}, "uniqueItems": True}}}, True),
    ({"type": "object", "properties": {"g": {"type": "object", "properties": {"n": {"type": "number"}}}}}, True),
    ({"type": "object", "properties": {"r": {"$ref": "#/defs/x"}}}, False),
    ({"type": "object", "properties": {"a": {"type": "string"}}, "if": {}, "then": {}}, False),
    ({"type": "object", "properties": {"m": {"type": ["string", "null"]}}}, False),
    ({"type": "object", "properties": {"t": {"type": "array", "items": {"type": "object", "properties": {"x": {"type": "array", "items": {"type": "string"}}}}}}}, False),
    ({"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": {"type": "string"}}, False),
])
def test_the_renderable_subset(schema, ok):
    assert interactions.renderable(schema) is ok, interactions.subset_problems(schema)


@pytest.mark.parametrize("hints, problem", [
    ({"order": ["nope"]}, "'nope' is not a field"),
    ({"fields": {"matches": {"widget": "carousel"}}}, "widget must be one of"),
    ({"fields": {"matches.item": {"label": "Item"}}, "colour": "red"}, "unknown hint 'colour'"),
    ({"groups": [{"title": "A"}]}, "groups[0] must be {title, fields}"),
])
def test_hints_are_checked_at_load(tmp_path, hints, problem):
    from baton.recipe import validate_recipe

    _, issues = validate_recipe(person_recipe(tmp_path / "r", hints=hints))
    bad = [i for i in issues if i.code == "interaction.bad_hints"]
    assert bad and any(problem in i.message for i in bad), issues


def test_hints_name_dotted_fields_and_need_an_output_schema(tmp_path):
    from baton.recipe import validate_recipe

    loaded, issues = validate_recipe(person_recipe(tmp_path / "r", hints={"fields": {"matches.item": {"label": "Item"}}}))
    assert loaded is not None and not [i for i in issues if i.severity == "error"]
    r = make_recipe(tmp_path / "n", [{"id": "a", "interaction": {"hints": "h.yaml"}}])
    (r / "h.yaml").write_text("{}", encoding="utf-8")
    _, issues = validate_recipe(r)
    assert [i.code for i in issues if i.severity == "error"] == ["interaction.needs_output_schema"]


# -- Slice 3: the Director renders requests ----------------------------------------------


def test_the_director_answers_a_table_row_by_row_in_conversation_over_mcp(tmp_path, monkeypatch):
    """The scenario of the Request: a person matches receipt lines to items, row by row with the Director."""
    import asyncio

    from mcp import Client

    from baton.mcp_server import build_server

    cli, project, run = person_run(tmp_path)
    monkeypatch.setenv("BATON_HOME", str(cli.home))
    photo = tmp_path / "receipt.png"
    photo.write_bytes(b"png")
    rows = [{"line": "Widget A", "item": "i1"}, {"line": "Widget B", "item": "i2"}]

    async def main():
        async with Client(build_server(project, cli.director)) as c:
            listed = (await c.call_tool("interactions", {"run": run})).structured_content["requests"]
            req = (await c.call_tool("interaction", {"request": listed[0]["id"]})).structured_content
            refused = await c.call_tool("answer", {"request": req["id"], "values": {"matches": rows, "checked": True},
                                                    "artifacts": {"photo": str(photo)}})  # no words
            done = await c.call_tool("answer", {
                "request": req["id"], "values": {"matches": rows, "checked": True},
                "words": {"matches": "A is the first item, B the second. Yes, both right."},
                "artifacts": {"photo": str(photo)},
                "note": "Yes, that's all of them, and here is the photo."})
            return req, refused, done

    req, refused, done = asyncio.run(main())
    assert req["kind"] == "person_step" and req["hints"]["fields"]["matches"]["widget"] == "table"
    assert refused.is_error and "answer.note_required" in refused.content[0].text
    out = done.structured_content
    assert out["via"] == "conversation" and out["outcome"] == "needs_human"
    res = json.loads(next(project.glob(f".baton/runs/{run}/**/result/result.json")).read_text(encoding="utf-8"))
    assert res["output"]["matches"] == rows
    assert res["notes"] == "Yes, that's all of them, and here is the photo.\nmatches: A is the first item, B the second. Yes, both right."


def test_the_director_skill_renders_requests():
    from conftest import ROOT

    text = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    part = text[text.index("## Answering requests"):text.index("## Two perspectives")]
    for phrase in ("`interactions`", "`interaction <id>`", "one row at a time", "confirm back the whole set",
                   "answer <id> --template", "--via answer_file", "always `--note", "`interaction.stale`", "renderable: false"):
        assert phrase in part, phrase
    assert "answer <id> --choice <decision>" in text and "--attach <name>=<path>" in text


@pytest.mark.parametrize("entry, kind", [
    ({"ref": "build", "step_path": "build", "attempt": 1, "kind": "escalation", "reason": "attempts_exhausted",
      "reasons": ["tests failed"], "questions": [], "options": [{"decision": "retry", "label": "Try again", "effect": "e"}]}, "escalation"),
    ({"ref": "build", "step_path": "build", "attempt": 1, "kind": "escalation", "reason": "wait_expired", "reasons": [],
      "questions": [], "options": [{"decision": "skip", "label": "Go on without it", "effect": "e"}]}, "wait_expired"),
    ({"ref": "checks/i1", "step_path": "checks/i1", "kind": "iteration_limit", "reasons": ["not converged"],
      "options": [{"decision": "retry", "label": "Give it another round", "effect": "e"}]}, "iteration_limit"),
    ({"ref": "baseline", "step_path": None, "kind": "baseline", "path": "docs/baseline.yaml", "prompt": "Review it",
      "options": [{"decision": "establish", "label": "That's an accurate picture", "effect": "e"}]}, "baseline"),
    ({"ref": "skip:7", "step_path": "build", "kind": "skip_notice", "prompt": "Reported: skipped",
      "options": [{"decision": "acknowledge", "label": "Noted", "effect": "e"}]}, "skip_notice"),
    ({"ref": "publish:build.doc", "step_path": "build", "kind": "publish_conflict", "artifact": "doc", "path": "docs/x.md",
      "reasons": ["a file is there"], "prompt": "Overwrite?", "options": [
          {"decision": "keep", "label": "Keep the existing file", "effect": "e"},
          {"decision": "alternate", "label": "Save the new one alongside", "effect": "e"}]}, "publish_conflict"),
    ({"ref": "drift:build.doc", "step_path": "build", "kind": "drift", "artifact": "doc", "path": "docs/x.md", "current_sha256": "ab",
      "prompt": "Edited", "options": [{"decision": "leave", "label": "Leave it as it is", "effect": "e"}]}, "drift"),
], ids=lambda v: v if isinstance(v, str) else None)
def test_every_kind_of_pending_decision_is_a_valid_request(ctx, entry, kind):
    req = valid(interactions.build(None, ctx, entry))
    assert req["kind"] == kind and req["title"] == interactions.TITLES[kind]
    assert [c["decision"] for c in req["choices"]] == [o["decision"] for o in entry["options"]]
    if kind == "publish_conflict":
        assert "answer" not in req["choices"][0] and list(req["choices"][1]["answer"]["schema"]["properties"]) == ["path"]
    changed = {**entry, "prompt": (entry.get("prompt") or "") + " now"}
    assert interactions.request_id(ctx, changed) != req["id"]
