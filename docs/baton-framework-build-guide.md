# Baton: Build Guide for a Vendor-Neutral, Director-Led Multi-Step Process Framework

> **Revision 2.2.** Adds adoption into existing projects (detect, doctor, research, triage, seeding, baseline), complexity-tailored processes, built-in subject-matter consultation, and the "invisible when healthy" principle. See §20; supporting changes in §1, §3, §5, §7, §11, §12, §14.
>
> **Revision 2.1.** Renamed from the working title "Relay" to **Baton** (repo `rowama/baton`). No design changes from Revision 2.
>
> **Revision 2.** Adds model-neutral process packages, capability-based dynamic routing, per-step isolated worker execution, repo-resident run persistence for cross-platform handoff, and publishing of deliverables into the project tree.
>
> **Audience:** a fresh AI coding session (Claude Code, Codex, Hermes, etc.) tasked with building this framework from scratch.
> **Read this whole document before writing code.** Then follow the Build Phases (§12) in order. Each phase has acceptance criteria. Do not start a phase until the previous one passes.

---

## 0. Ground Rules for the Building Agent

1. **Do not invent APIs.** Before using any library (`mcp`, `litellm`, `jsonschema`, `typer`, etc.) or any CLI (`claude`, `codex`, `hermes`), check its installed version's docs or `--help`. Where this guide marks something **[VERIFY]**, you must confirm it against current docs before relying on it.
2. **Determinism over prompting.** Anything that must be 100% reliable is enforced in code. It is never left to an LLM following instructions.
3. **Thin layer.** No web UI, no message broker, no database server. Use the filesystem, git, SQLite (as a cache only) and plain Python. Every dependency must justify itself.
4. **Vendor neutrality.** No model vendor is privileged anywhere in the core or in process packages. Vendors exist only inside worker profiles and adapters.
5. **Small, tested increments.** Write tests alongside each module. Keep `pytest` green at every commit.
6. **Ask the human** when a requirement here is ambiguous. Do not silently pick an interpretation for anything listed in §14 (Open Decisions).
7. **The name is a label, not a spec.** "Baton" evokes work passed from worker to worker under the Director. Use the metaphor only where it helps explain or group a concept. Never derive a design decision, feature or term from it; use plain technical names (step, packet, result, worker, gate) in code and docs.

---

## 1. What We Are Building

A small runtime ("**Baton**") that lets *any* agentic harness act as the **Director** of a multi-step process, while each step is executed by a **Worker**. A Worker can be a raw model API call, another harnessed agent or a human. Baton guarantees:

| Guarantee | Mechanism |
|---|---|
| **100% reliable context handoff** | Runtime (not the Director) assembles each step's context packet from a declared contract. A missing or invalid required input means the step refuses to start. Packets are content-hashed. |
| **Standard communication** | Fixed file-based packet in / result out protocol, the same for every worker type. |
| **Model-neutral, shareable recipes** | Process packages declare *capability requirements*, never models or vendors. A loader lint enforces this. |
| **Dynamic routing** | The Director picks a worker per step from the runtime-computed eligible set. The runtime enforces eligibility and pins and logs the choice. |
| **Per-step isolation** | Every worker runs as a child process with its own constructed environment and auth (API key or CLI subscription login), selectable per worker profile. |
| **Observability** | Append-only event log (JSONL) of every transition, packet, result, gate outcome, routing choice and human decision. |
| **Documentation** | Each step renders a Markdown record. Each run produces a summary. |
| **Verification** | Declarative gates per step: schema, script, LLM review, human sign-off. |
| **Cross-platform continuity** | Run state lives in the project repo. Any capable Director can `baton resume` from the last committed checkpoint. |
| **Deliverables in the project** | Specs, designs, plans and drawings are published to real project paths. The run directory holds their provenance. |
| **Tailored formality** | A triage step rates the work on the recipe's own complexity scale. The runtime includes or skips steps and gates from that rating deterministically. |
| **Low-friction adoption** | Existing projects are adopted in place: existing work is imported as attested step outputs, and a single human-approved baseline starts normal operation. |
| **Subject-matter consultation** | Subject-matter questions always go to a consult worker with a runtime-assembled packet. The Director routes; it never answers from its own inference. |
| **Invisible when healthy** | Checks, detection and resume are silent unless something is wrong. Human attention is spent only at gates, escalations and the adoption baseline. |

### Non-goals

- Not an agent framework. Baton does not run an LLM loop itself; Directors and Workers do.
- Not a scheduler or queue. Steps run when the Director dispatches them.
- No GUI. Use the CLI and Markdown outputs.

---

## 2. Roles

- **Human:** owns goals, approves human gates, answers escalations. Talks only to the Director.
- **Director:** any harness loaded with the `baton-director` skill and connected to the Baton MCP server (or using the CLI). It is an expert at *running processes, routing work and communicating*, not at any step's domain. It **never performs step work itself**.
- **Baton runtime:** deterministic Python, installed as a pinned tool. The project repo's event logs are the source of truth for run state.
- **Worker:** executes exactly one step attempt under one **worker profile**. It receives a packet directory and must produce a result directory. It is stateless with respect to the run.

```
Human ⇄ Director (any harness)
            │  MCP tools / CLI
            ▼
        Baton runtime ── project repo: .baton/runs/<run_id>/ (events, CAS, docs)
            │  spawn child process with profile's env + auth
            ▼
        Worker (API model | headless harness | human)
            │  writes result/ (result.json + artifacts)
            ▼
        Baton validates → gates → records → publishes → checkpoint commit → next step ready
```

---

## 3. Key Design Decisions (and why)

1. **Runtime owns handoff.** The Director only says "begin step X with worker profile P". Baton decides what goes into the packet based on the process definition. This removes the main failure mode, a Director that summarizes, forgets or paraphrases context.
2. **File-based protocol.** Every harness can read and write files. Packets and results are directories, so they are inspectable, diffable and replayable.
3. **Content addressing.** Every artifact is stored by SHA-256. A packet manifest lists the hashes. The worker's `result.json` must echo `packet_sha256`, which proves it was produced against that exact packet.
4. **Provenance-checked gates.** An artifact counts only if it was registered through `submit_step`. This blocks a Director that bypasses Baton and does the work itself.
5. **Processes are model-neutral data.** Domain knowledge lives in YAML, schemas, prompts and templates. Steps declare *what capabilities they need*, never *who* does them. The same package can run on completely different models in different instances.
6. **Routing is dynamic but enforced.** The Director chooses, the runtime constrains. Eligibility is computed deterministically from capability declarations; an ineligible choice is rejected.
7. **Isolation by construction.** Workers never inherit the Director's environment by default. Each profile declares exactly what its child process sees, so one step's API key can never change another step's billing or auth.
8. **The repo is the system of record.** Event logs, artifacts and records are committed at checkpoints. SQLite is a rebuildable cache. This makes runs portable across machines and Director platforms.
9. **MCP as the Director interface, CLI as the fallback.** Both call the same Python core.
10. **Invisible when healthy.** Baton earns its place only if the human isn't babysitting it. Every check reports nothing when there is nothing to report, and every human touchpoint must be a real decision (a gate, an escalation, the adoption baseline), never a confirmation of routine machinery.
11. **The Director is the process expert, not the subject-matter expert.** It explains the run in plain language (where it has been, where it is, where it could go) from the record. For subject matter it points to recorded work or routes the question to a consult worker. It never answers subject-matter questions from its own inference, and the process never changes based on anything held only in the Director's context.
12. **Formality scales with complexity, decided once and recorded.** Triage is a normal step whose output picks the complexity level. The runtime applies it; the Director never decides which steps to skip.
13. **The Director never modifies a process.** It does not add, remove or reorder steps or roles. Variability comes only from the recipe's own complexity levels and the built-in consult mechanism.

---

## 4. Repository Layouts

There are three distinct things. Keep them separate.

### 4.1 The Baton runtime (its own repo, installed as a pinned tool)

