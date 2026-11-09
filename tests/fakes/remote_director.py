"""One session of a scripted remote Director that only has a shell on the runtime host (Phase 16).

    python remote_director.py <wake.json> <outbox.jsonl> <sessions.jsonl>

It keeps no memory between sessions: everything it knows comes from the wake
that started it (a completion hook's variables, or the owner's reply) and from
``baton … --json``. It follows the director skill: relay the owner's words,
route from ``eligible`` in preference order, dispatch without waiting and end
the turn (telling the owner ``wake.notice`` first when no hook would wake it),
tell the owner where a person's packet is and ``submit`` when they say they
are done. Messages for the owner go to the outbox; every command it
ran goes to the sessions log.
"""

import json
import os
import subprocess
import sys
import uuid

wake_file, outbox, sessions = sys.argv[1:4]
wake = json.loads(open(wake_file, encoding="utf-8").read())
commands: list[list[str]] = []


def baton(*args: str) -> tuple[int, dict]:
    commands.append(list(args))
    proc = subprocess.run([sys.executable, "-m", "baton", *args, "--json"], capture_output=True, text=True, timeout=300)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except ValueError:
        payload = {"raw": proc.stdout + proc.stderr}
    return proc.returncode, payload


def tell(**message: object) -> None:
    with open(outbox, "a", encoding="utf-8") as f:
        f.write(json.dumps(message) + "\n")


baton("detect")
runs: list[str] = []
owner = wake.get("owner") or {}
if owner.get("kind") == "start":
    code, out = baton("start", owner["recipe"], "--inputs", json.dumps(owner["inputs"]))
    runs.append(out["run_id"])
elif owner.get("kind") == "decision":  # the owner's words, verbatim
    baton("decide", owner["run"], owner["ref"], owner["decision"], "--note", owner["note"])
    runs.append(owner["run"])
elif owner.get("kind") == "submitted":  # the person wrote their result; hand it in
    baton("submit", owner["run"], owner["step"])
    runs.append(owner["run"])
hook_run = (wake.get("hook") or {}).get("BATON_RUN_ID")
if hook_run:
    runs.append(hook_run)
code, board = baton("board")
runs += [r["run_id"] for r in board.get("runs", [])]

for run in dict.fromkeys(runs):
    for _ in range(10):
        code, st = baton("status", run)
        if st.get("state") == "completed":
            code, summary = baton("summary", run)
            tell(kind="done", run=run)
            break
        if st.get("running") or st.get("queued"):
            break  # a hook will wake us
        if st.get("pending_decisions"):
            for p in st["pending_decisions"]:
                tell(kind="question", run=run, ref=p["ref"], attempt=p.get("attempt"), prompt=p.get("prompt"), options=p.get("options"))
            break
        if not st.get("ready"):
            break
        step = st["ready"][0]
        code, el = baton("eligible", run, step)
        worker = el["eligible"][0]["profile"]
        if not el.get("wake", {}).get("configured", True) and el["wake"].get("notice"):
            tell(kind="notice", run=run, step=step, text=el["wake"]["notice"])  # no wake path: the owner hears first
        code, d = baton("dispatch", run, step, "--worker", worker)
        if d.get("adapter") == "manual":  # a person: tell them where the packet is; never do it for them
            tell(kind="manual", run=run, step=step, packet=d["packet"], attempt=d.get("attempt"))
        break  # dispatched: end the turn

with open(sessions, "a", encoding="utf-8") as f:
    # A fresh id per session: Windows reuses a finished process's pid at once, so pids can repeat across sessions.
    f.write(json.dumps({"session": uuid.uuid4().hex, "pid": os.getpid(), "wake": wake, "commands": commands}) + "\n")
