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

import json
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
GENERATED_PROFILES = "workers"  # one generated profile per file (§6.4)
GITIGNORE_LINES = (".baton/cache/", ".baton/workers.local.yaml")
#: ``.baton/.gitattributes``: git must never rewrite line endings under .baton/
#: (hash-chained logs, content-addressed blobs, hashed recipes), whatever a
#: clone's ``core.autocrlf`` says (§15.1).
GITATTRIBUTES_RULE = "* -text"
GITATTRIBUTES = f"# Written by baton init: stored bytes are hashed; never convert line endings.\n{GITATTRIBUTES_RULE}\n"

DEFAULT_PROJECT_YAML = """\
# Baton project configuration (§4.3). Commit this file; never put secrets here.
paths: { process_plans: docs, notes: docs }   # logical path keys (folders) for publishing, e.g. specs: docs/specs
project: { name: __NAME__ }   # project variables, e.g. test_command: "pytest -q"; name: its lasting name (the local page's address)
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
policy:                       # rules every run follows; change with `baton policy set` (a hand edit waits for the owner's confirmation)
  floors: {}                  # lowest rating per recipe and axis, e.g. { eng-process: { assurance: medium }, "*": { release: medium } }
  governing: []               # the recipe for a kind of work (advice), e.g. [ { work: "software development", recipe: eng-process } ]
permissions:                  # release authority, part of the policy: what the runtime and the Director may do to the repo and remotes: allow | ask | deny
  push: { docs_only: allow, after_verified: allow, other: ask }
  tag: ask
  force_push: deny
  merge: deny
  deploy: deny
docs_only_globs: ["docs/**", "**/*.md", ".baton/runs/**", ".baton/project/**", ".baton/platform/**", ".baton/process/**"]
"""

#: Skills shipped with the runtime and vendored into projects (§4.3, §13.3).
SKILLS: tuple[str, ...] = ("baton-director", "baton-worker")
SKILLS_DIR = ".agents/skills"


#: Recipes shipped with the runtime (§11.1): loaded from ``builtin/``, never vendored.
BUILTIN_RECIPES: dict[str, str] = {"baton-adopt@1": "baton-adopt", "baton-frame@1": "baton-frame", "baton-frame@2": "baton-frame-2"}

#: Recipes ``init`` vendors unless ``--bare`` (§11.6): the starter kit an owner needs to begin.
STARTER_RECIPES: tuple[str, ...] = ("fit-check",)


def catalog_dir() -> Path:
    """Where the recipes shipped with the runtime live (``examples/recipes``, §5.7)."""
    return data.path("examples") / "recipes"


def catalog() -> dict[str, LoadedRecipe]:
    """The shipped recipes (the catalog framing proposes from, §11.6), by recipe id; the highest version of each."""
    out: dict[str, LoadedRecipe] = {}
    root = catalog_dir()
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not (d / "recipe.yaml").is_file():
            continue
        try:
            loaded = load_recipe(d)
        except RecipeError as e:  # pragma: no cover - shipped recipes are tested
            raise EngineError("recipe.invalid", f"shipped recipe {d.name} is invalid: {e}") from e
        prev = out.get(loaded.recipe.id)
        if prev is None or loaded.recipe.version > prev.recipe.version:
            out[loaded.recipe.id] = loaded
    return out


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


