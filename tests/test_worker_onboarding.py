"""Machine worker setup as the Director and the owner meet it: doctor, detect and init (§6.4, §13.4; 0074, 0081)."""

from __future__ import annotations

from pathlib import Path

import pytest

from baton import resources
from baton.doctor import NO_WORKER_SETUP_DONE, NO_WORKER_SETUP_OFFER, doctor
from baton.project import Project, init

from test_resources import found, run_setup

PERSON = "owner:\n  adapter: manual\n  creator: human\n  person: owner\n  capabilities: [human_judgment]\n  tier: strong\n"


def project(tmp_path: Path, name: str, home: Path) -> Project:
    root = tmp_path / name
    root.mkdir()
    init(root, bare=True)
    return Project.open(root, home=home)


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("BATON_HOME", str(h))
    return h


def test_setup_is_offered_once_per_machine_not_per_project(tmp_path, home):
    (home / "workers.yaml").write_text(PERSON, encoding="utf-8")
    a = project(tmp_path, "a", home)
    rep = doctor(a, run_noop=False)
    assert rep["ok"] and rep["worker_setup"]["offer_setup"] is True  # an offer, not a problem
    run_setup(home, found("codex"))  # the owner agreed, in project a
    b = project(tmp_path, "b", home)
    rep = doctor(b, run_noop=False)
    assert rep["worker_setup"]["offer_setup"] is False and rep["worker_setup"]["setup_complete"] is True


def test_nothing_more_is_an_answer_too(tmp_path, home):
    (home / "workers.yaml").write_text(PERSON, encoding="utf-8")
    resources.declare(home, nothing_more=True)
    assert doctor(project(tmp_path, "a", home), run_noop=False)["worker_setup"]["offer_setup"] is False


def test_no_worker_before_setup_points_to_setup(tmp_path, home):
    rep = doctor(project(tmp_path, "a", home), run_noop=False)
    assert not rep["ok"] and NO_WORKER_SETUP_OFFER in rep["problems"]


def test_completed_setup_with_no_usable_worker_is_a_problem_without_asking_again(tmp_path, home):
    out = run_setup(home, found())  # nothing installed, nothing declared
    assert out["written"] == []
    rep = doctor(project(tmp_path, "a", home), run_noop=False)
    assert not rep["ok"] and NO_WORKER_SETUP_DONE in rep["problems"]
    assert rep["worker_setup"]["offer_setup"] is False


def test_a_healthy_machine_is_still_one_line(tmp_path, home):
    (home / "workers.yaml").write_text(PERSON, encoding="utf-8")
    run_setup(home, found())
    rep = doctor(project(tmp_path, "a", home), run_noop=False)
    assert rep["ok"] and rep["line"] == "doctor: 1 profile(s) ready"
    assert not any("setup" in w for w in rep["warnings"])


def test_init_mentions_setup_only_while_it_is_not_done(tmp_path, home):
    root = tmp_path / "p"
    root.mkdir()
    out = init(root, bare=True)
    assert any("workers setup" in n for n in out["notes"]) and out["worker_setup"]["offer_setup"]
    run_setup(home, found("codex"))
    profiles = sorted(p.name for p in (home / "workers").glob("*.yaml"))
    assert "codex.yaml" in profiles   # setup also writes one profile per pinned Codex model (2026-11-cli-model-routes)
    root2 = tmp_path / "q"
    root2.mkdir()
    out = init(root2, bare=True)
    assert not any("workers setup" in n for n in out["notes"])
    # init writes no profile and runs no research.
    assert sorted(p.name for p in (home / "workers").glob("*.yaml")) == profiles


def test_detect_carries_the_setup_state(tmp_path, home):
    from baton.adopt import detect

    (home / "workers.yaml").write_text(PERSON, encoding="utf-8")
    p = project(tmp_path, "a", home)
    out = detect(p.root, home=home)
    assert out["machine"]["worker_setup"]["offer_setup"] is True
    assert not any("setup" in w for w in out["warnings"])  # detect stays quiet: the offer is structured


def test_setup_makes_one_profile_per_documented_model_for_each_logged_in_cli(home):
    """Criterion 8 (2026-11-cli-model-routes): per-model CLI profiles beside the default-alias one."""
    run_setup(home, found("claude_code", "codex"))
    names = {p.stem for p in (home / "workers").glob("*.yaml")}
    assert {"claude-code", "claude-code-claude-haiku-5-5", "claude-code-claude-fable-5-1", "codex", "codex-gpt-6-astra"} <= names
