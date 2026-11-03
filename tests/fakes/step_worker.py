"""A worker for the ``command`` adapter that answers per step (Phase 14 Director tests).

    python step_worker.py <packet> <result> <outputs.json>

``outputs.json`` maps a step id (the last segment of the packet's step path)
to the output to return. Each call is appended to ``calls.jsonl`` beside it.
"""

import json
import pathlib
import sys

packet, result, outputs = (pathlib.Path(a) for a in sys.argv[1:4])
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
step = manifest["step_path"].rsplit("/", 1)[-1]
table = json.loads(outputs.read_text(encoding="utf-8"))
with open(outputs.parent / "calls.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"step": manifest["step_path"], "profile": manifest.get("worker_profile")}) + "\n")
result.mkdir(parents=True, exist_ok=True)
doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": table[step]}
tmp = result / "result.json.tmp"
tmp.write_text(json.dumps(doc), encoding="utf-8")
tmp.replace(result / "result.json")
