"""Worker profiles (§6.1): loading, secrets, environment construction and PATH resolution (§6.2).

``build_env`` is the one place a worker's environment is made:

1. start empty (``clean``, ``allowlist``) or from the parent (``inherit``);
2. copy the allowed variables (``allowlist``: the base list plus ``env_allow``);
3. build ``PATH`` (``path.prepend``, then the minimal system PATH, or the
   parent's PATH under ``inherit``), with the resolved executable's directory first;
4. inject resolved secrets for ``auth.mode: api_key`` (``auth.env``);
5. set the adapter's config-home variable when ``auth.config_home`` is set;
6. **remove ``env_deny`` last** (exact names or ``fnmatch`` patterns), so a
   denied name never reaches the worker, whatever put it there;
7. add ``BATON_PACKET_DIR``, ``BATON_RESULT_DIR``, ``BATON_WORKSPACE``.

Only variable *names* are reported or recorded. Secret values are resolved at
spawn time and registered with ``redact`` so they never reach anything committed.

**Secrets** (``secret:<name>``) resolve, in order, from the environment variable
``BATON_SECRET_<NAME>`` (name upper-cased, other characters as ``_``), the OS
keyring (service ``baton``, if the optional ``keyring`` package is installed), or
the file ``$BATON_HOME/secrets/<name>`` (whitespace stripped). A missing secret
is a ``configuration`` failure naming exactly where it was looked for.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from pydantic import ValidationError

from . import redact
from . import vocab as vocab_mod
from .data import YamlError, load_yaml
from .models import Issue, WorkerProfile
from .vocab import Vocabulary

SECRET_PREFIX = "secret:"

#: Variables ``allowlist`` passes before ``env_allow`` (§6.1).
ALLOWLIST_BASE = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "TERM")
#: On Windows a child process cannot start its runtime without these, whatever the mode.
WINDOWS_ESSENTIAL = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")
#: Minimal system PATH (§6.2 step 2).
POSIX_SYSTEM_PATH = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin")
#: ``path.search`` source names; anything else must be a directory path.
SEARCH_SOURCES = ("nvm", "pyenv", "asdf")
#: Variables the runtime adds last.
BATON_VARS = ("BATON_PACKET_DIR", "BATON_RESULT_DIR", "BATON_WORKSPACE")


#: Executable used when a harness profile names none (§6.3 presets).
DEFAULT_EXECUTABLES = {"claude_code": "claude", "codex": "codex"}


def executable_for(profile: WorkerProfile) -> str | None:
    """The executable to resolve: ``executable``, else the preset's default, else the ``command`` adapter's first word."""
    if profile.executable:
        return profile.executable
    if profile.adapter in DEFAULT_EXECUTABLES:
        return DEFAULT_EXECUTABLES[profile.adapter]
    if profile.adapter == "command" and profile.command:
        words = split_command(profile.command)
        return words[0] if words else None
    return None


def split_command(line: str) -> list[str]:
    """Split a command line into words like a shell would, without running one.

    POSIX: ``shlex`` rules. Windows: the same quoting, but a backslash is an
    ordinary character, so ``C:\\tools\\x.exe`` stays intact.
    """
    import shlex

    if os.name != "nt":
        return shlex.split(line)
    lex = shlex.shlex(line, posix=True)
    lex.whitespace_split = True
    lex.escape = ""
    lex.commenters = ""
    return list(lex)


class ProfileError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}


class SetupError(Exception):
    """A worker cannot be started on this machine.

    ``failure_class`` is ``configuration`` (the owner fixes a file or secret) or
    ``platform`` (the machine lacks something, e.g. an executable, §8.8).
    """

    def __init__(self, code: str, message: str, failure_class: str, **detail: object):
        super().__init__(message)
        self.code = code
        self.failure_class = failure_class
        self.detail = detail


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def _secret_refs(value: object, where: str) -> list[str]:
    if isinstance(value, str):
        return [where] if SECRET_PREFIX in value else []
    if isinstance(value, dict):
        return [w for k, v in value.items() for w in _secret_refs(v, f"{where}.{k}")]
    if isinstance(value, list):
        return [w for i, v in enumerate(value) for w in _secret_refs(v, f"{where}[{i}]")]
    return []


def validate_profiles(raw: object, vocab: Vocabulary, source: str = "workers.yaml") -> tuple[dict[str, WorkerProfile], list[Issue]]:
    issues: list[Issue] = []
    profiles: dict[str, WorkerProfile] = {}
    if not isinstance(raw, dict):
        return {}, [Issue(code="profile.not_a_mapping", where=source, message="profiles must be a mapping of name -> profile")]
    for name, body in raw.items():
        where = f"{source}:{name}"
        try:
            profile = WorkerProfile.model_validate(body)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                issues.append(Issue(code="profile.invalid", where=f"{where}.{loc}" if loc else where, message=err["msg"]))
            continue
        for cap in profile.capabilities:
            if cap not in vocab.capabilities:
                issues.append(
                    Issue(code="vocab.unknown_capability", where=f"{where}.capabilities", message=f"capability {cap!r} is not in {vocab.id}")
                )
        if profile.tier is not None and profile.tier not in vocab.tiers:
            issues.append(Issue(code="vocab.unknown_tier", where=f"{where}.tier", message=f"tier {profile.tier!r} is not one of {vocab.tiers}"))
        # secret: references belong in auth.env only; everything else may be recorded or hashed.
        body_dict = body if isinstance(body, dict) else {}
        for key, value in body_dict.items():
            if key == "auth" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if k != "env"}
            for w in _secret_refs(value, key):
                issues.append(Issue(code="profile.secret_outside_auth", where=f"{where}.{w}", message="secret: references are allowed only in auth.env"))
        for src in profile.path.search if profile.path else []:
            if src not in SEARCH_SOURCES and not _looks_like_dir(src):
                issues.append(
                    Issue(code="profile.unknown_search", where=f"{where}.path.search", message=f"{src!r} is neither one of {SEARCH_SOURCES} nor a directory path")
                )
        profiles[str(name)] = profile
    return profiles, issues


def _looks_like_dir(s: str) -> bool:
    return "/" in s or "\\" in s or s.startswith("~")


def load_profiles(path: str | Path, vocab_id: str = vocab_mod.DEFAULT) -> dict[str, WorkerProfile]:
    path = Path(path)
    try:
        raw = load_yaml(path)
    except YamlError as e:
        raise ProfileError([Issue(code="yaml.invalid", where=str(path), message=str(e))]) from e
    profiles, issues = validate_profiles(raw or {}, vocab_mod.load(vocab_id), source=path.name)
    if issues:
        raise ProfileError(issues)
    return profiles


def effective_env_mode(profile: WorkerProfile) -> str:
    """``env_mode`` if set, else ``clean`` for API keys and ``allowlist`` otherwise (§6.1)."""
    if profile.env_mode:
        return profile.env_mode
    return "clean" if profile.auth.mode == "api_key" else "allowlist"


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def secret_env_name(name: str) -> str:
    return "BATON_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def _keyring_get(name: str) -> str | None:
    try:
        import keyring  # optional dependency
    except ImportError:
        return None
    try:
        return keyring.get_password("baton", name)
    except Exception:  # noqa: BLE001 - a broken keyring backend is "not found here"
        return None


def resolve_secret(name: str, home: Path, environ: Mapping[str, str] | None = None) -> str:
    """The secret's value, from env, keyring or ``<home>/secrets/<name>``. Raises ``SetupError``."""
    environ = os.environ if environ is None else environ
    var = secret_env_name(name)
    value = environ.get(var)
    if not value:
        value = _keyring_get(name)
    path = home / "secrets" / name
    if not value and path.is_file():
        value = path.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise SetupError(
            "configuration.missing_secret",
            f"secret {name!r} is not set: set the environment variable {var}, store it in the OS keyring "
            f"(service 'baton', name {name!r}), or write it to {path}",
            "configuration",
            secret=name,
            looked_in=[f"env:{var}", f"keyring:baton/{name}", str(path)],
        )
    redact.register(value)
    return value