def project_name(root: Path, config: Any = None) -> str:
    """``project.name`` (slugified), else the folder's name: what the project is called on this machine's local page."""
    if config is None:
        config, _ = load_config(Path(root) / BATON_DIR / PROJECT_FILE)
    given = (config.project.get("name") if config is not None else None) or Path(root).name
    return slugify(given, 40) if str(given).strip() else "project"


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

    @classmethod
    def over_store(cls, store: Store) -> Project:
        """A view of the project a store belongs to, for reading its lockfile and vendored recipes (no configuration)."""
        return cls(store.root, store, None, machine_home())  # type: ignore[arg-type]

    @property
    def baton(self) -> Path:
        return self.root / BATON_DIR

    @property
    def recipes_dir(self) -> Path:
        return self.baton / "recipes"

    # -- policy (§13.7; Decisions 0143, 0151, 0153) ---------------------------

    def policy_state(self) -> Any:
        """The project policy: in force, in the file, and recorded (``policy.State``)."""
        from . import policy

        return policy.current(self.store.project_log().events(), self.config)

    def permissions_in_force(self) -> Any:
        """The action permissions the runtime enforces: the recorded ones (the file's until a first record)."""
        return self.policy_state().permissions()

    def reload_config(self) -> None:
        config, issues = load_config(self.baton / PROJECT_FILE)
        if config is None:
            raise EngineError("configuration.project", "; ".join(f"{i.where}: {i.message}" for i in issues))
        self.config = config

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

    @property
    def name(self) -> str:
        """The project's lasting name: ``project.name`` in ``project.yaml``, else its folder's name, as a slug
        (the local page's address, §13.9; Decision 0171, item 2)."""
        return project_name(self.root, self.config)

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
        """Generated profiles (``workers/``, one per file), then the owner's machine profiles, then
        project-local overrides, each by name (§6.1, §6.4)."""
        vocab = load_vocab(DEFAULT_VOCAB)
        out: dict[str, WorkerProfile] = {}
        issues: list[Issue] = []
        gen = self.home / GENERATED_PROFILES
        for path in sorted(gen.glob("*.yaml")) if gen.is_dir() else []:
            try:
                raw = load_yaml(path)
            except YamlError as e:
                issues.append(Issue(code="yaml.invalid", where=str(path), message=str(e)))
                continue
            found, problems = validate_profiles({path.stem: raw}, vocab, source=str(path))
            out.update(found)
            issues += problems
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
        from . import capability_states

        try:
            states = capability_states.load(self.home)
        except capability_states.CapabilityStatesError as e:
            raise EngineError("configuration.capability_states", str(e)) from e
        from . import quota

        from . import resources

        until = quota.load(self.home)
        off = resources.switched_off(self.home)
        from . import runner_tools

        declared = resources.declared_search(self.home)
        search = declared.provider if declared is not None else None

        def provided(p: WorkerProfile, recorded: dict[str, Any]) -> WorkerProfile:
            tool_use = recorded.get("tool_use")
            absent = tool_use is not None and tool_use.state == "absent"
            return p.with_provided(runner_tools.provided(p.adapter, p.capabilities, absent, p.model, search),
                                   runner_tools.search_backend(p.model, search))

        shaped = {n: (lambda q: q.with_quota(until[n]) if n in until else q)(provided(p, states.get(n, {})).with_capability_states(states.get(n, {})))
                  for n, p in out.items()}
        return {n: (p.with_switched_off(True) if p.resource in off else p) for n, p in shaped.items()}

    # -- git ----------------------------------------------------------------

    def branch(self) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(self.root), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True, check=False
            )
        except FileNotFoundError:  # expected: no git: there is no current branch
            return None
        return out.stdout.strip() or None


def _ref_key(ref: str) -> tuple[str, int]:
    rid, _, ver = ref.partition("@")
    return rid, int(ver) if ver.isdigit() else 0


def read_lock(path: Path) -> dict[str, Any]:
    """The lockfile in the current format (the previous one is upcast in memory, §14.2)."""
    import json

    if not path.is_file():
        raise EngineError("project.no_lock", f"{path} is missing (run `baton init`)")
    try:
        lock = json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise EngineError("project.bad_lock", f"{path} is not valid JSON: {e}") from e
    if not isinstance(lock, dict):
        raise EngineError("project.bad_lock", f"{path} is not a JSON object")
    problem = versions.format_problem("lock", lock.get("format"), "baton.lock")
    if problem is not None:
        raise EngineError(problem[0], problem[1])
    if versions.classify("lock", lock.get("format")) != "current":
        lock = versions.upcast("lock", lock)
    return lock


# ---------------------------------------------------------------------------
# Setup: init and vendor (§13.1, §14)
# ---------------------------------------------------------------------------


def _record_initial_policy(root: Path) -> None:
    """``init`` records the policy it wrote, so the defaults count as recorded (§13.7; Decision 0153)."""
    from . import policy
    from .locks import project_lock

    config, _ = load_config(root / BATON_DIR / PROJECT_FILE)
    assert config is not None  # the default is valid
    store = Store(root)
    try:
        if any(e.type == "policy_changed" for e in store.project_log().events()):
            return
        value = policy.value_of(config)
        sha = store.project_cas.put(data_bytes(value))
        with project_lock(root / BATON_DIR):
            store.project_log().append("policy_changed", actor="runtime:init",
                                       data={"before": None, "after": value, "sha256": sha, "decision_id": None, "changes": policy.differences(None, value)})
    finally:
        store.close()


