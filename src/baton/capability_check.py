"""Capability checks (§6.4; Decisions 0175, 0176, 0177; change 2026-11-model-assessment).

Baton ships a small set of short tasks per capability (``defaults/capability-checks.yaml``,
``baton-capability-checks/1``), each graded by code. ``baton workers check`` and the
setup page run them once per model and route, on the owner's request, after showing
an estimate of their cost:

* each task is a tiny packet (``manifest.json``, ``INSTRUCTIONS.md``, ``output_schema.json``)
  run through the profile's own adapter, exactly as a step's packet is, so API and
  harness routes take one path; a task with ``workspace`` files runs in read mode with
  those files as the working tree;
* a capability is ``verified`` (``by: check``) when all of its tasks pass and ``absent``
  when one fails, naming it; a task that could not run (no answer, an auth or quota
  failure) records nothing, and the profile stays due;
* a check never adds a capability, except ``structured_output`` and ``tool_use`` on an
  unjudged listing profile (0176, item 3): those are kept in the track record and
  ``workers setup`` adds them to the profile (``workspace_read`` follows from
  ``tool_use`` on an API route, §6.1);
* what each check cost and how long it took goes into the track record,
  ``$BATON_HOME/track-record.yaml`` (``baton-track-record/1``), keyed by profile
  (one model on one route), which ``workers check`` also reads to skip what is
  already checked under the current set version, unless the route is an alias
  (no ``model_id``) or the owner asks again.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from . import data
from .data import YamlError, load_yaml

FORMAT = "baton-capability-checks/1"
FILE = "capability-checks.yaml"
RECORD_FORMAT = "baton-track-record/1"
RECORD_FILE = "track-record.yaml"
RECORD_LOCK = ".track-record.lock"
#: Capabilities a passed check may add to an unjudged model's profile (0176, item 3).
ADDABLE = ("structured_output", "tool_use")
GRADERS = ("schema", "equals", "contains_all", "excludes", "words", "headings", "numbered", "tool_called")
#: Seconds one task may take.
TASK_TIMEOUT_S = 180
#: Tasks run at once, across all the profiles being checked.
PARALLEL = 6
#: Input tokens assumed for the runner's system message and reply schema, per call.
OVERHEAD_TOKENS = 700
#: Model calls assumed for a task that offers tools.
TOOL_TASK_CALLS = 3
SUBSCRIPTION = "included in the subscription"


class CheckError(Exception):
    pass


# ---------------------------------------------------------------------------
# The check set
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    capability: str
    id: str
    prompt: str
    output_schema: dict[str, Any]
    grade: tuple[dict[str, Any], ...]
    workspace: dict[str, str] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    expect_tokens: int = 200


@dataclass(frozen=True)
class CheckSet:
    version: int
    tasks: tuple[Task, ...]

    def capabilities(self) -> list[str]:
        return list(dict.fromkeys(t.capability for t in self.tasks))

    def for_capability(self, cap: str) -> list[Task]:
        return [t for t in self.tasks if t.capability == cap]


def set_path() -> Path:
    return data.path("defaults") / FILE


def parse(raw: Any, source: str = FILE, vocabulary: Iterable[str] | None = None) -> CheckSet:
    """Validate a check set; raises ``CheckError`` naming every problem."""
    from .runner_tools import TOOL_NAMES

    problems: list[str] = []
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise CheckError(f"{source}: expected format {FORMAT}")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        problems.append("version must be a positive whole number")
    known = set(vocabulary) if vocabulary is not None else None
    tasks: list[Task] = []
    seen: set[str] = set()
    for cap, items in (raw.get("checks") or {}).items():
        if known is not None and cap not in known:
            problems.append(f"checks.{cap}: not a capability in the vocabulary")
        if not isinstance(items, list) or not items:
            problems.append(f"checks.{cap}: a list of tasks is required")
            continue
        for i, t in enumerate(items):
            where = f"checks.{cap}[{i}]"
            if not isinstance(t, dict):
                problems.append(f"{where}: must be a mapping")
                continue
            tid = t.get("id")
            if not isinstance(tid, str) or not tid:
                problems.append(f"{where}: id is required")
            elif tid in seen:
                problems.append(f"{where}: id {tid!r} is used twice")
            seen.add(str(tid))
            if not isinstance(t.get("prompt"), str) or not t["prompt"].strip():
                problems.append(f"{where}: prompt is required")
            if not isinstance(t.get("output_schema"), dict):
                problems.append(f"{where}: output_schema must be a mapping")
            grade = t.get("grade")
            if not isinstance(grade, list) or not grade:
                problems.append(f"{where}: grade must list at least one grader")
                grade = []
            for g in grade:
                if not isinstance(g, dict) or g.get("type") not in GRADERS:
                    problems.append(f"{where}: grader {g!r} is not one of {', '.join(GRADERS)}")
                elif g["type"] not in ("schema", "tool_called") and not g.get("field"):
                    problems.append(f"{where}: grader {g['type']} needs a field")
            tools = t.get("tools") or []
            bad = [x for x in tools if x not in TOOL_NAMES]
            if bad:
                problems.append(f"{where}: tools {', '.join(map(str, bad))} are not runner tools")
            ws = t.get("workspace") or {}
            if not isinstance(ws, dict) or any(not isinstance(v, str) or ".." in Path(k).parts or Path(k).is_absolute() for k, v in ws.items()):
                problems.append(f"{where}: workspace must map relative paths to text")
                ws = {}
            if problems:
                continue
            tasks.append(Task(cap, tid, t["prompt"], t["output_schema"], tuple(grade), dict(ws), tuple(tools), int(t.get("expect_tokens") or 200)))
    if problems:
        raise CheckError(f"{source}: " + "; ".join(problems))
    return CheckSet(version, tuple(tasks))


def load_set(path: Path | None = None) -> CheckSet:
    from . import vocab as vocab_mod

    p = path or set_path()
    try:
        raw = load_yaml(p)
    except (OSError, YamlError) as e:
        raise CheckError(f"{p}: {e}") from e
    return parse(raw, str(p), vocab_mod.load(vocab_mod.DEFAULT).capabilities)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def _norm(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = " ".join(v.split()).casefold()
        return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else s
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def _words(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text))


def grade(task: Task, envelope: dict[str, Any] | None, tool_log: list[dict[str, Any]] | None) -> list[str]:
    """Why the task failed (empty: it passed). ``tool_log`` is None when the route keeps none (a harness)."""
    import jsonschema

    if not isinstance(envelope, dict):
        return ["no result was written"]
    if envelope.get("status") != "completed":
        return [f"the result's status is {envelope.get('status')!r}" + (f": {envelope.get('notes')}" if envelope.get("notes") else "")]
    out = envelope.get("output")
    if not isinstance(out, dict):
        return ["the result has no output object"]
    reasons: list[str] = []
    for g in task.grade:
        kind, f = g["type"], g.get("field")
        value = out.get(f) if f else None
        text = value if isinstance(value, str) else ""
        if kind == "schema":
            errors = sorted(jsonschema.Draft202012Validator(task.output_schema).iter_errors(out), key=lambda e: list(e.path))
            if errors:
                reasons.append("output does not match the schema: " + errors[0].message)
        elif kind == "equals":
            if _norm(value) != _norm(g.get("value")):
                reasons.append(f"{f} is {value!r}, not {g.get('value')!r}")
        elif kind == "contains_all":
            missing = [v for v in g.get("values", []) if str(v).casefold() not in text.casefold()]
            if missing:
                reasons.append(f"{f} lacks {', '.join(map(str, missing))}")
        elif kind == "excludes":
            found = [v for v in g.get("values", []) if re.search(rf"\b{re.escape(str(v))}\b", text, re.IGNORECASE)]
            if found:
                reasons.append(f"{f} uses {', '.join(map(str, found))}")
        elif kind == "words":
            n = _words(text)
            if (g.get("min") is not None and n < g["min"]) or (g.get("max") is not None and n > g["max"]):
                reasons.append(f"{f} has {n} words (wanted {g.get('min', 0)} to {g.get('max', 'any')})")
        elif kind == "headings":
            n = len(re.findall(r"(?m)^## \S", text))
            others = len(re.findall(r"(?m)^#{1,6} \S", text)) - n
            if n != g["count"] or others:
                reasons.append(f"{f} has {n} `##` headings" + (f" and {others} others" if others else "") + f" (wanted {g['count']})")
        elif kind == "numbered":
            n = len(re.findall(r"(?m)^\s*\d+[.)]\s+\S", text))
            if n != g["count"]:
                reasons.append(f"{f} has {n} numbered lines (wanted {g['count']})")
        elif kind == "tool_called" and tool_log is not None:
            if not any(r.get("tool") == g["tool"] and "refused" not in r for r in tool_log):
                reasons.append(f"no successful {g['tool']} call")
    return reasons


# ---------------------------------------------------------------------------
# One task through a profile's adapter
# ---------------------------------------------------------------------------


@dataclass
class TaskOutcome:
    task: Task
    passed: bool = False
    reasons: list[str] = field(default_factory=list)
    #: Set when the task could not run at all: nothing is recorded for its capability.
    error: str | None = None
    seconds: float = 0.0
    usage: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task": self.task.id, "passed": self.passed, "seconds": round(self.seconds, 2)}
        if self.reasons:
            out["reasons"] = self.reasons
        if self.error:
            out["error"] = self.error
        if self.usage:
            out["usage"] = self.usage
        return out


def instructions(task: Task, api: bool) -> str:
    lines = ["# A capability check", "", task.prompt.rstrip(), ""]
    if task.workspace:
        lines += ["The project's working tree holds the files you need. Read them; do not change them.", ""]
    if not api:
        lines += [
            "## Protocol", "",
            "- This directory is the packet. Do not modify anything in it.",
            "- Write `../result/result.json` (relative to this packet directory), a JSON object:",
            "", "```json",
            json.dumps({"protocol": "baton-packet/1", "packet_sha256": "<copy from manifest.json>", "status": "completed | failed",
                        "output": "<an object matching output_schema.json>", "artifacts": [], "notes": "",
                        "questions_for_human": [], "process_feedback": []}, indent=2),
            "```", "",
        ]
    lines += ["## Output schema", "", "```json", json.dumps(task.output_schema, indent=2), "```", ""]
    return "\n".join(lines)


def write_packet(root: Path, task: Task, api: bool) -> tuple[Path, Path, Path | None]:
    """``(packet, result, workspace)`` for one task, under ``root``."""
    packet, result = root / "packet", root / "result"
    packet.mkdir(parents=True)
    result.mkdir()
    workspace = None
    if task.workspace:
        workspace = root / "workspace"
        for rel, text in task.workspace.items():
            p = workspace / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    manifest: dict[str, Any] = {
        "protocol": "baton-packet/1", "packet_sha256": f"capability-check-{task.id}", "required_artifacts": [], "optional_artifacts": [],
        "inputs": [], "protected_paths": [], "workspace": "read" if workspace else "none",
    }
    if api and task.tools:
        manifest["tools"] = list(task.tools)
        manifest["tool_calls"] = 10
    (packet / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (packet / "output_schema.json").write_text(json.dumps(task.output_schema, indent=2), encoding="utf-8")
    (packet / "INSTRUCTIONS.md").write_text(instructions(task, api), encoding="utf-8")
    return packet, result, workspace


Runner = Callable[[Path, str, Any, Task], TaskOutcome]


def run_task(home: Path, name: str, profile: Any, task: Task) -> TaskOutcome:
    """Run one task through ``profile``'s adapter and grade it."""
    from . import adapters
    from .doctor import _run
    from .engine import classify_exit
    from .profiles import SetupError, build_env, executable_for

    adapter = adapters.ADAPTERS.get(profile.adapter)
    if adapter is None or profile.adapter in ("manual", "program"):
        return TaskOutcome(task, error=f"adapter {profile.adapter} cannot take a check")
    api = profile.adapter == "litellm_api"
    with tempfile.TemporaryDirectory(prefix="baton-check-") as tmp:
        root = Path(tmp)
        packet, result, workspace = write_packet(root, task, api)
        cwd = workspace or (root / "empty")
        cwd.mkdir(exist_ok=True)
        try:
            env = build_env(profile, home=home, packet_dir=packet, result_dir=result, workspace=workspace,
                            config_home_var=getattr(adapter, "config_home_var", None), resolve=bool(executable_for(profile)))
            argv = adapter.command(profile, packet, result, workspace, "read" if workspace else "none")
        except SetupError as e:
            return TaskOutcome(task, error=str(e))
        started = time.monotonic()
        child = _run(argv, env, cwd, Path(home) / "logs" / "workers" / f"{name}-check-{task.id}.log", TASK_TIMEOUT_S)
        seconds = time.monotonic() - started
        usage = _read_json(root / "usage.json")
        if child.timed_out:
            return TaskOutcome(task, error=f"no answer within {TASK_TIMEOUT_S} s", seconds=seconds, usage=usage)
        envelope = _read_json(result / "result.json")
        if child.exit_code != 0 and envelope is None:
            cls = classify_exit(child, adapter.failure_signals)
            return TaskOutcome(task, error=f"{cls['class']} ({cls['code']}): {cls['message']}", seconds=seconds, usage=usage)
        log = None
        if api:
            p = root / "tool_calls.jsonl"
            log = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.is_file() else []
        reasons = grade(task, envelope, log)
        return TaskOutcome(task, not reasons, reasons, None, seconds, usage)


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: the worker wrote nothing, or nothing readable
        return None


