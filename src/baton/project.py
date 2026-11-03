"""A project using Baton (§4.3): its root, configuration, lockfile, vendored recipes and profiles.

Layout under ``<project>/.baton/``::

    project.yaml          non-secret configuration (models.ProjectConfig)
    communication.md      owner communication contract (§13.6)
    baton.lock            runtime, formats, vocabulary, vendored recipe hashes (versions.py)
    recipes/<id>@<ver>/   vendored, pinned recipe packages
    workers.local.yaml    GITIGNORED project-specific profile overrides
    cache/                GITIGNORED

Machine-local files live in ``$BATON_HOME`` (default ``~/.baton``, §4.4):
``workers.yaml`` holds worker profiles.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
from pydantic import ValidationError

from . import data, versions
from .data import YamlError, load_yaml, read_text
from .models import Issue, ProjectConfig, WorkerProfile
from .packet import EngineError, RunContext
from .profiles import ProfileError, validate_profiles
from .recipe import LoadedRecipe, RecipeError, load_recipe, package_sha256
from .store import BATON_DIR, Store, atomic_write, ensure_dir, utc_now
from .vocab import DEFAULT as DEFAULT_VOCAB
from .vocab import load as load_vocab

PROJECT_FILE = "project.yaml"
COMM_FILE = "communication.md"
LOCK_FILE = "baton.lock"
LOCAL_PROFILES = "workers.local.yaml"
MACHINE_PROFILES = "workers.yaml"
GITIGNORE_LINES = (".baton/cache/", ".baton/workers.local.yaml")
#: ``.baton/.gitattributes``: git must never rewrite line endings under .baton/
#: (hash-chained logs, content-addressed blobs, hashed recipes), whatever a
#: clone's ``core.autocrlf`` says (§15.1).
GITATTRIBUTES_RULE = "* -text"
GITATTRIBUTES = f"# Written by baton init: stored bytes are hashed; never convert line endings.\n{GITATTRIBUTES_RULE}\n"

DEFAULT_PROJECT_YAML = """\
# Baton project configuration (§4.3). Commit this file; never put secrets here.
paths: {}                     # logical path keys for publishing, e.g. specs: docs/specs
project: {}                   # project variables, e.g. test_command: "pytest -q"
run_slug: "{{ run.inputs.title | slugify }}"
leases: { minutes: 60 }       # renewed on activity
checkpoints: { commit: true } # commit the run's record at checkpoints, on the current branch
lfs: { threshold_mb: 5 }      # with git-lfs installed, larger stored blobs go to LFS
contacts: { owner: owner }
effort:                       # time a worker gets per step effort; overdue once -> one more band
  bands: { S: 45m, M: 2h, L: 4h }
  extend_once: true
  default: M                  # steps that declare no effort
hooks:                        # completion hooks (shell commands, non-secret); machine hooks: ~/.baton/hooks.yaml
  on_complete: ""
  on_needs_human: ""          # falls back to on_complete
  on_platform_failure: ""     # falls back to on_complete
