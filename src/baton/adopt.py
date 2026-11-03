"""Adoption (§11): detect, research scope, crosswalk candidates, seeds and the baseline proposal.

Helpers only: nothing here appends a step transition. ``engine.py`` starts the
adoption run and the work-item runs, imports seeds and records the baseline;
this module works out *what* to propose and checks what the owner approved.

The flow (§11.1): ``adopt`` starts an adoption run of the built-in recipe
``baton-adopt@1`` whose one step, ``research``, returns ``baton-research/1``.
When research passes, one work-item run per in-flight item is started; each is
triaged; then the baseline proposal (``baton-baseline/1``) is written to
``.baton/adoption/<adoption run>/baseline.yaml``. ``establish_baseline``
re-checks it (``check_baseline``) and applies it as the owner's one decision.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .data import YamlError, load_yaml, read_text
from .models import FindingsGate, Group, HumanGate, Issue, ReviewGate, SchemaGate, ScriptGate, Step
from .packet import EngineError, RunContext, gate_included, output_schema_for
from .recipe import LoadedRecipe, crosswalk_issues
from .store import BATON_DIR, canonical_json

ADOPT_RECIPE = "baton-adopt@1"
RESEARCH_FORMAT = "baton-research/1"
BASELINE_FORMAT = "baton-baseline/1"
#: §18 #14 (decided): above either limit, ``adopt`` asks the owner to narrow the scope.
SCOPE_MAX_FILES = 10_000
SCOPE_MAX_BYTES = 200 * 1024 * 1024
#: The one-line pointer an adopting repo's ``AGENTS.md`` carries (§4.3).
AGENTS_POINTER = "This repo uses Baton; see .agents/skills/baton-director"


def adoption_dir(baton: Path, run_id: str) -> Path:
    return baton / "adoption" / run_id


def baseline_path(baton: Path, run_id: str) -> Path:
    return adoption_dir(baton, run_id) / "baseline.yaml"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# detect (§11.1)
# ---------------------------------------------------------------------------


def run_situation(project: Any, run_id: str, director: Any) -> dict[str, Any] | None:
    """``idle | active_here | active_elsewhere | orphaned_attempts | diverged`` for a non-terminal run; ``None`` when terminal."""
    from . import locks, supervisor
    from .check import run_integrity
    from .store import RunLog

    store = project.store
    problems = run_integrity(store, run_id)
    if problems:
        return {"run_id": run_id, "situation": "diverged", "problems": [f"{i.where}: {i.message}" for i in problems]}
    log = RunLog(store, run_id)
    events = log.events()
    rs = log.state()
    if rs.state != "active":
        return None
    started = events[0].data
    out: dict[str, Any] = {"run_id": run_id, "title": started.get("title"), "recipe": started.get("recipe")}
    lease = locks.current(events)
    now = log.clock()
    mine = lease is not None and not lease.expired(now) and lease.held_by(director, project.branch())
    theirs = lease is not None and not lease.expired(now) and not mine
    here, elsewhere, orphaned = [], [], []
    for path, st in sorted(rs.steps.items()):
        if st.state not in ("dispatched", "running"):
            continue
        disp = next((e.data for e in reversed(events) if e.type == "dispatched" and e.step_path == path and e.attempt == st.attempt), {})
        if disp.get("adapter") in ("manual", None) or not disp.get("dispatch_id"):
            (elsewhere if theirs else here).append(path)
            continue
        live = supervisor.liveness(project.baton, disp["dispatch_id"])
        if live.remote:
            elsewhere.append(path)
        elif live.supervisor_alive:
            here.append(path)
        else:
            orphaned.append(path)
    if orphaned:
        out.update(situation="orphaned_attempts", attempts=orphaned)
    elif theirs or elsewhere:
        out.update(situation="active_elsewhere", running=elsewhere, lease=lease.describe() if lease else None)
    elif mine or here:
        out.update(situation="active_here", running=here)
    else:
        out["situation"] = "idle"
    return out


def detect(root: str | Path | None, *, home: str | Path | None = None, director: Any = None, machine: bool = True) -> dict[str, Any]:
    """The project situation, per-run situations, machine readiness and open incidents (§11.1). Records nothing."""
    from .gitops import is_repo
    from .locks import Director
    from .project import Project, find_root

    start = Path(root or Path.cwd()).resolve()
    try:
        found = find_root(start)
    except EngineError:
        git = is_repo(start) if start.is_dir() else False
        line = f"No Baton project at {start}" + (" (a git repository)" if git else "") + ": adopt it with `baton adopt <recipe>`."
        return {"ok": True, "project": {"situation": "no_baton", "root": str(start), "git": git}, "runs": [], "machine": None,
                "incidents": [], "problems": [], "warnings": [], "line": line}
    project = Project.open(found, home=home)
    try:
        director = director or Director.current()
        runs = [s for rid in project.store.run_ids() if (s := run_situation(project, rid, director)) is not None]
        adopting = [r["run_id"] for r in runs if (r.get("recipe") == ADOPT_RECIPE)]
        problems: list[str] = []
        warnings: list[str] = []
        for r in runs:
            if r["situation"] == "diverged":
                problems.append(f"run {r['run_id']} failed verification (diverged or tampered): " + "; ".join(r["problems"][:3]))
            elif r["situation"] == "orphaned_attempts":
                problems.append(f"run {r['run_id']} has attempts whose supervisor died: {', '.join(r['attempts'])} (run `baton resume {r['run_id']}`)")
        mach = None
        if machine:
            from .doctor import doctor

            mach = doctor(project, run_noop=False)
            problems += [f"doctor: {p}" for p in mach["problems"]]
            warnings += [f"doctor: {w}" for w in mach["warnings"]]
        counts: dict[str, int] = {}
        for r in runs:
            counts[r["situation"]] = counts.get(r["situation"], 0) + 1
        situation = "adopting" if adopting else "baton"
        shown = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(counts.items()))
        line = f"baton: healthy; {len(runs)} active run{'s' if len(runs) != 1 else ''}" + (f" ({shown})" if runs else "")
        if adopting:
            line += f"; adoption in progress ({', '.join(adopting)})"
        return {
            "ok": not problems, "project": {"situation": situation, "root": str(project.root), "git": is_repo(project.root), "branch": project.branch()},
            "runs": runs, "machine": mach, "incidents": [], "problems": problems, "warnings": warnings, "line": line,
        }
    finally:
        project.store.close()


# ---------------------------------------------------------------------------
# Research scope (§11.2, §18 #14)
# ---------------------------------------------------------------------------


def scope_files(root: Path, scope: list[str] | None) -> list[tuple[str, int]]:
    """Non-ignored files in scope as ``(POSIX path, size)``, never under ``.git`` or ``.baton``."""
    from .gitops import git, is_repo

    paths = [PurePosixPath(s.replace("\\", "/")).as_posix().strip("/") for s in (scope or [])]
    for p in paths:
        if p.startswith("..") or PurePosixPath(p).is_absolute():
            raise EngineError("adopt.bad_scope", f"scope {p!r} must be a path inside the project")
    if is_repo(root):
        out = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *(paths or ["."])).stdout
        rels = sorted({r for r in out.split("\0") if r})
    else:
        rels = []
        bases = [root / p for p in paths] if paths else [root]
        for base in bases:
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in (".git", BATON_DIR)]
                rels += [Path(dirpath, f).relative_to(root).as_posix() for f in filenames]
        rels = sorted(set(rels))
    files = []
    for r in rels:
        if r.split("/", 1)[0] in (".git", BATON_DIR):
            continue
        p = root / r
        if p.is_file() and not p.is_symlink():
            files.append((r, p.stat().st_size))
    return files


def check_scope(files: list[tuple[str, int]]) -> dict[str, int]:
    total = sum(s for _, s in files)
    if len(files) > SCOPE_MAX_FILES or total > SCOPE_MAX_BYTES:
        raise EngineError(
            "adopt.scope_too_large",
            f"research would cover {len(files)} files ({total / 1048576:.0f} MB); the limit is {SCOPE_MAX_FILES} files or "
            f"{SCOPE_MAX_BYTES // 1048576} MB. Narrow it with `--scope <path>` (repeatable), e.g. the directories the prior process used.",
        )
    return {"files": len(files), "bytes": total}


# ---------------------------------------------------------------------------
# Crosswalks (§11.3)
# ---------------------------------------------------------------------------


def load_crosswalk(spec: str, loaded: LoadedRecipe, root: Path) -> dict[str, Any]:
    """A crosswalk by name (``<recipe>/crosswalks/<name>.yaml``) or by path, validated against the recipe."""
    named = loaded.root / "crosswalks" / f"{spec}.yaml"
    path = named if named.is_file() else (Path(spec) if Path(spec).is_absolute() else root / spec)
    if not path.is_file():
        shipped = sorted(p.stem for p in (loaded.root / "crosswalks").glob("*.yaml")) if (loaded.root / "crosswalks").is_dir() else []
        raise EngineError("crosswalk.not_found", f"no crosswalk {spec!r} (shipped with {loaded.recipe.ref}: {', '.join(shipped) or 'none'})")
    try:
        raw = load_yaml(path)
    except YamlError as e:
        raise EngineError("crosswalk.invalid", f"{path}: {e}") from e
    issues = crosswalk_issues(raw, loaded.recipe, str(path))
    if not named.is_file():  # a recipe's own crosswalks were linted when it loaded
        hit = next((h for h in _strings(raw) if loaded.vocab.find_vendor_string(h)), None)
        if hit:
            issues.append(Issue(code="neutrality.vendor_string", where=str(path), message=f"{hit!r} names a vendor; crosswalks must be model-neutral"))
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise EngineError("crosswalk.invalid", "; ".join(f"{i.where}: [{i.code}] {i.message}" for i in errors))
    return raw


def _strings(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for k, x in v.items() for s in [str(k), *_strings(x)]]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def glob_regex(glob: str) -> re.Pattern[str]:
    """``*`` and ``**`` become captures (``*`` within one path segment); ``?`` one character."""
    p = glob.replace("\\", "/").lstrip("/")
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += r"(?:(.*)/)?"
            i += 3
        elif p.startswith("**", i):
            out += r"(.*)"
            i += 2
        elif p[i] == "*":
            out += r"([^/]*)"
            i += 1
        elif p[i] == "?":
            out += r"[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile(f"^{out}$")


def _fill(template: str | None, caps: tuple[str | None, ...]) -> str | None:
    if template is None:
        return None
    return re.sub(r"\{(\d+)\}", lambda m: caps[int(m.group(1)) - 1] or "", template)


def match_candidates(crosswalk: dict[str, Any] | None, files: list[tuple[str, int]], root: Path) -> list[dict[str, Any]]:
    """Every in-scope file a crosswalk rule matches, with its hash and target (§11.3)."""
    if not crosswalk:
        return []
    out = []
    for i, m in enumerate(crosswalk.get("maps") or []):
        rx = glob_regex(m["match"])
        for rel, _size in files:
            hit = rx.match(rel)
            if not hit:
                continue
            caps = hit.groups()
            cand: dict[str, Any] = {"path": rel, "sha256": sha256_file(root / rel), "rule": i, "step": m["step"].split("/", 1)[1], "qualified": m["step"],
                                    "work_item": _fill(m["work_item"], caps)}
            if m.get("artifact") is not None:
                cand["artifact"] = m["artifact"]
            elif m.get("gate") is not None:
                cand["gate"] = m["gate"]
            else:
                cand["output"] = True
            if m.get("item") is not None:
                cand["item"] = _fill(m["item"], caps)
            out.append(cand)
    return out


# ---------------------------------------------------------------------------
# What research is told about the recipe
# ---------------------------------------------------------------------------


def recipe_summary(loaded: LoadedRecipe) -> dict[str, Any]:
    r = loaded.recipe

    def node(n: Any, prefix: str = "") -> dict[str, Any]:
        path = f"{prefix}{n.id}"
        d: dict[str, Any] = {"path": path, "title": n.title or n.id, "depends_on": list(n.depends_on)}
        if n.applies_to is not None:
            d["applies_to"] = list(n.applies_to)
        if isinstance(n, Group):
            d["kind"] = "group"
            if n.foreach:
                d["foreach"] = n.foreach
            d["steps"] = [node(c, f"{path}/") for c in n.steps]
            return d
        d["kind"] = "step"
        d["output_schema"] = output_schema_for(loaded, n) if n.output_schema else None
        d["artifacts"] = [{"name": a.name, "required": a.required, **({"media_type": a.media_type} if a.media_type else {})} for a in n.artifacts]
        d["gates"] = [{"index": i, "type": g.type, **({"applies_to": list(g.applies_to)} if g.applies_to else {})} for i, g in enumerate(n.gates)]
        return d

    out: dict[str, Any] = {"recipe": r.ref, "description": r.description, "steps": [node(n) for n in r.steps]}
    if r.complexity is not None:
        out["levels"] = list(r.complexity.levels)
        out["triage_step"] = r.complexity.triage_step
    if r.run_inputs is not None:
        out["run_inputs_schema"] = loaded.schemas[r.run_inputs.schema_]
    return out


# ---------------------------------------------------------------------------
# Work items from research (§11.1 step 3)
# ---------------------------------------------------------------------------


def work_items(research: dict[str, Any], loaded: LoadedRecipe) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """``(in-flight items to start as runs, finished items, gaps)``."""
    schema = loaded.schemas[loaded.recipe.run_inputs.schema_] if loaded.recipe.run_inputs is not None else None
    start, history, gaps = [], [], []
    seen: set[str] = set()
    for w in research.get("work_items") or []:
        key = w["key"]
        if key in seen:
            gaps.append(f"work item {key!r} is listed more than once; only the first is used")
            continue
        seen.add(key)
        if w["status"] == "finished":
            history.append({k: w[k] for k in ("key", "title", "position") if k in w})
            continue
        inputs = w.get("inputs") or {}
        if schema is not None:
            v = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
            errs = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(inputs)]
            if errs:
                gaps.append(f"in-flight work item {key!r} ({w['title']}) has run inputs that do not match {loaded.recipe.ref}: {'; '.join(errs)}; it was not started")
                continue
        start.append({"key": key, "title": w["title"], "inputs": inputs, "position": w.get("position")})
    return start, history, gaps


# ---------------------------------------------------------------------------
# Seeds (§11.4)
# ---------------------------------------------------------------------------


class _Seed:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.step: str = raw["step"]
        self.item: int | None = raw.get("item")
        self.reasons: list[str] = []
        self.entry: dict[str, Any] = {"step": self.step, **({"item": self.item} if self.item is not None else {})}

    @property
    def key(self) -> tuple[str, int | None]:
        return self.step, self.item


def _locate(loaded: LoadedRecipe, step: str) -> tuple[Group | None, Step | Group | None]:
    parts = step.split("/")
    top = next((n for n in loaded.recipe.steps if n.id == parts[0]), None)
    if len(parts) == 1:
        return None, top
    if not isinstance(top, Group):
        return None, None
    return top, next((n for n in top.steps if n.id == parts[1]), None)


def _included(node: Any, level: str | None) -> bool:
    return node.applies_to is None or level is None or level in node.applies_to


def _project_file(root: Path, rel: str) -> Path | None:
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (p.parts and p.parts[0] in (".git", BATON_DIR)):
        return None
    full = root / p
    return full if full.is_file() and not full.is_symlink() else None


def check_seeds(
    ctx: RunContext, raw_seeds: list[dict[str, Any]], level: str | None, *, run_gates: bool = True, project_vars: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, str]]:
    """Check one work item's seeds: ``(seed entries, proposed waivers, attested approvals, files read)``.

    A seed is imported only if its output validates, its files exist, its step
    is included at the level, every dependency is seeded or skipped (or is the
    triage step), and the gates that can run on it pass (§11.4).
    """
    loaded = ctx.recipe
    root = ctx.store.root
    cx = loaded.recipe.complexity
    triage = cx.triage_step if cx else None
    files: dict[str, str] = {}
    seeds: dict[tuple[str, int | None], _Seed] = {}
    order: list[_Seed] = []
    for raw in raw_seeds:
        s = _Seed(raw)
        order.append(s)
        if s.key in seeds:
            s.reasons.append("seeded twice; only the first is used")
            continue
        seeds[s.key] = s
    outputs: dict[tuple[str, int | None], Any] = {}

    def read(rel: str, s: _Seed, what: str) -> Path | None:
        p = _project_file(root, rel)
        if p is None:
            s.reasons.append(f"{what} {rel!r} is not a file in the project")
            return None
        files[PurePosixPath(rel.replace("\\", "/")).as_posix()] = sha256_file(p)
        return p

    for s in order:
        if s.reasons:
            continue
        group, node = _locate(loaded, s.step)
        if node is None or isinstance(node, Group):
            s.reasons.append(f"{loaded.recipe.ref} has no step {s.step!r}")
            continue
        if s.step == triage:
            s.reasons.append("the triage step is never seeded; it runs in the work-item run")
            continue
        if group is not None and group.foreach and s.item is None:
            s.reasons.append(f"{s.step} is inside the foreach group {group.id!r}; the seed needs its item index")
            continue
        if (group is None or not group.foreach) and s.item not in (None, 0):
            s.reasons.append(f"{s.step} is not in a per-item group; it has no item {s.item}")
            continue
        for n in ([group] if group is not None else []) + [node]:
            if not _included(n, level):
                s.reasons.append(f"{n.id} is not included at level {level!r}")
        if s.reasons:
            continue
        output = s.raw.get("output")
        if "output_from" in s.raw:
            p = read(s.raw["output_from"], s, "output_from")
            if p is not None:
                try:
                    output = json.loads(read_text(p))
                except json.JSONDecodeError as e:
                    s.reasons.append(f"output_from {s.raw['output_from']!r} is not JSON ({e})")
        if node.output_schema:
            if output is None and not s.reasons:
                s.reasons.append("no output given")
            elif output is not None:
                v = Draft202012Validator(output_schema_for(loaded, node), format_checker=Draft202012Validator.FORMAT_CHECKER)
                errs = [f"output {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(output)]
                s.reasons += [f"nonconforming: {e}" for e in errs]
        outputs[s.key] = output
        declared = {a.name: a for a in node.artifacts}
        arts = {}
        for name, rel in (s.raw.get("artifacts") or {}).items():
            if name not in declared:
                s.reasons.append(f"artifact {name!r} is not declared by {s.step}")
                continue
            p = read(rel, s, f"artifact {name!r}")
            if p is not None:
                arts[name] = {"path": PurePosixPath(rel.replace("\\", "/")).as_posix(), "sha256": files[PurePosixPath(rel.replace("\\", "/")).as_posix()]}
        for name, a in declared.items():
            if a.required and name not in (s.raw.get("artifacts") or {}):
                s.reasons.append(f"required artifact {name!r} is missing")
        s.entry["artifacts"] = arts
        ev = []
        for rel in s.raw.get("evidence") or []:
            if read(rel, s, "evidence") is not None:
                ev.append({"path": PurePosixPath(rel.replace("\\", "/")).as_posix(), "sha256": files[PurePosixPath(rel.replace("\\", "/")).as_posix()]})
        s.entry["evidence"] = ev

    # Items of foreach groups: the seeded source must say how many there are.
    for s in order:
        if s.reasons or s.item is None:
            continue
        group, _ = _locate(loaded, s.step)
        assert group is not None and group.foreach
        from . import refs

        ref = refs.parse(group.foreach)
        src = seeds.get((ref.step or "", None))
        if src is None or src.reasons:
            s.reasons.append(f"its group's source {ref.step!r} is not seeded, so item {s.item} cannot be placed")
            continue
        value = outputs.get(src.key)
        for seg in ref.path:
            value = value.get(seg) if isinstance(value, dict) else None
        if not isinstance(value, list) or s.item >= len(value):
            s.reasons.append(f"item {s.item} is out of range for {group.foreach}")

    # Dependencies: seeded, skipped at the level, or triage (fixpoint: a refused seed refuses its dependents).
    def dep_ok(dep: str, scope_group: Group | None, item: int | None) -> bool:
        if scope_group is None:
            n = next((x for x in loaded.recipe.steps if x.id == dep), None)
            if n is None:
                return False
            if not _included(n, level) or dep == triage:
                return True
            if isinstance(n, Group):
                return False  # a whole group is never satisfied by seeds before the baseline
            d = seeds.get((dep, None))
            return d is not None and not d.reasons
        n = next((x for x in scope_group.steps if x.id == dep), None)
        if n is None:
            return False
        if not _included(n, level):
            return True
        d = seeds.get((f"{scope_group.id}/{dep}", item))
        return d is not None and not d.reasons

    changed = True
    while changed:
        changed = False
        for s in order:
            if s.reasons:
                continue
            group, node = _locate(loaded, s.step)
            assert node is not None
            missing = [d for d in node.depends_on if not dep_ok(d, group, s.item)]
            if group is not None:
                missing += [d for d in group.depends_on if not dep_ok(d, None, None)]
            if missing:
                s.reasons.append(f"depends on {', '.join(missing)}, which {'is' if len(missing) == 1 else 'are'} neither seeded nor skipped")
                changed = True

    # Gates on seeds that would otherwise be imported.
    waivers: list[dict[str, Any]] = []
    attested: list[str] = []
    for s in order:
        if s.reasons:
            continue
        group, node = _locate(loaded, s.step)
        assert isinstance(node, Step)
        given = {g["gate"]: g["evidence"] for g in s.raw.get("gates") or []}
        gates = []
        for i, g in enumerate(node.gates):
            if not gate_included(g, level):
                continue
            entry: dict[str, Any] = {"gate": i, "type": g.type}
            evid = []
            for rel in given.get(i, []):
                if read(rel, s, f"gate {i} evidence") is not None:
                    evid.append({"path": PurePosixPath(rel.replace("\\", "/")).as_posix(), "sha256": files[PurePosixPath(rel.replace("\\", "/")).as_posix()]})
            if isinstance(g, SchemaGate):
                entry["status"] = "passed"
            elif isinstance(g, ScriptGate):
                if not run_gates:
                    entry["status"] = "passed at proposal"
                else:
                    from .intake import run_script_gate

                    variables = {**ctx.project, "project": {**(ctx.project.get("project") or {}), **(project_vars or {})}}
                    gctx = RunContext(ctx.store, ctx.run_id, loaded, variables)
                    res = run_script_gate(gctx, g, s.step.replace("/", "_"))
                    if res.passed:
                        entry["status"] = "passed at proposal"
                    else:
                        s.reasons.append(f"gate {i} (script) fails on the seed: " + "; ".join(r.splitlines()[0] for r in res.reasons[:2]))
            elif isinstance(g, FindingsGate):
                block = set(g.block_on or [])
                out = outputs.get(s.key) or {}
                hits = [f.get("id") for f in (out.get("findings") or []) if isinstance(f, dict) and f.get("severity") in block]
                if hits and not g.advisory:
                    s.reasons.append(f"gate {i} (findings) would fail: open {', '.join(map(str, hits))}")
                entry["status"] = "evaluated on the seed"
            elif isinstance(g, ReviewGate):
                if evid:
                    entry["status"] = "imported with evidence"
                elif not g.advisory:
                    entry["status"] = "waiver proposed"
                    waivers.append({"step": s.step, **({"item": s.item} if s.item is not None else {}), "gate": i,
                                    "reason": "approved under the prior process before this review gate applied (adoption baseline)"})
            elif isinstance(g, HumanGate):
                if evid:
                    entry["status"] = "approved outside Baton (evidence)"
                else:
                    entry["status"] = "attested by the baseline"
                    attested.append(f"{s.step}{f'[{s.item}]' if s.item is not None else ''} gate {i}: {g.prompt}")
            if evid:
                entry["evidence"] = evid
            gates.append(entry)
        if not s.reasons:
            s.entry["gates"] = gates
    if any(s.reasons for s in order):
        # A refused gate refuses its dependents too.
        changed = True
        while changed:
            changed = False
            for s in order:
                if s.reasons:
                    continue
                group, node = _locate(loaded, s.step)
                missing = [d for d in node.depends_on if not dep_ok(d, group, s.item)] + ([d for d in group.depends_on if not dep_ok(d, None, None)] if group else [])
                if missing:
                    s.reasons.append(f"depends on {', '.join(missing)}, which {'is' if len(missing) == 1 else 'are'} neither seeded nor skipped")
                    changed = True
    entries = []
    for s in order:
        e = dict(s.entry)
        if s.reasons:
            e = {k: v for k, v in e.items() if k in ("step", "item")}
            e.update({"import": False, "reasons": s.reasons, "action": "rerun"})
        else:
            e["import"] = True
            if outputs.get(s.key) is not None:
                e["output"] = outputs[s.key]
                e["output_sha256"] = hashlib.sha256(canonical_json(outputs[s.key]).encode("utf-8")).hexdigest()
        entries.append(e)
    refused = {(e["step"], e.get("item")) for e in entries if not e["import"]}
    waivers = [w for w in waivers if (w["step"], w.get("item")) not in refused]
    return entries, waivers, attested, files


def plan_for(loaded: LoadedRecipe, level: str | None, entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Top-level plan of a work item at its level: steps imported, to run, skipped."""
    imported = {e["step"] for e in entries if e["import"] and "/" not in e["step"]}
    out: dict[str, list[str]] = {"imported": [], "run": [], "skip": []}
    for n in loaded.recipe.steps:
        if not _included(n, level):
            out["skip"].append(n.id)
        elif n.id in imported:
            out["imported"].append(n.id)
        else:
            out["run"].append(n.id)
    return out


