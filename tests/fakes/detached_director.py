"""A scripted detached Director's one turn: frame a goal, dispatch the framing step with --wait (change 2026-11-director-wake).

    python detached_director.py <words> <transcript.jsonl>

The bug eval's case (2026-11-04-director-wake-on-needs-human): a chat agent
with only a shell runs ``dispatch … --wait --json`` as a background job and
ends its turn. It follows the director skill's wake-path rules: before
dispatching it reads ``eligible``'s ``wake``, and with no wake path it tells
the owner ``wake.notice`` first; exit 4 (or ``needs_owner``) from
``dispatch --wait`` means the work finished and the owner is needed now.

The transcript holds, in order, every command it ran (``{"cmd", "exit"}``)
and every message to the owner (``{"tell": …}``), so a test can check that the
notice reached the owner before the dispatch.
"""

import json
import subprocess
import sys

words, transcript = sys.argv[1:3]


def log(entry: dict) -> None:
    with open(transcript, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def baton(*args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, "-m", "baton", *args, "--json"], capture_output=True, text=True, timeout=300)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except ValueError:
        payload = {"raw": proc.stdout}
    log({"cmd": list(args), "exit": proc.returncode, "warnings": payload.get("warnings") or []})
    return proc.returncode, payload


def tell(**message: object) -> None:
    log({"tell": message})


code, fr = baton("frame", "--note", words)
run = fr["framing"]
code, el = baton("eligible", run, "frame")
worker = el["eligible"][0]["profile"]
wake = el["wake"]
if not wake["configured"]:
    tell(kind="notice", text=wake["notice"])  # before the dispatch it will not stay attached for
code, d = baton("dispatch", run, "frame", "--worker", worker, "--wait")  # the harness's background job
if code == 4 or d.get("needs_owner"):  # finished, and the owner is needed now: not a failure
    code, st = baton("status", run)
    for p in st.get("pending_decisions") or []:
        tell(kind="question", run=run, ref=p["ref"], prompt=p.get("prompt"), options=[o["label"] for o in p.get("options") or []])
