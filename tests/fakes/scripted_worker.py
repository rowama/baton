"""A worker for the ``command`` adapter whose behaviour a test scripts (Phase 7).

    python scripted_worker.py <packet> <result> <behavior.json>

``behavior.json``: ``{"mode": ..., "output": {...}, "seconds": n, "gate": path}``

* ``good``: write a completed result with ``output`` (after ``seconds``, if given).
* ``bad``: write a completed result whose output is ``{}`` (fails the schema).
* ``hang``: sleep forever (until killed).
* ``crash``: print a line and exit 3 without a result.
* ``result_then_hang``: write the good result, then sleep forever.
* ``gate``: wait until the file ``gate`` exists, then behave as ``good``.
"""

import json
import pathlib
import sys
import time

packet, result, behavior = (pathlib.Path(a) for a in sys.argv[1:4])
b = json.loads(behavior.read_text(encoding="utf-8"))
mode = b.get("mode", "good")
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))


def write(output):
    result.mkdir(parents=True, exist_ok=True)
    doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": output}
    tmp = result / "result.json.tmp"
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(result / "result.json")


print(f"scripted worker: {mode}", flush=True)
if mode == "gate":
    while not pathlib.Path(b["gate"]).exists():
        time.sleep(0.05)
    mode = "good"
if b.get("seconds"):
    time.sleep(b["seconds"])
if mode == "good":
    write(b.get("output", {}))
elif mode == "bad":
    write({})
elif mode == "crash":
    print("something broke badly", flush=True)
    sys.exit(3)
elif mode in ("hang", "result_then_hang"):
    if mode == "result_then_hang":
        write(b.get("output", {}))
    while True:
        time.sleep(1)