```
baton/
├── pyproject.toml
├── README.md
├── src/baton/
│   ├── models.py          # pydantic models: ProcessDef, StepDef, Requires, WorkerProfile, Packet, Result, Event…
│   ├── capabilities.py    # vocabulary loading + matching
│   ├── process_loader.py  # load + validate + neutrality lint
│   ├── profiles.py        # worker profile loading, secret resolution, env construction
│   ├── routing.py         # eligible_workers(), preference ordering
│   ├── store.py           # run dir, CAS, events.jsonl writer, SQLite cache rebuild
│   ├── state.py           # step state machine
│   ├── lease.py           # run lease claim/renew/takeover
│   ├── packet.py          # context packet builder (the critical module)
│   ├── validate.py        # JSON Schema validation
│   ├── gates.py
│   ├── publish.py         # deliverable publishing + drift detection
│   ├── docs.py            # Jinja2 rendering
│   ├── gitops.py          # checkpoint commits
│   ├── redact.py          # secret redaction for anything committed
│   ├── engine.py          # orchestration API used by MCP + CLI
│   ├── worker_runner.py   # `python -m baton.worker_runner` — child-process entrypoint for API workers
│   ├── adapters/
│   │   ├── base.py
│   │   ├── litellm_api.py
│   │   ├── subprocess_harness.py
│   │   ├── claude_code.py # preset [VERIFY flags]
│   │   ├── codex.py       # preset [VERIFY flags]
│   │   └── manual.py
│   ├── mcp_server.py
│   └── cli.py
├── capabilities/
│   └── baton-capabilities-1.yaml   # versioned controlled vocabulary (§5.4)
├── skills/
│   ├── baton-director/SKILL.md
│   └── baton-worker/SKILL.md
├── examples/processes/
│   ├── software-feature/
│   └── backyard-project/
└── tests/
```

### 4.2 A process package (shareable recipe directory; model-neutral)

```
software-feature/
├── process.yaml
├── schemas/*.json
├── prompts/*.md
├── templates/*.md.j2
└── static/…               # reference files shipped with the recipe
```

### 4.3 Machine/user-local configuration (never in any repo)

```
~/.baton/
├── workers.yaml           # worker profiles (§5.5)
├── secrets/               # optional file-based secret store (0700)
├── homes/<profile>/       # optional relocated CLI config homes [VERIFY support per CLI]
└── logs/                  # unredacted raw worker stdout/stderr
```

Project-local overrides go in `.baton/workers.local.yaml`, which is **gitignored**.

---

## 5. Process Definition Format

### 5.1 `process.yaml`

```yaml
id: software-feature
version: 1
capabilities_vocab: baton-capabilities/1
description: Take a feature request to a merged, tested change.

run_inputs:
  schema: schemas/run_inputs.json

defaults:
  max_attempts: 3

complexity:                        # recipe-owned scale, lowest to highest (§20.4)
  levels: [minor, standard, major]
  triage_step: triage

consult_requires:                  # optional; default is in the vocabulary file (§20.6)
  capabilities: [long_form_writing, technical_reasoning]
  tier: strong

steps:
  - id: triage
    title: Assess complexity
    requires:
      capabilities: [structured_output, technical_reasoning]
      tier: standard
    prompt: prompts/triage.md       # recipe-specific criteria
    inputs:
      - { name: feature_request, from: run.inputs.feature_request, required: true }
      - { name: research,        from: research.findings,          required: false }   # present on adoption (§20.3)
    output_schema: schemas/triage_out.json   # must include level + reasons (§20.4)
    gates:
      - type: schema

  - id: requirements
    title: Clarify requirements
    depends_on: [triage]
    applies_to: [standard, major]     # skipped (recorded) for minor work
    requires:
      capabilities: [structured_output, long_form_writing]
      min_context_tokens: 64000
      tier: strong                     # vocabulary-defined: basic | standard | strong
    prompt: prompts/requirements.md
    inputs:
      - { name: feature_request, from: run.inputs.feature_request, required: true }
      - { name: repo_overview,   from: run.inputs.repo_overview,   required: false }
    output_schema: schemas/requirements_out.json
    artifacts:
      - name: requirements_doc
        required: true
        media_type: text/markdown
        publish: { to: "{{ paths.specs }}/{{ run.slug }}-requirements.md" }
    gates:
      - type: schema
      - type: human
        applies_to: [major]          # gates can be level-scoped too
        prompt: "Approve requirements before design?"
    doc_template: templates/step_record.md.j2

  - id: design
    title: Technical design
    depends_on: [requirements]
    applies_to: [major]
    requires:
      capabilities: [structured_output, long_form_writing, technical_reasoning]
      tier: strong
    prompt: prompts/design.md
    inputs:
      - { name: requirements,     from: steps.requirements.output,                     required: true }
      - { name: requirements_doc, from: steps.requirements.artifacts.requirements_doc, required: true }
    output_schema: schemas/design_out.json
    artifacts:
      - name: design_doc
        required: true
        media_type: text/markdown
        publish: { to: "{{ paths.designs }}/{{ run.slug }}-design.md" }
    gates:
      - type: schema
      - type: llm_review
        reviewer_requires:
          capabilities: [structured_output, technical_reasoning]
          tier: strong
        independence: different_vendor    # different_model | different_vendor
        rubric: prompts/design_review_rubric.md

  - id: implement
    depends_on: [triage, requirements, design]   # skipped dependencies count as satisfied
    requires:
      capabilities: [tool_use, file_write, shell, code_exec, repo_workspace]
      tier: strong
    workspace: project_root           # worker operates in the project repo
    prompt: prompts/implement.md
    inputs:
      - { name: feature_request,  from: run.inputs.feature_request,                    required: true }
      - { name: triage,           from: steps.triage.output,                           required: true }
      - { name: requirements_doc, from: steps.requirements.artifacts.requirements_doc, required: true }
      - { name: design,           from: steps.design.output,                           required: true }
      - { name: design_doc,       from: steps.design.artifacts.design_doc,             required: true }
      # "required" applies only when the source step is included at the run's level (§20.4)
    output_schema: schemas/implement_out.json   # must include commit_sha
    gates:
      - type: schema
      - type: script
        run: "{{ project.test_command }}"
        cwd: project_root
        timeout_s: 900
```

### 5.2 Input source references (closed grammar)

Only these forms are legal. The loader must reject anything else.

| Reference | Resolves to |
|---|---|
| `run.inputs.<key>` | Field of validated run inputs |
| `steps.<id>.output` | The `output` object of that step's **passed** result |
| `steps.<id>.output.<json.path>` | Sub-field of the above |
| `steps.<id>.artifacts.<name>` | CAS blob from that step's passed result (**never** the published copy; see §19) |
| `static.<relative/path>` | File shipped inside the process package |
| `human.<decision_id>` | A recorded human decision |
| `human_revision.<step_id>.<artifact>` | A human edit to a published artifact, explicitly ingested (§19.3) |
| `research.findings` | The adoption research result (§20.3); absent for runs that did not start with adoption |

`steps.<id>.*` references resolve equally to a **passed** or an **imported** (seeded) step (§20.5). Consultation answers are deliberately **not** referenceable; they enter a run only after promotion to a human decision or revision (§20.6).

**Load-time validation** (in `process_loader.py`):
- Every `steps.<id>` reference names an ancestor in `depends_on`, including transitive ancestors.
- No cycles. Every file path exists. Every schema is valid JSON Schema (Draft 2020-12).
- Every gate `type` is known, and every `requires` / `reviewer_requires` / `consult_requires` uses only names from the declared `capabilities_vocab`.
- `publish.to` templates may reference only `paths.*`, `run.*` and `project.*` variables.
- If `complexity` is declared: the triage step exists, has no `applies_to`, and its output schema includes `level` constrained to the declared levels. Every `applies_to` (on steps and gates) uses only declared levels.
- **Per-level closure:** for each level, compute the included steps. Every included step must still be reachable, and the run must have at least one included step after triage. The loader prints a per-level step table (`baton plan <process>`) so recipe authors can see exactly what each level runs.

### 5.3 Neutrality lint (mandatory, blocking)

