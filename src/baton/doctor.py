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

The **effective auth mode** is what the worker would really use under its
exact environment: harness CLIs are asked (``claude auth status``, ``codex
login status``); a ``cli_login`` profile whose CLI would use an API key is a
problem (billing would switch), as is one that is not logged in.

**Gate preflight** (write-capable harness profiles, i.e. claiming
``repo_workspace``): ``project.preflight`` (or ``project.test_command``) runs
once directly and once through the worker under its own write-mode args, via
``baton.probe``; a command the worker cannot run, or whose exit differs, would
fail every script gate, so it is reported before a real run (§13.4).

**Async machinery** (§8.7): a supervisor can be started detached from this
process (a new session on POSIX), and every configured completion hook can
run here: ``hooks.yaml`` is valid, its ``secret:`` references resolve, and
each command's program is found on PATH. Hooks are never fired by doctor.

Platform incidents arrive with their layer (Phase 12).
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .models import Group, Step
from .packet import EngineError

NOOP_TIMEOUT_S = 120
AUTH_TIMEOUT_S = 60
PREFLIGHT_TIMEOUT_S = 600

#: How to log in again, per harness, for the "not logged in" fix.
LOGIN_HINTS = {"claude_code": "claude auth login", "codex": "codex login"}


def _run(argv: list[str], env: Any, cwd: Path, log_path: Path, timeout_s: float) -> Any:
    from .supervisor import run_child

    if env.resolved is not None:
        argv = [env.resolved.executable, *argv[1:]]
    return run_child(argv, env=env.env, cwd=cwd, log_path=log_path, timeout_s=timeout_s)


def _effective_auth(project: Any, name: str, profile: Any, adapter: Any, env: Any) -> dict[str, Any]:
    """What the worker would actually authenticate with, under its exact environment."""
    if profile.adapter == "manual":
        return {"mode": "none", "detail": "a person does this work"}
    if profile.adapter == "litellm_api":
        return {"mode": "api_key" if env.secrets else "none", "detail": "resolved " + ", ".join(env.secrets) if env.secrets else "no key"}
    status = getattr(adapter, "auth_status_command", None)
    argv = status(profile) if status else None
    if not argv:
        return {"mode": profile.auth.mode, "detail": "declared; this adapter cannot report it"}
    with tempfile.TemporaryDirectory(prefix="baton-doctor-") as tmp:
        child = _run(argv, env, Path(tmp), project.home / "logs" / "doctor" / f"{name}-auth.log", AUTH_TIMEOUT_S)
    text = child.log_path.read_text(encoding="utf-8", errors="replace")  # machine-local; only the parsed mode is reported
    if child.timed_out:
        return {"mode": "unknown", "detail": f"auth status did not answer within {AUTH_TIMEOUT_S} s"}
    return adapter.parse_auth_status(child.exit_code, text)


def _auth_problems(profile: Any, eff: dict[str, Any]) -> tuple[list[str], list[str]]:
    declared, actual = profile.auth.mode, eff.get("mode")
    if profile.adapter in ("manual", "command") or actual == declared:
        return [], []
    if actual == "unknown":
        return [], [f"cannot tell which auth the CLI would use ({eff.get('detail', '')})"]
    if actual == "none":
        hint = LOGIN_HINTS.get(profile.adapter)
        fix = f"; log in on this machine with `{hint}`" if hint and declared == "cli_login" else ""
        return [f"auth.mode is {declared} but the worker is not authenticated{fix}"], []
    if declared == "cli_login" and actual == "api_key":
        return [f"auth.mode is cli_login but the CLI would use an API key ({eff.get('detail', '')}): billing would switch to the API; add the key's variable to env_deny"], []
    return [f"auth.mode is {declared} but the CLI would use {actual} ({eff.get('detail', '')})"], []


