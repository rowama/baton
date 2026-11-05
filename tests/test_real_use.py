"""Phase 16: real use of the shipped example recipes (§5.7, §16).

Each recipe runs end to end through the CLI, unchanged, with scripted workers
and a scripted Director; the shipped recipes pass the lint with no warnings.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from baton.recipe import load_recipe

from conftest import FIT_CHECK, ROOT, SOFTWARE_FEATURE
from projectkit import FIT_INPUTS, GOOD_PROFILE, git, packet_dir, setup_fit_check, write_result
from realkit import Director, calls, make_toy_project, run_events

BACKYARD = ROOT / "examples" / "recipes" / "backyard-project"
EXAMPLES = ROOT / "examples" / "recipes"
CLEAN = {"output": {"findings": [], "coverage": {"complete": True, "notes": ""}}}


def good(path: str, text: str = "def f():\n    return 1\n", summary: str = "done") -> dict:
    return {"commit": {"path": path, "text": text}, "output": {"summary": summary, "tests_added": [f"tests/test_{Path(path).stem}.py"]}}


def high(fid: str, title: str, location: str) -> dict:
    return {"output": {"findings": [{"id": fid, "severity": "high", "title": title, "location": location, "detail": "…", "suggested_fix": "…"}],
                       "coverage": {"complete": True, "notes": ""}}}


def slices(*titles: str) -> dict:
    return {"output": {"slices": [{"title": t, "outcome": f"{t} works", "criteria": [f"R1: {t} is tested"], "effort": "S"} for t in titles]}}


def doc(name: str, text: str, summary: str) -> dict:
    return {"artifacts": {name: text}, "output": {"summary": summary, "open_questions": []}}


def assert_clean_record(cli, project: Path, run: str) -> list[dict]:
    """Every result came from a worker; the Director only routed and relayed; the repository checks clean."""
    evs = run_events(project, run)
    assert any(e["type"] == "run_completed" for e in evs)
    assert all(e["actor"].startswith("worker:") for e in evs if e["type"] == "result_submitted")
    director_types = {e["type"] for e in evs if e["actor"].startswith("director")}
    assert not director_types & {"result_submitted", "step_passed", "gate_passed", "findings_recorded", "artifact_published", "human_decision"}
    # Every owner decision answered a gate the recipe (or the runtime's implicit triage gate) defines.
    for e in evs:
        if e["type"] == "human_decision":
            assert e["actor"] == "human" and e["data"].get("kind", "gate") == "gate", e
    assert cli("check").exit_code == 0
    assert not git(project, "status", "--porcelain").strip(), "every change is committed"
    return evs


# ---------------------------------------------------------------------------
# The lint: the shipped recipes load with no errors and no warnings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["fit-check", "software-feature", "backyard-project"])
def test_shipped_recipes_pass_the_lint_with_no_warnings(name):
    loaded = load_recipe(EXAMPLES / name)
    assert loaded.warnings == []


def test_the_examples_directory_ships_exactly_the_three_recipes():
    assert sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir()) == ["backyard-project", "fit-check", "software-feature"]
    assert SOFTWARE_FEATURE == EXAMPLES / "software-feature" and FIT_CHECK == EXAMPLES / "fit-check"


# ---------------------------------------------------------------------------
# software-feature at each level
# ---------------------------------------------------------------------------

FIX = {"title": "Greeting", "kind": "fix", "feature_request": "Add a greet() function that returns 'hi'."}


def test_software_feature_minor(tmp_path):
    script = {"triage": {"output": {"level": "minor", "reasons": ["one small fix: bug fix, one sitting"]}},
              "implement": good("src/greet.py", "def greet():\n    return 'hi'\n"), "code_review": CLEAN}
    cli, project, sf = make_toy_project(tmp_path, script)
    run = cli.run("start", "software-feature", "--inputs", json.dumps(FIX))["run_id"]
    d = Director(cli, project, run)
    st = d.drive()
    assert st["level"] == "minor"
    assert [s for s, v in st["steps"].items() if v["state"] == "skipped"] == ["requirements", "design", "plan"]
    inst = st["groups"]["slices"]["instances"]
    assert len(inst) == 1 and inst[0]["state"] == "passed"  # one instance from the run inputs (foreach_if_source_skipped: once)
    assert [s.rsplit("/", 1)[-1] for s, _ in d.dispatches] == ["triage", "implement", "code_review", "accept"]
    assert [r.rsplit("/", 1)[-1] for r, _ in d.owner_decisions] == ["accept"]  # minor: no triage approval, only acceptance
    impl = next(c for c in calls(sf) if c["step"].endswith("/implement"))
    assert "design_doc" in [n["name"] for n in impl["not_applicable"]] and "slice" in impl["inputs"]
    assert (project / "src" / "greet.py").read_text(encoding="utf-8").startswith("def greet")
    evs = assert_clean_record(cli, project, run)
    gate_runs = [e for e in evs if e["type"] == "gate_passed" and e["step_path"].endswith("/implement") and e["data"].get("type") == "script"]
    assert gate_runs, "the project's test command ran as a gate"


def test_software_feature_standard(tmp_path):
    script = {
        "triage": {"output": {"level": "standard", "reasons": ["a feature touching several modules"]}},
        "requirements": doc("requirements_doc", "# Requirements\n\n1. Users can sign in.\n", "Sign-in"),
        "plan": slices("Login form", "Session", "Logout"),
        "plan~review": CLEAN,
        "implement:Login form": [good("src/login.py", "BROKEN = True\n"), good("src/login.py")],  # attempt 1 fails the test gate
        "implement:Session": [good("src/session.py"), {**good("src/session.py", "def f():\n    return 2\n"), "dispose": "fixed"}],
        "implement:Logout": good("src/logout.py"),
        "code_review:Session": [high("F1", "Session never expires", "src/session.py:1"), CLEAN],
        "code_review": CLEAN,
    }
    cli, project, sf = make_toy_project(tmp_path, script)
    inputs = {"title": "Sign in", "kind": "feature", "feature_request": "Let users sign in and out."}
    run = cli.run("start", "software-feature", "--inputs", json.dumps(inputs))["run_id"]
    d = Director(cli, project, run)
    st = d.drive()
    assert st["level"] == "standard"
    assert st["steps"]["design"]["state"] == "skipped"
    by_title = {i["title"]: i for i in st["groups"]["slices"]["instances"]}
    assert set(by_title) == {"Login form", "Session", "Logout"} and all(i["state"] == "passed" for i in by_title.values())

    # Owner touchpoints are exactly the recipe's decisions: triage approval, the plan, each slice's acceptance.
    assert [r.rsplit("/", 1)[-1] for r, _ in d.owner_decisions] == ["triage", "plan", "accept", "accept", "accept"]
    # The plan was reviewed by the other vendor before the owner saw it.
    assert ("plan~review", "checker") in d.dispatches
    # Login form: the test command failed on attempt 1, attempt 2 passed.
    evs = run_events(project, run)
    login = by_title["Login form"]["id"]
    impl = [e for e in evs if e["step_path"] == f"slices/{login}/i1/implement"]
    assert [e["attempt"] for e in impl if e["type"] == "dispatched"] == [1, 2]
    assert any(e["type"] == "gate_failed" and e["attempt"] == 1 for e in impl)
    # Session: the review's high finding started iteration 2, whose implement packet carried it; the fix was confirmed.
    session = by_title["Session"]["id"]
    assert any(e["type"] == "iteration_started" and e["step_path"] == f"slices/{session}" and e["data"]["iteration"] == 2 for e in evs)
    i2 = packet_dir(project, run, f"slices/{session}/i2/implement", 1)
    open_findings = json.loads((i2 / "inputs" / "open_findings.json").read_text(encoding="utf-8"))
    assert [f["id"] for f in open_findings["findings"]] == ["F1"]
    last_review = [e for e in evs if e["type"] == "findings_recorded" and e["step_path"] == f"slices/{session}/i2/code_review"][-1]
    assert last_review["data"]["open"] == [] and last_review["data"]["resolved"] == [
        {"id": "F1", "severity": "high", "title": "Session never expires", "disposition": "fixed", "confirmed": True}]  # the worker's claim, confirmed
    claim = next(e for e in evs if e["type"] == "finding_dispositioned")
    assert claim["data"]["by"] == "worker" and claim["data"]["disposition"] == "fixed" and claim["data"]["provisional"]
    # The requirements were published to the mapped path.
    published = project / "docs" / "specs" / "sign-in-requirements.md"
    assert published.read_text(encoding="utf-8").startswith("# Requirements")
    # The protected acceptance specs were never touched.
    assert (project / "tests" / "acceptance" / "specs" / "login.md").read_text(encoding="utf-8").startswith("# Acceptance specs")
    assert_clean_record(cli, project, run)


def test_software_feature_major(tmp_path):
    script = {
        "triage": {"output": {"level": "major", "reasons": ["changes a stored format"]}},
        "requirements": doc("requirements_doc", "# Requirements\n\n1. Export to CSV.\n", "Export"),
        "design": doc("design_doc", "# Design\n\nA CSV writer.\n", "CSV writer"),
        "design~review": {"output": {"findings": [{"id": "D1", "severity": "medium", "title": "Failure mode vague", "location": "Failure modes",
                                                   "detail": "…", "suggested_fix": "…"}], "coverage": {"complete": True, "notes": ""}}},
        "plan": slices("Writer", "Command"),
        "plan~review": CLEAN,
        "implement:Writer": good("src/writer.py"),
        "implement:Command": [good("src/command.py"), good("src/command.py", "def f():\n    return 3\n")],
        "code_review": CLEAN,
    }
    cli, project, sf = make_toy_project(tmp_path, script)
    inputs = {"title": "CSV export", "kind": "feature", "feature_request": "Export reports as CSV."}
    run = cli.run("start", "software-feature", "--inputs", json.dumps(inputs))["run_id"]
    # The owner rejects the second slice once: acceptance is a judge, so the slice goes back to implement.
    d = Director(cli, project, run, decisions={"accept": [("approve", "Writer works."), ("reject", "The command ignores --out."),
                                                          ("approve", "Now it writes where I asked.")]})
    st = d.drive()
    assert st["level"] == "major"
    assert [r.rsplit("/", 1)[-1] for r, _ in d.owner_decisions] == ["triage", "requirements", "plan", "accept", "accept", "accept"]
    # Both deliverables published; the advisory design review recorded its finding without blocking.
    assert (project / "docs" / "specs" / "csv-export-requirements.md").is_file()
    assert (project / "docs" / "design" / "csv-export-design.md").read_text(encoding="utf-8").startswith("# Design")
    evs = run_events(project, run)
    design_findings = [e for e in evs if e["type"] == "findings_recorded" and e["step_path"] == "design"]
    assert design_findings and design_findings[-1]["data"]["open"] == ["D1"] and st["steps"]["design"]["state"] == "passed"
    # The rejected acceptance started iteration 2 at implement, carrying the owner's words.
    command = next(i["id"] for i in st["groups"]["slices"]["instances"] if i["title"] == "Command")
    assert any(e["type"] == "iteration_started" and e["step_path"] == f"slices/{command}" and e["data"]["iteration"] == 2 for e in evs)
    i2 = packet_dir(project, run, f"slices/{command}/i2/implement", 1)
    carried = (i2 / "inputs" / "open_findings.json").read_text(encoding="utf-8")
    assert "The command ignores --out." in carried
    assert [c["key"] for c in calls(sf) if c["step"].startswith(f"slices/{command}/") and c["step"].endswith("/implement")] == \
        ["implement:Command", "implement:Command"]
    assert_clean_record(cli, project, run)


# ---------------------------------------------------------------------------
# fit-check: one run per verdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict, next_step", [
    ("fits", "Author a contract-review recipe."),
    ("fits_per_occurrence", "A recipe plus a scheduler that calls baton start per contract."),
    ("operations_engine", "Start a software-feature run whose deliverable is that system."),
])
def test_fit_check_each_verdict(tmp_path, verdict, next_step):
    cli, project = setup_fit_check(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    for step, output in (("describe", GOOD_PROFILE),
                         ("assess", {"verdict": verdict, "reasons": [{"row": "occurrences", "leans": "baton", "reason": "x"}], "next_step": next_step})):
        a = cli.run("dispatch", run, step, "--worker", "owner")["attempt"]
        write_result(packet_dir(project, run, step, a), output)
        cli("submit", run, step, expect=None)
    assert cli("status", run, expect=4).payload["pending_decisions"][0]["ref"] == "assess"
    assert cli.run("decide", run, "assess", "approve", "--note", "Agreed.")["run_completed"]
    assert_clean_record(cli, project, run)


# ---------------------------------------------------------------------------
# A remote Director: shell only, many short sessions, woken by hooks (§3, §8.7)
# ---------------------------------------------------------------------------

REMOTE = Path(__file__).parent / "fakes" / "remote_director.py"
WAKE = """\
import json, os, sys
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps({k: v for k, v in os.environ.items() if k.startswith("BATON_")}) + "\\n")
"""


def test_remote_director_completes_a_multi_slice_work_item_across_sessions(tmp_path):
    """The Phase 16 scenario: each Director session is a fresh process with only a shell; it dispatches without
    waiting and ends its turn; completion hooks (a webhook to the remote agent) start the next session. The owner
    only answers the recipe's own decisions and does the person's step."""
    import subprocess
    import sys
    import time

    from realkit import cmdline, configure

    script = {
        "triage": {"output": {"level": "standard", "reasons": ["several modules"]}},
        "requirements": doc("requirements_doc", "# Requirements\n\n1. Users can sign in.\n", "Sign-in"),
        "plan": slices("Login form", "Session"),
        "plan~review": CLEAN,
        "implement:Login form": good("src/login.py"),
        "implement:Session": [good("src/session.py"), {**good("src/session.py", "def f():\n    return 2\n"), "dispose": "fixed"}],
        "code_review:Session": [high("F1", "Session never expires", "src/session.py:1"), CLEAN],
        "code_review": CLEAN,
    }
    cli, project, sf = make_toy_project(tmp_path, script)
    inbox, outbox, sessions = tmp_path / "inbox.jsonl", tmp_path / "outbox.jsonl", tmp_path / "sessions.jsonl"
    wake_py = tmp_path / "wake.py"
    wake_py.write_text(WAKE, encoding="utf-8")
    configure(project, hooks={"on_complete": cmdline([sys.executable, str(wake_py), str(inbox)])})
    (project / ".baton" / "preferences.yaml").write_text(  # the owner's routing preference: the agents before the person
        "prefer:\n  by_capability:\n    structured_output: [builder, checker]\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Wake the remote Director on completion")

    env = {k: v for k, v in os.environ.items() if not k.startswith("BATON_")}
    env.update(BATON_HOME=str(cli.home), BATON_DIRECTOR="remote@cloud", BATON_HARNESS="cloud-chat",
               PYTHONPATH=str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""))

    def session(wake: dict) -> None:
        w = tmp_path / "wake.json"
        w.write_text(json.dumps(wake), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(REMOTE), str(w), str(outbox), str(sessions)], cwd=project, env=env,
                              capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def lines(f: Path) -> list[dict]:
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    owner_actions: list[tuple[str, str]] = []
    answered: set[tuple] = set()
    hooks_seen = messages_seen = 0
    inputs = {"title": "Sign in", "kind": "feature", "feature_request": "Let users sign in and out."}
    session({"owner": {"kind": "start", "recipe": "software-feature", "inputs": inputs}})
    run = None
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        # The owner reads what the Director told them and answers only what the recipe asks.
        out = lines(outbox)
        reply = None
        for m in out[messages_seen:]:
            run = m["run"]
            if m["kind"] == "done":
                reply = "done"
            elif m["kind"] == "question" and (m["ref"], m["attempt"]) not in answered:
                answered.add((m["ref"], m["attempt"]))
                owner_actions.append(("decide", m["ref"].rsplit("/", 1)[-1]))
                reply = {"kind": "decision", "run": m["run"], "ref": m["ref"], "decision": "approve", "note": "Looks right."}
            elif m["kind"] == "manual":
                owner_actions.append(("do", m["step"].rsplit("/", 1)[-1]))
                write_result(Path(m["packet"]), {"accepted": True, "notes": "Tried it."})
                reply = {"kind": "submitted", "run": m["run"], "step": m["step"]}
            if reply:
                break
        messages_seen = out.index(m) + 1 if reply else len(out)
        if reply == "done":
            break
        if reply:
            session({"owner": reply})
            continue
        hooks = lines(inbox)
        if len(hooks) > hooks_seen:
            for h in hooks[hooks_seen:]:
                session({"hook": h})
            hooks_seen = len(hooks)
            continue
        time.sleep(0.1)
    else:
        raise AssertionError("the work item did not finish")

    st = cli.run("status", run)
    assert st["state"] == "completed" and len(st["groups"]["slices"]["instances"]) == 2
    # The owner did nothing beyond the recipe's decisions: triage, the plan, and each slice's acceptance (do + approve).
    assert owner_actions == [("decide", "triage"), ("decide", "plan")] + [("do", "accept"), ("decide", "accept")] * 2
    logged = lines(sessions)
    assert len(logged) >= 8 and len({s["pid"] for s in logged}) == len(logged)  # many separate sessions
    woken_by_hook = [s for s in logged if "hook" in s["wake"]]
    assert len(woken_by_hook) >= 6
    every = [c for s in logged for c in s["commands"]]
    assert not any("--wait" in c or c[0] == "wait" for c in every)  # never attached: always ended the turn
    assert {c[0] for c in every} <= {"detect", "board", "status", "eligible", "dispatch", "decide", "submit", "start", "summary"}
    evs = assert_clean_record(cli, project, run)
    assert {e["data"]["director_id"] for e in evs if e["type"] in ("lease_claimed", "lease_renewed")} <= {"remote@cloud"}
    session_iteration = [e for e in evs if e["type"] == "iteration_started" and e["data"]["iteration"] == 2]
    assert len(session_iteration) == 1  # the review sent one slice back, handled by the recipe without the owner
    assert [c["profile"] for c in calls(sf) if c["step"].endswith("code_review")] == ["checker"] * 3


# ---------------------------------------------------------------------------
# Principle checks (§19)
# ---------------------------------------------------------------------------


def test_a_healthy_project_makes_no_routine_owner_prompts(tmp_path):
    """After setup and a finished work item, the routine checks say one line each and nothing needs the owner.
    (Adoption needing exactly one owner decision: test_adoption; every owner touchpoint being a recipe gate:
    ``assert_clean_record`` in every run above and the remote-Director scenario.)"""
    from typer.testing import CliRunner

    from baton.cli import app

    script = {"triage": {"output": {"level": "minor", "reasons": ["a small fix"]}},
              "implement": good("src/greet.py"), "code_review": CLEAN}
    cli, project, _ = make_toy_project(tmp_path, script)
    run = cli.run("start", "software-feature", "--inputs", json.dumps(FIX))["run_id"]
    Director(cli, project, run).drive()
    runner = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_PROJECT": str(project), "BATON_DIRECTOR": "alice@host1"})
    res = runner.invoke(app, ["detect"])  # no hook, attached Director: the routine check stays one line (decision 0061)
    assert res.exit_code == 0 and len(res.stdout.strip().splitlines()) <= 1, res.stdout
    # A healthy project has a wake path (§13.4); without one, doctor warns.
    wake = (shlex.join if os.name == "posix" else subprocess.list2cmdline)([sys.executable, "-c", "pass"])
    (cli.home / "hooks.yaml").write_text(yaml.safe_dump({"hooks": {"on_needs_human": wake}}), encoding="utf-8")
    for args in (["detect"], ["doctor", "--no-run"], ["check"], ["board", "--needs-me"], ["resume", run], ["status", run]):
        res = runner.invoke(app, args)
        assert res.exit_code == 0, (args, res.stdout)
        assert len(res.stdout.strip().splitlines()) <= 1, (args, res.stdout)
    assert cli.run("board", "--needs-me")["runs"] == []


def test_readme_profile_example_is_valid(tmp_path):
    """The README's worker profiles load as written (§19: the README covers writing profiles)."""
    import re

    from baton.profiles import load_profiles

    text = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"## Worker profiles.*?```yaml\n(.*?)```", text, re.S).group(1)
    f = tmp_path / "workers.yaml"
    f.write_text(block, encoding="utf-8")
    assert sorted(load_profiles(f)) == ["api-writer", "claude-code-sub", "codex-sub", "owner"]
