## 7. The Packet Protocol

### 7.1 Packet (runtime → worker)

```
.baton/runs/<run_id>/steps/<step_path>/attempt-<n>/packet/
├── manifest.json   INSTRUCTIONS.md   output_schema.json
└── inputs/<name>.json | <name>.<ext> | <name>/<n>.<ext>   (the last: each document of a `many` role, §5.1)
```

```json
{
  "protocol": "baton-packet/1",
  "run_id": "r_20261101_ab12",
  "recipe": "software-feature@1",
  "recipe_sha256": "…",
  "step_path": "slices/x7f3a9c2/i1/implement",
  "attempt": 1,
  "effort": "M",
  "deadline": "2026-11-01T22:00:00Z",
  "workspace": "write",
  "exit_criteria": ["…rendered from the step's gates and output contract…"],
  "protected_paths": ["tests/acceptance/specs/**"],
  "worker_profile": "claude-code-sub",
  "worker_profile_sha256": "…",
  "inputs": [ {"name": "slice", "kind": "json", "path": "inputs/slice.json", "sha256": "…"} ],
  "not_applicable": [],
  "required_artifacts": [],
  "optional_artifacts": [],
  "prior_feedback": null,
  "packet_sha256": "…"
}
```

- `step_path` is `<step>` or, inside a group, `<group>/<instance>/<iteration>/<step>`, where `<instance>` is the runtime-assigned instance id (§5.8).
- `exit_criteria` tells the worker what "done" means (its own DoD); `deadline` bounds its internal iteration.
- `worker_profile_sha256` covers non-secret profile fields only.
- `packet_sha256`: SHA-256 of `"baton-packet/1\n"`, then the canonical manifest JSON (sorted keys, no whitespace, `packet_sha256: null`) and `"\n"`, then `"<path>\0<sha256>\n"` for every other packet file (inputs, `INSTRUCTIONS.md`, `output_schema.json`) sorted by POSIX path. Documented in `packet.py` and tested. The manifest holds no clock reading except `deadline`, which the caller supplies.
- `workspace` is the step's mode (`none` | `read` | `write`); `optional_artifacts` lists declared artifacts that are not required.
- Inputs resolve only from the run's record: run inputs from the CAS blob named in `run_started`, step outputs and artifacts from the hashes in the source step's `step_passed` (or `step_imported`) event, project documents from the run's latest `project_input_bound` for the role (§8.6). Small JSON inputs (up to 16 KiB) are inlined in `INSTRUCTIONS.md`.
- A project document's entry carries `source`: `{kind, path, version, run?, step?, artifact?, revision?, decision_id?, bound_by, edited_since_accepted?}`, `kind` being `deliverable` (with the run, step and artifact that published it) or `attested` (with the attestation's `decision_id`), and `bound_by` the owner's binding decision; `INSTRUCTIONS.md` says which document it is and, when it was edited since it was accepted, that the owner confirmed it as it is. Each document of a `many` role is its own entry with the input's `name`, an `index` from 1 in binding order, and the path `inputs/<name>/<index>.<ext>`.
- `prior_feedback`: `{attempt, reasons, findings?, guidance?, answers?, revision?}`: gate reasons from the previous attempt and any retry guidance; `answers` lists the owner's confirmed answers to the previous attempt's questions (`[{id, answer, owner_words}]`, §13.8), so a `blocked` step resumes with exactly what the owner confirmed; `findings` lists the open findings of a failed findings or review gate, each with its `step`, so the worker can address and disposition them (§9.2). While a revision (§8.9) is not yet accepted, `revision` is `{reason, attempt, output, artifacts, items?}`: the previous accepted result is in the packet as `previous/output.json` and `previous/artifacts/<name>` (hashed like any packet file); for a `foreach` source, `items` names the array whose items carry their ids.

- **Reviewer packets** (steps whose output is `baton:findings`, and review steps, §9.1) also carry `prior_findings`: `null` at the first review, else `{evaluated_at, attempt, findings}`, the previous evaluation of the same findings line with each finding's status and disposition. A review step's inputs are the reviewed step's declared inputs plus the result under review: `reviewed_output` (JSON) and `reviewed_<artifact>` for each registered artifact, from the reviewed attempt's `result_submitted`.

`INSTRUCTIONS.md` contains: role and step title; the rendered step prompt (small JSON inputs inlined, large ones referenced by path); protocol rules (where inputs are, where to write, echo `packet_sha256`, write `result.json` last, do not modify `packet/`, do not modify protected paths); the output schema; prior feedback; for reviewers, the earlier findings with the rule "reuse an id you still see, leave out a resolved one, check each disposition's evidence"; for steps shown findings, how to write `dispositions`.

### 7.2 Result (worker → runtime)

```
attempt-<n>/result/  result.json  artifacts/<name>.<ext>
```

```json
{
  "protocol": "baton-packet/1",
  "packet_sha256": "…",
  "status": "completed",
  "output": { },
  "artifacts": [ {"name": "design_doc", "path": "artifacts/design_doc.md"} ],
  "notes": "",
  "questions_for_human": [],
  "process_feedback": [],
  "dispositions": []
}
```

`dispositions` (optional): `[{step, finding, disposition, evidence}]`, a worker's `fixed` or `rejected` claims about findings it was shown (its own gates' findings, or the judges' findings of an enclosing loop; `step` is the recording step's id or path). Intake checks the evidence (§9.2); an invalid entry rejects the result. `accepted-risk` is not allowed here.

`questions_for_human` (Decision: [0031](../decisions/0031-structured-questions.md)) is structured, so the Director can hold a conversation from it without knowing the step's subject:

```json
{"id": "q1", "ask": "Will each site be one machine, or several?", "why": "Sets how much equipment planning is needed",
 "best_guess": "One machine per site at first", "options": [{"id": "one", "label": "One machine"}, {"id": "several", "label": "Several"}],
 "multi_select": false, "priority": "needed"}
```

`id` (unique in the result), `ask` and `why` are required; `best_guess`, `options` (each `{id, label}`), `multi_select` (default false) and `priority` (`needed` | `helpful`, default `needed`) are optional. `ask`, `why` and labels use the owner's terms, never the recipe's internal vocabulary. A bare string is accepted and normalized to `{id: "q<n>", ask: <string>, why: ""}`, so existing workers keep working; intake (§8.10) rejects an entry that is neither. Answers come back confirmed and structured (`prior_feedback.answers`, §13.8).

`status` is `completed`, `blocked` (needs an owner answer) or `failed`. Workers write only inside `result/`, except `workspace: write` steps, whose changes are checked by gates and recorded through `commit_sha` in `output`. `process_feedback` lets workers report friction (§12.4).