The loader **rejects** any process package containing:
- the keys `worker`, `model`, `adapter`, `provider`, `profile`, `api_key`, `auth` anywhere in `process.yaml`;
- string values matching known vendor or model patterns (a maintained denylist in `baton-capabilities-*.yaml`: e.g. `openai/`, `anthropic/`, `gpt-`, `claude-`, `gemini`, `grok`, `llama`). Prompts and templates are scanned too, with a warning rather than an error, since prose may legitimately mention a vendor.

This is what makes a package safely shareable: it can be dropped into any project and run with any compliant workers.

### 5.4 Capability vocabulary (`baton-capabilities/1`)

A versioned, controlled list shipped with the runtime. Example entries:

```yaml
id: baton-capabilities/1
capabilities:
  structured_output:   "Reliably returns JSON conforming to a supplied schema"
  long_form_writing:   "Produces coherent multi-page documents"
  technical_reasoning: "Sound multi-step technical/engineering analysis"
  tool_use:            "Can call tools / functions"
  file_write:          "Can write files to a given directory"
  shell:               "Can execute shell commands"
  code_exec:           "Can run code and observe results"
  repo_workspace:      "Can operate inside a git working tree and commit"
  workspace_read:      "Can read (not modify) files in a project working tree"
  vision:              "Accepts image inputs"
  web_access:          "Can fetch / search the web"
tiers: [basic, standard, strong]
numeric:
  min_context_tokens: "Worker profile context_tokens must be >= this"
vendor_denylist: ["openai/", "anthropic/", "gpt-", "claude-", "gemini", "grok", "llama", "mistral"]
```

Rules:
- Unknown capability names are a **load error** for both packages and profiles.
- New capabilities ⇒ new vocabulary version. The runtime supports multiple versions side by side; packages declare which one they target.

### 5.5 Worker profiles (`~/.baton/workers.yaml`, machine-local)

A profile bundles everything needed to run one worker in isolation:

```yaml
openai-api-strong:
  adapter: litellm_api
  vendor: openai                     # used only for `independence` checks
  model: "openai/…"                  # [VERIFY current model strings]
  capabilities: [structured_output, long_form_writing, technical_reasoning, tool_use]
  tier: strong
  context_tokens: 200000
  auth:
    mode: api_key
    env: { OPENAI_API_KEY: "secret:openai_main" }
  env_mode: clean
  isolation: none

codex-pro-sub:
  adapter: codex
  vendor: openai
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth:
    mode: cli_login                  # uses the CLI's stored login (e.g. ChatGPT plan)
  env_mode: allowlist
  env_allow: [HOME, USERPROFILE, APPDATA, LOCALAPPDATA, PATH, LANG, TERM]
  env_deny:  [OPENAI_API_KEY, CODEX_API_KEY]   # stray keys could flip billing to API
  timeout_s: 3600

claude-code-max:
  adapter: claude_code
  vendor: anthropic
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }
  env_mode: allowlist
  env_allow: [HOME, USERPROFILE, APPDATA, LOCALAPPDATA, PATH, LANG, TERM]
  env_deny:  [ANTHROPIC_API_KEY]
  timeout_s: 3600

human:
  adapter: manual
  vendor: human
  capabilities: [long_form_writing, vision, file_write]
  tier: strong
```

**Field rules**

| Field | Values | Notes |
|---|---|---|
| `auth.mode` | `api_key` \| `cli_login` \| `none` | `api_key` injects resolved secrets into the child environment. `cli_login` relies on the CLI's stored credentials on disk or in the OS keystore. |
| `env_mode` | `clean` \| `allowlist` \| `inherit` | `clean`: build env from scratch (PATH, LANG, injected secrets only). `allowlist`: clean + `env_allow` passthroughs. `inherit`: full parent env minus `env_deny`, the escape hatch when a harness's auth depends on something unidentified. |
| defaults | `api_key` ⇒ `clean`; `cli_login` ⇒ `allowlist` with HOME-type vars | `env_deny` is always applied last, in every mode. |
| `auth.config_home` | path | Optional relocated CLI config directory so multiple logins can coexist **[VERIFY each CLI supports this and which env var it uses]**. |
| `isolation` | `none` \| `user` \| `container` | `container` runs the worker in a container with only the packet, result and workspace mounted. |
| secrets | `secret:<name>` | Resolved only at spawn time, from env var, OS keyring or `~/.baton/secrets/<name>`, in that configurable order. **Never** written to packets, manifests, events or logs. |

**Credential storage caveat [VERIFY]:** CLI logins are usually files under the user's home directory (e.g. Codex keeps its login under `~/.codex/`). Some CLIs may use the OS keychain on some platforms, which can require the user's login session rather than any env var. `baton doctor` (§11.2) exists to catch this per profile, per machine.

---

## 6. The Communication Protocol

### 6.1 Packet (Baton → Worker)

```
.baton/runs/<run_id>/steps/<step_id>/attempt-<n>/packet/
├── manifest.json
├── INSTRUCTIONS.md        # rendered prompt + protocol rules + output contract
├── inputs/
│   ├── <name>.json
│   └── <name>.<ext>
└── output_schema.json
```

`manifest.json`:

```json
{
  "protocol": "baton/2",
  "run_id": "r_20261101_ab12",
  "process_id": "software-feature",
  "process_version": 1,
  "process_package_sha256": "…",
  "step_id": "design",
  "attempt": 1,
  "worker_profile": "openai-api-strong",
  "worker_profile_sha256": "…",
  "inputs": [
    {"name": "requirements", "kind": "json", "path": "inputs/requirements.json", "sha256": "…"},
    {"name": "requirements_doc", "kind": "file", "path": "inputs/requirements_doc.md", "sha256": "…"}
  ],
  "required_artifacts": ["design_doc"],
  "result_dir": "../result",
  "prior_attempt_feedback": null,
  "packet_sha256": "…"
}
```

- `worker_profile_sha256` is a hash of the profile's **non-secret** fields (adapter, vendor, model, capabilities, tier, env_mode, isolation). It gives auditability without leaking credentials.
- `packet_sha256` is SHA-256 over the canonical JSON (sorted keys, no whitespace) of the manifest **with `packet_sha256` set to `null`**, combined with the hashes of every file in `inputs/`, `INSTRUCTIONS.md` and `output_schema.json`. Document the exact algorithm in code and test it.
- On retry, `prior_attempt_feedback` holds the gate failure reasons from the previous attempt.

### 6.2 Result (Worker → Baton)

```
attempt-<n>/result/
├── result.json
└── artifacts/<name>.<ext>
```

```json
{
  "protocol": "baton/2",
  "packet_sha256": "…",
  "status": "completed",
  "output": { "...": "must validate against output_schema.json" },
  "artifacts": [{"name": "design_doc", "path": "artifacts/design_doc.md"}],
  "notes": "free text for the record",
  "questions_for_human": []
}
```

- `packet_sha256` must match the packet, or the result is rejected.
- `status` is one of `completed`, `blocked` (needs a human answer) or `failed`.
- Workers write **only** inside `result/`, except workspace workers, whose project changes are captured by gates and a `commit_sha` in `output`.

### 6.3 `INSTRUCTIONS.md` structure (rendered by Baton)

1. Role and step title
2. Step prompt (Jinja2; small JSON inputs inlined, large inputs referenced by path)
3. **Protocol rules:** input and output locations, the required `packet_sha256`, "write `result.json` last", "do not modify `packet/`"
4. Output schema inline
5. Prior-attempt feedback, if any

---

## 7. Runtime Internals

### 7.1 Step state machine (`state.py`)

```
blocked_on_deps → ready → dispatched → submitted → verifying → passed → published
                     ↑          │                       │
                     │          └→ orphaned (on resume) ┤
                     └──── retry (attempt+1) ◄──────────┤ failed (attempts < max)
                                                        └→ escalated (attempts ≥ max | status=blocked | no eligible worker)
escalated → ready (after human decision) | abandoned
awaiting_human  (human gate pending) → verifying
blocked_on_deps → skipped    (not applicable at the run's complexity level; set by the runtime after triage)
blocked_on_deps → imported   (seeded from existing work at adoption; §20.5)
skipped → blocked_on_deps    (only via an approved re-triage; §20.4)
```

