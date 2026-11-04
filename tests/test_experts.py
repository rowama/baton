"""Phase 12: experts (L7), the platform area and process feedback (§12).

Acceptance: packets contain only Director-selected references plus the index,
with hashes; a non-promoted answer is unreachable from any step; an
``executable_not_found`` failure opens an incident and preselects facts and
logs for the platform SME; a promoted platform fact appears in the next
platform packet; a skipped blocking gate is surfaced to the owner immediately.
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

from baton import refs as refgrammar
from baton import sme
from baton.engine import Api
from baton.packet import _resolve, _Unresolvable
from baton.redact import SENTINEL_PREFIX
from conftest import FIT_CHECK
from projectkit import FIT_INPUTS, GOOD_PROFILE, OWNER_PROFILE, VERDICT, Cli, git, make_git_project, make_home, packet_dir, write_result

FAKES = Path(__file__).resolve().parent / "fakes"
FIT_CAPS = ["structured_output", "long_form_writing", "technical_reasoning"]
SECRET = SENTINEL_PREFIX + "experts0042"
HOOK = """\
import json, os, sys
rec = {k: v for k, v in os.environ.items() if k.startswith("BATON_")}
rec["tag"] = sys.argv[2]
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\\n")
"""


def _cmdline(argv: list[str]) -> str:
    return shlex.join(argv) if os.name == "posix" else subprocess.list2cmdline(argv)


class Setup:
    def __init__(self, tmp_path: Path, *, hooks: bool = False, start: bool = True):
        self.tmp = tmp_path
        self.step_behavior = tmp_path / "step.json"
        self.sme_behavior = tmp_path / "sme.json"
        self.behave_step("good", output=GOOD_PROFILE)
        self.behave_sme("answer", answer="Saw: {inputs}")
        self.hook_log = tmp_path / "hooks.jsonl"
        (tmp_path / "hook.py").write_text(HOOK, encoding="utf-8")

        def command(name: str, argv: list[str], caps: list[str], vendor: str = "other") -> str:
            return f"{name}:\n  adapter: command\n  vendor: {vendor}\n  command: {json.dumps(_cmdline(argv))}\n  capabilities: {json.dumps(caps)}\n  tier: strong\n"

        profiles = OWNER_PROFILE
        profiles += command("bot", [sys.executable, str(FAKES / "scripted_worker.py"), "{packet}", "{result}", str(self.step_behavior)], FIT_CAPS)
        profiles += command("bot127", [sys.executable, "-c", "import sys; print('mytool: command not found'); sys.exit(127)"], FIT_CAPS, "other2")
        profiles += command("sage", [sys.executable, str(FAKES / "fake_sme.py"), "{packet}", "{result}", str(self.sme_behavior)],
                            ["long_form_writing", "technical_reasoning"])
        profiles += command("ops", [sys.executable, str(FAKES / "fake_sme.py"), "{packet}", "{result}", str(self.sme_behavior)],
                            ["technical_reasoning", "shell"], "other3")
        profiles += "missing:\n  adapter: command\n  vendor: other4\n  command: \"definitely-missing-tool-xyz {packet}\"\n" \
                    f"  capabilities: {json.dumps(FIT_CAPS)}\n  tier: strong\n"
        self.project = make_git_project(tmp_path / "proj")
        self.home = make_home(tmp_path / "home", profiles)
        self.cli = Cli(self.project, self.home)
        self.cli.run("init", str(self.project))
        self.cli.run("vendor", str(FIT_CHECK))
        (self.project / "README.md").write_text(f"# Contract review\n\nThe staging token is {SECRET}.\n", encoding="utf-8")
        py = self.project / ".baton" / "project.yaml"
        cfg = yaml.safe_load(py.read_text(encoding="utf-8"))
        cfg["sme"] = {"project": {"preferred_profiles": ["sage"]}, "process": {"preferred_profiles": ["sage"]},
                      "platform": {"preferred_profiles": ["ops"]}}
        if hooks:
            hook = _cmdline([sys.executable, str(tmp_path / "hook.py"), str(self.hook_log)])
            cfg["hooks"] = {"on_complete": hook + " complete", "on_needs_human": hook + " needs_human", "on_platform_failure": hook + " platform"}
        py.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "Adopt Baton")
        self.run = self.cli.run("start", "fit-check", "--inputs", json.dumps(FIT_INPUTS))["run_id"] if start else None

    def behave_step(self, mode: str, **kw: object) -> None:
        self.step_behavior.write_text(json.dumps({"mode": mode, **kw}), encoding="utf-8")

    def behave_sme(self, mode: str, **kw: object) -> None:
        self.sme_behavior.write_text(json.dumps({"mode": mode, **kw}), encoding="utf-8")

    @property
    def baton(self) -> Path:
        return self.project / ".baton"

    def api(self) -> Api:
        return Api.open(self.project, director_id="alice@host1", home=self.home)

    def project_events(self) -> list[dict]:
        p = self.baton / "project" / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def run_events(self) -> list[dict]:
        p = self.baton / "runs" / self.run / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def describe_passed(self) -> None:
        self.cli.run("dispatch", self.run, "describe", "--worker", "bot", "--wait")

    def hooks(self) -> list[dict]:
        return [json.loads(x) for x in self.hook_log.read_text(encoding="utf-8").splitlines()] if self.hook_log.exists() else []

    def ask(self, *args: str, expect: int = 0) -> dict:
        return self.cli.run("ask-sme", *args, "--wait", "--timeout", "60", expect=expect)


def _manifest(packet: str | Path) -> dict:
    return json.loads((Path(packet) / "manifest.json").read_text(encoding="utf-8"))


def _sha(p: Path) -> str:
    import hashlib

    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Packets: only Director-selected references plus the index, with hashes
# ---------------------------------------------------------------------------


def test_packet_holds_only_selected_refs_plus_index_with_hashes(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.describe_passed()
    out = s.ask("project", "Is a weekly review realistic?", "--run", s.run, "--ref", "step:describe", "--ref", "project:README.md")
    assert out["state"] == "answered" and out["turns"][0]["worker"] == "sage"  # project.yaml preferred_profiles
    m = _manifest(out["turns"][0]["packet"])
    pdir = Path(out["turns"][0]["packet"])
    assert {i["ref"] for i in m["inputs"]} == {"step:describe", "project:README.md"}
    assert all(i["group"] == "selected" for i in m["inputs"])
    for i in m["inputs"]:
        assert _sha(pdir / i["path"]) == i["sha256"]
    labels = [i["label"] for i in m["inputs"]]
    assert "accepted Profile the idea, attempt 1: output" in labels
    index = json.loads((pdir / "index.json").read_text(encoding="utf-8"))
    titles = {e["ref"]: e["title"] for e in index}
    assert "record:describe" in titles and "summary" in titles and "step:describe" not in titles
    assert all(set(e) == {"ref", "title"} for e in index)  # titles only
    # Nothing outside the selection or index: the run's other records are not in the packet.
    files = sorted(p.relative_to(pdir).as_posix() for p in pdir.rglob("*") if p.is_file())
    assert files == sorted(["manifest.json", "INSTRUCTIONS.md", "output_schema.json", "index.json", *(i["path"] for i in m["inputs"])])
    answer = out["turns"][0]["answer"]
    assert answer["answer"] == "Saw: project:README.md, step:describe" and answer["sources_used"] == ["project:README.md", "step:describe"]
    req = [e for e in s.run_events() if e["type"] == "sme_requested"][0]["data"]
    assert req["packet_sha256"] == m["packet_sha256"] and {r["ref"] for r in req["refs"]} == {"step:describe", "project:README.md"}
    # The packet hash is reproducible from the files (same formula as step packets).
    from baton.packet import verify_packet

    assert verify_packet(pdir) == (m["packet_sha256"], [])


def test_refs_are_scoped_by_subject_and_people_are_never_consulted_directly(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    r = s.cli.run("ask-sme", "project", "q", "--ref", "facts", expect=1)
    assert r["error"] == "sme.refs" and "not in a project expert's scope" in r["message"]
    r = s.cli.run("ask-sme", "process", "q", "--ref", "events", expect=1)
    assert "consult with --run" in r["message"]
    r = s.cli.run("ask-sme", "project", "q", "--ref", "nonsense:x", expect=1)
    assert "not an expert reference" in r["message"]
    r = s.cli.run("ask-sme", "project", "q", "--ref", "project:../etc/passwd", expect=1)
    assert "inside the project" in r["message"]
    el = s.cli.run("sme-eligible", "project")
    assert [e["profile"] for e in el["eligible"]][0] == "sage"
    owner = next(x for x in el["excluded"] if x["profile"] == "owner")
    assert "never consulted directly" in owner["reasons"][0]
    r = s.cli.run("ask-sme", "project", "q", "--worker", "owner", expect=1)
    assert r["error"] == "sme.ineligible"
    assert s.cli.run("ask-sme", "platform", "q", "--worker", "sage", expect=1)["error"] == "sme.ineligible"  # no shell


# ---------------------------------------------------------------------------
# Isolation and promotion (§12.2)
# ---------------------------------------------------------------------------


def test_answer_is_unreachable_from_steps_until_promoted(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.behave_sme("answer", answer="Treat renewals as a separate idea.")
    s.describe_passed()
    out = s.ask("project", "Do renewals count?", "--run", s.run, "--ref", "step:describe")
    c = out["consultation"]
    # No reference grammar reaches an answer.
    for raw in (f"sme.{c}", "sme.answer", f"steps.sme.output", "experts.answer"):
        try:
            ref = refgrammar.parse(raw)
        except refgrammar.RefSyntaxError:
            continue
        assert ref.kind == "step_output" and ref.step == "sme"  # a step id; the loader rejects unknown steps
    # The next step's packet carries nothing of it.
    s.behave_step("good", output=VERDICT)
    s.cli.run("dispatch", s.run, "assess", "--worker", "bot", "--wait", expect=4)
    apk = packet_dir(s.project, s.run, "assess", 1)
    assert not any("renewals" in p.read_text(encoding="utf-8", errors="replace") for p in apk.rglob("*") if p.is_file())
    api = s.api()
    ctx = api._ctx(s.run)
    decision_ids = [e["data"]["decision_id"] for e in s.run_events() if e["type"] == "human_decision" and "decision_id" in e["data"]]
    assert decision_ids == []
    with pytest.raises(_Unresolvable):
        _resolve(ctx, ctx.record(), "advice", "human.d1")
    # Promotion needs the owner's words; then a step may reference it.
    assert s.cli.run("promote-sme", c, "decision", "--note", " ", expect=1)["error"] == "sme.no_note"
    p = s.cli.run("promote-sme", c, "decision", "--note", "Yes, take that as decided.", expect=4)  # assess awaits the owner
    assert p["reference"] == f"human.{p['decision_id']}"
    value = _resolve(ctx, ctx.record(), "advice", p["reference"]).inline
    assert value == {"decision_id": p["decision_id"], "decision": "Treat renewals as a separate idea.", "note": "Yes, take that as decided."}
    prom = [e for e in s.run_events() if e["type"] == "sme_promoted"][0]
    assert prom["actor"] == "human" and prom["data"]["target"] == "decision" and prom["data"]["note"] == "Yes, take that as decided."
    # A checkpoint carried the decision.
    assert "expert answer promoted" in git(s.project, "log", "-1", "--format=%s")


def test_lesson_and_proposal_promotions_write_project_files(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.behave_sme("answer", answer="When a profile is vague, ask for one example occurrence, because scoring needs it.")
    out = s.ask("process", "How could describe go faster?", "--ref", "stats", "--ref", "recipe:fit-check@2")
    c = out["consultation"]
    s.cli.run("promote-sme", c, "lesson", "--note", "Good lesson.")
    lessons = (s.baton / "process" / "lessons.md").read_text(encoding="utf-8")
    assert "ask for one example occurrence" in lessons and f"origin: consultation {c}" in lessons and "confirmations: 1" in lessons
    pr = s.cli.run("promote-sme", c, "proposal", "--note", "Propose it to the maintainer.", "--text", "Add an example field to describe.")
    text = Path(pr["path"]).read_text(encoding="utf-8")
    assert "Add an example field to describe." in text and "never edits a vendored recipe" in text
    assert "baton(project): expert answer" in git(s.project, "log", "-1", "--format=%s")
    assert s.cli.run("check")["ok"]


# ---------------------------------------------------------------------------
# The platform area (§12.3)
# ---------------------------------------------------------------------------


def test_executable_not_found_opens_incident_and_preselects_facts_and_logs(tmp_path: Path) -> None:
    s = Setup(tmp_path, hooks=True)
    d = s.cli.run("dispatch", s.run, "describe", "--worker", "bot127", "--wait", expect=4)
    assert d["outcome"] == "escalated" and any("executable_not_found" in r for r in d["reasons"])
    opened = [e for e in s.project_events() if e["type"] == "platform_incident_opened"]
    assert len(opened) == 1
    inc = opened[0]["data"]
    assert (inc["run"], inc["step_path"], inc["attempt"], inc["class"], inc["code"]) == (s.run, "describe", 1, "platform", "executable_not_found")
    assert inc["refs"] == ["facts", f"log:{s.run}:describe@1"]
    # The hook that woke the platform side names the incident.
    plat = [h for h in s.hooks() if h["tag"] == "platform"]
    assert plat and plat[-1]["BATON_INCIDENT"] == inc["incident"]
    st = s.cli.run("status", s.run, expect=4)
    esc = next(p for p in st["pending_decisions"] if p["kind"] == "escalation")
    assert esc["incident"] == inc["incident"]
    assert s.cli.run("board", expect=4)["incidents"][0]["id"] == inc["incident"]
    # The platform expert's packet preselects the facts, the incident and the failed attempt's log.
    out = s.ask("platform", "Why did describe fail?", "--run", s.run, expect=4)  # describe is escalated
    m = _manifest(out["turns"][0]["packet"])
    auto = {i["ref"] for i in m["inputs"] if i["group"] == "auto"}
    assert auto == {"facts", f"incident:{inc['incident']}", f"log:{s.run}:describe@1"}
    pdir = Path(out["turns"][0]["packet"])
    log_item = next(i for i in m["inputs"] if i["ref"].startswith("log:"))
    assert "mytool: command not found" in (pdir / log_item["path"]).read_text(encoding="utf-8")
    # Resolving it readies the step once (the one automatic retry, §8.8).
    r = s.cli.run("platform-incident", "resolve", inc["incident"], "--fix", "Installed mytool on the runtime host.")
    assert r["readied"] == [{"run": s.run, "step_path": "describe", "attempt": 1}]
    ready = [e for e in s.run_events() if e["type"] == "step_ready" and e["data"].get("after_incident")]
    assert len(ready) == 1 and s.cli.run("status", s.run)["ready"] == ["describe"]
    assert s.cli.run("board")["incidents"] == []
    assert s.cli.run("platform-incident", "resolve", inc["incident"], "--fix", "again", expect=1)["error"] == "incident.resolved"
    assert s.cli.run("check")["ok"]


def test_dispatch_refused_for_a_missing_executable_opens_an_incident(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    r = s.cli.run("dispatch", s.run, "describe", "--worker", "missing", expect=1)
    assert r["error"] == "platform.executable_not_found" and "platform incident inc_" in r["message"]
    inc = s.cli.run("platform-incident", "list")["incidents"][0]
    assert inc["status"] == "open" and inc["attempt"] is None and inc["worker"] == "missing" and inc["refs"] == ["facts"]
    assert any("open platform incident" in w for w in s.cli.run("detect", expect=None)["warnings"])


def test_promoted_platform_fact_appears_in_the_next_platform_packet(tmp_path: Path) -> None:
    s = Setup(tmp_path, start=False)
    s.behave_sme("answer", answer="mytool is installed under /opt/tools/bin on the runtime host.")
    first = s.ask("platform", "Where is mytool?")
    m1 = _manifest(first["turns"][0]["packet"])
    facts1 = (Path(first["turns"][0]["packet"]) / next(i["path"] for i in m1["inputs"] if i["ref"] == "facts")).read_text(encoding="utf-8")
    assert "/opt/tools/bin" not in facts1
    c = first["consultation"]
    assert first["run_id"] is None and (s.baton / "project" / "sme" / c / "turn-1" / "packet").is_dir()
    s.cli.run("promote-sme", c, "fact", "--note", "Right, record it.")
    assert "/opt/tools/bin" in (s.baton / "platform" / "facts.md").read_text(encoding="utf-8")
    assert any(e["type"] == "platform_fact_recorded" for e in s.project_events())
    second = s.ask("platform", "And where is its config?")
    m2 = _manifest(second["turns"][0]["packet"])
    facts2 = (Path(second["turns"][0]["packet"]) / next(i["path"] for i in m2["inputs"] if i["ref"] == "facts")).read_text(encoding="utf-8")
    assert "mytool is installed under /opt/tools/bin" in facts2 and f"expert consultation {c} turn 1" in facts2
    # Facts recorded directly are there too, with source and date; project records are committed.
    s.cli.run("platform-fact", "The service listens on 8080 in the container.", "--source", "owner")
    assert "8080" in (s.baton / "platform" / "facts.md").read_text(encoding="utf-8")
    assert git(s.project, "status", "--porcelain", ".baton/platform", ".baton/project") == ""
    assert s.cli.run("check")["ok"]


# ---------------------------------------------------------------------------
# Process feedback (§12.4)
# ---------------------------------------------------------------------------


def test_skipped_blocking_gate_is_surfaced_to_the_owner_at_once(tmp_path: Path) -> None:
    s = Setup(tmp_path, hooks=True)
    r = s.cli.run("feedback", "skipped_step", "The verdict was acted on before the owner accepted it.", "--run", s.run,
                  "--step", "assess", "--gate", "human", expect=4)
    ref = r["notice"]
    assert ref.startswith("skip:") and r["needs_owner"]
    hook = [h for h in s.hooks() if h["tag"] == "needs_human"]
    assert hook and hook[-1]["BATON_OUTCOME"] == "needs_human" and hook[-1]["BATON_STEP_PATH"] == "assess"
    types = [e["type"] for e in s.project_events()]
    assert "process_feedback" in types and "step_skip_recorded" in types
    st = s.cli.run("status", s.run, expect=4)
    notice = next(p for p in st["pending_decisions"] if p["kind"] == "skip_notice")
    assert notice["ref"] == ref and "acted on before the owner accepted it" in notice["prompt"]
    assert [x["run_id"] for x in s.cli.run("board", "--needs-me", expect=4)["runs"]] == [s.run]
    assert s.cli.run("decide", s.run, ref, "approve", expect=1)["error"] == "decide.bad_decision"
    s.cli.run("decide", s.run, ref, "acknowledge", "--note", "Noted; it won't happen again.")
    assert not any(p["kind"] == "skip_notice" for p in s.cli.run("status", s.run)["pending_decisions"])
    # Ordinary feedback surfaces nothing.
    r = s.cli.run("feedback", "friction", "The rubric is long.", "--run", s.run, "--step", "assess")
    assert "notice" not in r and not s.cli.run("status", s.run)["needs_owner"]
    assert s.cli.run("feedback", "skipped_step", "x", expect=1)["error"] == "feedback.needs_step"
    assert s.cli.run("check")["ok"]


def test_worker_process_feedback_reaches_the_project_log_and_stats(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.cli.run("dispatch", s.run, "describe", "--worker", "owner")
    write_result(packet_dir(s.project, s.run, "describe", 1), {"summary": "x"},
                 process_feedback=[{"kind": "confusing", "text": "The idea field was ambiguous."}, "too many questions"])
    s.cli.run("submit", s.run, "describe", expect=None)  # rejected by schema; feedback is still recorded
    fb = [e["data"] for e in s.project_events() if e["type"] == "process_feedback"]
    assert [(f["kind"], f["text"]) for f in fb] == [("confusing", "The idea field was ambiguous."), ("friction", "too many questions")]
    assert fb[0]["qualified"] == "fit-check@2/describe"
    out = s.ask("process", "Where is time going?", "--ref", "stats", "--ref", "feedback", "--run", s.run, "--ref", "events")
    pdir = Path(out["turns"][0]["packet"])
    m = _manifest(pdir)
    stats = json.loads((pdir / next(i["path"] for i in m["inputs"] if i["ref"] == "stats")).read_text(encoding="utf-8"))
    d = stats["steps"]["fit-check@2/describe"]
    assert d["attempts"] == 1 and d["rejected"] == 1 and d["runs"] == 1


def test_qualified_ids_drop_instances_and_iterations() -> None:
    assert sme.qualified("software-feature@1", "slices/x7f3a9c2/i2/implement") == "software-feature@1/slices/implement"
    assert sme.qualified("r@2", "design~review") == "r@2/design~review"
    assert sme.qualified("r@1", "g/a1b2/i1/h/c3d4/i3/s") == "r@1/g/h/s"


# ---------------------------------------------------------------------------
# Relay turns, proxies for people, handoff (§18 #17), transcripts (§18 #13)
# ---------------------------------------------------------------------------


def test_proxy_drafts_then_the_persons_reply_comes_back_as_an_attachment(tmp_path: Path) -> None:
    s = Setup(tmp_path, start=False)
    s.behave_sme("answer", answer="I drafted an email for the owner to send.", artifacts={"draft_email": "Dear Ms. Rivera, ..."},
                 awaiting={"who": "Ms. Rivera (county permits)", "what": "whether a shed under 120 sq ft needs a permit"})
    first = s.ask("project", "Does the shed need a permit?", "--contact", "Ms. Rivera, county permits office, by email")
    c = first["consultation"]
    assert first["state"] == "awaiting_reply" and first["contact"].startswith("Ms. Rivera")
    t1 = first["turns"][0]
    assert t1["awaiting"]["who"].startswith("Ms. Rivera") and Path(t1["artifacts"]["draft_email"]).read_text(encoding="utf-8").startswith("Dear")
    assert "never send" in (Path(t1["packet"]) / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    reply = tmp_path / "reply.txt"
    reply.write_text("No permit is needed under 120 sq ft. -- R. Rivera", encoding="utf-8")
    s.behave_sme("answer", answer="The reply settles it: no permit.")
    second = s.cli.run("sme-followup", c, "--attach", str(reply), "--wait", "--timeout", "60")
    assert second["state"] == "answered" and [t["turn"] for t in second["turns"]] == [1, 2]
    pdir = Path(second["turns"][1]["packet"])
    m = _manifest(pdir)
    att = next(i for i in m["inputs"] if i["group"] == "attachments")
    assert att["label"] == "attachment reply.txt, supplied by the owner; the reply of Ms. Rivera, county permits office, by email"
    assert (pdir / att["path"]).read_text(encoding="utf-8") == reply.read_text(encoding="utf-8") and _sha(pdir / att["path"]) == att["sha256"]
    prior = {i["ref"] for i in m["inputs"] if i["group"] == "prior"}
    assert prior == {"turn:1"}
    prior_files = [i["path"] for i in m["inputs"] if i["group"] == "prior"]
    assert any(p.endswith("draft_email.md") for p in prior_files) and any(p.endswith("turn-1.json") for p in prior_files)
    assert s.cli.run("sme-followup", c, expect=1)["error"] == "sme.empty_followup"


def test_handoff_is_generated_by_the_runtime_or_refused_with_a_reason(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.describe_passed()
    out = s.ask("project", "Is a weekly review realistic?", "--run", s.run, "--ref", "step:describe")
    h = s.cli.run("sme-handoff", out["consultation"])
    text = h["handoff"]
    assert "The project's owner will now talk with you directly" in text and "Is a weekly review realistic?" in text
    assert "accepted Profile the idea, attempt 1" in text and "Saw: step:describe" in text  # material and the earlier answer
    assert Path(h["path"]).read_text(encoding="utf-8") == text
    ev = [e for e in s.run_events() if e["type"] == "sme_requested" and e["data"].get("mode") == "handoff"][0]["data"]
    assert ev["handoff_sha256"] == h["sha256"] and ev["path"].endswith("handoff.md")
    # A platform expert relies on a shell: a pasted prompt cannot do its work.
    r = s.cli.run("ask-sme", "platform", "Why is the build slow?", "--mode", "handoff", expect=1)
    assert r["error"] == "sme.handoff_refused" and r["message"].startswith("A pastable handoff is impossible") and "shell" in r["message"]
    # ...unless the expert is a black box behind the command adapter.
    plat = s.ask("platform", "Why is the build slow?")
    assert s.cli.run("sme-handoff", plat["consultation"])["sha256"]
    # A handoff started from scratch records only the handoff.
    fresh = s.cli.run("ask-sme", "project", "Talk me through the rubric.", "--run", s.run, "--mode", "handoff")
    st = s.cli.run("sme", fresh["consultation"])
    assert st["state"] == "handed_off" and st["turns"] == [] and len(st["handoffs"]) == 1


def test_transcripts_are_kept_in_full_and_redacted(tmp_path: Path) -> None:
    s = Setup(tmp_path, start=False)
    s.behave_sme("answer", answer=f"The token {SECRET} should be rotated.", artifacts={"notes": f"token: {SECRET}"})
    out = s.ask("project", "Anything risky in the README?", "--ref", "project:README.md")
    tdir = s.baton / "project" / "sme" / out["consultation"] / "turn-1"
    for p in tdir.rglob("*"):
        if p.is_file():
            assert SECRET not in p.read_text(encoding="utf-8", errors="replace"), p
    assert "[REDACTED]" in out["turns"][0]["answer"]["answer"]
    assert (tdir / "result" / "result.json").is_file() and (tdir / "packet" / "INSTRUCTIONS.md").is_file()  # full transcript
    git(s.project, "add", "-A")
    git(s.project, "commit", "-qm", "wip")
    assert s.cli.run("check")["ok"]


def test_expert_failures_are_recorded_not_answers(tmp_path: Path) -> None:
    s = Setup(tmp_path, start=False)
    s.behave_sme("crash")
    out = s.ask("project", "q")
    t = out["turns"][0]
    assert out["state"] == "failed" and t["status"] == "failed" and t["classification"] == "unknown"
    s.behave_sme("bad")
    out = s.cli.run("sme-followup", out["consultation"], "--question", "again?", "--wait", "--timeout", "60")
    t = out["turns"][1]
    assert t["status"] == "rejected" and any("answer" in r for r in t["reasons"])
    assert s.cli.run("promote-sme", out["consultation"], "lesson", "--note", "ok", expect=1)["error"] == "sme.no_answer"


def test_async_turn_returns_at_once_and_wait_collects_it(tmp_path: Path) -> None:
    s = Setup(tmp_path, start=False)
    out = s.cli.run("ask-sme", "project", "q")
    assert out["turn"] == 1 and out["warnings"]  # no hook configured
    done = s.cli.run("sme", out["consultation"], "--wait", "--timeout", "60")
    assert done["state"] == "answered"
