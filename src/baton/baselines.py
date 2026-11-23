"""Baselines and the detectors over a run's record (change 2026-11-self-improvement, D5; §5.1, §12.4).

* **Measures.** Per step of one run (its qualified id without the recipe, ``slices/implement``): cost in US dollars
  (priced attempts only), time from dispatch to result, attempts, the iteration it reached, the owner's stops and the
  questions it asked. ``run_measures`` reads them from the events, as ``stats`` counts them.
* **Baselines.** ``baselines.json`` in a recipe package holds each step's medians, with their sample counts, derived
  from completed runs (``derive``; ``baton recipe baselines``). It is part of the package and its hash.
* **Off baseline.** When a run completes, a measure above ``factor`` times its median (counts compared with at least 1),
  with at least ``min_samples`` samples, opens one ``off_baseline`` case per step and measure, with the quality guards.
* **Late defects.** A review finding whose location names a file another step produced, after that step had passed a
  review or findings gate of its own, is a defect found late against it (Decision 0188, item 8).

Everything here observes: nothing changes a step, a gate or a recipe (Principle 5).
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

BASELINES_FILE = "baselines.json"
FORMAT = "baton-baselines/1"
MEASURES = ("cost_usd", "duration_s", "attempts", "iterations", "owner_stops", "owner_questions")
#: Count measures: a median below 1 is compared as 1, so a step that never stopped the owner is not flagged for one stop.
COUNTS = ("attempts", "iterations", "owner_stops", "owner_questions")
_STOPS = ("human_gate_opened", "step_escalated", "iteration_limit_reached")


class BaselineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def step_key(recipe_ref: str, path: str) -> str:
    """A step path as a baseline names it: the qualified id (§5.8) without the recipe."""
    from .sme import _key

    return _key(recipe_ref, path).split("/", 1)[1]


def _ts(e: Any) -> datetime:
    return datetime.fromisoformat(e.ts.replace("Z", "+00:00"))


def _iteration(path: str) -> int:
    its = [int(p[1:]) for p in path.split("/") if len(p) > 1 and p[0] == "i" and p[1:].isdigit()]
    return max(its) if its else 1


def run_measures(events: list[Any], run_dir: Path | None) -> dict[str, dict[str, float]]:
    """Each step's measures in one run. ``cost_usd`` only when an attempt was priced."""
    from .sme import _usage

    if not events or events[0].type != "run_started":
        return {}
    recipe = events[0].data.get("recipe") or "?"
    out: dict[str, dict[str, float]] = {}
    dispatched: dict[tuple[str, int], datetime] = {}

    def m(path: str) -> dict[str, float]:
        return out.setdefault(step_key(recipe, path), {"duration_s": 0.0, "attempts": 0, "iterations": 1, "owner_stops": 0, "owner_questions": 0})

    for e in events:
        if not e.step_path:
            continue
        if e.type in _STOPS:
            m(e.step_path)["owner_stops"] += 1
        elif e.type == "dispatched":
            s = m(e.step_path)
            s["attempts"] += 1
            s["iterations"] = max(s["iterations"], _iteration(e.step_path))
            dispatched[(e.step_path, e.attempt or 0)] = _ts(e)
            u = _usage(run_dir, e.step_path, e.attempt or 0)
            usd = u.get("cost_usd") if u else None
            if isinstance(usd, (int, float)) and not isinstance(usd, bool):
                s["cost_usd"] = round(s.get("cost_usd", 0.0) + float(usd), 6)
        elif e.type == "result_submitted":
            t0 = dispatched.get((e.step_path, e.attempt or 0))
            if t0 is not None:
                m(e.step_path)["duration_s"] = round(m(e.step_path)["duration_s"] + (_ts(e) - t0).total_seconds(), 3)
            m(e.step_path)["owner_questions"] += len(e.data.get("questions") or [])
        elif e.type == "step_escalated" and e.data.get("reason") == "blocked":
            m(e.step_path)["owner_questions"] += len(e.data.get("questions") or [])
    return {k: v for k, v in out.items() if v["attempts"]}


def guards(events: list[Any], key: str) -> dict[str, Any]:
    """The quality guards of a step in one run: did every instance pass on its first attempt, how many rejections and
    failed blocking gates, how many of the owner's rejections at its gates, and its defects found late."""
    if not events or events[0].type != "run_started":
        return {}
    recipe = events[0].data.get("recipe") or "?"
    paths: set[str] = set()
    first: set[str] = set()
    rejections = owner_rejections = 0
    for e in events:
        if not e.step_path or step_key(recipe, e.step_path) != key:
            continue
        paths.add(e.step_path)
        if e.type == "step_passed" and e.attempt == 1 and not e.data.get("confirmed"):
            first.add(e.step_path)
        elif e.type == "result_rejected" or (e.type == "gate_failed" and not e.data.get("advisory")):
            rejections += 1
        elif e.type == "human_decision" and e.data.get("kind") == "gate" and e.data.get("decision") == "reject":
            owner_rejections += 1
    return {"first_try": bool(paths) and paths <= first, "rejections": rejections, "owner_rejections": owner_rejections,
            "defects_late": late_defects(events).get(key, 0)}


# ---------------------------------------------------------------------------
# Defects found late (Decision 0188, item 8)
# ---------------------------------------------------------------------------


def _file_of(location: str) -> str:
    """A finding location's file: the part before ``:line`` (or ``::test``), without a leading ``./``."""
    loc = location.strip().split("::", 1)[0]
    head, sep, tail = loc.rpartition(":")
    if sep and tail.strip().split("-")[0].isdigit():
        loc = head
    return loc[2:] if loc.startswith("./") else loc