"""


#: Recipes shipped with the runtime (§11.1): loaded from ``builtin/``, never vendored.
BUILTIN_RECIPES: dict[str, str] = {"baton-adopt@1": "baton-adopt"}


def builtin_recipe(ref: str) -> LoadedRecipe:
    try:
        return load_recipe(data.path("builtin") / BUILTIN_RECIPES[ref])
    except RecipeError as e:  # pragma: no cover - shipped recipes are tested
        raise EngineError("recipe.invalid", f"built-in recipe {ref} is invalid: {e}") from e


def machine_home() -> Path:
    return Path(os.environ.get("BATON_HOME") or Path.home() / ".baton")


def slugify(value: Any, max_len: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return s[:max_len].rstrip("-") or "run"


def find_root(start: str | Path | None = None) -> Path:
    """The nearest directory at or above ``start`` holding ``.baton/project.yaml``."""
    here = Path(start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / BATON_DIR / PROJECT_FILE).is_file():
            return d
    raise EngineError("project.not_found", f"no Baton project at or above {here} (run `baton init` in the project root)")


def _secret_refs(value: Any, where: str) -> list[str]:
    if isinstance(value, str):
        return [where] if "secret:" in value else []
    if isinstance(value, dict):
        return [w for k, v in value.items() for w in _secret_refs(v, f"{where}.{k}" if where else str(k))]
    if isinstance(value, list):
        return [w for i, v in enumerate(value) for w in _secret_refs(v, f"{where}[{i}]")]
    return []


def load_config(path: Path) -> tuple[ProjectConfig | None, list[Issue]]:
    where = str(path)
    if not path.is_file():
        return None, [Issue(code="project.missing", where=where, message="project.yaml is missing (run `baton init`)")]
    try:
        raw = load_yaml(path)
    except YamlError as e:
        return None, [Issue(code="yaml.invalid", where=where, message=str(e))]
    raw = raw or {}
    if not isinstance(raw, dict):
        return None, [Issue(code="project.invalid", where=where, message="project.yaml must be a mapping")]
    issues = [
        Issue(code="project.secret_reference", where=f"{where}:{w}", message="secret: references belong in machine-level configuration only")
        for w in _secret_refs(raw, "")
    ]
    try:
        config = ProjectConfig.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            issues.append(Issue(code="project.invalid", where=f"{where}:{loc}", message=err["msg"]))
        return None, issues
    return (None if issues else config), issues


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


@dataclass
class Project:
    root: Path
    store: Store
    config: ProjectConfig
    home: Path
    _recipes: dict[str, LoadedRecipe] = field(default_factory=dict)

    @classmethod
    def open(cls, root: str | Path | None = None, *, home: str | Path | None = None, clock: Any = utc_now) -> Project:
        r = find_root(root)
        config, issues = load_config(r / BATON_DIR / PROJECT_FILE)
        if config is None:
            raise EngineError("configuration.project", "; ".join(f"{i.where}: {i.message}" for i in issues))
        return cls(r, Store(r, clock=clock), config, Path(home) if home else machine_home())

    @property
    def baton(self) -> Path:
        return self.root / BATON_DIR

    @property
    def recipes_dir(self) -> Path:
        return self.baton / "recipes"

    # -- lockfile -----------------------------------------------------------

    def lock(self) -> dict[str, Any]:
        return read_lock(self.baton / LOCK_FILE)

    # -- recipes ------------------------------------------------------------

    def vendored(self) -> list[str]:
        """Recipe refs (``id@version``) recorded in the lockfile, sorted."""
        return sorted(self.lock().get("recipes", {}), key=_ref_key)

    def resolve_ref(self, ref: str) -> str:
        known = self.vendored()
        if ref in known:
            return ref
        if "@" not in ref:
            same = [r for r in known if r.split("@", 1)[0] == ref]
            if same:
                return same[-1]
        raise EngineError("recipe.not_vendored", f"recipe {ref!r} is not vendored in this project (vendored: {', '.join(known) or 'none'})")

    def recipe(self, ref: str) -> LoadedRecipe:
        """A vendored recipe, verified against its lockfile hash (or a built-in one, §11.1)."""
        if ref in BUILTIN_RECIPES:
            if ref not in self._recipes:
                self._recipes[ref] = builtin_recipe(ref)
            return self._recipes[ref]
        ref = self.resolve_ref(ref)
        if ref not in self._recipes:
            entry = self.lock()["recipes"][ref]
            root = self.recipes_dir / ref
            if not (root / "recipe.yaml").is_file():
                raise EngineError("recipe.missing", f"vendored recipe {ref} is missing at {root}")
            try:
                loaded = load_recipe(root)
            except RecipeError as e:
                raise EngineError("recipe.invalid", f"vendored recipe {ref} is invalid: {e}") from e
            if loaded.sha256 != entry.get("sha256"):
                raise EngineError("recipe.lock_mismatch", f"vendored recipe {ref} does not match its lockfile hash (it was edited in place)")
            self._recipes[ref] = loaded
        return self._recipes[ref]

    def recipe_for_run(self, run_id: str) -> LoadedRecipe:
        started = self.store.run(run_id).events()[0].data
        loaded = self.recipe(started["recipe"])
        if loaded.sha256 != started.get("recipe_sha256"):
            raise EngineError("run.recipe_mismatch", f"run {run_id} is pinned to {started['recipe']} with a different hash than the vendored copy")
        return loaded

    def context(self, run_id: str) -> RunContext:
        return RunContext(self.store, run_id, self.recipe_for_run(run_id), self.variables())

    def variables(self) -> dict[str, Any]:
        """Non-secret configuration for templates (``project.*``, ``paths.*``)."""
        return {"project": dict(self.config.project), "paths": dict(self.config.paths)}

    def render_slug(self, inputs: dict[str, Any], title: str | None) -> str:
        env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
        env.filters["slugify"] = slugify
        try:
            text = env.from_string(self.config.run_slug).render(run={"inputs": inputs, "title": title}, project=self.config.project)
        except jinja2.TemplateError as e:
            raise EngineError("configuration.run_slug", f"run_slug {self.config.run_slug!r} cannot be rendered: {e}") from e
        return slugify(text)

    # -- profiles -----------------------------------------------------------

    def profiles(self) -> dict[str, WorkerProfile]:
        """Machine profiles, then project-local overrides by name (§6.1)."""
        vocab = load_vocab(DEFAULT_VOCAB)
        out: dict[str, WorkerProfile] = {}
        issues: list[Issue] = []
        for path in (self.home / MACHINE_PROFILES, self.baton / LOCAL_PROFILES):
            if not path.is_file():
                continue
            try:
                raw = load_yaml(path)
            except YamlError as e:
                issues.append(Issue(code="yaml.invalid", where=str(path), message=str(e)))
                continue
            found, problems = validate_profiles(raw or {}, vocab, source=str(path))
            out.update(found)
            issues += problems
        if issues:
            raise EngineError("configuration.profiles", str(ProfileError(issues)))
        return out

    # -- git ----------------------------------------------------------------

    def branch(self) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(self.root), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True, check=False
            )
        except FileNotFoundError:
            return None
        return out.stdout.strip() or None


def _ref_key(ref: str) -> tuple[str, int]:
    rid, _, ver = ref.partition("@")
    return rid, int(ver) if ver.isdigit() else 0


def read_lock(path: Path) -> dict[str, Any]:
    import json

    if not path.is_file():
        raise EngineError("project.no_lock", f"{path} is missing (run `baton init`)")
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise EngineError("project.bad_lock", f"{path} is not valid JSON: {e}") from e


# ---------------------------------------------------------------------------
# Setup: init and vendor (§13.1, §14)
# ---------------------------------------------------------------------------


def init(root: str | Path) -> dict[str, Any]:
    """Create ``.baton/`` with defaults. Existing files are left untouched."""
    r = Path(root).resolve()
    if not r.is_dir():
        raise EngineError("init.no_dir", f"{r} is not a directory")
    baton = ensure_dir(r / BATON_DIR)
    created: list[str] = []

    def create(rel: str, content: str) -> None:
        p = r / rel
        if not p.exists():
            atomic_write(p, content.encode("utf-8"))
            created.append(rel)

    create(f"{BATON_DIR}/{PROJECT_FILE}", DEFAULT_PROJECT_YAML)
    create(f"{BATON_DIR}/{COMM_FILE}", read_text(data.path("defaults") / COMM_FILE))
    create(f"{BATON_DIR}/{LOCK_FILE}", versions.dump_lock(versions.new_lock()))
    ensure_dir(baton / "recipes")
    ga = baton / ".gitattributes"
    if not ga.is_file():
        create(f"{BATON_DIR}/.gitattributes", GITATTRIBUTES)
    elif GITATTRIBUTES_RULE not in read_text(ga).splitlines():
        text = read_text(ga)
        ga.write_bytes((text + ("" if text.endswith("\n") or not text else "\n") + GITATTRIBUTES).encode("utf-8"))
        created.append(f"{BATON_DIR}/.gitattributes (updated)")

    gi = r / ".gitignore"
    existing = read_text(gi).splitlines() if gi.is_file() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing:
        text = read_text(gi) if gi.is_file() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        text += "".join(f"{line}\n" for line in missing)
        gi.write_bytes(text.encode("utf-8"))
        created.append(".gitignore" if not existing else ".gitignore (updated)")

    from .gitops import is_repo, lfs_available

    notes = []
    if not is_repo(r):
        notes.append("not a git repository: checkpoint commits start once it is one")
    elif not lfs_available(r):
        notes.append("git-lfs is not installed: large stored blobs will be committed to git directly")
    return {"root": str(r), "created": created, "notes": notes}


def vendor(project: Project, src: str | Path) -> dict[str, Any]:
    """Copy a recipe package into ``.baton/recipes/<id>@<version>/`` and record it in the lockfile.

    A vendored version is never edited in place: vendoring different content
    under an existing ``id@version`` is refused.
    """
    try:
        loaded = load_recipe(src)
    except RecipeError as e:
        raise EngineError("recipe.invalid", str(e)) from e
    ref = loaded.recipe.ref
    target = project.recipes_dir / ref
    lock = project.lock()
    entry = lock.setdefault("recipes", {}).get(ref)
    if target.exists() or entry is not None:
        if target.exists() and entry is not None and package_sha256(target) == loaded.sha256 == entry.get("sha256"):
            return {"recipe": ref, "sha256": loaded.sha256, "changed": False}
        raise EngineError(
            "vendor.version_exists",
            f"{ref} is already vendored with different content; publish a new recipe version instead of editing one in place",
        )
    tmp = project.recipes_dir / f".vendor-{ref}"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(loaded.root, tmp, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if package_sha256(tmp) != loaded.sha256:  # pragma: no cover - copy is byte-exact
        shutil.rmtree(tmp)
        raise EngineError("vendor.copy_mismatch", f"vendored copy of {ref} does not hash like its source")
    os.replace(tmp, target)
    lock["recipes"][ref] = {
        "sha256": loaded.sha256,
        "vocab": loaded.recipe.capabilities_vocab,
        "steps": versions.step_signatures(loaded),
    }
    if loaded.recipe.capabilities_vocab not in lock.setdefault("vocab", []):
        lock["vocab"].append(loaded.recipe.capabilities_vocab)
    atomic_write(project.baton / LOCK_FILE, versions.dump_lock(lock).encode("utf-8"))
    return {"recipe": ref, "sha256": loaded.sha256, "changed": True}
