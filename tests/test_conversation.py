"""Phase 17: the conversation layer (§13.8) and framing new work (§11.6).

- Structured ``questions_for_human`` (bare strings still work), confirmed answers through
  ``decide … retry --answers`` and exactly those answers in the next packet.
- Every pending decision lists options with plain-language labels.
- ``init`` vendors the starter recipes; framing proposes from vendored and shipped recipes,
  starts runs for the selected parts (vendoring shipped recipes on selection) and reports gaps.
- The conversational and operator communication defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton import labels
from baton.project import STARTER_RECIPES, catalog

from conftest import FIT_CHECK, ROOT
from projectkit import FIT_INPUTS, GOOD_PROFILE, Cli, git, make_git_project, make_home, packet_dir, write_result

WORDS = "I want to start a pure-water vending business: a few self-serve machines around town."

QUESTIONS = [
    {"id": "site", "ask": "Will each site be one machine, or several?", "why": "Sets how much equipment planning is needed",
     "best_guess": "One machine per site at first", "options": [{"id": "one", "label": "One machine"}, {"id": "several", "label": "Several"}]},
    {"id": "permits", "ask": "Will you handle the permits yourself?", "why": "Decides who is involved in opening a site"},
    {"id": "hours", "ask": "Should machines run around the clock?", "why": "Affects how often someone visits", "priority": "helpful"},
]
ASSUMPTIONS = [{"field": "occurrence.frequency", "value": "a few site openings a year", "basis": "you said a few machines around town"}]


def fresh(tmp_path: Path, *, bare: bool = False) -> tuple[Cli, Path]:
    project = make_git_project(tmp_path / "proj")
    home = make_home(tmp_path / "home")
    cli = Cli(project, home)
    cli.run("init", str(project), *(["--bare"] if bare else []))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return cli, project


def status(cli: Cli, run: str) -> dict:
    return cli("status", run, expect=None).payload


def manual(cli: Cli, project: Path, run: str, step: str, output, **extra):
    d = cli.run("dispatch", run, step, "--worker", "owner")
    write_result(packet_dir(project, run, step, d["attempt"]), output, **extra)
    return cli("submit", run, step, expect=None).payload


# -- init: the starter kit ----------------------------------------------------


@pytest.mark.slow
def test_init_vendors_the_starter_recipes(tmp_path):
    cli, project = fresh(tmp_path)
    assert STARTER_RECIPES == ("fit-check",)
    ref = f"fit-check@{catalog()['fit-check'].recipe.version}"
    assert (project / ".baton" / "recipes" / ref / "recipe.yaml").is_file()
    assert ref in json.dumps(cli.run("recipes"))
    assert cli.run("check")["ok"]
    again = cli.run("init", str(project))  # idempotent: nothing vendored twice
    assert again["vendored"] == []


def test_init_bare_vendors_nothing(tmp_path):
    cli, project = fresh(tmp_path, bare=True)
    assert not any((project / ".baton" / "recipes").iterdir())


def test_examples_ship_in_the_package():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"examples" = "baton/_data/examples"' in text
    assert set(catalog()) == {"fit-check", "software-feature", "backyard-project", "recipe-builder"}


# -- structured questions and confirmed answers ----------------------------


def _blocked_fit_check(cli: Cli, project: Path) -> str:
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    out = manual(cli, project, run, "describe", None, status="blocked", questions_for_human=QUESTIONS)
    assert out["outcome"] == "escalated"
    return run


@pytest.mark.slow
def test_blocked_step_lists_structured_questions_and_labelled_options(tmp_path):
    cli, project = fresh(tmp_path)
    run = _blocked_fit_check(cli, project)
    pd = status(cli, run)["pending_decisions"]
    assert len(pd) == 1 and pd[0]["kind"] == "escalation" and pd[0]["reason"] == "blocked"
    qs = pd[0]["questions"]
    assert [q["id"] for q in qs] == ["site", "permits", "hours"]
    assert qs[0]["best_guess"] == "One machine per site at first" and qs[0]["options"][1] == {"id": "several", "label": "Several"}
    assert [q["priority"] for q in qs] == ["needed", "needed", "helpful"]
    assert pd[0]["options"] == [
        {"decision": "retry", "label": "Try again with your answers", "effect": labels.defaults()["blocked"]["retry"]["effect"]},
        {"decision": "abandon", "label": "Set this aside for now", "effect": labels.defaults()["blocked"]["abandon"]["effect"]},
    ]


def _answers(tmp_path: Path, answers) -> str:
    p = tmp_path / "answers.json"  # outside .baton/
    p.write_text(json.dumps(answers), encoding="utf-8")
    return str(p)


CONFIRMED = [
    {"id": "site", "answer": "One machine per site to start", "owner_words": "One each for now. Yes, that's right."},
    {"id": "permits", "answer": "The owner handles permits personally", "owner_words": "I'll do the permits myself. Yes."},
]


@pytest.mark.slow
def test_answers_resume_the_step_with_exactly_the_confirmed_answers(tmp_path):
    cli, project = fresh(tmp_path)
    run = _blocked_fit_check(cli, project)
    out = cli.run("decide", run, "describe", "retry", "--answers", _answers(tmp_path, CONFIRMED),
                  "--note", "One each for now; I'll do the permits. Yes, go ahead.")
    assert out["outcome"] == "retry"
    ev = [json.loads(line) for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    dec = [e for e in ev if e["type"] == "human_decision"][-1]
    assert dec["data"]["kind"] == "answers" and dec["data"]["answers"] == CONFIRMED and dec["data"]["decision_id"].startswith("d")
    assert ev[ev.index(dec) + 1]["type"] == "step_ready"  # the decision precedes the retry it feeds

    d = cli.run("dispatch", run, "describe", "--worker", "owner")
    manifest = json.loads((packet_dir(project, run, "describe", d["attempt"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prior_feedback"]["answers"] == CONFIRMED
    text = (packet_dir(project, run, "describe", d["attempt"]) / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "## The owner's answers" in text and "One machine per site to start" in text and "I'll do the permits myself. Yes." in text

    # The resumed attempt passes with a profile that carries its assumptions.
    write_result(packet_dir(project, run, "describe", d["attempt"]), {**GOOD_PROFILE, "assumptions": ASSUMPTIONS})
    assert cli.run("submit", run, "describe")["outcome"] == "passed"
    record = (project / ".baton" / "runs" / run / "docs" / "describe.md").read_text(encoding="utf-8")
    assert "answer site: One machine per site to start" in record


@pytest.mark.parametrize("answers, partial, message", [
    ([{"id": "site", "answer": "One"}, CONFIRMED[1]], False, "owner_words is required"),
    ([{"id": "colour", "answer": "Blue", "owner_words": "Blue."}, *CONFIRMED], False, "'colour' is not one of the step's questions"),
    ([CONFIRMED[0]], False, "needed questions not answered: permits"),
    ([CONFIRMED[0], CONFIRMED[0], CONFIRMED[1]], False, "answered more than once"),
], ids=["no-owner-words", "unknown-id", "missing-needed", "duplicate"])
@pytest.mark.slow
def test_bad_answers_are_refused_and_nothing_is_recorded(tmp_path, answers, partial, message):
    cli, project = fresh(tmp_path)
    run = _blocked_fit_check(cli, project)
    before = (project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8")
    out = cli.run("decide", run, "describe", "retry", "--answers", _answers(tmp_path, answers), "--note", "words", expect=1)
    assert out["error"] == "answers.invalid" and message in out["message"]
    assert (project / ".baton" / "runs" / run / "events.jsonl").read_text(encoding="utf-8") == before


@pytest.mark.slow
def test_partial_answers_need_the_partial_flag(tmp_path):
    cli, project = fresh(tmp_path)
    run = _blocked_fit_check(cli, project)
    out = cli.run("decide", run, "describe", "retry", "--answers", _answers(tmp_path, [CONFIRMED[0]]),
                  "--note", "One each. I'm not sure about permits yet.", "--partial")
    assert out["outcome"] == "retry"
    d = cli.run("dispatch", run, "describe", "--worker", "owner")
    manifest = json.loads((packet_dir(project, run, "describe", d["attempt"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prior_feedback"]["answers"] == [CONFIRMED[0]]


@pytest.mark.slow
def test_answers_only_for_a_blocked_step(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    out = cli.run("decide", run, "describe", "retry", "--answers", _answers(tmp_path, CONFIRMED), "--note", "x", expect=1)
    assert out["error"] == "decide.nothing_pending"


@pytest.mark.slow
def test_bare_string_questions_still_work(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", None, status="blocked", questions_for_human=["How often does it happen?", "Who signs off?"])
    qs = status(cli, run)["pending_decisions"][0]["questions"]
    assert [(q["id"], q["ask"], q["why"]) for q in qs] == [("q1", "How often does it happen?", ""), ("q2", "Who signs off?", "")]
    # The older path (a note, no answers file) still retries; so do confirmed answers keyed q1/q2.
    out = cli.run("decide", run, "describe", "retry", "--answers", _answers(tmp_path, [
        {"id": "q1", "answer": "A few times a month", "owner_words": "A few a month, yes."},
        {"id": "q2", "answer": "The owner", "owner_words": "Me. Right."}]), "--note", "A few a month; me.")
    assert out["outcome"] == "retry"


@pytest.mark.slow
def test_invalid_question_entries_reject_the_result(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    out = manual(cli, project, run, "describe", None, status="blocked", questions_for_human=[{"ask": "no id or why"}, 7])
    assert out["outcome"] == "retry" and any("questions_for_human" in r for r in out["reasons"])


# -- labels -------------------------------------------------------------------


@pytest.mark.slow
def test_every_pending_decision_lists_labelled_options(tmp_path):
    cli, project = fresh(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    manual(cli, project, run, "describe", GOOD_PROFILE)
    out = manual(cli, project, run, "assess", {"verdict": "fits", "reasons": [{"row": "occurrences", "leans": "baton", "reason": "few"}],
                                               "next_step": "Author a recipe."})
    assert out["needs_owner"]
    pd = status(cli, run)["pending_decisions"]
    # fit-check labels its own verdict gate (§13.8); the effect comes from the defaults.
    assert pd[0]["options"] == [
        {"decision": "approve", "label": "That verdict sounds right", "effect": labels.defaults()["gate"]["approve"]["effect"]},
        {"decision": "reject", "label": "I don't think that's right", "effect": labels.defaults()["gate"]["reject"]["effect"]},
    ]
    board = cli("board", expect=None).payload
    for r in board["runs"]:
        for p in r["pending_decisions"]:
            assert p["options"] and all(set(o) >= {"decision", "label", "effect"} and o["label"] for o in p["options"])


def test_default_labels_cover_every_decision_kind():
    d = labels.defaults()
    from baton.engine import ESCALATION_DECISIONS, GATE_DECISIONS, SKIP_DECISIONS
    from baton.frame import FRAME_DECISIONS
    from baton.publish import CONFLICT_DECISIONS

    want = {"gate": GATE_DECISIONS, "triage": GATE_DECISIONS, "protected": GATE_DECISIONS, "escalation": ESCALATION_DECISIONS,
            "blocked": ESCALATION_DECISIONS, "iteration_limit": ESCALATION_DECISIONS, "skip_notice": SKIP_DECISIONS,
            "publish_conflict": CONFLICT_DECISIONS, "drift": ("leave", "ingest"), "baseline": ("establish",), "frame": FRAME_DECISIONS}
    for kind, decisions in want.items():
        for dec in decisions:
            entry = d[kind][dec]
            assert entry["label"] and entry["effect"], (kind, dec)
            for word in ("run", "step", "attempt", "dispatch", "escalat", "gate", "worker", "packet"):
                assert word not in f" {entry['label'].lower()} ", (kind, dec, word)


# -- framing: the water-vending scenario ---------------------------------------


def frame_output(kiosk_inputs=None) -> dict:
    return {
        "goal": "Start a business selling purified water from a few self-serve machines around town.",
        "parts": [
            {"id": "setup", "label": "Setting up the business", "description": "Registering it, banking, insurance and permits.",
             "kind": "project", "proposal": {"fit_check": {"idea": "Set up a small water-vending business: registration, insurance, permits."}},
             "reasons": ["No listed process covers business setup"]},
            {"id": "kiosk", "label": "Building the first machine site", "description": "Preparing the ground and shelter for the first machine.",
             "kind": "project",
             "proposal": {"recipe": "backyard-project", "inputs": kiosk_inputs or {"title": "First machine site", "description": "A pad and shelter for one water machine."}},
             "reasons": ["Physical build work"]},
            {"id": "signage", "label": "Signs for the sites", "description": "Signs that tell passers-by what the machine is.",
             "kind": "project", "proposal": {"recipe": "backyard-project", "inputs": {"title": "Signs"}},  # missing description: invalid
             "reasons": ["Physical build work"]},
            {"id": "running", "label": "Running the machines day to day", "description": "Refilling, cleaning and collecting payments.",
             "kind": "operations", "proposal": {"fit_check": {"idea": "Run water machines day to day: refills, cleaning, payments.", "title": "Daily operations"}},
             "reasons": ["Day-to-day work is an operations question"]},
        ],
        "assumptions": [{"about": "scale", "value": "a handful of machines", "basis": "you said a few around town"}],
    }


def _frame(cli: Cli, project: Path) -> str:
    out = cli.run("frame", "--note", WORDS)
    assert out["started"] and out["state"] == "active"
    return out["framing"]


@pytest.mark.slow
def test_framing_inputs_hold_the_owners_words_and_every_recipe(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    d = cli.run("dispatch", fr, "frame", "--worker", "owner")
    pdir = packet_dir(project, fr, "frame", d["attempt"])
    words = json.loads((pdir / "inputs" / "words.json").read_text(encoding="utf-8"))
    assert words == WORDS
    recipes = json.loads((pdir / "inputs" / "recipes.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in recipes}
    assert set(by_id) == {"fit-check", "software-feature", "backyard-project"}
    assert by_id["fit-check"]["vendored"] and not by_id["backyard-project"]["vendored"]
    assert by_id["backyard-project"]["run_inputs"]["required"] == ["title", "description"]
    rubric = json.loads((pdir / "inputs" / "rubric.json").read_text(encoding="utf-8"))
    assert rubric == (FIT_CHECK / "static" / "rubric.md").read_text(encoding="utf-8")
    # While it is active, frame reports it instead of starting another.
    again = cli.run("frame", "--note", "something else")
    assert again["started"] is False and again["framing"] == fr


@pytest.mark.slow
def test_water_vending_framing_selects_two_parts_and_reports_a_gap(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    out = manual(cli, project, fr, "frame", frame_output())
    assert out["outcome"] == "needs_human"
    st = cli("frame", expect=4).payload
    assert st["goal"].startswith("Start a business") and [p["id"] for p in st["parts"]] == ["setup", "kiosk", "signage", "running"]
    pd = status(cli, fr)["pending_decisions"]
    assert [(p["ref"], p["kind"]) for p in pd] == [("frame", "gate")]
    assert [o["decision"] for o in pd[0]["options"]] == ["select", "reject"] and pd[0]["options"][0]["label"] == "Include these"

    # approve is not how a selection is made
    bad = cli.run("decide", fr, "frame", "approve", "--note", "ok", expect=1)
    assert bad["error"] == "decide.bad_decision"
    bad = cli.run("decide", fr, "frame", "select", "--items", "setup,nope", "--note", "x", expect=1)
    assert bad["error"] == "frame.unknown_part"

    note = "Let's do the business setup, the first site and the signs. Yes, those three."
    sel = cli.run("decide", fr, "frame", "select", "--items", "setup,kiosk,signage", "--note", note)
    assert sel["selected"] == ["setup", "kiosk", "signage"]
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("setup", "fit-check@3"), ("kiosk", "backyard-project@1")]
    assert [g["part"] for g in sel["gaps"]] == ["signage"] and "description" in sel["gaps"][0]["reason"]
    assert sel["vendored"] == ["backyard-project@1"] and sel["state"] == "completed"

    ev = [json.loads(line) for line in (project / ".baton" / "runs" / fr / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    types = [e["type"] for e in ev]
    dec = next(e for e in ev if e["type"] == "human_decision")
    assert dec["data"]["note"] == note and dec["data"]["items"] == ["setup", "kiosk", "signage"]
    fs = next(e for e in ev if e["type"] == "framing_selected")
    assert fs["data"]["decision_id"] == dec["data"]["decision_id"] and fs["data"]["runs"] == sel["runs"]
    assert types.index("framing_selected") < types.index("run_completed")

    for r in sel["runs"]:
        started = json.loads((project / ".baton" / "runs" / r["run"] / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert started["data"]["framing"] == {"run": fr, "part": r["part"]}
    setup = status(cli, sel["runs"][0]["run"])
    assert setup["recipe"].startswith("fit-check") and "describe" in setup["ready"]
    assert cli.run("check")["ok"]
    assert "nothing to commit" not in json.dumps(sel.get("checkpoint") or {})
    assert git(project, "status", "--porcelain", "--", ".baton/").strip() == ""  # runs, recipes and lockfile committed


@pytest.mark.slow
def test_every_frame_option_says_what_choosing_it_triggers(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    for payload in (status(cli, fr), cli("board", expect=None).payload["runs"][0]):
        (pd,) = payload["pending_decisions"]
        assert pd["prompt"] and "kiosk" not in pd["prompt"] and "Building the first machine site" in pd["prompt"]
        opts = {o["decision"]: o for o in pd["options"]}
        assert all("next" in o for o in opts.values())
        assert opts["reject"]["next"] == "the breakdown is redone with what you said"
        nxt = {p["part"]: p for p in opts["select"]["next"]}
        assert list(nxt) == ["setup", "kiosk", "signage", "running"]
        assert nxt["kiosk"]["label"] == "Building the first machine site"
        fc = "a fit check: a few questions and a recommendation, no commitment"
        assert nxt["setup"]["next"] == fc and nxt["running"]["next"] == fc
        desc = catalog()["backyard-project"].recipe.description
        assert nxt["kiosk"]["next"] == f"starts backyard-project: {desc}"
        assert nxt["signage"]["next"].startswith("can't start yet: ") and "description" in nxt["signage"]["next"]
    # Reading next changes nothing: the selection still starts exactly the proposals.
    sel = cli.run("decide", fr, "frame", "select", "--items", "setup,kiosk", "--note", "Those two. Yes.")
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("setup", "fit-check@3"), ("kiosk", "backyard-project@1")]


PLAN = "docs/pure-water-vending-business-self-serve-process-plan.md"


@pytest.mark.slow
def test_selection_publishes_the_process_plan_with_every_part(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    sel = cli.run("decide", fr, "frame", "select", "--items", "setup,kiosk", "--note", "The setup and the first site. Yes.")
    assert [(r["part"], r["recipe"]) for r in sel["runs"]] == [("setup", "fit-check@3"), ("kiosk", "backyard-project@1")]
    assert sel["plan"] == PLAN and sel["state"] == "completed"
    text = (project / PLAN).read_text(encoding="utf-8")
    sections = text.split("\n## ")[1:]
    assert [s.splitlines()[0] for s in sections] == [p["label"] for p in frame_output()["parts"]]
    by = {s.splitlines()[0]: s for s in sections}
    runs = {r["part"]: r["run"] for r in sel["runs"]}
    assert f"started (fit-check, run {runs['setup']})" in by["Setting up the business"]
    assert f"started (backyard-project, run {runs['kiosk']})" in by["Building the first machine site"]
    assert "Registering it, banking, insurance and permits." in by["Setting up the business"]
    for label in ("Signs for the sites", "Running the machines day to day"):
        assert "**Status:** for later" in by[label] and "**Choosing it starts:**" in by[label]
    assert "a fit check: a few questions and a recommendation, no commitment" in by["Running the machines day to day"]
    assert f"`{fr}/running`" in by["Running the machines day to day"]
    assert "Nothing here is scheduled" in text
    ev = [json.loads(line) for line in (project / ".baton" / "runs" / fr / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    pub = [e for e in ev if e["type"] == "artifact_published"]
    assert [(e["step_path"], e["data"]["artifact"], e["data"]["path"]) for e in pub] == [("frame", "process_plan", PLAN)]
    assert git(project, "status", "--porcelain").strip() == ""  # the plan is in the selection's checkpoint
    assert cli.run("frame", "--note", "x")["started"] is True  # a new framing run; the finished one is not reported
    assert cli.run("check")["ok"]


@pytest.mark.slow
def test_a_file_already_at_the_process_plan_path_is_a_conflict(tmp_path):
    cli, project = fresh(tmp_path)
    (project / PLAN).parent.mkdir(parents=True, exist_ok=True)
    (project / PLAN).write_text("my own notes\n", encoding="utf-8")
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    sel = cli.run("decide", fr, "frame", "select", "--items", "setup", "--note", "Just the setup. Yes.", expect=4)
    assert sel["state"] == "active"  # the conflict holds completion
    pd = status(cli, fr)["pending_decisions"]
    assert [p["ref"] for p in pd] == ["publish:frame.process_plan"]
    out = cli.run("decide", fr, "publish:frame.process_plan", "alternate", "--note", "Put it beside mine.")
    alt = PLAN.replace(".md", f".{fr}.md")
    assert out["reasons"] == [f"alternate: {alt}"] and (project / alt).is_file()
    assert (project / PLAN).read_text(encoding="utf-8") == "my own notes\n"
    assert status(cli, fr)["state"] == "completed"


def _selected_two(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"][2]["proposal"]["inputs"]["description"] = "Signs at each site."  # a part that can start later
    manual(cli, project, fr, "frame", out)
    sel = cli.run("decide", fr, "frame", "select", "--items", "setup,kiosk", "--note", "The setup and the first site. Yes.")
    return cli, project, fr, sel, out


@pytest.mark.slow
def test_parts_left_in_the_plan_start_later_exactly_as_proposed(tmp_path):
    cli, project, fr, sel, proposed = _selected_two(tmp_path)
    # The owner edits the plan (rewording a part's proposal); the record, not the file, decides what starts.
    plan = project / PLAN
    plan.write_text(plan.read_text(encoding="utf-8").replace("Signs that tell passers-by what the machine is.", "Neon signs everywhere."), encoding="utf-8")
    git(project, "commit", "-qam", "my edits")
    later = cli.run("start", "--from-plan", "signage", expect=None)
    assert later["from_plan"]["framing"] == fr and later["from_plan"]["recipe"] == "backyard-project@1"
    sig = later["run_id"]
    ev0 = json.loads((project / ".baton" / "runs" / sig / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert ev0["data"]["framing"] == {"run": fr, "part": "signage"} and ev0["data"]["recipe"].startswith("backyard-project")
    st = cli.run("status", sig, expect=None)
    assert st["title"] == "Signs"
    # The edited plan is a conflict, decided on the run that was just started; it holds that run.
    pd = [p for p in st["pending_decisions"] if p["kind"] == "publish_conflict"]
    assert [p["ref"] for p in pd] == ["publish:frame.process_plan"] and "edited since" in pd[0]["reasons"][0]
    cli.run("decide", sig, "publish:frame.process_plan", "overwrite", "--note", "Yes, replace my edits.")
    text = plan.read_text(encoding="utf-8")
    assert f"started (backyard-project, run {sig})" in text and "Neon" not in text
    assert all(p["kind"] != "publish_conflict" for p in cli.run("status", sig, expect=None)["pending_decisions"])

    # Untouched since Baton wrote it: re-published silently. By <framing run>/<part> this time.
    run2 = cli.run("start", "--from-plan", f"{fr}/running", expect=None)
    assert run2["from_plan"]["recipe"].startswith("fit-check")
    ev0 = json.loads((project / ".baton" / "runs" / run2["run_id"] / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert ev0["data"]["framing"] == {"run": fr, "part": "running"}
    assert all(p["kind"] != "publish_conflict" for p in run2["pending_decisions"])
    text = plan.read_text(encoding="utf-8")
    assert f"run {run2['run_id']})" in text and "for later" not in text
    fev = [json.loads(line) for line in (project / ".baton" / "runs" / fr / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["data"]["part"] for e in fev if e["type"] == "framing_started_later"] == ["signage", "running"]
    assert sum(1 for e in fev if e["type"] == "artifact_published") == 3  # selection, then each later start
    assert git(project, "status", "--porcelain", "--", ".baton/", "docs/").strip() == ""
    assert cli.run("check")["ok"]

    # Started parts are refused, naming their run.
    again = cli.run("start", "--from-plan", "kiosk", expect=1)
    assert again["error"] == "frame.part_started" and sel["runs"][1]["run"] in again["message"]
    assert cli.run("start", "--from-plan", "nope", expect=1)["error"] == "frame.unknown_part"
    assert cli.run("start", "fit-check", "--from-plan", "setup", expect=1)["error"] == "start.from_plan_alone"


@pytest.mark.slow
def test_a_part_id_in_two_plans_must_be_named_with_its_framing_run(tmp_path):
    cli, project, fr, sel, _ = _selected_two(tmp_path)
    fr2 = cli.run("frame", "--note", "Also a second goal.")["framing"]
    manual(cli, project, fr2, "frame", frame_output())
    cli.run("decide", fr2, "frame", "select", "--items", "", "--note", "None yet.")
    amb = cli.run("start", "--from-plan", "running", expect=1)
    assert amb["error"] == "frame.ambiguous_part" and f"{fr}/running" in amb["message"] and f"{fr2}/running" in amb["message"]


@pytest.mark.slow
def test_unmapped_process_plan_path_uses_the_default(tmp_path):
    cli, project = fresh(tmp_path)
    pyaml = project / ".baton" / "project.yaml"
    pyaml.write_text(pyaml.read_text(encoding="utf-8").replace("paths: { process_plans: docs, notes: docs }", "paths: {}", 1), encoding="utf-8")
    git(project, "commit", "-qam", "no paths")
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    sel = cli.run("decide", fr, "frame", "select", "--items", "", "--note", "None for now.")
    assert sel["plan"] == PLAN and (project / PLAN).is_file()



@pytest.mark.parametrize(("words", "slug"), [
    ("Pure-water vending in Tucson", "pure-water-vending-in-tucson"),  # fits: kept whole, lead-in and all
    ("I want a water business", "i-want-a-water-business"),
    ("I want to start a pure-water vending business in Tucson", "pure-water-vending-business-in-tucson"),  # lead-in cut
    ("help me build a website for the church choir and its concerts", "website-church-choir-concerts"),  # common words dropped
    ("I need a plan for converting the garage into a home office with a bathroom", "converting-garage-home-office-bathroom"),
    ("I want to start a pure-water vending business in Tucson, with three machines at first", "pure-water-vending-business-tucson-three"),  # cut at a word
    ("Ich möchte ein Geschäft für reines Wasser gründen und betreiben", "ich-mochte-ein-geschaft-fur-reines"),  # accents folded
    ("I want to start to build to make to open to launch a", "i-want-start-build-make-open-launch"),  # all lead-in: kept, common words dropped
    ("Supercalifragilisticexpialidociousandmorewordsjoinedtogether here", "supercalifragilisticexpialidociousandmor"),
])
def test_the_goal_slug_keeps_a_short_goal_and_shortens_a_long_one_without_summarizing(words, slug):
    from baton.frame import SLUG_MAX, goal_slug, plan_target

    assert goal_slug(words) == slug and len(slug) <= SLUG_MAX
    assert plan_target({"process_plans": "plans/"}, words) == f"plans/{slug}-process-plan.md"


@pytest.mark.slow
def test_selecting_nothing_ends_framing_with_no_runs(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    sel = cli.run("decide", fr, "frame", "select", "--items", "", "--note", "None of these for now, thanks.")
    assert sel["runs"] == [] and sel["gaps"] == [] and sel["state"] == "completed"


@pytest.mark.slow
def test_rejecting_the_breakdown_retries_with_the_note(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    out = cli.run("decide", fr, "frame", "reject", "--note", "Marketing is missing.")
    assert out["outcome"] == "retry"
    d = cli.run("dispatch", fr, "frame", "--worker", "owner")
    manifest = json.loads((packet_dir(project, fr, "frame", d["attempt"]) / "manifest.json").read_text(encoding="utf-8"))
    assert any("Marketing is missing." in r for r in manifest["prior_feedback"]["reasons"])


@pytest.mark.slow
def test_framing_with_one_part_still_asks_the_owner(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    one = frame_output()
    one["parts"] = one["parts"][:1]
    out = manual(cli, project, fr, "frame", one)
    assert out["outcome"] == "needs_human"  # §18 #23: selecting is the owner's decision even with one option


@pytest.mark.slow
def test_a_bare_project_vendors_fit_check_on_selection(tmp_path):
    cli, project = fresh(tmp_path, bare=True)
    fr = _frame(cli, project)
    manual(cli, project, fr, "frame", frame_output())
    sel = cli.run("decide", fr, "frame", "select", "--items", "running", "--note", "Just the day-to-day question. Yes.")
    assert sel["vendored"] == ["fit-check@3"] and sel["runs"][0]["recipe"] == "fit-check@3"


@pytest.mark.slow
def test_a_proposal_for_an_unknown_recipe_is_a_gap(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"][1]["proposal"] = {"recipe": "water-business", "inputs": {"title": "x"}}
    manual(cli, project, fr, "frame", out)
    sel = cli.run("decide", fr, "frame", "select", "--items", "kiosk", "--note", "That one. Yes.")
    assert sel["runs"] == [] and "neither in this project nor shipped" in sel["gaps"][0]["reason"]


@pytest.mark.slow
def test_a_shipped_recipe_needing_unmapped_paths_is_a_gap(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"][1]["proposal"] = {"recipe": "software-feature", "inputs": {"title": "Payments app", "kind": "feature",
                                                                           "feature_request": "Let customers pay by phone."}}
    manual(cli, project, fr, "frame", out)
    sel = cli.run("decide", fr, "frame", "select", "--items", "kiosk", "--note", "That one. Yes.")
    assert sel["runs"] == [] and "paths.specs" in sel["gaps"][0]["reason"] and sel["vendored"] == []


@pytest.mark.slow
def test_frame_output_schema_requires_one_kind_of_proposal(tmp_path):
    cli, project = fresh(tmp_path)
    fr = _frame(cli, project)
    out = frame_output()
    out["parts"][0]["proposal"] = {"recipe": "backyard-project", "inputs": {}, "fit_check": {"idea": "both"}}
    res = manual(cli, project, fr, "frame", out)
    assert res["outcome"] == "retry"


# -- owner notes (Decisions 0065, 0067, 0070) ------------------------------------

NOTE = "Remember: ask the council about\n  permits for the *corner* site — before May.\n"


@pytest.mark.slow
def test_a_note_is_kept_verbatim_only_after_the_owner_accepts_the_file(tmp_path):
    cli, project = fresh(tmp_path)
    notes = project / "docs" / "notes.md"
    offer = cli.run("note", NOTE, expect=4)  # the offer is a question for the owner
    assert offer["notes"] == "offer" and offer["recorded"] is False and not notes.exists()
    # Declined: nothing is kept, and the offer is not made again.
    no = cli.run("note", "--keep-file", "no", "--note", "No thanks, I keep my own.")
    assert no["notes"] == "declined"
    later = cli.run("note", NOTE)
    assert later["notes"] == "declined" and later["recorded"] is False and not notes.exists() and "anywhere" in later["next"]
    # The owner changes their mind.
    yes = cli.run("note", NOTE, "--keep-file", "yes", "--note", "Actually yes, keep one for me.")
    assert yes["notes"] == "kept" and yes["recorded"] is True and yes["path"] == "docs/notes.md"
    text = notes.read_text(encoding="utf-8")
    assert text.startswith("# Notes\n") and f"\n## {yes['at']}\n\n{NOTE}" in text
    import re
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", yes["at"])
    cli.run("note", "Second thought.")
    assert notes.read_text(encoding="utf-8").endswith("\n\nSecond thought.\n") and text in notes.read_text(encoding="utf-8")
    plog = [json.loads(line) for line in (project / ".baton" / "project" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    answers = [e["data"]["decision"] for e in plog if e["type"] == "human_decision" and e["data"].get("kind") == "notes"]
    assert answers == ["no", "yes"]
    assert [e["data"]["text"] for e in plog if e["type"] == "note_recorded"] == [NOTE, "Second thought."]
    assert git(project, "status", "--porcelain").strip() == ""  # each note is committed
    assert cli.run("check")["ok"]
    assert cli.run("note", "--keep-file", "maybe", "--note", "x", expect=1)["error"] == "note.bad_answer"
    assert cli.run("note", "--keep-file", "yes", expect=1)["error"] == "note.note_required"


@pytest.mark.slow
def test_no_packet_ever_contains_a_note(tmp_path):
    cli, project = fresh(tmp_path)
    cli.run("note", "Unique-note-marker 7f3a", "--keep-file", "yes", "--note", "Yes please.")
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    fr = _frame(cli, project)
    for r, step in ((run, "describe"), (fr, "frame")):
        d = cli.run("dispatch", r, step, "--worker", "owner")
        pdir = packet_dir(project, r, step, d["attempt"])
        for f in pdir.rglob("*"):
            if f.is_file():
                assert "Unique-note-marker" not in f.read_text(encoding="utf-8", errors="replace"), f


# -- communication defaults -----------------------------------------------------


@pytest.mark.slow
def test_communication_defaults(tmp_path):
    conv = (ROOT / "defaults" / "communication.md").read_text(encoding="utf-8")
    oper = (ROOT / "defaults" / "communication-operator.md").read_text(encoding="utf-8")
    for phrase in ("project manager", "confirm back", "best guess", "One topic at a time"):
        assert phrase.lower() in conv.lower(), phrase
    # The operator style is the earlier default, byte for byte: its shape is unchanged (§13.6).
    import hashlib

    assert hashlib.sha256(oper.encode("utf-8")).hexdigest() == "2fe218c361f204757c260c369af4254b39ccc07f601c9f8fadb2389402c4bd65"
    for phrase in ("## Shape of every message", "PASTE_TOKEN_HERE", "**First mention**", "**Manual verification**", "Before → After", "No action needed."):
        assert phrase in oper, phrase
    cli, project = fresh(tmp_path)
    assert (project / ".baton" / "communication.md").read_text(encoding="utf-8") == conv