`skipped` and `imported` both satisfy `depends_on`. Inputs referencing a `skipped` step are omitted and listed in the manifest as `not_applicable`; their `required` flag does not apply.

Only `engine.py` performs transitions; each one appends exactly one event. Illegal transitions raise errors. Test every edge.

### 7.2 Store (`store.py`): events are the source of truth

- **Run directory:** `<project>/.baton/runs/<run_id>/` containing `events.jsonl`, `cas/`, `steps/` and `docs/`.
- **`events.jsonl`** is append-only and is the authoritative state. Each event has `seq` (monotonic), `ts`, `run_id`, `step_id`, `attempt`, `type`, `actor` (director id / runtime / human) and `data`. Each line also carries `prev_sha256` (hash chain), which detects tampering or bad merges.
- **CAS:** `.baton/runs/<run_id>/cas/<sha[:2]>/<sha>`, written atomically (temp file plus `os.replace`). Binaries over a configurable size are expected to be tracked by Git LFS (§17).
- **SQLite** (`.baton/cache/state.db`, gitignored) is a **derived cache** for fast queries. `store.rebuild(run_id)` replays events to regenerate it. On any mismatch, events win.
- Event types: `run_started`, `lease_claimed`, `lease_renewed`, `lease_taken_over`, `lease_released`, `step_ready`, `worker_selected`, `packet_built`, `dispatched`, `result_submitted`, `result_rejected`, `gate_passed`, `gate_failed`, `step_passed`, `artifact_published`, `drift_detected`, `human_revision_ingested`, `step_escalated`, `attempt_orphaned`, `human_decision`, `checkpoint_committed`, `run_completed`, `run_abandoned`, plus (§20) `situation_detected`, `research_recorded`, `complexity_set`, `step_skipped`, `step_imported`, `retriage_requested`, `retriage_applied`, `baseline_established`, `consult_requested`, `consult_answered`, `consult_promoted`.

### 7.3 Routing (`routing.py`)

`eligible_workers(run_id, step_id)`:
1. Load all profiles (user-level, then `.baton/workers.local.yaml` overrides).
2. Keep a profile only if it has **all** required capabilities, its tier is ≥ the required tier, and it meets every numeric minimum (e.g. `context_tokens ≥ min_context_tokens`). For `workspace` steps it must also have `repo_workspace`.
3. Order the survivors by `.baton/preferences.yaml` (committed, non-secret), e.g.:
   ```yaml
   prefer:
     by_step: { implement: [claude-code-max, codex-pro-sub] }
     by_capability: { vision: [human] }
   exclude: [some-profile]
   ```
   Preferences **reorder or exclude only**; they can never add an ineligible profile.
4. Return the ordered list with a short reason per profile, plus the reason for each exclusion (useful to the Director and the human).

If the list is empty, the step goes to `escalated` with reason `no_eligible_worker` (or fails; see §14).

**Review-gate routing:** `llm_review` selects from profiles satisfying `reviewer_requires` **and** the `independence` constraint relative to the step's chosen profile: `different_model` compares `model`, `different_vendor` compares `vendor`.

### 7.4 Packet builder (`packet.py`): the critical module

`build_packet(run, step, profile)`:
1. Assert all `depends_on` steps are `passed`, and that `profile` is in `eligible_workers` (re-checked here, not trusted from the caller).
2. Resolve each input. If any **required** input is unresolvable, raise `HandoffError` listing *every* missing input. No partial packet is written.
3. Copy resolved blobs from CAS (inputs always come from CAS or recorded human revisions, never from published copies).
4. Render `INSTRUCTIONS.md` and copy `output_schema.json`.
5. Compute hashes, write `manifest.json`, make the packet read-only.
6. Emit `worker_selected` and `packet_built` events.

Property tests: same state + same profile ⇒ identical `packet_sha256`; removing any required input ⇒ `HandoffError`.

### 7.5 Result intake (`engine.submit_step`)

1. Load `result.json` and check `protocol` and `packet_sha256`.
2. Validate `output` with `jsonschema` (Draft 2020-12, format checking on).
3. Verify required artifacts exist and are non-empty, then ingest them into CAS.
4. If `status == blocked`, go to `escalated` with `questions_for_human`.
5. Run the gates in order and stop at the first failure.
6. If all pass: `step_passed`, then publish (§19), render the step record (§9), checkpoint commit (§18.2) and mark dependents `ready`.

### 7.6 Engine API (`engine.py`)

| Function | Purpose |
|---|---|
| `list_processes()` | Process packages vendored in this project |
| `start_run(process_id, inputs)` | Validate inputs, claim lease, create run, return `run_id` + ready steps |
| `status(run_id)` | Step states, attempts, pending human items, lease holder, drift warnings |
| `eligible_workers(run_id, step_id)` | Ordered eligible profiles + exclusion reasons |
| `begin_step(run_id, step_id, worker)` | Validate eligibility, build packet, return packet path |
| `dispatch_step(run_id, step_id, worker)` | `begin_step` + spawn worker + `submit_step` (the common path) |
| `submit_step(run_id, step_id, result_dir)` | For externally run (e.g. manual) workers |
| `record_human_decision(run_id, ref, decision, note)` | Approve gates / answer questions (verbatim text) |
| `retry_step(run_id, step_id, worker?, extra_guidance?)` | New attempt; may switch worker; guidance is additive only |
| `ingest_human_revision(run_id, step_id, artifact)` | Accept a drifted published file as a recorded revision (§19.3) |
| `resume(run_id)` | Rebuild cache, verify CAS + hash chain, orphan stale attempts, claim lease |
| `claim_lease / renew_lease / release_lease / take_over_lease(reason)` | Run lease management (§18.3) |
| `get_step_record(run_id, step_id)` / `run_summary(run_id)` | Rendered docs |
| `abandon_run(run_id, reason)` | Terminal |
| `detect()` | Deterministic situation check (§20.2); silent summary when healthy |
| `adopt(process_id, inputs, crosswalk?)` | Start an adoption run: research → triage → proposed seeds and baseline (§20.3) |
| `establish_baseline(run_id, decision)` | Apply the human-approved baseline: imports, complexity, skipped steps (§20.7) |
| `request_retriage(run_id, reason)` | Re-run triage behind a human gate; affects not-yet-started steps only (§20.4) |
| `explain(run_id, scope?)` | Plain-language narrative of past, present and possible paths, built from the record (§20.8) |
| `consult(run_id, question, refs, mode)` | Subject-matter consultation; runtime assembles the packet from the Director's references (§20.6) |
| `consult_followup(consult_id, question, extra_refs?)` | Next turn of a consultation |
| `promote_consult(consult_id, as, note)` | Turn a consult answer into a human decision or revision, with human approval |
| `doctor(profile?)` | Profile health check (§11.2) |

Every mutating call requires the caller to hold the run lease.

---

## 8. Verification Gates (`gates.py`)

| Type | Behaviour | Pass condition |
|---|---|---|
| `schema` | Done at intake; recorded as a gate for the audit trail | Valid |
| `script` | Runs a command with `cwd`/`timeout_s` under a clean env; output is redacted, then stored in CAS | Exit 0 |
| `llm_review` | Builds a **review packet** (step inputs + result + rubric) and dispatches it to a reviewer chosen per §7.3. Fixed reviewer schema: `{verdict: pass\|fail, reasons: [str]}` | `verdict == pass` |
| `human` | Moves the step to `awaiting_human`; the Director asks and calls `record_human_decision` | Decision = approve |
| `provenance` | Implicit: every referenced artifact was registered via `submit_step` | Always enforced |

Gate failures produce structured `reasons`, which become `prior_attempt_feedback` on retry.

---

## 9. Documentation System (`docs.py`)