# ---------------------------------------------------------------------------
# The track record
# ---------------------------------------------------------------------------


def record_path(home: Path) -> Path:
    return Path(home) / RECORD_FILE


def load_record(home: Path) -> dict[str, Any]:
    """profile -> its record. Missing file: none."""
    p = record_path(home)
    if not p.is_file():
        return {}
    try:
        raw = load_yaml(p) or {}
    except YamlError as e:
        raise CheckError(f"{p}: {e}") from e
    if not isinstance(raw, dict) or raw.get("format", RECORD_FORMAT) != RECORD_FORMAT:
        raise CheckError(f"{p}: expected a {RECORD_FORMAT} mapping")
    return {str(k): v for k, v in (raw.get("profiles") or {}).items() if isinstance(v, dict)}


def _save_record(home: Path, profiles: dict[str, Any]) -> None:
    from .resources import _atomic_write

    body = {"format": RECORD_FORMAT, "profiles": dict(sorted(profiles.items()))}
    header = "# What Baton has seen each model do, per route (baton-track-record/1, §6.4). Written by Baton.\n"
    _atomic_write(record_path(home), header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True))


def added(home: Path) -> dict[str, list[str]]:
    """Capabilities checks added to unjudged profiles: profile -> capabilities (0176, item 3)."""
    try:
        rec = load_record(home)
    except CheckError:  # expected: an unreadable track record adds nothing; `workers check` reports it when it next writes
        return {}
    return {n: list(r["checks"]["adds"]) for n, r in rec.items() if isinstance(r.get("checks"), dict) and r["checks"].get("adds")}


