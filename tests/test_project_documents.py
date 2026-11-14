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


# ---------------------------------------------------------------------------
# Slice 2: recipes declare roles
# ---------------------------------------------------------------------------

PLAN_ROLE = {"role": "business_plan", "description": "The business's settled plan: its constraints and target customers",
             "media_type": "text/markdown"}


def _role_recipe(root: Path, roles: list[dict] | None = None, ref: str = "project.business_plan", **top) -> Path:
    use = {"id": "market", "output_schema": "schemas/out.json", "inputs": [{"name": "plan", "from": ref, "required": True}]}
    return make_recipe(root, [use], schemas={"out.json": OBJ}, project_inputs=[PLAN_ROLE] if roles is None else roles, **top)


def _codes(root: Path) -> set[str]:
    from baton.recipe import validate_recipe

    _, issues = validate_recipe(root)
    return {i.code for i in issues if i.severity == "error"}


@pytest.mark.not_slow("loads a recipe in process")
def test_a_recipe_declares_roles_and_steps_reference_them(tmp_path):
    from baton.recipe import load_recipe

    r = load_recipe(_role_recipe(tmp_path / "r", [PLAN_ROLE, {"role": "policies", "description": "Policies the project follows", "many": True,
                                                                "required": False}])).recipe
    plan, policies = r.project_inputs
    assert (plan.role, plan.required, plan.many, plan.media_type) == ("business_plan", True, False, "text/markdown")  # required by default (0148)
    assert (policies.required, policies.many) == (False, True)
    assert r.role("policies") is policies and r.role("nope") is None


@pytest.mark.parametrize("roles, ref, code", [
    (None, "project.marketing_plan", "ref.unknown_role"),
    ([PLAN_ROLE, PLAN_ROLE], "project.business_plan", "project_inputs.duplicate_role"),
    ([{"role": "business_plan"}], "project.business_plan", "recipe.missing_key"),
    ([{**PLAN_ROLE, "role": "Business Plan"}], "project.business_plan", "recipe.invalid_value"),
    ([{**PLAN_ROLE, "kind": "plan"}], "project.business_plan", "recipe.unknown_key"),
    ([{**PLAN_ROLE, "role": "software_feature_design"}], "project.software_feature_design", "neutrality.role_names_recipe"),
    ([{**PLAN_ROLE, "description": "The plan that fit-check@4 wrote"}], "project.business_plan", "neutrality.role_names_recipe"),
    ([{**PLAN_ROLE, "description": "What steps.setup.artifacts.plan produced"}], "project.business_plan", "neutrality.role_names_recipe"),
    ([{**PLAN_ROLE, "description": "The design from the recipe-builder run"}], "project.business_plan", "neutrality.role_names_recipe"),
])
@pytest.mark.not_slow("loads a recipe in process")
def test_the_loader_refuses_bad_roles(tmp_path, roles, ref, code):
    assert code in _codes(_role_recipe(tmp_path / "r", roles, ref))


@pytest.mark.not_slow("loads a recipe in process")
def test_a_project_reference_needs_declared_roles(tmp_path):
    assert "ref.unknown_role" in _codes(_role_recipe(tmp_path / "r", [], "project.business_plan"))
    assert "ref.invalid" in _codes(_role_recipe(tmp_path / "s", None, "project.business-plan"))


@pytest.mark.not_slow("loads recipes in process")
def test_shipped_recipes_declare_no_roles_and_their_summaries_are_unchanged():
    from baton.frame import _summary
    from baton.project import builtin_recipe, catalog

    for loaded in [*catalog().values(), builtin_recipe("baton-frame@1"), builtin_recipe("baton-adopt@1")]:
        assert loaded.recipe.project_inputs == []
        assert "project_inputs" not in _summary(loaded, False, with_scope=True)