- **Step record** (`.baton/runs/<id>/docs/<step_id>.md`): title, worker profile (name and non-secret hash, never secrets), attempt count, inputs with hashes, output, artifacts (CAS hash **and** published path), gate results, notes and human decisions.
- **Run summary** (`.baton/runs/<id>/docs/SUMMARY.md`): process and version, inputs, timeline from events, a per-step table (worker, attempts, gates, published deliverables), escalations and lease history.
- Docs are **derived** and regenerable from events and CAS, never hand-edited. They are committed because they are the human-readable view for anyone picking up the repo.

---

## 10. Worker Adapters & Execution Isolation

### 10.1 Uniform execution model

**Every** worker, including API workers, runs as a **child process** that `profiles.build_env(profile)` builds:

1. Start from `{}` (`clean` / `allowlist`) or from a copy of `os.environ` (`inherit`).
2. `allowlist`: copy each `env_allow` variable from the parent if present.
3. Always set a minimal `PATH` and `LANG` if they are absent.
4. If `auth.mode == api_key`, resolve each `secret:` reference and inject it.
5. If `auth.config_home` is set, set the CLI's config-dir variable **[VERIFY name per CLI]**.
6. **Remove every `env_deny` variable last**, in every mode.
7. Add `BATON_PACKET_DIR`, `BATON_RESULT_DIR` and `BATON_WORKSPACE` (if any).

The constructed environment's **variable names** (never values) are logged in the `dispatched` event.

### 10.2 Adapter protocol

```python
class WorkerAdapter(Protocol):
    name: str
    def command(self, profile: WorkerProfile, packet_dir: Path,
                result_dir: Path, workspace: Path | None) -> list[str]: ...
    def postprocess(self, profile, packet_dir, result_dir, proc_result) -> None: ...
```

A shared `spawn()` runs the command with the constructed environment, timeout, `cwd` and optional container or user isolation. It captures stdout and stderr to `~/.baton/logs/` (raw) and a redacted copy to CAS. Adapters never interpret results; intake does.

### 10.3 `litellm_api`

- The command is `python -m baton.worker_runner --adapter litellm_api --profile-json <non-secret profile> …`; the child reads secrets only from its own environment.
- Inside the child: build messages (system = protocol rules; user = `INSTRUCTIONS.md` + inlined inputs), call LiteLLM, and request structured output where supported **[VERIFY per model]**. The model returns `{output, artifacts: {name: content}, notes}`, and the runner writes `result.json` and artifacts, filling in `packet_sha256` itself.
- Inputs too large to inline produce a hard error by default (see §14).

### 10.4 `subprocess_harness` and presets

Runs a headless harness non-interactively. `cwd` is the attempt directory, or the project root for `workspace` steps. The prompt is: *"Read <packet>/INSTRUCTIONS.md and follow it exactly. Write outputs to <result>/."*

Presets (**all flags [VERIFY] against installed `--help`**):
- `claude_code`: non-interactive print mode (`claude -p "<prompt>"`) plus whatever permission flags are needed for unattended file writes.
- `codex`: non-interactive exec mode (`codex exec "<prompt>"`) plus sandbox/approval flags. With `auth.mode: cli_login`, it relies on the stored login; `env_deny` must strip API-key variables (Codex reads `CODEX_API_KEY` in exec mode **[VERIFY]**).
- Others (e.g. Hermes): add a preset only after confirming a non-interactive invocation exists.

### 10.5 `manual`

Prints the packet path and waits. The human (or the Director, relaying for the human) places the result files, then calls `submit_step`. This is useful for physical-world steps.

---

## 11. Director Interface

### 11.1 MCP server (`mcp_server.py`)

- Use the official MCP Python SDK **[VERIFY current package name / server API]**, stdio transport.
- One tool per engine function in §7.6. Tool results are compact JSON with next-action hints, e.g. `{"ready_steps": ["design"], "awaiting_human": [], "lease": "held"}`.
- **Never** expose a tool that lets the Director write step outputs, artifacts or events directly.

Registration (**[VERIFY]** each against current docs):
- Claude Code: project-scoped `.mcp.json`, or `claude mcp add baton -- baton mcp`
- Codex: an `[mcp_servers.baton]` entry with `command`/`args` in Codex config (check whether project-level config is supported)
- Hermes: `hermes mcp add baton --command "baton mcp"`

### 11.2 CLI (`cli.py`)

`baton processes | plan | detect | adopt | baseline | start | status | explain | eligible | begin | dispatch | submit | decide | retry | retriage | revise | consult | resume | lease | record | summary | abandon | trace | doctor | mcp`

- **Quiet by default.** `detect`, `doctor`, `resume` and `status` print a single "ok" line when healthy and detail only for problems. `--verbose` shows everything.
- `baton plan <process>` prints the per-level step and gate table (§5.2).
- `baton trace <run_id>` tails `events.jsonl` in readable form.
- `baton doctor [<profile>]`:
  - Checks that the runtime version matches `.baton/baton.lock`, that every vendored package hash matches, and that the vocabulary version is supported.
  - For each profile (or the named one): builds its exact environment, then runs a trivial no-op task through its adapter (e.g. "write `{"ok":true}` to result.json"). It reports success, duration, which auth mode was effective, and which env var names were present or denied.
  - Reports, per vendored process, which steps currently have **zero** eligible profiles on this machine.

### 11.3 `skills/baton-director/SKILL.md` (Agent Skills format)

```markdown
---
name: baton-director
description: Run, resume, or adopt a multi-step Baton process as Director — route steps to capable workers, dispatch them, handle gates and escalations, explain the process in plain language, route subject-matter questions to a consultant, and keep the human informed. Use whenever the user asks to start, continue, resume, adopt into a project, check, or ask about a Baton process run.
---

# Baton Director

You coordinate. You are the expert on the process, and NOT the expert on any step's subject matter.

## Hard rules
- Never perform step work yourself. Every step's output must come from dispatch_step / submit_step.
- Never compose or edit a context packet. Baton builds packets. If a step cannot start, report the HandoffError's missing inputs to the human.
- Never fabricate a human decision. record_human_decision only with the human's actual words.
- Retry guidance must be additive; never restate or summarize inputs.
- Only choose workers from eligible_workers. Never edit worker profiles, preferences, or the lockfile without the human's instruction.
- Never add, remove, skip or reorder steps or roles. Step inclusion comes only from triage and the recipe; changes go through request_retriage.

## Process questions (you answer these)
- Explain where the run has been, where it is, and where it could go, in plain language, using explain/status/step records. Name the next decision the human will face, if any.
- Base explanations on the record, never on memory or guesswork. If the record doesn't say, say so.

## Subject-matter questions (you route these)
- Never answer subject-matter questions from your own inference, even when asked directly or when you think you know.
- Say so plainly ("I'm not the expert on this, so I'll ask one"), then call consult with references to the relevant recorded work. Choose references by step names, titles and the recipe; do not read the subject content to choose them.
- Relay the consultant's answer faithfully (verbatim when short), labeled as the consultant's. Do not add your own analysis.
- If the answer should change the project, ask the human; only promote_consult with their explicit agreement. Nothing from a consultation affects the run otherwise.
- Do not use consultation content in later routing decisions. After a consultation, prefer resuming from a fresh session (state lives in the record, so nothing is lost).

## Starting, resuming or adopting
1. detect, then doctor. Both are silent when healthy; only interrupt the human if they report a problem.
2. Existing run: resume(run_id). If the lease is held by another Director, report holder and expiry; take over only with the human's approval and a stated reason.
3. Existing project without Baton runs: adopt. Present the proposed baseline as ONE decision (what will be imported, the complexity level and why, which steps will run and which are skipped). Record the human's answer verbatim.

## Loop
1. status(run_id) → ready steps, awaiting_human items, drift warnings.
2. awaiting_human: present question, relevant step record, options; record the answer verbatim.
3. drift warnings: ask the human whether to ingest the edited published file as a revision or leave it outside the process.
4. ready step: eligible_workers → choose (respect preference order unless there is a stated reason not to) → dispatch_step. Mention the worker choice only if the human has asked to see routing, or if it departs from preference.
5. gate failure: if attempts remain, retry_step (may switch to another eligible worker; optional additive guidance); otherwise escalate with reasons.
6. no eligible worker: escalate; explain which capabilities are missing.
7. scope appears to have changed (the human says so, or a consult or gate result suggests it): offer request_retriage.
8. all steps passed: run_summary → present to human; release lease.

## Communicating with the human
- Be quiet when things are healthy. Report at step completion briefly (step, result, published deliverables, next action), and in full only at decisions and escalations.
- Escalations: what failed, why (gate reasons), options, your recommendation about the *process* (retry, switch worker, retriage, consult); never a subject-matter verdict.
```

