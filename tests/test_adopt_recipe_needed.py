"""`adopt` with no recipe starts nothing and says how to find or build one (Decision 0136)."""
from __future__ import annotations

import pytest

from conftest import ROOT
from projectkit import setup_fit_check


@pytest.mark.not_slow("one in-process CLI call")
def test_adopt_with_no_recipe_starts_nothing_and_names_the_procedure(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    before = sorted(p.name for p in (project / ".baton").iterdir())
    out = cli.run("adopt")
    assert out["state"] == "recipe_needed" and out["started"] is False
    joined = " ".join(out["steps"])
    assert "fit-check" in joined and "context" in joined and "recipe-builder" in joined and "stop" in joined
    assert "situation" in out and "adopt <recipe>" in out["next"]
    assert sorted(p.name for p in (project / ".baton").iterdir()) == before  # no run, no adoption folder


@pytest.mark.not_slow("one in-process CLI call")
def test_the_text_form_lists_the_steps(tmp_path):
    cli, _ = setup_fit_check(tmp_path)
    res = cli("adopt")
    assert "Adoption needs a recipe" in res.stdout or res.payload["state"] == "recipe_needed"


@pytest.mark.not_slow("reads two files")
def test_the_director_skill_and_its_design_copy_name_the_procedure():
    for text in ((ROOT / "skills" / "baton-director" / "SKILL.md").read_text(encoding="utf-8"),
                 (ROOT / "docs" / "design" / "director-interface.md").read_text(encoding="utf-8")):
        assert "recipe_needed" in text and "`context`" in text
