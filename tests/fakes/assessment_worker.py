"""A fake assessment worker for the ``command`` adapter (``baton workers assess``).

    python assessment_worker.py <packet> <result> <overlay.yaml> [dump.json]

Returns ``overlay.yaml`` as the ``overlay`` artifact and a fixed report.
"""

import json
import pathlib
import sys

packet, result, overlay = (pathlib.Path(a) for a in sys.argv[1:4])
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
(result / "artifacts").mkdir(parents=True, exist_ok=True)
(result / "artifacts" / "overlay.yaml").write_bytes(overlay.read_bytes())
if len(sys.argv) > 4:
    dump = {str(p.relative_to(packet)): p.read_text(encoding="utf-8", errors="replace") for p in packet.rglob("*") if p.is_file()}
    pathlib.Path(sys.argv[4]).write_text(json.dumps(dump), encoding="utf-8")
report = {"assessed": [{"model_id": "acme/big-2", "tier": "standard", "summary": "Solid at structured work.", "sources": ["https://example.com/acme"]}],
          "not_assessed": []}
doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": report,
       "artifacts": [{"name": "overlay", "path": "artifacts/overlay.yaml"}], "questions_for_human": []}
(result / "result.json").write_text(json.dumps(doc), encoding="utf-8")
