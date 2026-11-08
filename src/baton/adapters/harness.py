"""Headless coding-agent adapters (§6.3): ``subprocess_harness`` and its presets.

A harness worker is a CLI agent started as a child process under the
profile's constructed environment (``allowlist`` by default for
``cli_login``, so the CLI finds its stored subscription login under ``HOME``
and nothing else). It is told to read ``INSTRUCTIONS.md`` and write its
result itself; intake then checks it like any other result.

**Working directory.** The attempt directory for ``workspace: none`` steps;
the project root for ``read`` and ``write`` steps (§6.3). The attempt's
``result/`` lies inside the project, so every mode must allow writes there.

**Modes.** Each preset has built-in args per workspace mode, verified against
the installed CLIs' ``--help``; a profile's ``args.write`` / ``args.read`` /
``args.none`` replaces the default for that mode. CLI flags cannot confine an
agent's writes to ``result/``, so ``read`` and ``none`` steps are enforced by
the runtime: the working tree is compared before and after (``engine``), and
any change escalates the step.

Presets (flags checked against ``claude`` 2.1.319 and ``codex-cli`` 0.166.0):

* ``claude_code``: ``claude -p <prompt> --permission-mode <mode> <tool args>
  --output-format stream-json --verbose``; config home ``CLAUDE_CONFIG_DIR``;
  auth from ``claude auth status --json``.
* ``codex``: ``codex <tool args before exec> exec --sandbox <mode> <tool args>
  --json --skip-git-repo-check <prompt>``; config home ``CODEX_HOME``; auth
  from ``codex login status``.

**Tools** (0085). The tool args come from the provider's tool map in the
known-workers data (``ToolPlan``): a step gets the args for the tooling
capabilities it requires, and the off args for the others. The adapter only
places them. A dispatch's output is the CLI's event stream, saved as the
attempt's log; ``tool_evidence`` reads tool use from it, intake never does.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import WorkerProfile
from ..profiles import SetupError, executable_for, split_command

MODES = ("none", "read", "write")

TASK_PROMPT = (
    "Read {packet}/INSTRUCTIONS.md and follow it exactly; write outputs to {result}/ "
    "(artifacts under {result}/artifacts/, then {result}/result.json last). "
    "Do not modify anything under {packet}/."
)
NOOP_PROMPT = "Reply with the single word OK. Do not use any tools."


@dataclass
class ToolPlan:
    """The tool args one dispatch gets (0085): ``on`` for the step's required tooling, ``off`` for the rest."""

    on: dict[str, Any] = field(default_factory=dict)   # capability -> known_workers.ToolArgs
    off: dict[str, Any] = field(default_factory=dict)

    def split(self) -> tuple[list[str], list[str]]:
        """``(before_subcommand, with_args)``."""
        before: list[str] = []
        with_args: list[str] = []
        for t in self.on.values():
            (before if t.position == "before_subcommand" else with_args).extend(t.args)
        for t in self.off.values():
            if t.off_args:
                (before if t.off_position == "before_subcommand" else with_args).extend(t.off_args)
        return before, with_args

    def describe(self) -> dict[str, Any]:
        before, with_args = self.split()
        return {"on": sorted(self.on), "off": sorted(c for c, t in self.off.items() if t.off_args), "args": before + with_args}


def plan_tools(tool_map: dict[str, Any], needed: list[str], claimed: list[str]) -> ToolPlan:
    """Turn on the mapped tools the step needs and the profile claims; turn off the others that can be (least privilege)."""
    on = {c: t for c, t in tool_map.items() if c in needed and c in claimed}
    off = {c: t for c, t in tool_map.items() if c not in on}
    return ToolPlan(on, off)


VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")


def mode_args(profile: WorkerProfile, mode: str, defaults: dict[str, list[str]]) -> list[str]:
    """The profile's args for ``mode`` (``args.<mode>``), else the adapter's default."""
    if mode not in MODES:
        raise ValueError(f"unknown workspace mode {mode!r}")
    own = getattr(profile.args, mode, None) if profile.args else None
    return list(own) if own is not None else list(defaults.get(mode, []))