def resolve_value(value: str, home: Path, environ: Mapping[str, str] | None = None) -> str:
    if value.startswith(SECRET_PREFIX):
        return resolve_secret(value[len(SECRET_PREFIX):], home, environ)
    return value


# ---------------------------------------------------------------------------
# PATH resolution (§6.2)
# ---------------------------------------------------------------------------


def system_path(environ: Mapping[str, str]) -> list[str]:
    if os.name == "nt":  # pragma: no cover - Windows CI
        root = environ.get("SYSTEMROOT", r"C:\Windows")
        return [rf"{root}\System32", root, rf"{root}\System32\Wbem"]
    return list(POSIX_SYSTEM_PATH)


def _version_key(p: Path) -> tuple:
    parts = re.findall(r"\d+|[^\d]+", p.name.lstrip("v"))
    return tuple((0, int(x)) if x.isdigit() else (1, x) for x in parts)


def _newest_first(pattern_root: Path, sub: str) -> list[Path]:
    if not pattern_root.is_dir():  # still reported as searched
        return [pattern_root / "*" / sub if sub else pattern_root / "*"]
    dirs = [d for d in pattern_root.iterdir() if d.is_dir()]
    return [d / sub if sub else d for d in sorted(dirs, key=_version_key, reverse=True)]


def user_home(environ: Mapping[str, str]) -> Path:
    """The user's home (``~`` in ``path.search``): ``HOME``, else ``USERPROFILE``, else the OS's idea of it."""
    for name in ("HOME", "USERPROFILE"):
        if environ.get(name):
            return Path(environ[name])
    return Path.home()