# ---------------------------------------------------------------------------
# Planning, estimating and running
# ---------------------------------------------------------------------------


@dataclass
class Planned:
    name: str
    body: dict[str, Any]
    capabilities: list[str]
    #: Of those, the ones checked to be added (not claimed).
    adding: list[str]
    tasks: list[Task]


def unjudged(body: dict[str, Any], judged: set[str]) -> bool:
    """A listing profile with no judgment: tier ``basic`` from 0110, its model in no data or overlay."""
    return bool((body.get("generated") or {}).get("listing")) and body.get("model_id") not in judged


def plan(home: Path, cs: CheckSet, names: list[str] | None, *, free: bool = False, provider: str | None = None,
         again: bool = False) -> tuple[list[Planned], list[dict[str, str]]]:
    """What to check: ``(planned, skipped)``. ``names`` None: every generated profile the filters keep."""
    from . import capability_states as cs_mod
    from . import known_workers as kw_mod
    from .resources import machine_claims, read_generated_dir, switched_off

    generated = {n: b for n, (_p, b) in read_generated_dir(home).items() if isinstance(b, dict)}
    claims = machine_claims(home)
    states = cs_mod.load(home)
    record = load_record(home)
    off = switched_off(home)
    from . import vocab as vocab_mod

    try:
        judged = set(kw_mod.load_with_overlay(vocab_mod.load(vocab_mod.DEFAULT), home, kw_mod.default_path()).models)
    except kw_mod.KnownWorkersError:  # expected: an invalid overlay refuses setup itself, which says so; here no model counts as judged
        judged = set()
    skipped: list[dict[str, str]] = []
    out: list[Planned] = []
    wanted = list(names) if names else sorted(generated)
    for name in wanted:
        body = generated.get(name)
        if body is None:
            skipped.append({"profile": name, "reason": "not a model Baton set up on this machine (`baton workers status` lists them)"})
            continue
        if names is None:
            price = body.get("price") or {}
            if free and not price.get("free"):
                continue
            if provider and body.get("provider") != provider and body.get("resource") != provider:
                continue
            if name in off:
                continue
        if body.get("adapter") in ("manual", "program"):
            skipped.append({"profile": name, "reason": "a person or a program: nothing to check"})
            continue
        checked = (record.get(name) or {}).get("checks") or {}
        if not again and body.get("model_id") and checked.get("set_version") == cs.version and checked.get("complete"):
            skipped.append({"profile": name, "reason": f"already checked on {checked.get('date')} (set {cs.version}); ask again to repeat"})
            continue
        claimed = set(claims.get(name, []))
        caps, adding = [], []
        for cap in cs.capabilities():
            st = cs_mod.state_of(states, name, cap)
            if st.state == "absent" and st.by == "owner":
                continue  # the owner said so; a check does not argue
            if cap in claimed:
                caps.append(cap)
            elif cap in ADDABLE and unjudged(body, judged) and body.get("adapter") == "litellm_api":
                caps.append(cap)
                adding.append(cap)
            elif cap == "workspace_read" and body.get("adapter") == "litellm_api" and ("tool_use" in claimed or "tool_use" in adding):
                caps.append(cap)  # the runner provides it with tool_use (§6.1)
        if not caps:
            skipped.append({"profile": name, "reason": "claims none of the capabilities the checks cover"})
            continue
        out.append(Planned(name, body, caps, adding, [t for c in caps for t in cs.for_capability(c)]))
    return out, skipped