@pytest.mark.not_slow("loads a recipe in process")
def test_catalog_summaries_and_the_manual_show_a_recipes_roles(tmp_path):
    from baton.frame import _summary
    from baton.manual_gen import parts_table
    from baton.recipe import load_recipe

    root = _role_recipe(tmp_path / "r", [PLAN_ROLE, {"role": "policies", "description": "Policies the project follows", "many": True, "required": False}])
    s = _summary(load_recipe(root), True, with_scope=True)
    assert s["project_inputs"] == [{**PLAN_ROLE, "required": True, "many": False},
                                   {"role": "policies", "description": "Policies the project follows", "required": False, "many": True}]
    assert "project_inputs" not in _summary(load_recipe(root), True)  # framing's own inputs are unchanged (0148)
    table = parts_table(root, {})
    assert "It can build on documents your project already has." in table
    assert "| The business's settled plan: its constraints and target customers | yes | one |" in table
    assert "| Policies the project follows | if you have one | one or more |" in table


@pytest.mark.not_slow("in-process API over a bare project")
def test_recipes_lists_a_vendored_recipes_roles(tmp_path):
    p = _bare(tmp_path)
    p.cli.run("vendor", str(_role_recipe(tmp_path / "r")))
    (entry,) = p.cli.run("recipes")["recipes"]
    assert entry["project_inputs"] == [{**PLAN_ROLE, "required": True, "many": False}]


# ---------------------------------------------------------------------------
# Slice 3: binding and the packet
# ---------------------------------------------------------------------------

POLICIES_ROLE = {"role": "policies", "description": "Policies the project follows", "required": False, "many": True}


def _market(root: Path) -> Path:
    """brief (business plan, required; policies, optional, many) -> launch (business plan)."""
    brief = {"id": "brief", "output_schema": "schemas/out.json",
             "inputs": [{"name": "plan", "from": "project.business_plan", "required": True},
                        {"name": "policies", "from": "project.policies", "required": False}]}
    launch = {"id": "launch", "depends_on": ["brief"], "output_schema": "schemas/out.json",
              "inputs": [{"name": "plan", "from": "project.business_plan", "required": True}]}
    return make_recipe(root, [brief, launch], schemas={"out.json": OBJ}, id="market",
                       run_inputs={"type": "object", "properties": {"title": {"type": "string"}}}, project_inputs=[PLAN_ROLE, POLICIES_ROLE])


class M(P):
    """A project with the publisher and the market recipe, and attested documents."""

    def __init__(self, tmp_path: Path):
        super().__init__(tmp_path, [_publisher(tmp_path / "toy"), _market(tmp_path / "market")])

    def attest(self, rel: str, text: str, note: str = "Yes, that one.") -> dict:
        f = self.file(rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return self.cli.run("attest", rel, "--note", note)["document"]

    def manifest(self) -> dict:
        return json.loads((self.last_packet / "manifest.json").read_text(encoding="utf-8"))

    def dispatch(self, run: str, step: str, expect: int | None = None) -> dict:
        res = self.cli("dispatch", run, step, "--worker", "owner", expect=expect)
        if res.exit_code in (0, 4):
            self.last_packet = packet_dir(self.project, run, step, res.payload["attempt"])
        return res.payload

    def events(self, run: str) -> list[dict]:
        p = self.project / ".baton" / "runs" / run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]


def _entry(m: dict, name: str) -> list[dict]:
    return [i for i in m["inputs"] if i["name"] == name]


