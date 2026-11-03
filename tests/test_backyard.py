"""The ``backyard-project`` example recipe (§5.7) through the CLI with manual workers.

Phase 11 acceptance: at ``minor`` (a flower bed) and ``major`` (a shed) the
recipe runs different, correct step sets; re-triage adds future steps only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import ROOT
from projectkit import Cli, git, make_git_project, make_home, packet_dir

BACKYARD = ROOT / "examples" / "recipes" / "backyard-project"
PERSON = """\
owner:
  adapter: manual
  vendor: human
  person: owner
  capabilities: [human_judgment, structured_output, long_form_writing, technical_reasoning, file_write, vision]
  tier: strong
"""
JPEG = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"


def setup(tmp_path: Path) -> tuple[Cli, Path]:
    project = make_git_project(tmp_path / "yard")
    cli = Cli(project, make_home(tmp_path / "home", PERSON))
    cli.run("init", str(project))
    cli.run("vendor", str(BACKYARD))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return cli, project


def do(cli: Cli, project: Path, run: str, step: str, output: Any, *, artifacts: dict[str, tuple[str, bytes]] | None = None, expect: int = 0) -> dict:
    """Dispatch to the person, play them, submit."""
    d = cli.run("dispatch", run, step, "--worker", "owner")
    pdir = packet_dir(project, run, step, d["attempt"])
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    rdir = pdir.parent / "result"
    listed = []
    for name, (filename, content) in (artifacts or {}).items():
        (rdir / "artifacts").mkdir(parents=True, exist_ok=True)
        (rdir / "artifacts" / filename).write_bytes(content)
        listed.append({"name": name, "path": f"artifacts/{filename}"})
    (rdir / "result.json").write_text(json.dumps({
        "protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": output, "artifacts": listed,
    }), encoding="utf-8")
    return cli.run("submit", run, step, expect=expect)


MATERIALS = {"items": [{"name": "compost", "quantity": "4 bags"}], "tools": ["spade"]}
BUILT = {"done": True, "notes": "Finished."}
SURVEY = {"area_m2": 6, "sun": "full", "ground": "level lawn"}
DESIGN = {"summary": "A 2.4 x 1.8 m shed on a slab.", "footprint": {"length_m": 2.4, "width_m": 1.8, "height_m": 2.2}}
PERMITS = {"permit_required": False, "basis": "Town rule 4.2: sheds under 10 m² need none", "neighbours_informed": True}


def executed(cli: Cli, run: str) -> list[str]:
    """Steps of the run that were done by a worker, in recipe order."""
    st = cli.run("status", run)
    return [s for s, v in st["steps"].items() if v["state"] == "passed"]


def skipped(cli: Cli, run: str) -> list[str]:
    return [s for s, v in cli.run("status", run)["steps"].items() if v["state"] == "skipped"]


def test_flower_bed_at_minor(tmp_path):
    cli, project = setup(tmp_path)
    run = cli.run("start", "backyard-project", "--inputs", json.dumps({"title": "Front flower bed", "description": "Plant a bed of perennials by the porch"}))["run_id"]
    out = do(cli, project, run, "triage", {"level": "minor", "reasons": ["planting only, no structure"]})
    assert out["outcome"] == "passed" and not out["needs_owner"]  # the lowest level needs no approval
    st = cli.run("status", run)
    assert st["level"] == "minor"
    assert skipped(cli, run) == ["site_survey", "design", "permits"]
    assert st["ready"] == ["materials"]
    d = cli.run("dispatch", run, "materials", "--worker", "owner")
    manifest = json.loads((Path(d["packet"]) / "manifest.json").read_text(encoding="utf-8"))
    assert [n["name"] for n in manifest["not_applicable"]] == ["layout_plan"]  # from a skipped step
    cli.run("cancel", run, "materials", expect=None)
    pdir = Path(d["packet"])
    (pdir.parent / "result").mkdir(exist_ok=True)
    (pdir.parent / "result" / "result.json").write_text(json.dumps({
        "protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": MATERIALS}), encoding="utf-8")
    cli.run("submit", run, "materials")
    out = do(cli, project, run, "build", BUILT, artifacts={"finished_photo": ("bed.jpg", JPEG)}, expect=4)
    assert [p["prompt"] for p in out["pending_decisions"]] == ["Accept the finished project as done?"]  # no inspection at minor
    out = cli.run("decide", run, "build", "approve", "--note", "Lovely")
    assert out["run_completed"]
    assert executed(cli, run) == ["triage", "materials", "build"]
    decisions = [json.loads(line) for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text().splitlines()]
    assert sum(1 for e in decisions if e["type"] == "human_decision") == 1


def test_shed_at_major(tmp_path):
    cli, project = setup(tmp_path)
    run = cli.run("start", "backyard-project", "--inputs", json.dumps({"title": "Garden shed", "description": "A small timber shed for tools"}))["run_id"]
    out = do(cli, project, run, "triage", {"level": "major", "reasons": ["roofed structure on a slab"]}, expect=4)
    assert out["pending_decisions"][0]["ref"] == "triage"
    cli.run("decide", run, "triage", "approve", "--note", "Yes, it is a real shed")
    st = cli.run("status", run)
    assert st["level"] == "major" and skipped(cli, run) == [] and st["ready"] == ["site_survey"]
    do(cli, project, run, "site_survey", SURVEY, artifacts={"site_photo": ("site.jpg", JPEG)})
    out = do(cli, project, run, "design", DESIGN, artifacts={"layout_plan": ("plan.md", b"# Shed\n2.4 x 1.8 m\n")}, expect=4)
    assert out["pending_decisions"][0]["prompt"].startswith("Approve the layout")
    cli.run("decide", run, "design", "approve")
    out = do(cli, project, run, "permits", PERMITS, expect=4)
    cli.run("decide", run, "permits", "approve")
    do(cli, project, run, "materials", MATERIALS)
    out = do(cli, project, run, "build", BUILT, artifacts={"finished_photo": ("shed.jpg", JPEG)}, expect=4)
    assert out["pending_decisions"][0]["prompt"] == "Did the finished structure pass inspection?"
    out = cli("decide", run, "build", "approve", "--note", "Inspector signed off", expect=4).payload
    assert out["pending_decisions"][0]["prompt"] == "Accept the finished project as done?"
    out = cli.run("decide", run, "build", "approve")
    assert out["run_completed"]
    assert executed(cli, run) == ["triage", "site_survey", "design", "permits", "materials", "build"]


def test_raised_bed_at_standard(tmp_path):
    """Phase 16: the middle level end to end: a survey and layout, no permits, no layout approval or inspection."""
    cli, project = setup(tmp_path)
    run = cli.run("start", "backyard-project", "--inputs", json.dumps({"title": "Raised bed", "description": "A timber raised bed by the fence"}))["run_id"]
    out = do(cli, project, run, "triage", {"level": "standard", "reasons": ["a raised bed changes the layout"]}, expect=4)
    cli.run("decide", run, "triage", "approve", "--note", "Yes, standard")
    assert skipped(cli, run) == ["permits"]
    do(cli, project, run, "site_survey", SURVEY, artifacts={"site_photo": ("site.jpg", JPEG)})
    do(cli, project, run, "design", DESIGN, artifacts={"layout_plan": ("plan.md", b"# Raised bed\n2.4 x 1.2 m\n")})  # no approval at standard
    do(cli, project, run, "materials", MATERIALS)
    out = do(cli, project, run, "build", BUILT, artifacts={"finished_photo": ("bed.jpg", JPEG)}, expect=4)
    assert [p["prompt"] for p in out["pending_decisions"]] == ["Accept the finished project as done?"]
    assert cli.run("decide", run, "build", "approve", "--note", "Done")["run_completed"]
    assert executed(cli, run) == ["triage", "site_survey", "design", "materials", "build"]
    evs = [json.loads(line) for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text().splitlines()]
    assert [e["step_path"] for e in evs if e["type"] == "human_decision"] == ["triage", "build"]
    assert cli("check").exit_code == 0


def test_retriage_from_minor_to_standard_adds_future_steps_only(tmp_path):
    cli, project = setup(tmp_path)
    run = cli.run("start", "backyard-project", "--inputs", json.dumps({"title": "Bed", "description": "A flower bed"}))["run_id"]
    do(cli, project, run, "triage", {"level": "minor", "reasons": ["planting"]})
    out = cli.run("retriage", run, "--reason", "The owner wants it raised, with a timber frame")
    assert out["outcome"] == "retriage_requested" and out["ready"] == ["triage"]
    out = do(cli, project, run, "triage", {"level": "standard", "reasons": ["a raised bed changes the layout"]}, expect=4)
    assert "instead of 'minor'" in out["pending_decisions"][0]["prompt"]
    cli.run("decide", run, "triage", "approve", "--note", "Yes")
    st = cli.run("status", run)
    assert st["level"] == "standard"
    assert skipped(cli, run) == ["permits"]  # site_survey and design are back; permits stays out
    assert st["ready"] == ["site_survey"]
    assert st["steps"]["triage"]["state"] == "passed"
    summary = cli("summary", run).stdout
    assert "re-triage applied: level minor" in summary