def _gate_preflight(project: Any, name: str, profile: Any, adapter: Any, env: Any) -> dict[str, Any]:
    """Run ``project.preflight`` (or the test command) through the worker's own write-mode args (§13.4)."""
    import secrets
    import shlex
    import subprocess
    import sys

    from .intake import GATE_ENV_ALLOW

    cfg = project.config.project
    command = cfg.get("preflight") or cfg.get("test_command")
    if not command:
        return {"skipped": "project.yaml sets neither project.preflight nor project.test_command"}
    command = str(command)
    root = project.root
    # The runtime's own run, as a script gate would run it.
    gate_env = {k: os.environ[k] for k in GATE_ENV_ALLOW if k in os.environ}
    try:
        direct = subprocess.run(command, shell=True, cwd=root, env=gate_env, stdin=subprocess.DEVNULL, capture_output=True, timeout=PREFLIGHT_TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        direct = None
    nonce = secrets.token_hex(8)
    marker = project.baton / "cache" / "doctor" / f"preflight-{name}-{nonce}.json"  # gitignored, inside the workspace
    probe_argv = [sys.executable, "-m", "baton.probe", "--marker", marker.as_posix(), "--nonce", nonce, "--", command]
    if os.name == "nt":
        # Workers' shells on Windows vary (cmd, PowerShell, Git Bash): forward slashes
        # and double quotes only where needed read the same in all of them [VERIFY].
        probe = subprocess.list2cmdline([Path(sys.executable).as_posix(), *probe_argv[1:]])
    else:
        probe = shlex.join(probe_argv)
    # One line: on Windows, harness CLIs are often .cmd shims, and cmd.exe ends an argument at a newline.
    prompt = (
        "This is a Baton readiness check, not a task. Using your shell tool, run exactly the command between "
        f"the backticks, from {root.as_posix()}, then reply with the single word DONE. Do not change any files yourself. "
        f"`{probe}`"
    )
    args = adapter.mode_args(profile, "write")
    child = _run(adapter.task_command(profile, prompt, "write"), env, root, project.home / "logs" / "doctor" / f"{name}-preflight.log", PREFLIGHT_TIMEOUT_S)
    rep: dict[str, Any] = {"command": command, "args": args, "runtime_exit": direct, "duration_s": child.duration_s}
    seen = None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("nonce") == nonce:
            seen = data.get("exit_code")
        marker.unlink()
    except (OSError, ValueError):
        pass
    rep["worker_exit"] = seen
    if seen is None:
        rep["ok"] = False
        rep["problem"] = (
            f"gate preflight: `{command}` could not run under this profile's write-mode args {args}"
            + (" (the worker did not finish in time)" if child.timed_out else "")
            + "; script gates would fail. Change args.write so the worker may run shell commands"
        )
    elif seen != direct:
        rep["ok"] = False
        rep["problem"] = f"gate preflight: `{command}` exits {seen} under the worker's args {args} but {direct} when the runtime runs it; the sandbox or permission mode changes its outcome"
    else:
        rep["ok"] = True
        if seen != 0:
            rep["warning"] = f"gate preflight: `{command}` exits {seen} even outside the worker"
    return rep


def _profile_report(project: Any, name: str, profile: Any, run_noop: bool) -> dict[str, Any]:
    from . import adapters
    from .profiles import SetupError, build_env, effective_env_mode, executable_for

    rep: dict[str, Any] = {"adapter": profile.adapter, "vendor": profile.vendor, "auth_mode": profile.auth.mode, "env_mode": effective_env_mode(profile), "problems": [], "warnings": []}
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
                profile, home=project.home, config_home_var=getattr(adapter, "config_home_var", None), resolve=bool(executable_for(profile))
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
    eff = _effective_auth(project, name, profile, adapter, env)
    rep["auth_effective"] = eff
    probs, warns = _auth_problems(profile, eff)
    rep["problems"] += probs
    rep["warnings"] += warns
    if probs:
        rep["failure_class"] = "configuration" if eff.get("mode") == "api_key" else "platform"
        return rep  # a no-op or preflight would only fail the same way
    noop = getattr(adapter, "noop_command", None)
    if env is None or noop is None:
        rep["noop"] = {"skipped": "a person does this work" if profile.adapter == "manual" else "no no-op for this adapter"}
    elif not run_noop:
        rep["noop"] = {"skipped": "--no-run"}
    else:
        from .engine import classify_exit

        with tempfile.TemporaryDirectory(prefix="baton-doctor-") as tmp:
            child = _run(noop(profile), env, Path(tmp), project.home / "logs" / "doctor" / f"{name}.log", NOOP_TIMEOUT_S)
        rep["noop"] = {"ok": child.exit_code == 0 and not child.timed_out, "duration_s": child.duration_s, "log": str(child.log_path)}
        if child.timed_out:
            rep["problems"].append(f"no-op did not finish within {NOOP_TIMEOUT_S} s")
        elif child.exit_code != 0:
            cls = classify_exit(child, adapter.failure_signals)
            rep["failure_class"] = cls["class"]
            rep["problems"].append(f"no-op failed ({cls['class']}, {cls['code']}): {cls['message']}")
    # Gate preflight for write-capable harness profiles (§13.4).
    if "repo_workspace" in profile.capabilities and hasattr(adapter, "task_command") and not rep["problems"]:
        if not run_noop:
            rep["preflight"] = {"skipped": "--no-run"}
        else:
            pf = _gate_preflight(project, name, profile, adapter, env)
            rep["preflight"] = pf
            if pf.get("problem"):
                rep["problems"].append(pf["problem"])
                rep["failure_class"] = "configuration"
            if pf.get("warning"):
                rep["warnings"].append(pf["warning"])
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
        problems.append(f"baton.lock pins runtime {lock.get('runtime')}; this is {__version__} "
                        "(run Baton through the launcher, the `baton` command, or `baton upgrade` to pin this one)")
    problems += [i.message for i in _check_lock(project.baton, project.baton / "baton.lock", lock) if i.severity == "error"]
    return problems


def _supervisor_problems(project: Any) -> list[str]:
    """Can a supervisor detach from this process? (§8.7)"""
    import time

    from .supervisor import selftest_spawn

    with tempfile.TemporaryDirectory(prefix="baton-doctor-") as tmp:
        out = Path(tmp) / "selftest.json"
        try:
            proc = selftest_spawn(out)
        except OSError as e:
            return [f"cannot start a supervisor: {e}"]
        end = time.monotonic() + 30
        while time.monotonic() < end and proc.poll() is None:
            time.sleep(0.05)
        if not out.is_file():
            return ["a detached supervisor did not start (dispatches could not run in the background)"]
        info = json.loads(out.read_text(encoding="utf-8"))
        if os.name == "posix" and info.get("sid") == os.getsid(0):
            return ["a supervisor did not detach into its own session; it would end with the Director's shell"]
    return []


def _hook_problems(project: Any) -> list[str]:
    """Configured hooks can run here: valid config, secrets resolve, programs found (never fired)."""
    import shutil

    from .profiles import SetupError, split_command
    from .supervisor import HookConfigError, load_hooks, render_hook

    try:
        configured = load_hooks(project)
    except HookConfigError as e:
        return [f"hooks: {e}"]
    problems = []
    for source, hooks in configured:
        for name, command in hooks.items():
            where = f"{source} hook {name}"
            try:
                rendered, _ = render_hook(command, source, project.home)
            except SetupError as e:
                problems.append(f"{where}: {e}")
                continue
            try:
                words = split_command(rendered)
            except ValueError as e:
                problems.append(f"{where}: cannot parse the command: {e}")
                continue
            prog = next((w for w in words if "=" not in w.split("/")[0]), None)  # skip VAR=value prefixes
            if prog and not shutil.which(prog) and not Path(prog).is_file():
                problems.append(f"{where}: {prog!r} is not found on PATH")
    return problems


def doctor(project: Any, only: str | None = None, *, run_noop: bool = True) -> dict[str, Any]:
    from .routing import PreferencesError, load_preferences

    problems: list[str] = _lock_problems(project)
    warnings: list[str] = []
    if only is None:
        problems += _supervisor_problems(project) + _hook_problems(project)
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
        warnings += [f"{n}: {w}" for w in r.get("warnings", [])]
    healthy = {n: p for n, p in profiles.items() if not reports.get(n, {"problems": []})["problems"]}
    uncovered = _uncovered_steps(project, healthy) if only is None else []
    if only is None:
        from .sme import incidents

        for i in incidents(project.store.project_log().events()).values():
            if i["status"] == "open":
                warnings.append(f"open platform incident {i['id']}: {i.get('class')}/{i.get('code')} on {i.get('step_path')} of {i.get('run')}: {i.get('message')}")
    warnings += [f"no healthy profile on this machine can do {s}" for s in uncovered]
    if "microsoft" in platform.uname().release.lower() and str(project.root).startswith("/mnt/") and os.name == "posix":
        warnings.append(f"{project.root} is on a Windows drive under WSL; keep repos on the Linux filesystem for speed (§15.1)")
    ok = not problems
    line = f"doctor: {len(reports)} profile(s) ready" if ok else f"doctor: {len(problems)} problem(s)"
    return {"ok": ok, "line": line, "problems": problems, "warnings": warnings, "profiles": reports, "uncovered_steps": uncovered}
