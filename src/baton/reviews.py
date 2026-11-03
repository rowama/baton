"""Reviews (L4, §9): review steps, findings and dispositions, waivers, protected files.

Nothing here appends to a log; ``engine.py`` turns what this module computes
into events.

**Review steps.** A ``type: review`` gate is done by a separate reviewer. When
intake reaches the gate, the step stays ``verifying`` and the runtime readies a
review at ``<step_path>~review`` (``~review.<gate index>`` when the step has
several review gates). The review is an ordinary step to the state machine:
the Director picks a reviewer from ``eligible`` (the gate's
``reviewer_requires`` and ``independence``) and dispatches it. Its packet holds
the step's inputs, the result under review and the rubric; it returns
``baton:findings``. Its findings then decide the step's gate.

**Lines.** The findings of one review, evaluated again and again (attempts of
a step, iterations of a loop), form a *line*: ``<step path>#<gate>`` at top
level, ``<instance path>/<step id>#<gate>`` inside a group (the same across
iterations). A finding is identified by its line and the id the reviewer gave
it; reviewers are asked to reuse the id of a finding they still see.

**Statuses** (§9.2, §18 #12). At each evaluation every reported finding is
``open``, except one the owner accepted as a risk at the previous evaluation
(``accepted-risk``, carried while it is re-reported). ``fixed`` and
``rejected`` never close a finding at a gate: they are claims the next review
confirms (by not re-reporting the id) or refutes (by reporting it again).
A previous finding the next review does not report is ``resolved``.

**Waivers** (§9.3). One owner decision covers one gate occurrence: a failed
occurrence the step still holds, or else the next occurrence (``scope:
next``), consumed by the next evaluation of that gate (an event carrying
``waiver_seq``).
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .models import ReviewGate, SchemaGate, Step

REVIEW_MARK = "~review"
FINDINGS_REF = "baton:findings"
#: Gate names that are not declared gates (§9.3).
IMPLICIT_WAIVABLE = ("independence", "protected")
WORKER_DISPOSITIONS = ("fixed", "rejected")
DISPOSITIONS = ("fixed", "rejected", "accepted-risk")
#: Declared gate types a waiver may cover; human gates are decided, schema failures are rejections.
WAIVABLE_TYPES = ("script", "review", "findings")


# ---------------------------------------------------------------------------
# Review steps
# ---------------------------------------------------------------------------


def review_gate_indices(step: Step) -> list[int]:
    return [i for i, g in enumerate(step.gates) if isinstance(g, ReviewGate)]


def review_suffix(step: Step, gate_index: int) -> str:
    return REVIEW_MARK if len(review_gate_indices(step)) == 1 else f"{REVIEW_MARK}.{gate_index}"


def review_path(parent_path: str, step: Step, gate_index: int) -> str:
    return parent_path + review_suffix(step, gate_index)


def split_review(path: str) -> tuple[str, str] | None:
    """``(parent path, suffix)`` for a review path, else ``None``."""
    head, _, last = path.rpartition("/")
    if "~" not in last:
        return None
    base, suffix = last.split("~", 1)
    return (f"{head}/{base}" if head else base), "~" + suffix


_NODES: dict[tuple[int, str], Step] = {}
_TARGETS: dict[int, tuple[Step, int]] = {}


def review_node(parent: Step, suffix: str) -> Step | None:
    """The runtime-made step that does ``parent``'s review gate named by ``suffix``."""
    idxs = review_gate_indices(parent)
    if suffix == REVIEW_MARK and len(idxs) == 1:
        gi = idxs[0]
    else:
        m = re.fullmatch(re.escape(REVIEW_MARK) + r"\.([0-9]+)", suffix)
        if m is None or len(idxs) < 2 or int(m.group(1)) not in idxs:
            return None
        gi = int(m.group(1))
    key = (id(parent), suffix)
    if key not in _NODES:
        gate = parent.gates[gi]
        assert isinstance(gate, ReviewGate)
        caps = gate.reviewer_requires.capabilities
        node = Step.model_construct(
            id=parent.id + suffix,
            title=f"Review: {parent.title or parent.id}",
            depends_on=[],
            applies_to=None,
            requires=gate.reviewer_requires,
            prompt=gate.rubric,
            inputs=list(parent.inputs),
            output_schema=FINDINGS_REF,
            artifacts=[],
            gates=[SchemaGate(type="schema")],
            workspace="read" if "workspace_read" in caps else "none",
            protect=None,
            effort=None,
            effort_from=None,
            independence=gate.independence,
            doc_template=None,
        )
        _NODES[key] = node
        _TARGETS[id(node)] = (parent, gi)
    return _NODES[key]


