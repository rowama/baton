"""The `quick-run` recipe (change 2026-11-quick-runs, Slice 2; Decisions 0145, 0163; §5.7, §10.4):
one dispatch following a bound guide, one owner approval, and a result that later runs can bind."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton.project import catalog
from baton.recipe import load_recipe
from conftest import ROOT
from projectkit import OWNER_PROFILE, Cli, git, make_git_project, make_home, packet_dir, write_result

QUICK = ROOT / "examples" / "recipes" / "quick-run"
GUIDE = "guides/lean-business-plan.md"
PLAN = "# Water vending: lean plan\n\nCustomers: households near the market.\n"


@pytest.mark.not_slow("loads a recipe in process")
def test_quick_run_ships_with_one_step_and_its_roles():
    loaded = catalog()["quick-run"]
    r = loaded.recipe
    assert r.complexity is None  # no triage
    assert [s.id for s in r.steps] == ["produce"]
    (step,) = r.steps
    assert step.workspace == "none" and not step.depends_on
    assert [g.type for g in step.gates] == ["schema", "human"]  # no review gate
    assert [(a.name, a.required, a.media_type, a.publish.to) for a in step.artifacts] == [
        ("deliverable", True, "text/markdown", "{{ paths.documents }}/{{ run.slug }}.md")]
    roles = {p.role: p for p in r.project_inputs}
    assert roles["guide"].required is True and roles["guide"].many is False and roles["guide"].media_type == "text/markdown"
    assert roles["context"].required is False and roles["context"].many is True
    assert {i.name: (i.from_, i.required) for i in step.inputs} == {
        "title": ("run.inputs.title", True), "request": ("run.inputs.request", True),
        "guide": ("project.guide", True), "context": ("project.context", False)}
    assert load_recipe(QUICK).recipe.ref == "quick-run@1"
    assert r.defaults.max_attempts == 3  # attempts bounded as for any step


@pytest.mark.not_slow("pure function")
def test_paths_documents_defaults_to_docs_and_a_mapping_wins():
    from baton import publish

    recipe = catalog()["quick-run"].recipe
    assert publish.missing_path_keys(recipe, {}) == []
    assert publish.with_defaults({}) == {"documents": "docs"}
    assert publish.with_defaults({"documents": "plans", "specs": "s"}) == {"documents": "plans", "specs": "s"}


class Q:
    """A committed git project with quick-run vendored, an owner profile, and the lean business plan guide copied in."""

    def __init__(self, tmp_path: Path, paths: dict[str, str] | None = None):
        import yaml

        self.project = make_git_project(tmp_path / "proj")
        self.cli = Cli(self.project, make_home(tmp_path / "home", OWNER_PROFILE))
        self.cli.run("init", str(self.project), "--bare")
        self.cli.run("vendor", str(QUICK))
        if paths is not None:
            py = self.project / ".baton" / "project.yaml"
            cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
            cfg["paths"] = paths
            py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")
        self.cli.run("guides", "copy", "lean-business-plan", "--note", "Use the standard business plan guide.")

    def start(self, title: str, *binds: str) -> str:
        args = [a for b in binds for a in ("--bind", b)]
        inputs = {"title": title, "request": f"I need a {title.lower()} good enough to start on."}
        return self.cli.run("start", "quick-run", "--inputs", json.dumps(inputs), *args,
                            *(["--note", "Yes, use those."] if binds else []), expect=None)["run_id"]

    def produce(self, run: str, doc: str) -> tuple[Path, dict]:
        d = self.cli.run("dispatch", run, "produce", "--worker", "owner", expect=None)
        pdir = packet_dir(self.project, run, "produce", d["attempt"])
        art = pdir.parent / "result" / "artifacts" / "deliverable.md"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(doc, encoding="utf-8")
        write_result(pdir, {"summary": "A lean plan.", "checklist": [{"point": "Numbers have a basis", "met": True, "how": "Each is marked."}],
                            "assumptions": []}, artifacts=[{"name": "deliverable", "path": "artifacts/deliverable.md"}])
        return pdir, self.cli("submit", run, "produce", expect=None).payload

    def manifest(self, pdir: Path) -> dict:
        return json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.slow
def test_a_quick_run_follows_its_guide_and_its_approved_result_is_a_project_document(tmp_path):
    q = Q(tmp_path)  # no paths.documents mapped: the default, docs
    run = q.start("Business plan", f"guide={GUIDE}")
    pdir, sub = q.produce(run, "# Draft\n")
    names = {e["name"]: e for e in q.manifest(pdir)["inputs"]}
    assert set(names) == {"title", "request", "guide"} and "context" not in names  # optional and unbound: left out
    assert "## What good looks like" in (pdir / names["guide"]["path"]).read_text(encoding="utf-8")
    assert sub["needs_owner"] is True and not (q.project / "docs" / "business-plan.md").exists()

    rej = q.cli.run("decide", run, "produce", "reject", "--note", "Add the monthly numbers.", expect=None)
    assert rej["outcome"] == "retry" and rej["reasons"] == ["the owner did not approve: Add the monthly numbers."]
    pdir2, _ = q.produce(run, PLAN)
    fb = q.manifest(pdir2)["prior_feedback"]
    assert any("Add the monthly numbers." in r for r in fb["reasons"])

    done = q.cli.run("decide", run, "produce", "approve", "--note", "Good enough to start.")
    assert done["run_completed"] is True
    assert (q.project / "docs" / "business-plan.md").read_text(encoding="utf-8") == PLAN
    docs = {d["path"]: d for d in q.cli.run("documents")["documents"]}
    plan = docs["docs/business-plan.md"]
    assert plan["kind"] == "deliverable" and plan["source"]["run"] == run and plan["source"]["artifact"] == "deliverable"
    assert docs[GUIDE]["kind"] == "attested"

    # A later quick run builds on the plan: a marketing plan from a second guide, with the plan as context.
    q.cli.run("guides", "copy", "marketing-plan", "--note", "And the marketing one.")
    later = q.start("Marketing plan", "guide=guides/marketing-plan.md", "context=docs/business-plan.md")
    pdir3, _ = q.produce(later, "# Marketing\n")
    (ctx,) = [e for e in q.manifest(pdir3)["inputs"] if e["name"] == "context"]
    assert ctx["source"]["kind"] == "deliverable" and ctx["source"]["run"] == run and ctx["source"]["path"] == "docs/business-plan.md"
    assert (pdir3 / ctx["path"]).read_text(encoding="utf-8") == PLAN


@pytest.mark.slow
def test_a_quick_run_publishes_where_the_project_maps_documents_and_needs_its_guide(tmp_path):
    q = Q(tmp_path, paths={"documents": "plans", "process_plans": "docs", "notes": "docs"})
    run = q.start("Charter")
    res = q.cli("dispatch", run, "produce", "--worker", "owner", expect=1).payload
    assert res["error"] == "handoff.missing_inputs" and res["missing"][0]["from"] == "project.guide"
    q.cli.run("bind", run, "guide", GUIDE, "--note", "Use that guide.")
    q.produce(run, "# Charter\n")
    q.cli.run("decide", run, "produce", "approve", "--note", "Fine.")
    assert (q.project / "plans" / "charter.md").is_file()