def search_dirs(source: str, home: Path, environ: Mapping[str, str]) -> list[Path]:
    """Directories a ``path.search`` source contributes, newest version first. ``home`` is the user's home."""
    out: list[Path] = []
    if source == "nvm":
        roots = []
        if environ.get("NVM_DIR"):
            roots.append(Path(environ["NVM_DIR"]))
        roots.append(home / ".nvm")
        for r in roots:
            out += _newest_first(r / "versions" / "node", "bin")
        if environ.get("NVM_HOME"):  # nvm-windows: <NVM_HOME>/v<version>/ [VERIFY]
            out += _newest_first(Path(environ["NVM_HOME"]), "")
    elif source == "pyenv":
        roots = [Path(environ["PYENV_ROOT"])] if environ.get("PYENV_ROOT") else []
        roots.append(home / ".pyenv")
        for r in roots:
            out += _newest_first(r / "versions", "bin")
    elif source == "asdf":
        root = Path(environ["ASDF_DATA_DIR"]) if environ.get("ASDF_DATA_DIR") else home / ".asdf"
        out.append(root / "shims")
    else:
        out.append(home / source[2:] if source.startswith(("~/", "~\\")) else Path(source))
    seen: set[str] = set()
    unique = []
    for d in out:
        if str(d) not in seen:
            seen.add(str(d))
            unique.append(d)
    return unique


@dataclass
class Resolved:
    executable: str  # absolute path
    path_dir: str | None  # directory prepended to PATH (search sources only)
    how: str  # absolute | base_path | search:<source>
    searched: list[str] = field(default_factory=list)


def resolve_executable(
    profile: WorkerProfile, base_path: list[str], *, home: Path, environ: Mapping[str, str] | None = None
) -> Resolved:
    """Find ``profile.executable`` (§6.2). Raises ``SetupError`` (platform) listing every place searched."""
    environ = os.environ if environ is None else environ
    exe = executable_for(profile)
    assert exe, "resolve_executable needs an executable"
    searched: list[str] = []
    p = Path(os.path.expanduser(exe))
    if p.is_absolute():
        searched.append(str(p))
        if p.is_file() and os.access(p, os.X_OK):
            return Resolved(str(p), None, "absolute", searched)
    else:
        for d in base_path:
            searched.append(d)
            hit = shutil.which(exe, path=d)
            if hit:
                return Resolved(str(Path(hit).absolute()), None, "base_path", searched)
        for src in profile.path.search if profile.path else []:
            for d in search_dirs(src, user_home(environ), environ):
                searched.append(str(d))
                hit = shutil.which(exe, path=str(d))
                if hit:
                    return Resolved(str(Path(hit).absolute()), str(d), f"search:{src}", searched)
    raise SetupError(
        "platform.executable_not_found",
        f"executable {exe!r} not found; searched: " + ", ".join(searched or ["(nowhere)"]),
        "platform",
        executable=exe,
        searched=searched,
    )


