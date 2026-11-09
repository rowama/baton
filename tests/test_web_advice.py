"""Web steps steer the owner to a subscription CLI (§13.4; 2026-11-capability-confidence criterion 10)."""

from __future__ import annotations

import pytest

from pathlib import Path

import yaml

from baton import capability_states as cs
from baton.routing import WEB_ADVICE

from projectkit import OWNER_PROFILE, Cli, git, make_git_project, make_home, packet_dir, write_result
from runkit import make_recipe

WEB_PROFILE = """\
searcher:
  adapter: manual
  vendor: acme
  capabilities: [structured_output, web_access]
  tier: strong
"""


def project_with_web_recipe(tmp_path: Path) -> tuple[Cli, Path]:
    recipe = make_recipe(
        tmp_path / "webby",
        [
            {"id": "look", "requires": {"capabilities": ["structured_output", "web_access"]}, "output_schema": "schemas/out.json"},
            {"id": "write", "depends_on": ["look"], "output_schema": "schemas/out.json"},
        ],
        schemas={"out.json": {"type": "object"}},
        id="webby",
        description="Looks something up, then writes it down.",
    )
    project = make_git_project(tmp_path / "proj")
    home = make_home(tmp_path / "home")
    cli = Cli(project, home)
    cli.run("init", str(project))
    cli.run("vendor", str(recipe))
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "Adopt Baton")
    return cli, project


@pytest.mark.slow
def test_doctor_recommends_a_subscription_cli_only_while_no_worker_can_search(tmp_path):
    cli, _project = project_with_web_recipe(tmp_path)
    out = cli.run("doctor", "--no-run")
    assert out["web_advice"] == {"steps": ["webby@1/look"], "advice": WEB_ADVICE}
    assert any("Claude Code" in w and "webby@1/look" in w for w in out["warnings"])
    assert "Codex" in WEB_ADVICE and "log in" in WEB_ADVICE and "baton workers setup" in WEB_ADVICE
    # A worker that can search: no advice, and nothing added to doctor.
    (cli.home / "workers.yaml").write_text(OWNER_PROFILE + WEB_PROFILE, encoding="utf-8")
    out = cli.run("doctor", "--no-run")
    assert "web_advice" not in out and not any("search the web" in w for w in out["warnings"])
    # One that turned out not to: the advice is back.
    cs.record(cli.home, "searcher", "web_access", "absent", by="observed", evidence="denied")
    assert cli.run("doctor", "--no-run")["web_advice"]["steps"] == ["webby@1/look"]


@pytest.mark.slow
def test_start_carries_the_advice_for_the_recipe_it_starts(tmp_path):
    cli, _project = project_with_web_recipe(tmp_path)
    out = cli.run("start", "webby", "--inputs", '{"title": "Look it up"}')
    assert out["web_advice"] == {"recipe": "webby@1", "steps": ["look"], "advice": WEB_ADVICE}
    import json

    from projectkit import FIT_INPUTS

    assert "web_advice" not in cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))


@pytest.mark.slow
def test_framing_choice_carries_the_advice_for_parts_that_need_the_web(tmp_path):
    cli, project = project_with_web_recipe(tmp_path)
    fr = cli.run("frame", "--note", "Find the best water machines and write up the choice.")["framing"]
    d = cli.run("dispatch", fr, "frame", "--worker", "owner")
    output = {
        "goal": "Choose water machines.",
        "parts": [
            {"id": "research", "label": "Finding the machines", "description": "Looking up what is on the market.", "kind": "project",
             "proposal": {"recipe": "webby", "inputs": {}}, "reasons": ["Needs a search"]},
            {"id": "setup", "label": "Setting up", "description": "Registering the business.", "kind": "project",
             "proposal": {"fit_check": {"idea": "Set up the business."}}, "reasons": ["No process covers it"]},
        ],
        "assumptions": [],
    }
    write_result(packet_dir(project, fr, "frame", d["attempt"]), output)
    cli("submit", fr, "frame", expect=None)
    (pd,) = cli("status", fr, expect=None).payload["pending_decisions"]
    assert pd["web_advice"] == {"parts": [{"part": "research", "label": "Finding the machines", "recipe": "webby@1"}], "advice": WEB_ADVICE}


def test_the_director_is_told_to_pass_it_on():
    from conftest import ROOT

    skill = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    assert "`web_advice`" in skill and "Claude Code or the Codex CLI" in skill