# ---------------------------------------------------------------------------
# The baseline (§11.5)
# ---------------------------------------------------------------------------


def _agents_md(root: Path) -> dict[str, Any]:
    p = root / "AGENTS.md"
    if not p.is_file():
        return {"path": "AGENTS.md", "action": "create", "line": AGENTS_POINTER}
    return {"path": "AGENTS.md", "action": "none" if AGENTS_POINTER in read_text(p) else "append", "line": AGENTS_POINTER}


def propose(
    project: Any, adoption: RunContext, research: dict[str, Any], runs: dict[str, RunContext], history: list[dict[str, Any]], gaps: list[str],
) -> dict[str, Any]:
    """The baseline proposal for an adoption whose work-item runs are all triaged."""
    cfg = project.config
    project_yaml = {
        "paths": {k: v for k, v in sorted((research.get("path_candidates") or {}).items()) if k not in cfg.paths},
        "project": {k: v for k, v in sorted((research.get("command_candidates") or {}).items()) if k not in cfg.project},
    }
    seeds_by_item: dict[str, list[dict[str, Any]]] = {}
    for s in research.get("proposed_seeds") or []:
        seeds_by_item.setdefault(s["work_item"], []).append(s)
    gaps = list(gaps) + list(research.get("gaps") or [])
    for key in sorted(set(seeds_by_item) - set(runs)):
        gaps.append(f"seeds for {key!r}, which is not an in-flight work item with a run, were ignored")
    items = []
    files: dict[str, str] = {}
    for key, ctx in runs.items():
        loaded = ctx.recipe
        level, reasons = triage_level(ctx)
        entries, waivers, attested, read = check_seeds(ctx, seeds_by_item.get(key, []), level, project_vars=project_yaml["project"])
        files.update(read)
        items.append({
            "key": key, "run": ctx.run_id, "title": ctx.record().started.get("title"), "level": level, "level_reasons": reasons, "create": True,
            "seeds": entries, "waivers": waivers, "attested": attested, "plan": plan_for(loaded, level, entries),
        })
    return {
        "format": BASELINE_FORMAT,
        "adoption": adoption.run_id,
        "recipe": runs[next(iter(runs))].recipe.recipe.ref if runs else adoption.record().started.get("adoption_of"),
        "research_sha256": adoption.record().registered("research")["output_sha256"],
        "project_yaml": project_yaml,
        "agents_md": _agents_md(project.root),
        "history": history,
        "work_items": items,
        "gaps": gaps,
        "files": dict(sorted(files.items())),
    }


