"""Owner-run assessment: a pinned fetched recipe, the runtime's own validator, the overlay (§6.4; Decisions 0111, 0120)."""

from __future__ import annotations

import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from baton import __version__, assess, listings, resources
from test_listings import OVERLAY, RAW, TODAY

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).resolve().parent / "fakes" / "assessment_worker.py"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_source(tmp_path, tag=None):
    """A repository holding the assessment recipe at ``tools/worker-research/assessment``, tagged ``v<version>``."""
    repo = tmp_path / "source"
    shutil.copytree(ROOT / "tools" / "worker-research" / "assessment", repo / "tools" / "worker-research" / "assessment")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "recipe")
    git(repo, "tag", tag or f"v{__version__}")
    return repo


def launcher(home, repo):
    (home / "launcher.yaml").write_text(f"source: 'git+{repo.as_uri()}@v{{version}}'\n", encoding="utf-8")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.mark.not_slow("a local clone, measured under 2 s")
def test_the_recipe_is_fetched_at_the_runtime_version_and_cached(home, tmp_path):
    repo = make_source(tmp_path)
    launcher(home, repo)
    calls = []

    def spy(cmd, **kw):
        calls.append(cmd)
        return subprocess.run(cmd, **kw)

    recipe = assess.fetch_recipe(home, run=spy)
    assert (recipe / "recipe.yaml").is_file() and recipe == home / "assessment" / __version__ / "recipe"
    assert calls and calls[0][calls[0].index("--branch") + 1] == f"v{__version__}"  # pinned: the runtime's own tag, never latest
    assess.fetch_recipe(home, run=lambda *a, **k: pytest.fail("a cached recipe is not fetched again"))


@pytest.mark.not_slow("a local clone, measured under 2 s")
def test_a_missing_tag_or_source_is_refused_in_plain_words(home, tmp_path):
    repo = make_source(tmp_path, tag="v0.0.0-other")
    launcher(home, repo)
    with pytest.raises(assess.AssessError) as e:
        assess.fetch_recipe(home)
    assert "write the overlay by hand" in str(e.value) and not (home / "assessment" / __version__ / ".fetched").exists()
    (home / "launcher.yaml").write_text("source: 'https://example.com/baton-{version}.tgz'\n", encoding="utf-8")
    with pytest.raises(assess.AssessError) as e2:
        assess.fetch_recipe(home)
    assert "not a git repository at a tag" in str(e2.value)


@pytest.mark.not_slow("measured under 1 s")
def test_the_runtimes_own_validator_checks_an_overlay_text():
    assert assess.check_overlay_text(OVERLAY) == []
    bad = assess.check_overlay_text(OVERLAY.replace("tier: standard", "tier: godlike"))
    assert any("godlike" in p for p in bad)
    assert any("not YAML" in p for p in assess.check_overlay_text("a: [unclosed"))


def setup_worker(home, tmp_path, overlay_text):
    declare = resources.declare
    declare(home, "or", provider="openrouter", credential="secret:or_key")
    listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    ov = tmp_path / "draft.yaml"
    ov.write_text(overlay_text, encoding="utf-8")
    line = shlex.join([sys.executable, str(FAKE), "{packet}", "{result}", str(ov), str(tmp_path / "dump.json")]) if os.name == "posix" else None
    (home / "workers.yaml").write_text(
        f"researcher:\n  adapter: command\n  creator: acme\n  command: {json.dumps(line)}\n"
        "  capabilities: [structured_output, web_access, file_write, technical_reasoning]\n  tier: strong\n", encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="the fake worker command line is POSIX-quoted")
@pytest.mark.slow
def test_assess_runs_the_fetched_recipe_validates_and_writes_the_overlay(home, tmp_path):
    launcher(home, make_source(tmp_path))
    setup_worker(home, tmp_path, OVERLAY)
    out = assess.assess(home, ["acme/big-2"], "researcher", today=TODAY)
    assert out["written"] == ["acme/big-2"] and out["assessed"][0]["tier"] == "standard"
    packet = json.loads((tmp_path / "dump.json").read_text(encoding="utf-8"))
    text = "\n".join(packet.values())
    assert "acme/big-2" in text and "check-overlay" in text and "openrouter: acme/big" in text  # the worker got the listing facts and the validator
    overlay = yaml.safe_load((home / "known-workers.local.yaml").read_text(encoding="utf-8"))
    assert overlay["models"]["acme/big-2"]["tier"] == "standard"
    assert json.loads((home / "assessments" / "2026-11-10.json").read_text(encoding="utf-8"))["requested"] == ["acme/big-2"]
    resources.setup(home, today=TODAY, discover_fn=lambda h, d: {})
    assert yaml.safe_load((home / "workers" / "or-acme-big.yaml").read_text(encoding="utf-8"))["tier"] == "standard"


@pytest.mark.skipif(os.name == "nt", reason="the fake worker command line is POSIX-quoted")
@pytest.mark.slow
def test_a_worker_overlay_the_validator_refuses_writes_nothing(home, tmp_path):
    launcher(home, make_source(tmp_path))
    setup_worker(home, tmp_path, OVERLAY.replace("tier: standard", "tier: godlike"))
    with pytest.raises(assess.AssessError) as e:
        assess.assess(home, ["acme/big-2"], "researcher", today=TODAY)
    assert "validator refused" in str(e.value) and "godlike" in str(e.value)
    assert not (home / "known-workers.local.yaml").exists()


@pytest.mark.not_slow("measured under 1 s")
def test_only_listed_unjudged_models_can_be_assessed(home, tmp_path):
    resources.declare(home, "or", provider="openrouter", credential="secret:or_key")
    listings.refresh(home, "openrouter", fetch=lambda url: RAW, today=TODAY)
    with pytest.raises(assess.AssessError) as e:
        assess.assess(home, ["acme/unknown"], "researcher", recipe_dir=tmp_path, today=TODAY)
    assert "no model list of yours offers acme/unknown" in str(e.value)
    with pytest.raises(assess.AssessError) as e2:
        assess.assess(home, ["anthropic/claude-opus-5-5"], "researcher", recipe_dir=tmp_path, today=TODAY)
    assert "already has a judgment" in str(e2.value)


@pytest.mark.not_slow("measured under 1 s")
def test_the_recipe_lints_clean():
    from baton.recipe import load_recipe

    loaded = load_recipe(ROOT / "tools" / "worker-research" / "assessment")
    assert [s.id for s in loaded.recipe.steps] == ["assess"]


@pytest.mark.not_slow("in-process CLI, measured under 1 s")
def test_check_overlay_command_accepts_and_refuses(tmp_path):
    from typer.testing import CliRunner

    from baton.cli import app

    ok, bad = tmp_path / "ok.yaml", tmp_path / "bad.yaml"
    ok.write_text(OVERLAY, encoding="utf-8")
    bad.write_text(OVERLAY.replace("tier: standard", "tier: godlike"), encoding="utf-8")
    r = CliRunner().invoke(app, ["workers", "check-overlay", str(ok)])
    assert r.exit_code == 0 and "accepted" in r.stdout
    r = CliRunner().invoke(app, ["workers", "check-overlay", str(bad)])
    assert r.exit_code == 1 and "godlike" in r.stdout and "refused" in r.stdout