class SubprocessHarnessAdapter:
    """Shared behaviour of the presets; subclasses set the CLI specifics."""

    name = "subprocess_harness"
    needs_executable = True
    #: Workers that run tools in the tree: read/none steps get the runtime's tree check.
    touches_files = True
    config_home_var: str | None = None
    default_args: dict[str, list[str]] = {}
    failure_signals: list[dict[str, Any]] = []
    #: Args that make a dispatch's output the CLI's machine-readable event stream (0085).
    stream_args: list[str] = []
    #: Reads a tool map from the known-workers data (0085).
    uses_tool_map = True

    # -- CLI specifics ------------------------------------------------------

    def argv(self, exe: str, prompt: str, args: list[str], profile: WorkerProfile, before: list[str] | None = None) -> list[str]:  # pragma: no cover - abstract
        raise NotImplementedError

    def version_argv(self, exe: str) -> list[str]:
        return [exe, "--version"]

    @staticmethod
    def parse_version(text: str) -> str | None:
        m = VERSION.search(text or "")
        return m.group(0) if m else None

    def auth_status_argv(self, exe: str) -> list[str] | None:
        return None

    def parse_auth_status(self, exit_code: int | None, text: str) -> dict[str, Any]:
        return {"mode": "unknown"}

    # -- protocol -----------------------------------------------------------

    def check_profile(self, profile: WorkerProfile) -> None:
        if profile.auth.mode == "none":
            raise SetupError(
                "configuration.harness_auth",
                f"a {self.name} profile needs auth.mode cli_login (the CLI's stored login) or api_key",
                "configuration",
            )

    def preflight(self, profile: WorkerProfile, packet_dir: Path) -> list[str]:
        return []

    def mode_args(self, profile: WorkerProfile, mode: str) -> list[str]:
        return mode_args(profile, mode, self.default_args)

    def task_command(self, profile: WorkerProfile, prompt: str, mode: str) -> list[str]:
        """Any prompt through this CLI under ``mode``'s args (used by dispatch, doctor no-ops and preflight)."""
        self.check_profile(profile)
        exe = executable_for(profile)
        assert exe
        return self.argv(exe, prompt, self.mode_args(profile, mode), profile)

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str,
                tools: ToolPlan | None = None) -> list[str] | None:
        """A dispatch: the task prompt, the mode's args, the tool plan's args and the event-stream args."""
        self.check_profile(profile)
        exe = executable_for(profile)
        assert exe
        before, with_args = (tools or ToolPlan()).split()
        prompt = TASK_PROMPT.format(packet=packet_dir.as_posix(), result=result_dir.as_posix())
        return self.argv(exe, prompt, [*self.mode_args(profile, mode), *with_args, *self.stream_args], profile, before)

    def noop_command(self, profile: WorkerProfile) -> list[str]:
        return self.task_command(profile, NOOP_PROMPT, "none")

    def auth_status_command(self, profile: WorkerProfile) -> list[str] | None:
        exe = executable_for(profile)
        return self.auth_status_argv(exe) if exe else None

    def postprocess(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, proc_result: Any) -> None:
        return None

    def handoff(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path) -> str:
        return f"Headless {executable_for(profile)} ({self.name}); the runtime runs it and takes in the result."


class ClaudeCodeAdapter(SubprocessHarnessAdapter):
    name = "claude_code"
    config_home_var = "CLAUDE_CONFIG_DIR"
    default_args = {
        "write": ["--permission-mode", "bypassPermissions"],
        "read": ["--permission-mode", "acceptEdits"],
        "none": ["--permission-mode", "acceptEdits"],
    }
    failure_signals = [
        {"pattern": r"(?i)not logged in|please run /login|invalid api key|authentication_error|oauth token has expired", "class": "platform", "code": "auth_failed"},
        {"pattern": r"(?i)ENOTFOUND|ECONNREFUSED|ETIMEDOUT|network error", "class": "platform", "code": "network"},
        {"pattern": r"(?i)error: unknown option|unknown option '--", "class": "platform", "code": "harness_flag_rejected"},
    ]
    stream_args = ["--output-format", "stream-json", "--verbose"]

    def argv(self, exe: str, prompt: str, args: list[str], profile: WorkerProfile, before: list[str] | None = None) -> list[str]:
        out = [exe, *(before or []), "-p", prompt, *args]
        if profile.model:
            out += ["--model", profile.model]
        return out

    def auth_status_argv(self, exe: str) -> list[str]:
        return [exe, "auth", "status", "--json"]

    def parse_auth_status(self, exit_code: int | None, text: str) -> dict[str, Any]:
        try:
            data = json.loads(text[text.index("{") : text.rindex("}") + 1])
        except ValueError:
            return {"mode": "unknown", "detail": text.strip()[-200:]}
        method = str(data.get("authMethod") or "")
        if not data.get("loggedIn"):
            mode = "none"
        elif "key" in method.lower() or method.lower() == "api":
            mode = "api_key"
        else:
            mode = "cli_login"
        out: dict[str, Any] = {"mode": mode, "detail": method or "not logged in"}
        if data.get("subscriptionType"):
            out["subscription"] = data["subscriptionType"]
        return out