def triage_level(ctx: RunContext) -> tuple[str | None, list[str]]:
    cx = ctx.recipe.recipe.complexity
    if cx is None:
        return None, []
    reg = ctx.record().registered(cx.triage_step)
    if reg is None or not reg.get("output_sha256"):
        return None, []
    out = json.loads(ctx.log.cas.read(reg["output_sha256"]))
    reasons = out.get("reasons") if isinstance(out, dict) else None
    return (out.get("level") if isinstance(out, dict) else None), ([str(r) for r in reasons] if isinstance(reasons, list) else [])


BASELINE_HEADER = """\
# Baton adoption baseline (baton-baseline/1, §11.5): ONE owner decision ends adoption.
# Review it; edit anything you disagree with (a level, a seed's `import`, a waiver,
# `create: false` for a work item, the proposed configuration). Then record the
# decision in your own words:
#   baton establish-baseline {run} --note "<your words>"
"""


def write_baseline(path: Path, doc: dict[str, Any]) -> None:
    from .store import atomic_write

    text = BASELINE_HEADER.format(run=doc["adoption"]) + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)
    atomic_write(path, text.encode("utf-8"))


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EngineError("baseline.missing", f"no baseline proposal at {path} yet (it is written once research and every triage have passed)")
    try:
        doc = load_yaml(path)
    except YamlError as e:
        raise EngineError("baseline.invalid", f"{path}: {e}") from e
    if not isinstance(doc, dict) or doc.get("format") != BASELINE_FORMAT:
        raise EngineError("baseline.invalid", f"{path} is not a {BASELINE_FORMAT} document")
    return doc