def _task_tokens(task: Task, api: bool) -> tuple[int, int]:
    calls = TOOL_TASK_CALLS if (api and task.tools) else 1
    text = len(instructions(task, api)) // 4 + sum(len(v) for v in task.workspace.values()) // 4
    return (text + OVERHEAD_TOKENS) * calls, task.expect_tokens + 60 * (calls - 1)


def estimate(planned: list[Planned]) -> dict[str, Any]:
    """Tokens and cost per profile and in all, from list prices. Unknown prices are said so, never guessed."""
    rows, total, unknown = [], 0.0, []
    for p in planned:
        api = p.body.get("adapter") == "litellm_api"
        tin = tout = 0
        for t in p.tasks:
            i, o = _task_tokens(t, api)
            tin, tout = tin + i, tout + o
        row: dict[str, Any] = {"profile": p.name, "model_id": p.body.get("model_id"), "tasks": len(p.tasks), "capabilities": p.capabilities,
                               "adding": p.adding, "input_tokens": tin, "output_tokens": tout}
        price = p.body.get("price") if isinstance(p.body.get("price"), dict) else None
        if (p.body.get("auth") or {}).get("mode") == "cli_login":
            row["cost"] = SUBSCRIPTION
        elif price and price.get("free"):
            row["cost_usd"] = 0.0
        elif price and price.get("input") is not None and price.get("output") is not None:
            row["cost_usd"] = round(tin * float(price["input"]) / 1e6 + tout * float(price["output"]) / 1e6, 6)
            total += row["cost_usd"]
        else:
            row["cost"] = "unknown: the provider lists no price"
            unknown.append(p.name)
        rows.append(row)
    return {"profiles": rows, "tasks": sum(len(p.tasks) for p in planned), "cost_usd": round(total, 6), "unknown_price": unknown}


