"""A fake research worker for the ``command`` adapter (tools/worker-research).

    python research_worker.py <packet> <result> <proposal.yaml>

Returns ``proposal.yaml`` as the ``known_workers`` artifact and a fixed report.
"""

import json
import pathlib
import sys

packet, result, proposal = (pathlib.Path(a) for a in sys.argv[1:4])
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
(result / "artifacts").mkdir(parents=True, exist_ok=True)
(result / "artifacts" / "known_workers.yaml").write_bytes(proposal.read_bytes())
report = {"inclusion_criteria": ["can do a bounded job on its own"], "providers_covered": ["anthropic", "openrouter"],
          "categories_covered": ["llm"], "coverage_gaps": ["open-weight models not covered in this fake"],
          "changes": [{"what": "added a model", "why": "test", "sources": ["https://example.org/m"]}]}
doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": "completed", "output": report,
       "artifacts": [{"name": "known_workers", "path": "artifacts/known_workers.yaml"}], "questions_for_human": []}
(result / "result.json").write_text(json.dumps(doc), encoding="utf-8")