def check_baseline(project: Any, adoption: RunContext, doc: dict[str, Any], runs: dict[str, RunContext], proposed: dict[str, Any]) -> list[str]:
    """Problems with an (owner-edited) baseline; empty when it can be applied.

    Seeds are re-checked against their schemas and dependencies (gates that
    ran at the proposal are not re-run); any file whose hash changed since the
    proposal refuses the whole baseline.
    """
    problems: list[str] = []
    if doc.get("adoption") != adoption.run_id:
        problems.append(f"the baseline is for adoption {doc.get('adoption')!r}, not {adoption.run_id}")
    for rel, sha in (proposed.get("files") or {}).items():
        p = _project_file(project.root, rel)
        if p is None or sha256_file(p) != sha:
            problems.append(f"{rel} changed since the proposal; regenerate it with `baton adopt` (delete {baseline_path(project.baton, adoption.run_id).relative_to(project.root).as_posix()} first)")
    for k in ("paths", "project"):
        v = (doc.get("project_yaml") or {}).get(k, {})
        if not isinstance(v, dict) or any(not isinstance(x, str) or "secret:" in x for x in v.values()):
            problems.append(f"project_yaml.{k} must map names to plain strings (no secret: references)")
    want = {w.get("key"): w for w in doc.get("work_items") or [] if isinstance(w, dict)}
    for key, ctx in runs.items():
        w = want.get(key)
        if w is None:
            problems.append(f"work item {key!r} ({ctx.run_id}) is missing from the baseline; set `create: false` to leave it out")
            continue
        if w.get("run") != ctx.run_id:
            problems.append(f"work item {key!r} names run {w.get('run')!r}, not {ctx.run_id}")
        if not w.get("create", True):
            continue
        cx = ctx.recipe.recipe.complexity
        level = w.get("level")
        if cx is not None and level not in cx.levels:
            problems.append(f"work item {key!r}: level {level!r} is not one of {cx.levels}")
            continue
        chosen = [s for s in w.get("seeds") or [] if isinstance(s, dict) and s.get("import")]
        raw = [_raw_seed(s) for s in chosen]
        entries, _w, _a, _f = check_seeds(ctx, raw, level, run_gates=False)
        for e in entries:
            if not e["import"]:
                where = e["step"] + (f"[{e['item']}]" if "item" in e else "")
                problems.append(f"work item {key!r} seed {where}: " + "; ".join(e["reasons"]))
        seeded = {(s.get("step"), s.get("item")) for s in chosen}
        for wv in w.get("waivers") or []:
            if (wv.get("step"), wv.get("item")) not in seeded:
                problems.append(f"work item {key!r}: waiver of {wv.get('step')} gate {wv.get('gate')} has no imported seed")
            elif not str(wv.get("reason") or "").strip():
                problems.append(f"work item {key!r}: waiver of {wv.get('step')} gate {wv.get('gate')} needs a reason")
    for key in set(want) - set(runs):
        problems.append(f"work item {key!r} has no run in this adoption")
    return problems


