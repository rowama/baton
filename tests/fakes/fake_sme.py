"""An expert (SME) for the ``command`` adapter whose answer a test scripts (Phase 12).

    python fake_sme.py <packet> <result> <behavior.json>

``behavior.json``: ``{"mode": "answer" | "crash" | "bad", "answer": str, "requested_refs": [...],
"artifacts": {name: text}, "awaiting": {...}, "confidence": ...}``. ``answer`` may contain
``{inputs}``, replaced by the input refs the packet holds.
"""

import json
import pathlib
import sys

packet, result, behavior = (pathlib.Path(a) for a in sys.argv[1:4])
b = json.loads(behavior.read_text(encoding="utf-8"))
mode = b.get("mode", "answer")
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
print(f"fake sme: {mode} turn {manifest['turn']}", flush=True)
if mode == "crash":
    print("the expert fell over", flush=True)
    sys.exit(3)
refs = sorted({i["ref"] for i in manifest["inputs"]})
listed = []
for name, text in (b.get("artifacts") or {}).items():
    p = result / "artifacts" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    listed.append({"name": name, "path": f"artifacts/{name}.md"})
output = {
    "answer": b.get("answer", "It depends.").replace("{inputs}", ", ".join(refs)),
    "confidence": b.get("confidence", "high"),
    "sources_used": refs,
    "requested_refs": b.get("requested_refs", []),
    "suggests_retriage": False,
}
if b.get("awaiting"):
    output["awaiting"] = b["awaiting"]
if mode == "bad":
    output = {"answer": ""}
doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": output, "artifacts": listed}
result.mkdir(parents=True, exist_ok=True)
(result / "result.json").write_text(json.dumps(doc), encoding="utf-8")