class CodexAdapter(SubprocessHarnessAdapter):
    name = "codex"
    config_home_var = "CODEX_HOME"
    default_args = {
        "write": ["--sandbox", "workspace-write"],
        "read": ["--sandbox", "workspace-write"],
        "none": ["--sandbox", "workspace-write"],
    }
    failure_signals = [
        {"pattern": r"(?i)not logged in|401 unauthorized|invalid api key|please log ?in", "class": "platform", "code": "auth_failed"},
        {"pattern": r"(?i)stream disconnected|error sending request|dns error", "class": "platform", "code": "network"},
        {"pattern": r"(?i)error: unexpected argument '--|unrecognized option", "class": "platform", "code": "harness_flag_rejected"},
    ]
    stream_args = ["--json"]

    def argv(self, exe: str, prompt: str, args: list[str], profile: WorkerProfile, before: list[str] | None = None) -> list[str]:
        out = [exe, *(before or []), "exec", *args, "--skip-git-repo-check", "--color", "never"]
        if profile.model:
            out += ["--model", profile.model]
        return out + [prompt]

    def auth_status_argv(self, exe: str) -> list[str]:
        return [exe, "login", "status"]

    def parse_auth_status(self, exit_code: int | None, text: str) -> dict[str, Any]:
        line = next((ln.strip() for ln in text.splitlines() if "log" in ln.lower()), text.strip())
        low = line.lower()
        if "not logged in" in low or (exit_code not in (0, None) and "logged in" not in low):
            mode = "none"
        elif "api key" in low:
            mode = "api_key"
        elif "logged in" in low:
            mode = "cli_login"
        else:
            mode = "unknown"
        return {"mode": mode, "detail": line[:200]}


class CommandAdapter:
    """``command`` (§6.3): a configured command line for other tools, or for relaying to another agent.

    ``command`` is split like a POSIX shell would (no shell runs it) and each
    word's placeholders are substituted: ``{prompt_file}`` (the packet's
    ``INSTRUCTIONS.md``), ``{packet}``, ``{result}``, ``{workspace}`` (empty for
    ``workspace: none`` steps). The first word is the executable, resolved like
    any other (§6.2) unless ``executable`` is set.
    """

    name = "command"
    needs_executable = True
    touches_files = True
    config_home_var: str | None = None
    failure_signals: list[dict[str, Any]] = []

    def check_profile(self, profile: WorkerProfile) -> None:
        if not profile.command or not split_command(profile.command):
            raise SetupError("configuration.no_command", "a command profile needs `command` (e.g. \"mytool --in {packet} --out {result}\")", "configuration")

    def preflight(self, profile: WorkerProfile, packet_dir: Path) -> list[str]:
        return []

    def command(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, workspace: Path | None, mode: str) -> list[str] | None:
        self.check_profile(profile)
        values = {
            "{prompt_file}": (packet_dir / "INSTRUCTIONS.md").as_posix(),
            "{packet}": packet_dir.as_posix(),
            "{result}": result_dir.as_posix(),
            "{workspace}": workspace.as_posix() if workspace else "",
        }
        words = split_command(str(profile.command))
        out = []
        for w in words:
            for k, v in values.items():
                w = w.replace(k, v)
            out.append(w)
        if profile.executable:
            out[0] = profile.executable
        return out

    def postprocess(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path, proc_result: Any) -> None:
        return None

    def handoff(self, profile: WorkerProfile, packet_dir: Path, result_dir: Path) -> str:
        return f"Command worker `{split_command(str(profile.command))[0]}`; the runtime runs it and takes in the result."