def _raw_seed(entry: dict[str, Any]) -> dict[str, Any]:
    """A baseline seed entry back in research's seed form (for re-checking)."""
    raw: dict[str, Any] = {"work_item": "", "step": entry["step"]}
    if entry.get("item") is not None:
        raw["item"] = entry["item"]
    if "output" in entry:
        raw["output"] = entry["output"]
    raw["artifacts"] = {n: a["path"] for n, a in (entry.get("artifacts") or {}).items()}
    raw["evidence"] = [e["path"] for e in entry.get("evidence") or []]
    gates = [{"gate": g["gate"], "evidence": [x["path"] for x in g["evidence"]]} for g in entry.get("gates") or [] if g.get("evidence")]
    if gates:
        raw["gates"] = gates
    return raw


# ---------------------------------------------------------------------------
# Applying the configuration parts
# ---------------------------------------------------------------------------


def merge_project_yaml(path: Path, changes: dict[str, dict[str, str]]) -> bool:
    """Add keys to ``paths`` and ``project`` in ``project.yaml``, keeping its other lines and comments."""
    from .store import atomic_write

    changes = {k: v for k, v in changes.items() if v}
    if not changes:
        return False
    text = read_text(path)
    current = yaml.safe_load(text) or {}
    lines = text.splitlines(keepends=True)
    for key, add in changes.items():
        merged = {**(current.get(key) or {}), **add}
        block = yaml.safe_dump({key: merged}, sort_keys=False, default_flow_style=False, allow_unicode=True)
        start = next((i for i, ln in enumerate(lines) if re.match(rf"^{key}\s*:", ln)), None)
        if start is None:
            lines.append(("" if not lines or lines[-1].endswith("\n") else "\n") + block)
            continue
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        comment = re.search(r"\s+#.*$", lines[start].rstrip("\n"))
        head = block.splitlines(keepends=True)
        if comment:
            head[0] = head[0].rstrip("\n") + comment.group(0) + "\n"
        lines[start:end] = head
    atomic_write(path, "".join(lines).encode("utf-8"))
    return True


def apply_agents_md(root: Path, spec: dict[str, Any]) -> bool:
    from .store import atomic_write

    action = (spec or {}).get("action")
    line = (spec or {}).get("line") or AGENTS_POINTER
    p = root / ((spec or {}).get("path") or "AGENTS.md")
    if action == "create" and not p.exists():
        atomic_write(p, (line + "\n").encode("utf-8"))
        return True
    if action == "append" and p.is_file() and line not in read_text(p):
        text = read_text(p)
        atomic_write(p, (text + ("" if text.endswith("\n") or not text else "\n") + "\n" + line + "\n").encode("utf-8"))
        return True
    return False