def _harness_version(profile: Any, home: Path) -> str | None:
    from . import adapters
    from .engine import harness_version
    from .profiles import SetupError, build_env, executable_for

    adapter = adapters.ADAPTERS.get(profile.adapter)
    exe = executable_for(profile)
    if not exe or not hasattr(adapter, "version_argv"):
        return None
    try:
        env = build_env(profile, home=home, config_home_var=getattr(adapter, "config_home_var", None))
    except SetupError:  # expected: the profile cannot start here; its tasks already failed with the reason
        return None
    return harness_version(env.resolved.executable if env.resolved else exe, adapter, env.env)


def check(home: Path, names: list[str] | None = None, *, free: bool = False, provider: str | None = None, again: bool = False,
          run: bool = True, runner: Runner = run_task, today: dt.date | None = None, set_file: Path | None = None,
          resetup: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Plan, estimate and (``run``) check. Returns ``{set_version, estimate, skipped, results}``.

    With ``run`` false nothing is called: the estimate is what the owner sees first.
    """
    from . import capability_states as cs_mod
    from .locks import file_lock
    from .models import WorkerProfile

    home = Path(home)
    today = today or dt.date.today()
    cs = load_set(set_file)
    planned, skipped = plan(home, cs, names, free=free, provider=provider, again=again)
    out: dict[str, Any] = {"set_version": cs.version, "estimate": estimate(planned), "skipped": skipped, "results": []}
    if not run or not planned:
        return out
    profiles = {p.name: WorkerProfile.model_validate({k: v for k, v in p.body.items() if k != "generated"}) for p in planned}
    jobs = [(p, t) for p in planned for t in p.tasks]
    outcomes: dict[str, list[TaskOutcome]] = {p.name: [] for p in planned}
    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(runner, home, p.name, profiles[p.name], t): p.name for p, t in jobs}
        for f in concurrent.futures.as_completed(futures):
            outcomes[futures[f]].append(f.result())
    added_any = False
    with file_lock(home / RECORD_LOCK):
        record = load_record(home)
        for p in planned:
            res = _settle(home, p, outcomes[p.name], cs, today, profiles[p.name], cs_mod)
            prev = (record.get(p.name) or {}).get("checks") or {}
            adds = sorted(set(prev.get("adds") or []) - set(res["capabilities_absent"]) | set(res["added"]))
            added_any = added_any or bool(res["added"])
            entry = dict(record.get(p.name) or {})
            if p.body.get("model_id"):
                entry["model_id"] = p.body["model_id"]
            entry["checks"] = {"set_version": cs.version, "date": today.isoformat(), "complete": res["complete"],
                               "capabilities": res["by_capability"], **({"adds": adds} if adds else {}),
                               "seconds": res["seconds"], **({"cost_usd": res["cost_usd"]} if res["cost_usd"] is not None else {}),
                               **({"cost": res["cost"]} if res.get("cost") else {})}
            record[p.name] = entry
            out["results"].append(res)
        _save_record(home, record)
    if added_any:
        out["setup"] = (resetup or _resetup)(home)
    return out


def _resetup(home: Path) -> dict[str, Any]:
    from . import resources

    got = resources.setup(home)
    return {"refreshed": got["refreshed"]}


def _settle(home: Path, p: Planned, outcomes: list[TaskOutcome], cs: CheckSet, today: dt.date, profile: Any, cs_mod: Any) -> dict[str, Any]:
    """Record each capability's state from its tasks' outcomes; the profile's result."""
    hv = _harness_version(profile, home) if profile.adapter != "litellm_api" else None
    by_cap: dict[str, Any] = {}
    verified, absent, unchecked, added_caps = [], [], [], []
    for cap in p.capabilities:
        mine = [o for o in outcomes if o.task.capability == cap]
        errors = [o for o in mine if o.error]
        failed = [o for o in mine if not o.error and not o.passed]
        row: dict[str, Any] = {"passed": [o.task.id for o in mine if o.passed], "seconds": round(sum(o.seconds for o in mine), 2)}
        cost = _cost(mine)
        if cost is not None:
            row["cost_usd"] = cost
        if failed:
            row["failed"] = [{"task": o.task.id, "reasons": o.reasons} for o in failed]
            evidence = f"check set {cs.version}: failed " + "; ".join(f"{o.task.id} ({o.reasons[0]})" for o in failed)
            cs_mod.record(home, p.name, cap, "absent", by="check", evidence=evidence[:400], today=today, harness_version=hv,
                          set_version=cs.version)
            row["result"] = "absent"
            absent.append(cap)
        elif errors:
            row["result"] = "not checked"
            row["error"] = errors[0].error
            unchecked.append(cap)
        else:
            cs_mod.record(home, p.name, cap, "verified", by="check", evidence=f"check set {cs.version}: {len(mine)} of {len(mine)} tasks passed",
                          today=today, harness_version=hv, set_version=cs.version)
            row["result"] = "verified"
            verified.append(cap)
            if cap in p.adding:
                added_caps.append(cap)
        by_cap[cap] = row
    res: dict[str, Any] = {
        "profile": p.name, "model_id": p.body.get("model_id"), "verified": verified, "absent": absent, "not_checked": unchecked,
        "added": added_caps, "capabilities_absent": absent, "by_capability": by_cap, "complete": not unchecked,
        "seconds": round(sum(o.seconds for o in outcomes), 2), "cost_usd": _cost(outcomes),
        "tasks": [o.as_dict() for o in sorted(outcomes, key=lambda o: o.task.id)],
    }
    if (p.body.get("auth") or {}).get("mode") == "cli_login":
        res["cost"] = SUBSCRIPTION
    return res


def _cost(outcomes: list[TaskOutcome]) -> float | None:
    known = [o.usage.get("cost_usd") for o in outcomes if o.usage and isinstance(o.usage.get("cost_usd"), (int, float))]
    return round(sum(known), 6) if known else None


def summary(home: Path, name: str) -> dict[str, Any] | None:
    """A profile's last check, for ``workers status`` and the setup page."""
    try:
        rec = (load_record(home).get(name) or {}).get("checks")
    except CheckError:  # expected: an unreadable track record shows no last check; `workers check` reports it
        return None
    if not isinstance(rec, dict):
        return None
    return {k: rec[k] for k in ("set_version", "date", "complete", "cost_usd", "cost", "seconds", "adds") if k in rec} | {
        "results": {c: r.get("result") for c, r in (rec.get("capabilities") or {}).items()}}