Also write `skills/baton-worker/SKILL.md` (the §6 protocol rules) for harness workers.

---

## 12. Build Phases & Acceptance Criteria

**Phase 1: Models, vocabulary, loader, neutrality lint.**
✅ A valid example package loads. Ten broken packages are each rejected with a specific error, including one with a `model:` key, one with an unknown capability and one with a vendor string. A profile with an unknown capability is rejected.

**Phase 2: Event store, CAS, state machine, cache rebuild.**
✅ All legal transitions pass and illegal ones raise. Deleting `state.db` and rebuilding from events yields identical status. A tampered `events.jsonl` line fails the hash-chain check.

**Phase 3: Routing.**
✅ Eligibility matrix tests (capabilities, tier, numeric minimums, workspace). Preferences reorder and exclude but never add. Independence constraints for review gates are honored. The empty set leads to escalation.

**Phase 4: Packet builder.**
✅ Deterministic `packet_sha256` for the same state and profile. A missing required input gives a `HandoffError` listing all missing inputs. Ineligible profiles are rejected inside `build_packet`. The packet is read-only.

**Phase 5: Intake + gates (schema, script, human).**
✅ Hash mismatch rejected; schema failure rejected with reasons; script gate pass/fail; human gate blocks until decided; provenance enforced.

**Phase 6: Engine + CLI + manual adapter + publishing + docs.**
✅ A full 3-step toy run done by hand via CLI, including a forced failure and retry. Deliverables appear at the mapped project paths. Editing a published file triggers `drift_detected`, and `baton revise` ingests it as a revision consumed by a later step. `SUMMARY.md` renders.

**Phase 6b: Profiles, environment isolation, doctor.**
✅ Tests prove that `clean` / `allowlist` / `inherit` produce the expected variable *names*, that `env_deny` always wins, and that secret values never appear in any file under `.baton/` (grep test). `baton doctor` succeeds for a fake adapter and reports a missing secret clearly.

**Phase 7: `litellm_api` adapter (child process) + `llm_review`.**
✅ The toy process completes with two different vendors' models. Review-gate failure feedback appears in the next attempt's packet.

**Phase 8: Harness adapters.**
✅ One step runs via headless Claude Code or Codex in `cli_login` mode and another via an `api_key` profile, **in the same run**. `baton doctor` confirms each profile's effective auth mode. Timeouts are handled cleanly.

**Phase 9: Persistence, leases, resume, checkpoint commits.**
✅ Start a run on machine/Director A and checkpoint. Clone fresh on machine/Director B (a different harness), then `doctor` → `resume` → complete. A stale `dispatched` attempt becomes `orphaned` and is retried. A second Director cannot mutate the run without a recorded takeover.

**Phase 10: MCP server + director skill.**
✅ Directors in at least two different harnesses complete the same package with **different worker assignments**, using only MCP tools. A transcript review shows no Director did step work.

**Phase 11: Real processes.** `software-feature` and one non-software package (e.g. `backyard-project`, with manual workers, photo artifacts and human gates).
✅ Both run end-to-end and both pass the neutrality lint. Domain changes required zero runtime code changes.

**Phase 12: Complexity tailoring.** Triage contract, `applies_to` on steps and gates, `skipped` state, `baton plan`, re-triage.
✅ The `backyard-project` recipe at `minor` (e.g. expand a flower bed) and `major` (e.g. build a shed) runs different, correct step sets, visible in `baton plan`. A re-triage from `minor` to `major` after two steps adds future steps only, behind a human gate. Passed steps are untouched.

**Phase 13: Adoption.** `detect`, research step, crosswalk, seeding (`imported`), baseline.
✅ Adopt into a fixture project that has existing specs and code from a different formal process, using a crosswalk. Seeded artifacts validate against step schemas, a seeded artifact that fails its schema is reported (not silently imported), and exactly **one** human decision (the baseline) occurs before normal operation. `detect` on a healthy project prints one line.

**Phase 14: Consultation.** `consult`, follow-ups, promotion, relay and handoff modes.
✅ A consult packet contains only Director-selected references plus the record index, with hashes. A follow-up requesting an extra item includes it. A non-promoted answer is unreachable from any step input; a promoted answer appears as a human decision. Transcript review shows the Director relayed answers without adding subject-matter content.

---

## 13. Testing Strategy

- **Unit:** loader and lint, vocabulary matching, routing, hashing, the state machine, gates, env construction, publishing and drift detection.
- **Property-based** (`hypothesis`): packet determinism; required-input removal; any sequence of legal events rebuilds to the same state.
- **Fake adapter:** scripted good, bad-schema, wrong-hash and blocked results, plus timeouts.
- **Secret-leak test:** run a full toy process with sentinel secret values, then assert the sentinels appear nowhere in the repo working tree or the git history.
- **Golden files:** `INSTRUCTIONS.md`, step records, summary.
- **Live tests** (opt-in env var): real LiteLLM and harness adapters.

---

## 14. Open Decisions (ask the human before choosing)

1. Parallel step dispatch inside Baton vs. leaving parallelism to the Director.
2. Large inputs for API workers: hard error (default) vs. auto-chunking vs. requiring a file-capable worker.
3. No eligible worker: escalate (default) vs. fail the run.
4. Who maintains the capability vocabulary, and the process for proposing new capabilities and denylist entries.
5. Lease duration and renewal interval defaults; whether takeover requires human approval (skill says yes) or is also enforced in the runtime.
6. Automatic checkpoint commits on by default, or opt-in? Commit message format? Commit to the current branch or a dedicated `baton/<run_id>` branch?
7. Git LFS size threshold and whether LFS is required or optional.
8. Optional OpenTelemetry export of events (off by default).
9. Process versioning: runs pin the package version and hash at start (suggested), and upgrading mid-run requires a recorded human decision.
10. Triage approval: always human-gated, or auto-accepted below a recipe-declared level (e.g. `minor` auto-accepts)? Suggested: auto-accept at the lowest level, gate above it; at adoption it is always part of the baseline decision.
11. Seed validation failures: block the baseline, or import with a recorded "nonconforming" flag that forces the step to re-run? Suggested: never import nonconforming; offer to re-run that step instead.
12. Consult handoff mode: which harnesses support spawning a separate session or bot, and how its transcript returns. Ship relay mode first; handoff per harness later.
13. Consultation retention: commit full consult transcripts with the run (suggested, redacted), or only the question and final answer.
14. Research scope limits: maximum files and bytes scanned, and file types considered, before research asks the human to narrow it.

---

## 15. Security & Safety Notes

- Script gates execute commands from process packages, so treat **vendored packages as trusted code**. Review them before vendoring, and keep the lockfile hash check (`baton doctor`) on.
- Harness workers may run with broad permissions. Prefer `isolation: container` or a dedicated user, with the workspace scoped.
- **Everything committed passes `redact.py`.** It strips known secret values (the resolved secrets for the current process) and known token patterns. Raw unredacted logs stay in `~/.baton/logs/`.
- Secrets are never written anywhere under the project tree. The Phase 6b and §13 tests enforce this.
- Packets and results may contain sensitive project data. Treat `.baton/runs/` like the rest of the repo's confidential content.

---

## 16. Definition of Done

- All phases' acceptance criteria pass.
- `README.md` covers install (pinned), registering the MCP server per harness, writing worker profiles, `baton doctor`, authoring a neutral process package, vendoring a package into a project and resuming a run on a new machine.
- One software and one non-software example package ship with the runtime.
- Swapping the Director harness, or any step's worker, requires only local config changes. Recipe changes require no runtime changes.
- Adopting into an existing project with a crosswalk requires exactly one human decision (the baseline), and a healthy project produces no routine prompts.