def data_bytes(value: Any) -> bytes:
    from .store import canonical_json

    return canonical_json(value).encode("utf-8")


def init(root: str | Path, *, agents_md: bool = True, bare: bool = False) -> dict[str, Any]:
    """Create ``.baton/`` with defaults. Existing files are left untouched.

    Unless ``bare``, also vendors the starter recipes (``STARTER_RECIPES``, §11.6) that are not
    vendored yet in any version, so a Director can begin with the owner straight away.

    Also vendors the director and worker skills into ``.agents/skills/`` and, unless
    ``agents_md`` is false (adoption, where the baseline proposes it, §11.5), writes the
    ``AGENTS.md`` pointer line (created, or appended to an existing file).
    """
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

    create(f"{BATON_DIR}/{PROJECT_FILE}", DEFAULT_PROJECT_YAML.replace("__NAME__", json.dumps(r.name)))
    if f"{BATON_DIR}/{PROJECT_FILE}" in created:
        _record_initial_policy(r)
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

    for name in SKILLS:
        create(f"{SKILLS_DIR}/{name}/SKILL.md", read_text(data.path("skills") / name / "SKILL.md"))
    if agents_md:
        from .adopt import AGENTS_POINTER

        am = r / "AGENTS.md"
        if not am.is_file():
            create("AGENTS.md", AGENTS_POINTER + "\n")
        elif AGENTS_POINTER not in read_text(am):
            text = read_text(am)
            am.write_bytes((text + ("" if text.endswith("\n") or not text else "\n") + AGENTS_POINTER + "\n").encode("utf-8"))
            created.append("AGENTS.md (pointer appended)")

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
    from .resources import readiness

    worker_setup = readiness(machine_home())
    if worker_setup["offer_setup"]:
        notes.append("this machine's workers are not set up yet: `baton workers setup`, or ask the Director to walk you through it")
    vendored: list[str] = []
    if not bare:
        shipped = catalog()
        project = Project.open(r)
        try:
            have = {ref.split("@", 1)[0] for ref in project.vendored()}
            for rid in STARTER_RECIPES:
                if rid in have or rid not in shipped:
                    continue
                out = vendor(project, shipped[rid].root)
                if out["changed"]:
                    vendored.append(out["recipe"])
                    created.append(f"{BATON_DIR}/recipes/{out['recipe']}/")
        finally:
            project.store.close()
    return {"root": str(r), "created": created, "notes": notes, "vendored": vendored, "worker_setup": worker_setup}


