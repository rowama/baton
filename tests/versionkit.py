"""Helpers for versioning tests: installed runtime versions, synthetic format versions, the launcher as a process."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

from baton import launcher, versions

from conftest import ROOT

DATA_DIRS = ("vocab", "formats", "defaults", "classify", "builtin", "skills")


def fake_install(home: Path, version: str) -> Path:
    """Install this source tree as runtime ``version`` into ``$BATON_HOME/versions/<version>/``.

    A real virtual environment holding its own copy of the package (with ``__version__``
    changed and the shipped data under ``_data``, as in a wheel); dependencies come from the
    test interpreter's site-packages through a ``.pth`` line. The package copy comes first.
    """
    vdir = launcher.version_dir(home, version)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(vdir)], check=True, capture_output=True)
    py = launcher.python_in(vdir)
    purelib = Path(subprocess.run([str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                                  check=True, capture_output=True, text=True).stdout.strip())
    pkg = purelib / "baton"
    shutil.copytree(ROOT / "src" / "baton", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    for name in DATA_DIRS:
        shutil.copytree(ROOT / name, pkg / "_data" / name)
    init = pkg / "__init__.py"
    init.write_text(init.read_text(encoding="utf-8").replace('__version__ = "0.1.0"', f'__version__ = "{version}"'), encoding="utf-8")
    parents = dict.fromkeys([sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"]])
    (purelib / "_baton_test_deps.pth").write_text("".join(f"{p}\n" for p in parents), encoding="utf-8")
    (vdir / launcher.INSTALLED_MARKER).write_text("{}\n", encoding="utf-8")
    return vdir


def launcher_env(home: Path, director: str = "alice@host1", **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BATON_") and k != "PYTHONPATH"}
    env.update(BATON_HOME=str(home), BATON_DIRECTOR=director, **extra)
    return env


def baton(cwd: Path, env: dict[str, str], *args: str, expect: int | None = 0, as_json: bool = True) -> Any:
    """Run the ``baton`` command (the launcher) in ``cwd``, the way an owner or Director would."""
    proc = subprocess.run([sys.executable, "-m", "baton", *args, *(["--json"] if as_json else [])], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=300)
    if expect is not None:
        assert proc.returncode == expect, f"baton {' '.join(args)} exited {proc.returncode} (wanted {expect}):\n{proc.stdout}\n{proc.stderr}"
    if not as_json:
        return proc
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def synthetic(monkeypatch: Any, **currents: int) -> None:
    """Pretend this runtime's current version of each named family is ``n`` (identity upcasters)."""
    fams = dict(versions.FAMILIES)
    for name, cur in currents.items():
        f = versions.FAMILIES[name]
        fams[name] = versions.Family(f.name, f.prefix, cur, f.what, {n: (lambda o: dict(o)) for n in range(1, cur)})
    monkeypatch.setattr(versions, "FAMILIES", fams)
