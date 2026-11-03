"""Adoption (L6, §11): detect, research, crosswalks, seeding (groups included), the baseline.

Phase 11 acceptance: adoption of a fixture project from a different prior
process, using a crosswalk, imports work at the right granularity (including a
partly finished slice), refuses a nonconforming seed, and needs exactly one
owner decision. ``detect`` on a healthy project prints one line.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from baton import adopt
from baton.cli import app

from conftest import SOFTWARE_FEATURE
from projectkit import Cli, git, make_git_project, make_home, packet_dir

PERSON = """\
owner:
  adapter: manual
  vendor: human
  person: owner
  capabilities: [human_judgment, structured_output, long_form_writing, technical_reasoning, file_write, workspace_read]
  tier: strong
  context_tokens: 200000
"""

CROSSWALK = {
    "format": "baton-crosswalk/1",
    "id": "eng-flow",
    "prior_process": "eng-flow: one folder per feature, JSON step records, APPROVED marker files",
    "maps": [
        {"match": "docs/features/*/requirements.md", "step": "software-feature@1/requirements", "artifact": "requirements_doc", "work_item": "{1}"},
        {"match": "docs/features/*/requirements.json", "step": "software-feature@1/requirements", "output": True, "work_item": "{1}"},
        {"match": "docs/features/*/design.md", "step": "software-feature@1/design", "artifact": "design_doc", "work_item": "{1}"},
        {"match": "docs/features/*/design.json", "step": "software-feature@1/design", "output": True, "work_item": "{1}"},
        {"match": "docs/features/*/plan.json", "step": "software-feature@1/plan", "output": True, "work_item": "{1}"},
        {"match": "docs/features/*/APPROVED-plan", "step": "software-feature@1/plan", "gate": 2, "work_item": "{1}"},
        {"match": "docs/features/*/slices/*/impl.json", "step": "software-feature@1/slices/implement", "output": True, "work_item": "{1}", "item": "{2}"},
        {"match": "docs/features/*/slices/*/review.json", "step": "software-feature@1/slices/code_review", "output": True, "work_item": "{1}", "item": "{2}"},
        {"match": "docs/features/*/slices/*/accepted.json", "step": "software-feature@1/slices/accept", "output": True, "work_item": "{1}", "item": "{2}"},
    ],
}

SLICES = [
    {"title": "Login form", "outcome": "users can sign in", "criteria": ["valid password signs in"], "effort": "S"},
    {"title": "Session", "outcome": "sessions persist", "criteria": ["stays signed in"], "effort": "M"},
    {"title": "Logout", "outcome": "users can sign out", "criteria": ["session ends"], "effort": "S"},
]
SLICE_DIRS = ["form", "session", "logout"]


def prior_project(root: Path) -> None:
    """A repo run under 'eng-flow': login (in flight, two of three slices started), export (in flight), search (finished)."""
    def w(rel: str, content: Any) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if isinstance(content, str) else json.dumps(content, indent=2), encoding="utf-8")

    f = "docs/features/login"
    w(f"{f}/request.md", "Users need to sign in.\n")
    w(f"{f}/requirements.md", "# Login requirements\n- password sign-in\n")
    w(f"{f}/requirements.json", {"summary": "Password sign-in with sessions"})
    w(f"{f}/design.md", "# Login design\nCookie sessions.\n")
    w(f"{f}/design.json", {"summary": "Cookie sessions, bcrypt"})
    w(f"{f}/plan.json", {"slices": SLICES})
    w(f"{f}/APPROVED-plan", "approved by the owner, 2026-10-30\n")
    w(f"{f}/slices/form/impl.json", {"commit_sha": "abc1234", "summary": "login form"})
    w(f"{f}/slices/form/review.json", {"findings": [{"id": "F1", "severity": "low", "title": "naming"}], "coverage": {"complete": True}})
    w(f"{f}/slices/form/accepted.json", {"accepted": True})
    w(f"{f}/slices/session/impl.json", {"commit_sha": "def5678", "summary": "session store"})
    w("docs/features/export/request.md", "Export reports as CSV.\n")
    w("docs/features/export/requirements.md", "# Export\n")
    w("docs/features/export/requirements.json", {"notes": "the prior process had no summary field"})  # nonconforming
    w("docs/features/search/request.md", "Search (shipped in 1.2).\n")
    w("docs/features/search/DONE", "shipped\n")
    w("src/app.py", "print('app')\n")
    w("CLAUDE.md", "Prior agent instructions.\n")


def setup(tmp_path: Path) -> tuple[Cli, Path, Path]:
    project = make_git_project(tmp_path / "proj")
    prior_project(project)
    recipe = tmp_path / "software-feature"
    shutil.copytree(SOFTWARE_FEATURE, recipe)
    (recipe / "crosswalks").mkdir()
    (recipe / "crosswalks" / "eng-flow.yaml").write_text(yaml.safe_dump(CROSSWALK, sort_keys=False), encoding="utf-8")
    cli = Cli(project, make_home(tmp_path / "home", PERSON))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Prior work under eng-flow")
    return cli, project, recipe


def submit(cli: Cli, project: Path, run: str, step: str, output: Any, *, expect: int = 0) -> dict:
    d = cli.run("dispatch", run, step, "--worker", "owner")
    pdir = packet_dir(project, run, step, d["attempt"])
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    (pdir.parent / "result" / "result.json").write_text(json.dumps({
        "protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": output}), encoding="utf-8")
    return cli.run("submit", run, step, expect=expect)


def packet_inputs(project: Path, run: str, step: str, attempt: int = 1) -> dict[str, Any]:
    pdir = packet_dir(project, run, step, attempt)
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    return {i["name"]: json.loads((pdir / i["path"]).read_text(encoding="utf-8")) for i in manifest["inputs"] if i["kind"] == "json"}


def research_output(candidates: list[dict[str, Any]], *, test_command: str) -> dict[str, Any]:
    """What a research worker would return, confirming the crosswalk's candidates."""
    by = {}
    for c in candidates:
        by.setdefault((c["work_item"], c["step"], c.get("item")), []).append(c)
    idx = {name: i for i, name in enumerate(SLICE_DIRS)}

    def seed(item: str, step: str, *, slice_key: str | None = None, **extra: Any) -> dict[str, Any]:
        cands = by[(item, step, slice_key)]
        s: dict[str, Any] = {"work_item": item, "step": step}
        if slice_key is not None:
            s["item"] = idx[slice_key]
        for c in cands:
            if c.get("output"):
                s["output_from"] = c["path"]
            elif "artifact" in c:
                s.setdefault("artifacts", {})[c["artifact"]] = c["path"]
            elif "gate" in c:
                s.setdefault("gates", []).append({"gate": c["gate"], "evidence": [c["path"]]})
        s["evidence"] = [c["path"] for c in cands]
        s.update(extra)
        return s

    seeds = [
        seed("login", "requirements"), seed("login", "design"), seed("login", "plan"),
        seed("login", "slices/implement", slice_key="form"), seed("login", "slices/code_review", slice_key="form"),
        seed("login", "slices/accept", slice_key="form"),
        seed("login", "slices/implement", slice_key="session"),  # partly finished: no review yet
        seed("export", "requirements"),  # nonconforming output
    ]
    return {
        "evidence": [{"path": c["path"], "sha256": c["sha256"], "kind": "prior record", "maps_to": c["step"], "confidence": "high"} for c in candidates],
        "work_items": [
            {"key": "login", "title": "Login", "status": "in_flight", "position": "slice 2 of 3 implemented",
             "inputs": {"title": "Login", "kind": "feature", "feature_request": "Users need to sign in."}},
            {"key": "export", "title": "CSV export", "status": "in_flight", "position": "requirements drafted",
             "inputs": {"title": "CSV export", "kind": "feature", "feature_request": "Export reports as CSV."}},
            {"key": "search", "title": "Search", "status": "finished", "position": "shipped in 1.2"},
        ],
        "proposed_seeds": seeds,
        "agent_config": [{"path": "CLAUDE.md", "kind": "agent instructions"}],
        "path_candidates": {"specs": "docs/features"},
        "command_candidates": {"test_command": test_command},
        "gaps": ["no record of who approved the login requirements"],
    }


