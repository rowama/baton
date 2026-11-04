"""The litellm_api adapter and worker runner (§6.3), secrets in a full run (§15.2), doctor (§13.4).

Unit tests drive ``worker_runner.run`` in-process with a fake completion
function. The end-to-end tests start the real child (``python -m
baton.worker_runner``) with real ``litellm``, using its offline
``mock_response`` option through the profile's ``options``; no network is used.
Opt-in live test: ``BATON_LIVE_MODELS="<vendor>=<model>,<vendor>=<model>"`` with
the providers' keys in ``BATON_SECRET_<VENDOR>`` (see ``test_live_two_vendors``).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from baton import worker_runner as wr
from baton.engine import classify_exit, finish_child
from baton.supervisor import ChildResult

from projectkit import FIT_INPUTS, GOOD_PROFILE, VERDICT, git, setup_fit_check
from runkit import PROFILE_OUT, VERDICT_OUT, start

from conftest import FIT_CHECK

SENTINEL_A = "BATON-SENTINEL-vendorAkey0001"
SENTINEL_B = "BATON-SENTINEL-vendorBkey0002"

try:
    import litellm  # noqa: F401

    HAVE_LITELLM = True
except ImportError:  # pragma: no cover
    HAVE_LITELLM = False
needs_litellm = pytest.mark.skipif(not HAVE_LITELLM, reason="litellm not installed (pip install baton[api])")


def reply(output, **extra) -> str:
    return json.dumps({"status": "completed", "output": output, "notes": "", **extra})


def api_profile(name: str, vendor: str, model: str, secret: str, mock: str | None, *, env_var: str = "PROVIDER_KEY", **extra) -> str:
    opts = f"\n  options: {json.dumps({'mock_response': mock})}" if mock is not None else ""
    more = "".join(f"\n  {k}: {v}" for k, v in extra.items())
    return (
        f"{name}:\n  adapter: litellm_api\n  vendor: {vendor}\n  model: {model}\n"
        f"  capabilities: [structured_output, long_form_writing, technical_reasoning]\n  tier: strong\n"
        f"  context_tokens: 128000\n  auth: {{ mode: api_key, env: {{ {env_var}: \"secret:{secret}\" }} }}{opts}{more}\n"
    )


# ---------------------------------------------------------------------------
# Worker runner, in-process
# ---------------------------------------------------------------------------


class FakeCompletion:
    def __init__(self, text: str = "", exc: Exception | None = None):
        self.text, self.exc, self.calls = text, exc, []

    def __call__(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


@pytest.fixture
def assess_packet(tmp_path):
    """A built packet for fit-check's assess step (rubric is a non-JSON input)."""
    from baton import engine
    from baton.models import WorkerProfile
    from baton.store import Store

    from runkit import WRITER, write_result

    store = Store(tmp_path / "proj")
    ctx = start(store, FIT_CHECK)
    p = engine.begin_attempt(ctx, "describe", "owner", WRITER)
    write_result(p, PROFILE_OUT)
    engine.submit(ctx, "describe")
    prof = WorkerProfile.model_validate(
        {"adapter": "litellm_api", "vendor": "v", "model": "m", "capabilities": ["structured_output", "technical_reasoning"], "tier": "strong"}
    )
    return engine.begin_attempt(ctx, "assess", "api", prof)


def test_messages_inline_text_inputs(assess_packet):
    msgs = wr.build_messages(assess_packet.dir)
    user = msgs[1]["content"]
    assert msgs[0]["role"] == "system" and "ONE JSON object" in msgs[0]["content"]
    assert "Contents of `inputs/rubric.md`" in user  # non-JSON input inlined by the runner
    assert '"frequency": "a few per month"' in user  # small JSON was already inlined in INSTRUCTIONS.md


def test_inputs_too_large_is_a_hard_error(assess_packet):
    with pytest.raises(wr.InputError) as e:
        wr.build_messages(assess_packet.dir, context_tokens=100)
    assert "budget is 200 bytes" in str(e.value) and "reads files" in str(e.value)