def signature_flags(lock: dict[str, Any], recipe_id: str, version: int, steps: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """What vendoring ``recipe_id@version`` would change about step ids the project has used (§5.8).

    ``signature_changed``: a kept id whose signature differs from a recorded version's.
    ``retired_id_reused``: an id an earlier version had, the recorded versions since then dropped,
    and this (later) version brings back. Each needs an owner decision.
    """
    recorded: dict[int, dict[str, Any]] = {}
    for ref, entry in (lock.get("recipes") or {}).items():
        rid, _, ver = ref.partition("@")
        if rid == recipe_id and ver.isdigit() and int(ver) != version:
            recorded[int(ver)] = entry.get("steps") or {}
    flags: list[dict[str, Any]] = []
    for sid in sorted(steps):
        sig = steps[sid]
        differs = {v: sorted(k for k in set(sig) | set(old[sid]) if sig.get(k) != old[sid].get(k))
                   for v, old in sorted(recorded.items()) if sid in old and old[sid] != sig}
        if differs:
            flags.append({"code": "signature_changed", "step": sid, "versions": sorted(differs),
                          "changed": sorted({k for ks in differs.values() for k in ks})})
        had = sorted(v for v, old in recorded.items() if sid in old and v < version)
        # Retired: absent from every recorded version since it last appeared (before this one).
        retired = sorted(v for v, old in recorded.items() if had and had[-1] < v < version and sid not in old)
        if retired:
            flags.append({"code": "retired_id_reused", "step": sid, "present_in": had, "retired_in": retired})
    return flags


def program_flags(lock: dict[str, Any], loaded: LoadedRecipe) -> list[dict[str, Any]]:
    """Each program the owner has not approved in this project yet, in the owner's terms (§5.9; criterion 10).

    A program whose exact files were approved with any vendored version of the
    same recipe is not asked about again; a new or changed program is.
    """
    from .program_env import describe

    approved: set[tuple[str, str]] = set()
    for ref, entry in (lock.get("recipes") or {}).items():
        if ref.partition("@")[0] == loaded.recipe.id:
            approved |= {(tid, sha) for tid, sha in (entry.get("programs") or {}).items()}
    out = []
    for tid, program in sorted(loaded.programs.items()):
        if (tid, program.sha256) not in approved:
            changed = any(t == tid for t, _ in approved)
            out.append({"code": "program", **describe(program), "sha256": program.sha256, "changed": changed})
    return out


def vendor(project: Project, src: str | Path, *, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    """Copy a recipe package into ``.baton/recipes/<id>@<version>/`` and record it in the lockfile.

    A vendored version is never edited in place: vendoring different content
    under an existing ``id@version`` is refused. When the new version changes a kept
    step id's signature or reuses a retired id (§5.8), nothing is copied and the result
    carries ``needs_owner`` and the ``flags``, unless ``decision`` (the owner's recorded
    decision: ``decision_id``, ``note``) is given; it is then kept in the lock entry.
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
            return {"recipe": ref, "sha256": loaded.sha256, "changed": False, "flags": [], "needs_owner": False}
        raise EngineError(
            "vendor.version_exists",
            f"{ref} is already vendored with different content; publish a new recipe version instead of editing one in place",
        )
    unbuilt = sorted(tid for tid, t in loaded.programs.items() if not t.built)
    if unbuilt:
        raise EngineError("vendor.program_unbuilt", f"{ref} has programs that are not built yet ({', '.join(unbuilt)}); "
                          "an engineered program is vendored only once it is built and passes its examples")
    steps = versions.step_signatures(loaded)
    flags = signature_flags(lock, loaded.recipe.id, loaded.recipe.version, steps) + program_flags(lock, loaded)
    if flags and decision is None:
        why = ("it brings programs that run on this machine" if all(f["code"] == "program" for f in flags)
               else "it changes step ids this project has used" if not any(f["code"] == "program" for f in flags)
               else "it changes step ids this project has used and brings programs that run on this machine")
        return {"recipe": ref, "sha256": loaded.sha256, "changed": False, "flags": flags, "needs_owner": True,
                "message": f"vendoring {ref}: {why}; it needs the owner's decision: "
                           "repeat with --approved --note \"<the owner's words>\""}
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
        "steps": steps,
    }
    if loaded.programs:  # only a recipe with programs carries the key (criterion 11)
        lock["recipes"][ref]["programs"] = {tid: t.sha256 for tid, t in sorted(loaded.programs.items())}
    if flags and decision is not None:
        lock["recipes"][ref]["decision"] = {**decision, "flags": flags}
    if loaded.recipe.capabilities_vocab not in lock.setdefault("vocab", []):
        lock["vocab"].append(loaded.recipe.capabilities_vocab)
    write_lock(project, lock)
    return {"recipe": ref, "sha256": loaded.sha256, "changed": True, "flags": flags, "needs_owner": False}


def write_lock(project: Project, lock: dict[str, Any]) -> None:
    atomic_write(project.baton / LOCK_FILE, versions.dump_lock(lock).encode("utf-8"))


def vendor_skills(root: Path) -> dict[str, list[str]]:
    """Write the shipped skills into ``.agents/skills/`` (``upgrade``, §14.3): replaced, created, unchanged."""
    out: dict[str, list[str]] = {"created": [], "replaced": [], "unchanged": []}
    for name in SKILLS:
        rel = f"{SKILLS_DIR}/{name}/SKILL.md"
        p = root / rel
        shipped = read_text(data.path("skills") / name / "SKILL.md").encode("utf-8")
        if p.is_file() and p.read_bytes() == shipped:
            out["unchanged"].append(rel)
            continue
        out["replaced" if p.exists() else "created"].append(rel)
        atomic_write(p, shipped)
    return out