def all_events(project: Path) -> list[dict[str, Any]]:
    out = []
    for log in sorted((project / ".baton" / "runs").glob("*/events.jsonl")):
        out += [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return out


TEST_COMMAND = f'"{sys.executable}" -c "pass"'


def through_triage(cli: Cli, project: Path, recipe: Path) -> tuple[str, dict[str, str]]:
    """init, vendor, adopt with the crosswalk, research, triage both in-flight items: the baseline is proposed."""
    out = cli.run("adopt", str(recipe), "--crosswalk", "eng-flow")
    assert out["started"] and out["research"] == "ready"
    adoption = out["adoption"]
    assert out["ready"] == ["research"] and "dispatch research" in out["next"]
    d = cli.run("dispatch", adoption, "research", "--worker", "owner")
    inputs = packet_inputs(project, adoption, "research")
    assert inputs["recipe"]["recipe"] == "software-feature@1" and inputs["crosswalk"]["id"] == "eng-flow"
    cands = inputs["candidates"]
    assert {(c["work_item"], c["step"], c.get("item")) for c in cands} >= {("login", "slices/implement", "session"), ("export", "requirements", None)}
    pdir = Path(d["packet"])
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    (pdir.parent / "result" / "result.json").write_text(json.dumps({
        "protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed",
        "output": research_output(cands, test_command=TEST_COMMAND)}), encoding="utf-8")
    out = cli.run("submit", adoption, "research")
    assert out["outcome"] == "passed" and not out["run_completed"]
    st = cli.run("adopt", "software-feature")
    assert not st["started"] and set(st["runs"]) == {"login", "export"}
    assert [h["key"] for h in st["history"]] == ["search"]
    runs = {k: v["run_id"] for k, v in st["runs"].items()}
    for key, level in (("login", "major"), ("export", "standard")):
        assert cli.run("status", runs[key])["ready"] == ["triage"]  # only triage before the baseline
        out = submit(cli, project, runs[key], "triage", {"level": level, "reasons": [f"{key} looks {level}"]})
        assert out["outcome"] == "passed" and not out["needs_owner"]  # the level is approved by the baseline
        assert "research" in packet_inputs(project, runs[key], "triage")
        assert packet_inputs(project, runs[key], "triage")["research"]["work_item"] == key
    st = cli.run("adopt", "software-feature", expect=4)
    assert st["baseline"] == f".baton/adoption/{adoption}/baseline.yaml"
    assert st["pending_decisions"][0]["kind"] == "baseline"
    return adoption, runs


def test_adoption_with_a_crosswalk_needs_exactly_one_owner_decision(tmp_path):
    cli, project, recipe = setup(tmp_path)
    adoption, runs = through_triage(cli, project, recipe)
    assert sum(1 for e in all_events(project) if e["type"] == "human_decision") == 0

    doc = yaml.safe_load((project / ".baton" / "adoption" / adoption / "baseline.yaml").read_text(encoding="utf-8"))
    items = {w["key"]: w for w in doc["work_items"]}
    login, export = items["login"], items["export"]
    assert login["level"] == "major" and export["level"] == "standard"
    seeds = {(s["step"], s.get("item")): s for s in login["seeds"]}
    assert all(s["import"] for s in login["seeds"]), [s for s in login["seeds"] if not s["import"]]
    plan_gates = {g["gate"]: g for g in seeds[("plan", None)]["gates"]}
    assert plan_gates[2]["status"] == "approved outside Baton (evidence)"
    assert plan_gates[1]["status"] == "waiver proposed"
    assert [(w["step"], w["gate"]) for w in login["waivers"]] == [("plan", 1)]
    assert any("requirements gate 1" in a for a in login["attested"])  # human gate at major without evidence
    assert seeds[("slices/implement", 0)]["gates"][1]["status"] == "passed at proposal"  # the script gate ran on the seed
    (refused,) = export["seeds"]
    assert not refused["import"] and refused["action"] == "rerun"
    assert any("nonconforming" in r and "summary" in r for r in refused["reasons"])
    assert export["plan"]["skip"] == ["design"] and "requirements" in export["plan"]["run"]
    assert doc["project_yaml"] == {"paths": {"specs": "docs/features"}, "project": {"test_command": TEST_COMMAND}}
    assert doc["agents_md"]["action"] == "create"
    assert [h["key"] for h in doc["history"]] == ["search"]
    assert "no record of who approved the login requirements" in doc["gaps"]

    head_before = git(project, "rev-parse", "HEAD").strip()
    out = cli.run("establish-baseline", adoption, "--note", "Yes, adopt it as proposed")
    assert out["state"] == "completed"
    # Exactly one owner decision for the whole adoption.
    decisions = [e for e in all_events(project) if e["type"] == "human_decision"]
    assert len(decisions) == 1 and decisions[0]["data"]["note"] == "Yes, adopt it as proposed"
    # One checkpoint commit carries all of it.
    commits = git(project, "rev-list", f"{head_before}..HEAD").split()
    assert len(commits) == 1
    changed = git(project, "show", "--name-only", "--format=", "HEAD").split()
    assert any(p.startswith(f".baton/runs/{runs['login']}/") for p in changed)
    assert any(p.startswith(f".baton/runs/{runs['export']}/") for p in changed)
    assert ".baton/project.yaml" in changed and "AGENTS.md" in changed
    assert f".baton/adoption/{adoption}/baseline.yaml" in git(project, "ls-files", ".baton/adoption").split()  # committed with the proposal

    # Login: imported at the right granularity.
    st = cli.run("status", runs["login"])
    assert st["level"] == "major"
    for s in ("requirements", "design", "plan"):
        assert st["steps"][s]["state"] == "imported", s
    info = st["groups"]["slices"]
    states = {i["title"]: i["state"] for i in info["instances"]}
    assert states == {"Login form": "passed", "Session": "active", "Logout": "not_started"}
    session = next(i["id"] for i in info["instances"] if i["title"] == "Session")
    assert st["ready"] == [f"slices/{session}/i1/code_review"]  # the partly finished slice goes on where it stopped
    ev = all_events(project)
    imported = [e["step_path"] for e in ev if e["run_id"] == runs["login"] and e["type"] == "step_imported"]
    assert len(imported) == 3 + 3 + 1
    assert all(e["actor"] == "human" for e in ev if e["type"] == "step_imported")
    (waived,) = [e for e in ev if e["type"] == "gate_waived"]
    assert waived["step_path"] == "plan" and waived["data"]["scope"] == "imported" and waived["data"]["gate"] == 1
    cs = [e for e in ev if e["type"] == "complexity_set"]
    assert {e["data"]["approval"] for e in cs} == {"baseline"}
    record = (project / ".baton" / "runs" / runs["login"] / "docs" / "plan.md").read_text(encoding="utf-8")
    assert "**imported** from existing work" in record and "APPROVED-plan" in record

    # Export: the nonconforming seed was refused; requirements reruns.
    st = cli.run("status", runs["export"])
    assert st["steps"]["requirements"]["state"] == "ready" and st["steps"]["design"]["state"] == "skipped"
    assert "requirements" in st["ready"]  # (the recipe's plan depends only on design, skipped here, so it is ready too)

    # Configuration and agent pointer; the repository checks clean.
    pyaml = yaml.safe_load((project / ".baton" / "project.yaml").read_text(encoding="utf-8"))
    assert pyaml["paths"] == {"specs": "docs/features"} and pyaml["project"]["test_command"] == TEST_COMMAND
    assert "# Baton project configuration" in (project / ".baton" / "project.yaml").read_text(encoding="utf-8")  # comments kept
    assert adopt.AGENTS_POINTER in (project / "AGENTS.md").read_text(encoding="utf-8")
    assert cli.run("check")["ok"]
    assert not cli.run("board", "--needs-me")["runs"]

    # The partly finished slice continues; the next one starts normally (nothing left to import).
    from baton.models import Findings  # noqa: F401 - the review returns baton:findings

    submit(cli, project, runs["login"], f"slices/{session}/i1/code_review", {"findings": [], "coverage": {"complete": True}})
    assert submit(cli, project, runs["login"], f"slices/{session}/i1/accept", {"accepted": True}, expect=4)["needs_owner"]
    cli.run("decide", runs["login"], f"slices/{session}/i1/accept", "approve", "--note", "Session works.")  # the recipe's acceptance gate
    st = cli.run("status", runs["login"])
    logout = next(i["id"] for i in st["groups"]["slices"]["instances"] if i["title"] == "Logout")
    assert st["ready"] == [f"slices/{logout}/i1/implement"]


def test_an_edited_baseline_is_rechecked(tmp_path):
    cli, project, recipe = setup(tmp_path)
    adoption, runs = through_triage(cli, project, recipe)
    bp = project / ".baton" / "adoption" / adoption / "baseline.yaml"
    doc = yaml.safe_load(bp.read_text(encoding="utf-8"))
    login = next(w for w in doc["work_items"] if w["key"] == "login")
    # The owner drops the plan seed: everything that depends on it would be orphaned.
    for s in login["seeds"]:
        if s["step"] == "plan":
            s["import"] = False
    bp.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    out = cli.run("establish-baseline", adoption, "--note", "go", expect=1)
    assert out["error"] == "baseline.invalid" and "source 'plan' is not seeded" in out["message"]
    assert sum(1 for e in all_events(project) if e["type"] == "human_decision") == 0
    # An undeclared level is refused.
    for s in login["seeds"]:
        if s["step"] == "plan":
            s["import"] = True
    login["level"] = "huge"
    bp.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    out = cli.run("establish-baseline", adoption, "--note", "go", expect=1)
    assert "level 'huge'" in out["message"]
    login["level"] = "major"
    next(w for w in doc["work_items"] if w["key"] == "export")["create"] = False
    bp.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    # A seeded file that changed since the proposal refuses the whole baseline.
    (project / "docs/features/login/plan.json").write_text(json.dumps({"slices": SLICES[:2]}), encoding="utf-8")
    out = cli.run("establish-baseline", adoption, "--note", "go", expect=1)
    assert "plan.json changed since the proposal" in out["message"]
    git(project, "checkout", "--", "docs/features/login/plan.json")
    out = cli.run("establish-baseline", adoption, "--note", "go, but leave export out")
    assert out["runs"]["export"]["state"] == "abandoned"
    assert cli.run("status", runs["login"])["steps"]["plan"]["state"] == "imported"


def test_establish_baseline_needs_the_owners_words_and_a_proposal(tmp_path):
    cli, project, recipe = setup(tmp_path)
    adoption = cli.run("adopt", str(recipe), "--crosswalk", "eng-flow")["adoption"]
    assert cli.run("establish-baseline", adoption, "--note", " ", expect=1)["error"] == "baseline.note_required"
    assert cli.run("establish-baseline", adoption, "--note", "ok", expect=1)["error"] == "baseline.not_ready"


def test_research_scope_cap(tmp_path, monkeypatch):
    cli, project, recipe = setup(tmp_path)
    monkeypatch.setattr(adopt, "SCOPE_MAX_FILES", 5)
    out = cli.run("adopt", str(recipe), expect=1)
    assert out["error"] == "adopt.scope_too_large" and "--scope" in out["message"]
    assert not list((project / ".baton" / "runs").glob("*")) if (project / ".baton" / "runs").exists() else True
    out = cli.run("adopt", "software-feature", "--scope", "docs/features/login/slices")
    assert out["started"]
    assert cli.run("status", out["adoption"])["state"] == "active"


def test_crosswalk_validation(tmp_path):
    from baton.recipe import RecipeError, load_recipe

    _, _, recipe = setup(tmp_path)
    bad = dict(CROSSWALK, maps=[
        {"match": "a/*", "step": "software-feature@1/nope", "output": True, "work_item": "{1}"},
        {"match": "a/*", "step": "software-feature@1/plan", "artifact": "missing", "work_item": "{2}"},
        {"match": "a/*", "step": "other-recipe@1/plan", "output": True, "work_item": "{1}"},
        {"match": "a/*", "step": "software-feature@1/slices/implement", "output": True, "work_item": "{1}"},
        {"match": "a/*/*", "step": "software-feature@1/plan", "gate": 7, "output": True, "work_item": "{1}"},
    ])
    (recipe / "crosswalks" / "eng-flow.yaml").write_text(yaml.safe_dump(bad, sort_keys=False), encoding="utf-8")
    with pytest.raises(RecipeError) as e:
        load_recipe(recipe)
    codes = {i.code for i in e.value.issues}
    assert {"crosswalk.unknown_step", "crosswalk.unknown_artifact", "crosswalk.bad_capture", "crosswalk.other_recipe",
            "crosswalk.item_missing", "crosswalk.unknown_gate", "crosswalk.target"} <= codes


def test_glob_captures():
    rx = adopt.glob_regex("docs/**/slices/*/impl.json")
    m = rx.match("docs/features/login/slices/form/impl.json")
    assert m and m.groups() == ("features/login", "form")
    assert not rx.match("docs/features/login/slices/form/x/impl.json")


def test_detect(tmp_path):
    bare = make_git_project(tmp_path / "bare")
    runner = CliRunner(env={"BATON_HOME": str(make_home(tmp_path / "home", PERSON)), "BATON_PROJECT": str(bare)})
    res = runner.invoke(app, ["detect"])
    assert res.exit_code == 0 and res.stdout.count("\n") == 1 and "baton adopt" in res.stdout

    cli, project, recipe = setup(tmp_path)
    cli.run("init", str(project))
    cli.run("vendor", str(recipe))
    pyaml = project / ".baton" / "project.yaml"
    pyaml.write_text(pyaml.read_text(encoding="utf-8").replace("paths: {}", "paths: { specs: docs/specs, designs: docs/design }", 1), encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Baton")
    run = cli.run("start", "software-feature", "--inputs", json.dumps({"title": "Login", "kind": "feature", "feature_request": "Sign in"}))["run_id"]
    res = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_DIRECTOR": cli.director, "BATON_PROJECT": str(project)}).invoke(app, ["detect"])
    assert res.exit_code == 0, res.stdout
    lines = [ln for ln in res.stdout.splitlines() if not ln.startswith("WARNING")]
    assert len(lines) == 1 and lines[0].startswith("baton: healthy; 1 active run (1 active here)")
    out = cli.run("detect")
    (r,) = out["runs"]
    assert r["run_id"] == run and r["situation"] == "active_here"
    other = Cli(project, cli.home, director="bob@host2")
    assert other.run("detect")["runs"][0]["situation"] == "active_elsewhere"
    # A tampered log is reported as diverged, and detect is no longer quiet.
    log = project / ".baton" / "runs" / run / "events.jsonl"
    log.write_text(log.read_text(encoding="utf-8").replace('"Login"', '"Logon"', 1), encoding="utf-8")
    out = cli.run("detect", expect=1)
    assert out["runs"][0]["situation"] == "diverged" and out["problems"]
