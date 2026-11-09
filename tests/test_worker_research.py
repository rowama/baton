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


def _setup(tmp_path: Path, proposal: dict, dump: Path | None = None) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    (repo / "defaults").mkdir(parents=True)
    shutil.copy(ROOT / "defaults" / "known-workers.yaml", repo / "defaults" / "known-workers.yaml")
    prop = tmp_path / "proposal.yaml"
    prop.write_text(yaml.safe_dump(proposal, sort_keys=False), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    line = _cmd([sys.executable, str(FAKE), "{packet}", "{result}", str(prop), *([str(dump)] if dump else [])])
    (home / "workers.yaml").write_text(
        f"researcher:\n  adapter: command\n  creator: acme\n  command: {json.dumps(line)}\n"
        "  capabilities: [structured_output, web_access, file_write, technical_reasoning]\n  tier: strong\n",
        encoding="utf-8")
    return repo, home, tmp_path / "reports"


def _seed() -> dict:
    """The shipped data, with every harness-creator model pinned on its harness (the shipped data predates the coverage check)."""
    raw = yaml.safe_load((ROOT / "defaults" / "known-workers.yaml").read_text(encoding="utf-8"))
    for pname, prov in raw["providers"].items():
        if prov["kind"] != "harness":
            continue
        have = {r["model_id"] for r in raw["routes"] if r["provider"] == pname and r.get("model_id")}
        for mid, m in raw["models"].items():
            if m["creator"] in prov["creators"] and mid not in have and not m.get("retired"):
                raw["routes"].append({"model_id": mid, "provider": pname, "adapter": prov_adapter(raw, pname),
                                      "invocation": mid.split("/", 1)[1], "supported": True})
    return raw


def prov_adapter(raw: dict, provider: str) -> str:
    return next(r["adapter"] for r in raw["routes"] if r["provider"] == provider)


@pytest.mark.slow
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
@pytest.mark.slow
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


@pytest.mark.not_slow("measured under 1 s")
def test_the_research_recipe_lints_clean():
    from baton.recipe import load_recipe

    loaded = load_recipe(_research().RECIPE)
    assert [s.id for s in loaded.recipe.steps] == ["research"]


@pytest.mark.slow
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



@pytest.mark.not_slow("measured under 1 s")
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


@pytest.mark.slow
def test_by_default_it_updates_the_checkout_it_was_installed_from(tmp_path):
    assert _research().default_checkout() == ROOT
    rc = subprocess.run([sys.executable, str(CLI), "--profile", "x", "--repo", str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 2 and "is not a Baton checkout" in rc.stderr


@pytest.mark.not_slow("measured under 1 s")
def test_an_unknown_profile_is_a_plain_usage_error(tmp_path, capsys):
    repo, home, reports = _setup(tmp_path, _seed())
    rc = _research().main(["--profile", "nope", "--home", str(home), "--repo", str(repo), "--reports", str(reports)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no worker profile 'nope'" in err and "baton workers status" in err and "Traceback" not in err


@pytest.mark.slow
def test_the_worker_gets_tool_maps_urls_litellm_entries_and_a_validator(tmp_path):
    dump = tmp_path / "dump.json"
    repo, home, reports = _setup(tmp_path, _seed(), dump)
    (repo / "tools" / "worker-research").mkdir(parents=True)
    (repo / "tools" / "worker-research" / "harness-docs.yaml").write_text("claude_code:\n  - https://example.org/cc\n", encoding="utf-8")
    rc = _research().main(["--profile", "researcher", "--home", str(home), "--repo", str(repo), "--reports", str(reports), "--today", "2026-11-08"])
    assert rc == 0
    text = "\n".join(json.loads(dump.read_text(encoding="utf-8")).values())
    for needle in ("tool_maps", "tooling_capabilities", "web_access", "https://example.org/cc", "supports_function_calling", "--check"):
        assert needle in text, needle
    report = (reports / "2026-11-08.md").read_text(encoding="utf-8")
    assert "LiteLLM model map: 1." in report


@pytest.mark.not_slow("measured under 1 s")
def test_litellm_entries_cover_every_api_route_and_name_the_version():
    version, entries = _research().litellm_entries(_seed())
    assert version and entries
    api = {r["invocation"] for r in _seed()["routes"] if r["adapter"] == "litellm_api" and r.get("invocation")}
    assert set(entries) == api
    assert all(set(e) <= {"supports_response_schema", "supports_function_calling", "supports_vision", "max_input_tokens"} for e in entries.values())
    assert any(entries.values())


@pytest.mark.not_slow("measured under 1 s")
def test_check_reports_what_the_tool_would_refuse(tmp_path, capsys):
    repo, _home, _reports = _setup(tmp_path, _seed())
    bad = _seed()
    bad["models"]["anthropic/claude-opus-5-5"]["capability_basis"].pop("vision")
    f = tmp_path / "p.yaml"
    f.write_text(yaml.safe_dump(bad, sort_keys=False), encoding="utf-8")
    assert _research().main(["--repo", str(repo), "--check", str(f)]) == 1
    out = capsys.readouterr().out
    assert "no basis" in out and out.rstrip().endswith("refused")
    f.write_text(yaml.safe_dump(_seed(), sort_keys=False), encoding="utf-8")
    assert _research().main(["--repo", str(repo), "--check", str(f)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("accepted")


@pytest.mark.slow
def test_the_validator_command_runs_as_the_worker_would_run_it(tmp_path):
    import shlex

    repo, _home, _reports = _setup(tmp_path, _seed())
    f = tmp_path / "p.yaml"
    f.write_text(yaml.safe_dump(_seed(), sort_keys=False), encoding="utf-8")
    proc = subprocess.run([*shlex.split(_research().validator_command(repo)), str(f)], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.strip() == "accepted"


@pytest.mark.not_slow("measured under 1 s")
def test_the_report_lists_each_harness(tmp_path):
    out = {"harnesses": [{"provider": "claude_code", "models_routed": ["anthropic/claude-haiku-5-5"],
                          "models_not_routed": [{"model_id": "anthropic/claude-x", "reason": "not documented"}],
                          "tools_proposed": ["web_access"], "widens_permissions": ["--allowedTools WebFetch reaches any URL"]}]}
    md = _research().report_markdown(out, "2026-11-08", "p", [], "1.2.3")
    for needle in ("## Harness: claude_code", "anthropic/claude-haiku-5-5", "Not routed: anthropic/claude-x: not documented", "Tools proposed: web_access", "Widens permissions", "LiteLLM model map: 1.2.3"):
        assert needle in md, needle


def _coverage(raw, output=None):
    return _research().coverage_problems(raw, output)


@pytest.mark.not_slow("measured under 1 s")
def test_a_model_of_a_harness_creator_needs_a_pinned_route_or_a_stated_gap():
    raw = _seed()
    assert _coverage(raw) == []
    raw["routes"] = [r for r in raw["routes"] if not (r["provider"] == "claude_code" and r.get("model_id") == "anthropic/claude-haiku-5-5")]
    (problem,) = _coverage(raw)
    assert "anthropic/claude-haiku-5-5" in problem and "claude_code" in problem
    # A gap must name the model; on that harness in models_not_routed, or inside a coverage-gaps line.
    assert _coverage(raw, {"harnesses": [{"provider": "claude_code", "models_not_routed": [{"model_id": "anthropic/claude-haiku-5-5", "reason": "not documented"}]}]}) == []
    assert _coverage(raw, {"coverage_gaps": ["anthropic/claude-haiku-5-5: the page was not readable"]}) == []
    assert _coverage(raw, {"harnesses": [{"provider": "codex", "models_not_routed": [{"model_id": "anthropic/claude-haiku-5-5", "reason": "x"}]}]}) != []
    assert _coverage(raw, {"coverage_gaps": ["haiku was skipped"]}) != []


@pytest.mark.not_slow("measured under 1 s")
def test_the_alias_route_is_not_a_pinned_route_and_retired_models_need_none():
    raw = _seed()
    raw["routes"] = [r for r in raw["routes"] if not (r["provider"] == "codex" and r.get("model_id"))]
    assert any("on codex" in p for p in _coverage(raw))   # only the default-model alias is left
    for m in raw["models"].values():
        m["retired"] = True
    assert _coverage(raw) == []


@pytest.mark.not_slow("measured under 1 s")
def test_any_harness_provider_is_covered_by_data_alone():
    raw = _seed()
    raw["providers"]["gemini_cli"] = {"kind": "harness", "creators": ["google"]}
    problems = _coverage(raw)
    assert problems and all("gemini_cli" in p for p in problems)


@pytest.mark.slow
def test_a_run_with_an_unrouted_model_is_refused(tmp_path):
    proposal = _seed()
    proposal["routes"] = [r for r in proposal["routes"] if not (r["provider"] == "claude_code" and r.get("model_id") == "anthropic/claude-haiku-5-5")]
    repo, home, reports = _setup(tmp_path, proposal)
    before = (repo / "defaults" / "known-workers.yaml").read_bytes()
    rc = _research().main(["--profile", "researcher", "--home", str(home), "--repo", str(repo), "--reports", str(reports), "--today", "2026-11-08"])
    assert rc == 1
    assert (repo / "defaults" / "known-workers.yaml").read_bytes() == before
    assert "anthropic/claude-haiku-5-5" in (reports / "2026-11-08.md").read_text(encoding="utf-8")
    assert (reports / "2026-11-08.refused-known-workers.yaml").is_file()
