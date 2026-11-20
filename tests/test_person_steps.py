"""Who does the steps for a person (change 2026-11-first-use-feedback-batch-a, Slice 2: F-2, F-3; Decision 0174).

Baton has a profile for the owner on every machine, which nobody writes; the Director asks at
``start``, once, who does a run's steps for a person, and the answer is kept in project policy;
a person the owner names gets a profile the same way, and the steps for a person go to them.
"""

from __future__ import annotations

import pytest
import yaml

from baton import policy
from baton.engine import Api
from baton.models import ProjectConfig
from baton.packet import EngineError
from baton.project import init

from projectkit import make_home
from runkit import Clock, make_recipe

pytestmark = pytest.mark.slow  # each test sets up a project with a vendored recipe (seconds)

AI = """\
helper:
  adapter: manual
  vendor: acme
  capabilities: [structured_output, vision, long_form_writing]
  tier: strong
"""


def _api(tmp_path, profiles: str = AI) -> tuple[Api, str]:
    recipe = make_recipe(
        tmp_path / "toy",
        [
            {"id": "draft", "requires": {"capabilities": ["structured_output"]}, "output_schema": "schemas/out.json"},
            {"id": "look", "depends_on": ["draft"], "requires": {"capabilities": ["vision"]}, "output_schema": "schemas/out.json"},
            {"id": "survey", "requires": {"capabilities": ["human_judgment", "vision"]}, "output_schema": "schemas/out.json"},
        ],
        schemas={"out.json": {"type": "object"}},
    )
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    api = Api.open(root, director_id="d@host", home=make_home(tmp_path / "home", profiles), clock=Clock())
    api.vendor(recipe)
    return api, "toy"


def _names(out: dict) -> list[str]:
    return [e["profile"] for e in out["eligible"]]


def test_the_owner_has_a_profile_nobody_wrote_and_it_does_only_the_steps_for_a_person(tmp_path):
    api, recipe = _api(tmp_path)
    owner = api.project.profiles()["owner"]
    assert (owner.adapter, owner.person, owner.tier) == ("manual", "owner", "strong")
    assert owner.capabilities == ["human_judgment", "long_form_writing", "vision", "file_write"]
    run = api.start(recipe, {"title": "Shed"})["run_id"]
    assert _names(api.eligible(run, "survey")) == ["owner"]
    # A step for an AI helper never goes to a person's built-in profile, and does not list it (0174).
    look = api.eligible(run, "draft")
    assert "owner" not in _names(look) and "owner" not in {e["profile"] for e in look["excluded"]}


def test_an_owners_own_profile_of_that_name_replaces_it(tmp_path):
    api, _ = _api(tmp_path, AI + "owner:\n  adapter: manual\n  creator: human\n  person: rob\n  capabilities: [human_judgment, vision]\n  tier: strong\n")
    owner = api.project.profiles()["owner"]
    assert owner.person == "rob" and owner.capabilities == ["human_judgment", "vision"] and not owner.builtin_person()


def test_doctor_covers_the_steps_for_a_person_and_says_plainly_when_the_owners_profile_was_replaced(tmp_path):
    api, _ = _api(tmp_path)
    rep = api.doctor()
    assert not any("survey" in w for w in rep["warnings"]), rep["warnings"]
    assert not any(s.endswith("/survey") for s in rep["uncovered_steps"])
    api2, _ = _api(tmp_path / "b", AI + "owner:\n  adapter: manual\n  creator: human\n  person: owner\n  capabilities: [human_judgment]\n  tier: strong\n")
    rep2 = api2.doctor()
    assert any("no profile for a person on this machine can do toy@1/survey" in w and "remove that profile" in w
               for w in rep2["warnings"]), rep2["warnings"]


def test_a_persons_profile_is_not_an_ai_helper_for_doctor(tmp_path):
    api, _ = _api(tmp_path, "")
    assert any("no worker on this machine is ready" in p for p in api.doctor()["problems"])