@pytest.mark.slow
def test_start_binds_a_role_and_the_packet_holds_the_bound_version_with_its_source(tmp_path):
    m = M(tmp_path)
    doc = m.attest("business/plan.md", "# Plan v1\n", "That's our settled plan.")
    out = m.cli.run("start", "market", "--inputs", json.dumps({"title": "Spring"}), "--bind", "business_plan=business/plan.md",
                    "--note", "Yes, use the business plan.")
    run = out["run_id"]
    (b,) = out["bound"]
    assert b["role"] == "business_plan" and b["documents"][0]["path"] == "business/plan.md"
    decision, bound = [e for e in m.events(run) if e["type"] in ("human_decision", "project_input_bound")]
    assert decision["data"]["kind"] == "bind" and decision["data"]["note"] == "Yes, use the business plan."
    d = bound["data"]
    assert d["role"] == "business_plan" and d["decision_id"] == decision["data"]["decision_id"] and d["many"] is False
    (bd,) = d["documents"]
    assert bd["path"] == "business/plan.md" and bd["sha256"] == doc["accepted_sha256"] and bd["edited_since_accepted"] is False
    assert bd["source"] == {"kind": "attested", "decision_id": doc["source"]["decision_id"]} and bd["version"] == 1
    st = m.cli.run("status", run, expect=None)
    assert st["project_inputs"][0]["bound"][0]["path"] == "business/plan.md" and st["waiting_on_binding"] == []
    assert st["project_inputs"][1] == {"role": "policies", "description": "Policies the project follows", "required": False, "many": True, "bound": None}

    m.file("business/plan.md").write_text("# Plan v2, not confirmed\n", encoding="utf-8")  # the living file moves on
    m.dispatch(run, "brief")
    man = m.manifest()
    (plan,) = _entry(man, "plan")
    assert (m.last_packet / plan["path"]).read_text(encoding="utf-8") == "# Plan v1\n"  # from the record, not the living file
    assert plan["path"] == "inputs/plan.md" and plan["sha256"] == doc["accepted_sha256"] and plan["from"] == "project.business_plan"
    assert plan["source"] == {"kind": "attested", "path": "business/plan.md", "version": 1, "decision_id": doc["source"]["decision_id"],
                              "bound_by": decision["data"]["decision_id"]}
    assert man["not_applicable"] == [{"name": "policies", "from": "project.policies", "reason": "no project document is bound to role 'policies'"}]
    text = (m.last_packet / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "This is the project document `business/plan.md` (version 1): a file the owner attested" in text


@pytest.mark.slow
def test_the_binding_changes_packet_sha256_as_any_input_does(tmp_path):
    from baton.packet import packet_digest

    m = M(tmp_path)
    m.attest("business/plan.md", "# Plan A\n")
    m.attest("business/other.md", "# Plan B\n")
    hashes = []
    for path in ("business/plan.md", "business/other.md"):
        run = m.cli.run("start", "market", "--inputs", json.dumps({"title": "Spring"}), "--bind", f"business_plan={path}", "--note", "Yes.")["run_id"]
        m.dispatch(run, "brief")
        man = m.manifest()
        hashes.append({i["name"]: i["sha256"] for i in man["inputs"]})
        files = {p.relative_to(m.last_packet).as_posix(): __import__("hashlib").sha256(p.read_bytes()).hexdigest()
                 for p in m.last_packet.rglob("*") if p.is_file() and p.name != "manifest.json"}
        assert packet_digest(man, files) == man["packet_sha256"]
    assert hashes[0]["plan"] != hashes[1]["plan"]


@pytest.mark.slow
def test_a_role_is_bound_later_and_an_unbound_required_role_refuses_the_dispatch(tmp_path):
    m = M(tmp_path)
    run = m.start("market", "Spring")
    st = m.cli.run("status", run, expect=None)
    assert st["waiting_on_binding"] == [{"step_path": "brief", "role": "business_plan", "description": PLAN_ROLE["description"]}]
    board = m.cli.run("board", expect=None)
    assert board["runs"][0]["waiting_on_binding"][0]["role"] == "business_plan"
    res = m.cli("dispatch", run, "brief", "--worker", "owner", expect=1)
    assert res.payload["error"] == "handoff.missing_inputs"
    assert res.payload["missing"] == [{"name": "plan", "from": "project.business_plan",
                                      "reason": "role 'business_plan' is not bound to a project document (the owner confirms one with `bind`)"}]
    assert not (m.project / ".baton" / "runs" / run / "steps" / "brief").exists() or not list((m.project / ".baton" / "runs" / run / "steps" / "brief").rglob("manifest.json"))

    m.attest("business/plan.md", "# Plan\n")
    out = m.cli.run("bind", run, "business_plan", "business/plan.md", "--note", "Use that plan.")
    assert out["documents"][0]["path"] == "business/plan.md" and out["checkpoint"]["committed"]
    assert m.cli.run("status", run, expect=None)["waiting_on_binding"] == []
    m.dispatch(run, "brief", expect=0)


@pytest.mark.slow
def test_a_many_role_takes_a_list_in_binding_order(tmp_path):
    m = M(tmp_path)
    m.attest("business/plan.md", "# Plan\n")
    m.attest("policy/refunds.md", "# Refunds\n")
    m.attest("policy/privacy.md", "# Privacy\n")
    run = m.cli.run("start", "market", "--inputs", json.dumps({"title": "Spring"}), "--bind", "business_plan=business/plan.md",
                    "--bind", "policies=policy/refunds.md", "--bind", "policies=policy/privacy.md", "--note", "Yes, those.")["run_id"]
    m.dispatch(run, "brief")
    pol = _entry(m.manifest(), "policies")
    assert [(p["path"], p["index"], p["source"]["path"]) for p in pol] == [
        ("inputs/policies/1.md", 1, "policy/refunds.md"), ("inputs/policies/2.md", 2, "policy/privacy.md")]
    assert (m.last_packet / "inputs/policies/2.md").read_text(encoding="utf-8") == "# Privacy\n"


@pytest.mark.slow
def test_binding_refusals(tmp_path):
    m = M(tmp_path)
    m.attest("business/plan.md", "# Plan\n")
    m.attest("business/notes.txt", "notes\n")
    (m.project / "loose.md").write_text("not a document\n", encoding="utf-8")
    run = m.start("market", "Spring")
    for args, code in [
        (["bind", run, "brand", "business/plan.md", "--note", "Yes."], "bind.unknown_role"),
        (["bind", run, "business_plan", "loose.md", "--note", "Yes."], "bind.not_a_document"),
        (["bind", run, "business_plan", "business/notes.txt", "--note", "Yes."], "bind.media_type"),
        (["bind", run, "business_plan", "business/plan.md", "business/plan.md", "--note", "Yes."], "bind.one_document"),
        (["bind", run, "business_plan", "business/plan.md", "--note", " "], "bind.note_required"),
    ]:
        assert m.cli(*args, expect=1).payload["error"] == code, args
    m.file("business/plan.md").unlink()
    assert m.cli("bind", run, "business_plan", "business/plan.md", "--note", "Yes.", expect=1).payload["error"] == "bind.deleted"
    assert not [e for e in m.events(run) if e["type"] == "project_input_bound"]
    before = set(p.name for p in (m.project / ".baton" / "runs").iterdir())
    res = m.cli("start", "market", "--inputs", json.dumps({"title": "X"}), "--bind", "business_plan=loose.md", "--note", "Yes.", expect=1)
    assert res.payload["error"] == "bind.not_a_document"
    assert set(p.name for p in (m.project / ".baton" / "runs").iterdir()) == before  # a refused binding starts nothing
    assert m.cli("start", "market", "--bind", "business_plan", "--note", "Yes.", expect=2).payload["error"] == "usage.bind"


@pytest.mark.slow
def test_binding_an_edited_deliverable_takes_the_living_file_and_says_so(tmp_path):
    m = M(tmp_path)
    setup = m.start("toy", "Plan")
    m.by_hand(setup, "draft", "# Plan as accepted\n")
    m.file("docs/out/plan-doc.md").write_text("# Plan as edited\n", encoding="utf-8")
    run = m.cli.run("start", "market", "--inputs", json.dumps({"title": "Spring"}), "--bind", "business_plan=docs/out/plan-doc.md",
                    "--note", "Yes, as I edited it.")["run_id"]
    (bd,) = [e for e in m.events(run) if e["type"] == "project_input_bound"][0]["data"]["documents"]
    assert bd["edited_since_accepted"] is True and bd["kind"] == "deliverable"
    assert bd["source"] == {"kind": "deliverable", "run": setup, "step": "draft", "artifact": "doc"}
    m.dispatch(run, "brief")
    (plan,) = _entry(m.manifest(), "plan")
    assert (m.last_packet / plan["path"]).read_text(encoding="utf-8") == "# Plan as edited\n"
    assert plan["source"]["edited_since_accepted"] is True and plan["media_type"] == "text/markdown"
    assert "edited since it was accepted" in (m.last_packet / "INSTRUCTIONS.md").read_text(encoding="utf-8")


@pytest.mark.slow
def test_a_fresh_clone_builds_the_packet_from_the_record(tmp_path):
    m = M(tmp_path)
    m.attest("business/plan.md", "# Plan v1\n")
    run = m.cli.run("start", "market", "--inputs", json.dumps({"title": "Spring"}), "--bind", "business_plan=business/plan.md",
                    "--note", "Yes.")["run_id"]
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(m.project), str(clone))
    (clone / "business").mkdir(exist_ok=True)  # the attested file itself is the owner's, not committed by Baton
    (clone / "business" / "plan.md").write_text("# Changed on the other machine\n", encoding="utf-8")
    other = Cli(clone, m.home)
    d = other.run("dispatch", run, "brief", "--worker", "owner", expect=None)
    pdir = packet_dir(clone, run, "brief", d["attempt"])
    (plan,) = _entry(json.loads((pdir / "manifest.json").read_text(encoding="utf-8")), "plan")
    assert (pdir / plan["path"]).read_text(encoding="utf-8") == "# Plan v1\n"


