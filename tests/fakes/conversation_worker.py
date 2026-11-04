"""A worker for the ``command`` adapter for the Phase 17 conversation tests.

    python conversation_worker.py <packet> <result> <outputs.json>

``outputs.json`` maps a step id to ``{"blocked": {...questions...}, "output": {...}}`` or a plain output.
A step with ``blocked`` asks its questions until the packet carries the owner's confirmed answers
(``prior_feedback.answers``), then returns ``output``. Each call is appended to ``calls.jsonl``.
"""

import json
import pathlib
import sys

packet, result, outputs = (pathlib.Path(a) for a in sys.argv[1:4])
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
step = manifest["step_path"].rsplit("/", 1)[-1]
entry = json.loads(outputs.read_text(encoding="utf-8"))[step]
answers = (manifest.get("prior_feedback") or {}).get("answers")
with open(outputs.parent / "calls.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"step": manifest["step_path"], "answers": answers}) + "\n")
doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"]}
if isinstance(entry, dict) and "blocked" in entry and not answers:
    doc.update(status="blocked", output=None, questions_for_human=entry["blocked"])
else:
    doc.update(status="completed", output=entry["output"] if isinstance(entry, dict) and "output" in entry else entry)
result.mkdir(parents=True, exist_ok=True)
tmp = result / "result.json.tmp"
tmp.write_text(json.dumps(doc), encoding="utf-8")
tmp.replace(result / "result.json")
