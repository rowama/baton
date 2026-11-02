"""``baton doctor``: is this machine ready to run this project's work? (§13.4)

Silent when healthy: the CLI prints one line unless something needs fixing.
Per machine:

* the lockfile against the running runtime (version, formats, vocabularies)
  and every vendored recipe's hash;
* worker profiles load and validate; ``preferences.yaml`` is valid;
* steps of vendored recipes that no profile on this machine can do;
* WSL: a repo on a Windows drive (``/mnt/<x>/``) is slow; a warning.

Per profile: the adapter exists in this runtime; the exact environment builds
(secrets resolve, the executable resolves, §6.2), reported as variable *names*
present and denied, never values; the effective auth mode; and a no-op round
trip through the adapter (``litellm_api``: a tiny model call; ``manual``: none,
a person does the work), with its duration and, on failure, its class.

Gate preflight, supervisor detachment, hooks and platform incidents arrive with
their layers (Phases 6, 7 and 12).
"""

from __future__ import annotations

import os
import platform
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .models import Group, Step
from .packet import EngineError

NOOP_TIMEOUT_S = 120


def _profile_report(project: Any, name: str, profile: Any, run_noop: bool) -> dict[str, Any]:
    from . import adapters
    from .profiles import SetupError, build_env, effective_env_mode
    from .supervisor import run_child

    rep: dict[str, Any] = {"adapter": profile.adapter, "vendor": profile.vendor, "auth_mode": profile.auth.mode, "env_mode": effective_env_mode(profile), "problems": []}
    adapter = adapters.ADAPTERS.get(profile.adapter)
    if adapter is None:
        rep["problems"].append(f"adapter {profile.adapter!r} is not available in this runtime (available: {', '.join(sorted(adapters.ADAPTERS))})")
    if profile.isolation != "none":
        rep["problems"].append(f"isolation {profile.isolation!r} is not supported by this runtime yet")
    try:
        if adapter is not None:
            adapter.check_profile(profile)
        if profile.adapter != "manual":
            env = build_env(
                profile, home=project.home, config_home_var=getattr(adapter, "config_home_var", None), resolve=bool(profile.executable)
            )
            rep["env"] = env.describe()
        else:
            env = None
    except SetupError as e:
        rep["problems"].append(str(e))
        rep["failure_class"] = e.failure_class
        if "searched" in e.detail:
            rep["searched"] = e.detail["searched"]
        return rep
    if adapter is None:
        return rep
    noop = getattr(adapter, "noop_command", None)
    if env is None or noop is None:
        rep["noop"] = {"skipped": "a person does this work" if profile.adapter == "manual" else "no no-op for this adapter"}
        return rep
    if not run_noop:
        rep["noop"] = {"skipped": "--no-run"}
        return rep
    from .engine import classify_exit

    with tempfile.TemporaryDirectory(prefix="baton-doctor-") as tmp:
        log_path = project.home / "logs" / "doctor" / f"{name}.log"
        child = run_child(noop(profile), env=env.env, cwd=Path(tmp), log_path=log_path, timeout_s=NOOP_TIMEOUT_S)
    rep["noop"] = {"ok": child.exit_code == 0 and not child.timed_out, "duration_s": child.duration_s, "log": str(log_path)}
    if child.timed_out:
        rep["problems"].append(f"no-op did not finish within {NOOP_TIMEOUT_S} s")
    elif child.exit_code != 0:
        cls = classify_exit(child)
        rep["failure_class"] = cls["class"]
        rep["problems"].append(f"no-op failed ({cls['class']}, {cls['code']}): {cls['message']}")
    return rep


def _uncovered_steps(project: Any, profiles: dict[str, Any]) -> list[str]:
    from .routing import requirement_gaps

    out = []
    for ref in project.vendored():
        try:
            loaded = project.recipe(ref)
        except EngineError:
            continue

        def visit(nodes: list, prefix: str) -> None:
            for n in nodes:
                if isinstance(n, Group):
                    visit(n.steps, f"{prefix}{n.id}/")
                elif isinstance(n, Step):
                    if not any(not requirement_gaps(n.requires, n.workspace, p, loaded.vocab) for p in profiles.values()):
                        out.append(f"{ref}/{prefix}{n.id}")

        visit(loaded.recipe.steps, "")
    return out


def _lock_problems(project: Any) -> list[str]:
    from .check import _check_lock

    problems = []
    try:
        lock = project.lock()
    except EngineError as e:
        return [str(e)]
    if lock.get("runtime") != __version__:
        problems.append(f"baton.lock pins runtime {lock.get('runtime')}; this is {__version__}")
    problems += [i.message for i in _check_lock(project.baton, project.baton / "baton.lock", lock) if i.severity == "error"]
    return problems


def doctor(project: Any, only: str | None = None, *, run_noop: bool = True) -> dict[str, Any]:
    from .routing import PreferencesError, load_preferences

    problems: list[str] = _lock_problems(project)
    warnings: list[str] = []
    try:
        profiles = project.profiles()
    except EngineError as e:
        return {"ok": False, "problems": problems + [str(e)], "warnings": warnings, "profiles": {}, "uncovered_steps": []}
    try:
        load_preferences(project.baton)
    except PreferencesError as e:
        problems.append(str(e))
    if only is not None and only not in profiles:
        raise EngineError("configuration.unknown_profile", f"no worker profile {only!r} on this machine (known: {', '.join(sorted(profiles)) or 'none'})")
    reports = {n: _profile_report(project, n, p, run_noop) for n, p in sorted(profiles.items()) if only in (None, n)}
    for n, r in reports.items():
        problems += [f"{n}: {p}" for p in r["problems"]]
    healthy = {n: p for n, p in profiles.items() if not reports.get(n, {"problems": []})["problems"]}
    uncovered = _uncovered_steps(project, healthy) if only is None else []
    warnings += [f"no healthy profile on this machine can do {s}" for s in uncovered]
    if "microsoft" in platform.uname().release.lower() and str(project.root).startswith("/mnt/") and os.name == "posix":
        warnings.append(f"{project.root} is on a Windows drive under WSL; keep repos on the Linux filesystem for speed (§15.1)")
    ok = not problems
    line = f"doctor: {len(reports)} profile(s) ready" if ok else f"doctor: {len(problems)} problem(s)"
    return {"ok": ok, "line": line, "problems": problems, "warnings": warnings, "profiles": reports, "uncovered_steps": uncovered}
