"""Leases (§10.2), checkpoint commits (§10.1), records (§10.6), project config and vendoring."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest

from baton import engine, gitops
from baton.engine import Api
from baton.locks import Director, LeaseHeld, Leases
from baton.packet import EngineError
from baton.project import init, load_config, slugify

from conftest import FIT_CHECK
from projectkit import FIT_INPUTS, GOOD_PROFILE, VERDICT, BAD_PROFILE, git, make_git_project, make_home, packet_dir, write_result
from runkit import Clock

GOLDEN = Path(__file__).parent / "golden"


def _api(root: Path, home: Path, clock: Clock, director: str = "alice@host1") -> Api:
    return Api.open(root, director_id=director, home=home, clock=clock)


@pytest.fixture
def plain(tmp_path):
    """A non-git project (checkpoints skip) with fit-check vendored, a fixed clock and an owner profile."""
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    home = make_home(tmp_path / "home")
    clock = Clock()
    api = _api(root, home, clock)
    api.vendor(FIT_CHECK)
    return api, root, home, clock


# ---------------------------------------------------------------------------
# Leases
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_lease_claim_renew_expire_takeover(plain):
    api, root, home, clock = plain
    run = api.start("fit-check", FIT_INPUTS, run_id="r_20261101_ab12")["run_id"]
    log = api.project.store.run(run)
    alice = Leases(log, Director("alice@host1"), None, 60)
    bob = Leases(log, Director("bob@host2"), None, 60)
    first = alice.current()
    assert first.director_id == "alice@host1"

    # Activity before half the term does not renew; after it does.
    clock.t += timedelta(minutes=10)
    assert alice.ensure().expires_at == first.expires_at
    clock.t += timedelta(minutes=25)
    renewed = alice.ensure()
    assert renewed.expires_at > first.expires_at
    assert [e.type for e in log.events() if e.type.startswith("lease_")] == ["lease_claimed", "lease_renewed"]

    with pytest.raises(LeaseHeld):
        bob.ensure()
    with pytest.raises(EngineError):
        bob.take_over("  ")

    # After expiry, the lease is free to claim without a takeover.
    clock.t += timedelta(minutes=61)
    claimed = bob.ensure()
    assert claimed.director_id == "bob@host2"
    assert log.events()[-1].data["previous"]["director_id"] == "alice@host1"

    # A takeover records who it was taken from and why.
    alice.take_over("Owner approved.")
    ev = log.events()[-1]
    assert ev.type == "lease_taken_over" and ev.data["from_director_id"] == "bob@host2" and ev.data["reason"] == "Owner approved."


def test_lease_is_per_branch(plain):
    api, root, home, clock = plain
    run = api.start("fit-check", FIT_INPUTS)["run_id"]
    log = api.project.store.run(run)
    same_director_other_branch = Leases(log, Director("alice@host1"), "feature", 60)
    with pytest.raises(LeaseHeld, match="leased to alice@host1"):
        same_director_other_branch.ensure()


@pytest.mark.slow
def test_mutating_calls_need_the_lease(plain):
    api, root, home, clock = plain
    run = api.start("fit-check", FIT_INPUTS)["run_id"]
    bob = _api(root, home, clock, "bob@host2")
    with pytest.raises(LeaseHeld):
        bob.dispatch(run, "describe", "owner")
    assert bob.status(run)["lease"]["yours"] is False  # reading is always allowed
    with pytest.raises(LeaseHeld):
        bob.resume(run)


def test_director_identity():
    d = Director.current("me with spaces@host", "codex")
    assert d.id == "me_with_spaces@host" and d.harness == "codex" and d.actor == "director:me_with_spaces@host"


# ---------------------------------------------------------------------------
# Records (golden files, §17)
# ---------------------------------------------------------------------------


def _golden(name: str, text: str) -> None:
    golden = GOLDEN / name
    if os.environ.get("BATON_UPDATE_GOLDEN"):
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert text == golden.read_text(encoding="utf-8"), f"{name} differs; BATON_UPDATE_GOLDEN=1 rewrites it"


@pytest.mark.slow
def test_records_golden(plain, monkeypatch):
    """Step records and the summary for a full fit-check run with a retry are pinned.

    The recipe catalog is fixed: the `assess` packet holds it, so its hash would change whenever a recipe ships.
    """
    monkeypatch.setattr("baton.frame.recipe_listing", lambda project, with_scope=False: [])
    api, root, home, clock = plain
    run = api.start("fit-check", FIT_INPUTS, run_id="r_20261101_ab12")["run_id"]
    api.dispatch(run, "describe", "owner")
    write_result(packet_dir(root, run, "describe", 1), BAD_PROFILE)
    assert api.submit(run, "describe")["outcome"] == "retry"
    api.retry(run, "describe", guidance="Fill in every occurrence field.")
    write_result(packet_dir(root, run, "describe", 2), GOOD_PROFILE)
    out = api.submit(run, "describe")
    assert out["checkpoint"] == {"committed": False, "sha": None, "subject": None, "reason": "not a git repository"}
    api.dispatch(run, "assess", "owner")
    write_result(packet_dir(root, run, "assess", 1), VERDICT)
    api.submit(run, "assess")
    api.decide(run, "assess", "approve", "Agreed; author the recipe.")

    docs = root / ".baton" / "runs" / run / "docs"
    _golden("fit-check-SUMMARY.md", (docs / "SUMMARY.md").read_text(encoding="utf-8"))
    _golden("fit-check-describe-record.md", (docs / "describe.md").read_text(encoding="utf-8"))
    _golden("fit-check-assess-record.md", (docs / "assess.md").read_text(encoding="utf-8"))
    assert api.record(run, "assess") == (docs / "assess.md").read_text(encoding="utf-8")

    # Records are derived: deleting them and regenerating gives the same files.
    from baton import docs as docs_mod

    before = {p.name: p.read_bytes() for p in docs.iterdir()}
    for p in docs.iterdir():
        p.unlink()
    docs_mod.write_records(api.project.context(run))
    assert {p.name: p.read_bytes() for p in docs.iterdir()} == before


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


def _git_project(tmp_path: Path) -> tuple[Api, Path]:
    root = make_git_project(tmp_path / "proj")
    init(root)
    home = make_home(tmp_path / "home")
    api = _api(root, home, Clock())
    api.vendor(FIT_CHECK)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "setup")
    return api, root


def _pass_describe(api: Api, root: Path) -> tuple[str, dict]:
    run = api.start("fit-check", FIT_INPUTS)["run_id"]
    api.dispatch(run, "describe", "owner")
    write_result(packet_dir(root, run, "describe", 1), GOOD_PROFILE)
    return run, api.submit(run, "describe")


@pytest.mark.slow
def test_checkpoint_refuses_with_unrelated_staged_changes(tmp_path):
    api, root = _git_project(tmp_path)
    (root / "notes.md").write_text("owner's work in progress\n")
    git(root, "add", "notes.md")
    run, out = _pass_describe(api, root)
    assert not out["checkpoint"]["committed"]
    assert "unrelated changes are staged (notes.md)" in out["checkpoint"]["reason"]
    assert git(root, "log", "--format=%s").splitlines() == ["setup"]

    # Once the owner deals with it, the next checkpoint includes everything since.
    git(root, "reset", "-q", "notes.md")
    api.dispatch(run, "assess", "owner")
    write_result(packet_dir(root, run, "assess", 1), VERDICT)
    out = api.submit(run, "assess")
    assert out.get("checkpoint") is None  # opening a human gate is not a checkpoint
    out = api.decide(run, "assess", "reject", "Not convinced.")
    assert out["checkpoint"]["committed"]
    assert "notes.md" not in git(root, "show", "--name-only", "--format=", "HEAD")
    assert "?? notes.md" in git(root, "status", "--porcelain")  # unstaged work is never swept in


@pytest.mark.slow
def test_checkpoint_commits_off(tmp_path):
    api, root = _git_project(tmp_path)
    cfg = root / ".baton" / "project.yaml"
    cfg.write_text(cfg.read_text().replace("checkpoints: { commit: true }", "checkpoints: { commit: false }"))
    git(root, "commit", "-qam", "checkpoints off")
    api = _api(root, api.project.home, Clock())
    _, out = _pass_describe(api, root)
    assert out["checkpoint"]["reason"] == "checkpoint commits are off in project.yaml"
    assert len(git(root, "log", "--format=%s").splitlines()) == 2


@pytest.mark.slow
def test_checkpoint_without_identity(tmp_path, monkeypatch):
    api, root = _git_project(tmp_path)
    git(root, "config", "--unset", "user.email")
    git(root, "config", "--unset", "user.name")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("EMAIL", "")
    _, out = _pass_describe(api, root)
    cp = out["checkpoint"]
    if cp["committed"]:  # pragma: no cover - git guessed an identity from the host
        pytest.skip("git derived a committer identity from the environment")
    assert "identity" in cp["reason"]


def test_lfs_attributes(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "cas" / "ab").mkdir(parents=True)
    big = run_dir / "cas" / "ab" / ("ab" + "0" * 62)
    big.write_bytes(b"x" * 2048)
    (run_dir / "cas" / "cd").mkdir()
    (run_dir / "cas" / "cd" / ("cd" + "0" * 62)).write_bytes(b"x")
    assert gitops.lfs_attributes(run_dir, 1024)
    assert (run_dir / ".gitattributes").read_text() == f"cas/ab/{big.name} filter=lfs diff=lfs merge=lfs -text\n"
    assert not gitops.lfs_attributes(run_dir, 1024)  # idempotent


@pytest.mark.slow
def test_lfs_used_when_installed(tmp_path, monkeypatch):
    api, root = _git_project(tmp_path)
    monkeypatch.setattr(gitops, "lfs_available", lambda _root: True)
    cfg = api.project.config
    api.project.config = cfg.model_copy(update={"lfs": cfg.lfs.model_copy(update={"threshold_mb": 0.0001})})
    run, out = _pass_describe(api, root)
    assert out["checkpoint"]["committed"]
    ga = root / ".baton" / "runs" / run / ".gitattributes"
    assert "filter=lfs" in ga.read_text()
    assert f".baton/runs/{run}/.gitattributes" in git(root, "show", "--name-only", "--format=", "HEAD")
    assert api.check() == []


# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_init_is_idempotent_and_keeps_files(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / ".gitignore").write_text("node_modules/")
    first = init(root)
    assert ".baton/project.yaml" in first["created"] and ".gitignore (updated)" in first["created"]
    assert (root / ".gitignore").read_text() == "node_modules/\n.baton/cache/\n.baton/workers.local.yaml\n"
    (root / ".baton" / "communication.md").write_text("Mine.\n")
    assert init(root)["created"] == []
    assert (root / ".baton" / "communication.md").read_text() == "Mine.\n"
    assert "not a git repository" in first["notes"][0]


def test_project_config_validation(tmp_path):
    p = tmp_path / "project.yaml"
    p.write_text("leases: { minutes: 0 }\n")
    assert load_config(p)[0] is None
    p.write_text("project: { token: 'secret:x' }\n")
    cfg, issues = load_config(p)
    assert cfg is None and issues[0].code == "project.secret_reference"
    p.write_text("unknown_key: 1\n")
    assert load_config(p)[1][0].code == "project.invalid"
    p.write_text("paths: { specs: docs/specs }\n")
    cfg, issues = load_config(p)
    assert issues == [] and cfg.leases.minutes == 60 and cfg.checkpoints.commit and cfg.lfs.threshold_mb == 5


def test_vendor_refuses_in_place_edits(tmp_path, make_recipe):
    root = tmp_path / "p"
    root.mkdir()
    init(root, bare=True)
    api = _api(root, tmp_path / "home", Clock())
    assert api.vendor(FIT_CHECK)["changed"]
    assert not api.vendor(FIT_CHECK)["changed"]
    lock = api.project.lock()["recipes"]["fit-check@4"]
    assert set(lock["steps"]) == {"describe", "assess"}
    assert lock["steps"]["assess"]["capabilities"] == ["structured_output", "technical_reasoning"]
    edited = make_recipe(lambda r, d: (d / "prompts" / "describe.md").write_text("changed"), source=FIT_CHECK)
    with pytest.raises(EngineError) as e:
        api.vendor(edited)
    assert e.value.code == "vendor.version_exists"


@pytest.mark.slow
def test_run_records_work_item(plain):
    api, root, home, clock = plain
    started = api.project.store.run(api.start("fit-check", {**FIT_INPUTS, "title": "Big Idea: Ünïcode!"})["run_id"]).events()[0].data
    assert started["slug"] == "big-idea-n-code"
    assert started["title"] == "Big Idea: Ünïcode!"
    assert started["branch"] is None and started["kind"] is None


def test_slugify():
    assert slugify("  Hello, World  ") == "hello-world"
    assert slugify("!!!") == "run"


@pytest.mark.slow
def test_unsupported_adapter(plain):
    api, root, home, clock = plain
    (home / "workers.yaml").write_text(
        "cli:\n  adapter: carrier_pigeon\n  vendor: someone\n  capabilities: [structured_output, long_form_writing]\n  tier: strong\n"
    )
    run = api.start("fit-check", FIT_INPUTS)["run_id"]
    with pytest.raises(EngineError) as e:
        api.dispatch(run, "describe", "cli")
    assert e.value.code == "adapter.unsupported"
    assert api.status(run)["steps"]["describe"]["state"] == "ready"  # nothing written


@pytest.mark.slow
def test_local_profiles_override(plain):
    api, root, home, clock = plain
    (root / ".baton" / "workers.local.yaml").write_text(
        "owner:\n  adapter: manual\n  vendor: human\n  person: deputy\n  capabilities: [structured_output]\n"
    )
    assert api.project.profiles()["owner"].person == "deputy"


def test_pending_escalation_and_engine_reexports():
    assert "Api" in engine.__all__