def test_non_text_input_is_a_hard_error(tmp_path):
    pdir = tmp_path / "packet"
    (pdir / "inputs").mkdir(parents=True)
    (pdir / "INSTRUCTIONS.md").write_text("# x\n", encoding="utf-8")
    (pdir / "inputs" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    (pdir / "manifest.json").write_text(json.dumps({"inputs": [{"name": "photo", "kind": "file", "path": "inputs/photo.png"}]}), encoding="utf-8")
    with pytest.raises(wr.InputError) as e:
        wr.build_messages(pdir)
    assert "not UTF-8 text" in str(e.value)


def test_run_writes_result_last_with_structured_output(assess_packet, tmp_path):
    fake = FakeCompletion(reply(VERDICT_OUT, notes="scored"))
    env = wr.run(assess_packet.dir, assess_packet.result_dir, "m", {"temperature": 0}, None, complete=fake, supports_schema=lambda m: True)
    assert env["status"] == "completed" and env["packet_sha256"] == assess_packet.sha256
    written = json.loads((assess_packet.result_dir / "result.json").read_text(encoding="utf-8"))
    assert written["output"] == VERDICT_OUT and written["notes"] == "scored"
    call = fake.calls[0]
    assert call["temperature"] == 0 and call["model"] == "m"
    schema = call["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["output"]["required"] == ["verdict", "reasons", "next_step"]
    assert "$schema" not in schema["properties"]["output"]


def test_prompt_only_when_no_schema_support(assess_packet):
    fake = FakeCompletion("Here you go:\n```json\n" + reply(VERDICT_OUT) + "\n```")
    env = wr.run(assess_packet.dir, assess_packet.result_dir, "m", {}, None, complete=fake)
    assert env["status"] == "completed" and "response_format" not in fake.calls[0]
    assert "## Reply schema" in fake.calls[0]["messages"][1]["content"]


def test_non_json_reply_is_a_failed_result(assess_packet):
    env = wr.run(assess_packet.dir, assess_packet.result_dir, "m", {}, None, complete=FakeCompletion("I cannot comply."))
    assert env["status"] == "failed" and "not a JSON object" in env["notes"]


def test_artifacts_written_by_name(tmp_path):
    pdir = tmp_path / "packet"
    pdir.mkdir()
    (pdir / "manifest.json").write_text(
        json.dumps({"protocol": "baton-packet/1", "packet_sha256": "abc", "required_artifacts": [{"name": "doc", "media_type": "text/markdown"}]}),
        encoding="utf-8",
    )
    env = wr.write_result(pdir, tmp_path / "result", {"status": "completed", "output": {}, "artifacts": {"doc": "# Doc\n", "../evil": "x"}})
    assert env["artifacts"] == [{"name": "doc", "path": "artifacts/doc.md"}]
    assert (tmp_path / "result" / "artifacts" / "doc.md").read_text(encoding="utf-8") == "# Doc\n"


def test_provider_exceptions_are_classified():
    class AuthenticationError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class NotFoundError(Exception):
        pass

    assert wr.classify_exception(AuthenticationError("bad key")).failure_class == "platform"
    assert wr.classify_exception(APIConnectionError("dns")).code == "provider_unavailable"
    assert wr.classify_exception(NotFoundError("no model")).failure_class == "configuration"
    assert wr.classify_exception(ValueError("?")).failure_class == "unknown"


def test_exit_without_result_is_classified_and_escalated(tmp_path):
    from baton import engine
    from baton.models import WorkerProfile
    from baton.store import Store

    ctx = start(Store(tmp_path / "proj"), FIT_CHECK)
    prof = WorkerProfile.model_validate({"adapter": "litellm_api", "vendor": "v", "model": "m", "capabilities": ["structured_output", "long_form_writing"], "tier": "strong"})
    b = engine.begin_attempt(ctx, "describe", "api", prof)
    tail = f"noise\nbaton-worker: failure=platform code=auth_failed message=Incorrect key {SENTINEL_A}\n".encode()
    from baton import redact

    redact.register(SENTINEL_A)
    out = finish_child(ctx, "describe", b.attempt, ChildResult(3, 1.0, False, tmp_path / "x.log", tail))
    assert out.outcome == "escalated"
    events = ctx.log.events()
    cls = [e for e in events if e.type == "failure_classified"][-1].data
    assert cls["class"] == "platform" and cls["code"] == "auth_failed"
    assert SENTINEL_A not in json.dumps([e.data for e in events])  # redacted before recording
    assert [e.type for e in events][-3:] == ["attempt_orphaned", "failure_classified", "step_escalated"]
    assert classify_exit(ChildResult(127, 0, False, tmp_path / "x", b""))["code"] == "executable_not_found"


def test_timeout_retries_while_attempts_remain(tmp_path):
    from baton import engine
    from baton.models import WorkerProfile
    from baton.store import Store

    ctx = start(Store(tmp_path / "proj"), FIT_CHECK)
    prof = WorkerProfile.model_validate({"adapter": "litellm_api", "vendor": "v", "model": "m", "capabilities": ["structured_output", "long_form_writing"], "tier": "strong"})
    b = engine.begin_attempt(ctx, "describe", "api", prof)
    out = finish_child(ctx, "describe", b.attempt, ChildResult(None, 9.0, True, tmp_path / "x.log", b""))
    assert out.outcome == "retry" and ctx.log.state().step("describe").state == "ready"


# ---------------------------------------------------------------------------
# Dispatch refusals: nothing is written
# ---------------------------------------------------------------------------


def _events(project: Path, run: str) -> list[str]:
    return [json.loads(line)["type"] for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text().splitlines()]


def test_missing_secret_refuses_dispatch(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    (cli.home / "workers.yaml").write_text(api_profile("api", "acme", "acme/model-a", "absent", reply(GOOD_PROFILE)), encoding="utf-8")
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    before = _events(project, run)
    res = cli("dispatch", run, "describe", "--worker", "api", "--wait", expect=1)
    assert res.payload["error"] == "configuration.missing_secret" and "BATON_SECRET_ABSENT" in res.payload["message"]
    assert _events(project, run) == before


def test_inputs_too_large_refuses_dispatch(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    (cli.home / "secrets").mkdir()
    (cli.home / "secrets" / "a").write_text(SENTINEL_A, encoding="utf-8")
    (cli.home / "workers.yaml").write_text(
        api_profile("api", "acme", "acme/model-a", "a", reply(GOOD_PROFILE)).replace("context_tokens: 128000", "context_tokens: 100"), encoding="utf-8"
    )
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    before = _events(project, run)
    res = cli("dispatch", run, "describe", "--worker", "api", "--wait", expect=1)
    assert res.payload["error"] == "dispatch.worker_cannot_take_packet" and "reads files" in res.payload["message"]
    assert _events(project, run) == before
    assert not (project / ".baton" / "runs" / run / "steps" / "describe" / "attempt-1").exists()


# ---------------------------------------------------------------------------
# End to end with real litellm children (offline mock_response)
# ---------------------------------------------------------------------------


@needs_litellm
def test_two_vendors_complete_fit_check_and_secrets_stay_out(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    (cli.home / "secrets").mkdir()
    (cli.home / "secrets" / "acme_key").write_text(SENTINEL_A + "\n", encoding="utf-8")
    (cli.home / "secrets" / "zenith_key").write_text(SENTINEL_B, encoding="utf-8")
    (cli.home / "workers.yaml").write_text(
        api_profile("acme-api", "acme", "openai/acme-model", "acme_key", reply(GOOD_PROFILE), env_var="OPENAI_API_KEY")
        + api_profile("zenith-api", "zenith", "anthropic/zenith-model", "zenith_key", reply(VERDICT), env_var="ANTHROPIC_API_KEY"),
        encoding="utf-8",
    )
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    assert [e["profile"] for e in cli.run("eligible", run, "describe")["eligible"]] == ["acme-api", "zenith-api"]

    d1 = cli.run("dispatch", run, "describe", "--worker", "acme-api", "--wait")
    assert d1["outcome"] == "passed", d1
    assert d1["worker_exit"]["exit_code"] == 0
    d2 = cli("dispatch", run, "assess", "--worker", "zenith-api", "--wait", expect=4).payload  # passes schema, waits on the human gate
    assert d2["outcome"] == "needs_human", d2
    done = cli.run("decide", run, "assess", "approve", "--note", "Agreed.")
    assert done["run_completed"] is True

    events = [json.loads(line) for line in (project / ".baton" / "runs" / run / "events.jsonl").read_text().splitlines()]
    selected = {e["step_path"]: e["data"] for e in events if e["type"] == "worker_selected"}
    assert selected["describe"]["vendor"] == "acme" and selected["assess"]["vendor"] == "zenith"
    disp = {e["step_path"]: e["data"] for e in events if e["type"] == "dispatched"}
    assert disp["describe"]["env"]["secret_names"] == ["OPENAI_API_KEY"]
    assert disp["describe"]["env"]["env_mode"] == "clean"
    assert "ANTHROPIC_API_KEY" not in disp["describe"]["env"]["names"]  # one step's key never reaches another
    assert disp["assess"]["env"]["secret_names"] == ["ANTHROPIC_API_KEY"]

    # Secrets never appear under .baton/, anywhere in the working tree, or in git history.
    for p in project.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            data = p.read_bytes()
            assert SENTINEL_A.encode() not in data and SENTINEL_B.encode() not in data, p
    assert git(project, "status", "--porcelain") == ""
    history = subprocess.run(["git", "-C", str(project), "log", "-p", "--all"], capture_output=True, text=True, check=True).stdout
    assert "baton(" in history  # checkpoint commits happened
    assert SENTINEL_A not in history and SENTINEL_B not in history
    assert cli("check", expect=0).payload["ok"] is True
    # The raw worker logs are machine-local.
    assert (cli.home / "logs" / run / "describe" / "attempt-1.log").is_file()


@needs_litellm
def test_doctor_quiet_when_healthy_and_reports_problems(tmp_path):
    cli, project = setup_fit_check(tmp_path)
    (cli.home / "secrets").mkdir()
    (cli.home / "secrets" / "k").write_text(SENTINEL_A, encoding="utf-8")
    owner = (cli.home / "workers.yaml").read_text(encoding="utf-8")
    (cli.home / "workers.yaml").write_text(owner + api_profile("api", "acme", "openai/acme-model", "k", '{"ok": true}'), encoding="utf-8")
    res = cli("doctor")
    assert res.exit_code == 0 and res.payload["ok"] is True
    rep = res.payload["profiles"]["api"]
    assert rep["noop"]["ok"] is True and rep["auth_mode"] == "api_key" and rep["env"]["secret_names"] == ["PROVIDER_KEY"]
    assert rep["env"]["denied"] == [] and SENTINEL_A not in json.dumps(res.payload)
    assert res.payload["profiles"]["owner"]["noop"] == {"skipped": "a person does this work"}
    assert res.payload["uncovered_steps"] == []
    # Text output is one line when healthy.
    from typer.testing import CliRunner

    from baton.cli import app

    text = CliRunner(env={"BATON_HOME": str(cli.home), "BATON_PROJECT": str(project)}).invoke(app, ["doctor", "--no-run"]).stdout
    assert text.strip().splitlines()[0] == "doctor: 2 profile(s) ready"

    # Problems: a missing secret, a CLI that cannot be found (listing where), an unavailable adapter.
    (cli.home / "workers.yaml").write_text(
        api_profile("api", "acme", "openai/acme-model", "absent", None)
        + "cli:\n  adapter: codex\n  vendor: zenith\n  executable: no-such-cli-xyz\n  path: { search: [nvm] }\n  capabilities: [structured_output]\n"
        + "  auth: { mode: cli_login }\n"
        + "odd:\n  adapter: carrier_pigeon\n  vendor: zenith\n  capabilities: [structured_output]\n",
        encoding="utf-8",
    )
    res = cli("doctor", "--no-run", expect=1).payload
    assert res["ok"] is False
    assert res["profiles"]["api"]["failure_class"] == "configuration"
    assert res["profiles"]["cli"]["failure_class"] == "platform" and res["profiles"]["cli"]["searched"]
    assert any("not available in this runtime" in p for p in res["profiles"]["odd"]["problems"])
    assert any("can do fit-check@2/assess" in w for w in res["warnings"])


# ---------------------------------------------------------------------------
# Live (opt-in): two real vendors' API models
# ---------------------------------------------------------------------------


@needs_litellm
@pytest.mark.skipif(not os.environ.get("BATON_LIVE_MODELS"), reason="live test: set BATON_LIVE_MODELS and the BATON_SECRET_<VENDOR> keys")
def test_live_two_vendors(tmp_path):
    """``BATON_LIVE_MODELS="openai=openai/<model>,anthropic=anthropic/<model>"``; keys in
    ``BATON_SECRET_OPENAI`` / ``BATON_SECRET_ANTHROPIC`` (injected as the providers' usual variables)."""
    pairs = [p.split("=", 1) for p in os.environ["BATON_LIVE_MODELS"].split(",")]
    assert len(pairs) == 2 and pairs[0][0] != pairs[1][0], "need two different vendors"
    cli, project = setup_fit_check(tmp_path)
    profiles = "".join(
        api_profile(f"{v}-api", v, m, v, None, env_var=f"{v.upper()}_API_KEY") for v, m in pairs
    )
    (cli.home / "workers.yaml").write_text(profiles, encoding="utf-8")
    run = cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"]
    d1 = cli("dispatch", run, "describe", "--worker", f"{pairs[0][0]}-api", "--wait", expect=None).payload
    assert d1["outcome"] == "passed", d1
    d2 = cli("dispatch", run, "assess", "--worker", f"{pairs[1][0]}-api", "--wait", expect=None).payload
    assert d2["outcome"] == "needs_human", d2
    assert cli.run("decide", run, "assess", "approve", "--note", "Live check.")["run_completed"] is True
