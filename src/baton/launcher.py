"""The launcher: the ``baton`` command runs the runtime version the project pins (§14.1).

The installed ``baton`` command is this package. Before anything else it reads
``.baton/baton.lock`` of the project it is pointed at (``--project``,
``BATON_PROJECT`` or the nearest directory holding ``.baton/project.yaml``) and,
when the pinned ``runtime`` is not this version, re-runs the same command line
under that version from ``$BATON_HOME/versions/<version>/`` (its own Python,
``-m baton``), installing it there first when it is missing. When the versions
match (the healthy case) nothing happens and the command runs in-process.

Which version runs:

* ``BATON_VERSION`` set: that version, for this one invocation;
* ``upgrade --to <v>``: ``<v>`` (the new runtime does its own upgrade, so it
  vendors its own skills); ``upgrade`` without ``--to``: this version;
* ``init``, or no project found: this version;
* otherwise: ``runtime`` in the project's ``baton.lock``.

**Installing** (owner decision, 2026-11-03, §18 #15): with uv (checked against uv 0.13.7):
``uv venv <dir>`` then ``uv pip install --python <dir's python> "baton[<extras>] @ <source>"``.
``$BATON_HOME/launcher.yaml`` (machine-local, optional) sets ``source`` (a URL
template with ``{version}``; default ``git+https://github.com/rowama/baton@v{version}``),
``extras`` (default ``[api, keyring]``, 0116, 0123; e.g. ``[mcp, api]``) and ``python`` (an interpreter for ``uv venv``).
``BATON_UV`` names the uv executable. Without uv the launcher refuses, naming
the install command and the directory a version may also be installed into by hand.
A version directory counts as installed once it holds ``.baton-installed``.

The re-run process gets ``BATON_LAUNCHED=<version>``; it checks that it really
is that version (refusing otherwise, so a broken install cannot loop) and
removes the variable, so commands it starts (hooks, gates) launch afresh.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__

LAUNCHED = "BATON_LAUNCHED"
DEFAULT_SOURCE = "git+https://github.com/rowama/baton@v{version}"
DEFAULT_EXTRAS = ("api", "keyring")  # so a pinned runtime can always run API routes (0116) and keep a key the owner pastes (0123); launcher.yaml `extras` replaces it, even with []
INSTALLED_MARKER = ".baton-installed"
_ROOT_OPTIONS_WITH_VALUES = ("--project", "--director")


class LauncherError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def home(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("BATON_HOME") or Path.home() / ".baton")


def version_dir(baton_home: Path, version: str) -> Path:
    return baton_home / "versions" / version


def python_in(vdir: Path) -> Path:
    return vdir / "Scripts" / "python.exe" if os.name == "nt" else vdir / "bin" / "python"


def installed(vdir: Path) -> bool:
    return (vdir / INSTALLED_MARKER).is_file() and python_in(vdir).exists()


# ---------------------------------------------------------------------------
# Which version
# ---------------------------------------------------------------------------


def parse_argv(argv: Sequence[str]) -> dict[str, Any]:
    """The root options, the command and ``upgrade --to`` from a ``baton`` command line."""
    out: dict[str, Any] = {"project": None, "command": None, "to": None}
    it = iter(range(len(argv)))
    rest: list[str] = []
    for i in it:
        tok = argv[i]
        if out["command"] is None:
            name, eq, val = tok.partition("=")
            if name in _ROOT_OPTIONS_WITH_VALUES:
                if not eq:
                    val = argv[i + 1] if i + 1 < len(argv) else ""
                    next(it, None)
                if name == "--project":
                    out["project"] = val
                continue
            if not tok.startswith("-"):
                out["command"] = tok
            continue
        rest.append(tok)
    for i, tok in enumerate(rest):
        if tok == "--to" and i + 1 < len(rest):
            out["to"] = rest[i + 1]
        elif tok.startswith("--to="):
            out["to"] = tok.split("=", 1)[1]
    return out


def find_project(start: Path) -> Path | None:
    here = start.resolve()
    for d in (here, *here.parents):
        if (d / ".baton" / "project.yaml").is_file():
            return d
    return None


def pinned(root: Path) -> str | None:
    """The runtime version ``baton.lock`` pins, or None (missing or unreadable: the runtime reports it)."""
    try:
        lock = json.loads((root / ".baton" / "baton.lock").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):  # expected: missing or unreadable: the runtime reports it
        return None
    v = lock.get("runtime") if isinstance(lock, dict) else None
    return v if isinstance(v, str) and v else None


def wanted_version(argv: Sequence[str], env: dict[str, str], cwd: Path) -> str:
    if env.get("BATON_VERSION"):
        return env["BATON_VERSION"]
    args = parse_argv(argv)
    if args["command"] == "upgrade":
        return args["to"] or __version__
    if args["command"] == "init":
        return __version__
    project = args["project"] or env.get("BATON_PROJECT")
    root = Path(project) if project else find_project(cwd)
    return (pinned(root) if root else None) or __version__


# ---------------------------------------------------------------------------
# Installing
# ---------------------------------------------------------------------------


def config(baton_home: Path) -> dict[str, Any]:
    p = baton_home / "launcher.yaml"
    if not p.is_file():
        return {}
    from .data import YamlError, load_yaml

    try:
        doc = load_yaml(p)
    except YamlError as e:
        raise LauncherError("launcher.config", f"{p} is not valid YAML: {e}") from e
    if doc is None:
        return {}
    if not isinstance(doc, dict) or set(doc) - {"source", "extras", "python"}:
        raise LauncherError("launcher.config", f"{p} may set only source, extras and python")
    return doc


def requirement(cfg: dict[str, Any], version: str) -> str:
    source = str(cfg.get("source") or DEFAULT_SOURCE)
    extras = cfg["extras"] if "extras" in cfg else list(DEFAULT_EXTRAS)  # an explicit list, even empty, is the owner's (0116)
    if extras is None:
        extras = []
    if not isinstance(extras, list) or not all(isinstance(x, str) for x in extras):
        raise LauncherError("launcher.config", "launcher.yaml extras must be a list of names")
    return f"baton{'[' + ','.join(extras) + ']' if extras else ''} @ {source.format(version=version)}"


def install(version: str, baton_home: Path, env: dict[str, str] | None = None) -> Path:
    """Install runtime ``version`` into ``$BATON_HOME/versions/<version>/`` with uv; returns its directory."""
    from .locks import file_lock

    env = dict(os.environ if env is None else env)
    vdir = version_dir(baton_home, version)
    cfg = config(baton_home)
    uv = env.get("BATON_UV") or shutil.which("uv")
    if not uv:
        raise LauncherError(
            "launcher.no_uv",
            f"baton.lock pins Baton {version}, which is not installed, and uv is not available to install it. "
            f"Install uv (https://docs.astral.sh/uv/), or install Baton {version} yourself into {vdir} "
            f"(a virtual environment; then create {vdir / INSTALLED_MARKER})",
        )
    req = requirement(cfg, version)
    vdir.parent.mkdir(parents=True, exist_ok=True)
    env.pop(LAUNCHED, None)
    with file_lock(vdir.parent / f".install-{version}.lock"):
        if installed(vdir):
            return vdir
        if vdir.exists():
            shutil.rmtree(vdir)  # an interrupted install
        print(f"baton: installing Baton {version} into {vdir} ({req})", file=sys.stderr)
        steps = [
            [uv, "venv", "--quiet", *(["--python", str(cfg["python"])] if cfg.get("python") else []), str(vdir)],
            [uv, "pip", "install", "--quiet", "--python", str(python_in(vdir)), req],
        ]
        for cmd in steps:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if proc.returncode != 0:
                shutil.rmtree(vdir, ignore_errors=True)
                tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
                raise LauncherError("launcher.install_failed", f"installing Baton {version} failed: `{' '.join(cmd)}` exited {proc.returncode}: " + " | ".join(tail))
        got = _reported_version(vdir, env)
        if got != version:
            shutil.rmtree(vdir, ignore_errors=True)
            raise LauncherError("launcher.install_failed", f"installing Baton {version} from {req} produced version {got!r}")
        (vdir / INSTALLED_MARKER).write_text(json.dumps({"version": version, "requirement": req}) + "\n", encoding="utf-8")
    return vdir


def _reported_version(vdir: Path, env: dict[str, str]) -> str | None:
    proc = subprocess.run([str(python_in(vdir)), "-c", "import baton; print(baton.__version__)"], env=env, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _refuse(argv: Sequence[str], e: LauncherError) -> None:
    if "--json" in argv:
        print(json.dumps({"ok": False, "error": e.code, "message": str(e)}, indent=2))
    print(f"ERROR: {e}", file=sys.stderr)
    raise SystemExit(1)


def relaunch_if_needed(argv: Sequence[str] | None = None) -> None:
    """Return to run in-process, or replace this process with the pinned runtime version."""
    argv = list(sys.argv[1:] if argv is None else argv)
    launched = os.environ.pop(LAUNCHED, None)
    if launched is not None:
        if launched != __version__:
            _refuse(argv, LauncherError("launcher.version_mismatch", f"the launcher started Baton {launched}, but this runtime is {__version__}; "
                                        f"reinstall it (remove {version_dir(home(), launched)})"))
        return
    try:
        want = wanted_version(argv, dict(os.environ), Path.cwd())
        if want == __version__:
            return
        vdir = version_dir(home(), want)
        if not installed(vdir):
            install(want, home())
    except LauncherError as e:
        _refuse(argv, e)
        return
    python = str(python_in(vdir))
    cmd = [python, "-m", "baton", *argv]
    env = {**os.environ, LAUNCHED: want}
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        raise SystemExit(subprocess.call(cmd, env=env))
    os.execve(python, cmd, env)  # pragma: no cover - replaces the process


def main() -> None:
    relaunch_if_needed()
    from .cli import app

    app()