def test_start_asks_who_does_the_steps_for_a_person_once_and_the_answer_is_kept(tmp_path):
    api, recipe = _api(tmp_path)
    out = api.start(recipe, {"title": "Shed"})
    assert out["people"]["steps"] == ["survey"] and out["people"]["default"] == "owner"
    api.policy_set("Yes, I'll do those myself.", person_steps="yes")
    assert policy.person_steps(api.project.policy_state().in_force) == "owner"
    assert "people" not in api.start(recipe, {"title": "Shed 2"})
    rec = [e for e in api.project.store.project_log().events() if e.type == "human_decision" and e.data.get("kind") == "policy"]
    assert rec[-1].data["note"] == "Yes, I'll do those myself."


def test_a_person_the_owner_names_gets_a_profile_and_the_steps_for_a_person(tmp_path):
    api, recipe = _api(tmp_path)
    run = api.start(recipe, {"title": "Shed"})["run_id"]
    api.policy_set("Sam Lee will do the site visits.", person_steps="Sam Lee")
    sam = api.project.profiles()["person-sam-lee"]
    assert (sam.adapter, sam.person, sam.builtin_person()) == ("manual", "sam-lee", True)
    out = api.eligible(run, "survey")
    assert _names(out) == ["person-sam-lee"]
    reasons = {e["profile"]: e["reasons"] for e in out["excluded"]}
    assert any("Sam Lee does the steps for a person" in r for r in reasons["owner"])
    # Changing it back is the owner's words again; Sam's profile goes with the rule.
    api.policy_set("I'll do them after all.", person_steps="owner")
    assert "person-sam-lee" not in api.project.profiles() and _names(api.eligible(run, "survey")) == ["owner"]


def test_the_people_rule_is_written_to_project_yaml_and_a_policy_without_it_hashes_as_before(tmp_path):
    api, _ = _api(tmp_path)
    before = api.project.policy_state().sha256
    assert "people" not in api.project.policy_state().in_force  # absent until asked: older projects are not "edited"
    api.policy_set("Sam will.", person_steps="Sam")
    text = yaml.safe_load((api.project.baton / "project.yaml").read_text(encoding="utf-8"))
    assert text["policy"]["people"] == {"person_steps": "Sam"}
    st = api.project.policy_state()
    assert st.state == "recorded" and st.sha256 != before
    assert {r["key"]: r["value"] for r in policy.listing(st)["rules"]}["people.person_steps"] == "Sam"
    assert ProjectConfig.model_validate({"policy": {"people": {"person_steps": "Sam"}}}).policy.people.person_steps == "Sam"


def test_person_steps_needs_a_name(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(EngineError) as e:
        api.policy_set("Nobody.", person_steps="  ")
    assert e.value.code == "policy.invalid"


def test_the_cli_takes_person_steps(tmp_path):
    from projectkit import Cli, make_git_project

    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home", AI))
    cli.run("init", str(project))
    out = cli.run("policy", "set", "--person-steps", "owner", "--note", "Me.")
    assert out["policy"]["people"] == {"person_steps": "owner"}


def test_workers_status_shows_the_owners_profile_and_whether_it_is_replaced(tmp_path):
    from baton import resources

    home = make_home(tmp_path / "home", AI)
    assert resources.status(home, discover_fn=lambda h, d: {})["people"]["owner"]["builtin"] is True
    home2 = make_home(tmp_path / "home2", AI + "owner:\n  adapter: manual\n  creator: human\n  person: owner\n  capabilities: [human_judgment]\n")
    assert resources.status(home2, discover_fn=lambda h, d: {})["people"]["owner"]["builtin"] is False


def test_the_director_skill_asks_who_does_the_steps_for_a_person_once():
    from conftest import ROOT

    text = (ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8")
    assert "When `start` returns `people`" in text and "with yes as the default" in text
    assert "`policy set --person-steps owner --note" in text and "The answer is kept for the project, so don't ask again" in text
    assert "the owner keeps every decision" in text