def _produced(e: Any) -> set[str]:
    """What a ``step_passed`` says its step produced: artifact names and filenames, and the files its attempt changed."""
    out: set[str] = set()
    for name, a in (e.data.get("artifacts") or {}).items():
        out.add(name)
        if isinstance(a, dict) and a.get("filename"):
            out.add(a["filename"])
    out.update(x for x in e.data.get("changed_files") or [] if isinstance(x, str))
    return out


def late_defects(events: list[Any]) -> dict[str, int]:
    """Defects found late per step key in one run: an open, new finding whose location's file another step produced,
    recorded after that step had passed a review or findings gate of its own. A location matching nothing counts nothing."""
    if not events or events[0].type != "run_started":
        return {}
    recipe = events[0].data.get("recipe") or "?"
    produced: dict[str, set[str]] = {}  # step path -> files of its latest pass
    published: dict[str, set[str]] = {}  # step path -> project paths its artifacts were published to
    reviewed: set[str] = set()  # step paths that have passed a review or findings gate
    out: dict[str, int] = {}
    for e in events:
        if not e.step_path:
            continue
        if e.type == "step_passed":
            produced[e.step_path] = _produced(e)
        elif e.type == "artifact_published" and e.data.get("path"):
            published.setdefault(e.step_path, set()).add(str(e.data["path"]))
        elif e.type == "gate_passed" and e.data.get("type") in ("review", "findings"):
            reviewed.add(e.step_path)
        elif e.type == "findings_recorded":
            for f in e.data.get("findings") or []:
                if f.get("status") != "open" or f.get("carried") or not f.get("location"):
                    continue
                file = _file_of(str(f["location"]))
                for p in sorted(reviewed):
                    if p == e.step_path:
                        continue
                    names = produced.get(p, set()) | published.get(p, set())
                    in_attempt = f"/steps/{p}/" in "/" + file and PurePosixPath(file).name in names
                    if file in names or in_attempt:
                        k = step_key(recipe, p)
                        out[k] = out.get(k, 0) + 1
                        break
    return out


# ---------------------------------------------------------------------------
# baselines.json
# ---------------------------------------------------------------------------


def load(root: Path) -> dict[str, Any] | None:
    """A recipe package's ``baselines.json``, checked; ``None`` when it has none."""
    f = Path(root) / BASELINES_FILE
    if not f.is_file():
        return None
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BaselineError("baselines.unreadable", f"{BASELINES_FILE}: {e}") from e
    problems = check(doc)
    if problems:
        raise BaselineError("baselines.invalid", f"{BASELINES_FILE}: " + "; ".join(problems))
    return doc


def check(doc: Any) -> list[str]:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        return [f"format must be {FORMAT!r}"]
    steps = doc.get("steps")
    if not isinstance(steps, dict):
        return ["steps must be an object"]
    out = []
    for key, ms in steps.items():
        if not isinstance(ms, dict):
            out.append(f"steps.{key} must be an object")
            continue
        for name, v in ms.items():
            if name not in MEASURES:
                out.append(f"steps.{key}.{name}: not a measure (one of {', '.join(MEASURES)})")
            elif not (isinstance(v, dict) and isinstance(v.get("median"), (int, float)) and isinstance(v.get("samples"), int) and v["samples"] >= 1):
                out.append(f"steps.{key}.{name} must be {{median, samples}}")
    return out


def derive(runs: list[tuple[list[Any], Path | None]], sources: list[str], today: str) -> dict[str, Any]:
    """Medians per step and measure over completed runs (Decision 0187, item 2: medians, not means)."""
    values: dict[str, dict[str, list[float]]] = {}
    versions: set[int] = set()
    used = 0
    for events, run_dir in runs:
        if not any(e.type == "run_completed" for e in events):
            continue
        used += 1
        ref = str(events[0].data.get("recipe") or "")
        if "@" in ref and ref.rsplit("@", 1)[1].isdigit():
            versions.add(int(ref.rsplit("@", 1)[1]))
        for key, ms in run_measures(events, run_dir).items():
            for name, v in ms.items():
                values.setdefault(key, {}).setdefault(name, []).append(v)
    steps = {k: {n: {"median": round(statistics.median(v), 6), "samples": len(v)} for n, v in sorted(ms.items())}
             for k, ms in sorted(values.items())}
    return {"format": FORMAT, "steps": steps,
            "derived": {"from": sources, "runs": used, "recipe_versions": sorted(versions), "date": today}}


# ---------------------------------------------------------------------------
# The off-baseline detector
# ---------------------------------------------------------------------------


def off_baseline(events: list[Any], run_dir: Path | None, baseline: dict[str, Any], factor: float, min_samples: int) -> list[dict[str, Any]]:
    """The ``off_baseline`` cases of a completed run: one per step and measure above ``factor`` times its median."""
    cases = []
    steps = baseline.get("steps") or {}
    for key, ms in sorted(run_measures(events, run_dir).items()):
        base = steps.get(key) or {}
        for name in MEASURES:
            b, v = base.get(name), ms.get(name)
            if not isinstance(b, dict) or v is None or b.get("samples", 0) < min_samples:
                continue
            median = float(b["median"])
            floor = max(median, 1.0) if name in COUNTS else median
            if floor <= 0 or v <= factor * floor:
                continue
            cases.append({"step": key, "measure": name, "value": v, "median": median, "samples": b["samples"], "factor": factor,
                          "guards": guards(events, key)})
    return cases
