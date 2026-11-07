"""The maintainer research utility and the installation boundary (0074, 0080, 0083)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).resolve().parent / "fakes" / "research_worker.py"
PKG = ROOT / "tools" / "worker-research"
CLI = PKG / "src" / "baton_worker_research" / "cli.py"


def _research():
    spec = importlib.util.spec_from_file_location("worker_research", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cmd(argv):
    import shlex

    return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)


def _setup(tmp_path: Path, proposal: dict) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    (repo / "defaults").mkdir(parents=True)
    shutil.copy(ROOT / "defaults" / "known-workers.yaml", repo / "defaults" / "known-workers.yaml")
    prop = tmp_path / "proposal.yaml"
    prop.write_text(yaml.safe_dump(proposal, sort_keys=False), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    line = _cmd([sys.executable, str(FAKE), "{packet}", "{result}", str(prop)])
    (home / "workers.yaml").write_text(
        f"researcher:\n  adapter: command\n  creator: acme\n  command: {json.dumps(line)}\n"
        "  capabilities: [structured_output, web_access, file_write, technical_reasoning]\n  tier: strong\n",
        encoding="utf-8")
    return repo, home, tmp_path / "reports"


def _seed() -> dict:
    return yaml.safe_load((ROOT / "defaults" / "known-workers.yaml").read_text(encoding="utf-8"))


def test_a_valid_proposal_replaces_the_file_with_a_report(tmp_path):
    proposal = _seed()
    proposal["models"]["acme/one"] = {"creator": "acme", "category": "llm", "researched": "2026-11-06",
                                      "sources": [{"url": "https://example.org/m", "retrieved": "2026-11-06"}]}
    repo, home, reports = _setup(tmp_path, proposal)
    rc = _research().main(["--profile", "researcher", "--home", str(home), "--repo", str(repo), "--reports", str(reports), "--today", "2026-11-06"])
    assert rc == 0
    written = yaml.safe_load((repo / "defaults" / "known-workers.yaml").read_text(encoding="utf-8"))
    assert "acme/one" in written["models"]
    report = (reports / "2026-11-06.md").read_text(encoding="utf-8")
    assert "## Coverage gaps" in report and "open-weight models not covered" in report and "Refused" not in report


@pytest.mark.parametrize("bad", ["invalid", "verified"])
def test_a_refused_proposal_leaves_the_repository_alone(tmp_path, bad):
    proposal = _seed()
    if bad == "invalid":
        proposal["models"]["anthropic/claude-opus-5-5"]["capabilities"].append("telepathy")
    else:  # research claiming a live check it did not do
        proposal["routes"][0]["verified"] = {"date": "2026-11-06", "tool": "litellm", "version": "1.106.6"}
    repo, home, reports = _setup(tmp_path, proposal)
    before = (repo / "defaults" / "known-workers.yaml").read_bytes()
    rc = _research().main(["--profile", "researcher", "--home", str(home), "--repo", str(repo), "--reports", str(reports), "--today", "2026-11-06"])
    assert rc == 1
    assert (repo / "defaults" / "known-workers.yaml").read_bytes() == before
    assert "Refused" in (reports / "2026-11-06.md").read_text(encoding="utf-8")
    assert (reports / "2026-11-06.refused-known-workers.yaml").is_file()
    if bad == "verified":
        assert "may not add or change verified" in (reports / "2026-11-06.md").read_text(encoding="utf-8")


def test_the_research_recipe_lints_clean():
    from baton.recipe import load_recipe

    loaded = load_recipe(_research().RECIPE)
    assert [s.id for s in loaded.recipe.steps] == ["research"]


def test_the_built_wheel_ships_the_data_and_not_the_researcher(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    proc = subprocess.run([uv, "build", "--wheel", "--offline", "-o", str(tmp_path), str(ROOT)], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        pytest.skip(f"cannot build a wheel offline here: {proc.stderr.strip()[-200:]}")
    names = zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist()
    assert "baton/_data/defaults/known-workers.yaml" in names
    assert not any("worker-research" in n or n.startswith("tools/") for n in names)



def test_the_researcher_is_its_own_package_with_a_command(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    proc = subprocess.run([uv, "build", "--wheel", "--offline", "-o", str(tmp_path), str(PKG)], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        pytest.skip(f"cannot build a wheel offline here: {proc.stderr.strip()[-200:]}")
    whl = zipfile.ZipFile(next(tmp_path.glob("baton_worker_research-*.whl")))
    names = whl.namelist()
    assert "baton_worker_research/recipe/recipe.yaml" in names
    assert "baton_worker_research/recipe/schemas/report.json" in names
    entry_points = next(n for n in names if n.endswith("entry_points.txt"))
    assert "baton-worker-research = baton_worker_research.cli:main" in whl.read(entry_points).decode()
    metadata = whl.read(next(n for n in names if n.endswith("METADATA"))).decode()
    assert "Requires-Dist: baton" in metadata


def test_by_default_it_updates_the_checkout_it_was_installed_from(tmp_path):
    assert _research().default_checkout() == ROOT
    rc = subprocess.run([sys.executable, str(CLI), "--profile", "x", "--repo", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 2 and "is not a Baton checkout" in rc.stderr
