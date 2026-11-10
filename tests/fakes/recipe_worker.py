"""A scripted worker for the ``command`` adapter that can do any step of the example recipes (Phase 16).

    python recipe_worker.py <packet> <result> <script.json> [<workspace>]

``script.json`` maps a key to a response, or to a list of responses used one per
call (the last one repeats). The key is tried as ``<step id>:<slice title>``
(when the packet has a ``slice`` input), then ``<step id>`` (review steps are
``<step>~review``). A response may hold:

- ``output``: the output (for a commit, ``commit_sha`` is filled in);
- ``artifacts``: ``{name: text}``, written to ``result/artifacts/<name>.md``;
- ``commit``: ``{path, text}``, written in the workspace and committed there;
- ``commit_files``: ``{path: text, ...}``, all written and committed together (a generated package);
- ``dispose``: ``fixed`` or ``rejected``: a disposition for every open finding
  the packet shows (``open_findings``), with the new commit as ``fixed`` evidence;
- ``status``, ``questions_for_human``.

Every call is appended to ``calls.jsonl`` beside the script.
"""

import json
import pathlib
import subprocess
import sys

packet, result, script = (pathlib.Path(a) for a in sys.argv[1:4])
workspace = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None
manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
step = manifest["step_path"].rsplit("/", 1)[-1]
inputs = {i["name"]: json.loads((packet / i["path"]).read_text(encoding="utf-8")) for i in manifest["inputs"] if i["kind"] == "json"}
title = (inputs.get("slice") or {}).get("title")

table = json.loads(script.read_text(encoding="utf-8"))
key = f"{step}:{title}" if title is not None and f"{step}:{title}" in table else step
counts_file = script.parent / "counts.json"
counts = json.loads(counts_file.read_text(encoding="utf-8")) if counts_file.exists() else {}
n = counts.get(key, 0)
counts[key] = n + 1
counts_file.write_text(json.dumps(counts), encoding="utf-8")
entry = table[key]
resp = entry[min(n, len(entry) - 1)] if isinstance(entry, list) else entry

with open(script.parent / "calls.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"step": manifest["step_path"], "profile": manifest.get("worker_profile"), "key": key, "n": n,
                        "inputs": sorted(inputs), "not_applicable": manifest.get("not_applicable", [])}) + "\n")


def git(*args):
    return subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=workspace, check=True, capture_output=True, text=True).stdout.strip()


output = dict(resp.get("output") or {})
sha = None
if "commit" in resp:
    target = workspace / resp["commit"]["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(resp["commit"]["text"].encode("utf-8"))
    git("add", resp["commit"]["path"])
    git("commit", "-q", "-m", f"{title or step}: {resp['commit']['path']}")
    sha = git("rev-parse", "HEAD")
    output["commit_sha"] = sha

if "commit_files" in resp:
    for rel, text in resp["commit_files"].items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        git("add", rel)
    git("commit", "-q", "-m", f"{title or step}: {len(resp['commit_files'])} files")
    sha = git("rev-parse", "HEAD")
    output["commit_sha"] = sha

result.mkdir(parents=True, exist_ok=True)
listed = []
for name, text in (resp.get("artifacts") or {}).items():
    (result / "artifacts").mkdir(exist_ok=True)
    (result / "artifacts" / f"{name}.md").write_bytes(text.encode("utf-8"))
    listed.append({"name": name, "path": f"artifacts/{name}.md"})

dispositions = []
if resp.get("dispose"):
    for fnd in (inputs.get("open_findings") or {}).get("findings", []):
        evidence = sha if resp["dispose"] == "fixed" else fnd.get("location")
        dispositions.append({"step": fnd["step"], "finding": fnd["id"], "disposition": resp["dispose"], "evidence": evidence})

doc = {"protocol": "baton-packet/1", "packet_sha256": manifest["packet_sha256"], "status": resp.get("status", "completed"),
       "output": output, "artifacts": listed, "questions_for_human": resp.get("questions_for_human", []), "dispositions": dispositions}
tmp = result / "result.json.tmp"
tmp.write_text(json.dumps(doc), encoding="utf-8")
tmp.replace(result / "result.json")