def review_target(node: Step) -> tuple[Step, int] | None:
    """``(parent step, gate index)`` when ``node`` is a review step, else ``None``."""
    return _TARGETS.get(id(node))


def is_reviewer(node: Any) -> bool:
    """Steps whose output is findings: review steps and steps with ``output_schema: baton:findings``."""
    return isinstance(node, Step) and node.output_schema == FINDINGS_REF


# ---------------------------------------------------------------------------
# Lines, statuses, dispositions
# ---------------------------------------------------------------------------


def line_of(loc: Any, gate: int) -> str:
    """The line of findings recorded on the step at ``loc`` (a ``groups.Located``) by gate ``gate``."""
    f = loc.frame
    base = f"{f.instance_path}/{loc.node.id}" if f is not None else loc.path
    return f"{base}#{gate}"


def evaluations(events: list[Any], line: str) -> list[Any]:
    return [e for e in events if e.type == "findings_recorded" and e.data.get("line") == line]


def latest_evaluation(events: list[Any], line: str) -> Any | None:
    evs = evaluations(events, line)
    return evs[-1] if evs else None


def dispositions_after(events: list[Any], line: str, after_seq: int) -> dict[str, Any]:
    """Latest ``finding_dispositioned`` per finding id on ``line`` after ``after_seq``."""
    out: dict[str, Any] = {}
    for e in events:
        if e.type == "finding_dispositioned" and e.data.get("line") == line and e.seq > after_seq:
            out[e.data["finding"]] = e
    return out


def effective(events: list[Any], evaluation: Any) -> list[dict[str, Any]]:
    """The findings of one evaluation with their current status and disposition."""
    disp = dispositions_after(events, evaluation.data["line"], evaluation.seq)
    out = []
    for f in evaluation.data.get("findings") or []:
        f = dict(f)
        d = disp.get(f["id"])
        if d is not None:
            f["disposition"] = {k: d.data.get(k) for k in ("disposition", "evidence", "by", "provisional", "decision_id") if d.data.get(k) is not None}
            if d.data["disposition"] == "accepted-risk":
                f["status"] = "accepted-risk"
            elif not d.data.get("provisional"):
                # Closed by the Director relaying evidence; a later review reporting it again reopens it.
                f["status"] = d.data["disposition"]
        out.append(f)
    return out


def evaluate(events: list[Any], line: str, output: dict[str, Any], block_on: list[str] | None) -> dict[str, Any]:
    """``findings_recorded`` data for a new evaluation of ``line`` (gate pass/fail is ``blocking == []``)."""
    findings = [f for f in output.get("findings") or [] if isinstance(f, dict)]
    coverage = output.get("coverage") or {}
    prev = latest_evaluation(events, line)
    prior = {f["id"]: f for f in effective(events, prev)} if prev is not None else {}
    block = set(block_on or [])
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "?")
        counts[sev] = counts.get(sev, 0) + 1
        row = {k: f.get(k) for k in ("id", "severity", "title", "location") if f.get(k)}
        row["status"] = "open"
        before = prior.get(f.get("id"))
        if before is not None:
            disp = before.get("disposition") or {}
            if before.get("status") == "accepted-risk":
                row["status"] = "accepted-risk"
                row["carried"] = True
                if disp.get("decision_id") or before.get("decision_id"):
                    row["decision_id"] = disp.get("decision_id") or before.get("decision_id")
            elif disp.get("disposition") in WORKER_DISPOSITIONS:
                row["reopened"] = disp["disposition"]  # the review still sees it: the claim is refuted
        rows.append(row)
    ids = {f.get("id") for f in findings}
    resolved = []
    for fid, before in prior.items():
        if fid in ids:
            continue
        r = {"id": fid, "severity": before.get("severity"), "title": before.get("title")}
        disp = (before.get("disposition") or {}).get("disposition") or (before["status"] if before.get("status") == "accepted-risk" else None)
        if disp:
            r["disposition"] = disp
            r["confirmed"] = disp in WORKER_DISPOSITIONS
        resolved.append(r)
    open_ = [r for r in rows if r["status"] == "open"]
    blocking = [r for r in open_ if r.get("severity") in block]
    data: dict[str, Any] = {
        "line": line,
        "findings": rows,
        "counts": counts,
        "open": [r["id"] for r in open_],
        "blocking": [r["id"] for r in blocking],
        "partial": coverage.get("complete") is False,
    }
    if prev is not None:
        data["previous_seq"] = prev.seq
        data["resolved"] = resolved
    if coverage.get("notes"):
        data["coverage_notes"] = coverage["notes"]
    return data