---

## 17. Adopting Baton in a Project (Vendoring)

This section covers *what files* an adopting project holds. For *how* Baton is brought into an ongoing project (detect, research, triage, seeding, baseline), see §20.

**Principle: commit what the process *is* and what it has *produced*; never commit who runs it or how they pay.**

```
<project>/
├── AGENTS.md                         # pointer: "This repo uses Baton. See .agents/skills/baton-director."
├── .agents/skills/baton-director/    # vendored skill (symlink/copy to .claude/skills/ etc. if a harness needs it)
├── .agents/skills/baton-worker/
├── .mcp.json                         # project MCP registration (no secrets) [VERIFY per harness]
├── .baton/
│   ├── baton.lock                    # runtime version, vocabulary version, package hashes
│   ├── project.yaml                  # path mapping + project vars (test_command, etc.)
│   ├── preferences.yaml              # optional, non-secret routing preferences
│   ├── processes/<id>@<version>/     # vendored, pinned process packages
│   ├── runs/<run_id>/                # events.jsonl, cas/, steps/, docs/
│   ├── workers.local.yaml            # GITIGNORED
│   └── cache/                        # GITIGNORED (SQLite)
├── docs/specs/ docs/design/ plans/ cad/ …   # published deliverables (§19)
└── .gitattributes                    # LFS rules for .baton/runs/**/cas large blobs + binary deliverables
```

| Item | Commit? |
|---|---|
| Process packages (pinned) + `baton.lock` | ✅ |
| Skills, `AGENTS.md` pointer, MCP project config | ✅ |
| `project.yaml`, `preferences.yaml` | ✅ |
| `.baton/runs/**` (events, CAS, packets, results, docs) | ✅ (redacted) |
| Published deliverables at project paths | ✅ |
| Baton runtime source | ❌ install it pinned (`uv tool install baton==X` or equivalent); vendor only for offline use or a fork |
| Worker profiles (`~/.baton/workers.yaml`, `.baton/workers.local.yaml`) | ❌ |
| Secrets, raw logs, SQLite cache | ❌ |

`baton init` creates this structure, the `.gitignore` entries and the `.gitattributes` LFS rules. `baton vendor <package-dir>` copies a package, runs the neutrality lint and records its hash in the lockfile.

---

## 18. Run Persistence & Handoff Between Directors

### 18.1 Goal

Any capable Director, on any machine, can clone the repo and continue a run reliably from the last checkpoint.

### 18.2 Checkpoint commits (`gitops.py`)

- After `step_passed` + publish, `human_decision`, `step_escalated` and `run_completed`, the runtime stages `.baton/runs/<run_id>/` plus the published deliverables, then commits with a structured message, e.g. `baton(<run_id>): design passed [attempt 1, worker openai-api-strong]`.
- A `checkpoint_committed` event (with the commit SHA) is appended **in the next commit**, since the SHA isn't known until after committing. Alternatively, record SHAs only in git and let `resume` read `git log`. Choose one and document it.
- Workspace steps (code) commit their own changes; their `commit_sha` is recorded in the step output, and the checkpoint commit follows.
- Never commit with uncommitted unrelated changes present; refuse and report instead (or use a dedicated branch; see §14).

### 18.3 Run lease (`lease.py`)

- A lease is an event: `lease_claimed {director_id, harness, host, expires_at}`. Mutating engine calls require a valid lease held by the caller.
- `renew_lease` extends it. `release_lease` on completion or pause.
- If an unexpired lease is held by someone else, mutation is refused. `take_over_lease(reason)` records the takeover; the director skill requires human approval first.
- Leases travel via git, so they coordinate *sequential* handoff, not real-time concurrency. Two Directors racing on unsynced clones will be caught at merge by the event hash chain. `resume` refuses a run whose chain has diverged and asks for human resolution.

### 18.4 `resume(run_id)`

1. Verify the event hash chain and every CAS blob's hash.
2. Rebuild the SQLite cache.
3. Any attempt in `dispatched` or `submitted` with no completed intake becomes `attempt_orphaned` (retryable).
4. Re-check published deliverables for drift.
5. Claim the lease (or report the holder).
6. Return status and ready steps.

### 18.5 What a new machine still needs (by design)

The pinned runtime (per the lockfile) and its own worker profiles that satisfy the steps' `requires`. `baton doctor` verifies both before the Director touches the run.

**Prescribed pickup workflow:** clone → install pinned runtime → write or confirm profiles → `baton doctor` → `baton resume <run_id>` → continue.

---

## 19. Publishing Deliverables

### 19.1 Declaration (in the neutral package)

```yaml
artifacts:
  - name: design_doc
    publish: { to: "{{ paths.designs }}/{{ run.slug }}-design.md" }
```

Packages reference only **logical** path keys. The project maps them in `.baton/project.yaml`:

```yaml
paths:
  specs: docs/specs
  designs: docs/design
  plans: plans
  drawings: cad/drawings
project:
  test_command: "pytest -q"
run_slug: "{{ run.inputs.short_name | slugify }}"
```

A missing path key is a **start-time error** (`start_run` refuses), so recipes fail fast in a project that hasn't mapped them.

### 19.2 Publishing (`publish.py`)

On `step_passed`, for each artifact with `publish`:
1. Render the target path and refuse anything outside the project root.
2. If the target exists and **was not** last written by Baton with the same hash, treat it as a conflict. Do not overwrite; escalate to the human (overwrite / keep / publish to an alternate name).
3. Copy from CAS, then append `artifact_published {step, artifact, path, sha256}`.

Workspace steps (source code) don't use `publish`; their output *is* the project tree, recorded via `commit_sha`.

### 19.3 Two copies, two roles; drift handling

- **CAS copy:** the immutable record. **Downstream steps always consume this**, which keeps the reliable-handoff guarantee.
- **Published copy:** the living file for humans and other tools.
- `status` / `resume` compare each published file's current hash with its `artifact_published` hash. A mismatch gives `drift_detected`.
- On drift, the human chooses:
  - **Leave it outside the process:** downstream steps keep using the CAS version, and the drift is noted in docs.
  - **Ingest it as a revision:** `ingest_human_revision` stores the edited file in CAS and appends `human_revision_ingested`. Steps that declare `human_revision.<step>.<artifact>` inputs, or any **not-yet-started** dependent step if the human so chooses, receive the revised version. Already-passed downstream steps are flagged as possibly stale, and the human decides whether to re-run them.

### 19.4 Large and binary deliverables

Drawings, photos and CAD files are tracked by Git LFS (rules set by `baton init`), so CAS and published copies cost only pointers in normal git history.

---

## 20. Adoption, Complexity Tailoring and Consultation

### 20.1 Goal and shape

Baton must drop into **ongoing projects**, including ones already run under a different formal process, with the least possible friction, and then stay out of the way. Every recipe must also scale its formality to the work: expanding a flower bed and building a shed are the same recipe at different complexity levels.

None of this adds a new subsystem. Research and triage are ordinary steps; detection is a deterministic check; consultation reuses the packet and worker machinery. The flow:

```
detect (deterministic, silent) ─► doctor (silent if healthy)
      │
      ├─ existing run ............................► resume ─► continue
      └─ project without Baton runs ─► research ─► triage ─► baseline (ONE human decision) ─► continue
new work in an adopted project ..................► triage ─► continue
```

### 20.2 `detect`: situation recognition (no AI)

`detect()` inspects the filesystem, git and the event logs and returns one situation plus a recommended next action. It is deterministic and fast.

| Situation | Signals | Next action |
|---|---|---|
| `not_adopted` | no `.baton/` | `adopt` (or `start` for brand-new work) |
| `idle` | `.baton/` present, no active run | ready for `start` |
| `active_here` | active run, lease held by this Director or expired | `resume` |
| `active_elsewhere` | unexpired lease held by another Director | report holder; takeover needs human approval |
| `orphaned_attempts` | attempts left `dispatched`/`submitted` | `resume` (marks them orphaned, retryable) |
| `diverged` | event hash chain conflict | stop; human resolves |
| `drift` | published deliverables edited outside Baton | ask human: ingest or leave (§19.3) |
| `machine_unready` | `doctor` reports a problem | fix profiles/auth first |

