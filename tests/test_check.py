"""``baton check`` (§13.5): clean, then a tampered event, a missing blob, a planted secret sentinel, and more."""

from __future__ import annotations

import json

import pytest

from baton.redact import SENTINEL_PREFIX, redact_text, scan_bytes

from projectkit import FIT_INPUTS, GOOD_PROFILE, packet_dir, setup_fit_check, write_result


@pytest.fixture
def done(tmp_path):
    """A project with one fit-check run whose describe step has passed."""
    cli, project = setup_fit_check(tmp_path)
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    cli.run("dispatch", run, "describe", "--worker", "owner")
    write_result(packet_dir(project, run, "describe", 1), GOOD_PROFILE)
    cli.run("submit", run, "describe")
    return cli, project, project / ".baton" / "runs" / run


def _errors(cli) -> list[dict]:
    res = cli("check", expect=None)
    issues = [i for i in res.payload["issues"] if i["severity"] == "error"]
    assert res.exit_code == (1 if issues else 0)
    return issues


def _text_check(cli) -> tuple[int, list[str]]:
    from typer.testing import CliRunner

    from baton.cli import app

    res = CliRunner(env={"BATON_PROJECT": str(cli.project)}).invoke(app, ["check"])
    return res.exit_code, res.stdout.splitlines()


def test_clean(done):
    cli, _, _ = done
    assert _errors(cli) == []
    code, lines = _text_check(cli)
    assert code == 0 and lines == []


def test_tampered_event(done):
    cli, _, rdir = done
    log = rdir / "events.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    ev = json.loads(lines[0])
    ev["data"]["title"] = "Something else"
    lines[0] = json.dumps(ev, sort_keys=True, separators=(",", ":"))
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    errs = _errors(cli)
    assert [e["code"] for e in errs] == ["events.hash_mismatch"]
    code, out = _text_check(cli)
    assert code == 1
    assert out[0].startswith(f"ERROR .baton/runs/{rdir.name}/events.jsonl:1: ")
    # resume refuses too, and changes nothing
    before = log.read_bytes()
    assert cli.run("resume", rdir.name, expect=1)["error"] == "resume.integrity"
    assert log.read_bytes() == before


def test_missing_blob(done):
    cli, _, rdir = done
    events = [json.loads(line) for line in (rdir / "events.jsonl").read_text().splitlines()]
    out_sha = next(e for e in events if e["type"] == "step_passed")["data"]["output_sha256"]
    blob = rdir / "cas" / out_sha[:2] / out_sha
    blob.chmod(0o600)
    blob.unlink()
    errs = _errors(cli)
    assert [e["code"] for e in errs] == ["cas.missing"]
    assert out_sha in errs[0]["where"]


def test_corrupt_blob(done):
    cli, _, rdir = done
    blob = next(p for p in (rdir / "cas").rglob("*") if p.is_file())
    blob.chmod(0o600)
    blob.write_bytes(b"changed")
    assert "cas.corrupt" in {e["code"] for e in _errors(cli)}


def test_planted_secret_sentinel(done):
    cli, project, rdir = done
    planted = rdir / "steps" / "describe" / "attempt-1" / "result" / "notes.txt"
    planted.write_text(f"token={SENTINEL_PREFIX}a1b2c3d4e5\n", encoding="utf-8")
    errs = _errors(cli)
    assert [e["code"] for e in errs] == ["secret.found"]
    assert errs[0]["where"].endswith("result/notes.txt")
    assert SENTINEL_PREFIX not in json.dumps(errs)  # the secret itself is never printed
    # Gitignored machinery is not scanned.
    planted.unlink()
    (project / ".baton" / "cache" / "x.txt").write_text(f"{SENTINEL_PREFIX}a1b2c3d4e5", encoding="utf-8")
    assert _errors(cli) == []


def test_secret_reference_in_project_yaml(done):
    cli, project, _ = done
    p = project / ".baton" / "project.yaml"
    p.write_text(p.read_text() + 'project: { token: "secret:github" }\n'.replace("project:", "hooks_like:"), encoding="utf-8")
    codes = {e["code"] for e in _errors(cli)}
    assert "project.secret_reference" in codes and "project.invalid" in codes


def test_missing_communication_contract(done):
    cli, project, _ = done
    (project / ".baton" / "communication.md").unlink()
    assert [e["code"] for e in _errors(cli)] == ["project.no_communication"]


def test_vendored_recipe_edited_in_place(done):
    cli, project, _ = done
    prompt = project / ".baton" / "recipes" / "fit-check@1" / "prompts" / "describe.md"
    prompt.write_text(prompt.read_text() + "\nAlso do something else.\n", encoding="utf-8")
    codes = [e["code"] for e in _errors(cli)]
    assert "lock.recipe_hash" in codes


def test_neutrality_violation_in_vendored_recipe(done):
    cli, project, _ = done
    rf = project / ".baton" / "recipes" / "fit-check@1" / "recipe.yaml"
    rf.write_text(rf.read_text().replace("tier: standard }", "tier: standard, model: x }", 1), encoding="utf-8")
    assert "neutrality.forbidden_key" in {e["code"] for e in _errors(cli)}


def test_impossible_state(done):
    """A log whose chain is intact but whose sequence is illegal is caught by the state machine."""
    from baton.store import canonical_json, event_sha256

    cli, _, rdir = done
    log = rdir / "events.jsonl"
    events = [json.loads(line) for line in log.read_text().splitlines()]
    last = events[-1]
    bogus = {**last, "seq": last["seq"] + 1, "type": "step_running", "step_path": "assess", "attempt": 1, "data": {}, "prev_sha256": last["sha256"]}
    bogus.pop("sha256")
    bogus["sha256"] = event_sha256(bogus)
    with open(log, "a", encoding="utf-8") as f:
        f.write(canonical_json(bogus) + "\n")
    assert [e["code"] for e in _errors(cli)] == ["events.impossible_state"]


def test_unreadable_lock_format(done):
    cli, project, _ = done
    lp = project / ".baton" / "baton.lock"
    lock = json.loads(lp.read_text())
    lock["formats"]["events"] = "baton-events/99"
    lp.write_text(json.dumps(lock), encoding="utf-8")
    assert [e["code"] for e in _errors(cli)] == ["lock.unknown_format"]


def test_not_a_project(tmp_path):
    from typer.testing import CliRunner

    from baton.cli import app

    res = CliRunner(env={"BATON_PROJECT": str(tmp_path)}).invoke(app, ["check"])
    assert res.exit_code == 1


@pytest.mark.parametrize(
    "token",
    [
        f"{SENTINEL_PREFIX}abcdef12",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "sk-" + "a" * 32,
        "AKIA" + "A" * 16,
        "ghp_" + "a" * 36,
        "xoxb-" + "1" * 12,
        "AIza" + "a" * 35,
    ],
)
def test_secret_patterns(token):
    assert scan_bytes(f"x {token} y".encode())
    assert token not in redact_text(f"x {token} y")


def test_hashes_are_not_secrets():
    assert scan_bytes(("a" * 64 + " " + "0123456789abcdef" * 4).encode()) == []