# ---------------------------------------------------------------------------
# Slice 4: upstream change and rebinding
# ---------------------------------------------------------------------------

ADS = {"type": "object", "properties": {"ads": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"},
                                                                                                         "text": {"type": "string"}}}}}}


def _campaign(root: Path) -> Path:
    """seed -> ads[foreach: write (plan) -> check];  brief (plan) -> launch;  side (independent)."""
    plan = {"name": "plan", "from": "project.business_plan", "required": True}
    steps = [
        {"id": "seed", "output_schema": "schemas/ads.json"},
        {"id": "ads", "depends_on": ["seed"], "foreach": "steps.seed.output.ads", "steps": [
            {"id": "write", "output_schema": "schemas/out.json", "inputs": [{"name": "ad", "from": "item"}, plan]},
            {"id": "check", "depends_on": ["write"], "output_schema": "schemas/out.json"},
        ]},
        {"id": "brief", "output_schema": "schemas/out.json", "inputs": [plan]},
        {"id": "launch", "depends_on": ["brief"], "output_schema": "schemas/out.json"},
        {"id": "side", "output_schema": "schemas/out.json"},
    ]
    make_recipe(root, steps, schemas={"out.json": OBJ, "ads.json": ADS}, id="campaign",
                run_inputs={"type": "object", "properties": {"title": {"type": "string"}}}, project_inputs=[PLAN_ROLE])
    doc = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
    group = doc["steps"][1]
    group.pop("requires"), group.pop("prompt")
    for s in group["steps"]:
        s.update(requires={"capabilities": ["structured_output"]}, prompt=f"prompts/{s['id']}.md")
        (root / s["prompt"]).write_text(f"Do the {s['id']} step.\n", encoding="utf-8")
    (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


def _triaged(root: Path) -> Path:
    triage = {"type": "object", "required": ["level"], "properties": {"level": {"enum": ["small", "large"]}}}
    steps = [
        {"id": "triage", "output_schema": "schemas/triage.json", "gates": [{"type": "schema"}],
         "inputs": [{"name": "plan", "from": "project.business_plan", "required": True}]},
        {"id": "after", "depends_on": ["triage"], "output_schema": "schemas/out.json"},
    ]
    return make_recipe(root, steps, schemas={"out.json": OBJ, "triage.json": triage}, id="sized", project_inputs=[PLAN_ROLE],
                       run_inputs={"type": "object", "properties": {"title": {"type": "string"}}},
                       complexity={"levels": ["small", "large"], "triage_step": "triage"})


class R(M):
    def __init__(self, tmp_path: Path):
        P.__init__(self, tmp_path, [_publisher(tmp_path / "toy"), _market(tmp_path / "market"), _campaign(tmp_path / "campaign"),
                                    _triaged(tmp_path / "sized")])

    def do(self, run: str, step: str, output: dict | None = None, expect: int | None = None) -> dict:
        self.dispatch(run, step)
        write_result(self.last_packet, output or {})
        return self.cli("submit", run, step, expect=expect).payload

    def ready(self, run: str) -> list[str]:
        return self.cli.run("status", run, expect=None)["ready"]

    def states(self, run: str) -> dict[str, str]:
        from baton.store import Store

        s = Store(self.project)
        try:
            return {p: st.state for p, st in s.run(run).state().steps.items()}
        finally:
            s.close()


def _bound_market(r: R, path: str = "business/plan.md") -> str:
    return r.cli.run("start", "market", "--inputs", json.dumps({"title": "Spring"}), "--bind", f"business_plan={path}",
                     "--note", "Yes, that plan.")["run_id"]


@pytest.mark.slow
def test_an_edit_and_a_newer_attestation_are_reported_never_propagated(tmp_path):
    r = R(tmp_path)
    r.attest("business/plan.md", "# Plan v1\n")
    run = _bound_market(r)
    assert r.cli.run("status", run, expect=None)["upstream_changes"] == []
    r.file("business/plan.md").write_text("# Plan, edited\n", encoding="utf-8")
    (u,) = r.cli.run("status", run, expect=None)["upstream_changes"]
    assert (u["role"], u["path"], u["change"], u["bound_version"], u["current_version"]) == ("business_plan", "business/plan.md", "edited", 1, 1)
    assert u["current_sha256"] != u["bound_sha256"] and u["run"] == run
    r.cli.run("attest", "business/plan.md", "--note", "The edited plan stands.")
    (u,) = r.cli.run("status", run, expect=None)["upstream_changes"]
    assert (u["change"], u["current_version"]) == ("newer_version", 2)
    (b,) = r.cli.run("board", expect=None)["runs"]
    assert b["upstream_changes"][0]["change"] == "newer_version"
    issues = r.cli.run("check", "--strict", expect=None)
    found = [i for i in issues["issues"] if i["code"] == "document.upstream_changed"]
    assert len(found) == 1 and found[0]["severity"] == "warning" and found[0]["where"] == "business/plan.md"

    r.do(run, "brief")  # nothing is stale or held: the run carries on with the version it bound, and completes
    (plan,) = _entry(r.manifest(), "plan")
    assert (r.last_packet / plan["path"]).read_text(encoding="utf-8") == "# Plan v1\n"
    out = r.do(run, "launch")
    assert out["run_completed"] is True
    assert not [e for e in r.events(run) if e["type"] == "step_stale"]
    assert r.cli.run("status", run, expect=None)["upstream_changes"] == []  # a finished run reports nothing


@pytest.mark.slow
def test_a_newer_publication_and_a_deletion_are_reported(tmp_path):
    r = R(tmp_path)
    first = r.start("toy", "Plan")
    r.by_hand(first, "draft", "# Plan v1\n")
    run = _bound_market(r, "docs/out/plan-doc.md")
    again = r.start("toy", "Plan")
    r.by_hand(again, "draft", "# Plan v2\n", expect=None)  # another run's file: a conflict the owner settles
    r.cli.run("decide", again, "publish:draft.doc", "overwrite", "--note", "Replace it.", expect=None)
    (u,) = r.cli.run("status", run, expect=None)["upstream_changes"]
    assert (u["change"], u["bound_version"], u["current_version"]) == ("newer_version", 1, 2)
    other = _bound_market(r, "docs/out/plan-doc.md")
    r.file("docs/out/plan-doc.md").unlink()
    (u,) = r.cli.run("status", other, expect=None)["upstream_changes"]
    assert u["change"] == "deleted" and u["current_sha256"] is None


@pytest.mark.slow
def test_rebinding_stales_exactly_the_consumers_and_their_dependents_in_that_run_only(tmp_path):
    r = R(tmp_path)
    r.attest("business/plan.md", "# Plan v1\n")
    r.attest("business/plan-v2.md", "# Plan v2\n")
    start = lambda: r.cli.run("start", "campaign", "--inputs", json.dumps({"title": "Fall"}), "--bind", "business_plan=business/plan.md",
                              "--note", "Yes.")["run_id"]
    run, bystander = start(), start()
    r.do(run, "seed", {"ads": [{"text": "one"}, {"text": "two"}]})
    for _ in range(10):
        ready = [p for p in r.ready(run) if p not in ("side",)]
        if not ready:
            break
        for p in ready:
            r.do(run, p)
    states = r.states(run)  # `side` stays ready, so the run is still active
    assert states["side"] == "ready" and {s for p, s in states.items() if p != "side"} == {"passed"}
    r.do(bystander, "brief")
    before = r.states(bystander)

    assert r.cli("bind", run, "business_plan", "business/plan-v2.md", "--note", "  ", expect=1).payload["error"] == "bind.note_required"
    out = r.cli.run("bind", run, "business_plan", "business/plan-v2.md", "--note", "Use the new plan.")
    assert out["rebound"] is True
    paths = r.states(run)
    instance_paths = sorted(p for p in paths if p.startswith("ads/"))
    assert len(instance_paths) == 4  # two instances, write and check each
    assert sorted(out["stale"]) == sorted(["brief", "launch", *instance_paths])
    states = r.states(run)
    assert all(states[p] == "stale" for p in out["stale"]) and states["seed"] == "passed" and states["side"] == "ready"
    st = [e for e in r.events(run) if e["type"] == "step_stale"]
    assert {e["data"]["cause"] for e in st} == {"rebound"} and {e["data"]["role"] for e in st} == {"business_plan"}
    assert r.states(bystander) == before  # another run bound to the same document is untouched

    r.dispatch(run, "brief")  # a stale consumer re-runs with the new binding
    (plan,) = _entry(r.manifest(), "plan")
    assert (r.last_packet / plan["path"]).read_text(encoding="utf-8") == "# Plan v2\n"
    res = r.cli("bind", run, "business_plan", "business/plan.md", "--note", "Back to v1.", expect=1)  # brief is in flight
    assert res.payload["error"] == "bind.in_flight" and "brief" in res.payload["message"]


@pytest.mark.slow
def test_a_role_triage_used_is_rebound_after_retriage(tmp_path):
    r = R(tmp_path)
    r.attest("business/plan.md", "# Plan v1\n")
    r.attest("business/plan-v2.md", "# Plan v2\n")
    run = r.cli.run("start", "sized", "--inputs", json.dumps({"title": "Fall"}), "--bind", "business_plan=business/plan.md",
                    "--note", "Yes.")["run_id"]
    r.do(run, "triage", {"level": "small"})
    res = r.cli("bind", run, "business_plan", "business/plan-v2.md", "--note", "Use v2.", expect=1)
    assert res.payload["error"] == "bind.triage" and "retriage" in res.payload["message"]
    r.cli.run("retriage", run, "--reason", "The plan changed.", expect=None)
    out = r.cli.run("bind", run, "business_plan", "business/plan-v2.md", "--note", "Use v2.")
    assert out["rebound"] is True and out["stale"] == []
    r.dispatch(run, "triage")
    (plan,) = _entry(r.manifest(), "plan")
    assert (r.last_packet / plan["path"]).read_text(encoding="utf-8") == "# Plan v2\n"


# ---------------------------------------------------------------------------
# Slice 5: end to end, and the records
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_one_process_builds_on_what_another_settled_end_to_end(tmp_path):
    """A setup run publishes a plan; a marketing run binds it; the plan is edited; the run reports it; the owner rebinds."""
    r = R(tmp_path)
    setup = r.start("toy", "Plan")
    r.by_hand(setup, "draft", "# Business plan\n\nTarget: offices.\n")
    assert r.cli.run("status", setup, expect=None)["state"] == "completed"
    (doc,) = r.cli.run("documents")["documents"]
    assert doc["path"] == "docs/out/plan-doc.md" and doc["kind"] == "deliverable"

    run = _bound_market(r, doc["path"])
    r.do(run, "brief")
    text = r.cli.run("record", run, "brief")["record"]
    assert "project document `docs/out/plan-doc.md` version 1, published by `draft.doc` of run `" + setup + "`" in text

    r.file("docs/out/plan-doc.md").write_text("# Business plan\n\nTarget: offices and gyms.\n", encoding="utf-8")
    (u,) = r.cli.run("status", run, expect=None)["upstream_changes"]
    assert u["change"] == "edited" and u["role"] == "business_plan"
    out = r.cli.run("bind", run, "business_plan", doc["path"], "--note", "Use the plan as I edited it.")
    assert out["rebound"] and out["stale"] == ["brief"] and out["documents"][0]["edited_since_accepted"] is True
    assert r.cli.run("status", run, expect=None)["upstream_changes"] == []
    r.do(run, "brief")
    (plan,) = _entry(r.manifest(), "plan")
    assert "gyms" in (r.last_packet / plan["path"]).read_text(encoding="utf-8")
    assert r.do(run, "launch")["run_completed"] is True

    stext = r.cli.run("summary", run)["summary"]
    assert "## Project documents" in stext and "bound 2 times" in stext and "edited since accepted" in stext
    assert "Use the plan as I edited it." in stext and "owner bound `business_plan`" in stext and "`business_plan` was rebound" in stext