def blocking_reasons(data: dict[str, Any]) -> list[str]:
    out = []
    for r in data["findings"]:
        if r["id"] in data["blocking"]:
            again = f" (reported again after it was marked {r['reopened']})" if r.get("reopened") else ""
            out.append(f"open {r.get('severity')} finding {r['id']}: {r.get('title')}" + (f" ({r['location']})" if r.get("location") else "") + again)
    return out


def prior_findings(events: list[Any], line: str) -> dict[str, Any] | None:
    """What a reviewer is told about the previous evaluation of its line (``prior_findings``)."""
    prev = latest_evaluation(events, line)
    if prev is None:
        return None
    return {"evaluated_at": prev.step_path, "attempt": prev.attempt, "findings": effective(events, prev)}


# ---------------------------------------------------------------------------
# Evidence (§9.2)
# ---------------------------------------------------------------------------

_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_FILE_LINE = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<line>[1-9][0-9]*)(?:-(?P<end>[1-9][0-9]*))?$")
_TEST = re.compile(r"^(?P<path>[^:\s][^:]*)::(?P<name>[^:\s]+(?:::[^:\s]+)*)$")


def _git_file(root: Path, commit: str, rel: str) -> str | None:
    from . import gitops

    try:
        proc = gitops.git(root, "show", f"{commit}:{rel}", check=False)
    except gitops.GitError:  # pragma: no cover
        return None
    return proc.stdout if proc.returncode == 0 else None


def _tree_file(root: Path, rel: str) -> str | None:
    p = (root / rel).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return None
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def _file_at(root: Path, rel: str, commit: str | None) -> tuple[str | None, str]:
    rel = rel.replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    if commit:
        return _git_file(root, commit, rel), f"at commit {commit[:12]}"
    return _tree_file(root, rel), "in the working tree"


def _check_file_line(root: Path, m: re.Match[str], commit: str | None) -> str | None:
    text, where = _file_at(root, m["path"], commit)
    if text is None:
        return f"{m['path']} does not exist {where}"
    n = len(text.splitlines())
    last = int(m["end"] or m["line"])
    if last > n:
        return f"{m['path']} has {n} lines {where}; line {last} does not exist"
    return None


def check_evidence(root: Path, disposition: str, evidence: str | None, *, reviewed_commit: str | None, head: str | None) -> list[str]:
    """Problems with a ``fixed`` / ``rejected`` disposition's evidence (empty: valid).

    ``fixed``: a commit that exists, or a ``file:line`` in the current tree.
    ``rejected``: a ``file:line`` that exists at the reviewed commit (the
    working tree when there is none), or a test reference ``path::name`` whose
    file exists now and contains the name.
    """
    ev = (evidence or "").strip()
    if not ev:
        return [f"{disposition} needs evidence: " + ("a commit or file:line" if disposition == "fixed" else "a file:line at the reviewed commit, or a test reference path::name")]
    if disposition == "fixed":
        if _COMMIT.match(ev):
            from . import gitops

            try:
                ok = gitops.is_repo(root) and gitops.git(root, "cat-file", "-e", f"{ev}^{{commit}}", check=False).returncode == 0
            except gitops.GitError:  # pragma: no cover
                ok = False
            return [] if ok else [f"commit {ev} does not exist in this repository"]
        m = _FILE_LINE.match(ev)
        if m:
            p = _check_file_line(root, m, head)
            return [p] if p else []
        return [f"evidence {ev!r} for fixed is neither a commit nor file:line"]
    if disposition == "rejected":
        m = _FILE_LINE.match(ev)
        if m:
            p = _check_file_line(root, m, reviewed_commit)
            return [p] if p else []
        t = _TEST.match(ev)
        if t:
            text, where = _file_at(root, t["path"], head)
            if text is None:
                return [f"test file {t['path']} does not exist {where}"]
            missing = [part for part in t["name"].split("::") if not re.search(rf"\b{re.escape(part.split('[')[0])}\b", text)]
            return [f"{t['path']} {where} has no {', '.join(missing)}"] if missing else []
        return [f"evidence {ev!r} for rejected is neither file:line nor a test reference path::name"]
    return [f"unknown disposition {disposition!r}"]


