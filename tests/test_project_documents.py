"""Project documents: listing, attestation, roles, binding, upstream change and rebinding
(change 2026-11-project-documents; Decisions 0142, 0146; §5.2, §8.6, §10.4)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from baton.mcp_server import build_server
from projectkit import OWNER_PROFILE, Cli, git, make_git_project, make_home, packet_dir, write_result
from runkit import make_recipe

OBJ = {"type": "object"}
TARGET = "{{ paths.docs }}/{{ run.slug }}-doc.md"


def _publisher(root: Path) -> Path:
    """One step that publishes `doc` at docs/out/<slug>-doc.md."""
    draft = {"id": "draft", "output_schema": "schemas/out.json",
             "artifacts": [{"name": "doc", "required": True, "media_type": "text/markdown", "publish": {"to": TARGET}}]}
    return make_recipe(root, [draft], schemas={"out.json": OBJ}, run_inputs={"type": "object", "properties": {"title": {"type": "string"}}})


class P:
    """A committed git project with a publishing recipe vendored and an owner profile."""

    def __init__(self, tmp_path: Path, recipes: list[Path] | None = None):
        self.tmp = tmp_path
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home", OWNER_PROFILE)
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project), "--bare")
        for r in recipes if recipes is not None else [_publisher(tmp_path / "toy")]:
            self.cli.run("vendor", str(r))
        py = self.project / ".baton" / "project.yaml"
        cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
        cfg["paths"] = {"docs": "docs/out"}
        py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")

    def start(self, recipe: str = "toy", title: str = "Login", *extra: str) -> str:
        return self.cli.run("start", recipe, "--inputs", json.dumps({"title": title}), *extra, expect=None)["run_id"]

    def by_hand(self, run: str, step: str, doc: str | None = None, expect: int | None = None) -> dict:
        d = self.cli.run("dispatch", run, step, "--worker", "owner", expect=None)
        pdir = packet_dir(self.project, run, step, d["attempt"])
        extra = {}
        if doc is not None:
            (pdir.parent / "result" / "artifacts").mkdir(parents=True, exist_ok=True)
            (pdir.parent / "result" / "artifacts" / "doc.md").write_text(doc, encoding="utf-8")
            extra["artifacts"] = [{"name": "doc", "path": "artifacts/doc.md"}]
        write_result(pdir, {}, **extra)
        self.last_packet = pdir
        return self.cli("submit", run, step, expect=expect).payload

    def docs(self) -> dict[str, dict]:
        return {d["path"]: d for d in self.cli.run("documents")["documents"]}

    def file(self, rel: str) -> Path:
        return self.project / rel

    def project_events(self) -> list[dict]:
        f = self.project / ".baton" / "project" / "events.jsonl"
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


# ---------------------------------------------------------------------------
# Slice 1: listing and attestation
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_documents_lists_every_runs_published_deliverables_with_their_state(tmp_path):
    p = P(tmp_path)
    assert p.docs() == {}
    login = p.start(title="Login")
    p.by_hand(login, "draft", "# Login v1\n")
    signup = p.start(title="Signup")
    p.by_hand(signup, "draft", "# Signup\n")
    docs = p.docs()
    assert set(docs) == {"docs/out/login-doc.md", "docs/out/signup-doc.md"}
    d = docs["docs/out/login-doc.md"]
    assert d["kind"] == "deliverable" and d["state"] == "unchanged" and d["version"] == 1 and d["media_type"] == "text/markdown"
    assert d["source"] == {"kind": "deliverable", "run": login, "step": "draft", "artifact": "doc"}
    assert d["sha256"] == d["accepted_sha256"] and d["accepted_at"]

    p.file("docs/out/signup-doc.md").write_text("# Signup, edited\n", encoding="utf-8")
    p.file("docs/out/login-doc.md").unlink()
    docs = p.docs()
    assert docs["docs/out/signup-doc.md"]["state"] == "edited"
    assert docs["docs/out/signup-doc.md"]["sha256"] != docs["docs/out/signup-doc.md"]["accepted_sha256"]
    assert docs["docs/out/login-doc.md"]["state"] == "deleted" and docs["docs/out/login-doc.md"]["sha256"] is None

    again = p.start(title="Login")  # a later run publishes at the same path: a newer version of the same document
    p.by_hand(again, "draft", "# Login v2\n")
    d = p.docs()["docs/out/login-doc.md"]
    assert d["version"] == 2 and d["state"] == "unchanged" and d["source"]["run"] == again


@pytest.mark.slow
def test_a_deliverable_is_a_document_once_its_step_is_accepted_not_before(tmp_path):
    two = make_recipe(tmp_path / "two", [
        {"id": "draft", "output_schema": "schemas/out.json",
         "artifacts": [{"name": "doc", "required": True, "media_type": "text/markdown", "publish": {"to": TARGET}}],
         "gates": [{"type": "human", "prompt": "Is the document right?"}]},
        {"id": "after", "depends_on": ["draft"], "output_schema": "schemas/out.json"},
    ], schemas={"out.json": OBJ}, run_inputs={"type": "object", "properties": {"title": {"type": "string"}}}, id="two")
    p = P(tmp_path, [two])
    run = p.start("two", "Plan")
    p.by_hand(run, "draft", "# Plan\n", expect=4)  # waiting on the owner's approval: not accepted yet
    assert p.docs() == {}
    p.cli.run("decide", run, "draft", "approve", "--note", "Looks right.", expect=None)
    assert list(p.docs()) == ["docs/out/plan-doc.md"]  # accepted and published, though the run has not completed


@pytest.mark.slow
def test_the_owner_attests_a_file_and_again_for_a_newer_version(tmp_path):
    p = P(tmp_path)
    plan = p.file("business/plan.md")
    plan.parent.mkdir(parents=True)
    plan.write_text("# Business plan\n", encoding="utf-8")
    git(p.project, "add", "-A")
    git(p.project, "commit", "-qm", "plan")
    out = p.cli.run("attest", "business/plan.md", "--note", "That's our settled plan.")
    d = out["document"]
    assert d["path"] == "business/plan.md" and d["kind"] == "attested" and d["version"] == 1 and d["state"] == "unchanged"
    assert d["source"] == {"kind": "attested", "decision_id": out["decision_id"], "note": "That's our settled plan."}
    assert d["media_type"] == "text/markdown"
    sha = d["accepted_sha256"]
    cas = p.project / ".baton" / "project" / "cas" / sha[:2] / sha
    assert cas.read_text(encoding="utf-8") == "# Business plan\n"
    decision, attested = [e for e in p.project_events() if e["type"] in ("human_decision", "document_attested")]
    assert decision["data"]["kind"] == "attest" and decision["data"]["note"] == "That's our settled plan." and decision["actor"] == "human"
    assert attested["data"]["path"] == "business/plan.md" and attested["data"]["sha256"] == sha
    assert attested["data"]["decision_id"] == decision["data"]["decision_id"]
    assert out["checkpoint"]["committed"]
    assert f".baton/project/cas/{sha[:2]}/{sha}" in git(p.project, "show", "--name-only", "--format=", "HEAD").split()
    assert p.docs()["business/plan.md"] == d

    plan.write_text("# Business plan, revised\n", encoding="utf-8")
    assert p.docs()["business/plan.md"]["state"] == "edited"
    again = p.cli.run("attest", str(plan), "--note", "The revised plan stands.")  # an absolute path inside the project
    assert again["document"]["version"] == 2 and again["document"]["state"] == "unchanged" and again["previous_version"] == 1


@pytest.mark.parametrize("path, code", [
    ("../outside.md", "document.bad_path"),
    (".git/config", "document.bad_path"),
    (".baton/project.yaml", "document.bad_path"),
    ("nowhere.md", "attest.no_file"),
    ("business", "attest.no_file"),
])
@pytest.mark.not_slow("in-process CLI, no commits")
def test_attest_refuses_paths_that_are_not_project_files(tmp_path, path, code):
    p = _bare(tmp_path)
    (p.project / "business").mkdir()
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    res = p.cli("attest", path, "--note", "Yes.", expect=1)
    assert res.payload["error"] == code
    assert not p.project_events() or not any(e["type"] == "document_attested" for e in p.project_events())


@pytest.mark.not_slow("in-process CLI, no commits")
def test_attest_needs_the_owners_words(tmp_path):
    p = _bare(tmp_path)
    (p.project / "plan.md").write_text("x", encoding="utf-8")
    assert p.cli("attest", "plan.md", "--note", "  ", expect=1).payload["error"] == "attest.note_required"


class _Bare:
    def __init__(self, project: Path, cli: Cli):
        self.project, self.cli = project, cli

    def project_events(self) -> list[dict]:
        f = self.project / ".baton" / "project" / "events.jsonl"
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def _bare(tmp_path: Path) -> _Bare:
    project = make_git_project(tmp_path / "proj")
    cli = Cli(project, make_home(tmp_path / "home"))
    cli.run("init", str(project), "--bare")
    return _Bare(project, cli)


@pytest.mark.slow
def test_cli_mcp_and_api_list_the_same_documents(tmp_path, monkeypatch):
    from mcp import Client

    from baton.engine import Api

    p = P(tmp_path)
    run = p.start(title="Login")
    p.by_hand(run, "draft", "# Login\n")
    (p.project / "terms.md").write_text("Terms\n", encoding="utf-8")
    p.cli.run("attest", "terms.md", "--note", "These are our terms.")
    monkeypatch.setenv("BATON_HOME", str(p.home))

    async def main():
        async with Client(build_server(p.project, "bob@host2")) as c:
            return (await c.call_tool("documents", {})).structured_content

    via_mcp = asyncio.run(main())
    api = Api.open(p.project, home=p.home)
    try:
        via_api = api.documents()
    finally:
        api.close()
    via_cli = p.cli.run("documents")
    assert len(via_cli["documents"]) == 2
    assert via_mcp["documents"] == via_cli["documents"] == via_api["documents"]