# ---------------------------------------------------------------------------
# Environment (§6.2)
# ---------------------------------------------------------------------------


@dataclass
class BuiltEnv:
    env: dict[str, str]
    mode: str
    denied: list[str]  # names removed by env_deny
    secrets: list[str]  # names of injected variables holding resolved secrets
    resolved: Resolved | None = None

    def names(self) -> list[str]:
        return sorted(self.env)

    def describe(self) -> dict[str, object]:
        """Names only: safe to record and print."""
        out: dict[str, object] = {"env_mode": self.mode, "names": self.names(), "denied": sorted(self.denied), "secret_names": sorted(self.secrets)}
        if self.resolved is not None:
            out["executable"] = self.resolved.executable
            out["resolved_by"] = self.resolved.how
        return out


def build_env(
    profile: WorkerProfile,
    *,
    home: Path,
    packet_dir: Path | None = None,
    result_dir: Path | None = None,
    workspace: Path | None = None,
    config_home_var: str | None = None,
    environ: Mapping[str, str] | None = None,
    resolve: bool = True,
) -> BuiltEnv:
    """The exact environment a worker under ``profile`` starts with.

    Raises ``SetupError``: ``configuration`` for a missing secret or an
    unsupported ``config_home``, ``platform`` for an executable not found.
    ``resolve=False`` skips executable resolution (adapters that start the
    runtime's own interpreter).
    """
    environ = dict(os.environ if environ is None else environ)
    mode = effective_env_mode(profile)
    env: dict[str, str] = {}
    if mode == "inherit":
        env.update(environ)
    elif mode == "allowlist":
        for name in (*ALLOWLIST_BASE, *profile.env_allow):
            if name in environ:
                env[name] = environ[name]
    if os.name == "nt":  # pragma: no cover - Windows CI
        for name in WINDOWS_ESSENTIAL:
            if name in environ:
                env.setdefault(name, environ[name])

    prepend = [os.path.expanduser(p) for p in (profile.path.prepend if profile.path else [])]
    base = prepend + (environ.get("PATH", "").split(os.pathsep) if mode == "inherit" else system_path(environ))
    base = [d for d in base if d]
    resolved = None
    if resolve and executable_for(profile):
        resolved = resolve_executable(profile, base, home=home, environ=environ)
    path_dirs = ([resolved.path_dir] if resolved and resolved.path_dir else []) + base
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_dirs))

    secret_names: list[str] = []
    if profile.auth.mode == "api_key":
        for name, value in profile.auth.env.items():
            env[name] = resolve_value(value, home, environ)
            secret_names.append(name)
    if profile.auth.config_home:
        if not config_home_var:
            raise SetupError(
                "configuration.config_home_unsupported",
                f"auth.config_home is set but the {profile.adapter!r} adapter has no config-home variable",
                "configuration",
            )
        env[config_home_var] = os.path.expanduser(profile.auth.config_home)

    denied = [n for n in env if any(fnmatch.fnmatchcase(n, pat) for pat in profile.env_deny)]
    for n in denied:
        del env[n]
    secret_names = [n for n in secret_names if n in env]

    for name, value in (("BATON_PACKET_DIR", packet_dir), ("BATON_RESULT_DIR", result_dir), ("BATON_WORKSPACE", workspace)):
        if value is not None:
            env[name] = str(value)
    return BuiltEnv(env, mode, denied, secret_names, resolved)