def repo_head(root: Path) -> str | None:
    from . import gitops

    try:
        if not gitops.is_repo(root):
            return None
        return gitops.git(root, "rev-parse", "--verify", "-q", "HEAD", check=False).stdout.strip() or None
    except gitops.GitError:  # pragma: no cover
        return None


# ---------------------------------------------------------------------------
# Gates by name, waivers
# ---------------------------------------------------------------------------


def resolve_gate(step: Step, spec: str) -> int | str:
    """A gate named by index, by type when the step declares exactly one of it, or ``independence`` / ``protected``."""
    from .packet import EngineError

    s = str(spec).strip()
    if s in IMPLICIT_WAIVABLE:
        if s == "protected" and step.protect is None:
            raise EngineError("waive.unknown_gate", f"{step.id} protects no paths")
        if s == "independence" and step.independence is None:
            raise EngineError("waive.unknown_gate", f"{step.id} declares no independence")
        return s
    if s.isdigit():
        i = int(s)
        if i >= len(step.gates):
            raise EngineError("waive.unknown_gate", f"{step.id} has {len(step.gates)} gates; there is no gate {i}")
    else:
        hits = [i for i, g in enumerate(step.gates) if g.type == s]
        if len(hits) != 1:
            why = "declares no" if not hits else "declares several"
            raise EngineError("waive.unknown_gate", f"{step.id} {why} {s} gate; name it by index (0-{len(step.gates) - 1})")
        i = hits[0]
    if step.gates[i].type not in WAIVABLE_TYPES:
        raise EngineError("waive.not_waivable", f"gate {i} of {step.id} is a {step.gates[i].type} gate; waivers cover {', '.join(WAIVABLE_TYPES)}, independence and protected gates")
    return i


def consumed(events: list[Any]) -> set[int]:
    return {e.data["waiver_seq"] for e in events if isinstance(e.data.get("waiver_seq"), int)}


def pending_waiver(events: list[Any], step_path: str, gate: int | str) -> Any | None:
    """The unconsumed ``scope: next`` waiver for this step path and gate, if any."""
    used = consumed(events)
    for e in events:
        if e.type == "gate_waived" and e.step_path == step_path and e.data.get("gate") == gate and e.data.get("scope") == "next" and e.seq not in used:
            return e
    return None


# ---------------------------------------------------------------------------
# Protected files (§9.4)
# ---------------------------------------------------------------------------


def _glob_re(pattern: str) -> re.Pattern[str]:
    p = pattern.replace("\\", "/").lstrip("/")
    out = ""
    i = 0
    while i < len(p):
        if p.startswith("**/", i):
            out += r"(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            out += r".*"
            i += 2
        elif p[i] == "*":
            out += r"[^/]*"
            i += 1
        elif p[i] == "?":
            out += r"[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile(rf"^{out}$")


def matches(path: str, globs: list[str]) -> bool:
    return any(_glob_re(g).match(path) for g in globs)


_SKIP_DIRS = {".git", ".baton"}


def protected_snapshot(root: Path, globs: list[str]) -> dict[str, str]:
    """``{POSIX path: sha256}`` of every file under ``root`` matching one of ``globs`` (``.git`` and ``.baton`` excluded)."""
    pats = [_glob_re(g) for g in globs]
    out: dict[str, str] = {}
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            rel_dir = ""
        for fn in filenames:
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            if any(p.match(rel) for p in pats):
                try:
                    out[rel] = hashlib.sha256((Path(dirpath) / fn).read_bytes()).hexdigest()
                except OSError:
                    out[rel] = "unreadable"
    return out


def protected_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    out = []
    for path in sorted(set(before) | set(after)):
        b, a = before.get(path), after.get(path)
        if b != a:
            out.append(f"{path} (added)" if b is None else f"{path} (deleted)" if a is None else path)
    return out

