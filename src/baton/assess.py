"""Owner-run assessment of chosen models (§6.4; Decisions 0111, 0120).

``baton workers assess <model_id>… --profile <name>`` judges models that
listings offer but research has not covered, and writes the result into the
owner's overlay (``~/.baton/known-workers.local.yaml``). The one-step
``model-assessment`` recipe is not in the wheel: it is fetched from the
repository at the tag of this runtime's version (never "latest") and cached
under ``~/.baton/assessment/<version>/``. It runs through the owner's own
profile in a scratch project, like research (0083). The runtime's own
validator (``known_workers.merge_overlay``) checks the worker's draft and,
again, the merged result before anything is written.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

from . import __version__
from . import known_workers as kw_mod
from . import listings as listings_mod
from . import resources as res_mod
from . import vocab as vocab_mod
from .data import load_yaml
from .launcher import DEFAULT_SOURCE, config as launcher_config

RECIPE_PATH = Path("tools") / "worker-research" / "assessment"
FETCHED = ".fetched"


class AssessError(Exception):
    """Refused in plain words; nothing was written."""


def source_ref(home: Path, version: str) -> tuple[str, str]:
    """``(repository URL, tag)`` the runtime was installed from, from ``launcher.yaml``'s ``source`` (0120)."""
    cfg = launcher_config(Path(home))
    source = str(cfg.get("source") or DEFAULT_SOURCE).format(version=version)
    m = re.fullmatch(r"git\+(?P<url>.+)@(?P<ref>[^@/]+)", source)
    if not m:
        raise AssessError(f"the launcher's source {source!r} is not a git repository at a tag (git+<url>@v<version>), so the assessment recipe cannot be fetched from it")
    return m["url"], m["ref"]


def fetch_recipe(home: Path, version: str = __version__, *, run: Callable[..., Any] = subprocess.run) -> Path:
    """The assessment recipe for ``version``, from the cache or fetched at that version's tag (never latest)."""
    dest = Path(home) / "assessment" / version
    if (dest / FETCHED).is_file():
        return dest / "recipe"
    url, ref = source_ref(home, version)
    with tempfile.TemporaryDirectory(prefix="baton-assessment-") as tmp:
        clone = Path(tmp) / "repo"
        try:
            r = run(["git", "clone", "--quiet", "--depth", "1", "--branch", ref, url, str(clone)], capture_output=True, text=True, timeout=300, check=False)
        except (OSError, subprocess.SubprocessError) as e:
            raise AssessError(f"could not fetch the assessment recipe ({e}); with no network, write the overlay by hand (§6.4)") from e
        if r.returncode != 0 or not (clone / RECIPE_PATH / "recipe.yaml").is_file():
            why = (r.stderr or "").strip().splitlines()[-1:] or ["the tag has no assessment recipe"]
            raise AssessError(f"could not fetch the assessment recipe for {version} from {url} at {ref} ({why[0]}); "
                              "with no network, write the overlay by hand (§6.4)")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        shutil.copytree(clone / RECIPE_PATH, dest / "recipe")
        (dest / FETCHED).write_text(json.dumps({"url": url, "ref": ref, "fetched": dt.date.today().isoformat()}), encoding="utf-8")
    return dest / "recipe"


def validator_command() -> str:
    import shlex

    return " ".join(shlex.quote(a) for a in (sys.executable, "-m", "baton", "workers", "check-overlay"))


def check_overlay_text(text: str, home: Path | None = None) -> list[str]:
    """Why Baton would refuse an overlay, using the runtime's own validator; empty when it would accept it.

    With ``home``, the check is of the file merged into that machine's existing overlay.
    """
    try:
        extra = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"not YAML: {e}"]
    if isinstance(extra, dict) and home is not None:
        extra = merged_overlay(home, extra)
    try:
        kw_mod.merge_overlay(vocab_mod.load(vocab_mod.DEFAULT), extra, where="overlay")
    except kw_mod.KnownWorkersError as e:
        return [str(i) for i in e.issues]
    return []


def existing_overlay(home: Path) -> dict[str, Any]:
    p = Path(home) / kw_mod.LOCAL_FILE
    if not p.is_file():
        return {"format": kw_mod.FORMAT}
    return load_yaml(p) or {"format": kw_mod.FORMAT}


def merged_overlay(home: Path, new: dict[str, Any]) -> dict[str, Any]:
    """The owner's existing overlay with ``new``'s models added; a model assessed again replaces its earlier assessment."""
    old = existing_overlay(home)
    out = {"format": kw_mod.FORMAT, **{k: v for k, v in old.items() if k not in ("format", "models")}}
    models = {**(old.get("models") or {}), **(new.get("models") or {})}
    if models:
        out["models"] = models
    for k, v in new.items():
        if k not in ("format", "models"):
            out[k] = v
    return out


