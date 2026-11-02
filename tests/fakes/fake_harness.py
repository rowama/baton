"""A stand-in for the ``claude`` and ``codex`` CLIs, offline (tests only).

Installed by ``harnesskit.install_fake`` as an executable named ``claude`` or
``codex`` (behaviour follows the name). It models what Baton relies on:

* auth status: an API key variable in the environment wins (as it does for the
  real CLIs, which is why profiles deny it); otherwise ``HOME`` must be present
  (the stored login lives there), else "not logged in";
* permission modes: shell commands run only under ``--permission-mode
  bypassPermissions`` (claude) or a writable sandbox (codex);
* tasks: reads the packet named by ``BATON_PACKET_DIR`` and writes the result
  scripted in ``outputs.json`` next to the executable, keyed by step path
  (``output``, ``status``, ``touch`` (a file to change in the cwd),
  ``no_result``, ``stderr``, ``exit``).

Every call is appended to ``calls.jsonl`` next to the executable (argv, cwd and
environment variable *names*).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(sys.argv[0]).resolve().parent
NAME = Path(sys.argv[0]).name
ARGS = sys.argv[1:]


def opt(flag):
    return ARGS[ARGS.index(flag) + 1] if flag in ARGS else None


def log_call():
    with open(HERE / "calls.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": ARGS, "cwd": os.getcwd(), "env": sorted(os.environ)}) + "\n")


def auth():
    key = "ANTHROPIC_API_KEY" if NAME == "claude" else "OPENAI_API_KEY"
    if os.environ.get(key):
        return "api_key"
    return "login" if os.environ.get("HOME") else None


def main():
    log_call()
    if NAME == "claude" and ARGS[:2] == ["auth", "status"]:
        a = auth()
        method = {"api_key": "api_key", "login": "claude.ai", None: "none"}[a]
        print(json.dumps({"loggedIn": a is not None, "authMethod": method, "subscriptionType": "pro" if a == "login" else None}))
        return 0 if a else 1
    if NAME == "codex" and ARGS[:2] == ["login", "status"]:
        a = auth()
        print({"api_key": "Logged in using an API key - sk-***", "login": "Logged in using ChatGPT", None: "Not logged in"}[a])
        return 0 if a else 1

    if NAME == "claude":
        prompt = opt("-p")
        shell_ok = opt("--permission-mode") == "bypassPermissions"
    else:
        assert ARGS[0] == "exec", ARGS
        prompt = ARGS[-1]
        shell_ok = opt("--sandbox") in ("workspace-write", "danger-full-access")
    if auth() is None:
        print("Not logged in · Please run /login", file=sys.stderr)
        return 1

    if "Reply with the single word OK" in prompt:
        print("OK")
        return 0
    block = re.search(r"```\n(.*?)\n```", prompt, re.S)
    if block:  # gate preflight: run the command if this mode allows shell commands
        if not shell_ok:
            print("Permission to use Bash has been denied in this mode.")
            return 0
        subprocess.run(block.group(1), shell=True)
        print("DONE")
        return 0

    packet = Path(os.environ["BATON_PACKET_DIR"])
    result = Path(os.environ["BATON_RESULT_DIR"])
    assert str(packet) in prompt and "INSTRUCTIONS.md" in prompt, prompt
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    spec = json.loads((HERE / "outputs.json").read_text(encoding="utf-8"))[manifest["step_path"]]
    if spec.get("touch"):
        Path(spec["touch"]).write_text("changed by the worker\n", encoding="utf-8")
    if spec.get("stderr"):
        print(spec["stderr"], file=sys.stderr)
    if not spec.get("no_result"):
        result.mkdir(parents=True, exist_ok=True)
        envelope = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": spec.get("status", "completed"), "output": spec.get("output", {})}
        (result / "result.json").write_text(json.dumps(envelope), encoding="utf-8")
    print("finished")
    return spec.get("exit", 0)


sys.exit(main())
