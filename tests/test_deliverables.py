"""Phase 13: deliverables (L8, §10.4, §10.5).

Acceptance: deliverables appear at mapped paths; a pre-existing file is never
silently overwritten; editing a published file triggers drift, and ingesting
it feeds a later step. Plus the owner decisions of 2026-11-03: conflict
choices (overwrite / keep / alternate), who may be overwritten silently, drift
left or ingested, revisions fed to not-yet-started dependents, possibly-stale
flags, completion held, ``check --strict``, ``detect``, and an expert's answer
promoted as a revision.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from baton.recipe import RecipeError, load_recipe
from projectkit import OWNER_PROFILE, Cli, git, make_git_project, make_home, packet_dir, write_result
from runkit import make_recipe

FAKES = Path(__file__).resolve().parent / "fakes"
OBJ = {"type": "object"}
TARGET = "{{ paths.docs }}/{{ run.slug }}-doc.md"


def _recipe(root: Path, *, in_group: bool = False) -> Path:
    """draft (publishes `doc`) -> review (doc + optional human revision) -> final (doc)."""
    draft = {"id": "draft", "output_schema": "schemas/out.json",
             "artifacts": [{"name": "doc", "required": True, "media_type": "text/markdown", "publish": {"to": TARGET}}]}
    review = {"id": "review", "depends_on": ["draft"], "output_schema": "schemas/out.json",
              "inputs": [{"name": "doc", "from": "steps.draft.artifacts.doc", "required": True},
                         {"name": "edited", "from": "human_revision.draft.doc", "required": False}]}
    final = {"id": "final", "depends_on": ["review"], "output_schema": "schemas/out.json",
             "inputs": [{"name": "doc", "from": "steps.draft.artifacts.doc", "required": True}]}
    steps: list[dict] = [draft] if in_group else [draft, review, final]
    root = make_recipe(root, steps, schemas={"out.json": OBJ}, run_inputs={"type": "object", "properties": {"title": {"type": "string"}}})
    if in_group:
        doc = yaml.safe_load((root / "recipe.yaml").read_text(encoding="utf-8"))
        doc["steps"] = [{"id": "parts", "steps": doc["steps"]}]
        (root / "recipe.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


def _cmdline(argv: list[str]) -> str:
    return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)


class P:
    def __init__(self, tmp_path: Path, *, paths: dict | None = None, sme: bool = False):
        self.tmp = tmp_path
        profiles = OWNER_PROFILE
        self.sme_behavior = tmp_path / "sme.json"
        if sme:
            argv = [sys.executable, str(FAKES / "fake_sme.py"), "{packet}", "{result}", str(self.sme_behavior)]
            profiles += f"sage:\n  adapter: command\n  vendor: other\n  command: {json.dumps(_cmdline(argv))}\n" \
                        "  capabilities: [long_form_writing, technical_reasoning]\n  tier: strong\n"
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home", profiles)
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project))
        self.cli.run("vendor", str(_recipe(tmp_path / "toy")))
        py = self.project / ".baton" / "project.yaml"
        cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
        cfg["paths"] = {"docs": "docs/out"} if paths is None else paths
        py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")

    def start(self, title: str = "Login") -> str:
        return self.cli.run("start", "toy", "--inputs", json.dumps({"title": title}))["run_id"]

    def by_hand(self, run: str, step: str, doc: str | None = None, expect: int | None = None) -> dict:
        d = self.cli.run("dispatch", run, step, "--worker", "owner", expect=None)  # exit 4 while drift is pending
        pdir = packet_dir(self.project, run, step, d["attempt"])
        extra = {}
        if doc is not None:
            (pdir.parent / "result" / "artifacts").mkdir(parents=True, exist_ok=True)
            (pdir.parent / "result" / "artifacts" / "doc.md").write_text(doc, encoding="utf-8")
            extra["artifacts"] = [{"name": "doc", "path": "artifacts/doc.md"}]
        write_result(pdir, {}, **extra)
        self.last_packet = pdir
        return self.cli("submit", run, step, expect=expect).payload

    def events(self, run: str) -> list[dict]:
        p = self.project / ".baton" / "runs" / run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def of(self, run: str, etype: str) -> list[dict]:
        return [e for e in self.events(run) if e["type"] == etype]

    def status(self, run: str) -> dict:
        return self.cli.run("status", run, expect=None)

    def pending(self, run: str, kind: str) -> list[dict]:
        return [p for p in self.status(run)["pending_decisions"] if p["kind"] == kind]

    def file(self, rel: str) -> Path:
        return self.project / rel


def _input(pdir: Path, name: str) -> tuple[dict, str]:
    m = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    entry = next(i for i in m["inputs"] if i["name"] == name)
    return entry, (pdir / entry["path"]).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Publishing and conflicts (§10.4)
# ---------------------------------------------------------------------------


def test_deliverable_appears_at_its_mapped_path_and_is_committed(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    out = p.by_hand(run, "draft", "# Login requirements\n")
    target = p.file("docs/out/login-doc.md")
    assert target.read_text(encoding="utf-8") == "# Login requirements\n"
    (pub,) = p.of(run, "artifact_published")
    assert pub["step_path"] == "draft" and pub["data"]["path"] == "docs/out/login-doc.md" and pub["data"]["artifact"] == "doc"
    assert out["checkpoint"]["committed"]
    assert "docs/out/login-doc.md" in git(p.project, "show", "--name-only", "--format=", "HEAD").split()
    st = p.status(run)
    assert st["deliverables"] == [{"step_path": "draft", "artifact": "doc", "path": "docs/out/login-doc.md", "sha256": pub["data"]["sha256"], "revisions": 0}]
    record = (p.project / ".baton" / "runs" / run / "docs" / "draft.md").read_text(encoding="utf-8")
    assert "## Deliverables" in record and "published to `docs/out/login-doc.md`" in record
    assert p.cli.run("check")["ok"]


def test_start_refuses_a_recipe_publishing_to_an_unmapped_path(tmp_path):
    p = P(tmp_path, paths={})
    err = p.cli.run("start", "toy", "--inputs", json.dumps({"title": "x"}), expect=1)
    assert err["error"] == "configuration.publish_path" and "paths.docs" in err["message"]


def test_publish_inside_a_group_is_a_load_error(tmp_path):
    with pytest.raises(RecipeError) as e:
        load_recipe(_recipe(tmp_path / "g", in_group=True))
    assert "publish.in_group" in {i.code for i in e.value.issues}


def test_a_pre_existing_file_is_never_overwritten_silently(tmp_path):
    p = P(tmp_path)
    target = p.file("docs/out/login-doc.md")
    target.parent.mkdir(parents=True)
    target.write_text("hand-written\n", encoding="utf-8")
    run = p.start("Login")
    out = p.by_hand(run, "draft", "# from Baton\n", expect=4)
    assert out["outcome"] == "passed" and target.read_text(encoding="utf-8") == "hand-written\n"
    (c,) = p.pending(run, "publish_conflict")
    assert c["ref"] == "publish:draft.doc" and "not written by Baton" in c["reasons"][0] and c["options"] == ["overwrite", "keep", "alternate"]
    assert not p.of(run, "artifact_published")
    assert p.status(run)["ready"] == ["review"]  # the step passed; later steps read CAS and are not held
    # keep: the existing file stays; the deliverable is recorded as not published.
    p.cli.run("decide", run, "publish:draft.doc", "keep", "--note", "My version is the real one")
    assert target.read_text(encoding="utf-8") == "hand-written\n"
    (kept,) = p.of(run, "artifact_published")
    assert kept["data"]["kept"] and not p.pending(run, "publish_conflict")
    assert not p.status(run)["drift"]  # a kept file is not Baton's to track


def test_identical_existing_file_is_recorded_not_rewritten(tmp_path):
    p = P(tmp_path)
    target = p.file("docs/out/login-doc.md")
    target.parent.mkdir(parents=True)
    target.write_text("# same\n", encoding="utf-8")
    run = p.start("Login")
    p.by_hand(run, "draft", "# same\n")
    (pub,) = p.of(run, "artifact_published")
    assert pub["data"]["unchanged"] and not p.pending(run, "publish_conflict")


def test_conflict_overwrite_and_alternate(tmp_path):
    p = P(tmp_path)
    a = p.start("Login")
    p.by_hand(a, "draft", "# run A\n")
    # Another work item with the same slug: the file was published by a different run.
    b = p.start("Login")
    p.by_hand(b, "draft", "# run B\n", expect=4)
    (c,) = p.pending(b, "publish_conflict")
    assert f"last published by run {a}" in c["reasons"][0]
    alt = p.cli.run("decide", b, "publish:draft.doc", "alternate", "--note", "keep both")
    assert alt["reasons"] == [f"alternate: docs/out/login-doc.{b}.md"]
    assert p.file(f"docs/out/login-doc.{b}.md").read_text(encoding="utf-8") == "# run B\n"
    assert p.file("docs/out/login-doc.md").read_text(encoding="utf-8") == "# run A\n"
    # A third run: overwrite, and an explicit alternate path that itself conflicts is refused.
    c3 = p.start("Login")
    p.by_hand(c3, "draft", "# run C\n", expect=4)
    err = p.cli.run("decide", c3, "publish:draft.doc", "alternate", "--path", f"docs/out/login-doc.{b}.md", expect=1)
    assert err["error"] == "publish.conflict"
    err = p.cli.run("decide", c3, "publish:draft.doc", "alternate", "--path", ".baton/x.md", expect=1)
    assert err["error"] == "publish.bad_target"
    p.cli.run("decide", c3, "publish:draft.doc", "overwrite", "--note", "C supersedes A")
    assert p.file("docs/out/login-doc.md").read_text(encoding="utf-8") == "# run C\n"
    dec = [e for e in p.of(c3, "human_decision") if e["data"]["kind"] == "publish"]
    assert dec[0]["data"]["decision"] == "overwrite" and dec[0]["data"]["note"] == "C supersedes A"


def test_a_revised_step_replaces_its_own_untouched_file_but_not_an_edited_one(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    p.by_hand(run, "draft", "v1\n")
    p.cli.run("revise", run, "draft", "--reason", "tighten it")
    p.by_hand(run, "draft", "v2\n")
    assert p.file("docs/out/login-doc.md").read_text(encoding="utf-8") == "v2\n" and len(p.of(run, "artifact_published")) == 2
    # Edited by a person, then revised again: the new version waits on the owner.
    p.file("docs/out/login-doc.md").write_text("v2 with my notes\n", encoding="utf-8")
    assert p.cli("revise", run, "draft", "--reason", "again", expect=4).payload["pending_decisions"][0]["kind"] == "drift"
    p.by_hand(run, "draft", "v3\n", expect=4)
    (c,) = p.pending(run, "publish_conflict")
    assert "edited since Baton published it" in c["reasons"][0]
    assert not p.pending(run, "drift")  # the conflict decides that file; not asked twice
    assert p.file("docs/out/login-doc.md").read_text(encoding="utf-8") == "v2 with my notes\n"


# ---------------------------------------------------------------------------
# Drift and revisions (§10.5)
# ---------------------------------------------------------------------------


def test_editing_a_published_file_triggers_drift_and_ingesting_it_feeds_a_later_step(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    p.by_hand(run, "draft", "# original\n")
    target = p.file("docs/out/login-doc.md")
    target.write_text("# original, corrected by the owner\n", encoding="utf-8")
    # Read-only views see it, without recording.
    (d,) = p.pending(run, "drift")
    assert d["ref"] == "drift:draft.doc" and d["current_sha256"]
    assert not p.of(run, "drift_detected")
    chk = p.cli("check", expect=0).payload
    assert any(i["code"] == "publish.drift" and i["severity"] == "warning" for i in chk["issues"])
    assert any(i["code"] == "publish.drift" and i["severity"] == "error" for i in p.cli("check", "--strict", expect=1).payload["issues"])
    det = p.cli.run("detect")
    assert det["runs"][0]["drift"] == ["docs/out/login-doc.md"] and any("changed since publishing" in w for w in det["warnings"])
    # A mutating call records it once.
    p.cli.run("resume", run, expect=None)
    p.cli.run("resume", run, expect=None)
    assert len(p.of(run, "drift_detected")) == 1
    # Ingest it (the owner's words), then the later step's packet carries it.
    out = p.cli.run("ingest-revision", run, "draft", "doc", "--note", "Use my corrected version")
    assert out["revision"] == 1 and out["reference"] == "human_revision.draft.doc"
    (rev,) = p.of(run, "human_revision_ingested")
    assert rev["data"]["source"] == "drift" and rev["data"]["feed"] == "revision_inputs"
    assert not p.pending(run, "drift") and p.status(run)["deliverables"][0]["revisions"] == 1
    p.by_hand(run, "review")
    edited, text = _input(p.last_packet, "edited")
    assert text == "# original, corrected by the owner\n" and edited["human_revision"]["revision"] == 1
    doc, text = _input(p.last_packet, "doc")
    assert text == "# original\n" and "human_revision" not in doc  # feed: revision inputs only
    assert "ingested by the owner" in (p.last_packet / "INSTRUCTIONS.md").read_text(encoding="utf-8")


def test_without_a_revision_the_human_revision_input_is_not_applicable(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    p.by_hand(run, "draft", "# original\n")
    p.by_hand(run, "review")
    m = json.loads((p.last_packet / "manifest.json").read_text(encoding="utf-8"))
    assert [n["name"] for n in m["not_applicable"]] == ["edited"]


def test_feeding_dependents_reaches_only_steps_not_yet_started_and_flags_passed_ones(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    p.by_hand(run, "draft", "# original\n")
    p.by_hand(run, "review")
    p.file("docs/out/login-doc.md").write_text("# edited\n", encoding="utf-8")
    out = p.cli.run("ingest-revision", run, "draft", "doc", "--note", "Carry this forward", "--feed", "dependents")
    assert out["possibly_stale"] == ["review"]
    st = p.status(run)
    assert st["possibly_stale"] == [{"step_path": "review", "source": "draft", "artifact": "doc", "revision": 1}]
    assert st["steps"]["review"]["state"] == "passed"  # a flag, not the stale state
    assert "**Possibly stale:**" in (p.project / ".baton" / "runs" / run / "docs" / "review.md").read_text(encoding="utf-8")
    p.by_hand(run, "final")
    doc, text = _input(p.last_packet, "doc")
    assert text == "# edited\n" and doc["human_revision"]["revision"] == 1


def test_leaving_drift_and_a_deleted_file(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    p.by_hand(run, "draft", "# original\n")
    target = p.file("docs/out/login-doc.md")
    target.write_text("# tweaked\n", encoding="utf-8")
    p.cli.run("decide", run, "drift:draft.doc", "leave", "--note", "cosmetic only")
    assert not p.pending(run, "drift")
    target.write_text("# tweaked again\n", encoding="utf-8")
    assert p.pending(run, "drift")  # a later edit is new drift
    target.unlink()
    (d,) = p.pending(run, "drift")
    assert d["current_sha256"] is None and d["options"] == ["leave"]
    assert p.cli.run("ingest-revision", run, "draft", "doc", "--note", "x", expect=1)["error"] == "revision.deleted"
    p.cli.run("decide", run, "drift:draft.doc", "leave", "--note", "I removed it on purpose")
    assert not p.pending(run, "drift")
    assert p.cli.run("decide", run, "drift:draft.doc", "leave", "--note", "again", expect=1)["error"] == "decide.nothing_pending"


def test_pending_drift_holds_run_completion_and_completed_runs_are_not_tracked(tmp_path):
    p = P(tmp_path)
    run = p.start("Login")
    p.by_hand(run, "draft", "# original\n")
    p.by_hand(run, "review")
    target = p.file("docs/out/login-doc.md")
    target.write_text("# edited\n", encoding="utf-8")
    p.by_hand(run, "final", expect=4)
    assert p.status(run)["state"] == "active"
    out = p.cli.run("decide", run, "drift:draft.doc", "leave", "--note", "fine")
    assert out["run_completed"] and p.status(run)["state"] == "completed"
    target.write_text("# edited after completion\n", encoding="utf-8")
    assert not p.status(run)["drift"] and not any(i["code"] == "publish.drift" for i in p.cli("check").payload["issues"])


# ---------------------------------------------------------------------------
# An expert's answer promoted as a revision (§12.2)
# ---------------------------------------------------------------------------


def test_expert_artifact_promoted_as_a_revision_is_published_and_fed(tmp_path):
    p = P(tmp_path, sme=True)
    run = p.start("Login")
    p.by_hand(run, "draft", "# original\n")
    p.sme_behavior.write_text(json.dumps({"mode": "answer", "answer": "Here is a clearer version.",
                                          "artifacts": {"better": "# clearer, from the expert\n"}}), encoding="utf-8")
    c = p.cli.run("ask-sme", "project", "Can the doc be clearer?", "--run", run, "--ref", "step:draft", "--wait", "--timeout", "60")["consultation"]
    assert p.cli.run("promote-sme", c, "revision", "--note", "yes, use it", expect=1)["error"] == "sme.revision_needs_artifact"
    out = p.cli.run("promote-sme", c, "revision", "--artifact", "draft.doc", "--from", "better", "--note", "Yes, use the expert's version")
    assert out["revision"] == 1 and out["path"] == "docs/out/login-doc.md"
    assert p.file("docs/out/login-doc.md").read_text(encoding="utf-8") == "# clearer, from the expert\n"
    (rev,) = p.of(run, "human_revision_ingested")
    assert rev["data"]["source"] == "sme" and p.of(run, "sme_promoted")[-1]["data"]["target"] == "revision"
    assert not p.pending(run, "drift")  # Baton wrote it: no drift
    p.by_hand(run, "review")
    edited, text = _input(p.last_packet, "edited")
    assert text == "# clearer, from the expert\n" and edited["human_revision"]["source"] == "sme"
    assert "an expert's answer the owner promoted" in (p.last_packet / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    # A drifted file must be settled first.
    p.file("docs/out/login-doc.md").write_text("# owner edit\n", encoding="utf-8")
    err = p.cli.run("promote-sme", c, "revision", "--artifact", "draft.doc", "--text", "# again\n", "--note", "again", expect=1)
    assert err["error"] == "revision.drifted"
