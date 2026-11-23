"""Repro bundles for a Baton problem: ``baton report`` (change 2026-11-self-improvement, D2; §13.1).

A report is assembled from the run's record, deterministically, and changes no state: ``report.md`` holds a header
taken from the events and empty sections for the Director to complete; ``bundle/`` holds the step's material,
redacted, with machine-local paths rewritten. It is written under ``.baton/reports/``, which git ignores.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .redact import redact_text

REPORTS = "reports"
LOG_TAIL = 64 * 1024
FILE_CAP = 256 * 1024
PACKET_SUFFIXES = (".md", ".json", ".yaml", ".yml", ".txt")
SECTIONS = ("What happened", "Root cause", "Expected", "Suggested fixes")


class ReportError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "report"


class _Scrub:
    """Redaction plus machine-local paths: the project root as ``<project>``, the home directory as ``~``."""

    def __init__(self, project_root: Path, home: Path):
        pairs = []
        for p, label in ((project_root, "<project>"), (home, "~")):
            for form in {str(p), p.as_posix()}:
                if form and form not in ("/", "."):
                    pairs.append((form, label))
        self.pairs = sorted(pairs, key=lambda x: -len(x[0]))

    def text(self, s: str) -> str:
        s = redact_text(s)
        for form, label in self.pairs:
            s = s.replace(form, label)
        return s

    def data(self, b: bytes) -> bytes:
        try:
            return self.text(b.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError:  # expected: binary content is left out of a bundle
            return b"(binary content left out)\n"


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _attempt_rows(events: list[Any], step_path: str) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for e in events:
        if e.step_path != step_path or not e.attempt:
            continue
        r = rows.setdefault(e.attempt, {"attempt": e.attempt, "worker": None, "adapter": None, "model": None, "outcome": None})
        d = e.data or {}
        if e.type == "worker_selected":
            r.update(worker=d.get("profile"), adapter=d.get("adapter"), model=d.get("model_id") or d.get("model"))
        elif e.type in ("result_rejected", "gate_failed", "step_escalated", "step_passed", "step_timed_out", "attempt_orphaned"):
            why = d.get("reason") or "; ".join(str(x) for x in (d.get("reasons") or [])[:2])
            r["outcome"] = f"{e.type}" + (f": {why}" if why else "")
    return [rows[k] for k in sorted(rows)]


def write(project: Any, ctx: Any, step_path: str | None, case: dict[str, Any] | None, title: str | None,
          now: datetime | None = None) -> dict[str, Any]:
    """Write a report for ``step_path`` of the run (or the run as a whole) and return where it went."""
    from . import docs

    now = now or datetime.now(timezone.utc)
    events = ctx.log.events()
    state = ctx.log.state()
    if step_path is not None and step_path not in state.steps:
        raise ReportError("report.unknown_step", f"run {ctx.run_id} has no step {step_path}")
    scrub = _Scrub(project.root.resolve(), Path.home())
    name = title or (f"{ctx.run_id} {step_path}" if step_path else ctx.run_id)
    root = project.baton / REPORTS
    base = f"{now.date().isoformat()}-{_slug(name)}"
    out = root / base
    k = 2
    while out.exists():
        out, k = root / f"{base}-{k}", k + 1
    bundle = out / "bundle"
    if not (root / ".gitignore").is_file():
        _write(root / ".gitignore", b"# Written by baton report: repro bundles stay on this machine.\n*\n")

    files: list[str] = []

    def put(rel: str, content: bytes) -> None:
        _write(bundle / rel, scrub.data(content[:FILE_CAP]) + (b"\n(cut at 256 KiB)\n" if len(content) > FILE_CAP else b""))
        files.append(rel)

    put("events.jsonl", ctx.log.path.read_bytes())
    put("summary.md", docs.summary(ctx).encode("utf-8"))
    attempts: list[dict[str, Any]] = []
    if step_path is not None:
        put("step-record.md", docs.step_record(ctx, step_path).encode("utf-8"))
        attempts = _attempt_rows(events, step_path)
        for row in attempts:
            n = row["attempt"]
            adir = ctx.attempt_dir(step_path, n)
            pdir = adir / "packet"
            if pdir.is_dir():
                for f in sorted(p for p in pdir.rglob("*") if p.is_file() and p.suffix in PACKET_SUFFIXES):
                    put(f"attempt-{n}/packet/{f.relative_to(pdir).as_posix()}", f.read_bytes())
            res = adir / "result" / "result.json"
            if res.is_file():
                put(f"attempt-{n}/result.json", res.read_bytes())
            for e in events:
                sha = (e.data or {}).get("output_sha256")
                if e.step_path == step_path and e.attempt == n and e.type in ("gate_failed", "gate_passed") and sha:
                    put(f"attempt-{n}/gate-{(e.data or {}).get('gate')}-output.txt", ctx.log.cas.read(sha))
            log = project.home / "logs" / ctx.run_id / PurePosixPath(step_path) / f"attempt-{n}.log"
            if log.is_file():
                data = log.read_bytes()
                put(f"attempt-{n}/worker.log", data[-LOG_TAIL:])
    recipe_yaml = ctx.recipe.root / "recipe.yaml"
    if recipe_yaml.is_file():
        put("recipe.yaml", recipe_yaml.read_bytes())

    lines = [f"# Baton problem: {scrub.text(name)}", "",
             f"- Reported: {now.isoformat(timespec='seconds')} by the Director",
             f"- Baton: {__version__}, recipe `{ctx.recipe.recipe.ref}`",
             f"- Run: `{ctx.run_id}`" + (f", step `{step_path}`" if step_path else "")]
    if step_path is not None:
        st = state.step(step_path)
        lines.append(f"- Step state: {st.state}, attempt {st.attempt}")
    if case is not None:
        lines.append(f"- Case: seq {case['seq']}, kind `{case.get('kind')}`" + (f", fix in `{case['fix_in']}`" if case.get("fix_in") else ""))
        lines += ["", "> " + scrub.text(str(case.get("text") or "")).replace("\n", "\n> ")]
        if case.get("owner_words"):
            lines += ["", "The owner's words: " + scrub.text(str(case["owner_words"]))]
    if attempts:
        lines += ["", "| Attempt | Worker | Adapter | Model | Outcome |", "|---|---|---|---|---|"]
        for r in attempts:
            lines.append("| {attempt} | {w} | {a} | {m} | {o} |".format(
                attempt=r["attempt"], w=r["worker"] or "", a=r["adapter"] or "", m=r["model"] or "",
                o=scrub.text(r["outcome"] or "").replace("|", "\\|").replace("\n", " ")))
    for s in SECTIONS:
        lines += ["", f"## {s}", "", "(to complete)"]
    lines += ["", "## Evidence", "", "In `bundle/` beside this file (redacted; the project root is written `<project>`, the home directory `~`):", ""]
    lines += [f"- `{f}`" for f in files]
    _write(out / "report.md", ("\n".join(lines) + "\n").encode("utf-8"))
    rel = out.relative_to(project.root).as_posix() if out.is_relative_to(project.root) else str(out)
    return {"path": rel, "report": f"{rel}/report.md", "files": files}


def case_event(project: Any, seq: int) -> dict[str, Any]:
    """The ``process_feedback`` event ``seq`` of the project log, as a case."""
    for e in project.store.project_log().events():
        if e.seq == seq and e.type == "process_feedback":
            return {**(e.data or {}), "seq": e.seq}
    raise ReportError("report.unknown_case", f"no process feedback with seq {seq} in this project")