def wanted(home: Path, data: kw_mod.KnownWorkers, ids: list[str]) -> list[dict[str, Any]]:
    """The facts the listings give about each chosen model, or ``AssessError`` for one that cannot be assessed."""
    res = res_mod.load_resources(home, data.machine_dependent)
    researched = {r.invocation: r.model_id for r in data.routes if r.invocation and r.model_id and not r.alias}
    found: dict[str, dict[str, Any]] = {}
    for rname, r in sorted(res.workers().items()):
        prov = data.providers.get(r.provider)
        generic = prov is not None and prov.kind == "openai_compatible"
        listing = listings_mod.load(home, rname if generic else r.provider)
        if listing is None:
            continue
        for c in listings_mod.candidates(listing, researched, r.provider):
            if c.model_id in ids:
                f = found.setdefault(c.model_id, {"model_id": c.model_id, "listed_as": [], "context_tokens": c.context_tokens,
                                                  "catalog_capabilities": dict(c.capabilities), "price": c.price})
                f["listed_as"].append(f"{r.provider}: {c.id}")
    out = []
    for mid in ids:
        if mid in data.models:
            raise AssessError(f"{mid} already has a judgment (shipped or in your overlay); remove it from the overlay first to assess it again")
        if mid not in found:
            raise AssessError(f"no model list of yours offers {mid} under that identity; `baton workers refresh` updates the lists, and `baton workers status` shows what is listed")
        out.append(found[mid])
    return out


def litellm_facts(models: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import importlib.metadata as md

        import litellm

        table, version = litellm.model_cost, md.version("litellm")
    except Exception:  # expected: no LiteLLM means no catalog facts, which the recipe is told
        return {"version": None, "entries": {}}
    fields = [*kw_mod.CATALOG_FIELDS, "max_input_tokens"]
    entries: dict[str, Any] = {}
    for m in models:
        for label in m["listed_as"]:
            inv = label.split(": ", 1)[1]
            e = table.get(inv) or table.get(m["model_id"]) or {}
            entries[inv] = {f: e[f] for f in fields if f in e}
    return {"version": version, "entries": entries}


def assess(home: Path, ids: list[str], profile: str, *, timeout: float | None = None, today: dt.date | None = None,
           recipe_dir: Path | None = None, project_api: Any = None) -> dict[str, Any]:
    """Assess ``ids`` through ``profile`` and write the overlay; returns the report. ``AssessError`` when refused."""
    from .engine import Api
    from .project import init

    home = Path(home)
    today = today or dt.date.today()
    voc = vocab_mod.load(vocab_mod.DEFAULT)
    data = kw_mod.load_with_overlay(voc, home)
    ids = list(dict.fromkeys(ids))
    models = wanted(home, data, ids)
    recipe = recipe_dir or fetch_recipe(home)
    inputs = {
        "title": f"Model assessment {today.isoformat()}",
        "models": models,
        "today": today.isoformat(),
        "capabilities": {"capabilities": voc.capabilities, "tiers": voc.tiers, "machine_dependent": data.machine_dependent},
        "litellm": litellm_facts(models),
        "validator": validator_command(),
    }
    scratch = Path(tempfile.mkdtemp(prefix="baton-assessment-run-"))
    try:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=scratch, check=True)
        for k, v in (("user.email", "assess@localhost"), ("user.name", "assessment")):
            subprocess.run(["git", "config", k, v], cwd=scratch, check=True)
        init(scratch, bare=True)
        api = Api.open(scratch, director_id="assessment@localhost", home=str(home))
        ref = api.vendor(recipe)["recipe"]
        run = api.start(ref, json.loads(json.dumps(inputs, default=str)))["run_id"]
        out = api.dispatch(run, "assess", profile, wait=True)
        if out.get("outcome") is None and timeout is not None:
            out = {**out, **api.wait(run, timeout=timeout)}
        if out.get("outcome") != "passed":
            raise AssessError(f"the assessment step did not pass: {json.dumps({k: out.get(k) for k in ('outcome', 'reasons')}, default=str)}")
        result = scratch / ".baton" / "runs" / run / "steps" / "assess" / f"attempt-{out['attempt']}" / "result"
        doc = json.loads((result / "result.json").read_text(encoding="utf-8"))
        art = next(a for a in doc["artifacts"] if a["name"] == "overlay")
        proposal = yaml.safe_load((result / art["path"]).read_text(encoding="utf-8"))
        report = doc.get("output") or {}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if not isinstance(proposal, dict):
        raise AssessError("the worker's overlay is not a mapping; nothing was written")
    proposal = {"format": kw_mod.FORMAT, "models": {m: v for m, v in (proposal.get("models") or {}).items() if m in ids}}
    problems = check_overlay_text(yaml.safe_dump(proposal, sort_keys=False), home)
    if problems:
        raise AssessError("Baton's validator refused the worker's overlay; nothing was written:\n  - " + "\n  - ".join(problems))
    merged = merged_overlay(home, proposal)
    path = Path(home) / kw_mod.LOCAL_FILE
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text("# Written by baton workers assess (§6.4). Yours to edit; `baton workers setup` applies it.\n" + yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    rdir = home / "assessments"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / f"{today.isoformat()}.json").write_text(json.dumps({"profile": profile, "requested": ids, **report}, indent=1, default=str), encoding="utf-8")
    return {"overlay": str(path), "assessed": report.get("assessed") or [], "not_assessed": report.get("not_assessed") or [],
            "written": sorted(proposal["models"]), "note": "`baton workers setup` now gives their listed workers the new tier and capabilities"}