Healthy situations (`idle`, `active_here` with no orphans or drift) print a single line. `situation_detected` is recorded only when a run exists.

### 20.3 Research (adoption only)

Research gathers **evidence**; it does not judge. It runs as a built-in first step of an adoption run, before the recipe's triage.

- **Scope is set by the recipe, not the project.** Research answers one question: *which of this recipe's step outputs and artifacts already exist here, where, and in what state?* It also reports existing agent configuration, candidate path mappings and candidate project commands. It is not a general audit.
- **Read-only.** The worker needs `workspace_read` (plus `structured_output`, `technical_reasoning`) and runs with the project root as a read-only workspace where the harness supports it [VERIFY per harness]. A built-in gate confirms deterministically that the working tree is unchanged afterward.
- **Output** (`research.findings`, schema shipped with the runtime):
  - `evidence[]`: `{path, sha256, kind, maps_to?, confidence, notes}`, where `maps_to` is a step artifact or output reference
  - `proposed_seeds[]`: `{step, artifacts{name: path}, output_draft}`. For seeds, research drafts the step's structured `output` from the existing artifact; it is validated and attested at baseline, never trusted as-is.
  - `agent_config`: existing `AGENTS.md`, `CLAUDE.md`, skills folders, MCP config (so `init` merges rather than overwrites)
  - `path_candidates`, `command_candidates`, `gaps[]`
- **Crosswalks make research near-deterministic.** For projects that ran under a known prior process, a crosswalk maps that process's artifacts to recipe steps:

  ```yaml
  # .baton/crosswalks/acme-eng-v3--software-feature.yaml (project-local or shipped with a recipe)
  from_process: acme-eng-v3
  to_process: software-feature@1
  artifacts:
    - { match: "docs/prd/*.md",  to: steps.requirements.artifacts.requirements_doc }
    - { match: "docs/tdd/*.md",  to: steps.design.artifacts.design_doc }
  completion_signals:
    - { step: requirements, evidence: "file docs/prd/<slug>.md contains 'Status: Approved'" }
  ```

  With a crosswalk, research mostly confirms matches and fills structured outputs, instead of interpreting the project from scratch. Writing one crosswalk per prior process is the single biggest friction reducer for adoption. Crosswalks contain no model or vendor references and pass the neutrality lint.

### 20.4 Triage and complexity levels

- **The recipe owns its scale** (`complexity.levels`, lowest to highest) and its triage criteria (in the triage prompt). A backyard recipe and a software recipe judge complexity differently; the runtime only applies the result.
- **Triage output contract:** `{level, reasons[], signals{...}}`, where `level` is one of the recipe's levels. Recorded as `complexity_set`.
- **Deterministic inclusion.** After triage passes, the runtime marks every step whose `applies_to` excludes the level as `skipped` (`step_skipped`, with the level as reason), and disables level-scoped gates the same way. Steps without `applies_to` always run. The Director has no say in this.
- **Re-triage.** Scope changes (the flower bed becomes a patio). `request_retriage(reason)` runs triage again with the run's current record as input, then a human gate. On approval (`retriage_applied`), steps not yet started are re-evaluated: newly applicable steps go from `skipped` to `blocked_on_deps`, newly excluded ones to `skipped`. **Passed and imported steps are never changed**; if the new level would have run a step differently, its record is flagged "pre-retriage" for the human's awareness.
- **Keep levels few.** Three is a sensible default. Each level should differ in steps or gates the human would actually notice.

### 20.5 Seeding: importing existing work

A seed turns existing work into a step result without re-doing it.

- A seeded step goes to `imported` (`step_imported`), with `worker = human` and the human's attestation from the baseline decision.
- **Same contract as any result:** seeded artifacts enter CAS with hashes, and the seed's `output` must validate against the step's output schema. A seed that fails validation is **not** imported; the baseline offers to run that step instead.
- Gates that can run on a seed (schema, script) do run. LLM-review and human gates are satisfied by the baseline attestation and recorded as such.
- Downstream steps consume imported results exactly like passed ones, so the handoff guarantee holds from the first Baton-executed step onward.

### 20.6 Consultation

Subject-matter questions always go to a consult worker. The Director's value is knowing **where** the relevant knowledge lives; the consultant's value is understanding **what** it means.

- **The Director selects, the runtime assembles.** `consult(run_id, question, refs, mode)`. The Director chooses `refs` by name from the record and recipe (e.g. `steps.design.artifacts.design_doc`, `steps.requirements.output`, `human.d_014`, published deliverables, and for consults only `project:<path-or-glob>`) without reading their content. The runtime resolves them into a hashed consult packet.
- **Plain provenance, not Baton.** Each item carries a neutral label (what it is, which step produced it, its standing: "approved design, attempt 2", "edited by a human after publishing", "imported from prior process"). The consultant needs no knowledge of Baton.
- **Safety net.** The packet includes an index of everything else on record (titles and references only). The answer schema is `{answer, confidence, sources_used[], requested_refs[], suggests_retriage}`. If `requested_refs` is non-empty, the Director approves a follow-up (or asks the human), and `consult_followup` includes those items plus the prior turns.
- **Routing.** The consultant is chosen by `eligible_workers` against the recipe's `consult_requires`, or the vocabulary default. No independence constraint.
- **Isolation from the run.** Consult answers are recorded (`consult_requested` / `consult_answered`, transcript in `.baton/runs/<id>/consults/`) but are **not** referenceable as step inputs. They affect the run only through `promote_consult(as: decision | revision)` with the human's explicit agreement (`consult_promoted`).
- **Keeping subject matter out of the Director.** The Director relays answers faithfully without adding analysis and does not use them in routing. Because all state lives in the record, the Director can resume in a fresh session after a consultation at no cost; the skill recommends this. Leakage is minimized, not eliminated: the relayed answer passes through the Director's context once.
- **Modes.** `relay` (default): the Director is the go-between, multi-turn via follow-ups. `handoff` (optional, per harness): the consult adapter opens a separate session or bot the user talks to directly, and its transcript or summary is recorded as the answer when the session closes. Baton does not care which mode was used.
- **Consultation is built in, not a step.** It sits outside the step graph, cannot satisfy gates, and requires no recipe change. This is why the Director never needs to add roles or steps.

### 20.7 The baseline

The baseline ends adoption and is the only human decision it requires.

- **Contents**, presented by the Director as one decision: proposed `project.yaml` path mappings and commands; agent-config merges; seeds to import (each with source path and the step it satisfies); the complexity level with triage reasons; the resulting plan (steps that will run, steps skipped); known gaps.
- **Blameless.** The baseline records what exists, what is assumed and what is missing. Gaps are listed as gaps, not failures of the prior process.
- **Applying it** (`establish_baseline`): writes `project.yaml` and config merges, imports seeds, applies the complexity level, records `baseline_established` with the human's verbatim decision, and makes a checkpoint commit. From here the run is ordinary Baton.
- The human may edit any part (drop a seed, change a path, override the level); the edited version is what gets applied and recorded.

### 20.8 Explaining the process

`explain(run_id, scope?)` returns **process facts only**, assembled deterministically from events, the recipe and the plan: completed, imported and skipped steps with outcomes (status, attempts, gate results, decisions); the current position and any pending decision; remaining steps at the current level; steps that would apply at other levels; and possible branches (retry, switch worker, escalate, re-triage). The Director turns this into plain language on request. Because `explain` contains no subject content, the Director can answer "where are we and what happens next?" fully without loading any subject matter.

### 20.9 What this deliberately does not add

- No Director-created roles, steps or process edits.
- No AI in situation detection.
- No expression language for step inclusion (only `applies_to` level lists).
- No project-wide audit during research.
- No second source of truth: research findings, triage, seeds, consultations and the baseline are all ordinary events and CAS blobs in the run.
