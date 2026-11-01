# Baton: Build Guide for a Vendor-Neutral, Director-Led Multi-Step Process Framework

> **Revision 3.** Informed by a review of `rowama/eng-process` (the owner's existing engineering process) and its use on `rowama/mmbridge`. Adds: projects with **concurrent work items** (runs) instead of a single project phase; **sub-processes** (`foreach` / `repeat_until`) for cross-worker iteration; **async execution and liveness** (completion hooks, running markers, effort timeouts, failure classification); `revise_step` within a work item; **findings-based reviews**, advisory gates and waivers; cross-step reviewer independence; protected files; PATH handling and gate preflight; **SMEs by subject** (project, platform, process) generalizing consultation; a project-level **platform area**; the owner communication contract; action permissions; Windows notes; `baton check`. New §21–§26; supporting changes throughout. The owner's eng-process will be ported as a Baton recipe; its crosswalk is a separate guide.
>
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
| **Subject-matter consultation** | Questions go to a subject-matter expert (SME) worker by subject (project, platform, process) with a runtime-assembled packet. The Director routes; it never answers from its own inference. |
| **Invisible when healthy** | Checks, detection and resume are silent unless something is wrong. Human attention is spent only at gates, escalations and the adoption baseline. |
| **Concurrent work items** | A project holds many runs, one per work item (feature, increment, fix), each at its own step. The project never "steps back"; work items move independently (§21). |
| **Cross-worker iteration** | Sub-processes repeat a group of steps per item (`foreach`, e.g. per slice) or until a gate passes (`repeat_until`), bounded and enforced by the runtime (§22). |
| **Long-running work** | Dispatch is asynchronous. The runtime tracks liveness, wakes the Director on completion, enforces effort-based timeouts and classifies failures (§23). |

### Non-goals

- Not an agent framework. Baton does not run an LLM loop itself; Directors and Workers do. Iteration *inside* a worker (e.g. a coding agent looping until its tests pass) is the worker's own business; Baton gives it the exit criteria and a budget, and models only iteration *across* workers.
- Not a general scheduler or queue. Steps run when the Director dispatches them; the runtime only supervises dispatched work and wakes the Director when it ends.
- No GUI. Use the CLI and Markdown outputs.
- No backlog or idea management. Owners keep notes and backlogs in tools of their choice.

---

## 2. Roles

- **Owner (human):** owns goals, approves human gates, answers escalations. Talks to the Director (and may be contacted by SMEs through it).
- **Director:** any harness loaded with the `baton-director` skill that can reach the Baton runtime: by shell (CLI) on the runtime host, or by MCP. It is an expert at *running processes, routing work and communicating*, not at any step's domain. It **never performs step work itself**.
- **Baton runtime:** deterministic Python, installed as a pinned tool **on the host where workers run** (the "runtime host"). The project repo's event logs are the source of truth.
- **Worker:** executes exactly one step attempt under one **worker profile**. It receives a packet directory and must produce a result directory. It is stateless with respect to the run.
- **SMEs (subject-matter experts):** workers consulted by subject (§25). Three subjects are built in: **project** (the work's domain), **platform** (development and deployment infrastructure: an IT-type expert such as the owner's platform agent) and **process** (Baton itself: introspection and process improvement). A platform SME may be an agent that interacts with workers, the Director and the owner to resolve infrastructure issues.

**Hierarchy:** a **project** (one repo) contains many **runs**, one per **work item** (a feature, an increment, a fix). A run follows one recipe through its **steps**; some steps are **sub-processes** that repeat. Views: the project board (runs × current position), a run, a step.

**Typical topology:** the runtime, the repo and CLI-harness workers live on one machine (the runtime host). The Director may run elsewhere (e.g. a cloud chat agent) as long as it can execute `baton` there by shell or reach its MCP server. Because a remote Director's turn can end while work is still running, the runtime wakes it through a completion hook (§23).

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
9. **CLI and MCP are equal Director interfaces.** Both call the same Python core. A Director with shell access to the runtime host uses the CLI; MCP is for harnesses that prefer tools. Neither is privileged.
10. **Invisible when healthy.** Baton earns its place only if the human isn't babysitting it. Every check reports nothing when there is nothing to report, and every human touchpoint must be a real decision (a gate, an escalation, the adoption baseline), never a confirmation of routine machinery.
11. **The Director is the process expert, not the subject-matter expert.** It explains the run in plain language (where it has been, where it is, where it could go) from the record. For subject matter it points to recorded work or routes the question to a consult worker. It never answers subject-matter questions from its own inference, and the process never changes based on anything held only in the Director's context.
12. **Formality scales with complexity, decided once and recorded.** Triage is a normal step whose output picks the complexity level. The runtime applies it; the Director never decides which steps to skip.
13. **The Director never modifies a process.** It does not add, remove or reorder steps or roles. Variability comes only from the recipe's own complexity levels, sub-process expansion and the built-in SME consultation.
14. **Work items move, projects don't.** Each work item is its own run with its own position. Correcting an earlier step is local to one run (`revise_step`, §21.3); nothing ever rewinds the project.
15. **Recipes hold the process; the runtime holds the machinery.** Hooks, process IDs, timeouts, liveness, PATH handling, permissions and platform facts are runtime and project configuration. A recipe never mentions them, so it stays portable.
16. **Async by default.** Every dispatch may outlive the Director's session. Completion is owned by the runtime, which records it and wakes whoever must act next (§23).
17. **Structured over parsed.** Reviewers and workers return schema-validated JSON (findings, verdicts, outputs). Nothing important is scraped from free text.
18. **Value added versus owner effort.** Every feature must save the owner more effort than it costs. Generalizing a mechanism is preferred to adding a parallel one (e.g. platform and process help are SME subjects, not new subsystems).

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
│   ├── findings.py        # findings-based review gates, dispositions, waivers (§24)
│   ├── subprocess_expand.py  # foreach / repeat_until expansion of step groups (§22)
│   ├── project.py         # project board: runs, work items, concurrency (§21)
│   ├── supervisor.py      # async dispatch, running markers, timeouts, completion hooks (§23)
│   ├── classify.py        # failure classification: subject vs platform vs process (§23.5)
│   ├── sme.py             # SME consultation by subject (§25)
│   ├── platform_area.py   # project-level platform facts + incidents (§25.3)
│   ├── permissions.py     # action permissions: push, tag, merge, deploy (§26.2)
│   ├── check.py           # `baton check` for CI / pre-commit (§26.4)
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
├── hooks.yaml             # machine-level completion hooks (e.g. wake a remote Director) (§23.3)
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

sme:                               # optional; per-subject SME requirements (§25). Defaults live in the vocabulary file.
  project:
    capabilities: [long_form_writing, technical_reasoning, workspace_read]
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
      - type: findings_review            # §24: severities + dispositions, not pass/fail
        advisory: true                   # records findings; never blocks by itself
        reviewer_requires:
          capabilities: [structured_output, technical_reasoning]
          tier: strong
        independence: { from_step: design, level: different_vendor }   # different_model | different_vendor
        rubric: prompts/design_review_rubric.md

  - id: plan
    title: Plan vertical slices
    depends_on: [design]
    applies_to: [standard, major]
    requires:
      capabilities: [structured_output, long_form_writing, technical_reasoning, workspace_read]
      tier: strong
    workspace: project_root
    workspace_mode: read
    prompt: prompts/plan.md
    inputs:
      - { name: requirements_doc, from: steps.requirements.artifacts.requirements_doc, required: true }
      - { name: design_doc,       from: steps.design.artifacts.design_doc,             required: true }
    output_schema: schemas/plan_out.json   # includes slices: [{id, title, outcome, criteria[], effort}]
    gates:
      - type: schema
      - type: findings_review            # gating: no open critical/high findings
        block_on: [critical, high]
        reviewer_requires: { capabilities: [structured_output, technical_reasoning], tier: strong }
        independence: { from_step: plan, level: different_vendor }
        rubric: prompts/plan_review_rubric.md
      - type: human
        prompt: "Approve the plan and its slices?"

  - id: slices                           # a sub-process (§22)
    title: Deliver each slice
    depends_on: [triage, requirements, design, plan]   # skipped dependencies count as satisfied
    foreach: steps.plan.output.slices    # one instance per slice, in order
    foreach_if_source_skipped: once      # minor work: run once with item = run.inputs
    concurrency: 1                       # WIP limit
    steps:
      - id: implement
        effort_from: item.effort         # S | M | L sets the timeout band (§23.4)
        requires:
          capabilities: [tool_use, file_write, shell, code_exec, repo_workspace]
          tier: strong
        workspace: project_root
        protect: ["tests/acceptance/specs/**"]   # §24.4: worker must not modify these
        prompt: prompts/implement.md
        inputs:
          - { name: slice,            from: item,                                          required: true }
          - { name: feature_request,  from: run.inputs.feature_request,                    required: true }
          - { name: design_doc,       from: steps.design.artifacts.design_doc,             required: true }
          - { name: prior_findings,   from: group.previous_iteration.findings,             required: false }
          # "required" applies only when the source step is included at the run's level (§20.4)
        output_schema: schemas/implement_out.json   # must include commit_sha
        gates:
          - type: schema
          - type: script
            run: "{{ project.test_command }}"
            cwd: project_root
            timeout_s: 900
      - id: code_review
        depends_on: [implement]
        requires: { capabilities: [structured_output, technical_reasoning, workspace_read], tier: strong }
        workspace: project_root
        workspace_mode: read
        prompt: prompts/code_review.md
        inputs:
          - { name: slice,  from: item,                         required: true }
          - { name: commit, from: group.steps.implement.output, required: true }
        output_schema: schemas/findings.json       # fixed findings schema (§24.1)
        independence: { from_step: implement, level: different_vendor }
        gates:
          - type: findings                         # this step's own output is a findings list
            block_on: [critical, high]
      - id: accept
        depends_on: [code_review]
        requires: { capabilities: [human_judgment] }   # only human profiles have it: owner's manual verification
        prompt: prompts/slice_acceptance.md            # lists only steps runnable against what is live now (§26.1)
        inputs:
          - { name: slice,   from: item,                           required: true }
          - { name: review,  from: group.steps.code_review.output, required: true }
        output_schema: schemas/acceptance_out.json
    repeat_until: group.steps.code_review.gates.passed   # re-run implement with the findings until clean
    max_iterations: 3
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
| `item` / `item.<json.path>` | Inside a `foreach` sub-process: the current item (§22) |
| `group.steps.<id>.output` / `.artifacts.<name>` | Inside a sub-process: a sibling step's result in the **same** instance and iteration |
| `group.previous_iteration.findings` | Inside a `repeat_until` sub-process: open findings from the previous iteration (§22.3) |
| `platform.facts` | The project's platform facts file (§25.3) |

`steps.<id>.*` references resolve equally to a **passed** or an **imported** (seeded) step (§20.5). Steps outside a sub-process may reference a sub-process only as a whole (`steps.<group>.outputs`, the list of each instance's final outputs). SME answers are deliberately **not** referenceable; they enter a run only after promotion to a human decision or revision (§25.2).

**Load-time validation** (in `process_loader.py`):
- Every `steps.<id>` reference names an ancestor in `depends_on`, including transitive ancestors.
- No cycles. Every file path exists. Every schema is valid JSON Schema (Draft 2020-12).
- Every gate `type` is known, and every `requires` / `reviewer_requires` / `sme.*` uses only names from the declared `capabilities_vocab`.
- Sub-processes: `foreach` names an ancestor step's output path whose schema is an array; `repeat_until` references only gates of steps inside the group; `max_iterations` is set (1–10) whenever `repeat_until` is; `group.*` and `item` references appear only inside a group; groups do not nest more than one level (§22.5).
- `independence.from_step` names the step itself or an ancestor (in the same group, if inside one).
- `protect` globs are relative to the workspace and appear only on workspace steps.
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
  loopback_network:    "Can bind and connect to localhost ports (needed to run socket/integration tests)"
  human_judgment:      "A person: manual verification, acceptance, physical-world work"
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
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, loopback_network, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }
  env_mode: allowlist
  env_allow: [HOME, USERPROFILE, APPDATA, LOCALAPPDATA, LANG, TERM]
  env_deny:  [ANTHROPIC_API_KEY]
  executable: claude
  path:
    search: [nvm]                    # resolve the CLI from nvm node dirs if not on the base PATH (§5.5.1)
    prepend: []
  args:
    write: ["--permission-mode", "bypassPermissions"]   # [VERIFY] headless runs must not stall on approvals
    read:  ["--permission-mode", "plan"]                # [VERIFY] read-only workspace steps

owner:
  adapter: manual
  vendor: human
  person: owner                      # who to contact (§26.1); a human profile per person
  capabilities: [human_judgment, long_form_writing, vision, file_write]
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

| `executable` | name or absolute path | The CLI to run for harness adapters. |
| `path.search` | list: `nvm`, `pyenv`, `asdf`, explicit dirs | Where to look for `executable` when it is not on the base PATH (§5.5.1). |
| `path.prepend` | list of dirs | Always prepended to the child PATH (`~` expanded; no `$VAR` expansion). |
| `args.write` / `args.read` | arg lists | Adapter args for workspace-writing vs read-only steps (permission/sandbox modes). `doctor` verifies gate commands actually run under them (§11.2). |
| `capabilities` | vocabulary names | Must be **true on this machine**. E.g. a sandboxed reviewer that cannot bind localhost must not claim `loopback_network`; its test results are then treated as partial (§24.1). |

**Credential storage caveat [VERIFY]:** CLI logins are usually files under the user's home directory (e.g. Codex keeps its login under `~/.codex/`). Some CLIs may use the OS keychain on some platforms, which can require the user's login session rather than any env var. `baton doctor` (§11.2) exists to catch this per profile, per machine.

#### 5.5.1 PATH resolution (why it is explicit)

CLI harnesses installed through version managers (e.g. Node via nvm) live in per-version directories that a non-login, non-interactive shell does not have on PATH. A clean environment makes this worse. Resolution, in order, recorded in the `dispatched` event:
1. `executable` is an absolute path → use it.
2. Found on the **base PATH**: the profile's `path.prepend` + a minimal system PATH (`/usr/local/bin:/usr/bin:/bin`, or the Windows system dirs).
3. Each `path.search` source: `nvm` → `$NVM_DIR/versions/node/*/bin` and `~/.nvm/versions/node/*/bin`, newest version first; others analogously. The first dir containing the executable is prepended.
4. Not found → the dispatch fails with `executable_not_found`, classified as a **platform** failure (§23.5), naming every location searched.

Platform facts discovered here (e.g. "codex lives under nvm v22") may be recorded in the project's platform area (§25.3) so they are visible to every Director and SME.

---

## 6. The Communication Protocol

### 6.1 Packet (Baton → Worker)

```
.baton/runs/<run_id>/steps/<step_path>/attempt-<n>/packet/
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
  "step_path": "design",
  "instance": null,
  "iteration": null,
  "attempt": 1,
  "effort": "M",
  "deadline": "2026-11-01T22:00:00Z",
  "exit_criteria": ["…rendered from the step's gates and output contract…"],
  "protected_paths": [],
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
- Inside a sub-process, `step_path` is `<group>/<instance>/<iteration>/<step>` (e.g. `slices/s2/i1/implement`); `instance` is the `foreach` item id and `iteration` the `repeat_until` count (§22).
- `exit_criteria` tells the worker what "done" means (its own DoD): every gate it will face and the output contract. Iteration *inside* the worker toward these criteria is the worker's business; `deadline` (from effort, §23.4) bounds it.

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
blocked_on_deps → ready → dispatched → running → submitted → verifying → passed → published
                     ↑          │          │                       │
                     │          │          ├→ timed_out ───────────┤ (classified, §23.5)
                     │          └──────────┴→ orphaned (on resume) ┤
                     └──── retry (attempt+1) ◄─────────────────────┤ failed (attempts < max)
                                                                   └→ escalated (attempts ≥ max | status=blocked | no eligible worker | platform failure)
escalated → ready (after human decision) | abandoned
awaiting_human  (human gate pending) → verifying
blocked_on_deps → skipped    (not applicable at the run's complexity level; set by the runtime after triage)
blocked_on_deps → imported   (seeded from existing work at adoption; §20.5)
skipped → blocked_on_deps    (only via an approved re-triage; §20.4)
passed | imported → superseded  (via revise_step: a new attempt replaces it; §21.3)
passed | imported → stale       (an upstream step in the same run was revised; must re-pass or be re-approved)
stale → ready | passed          (re-run, or human re-approval recorded)
```

`skipped` and `imported` both satisfy `depends_on`; `stale` and `superseded` do **not**. Inputs referencing a `skipped` step are omitted and listed in the manifest as `not_applicable`; their `required` flag does not apply.

`dispatched` means the worker process was started; `running` means the supervisor has confirmed it alive (§23.2). Sub-process groups have their own aggregate state (§22.4).

Only `engine.py` performs transitions; each one appends exactly one event. Illegal transitions raise errors. Test every edge.

### 7.2 Store (`store.py`): events are the source of truth

- **Run directory:** `<project>/.baton/runs/<run_id>/` containing `events.jsonl`, `cas/`, `steps/` and `docs/`.
- **`events.jsonl`** is append-only and is the authoritative state. Each event has `seq` (monotonic), `ts`, `run_id`, `step_id`, `attempt`, `type`, `actor` (director id / runtime / human) and `data`. Each line also carries `prev_sha256` (hash chain), which detects tampering or bad merges.
- **CAS:** `.baton/runs/<run_id>/cas/<sha[:2]>/<sha>`, written atomically (temp file plus `os.replace`). Binaries over a configurable size are expected to be tracked by Git LFS (§17).
- **SQLite** (`.baton/cache/state.db`, gitignored) is a **derived cache** for fast queries. `store.rebuild(run_id)` replays events to regenerate it. On any mismatch, events win.
- Event types: `run_started`, `lease_claimed`, `lease_renewed`, `lease_taken_over`, `lease_released`, `step_ready`, `worker_selected`, `packet_built`, `dispatched`, `result_submitted`, `result_rejected`, `gate_passed`, `gate_failed`, `step_passed`, `artifact_published`, `drift_detected`, `human_revision_ingested`, `step_escalated`, `attempt_orphaned`, `human_decision`, `checkpoint_committed`, `run_completed`, `run_abandoned`, plus (§20) `situation_detected`, `research_recorded`, `complexity_set`, `step_skipped`, `step_imported`, `retriage_requested`, `retriage_applied`, `baseline_established`, plus (Rev 3) `group_expanded`, `iteration_started`, `iteration_limit_reached`, `step_running`, `heartbeat`, `step_timed_out`, `failure_classified`, `completion_hook_fired`, `completion_hook_failed`, `step_revised`, `step_stale`, `findings_recorded`, `finding_dispositioned`, `gate_waived`, `protected_path_modified`, `sme_requested`, `sme_answered`, `sme_promoted`, `platform_fact_recorded`, `platform_incident_opened`, `platform_incident_resolved`, `process_feedback`, `step_skip_recorded`, `permission_used`, `permission_requested`.

Project-level events (platform area, process feedback) live in `.baton/project/events.jsonl` with the same format and hash chain (§21.1).

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

**Independence.** A review gate (`reviewer_requires`) or a reviewing step selects only profiles that satisfy its `independence` constraint relative to the worker that produced the referenced step's **current** result: `independence.from_step` (default: the step itself) and `level` (`different_profile` | `different_model` | `different_vendor`). E.g. a code review can require a different vendor than whoever ran `implement` in the same slice instance. Self-review is refused unless a human decision waives it (§24.3).

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
| `dispatch_step(run_id, step_id, worker, wait=false)` | `begin_step` + spawn worker under the supervisor; returns immediately with a dispatch id unless `wait` (§23). Intake runs automatically when the worker exits. |
| `wait(run_id, dispatch_id?, timeout?)` | Block until a dispatch completes or the timeout passes (for Directors that can stay attached) |
| `board(project?)` | All runs: work item, recipe, position, pending decisions, running work (§21.2) |
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
| `ask_sme(subject, question, refs, run_id?, mode)` | SME consultation by subject (`project` / `platform` / `process`); runtime assembles the packet from the Director's references (§25) |
| `sme_followup(consult_id, question, extra_refs?)` | Next turn of a consultation |
| `promote_sme(consult_id, as, note)` | Turn an SME answer into a human decision, revision or platform fact, with human approval |
| `revise_step(run_id, step_path, reason)` | Correct an earlier step within one work item: new attempt, downstream steps in that run marked `stale` (§21.3) |
| `disposition_finding(run_id, step_path, finding_id, disposition, evidence?)` | Record `fixed` / `accepted-risk` / `rejected` on a review finding (§24.2) |
| `waive_gate(run_id, step_path, gate, reason)` | Human-approved waiver of one gate occurrence (§24.3) |
| `platform_fact / platform_incident(…)` | Record platform facts and incidents at project level (§25.3) |
| `process_feedback(kind, text, run_id?)` | Record friction or a skipped step for the process SME (§25.4) |
| `doctor(profile?)` | Profile health check (§11.2) |
| `check()` | Non-interactive consistency check for CI / pre-commit (§26.4) |

Every mutating call on a run requires the caller to hold **that run's** lease. Project-level calls (platform, process feedback) use a short project-level lock instead.

---

## 8. Verification Gates (`gates.py`)

| Type | Behaviour | Pass condition |
|---|---|---|
| `schema` | Done at intake; recorded as a gate for the audit trail | Valid |
| `script` | Runs a command with `cwd`/`timeout_s` under a clean env; output is redacted, then stored in CAS | Exit 0 |
| `llm_review` | Builds a **review packet** (step inputs + result + rubric) and dispatches it to a reviewer chosen per §7.3. Fixed reviewer schema: `{verdict: pass\|fail, reasons: [str]}` | `verdict == pass` |
| `findings_review` | Like `llm_review`, but the reviewer returns a **findings list** (§24.1); dispositions are recorded per finding | No finding at a `block_on` severity is `open` (§24.2) |
| `findings` | For a step whose own output is a findings list (e.g. a code-review step) | Same rule as `findings_review` |
| `protected` | Implicit on workspace steps with `protect:`: hashes the protected paths before and after the run | No change, or `on_violation: warn` (§24.4) |
| `human` | Moves the step to `awaiting_human`; the Director asks and calls `record_human_decision` | Decision = approve |
| `provenance` | Implicit: every referenced artifact was registered via `submit_step` | Always enforced |

Common gate options:
- `advisory: true` records the gate's result but never blocks (e.g. cross-model review of a design). Advisory gates still appear in step records and in the process SME's statistics.
- `applies_to: [levels]` scopes a gate to complexity levels (§20.4).
- Any blocking gate occurrence can be **waived** by a recorded human decision with a reason (`waive_gate`, §24.3). Waivers are visible in every record that depends on that step.

Gate failures produce structured `reasons` (and, for findings gates, the open findings), which become `prior_attempt_feedback` on retry or `group.previous_iteration.findings` in a `repeat_until` loop.

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
3. Build `PATH` per §5.5.1 (minimal system PATH, `path.prepend`, and the dir that resolved `executable`); set `LANG` if absent.
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

A shared `spawn()` runs the command **under the supervisor** (§23) with the constructed environment, `cwd` and optional container or user isolation, detached from the caller's session (its own process group/session, so the Director's shell ending or a hang-up does not kill it). It captures stdout and stderr to `~/.baton/logs/` (raw) and a redacted copy to CAS. Adapters never interpret results; intake does.

Workspace steps pass `args.write` or `args.read` (from `workspace_mode`) so read-only steps (research, review) run in the harness's read-only mode where it has one.

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

- Use the official MCP Python SDK **[VERIFY current package name / server API]**. Transport: stdio by default. An optional authenticated HTTP transport (bearer token from a secret, bound to localhost or a private network) serves Directors that cannot run a local process; it is not needed when the Director has a shell on the runtime host (§2 topology).
- One tool per engine function in §7.6. Tool results are compact JSON with next-action hints, e.g. `{"ready_steps": ["design"], "awaiting_human": [], "lease": "held"}`.
- **Never** expose a tool that lets the Director write step outputs, artifacts or events directly.

Registration (**[VERIFY]** each against current docs):
- Claude Code: project-scoped `.mcp.json`, or `claude mcp add baton -- baton mcp`
- Codex: an `[mcp_servers.baton]` entry with `command`/`args` in Codex config (check whether project-level config is supported)
- Hermes: `hermes mcp add baton --command "baton mcp"`

### 11.2 CLI (`cli.py`)

`baton processes | plan | detect | adopt | baseline | start | board | status | explain | eligible | begin | dispatch | wait | submit | decide | retry | retriage | revise | findings | waive | ask | platform | feedback | resume | lease | record | summary | abandon | trace | supervise | doctor | check | mcp`

- **Every command emits `--json`** for Directors and prints readable text by default. Exit codes are stable (0 ok, 1 problem found, 2 usage error, 3 lease held elsewhere, 4 needs human decision).

- **Quiet by default.** `detect`, `doctor`, `resume` and `status` print a single "ok" line when healthy and detail only for problems. `--verbose` shows everything.
- `baton plan <process>` prints the per-level step and gate table (§5.2).
- `baton trace <run_id>` tails `events.jsonl` in readable form.
- `baton doctor [<profile>]`:
  - Checks that the runtime version matches `.baton/baton.lock`, that every vendored package hash matches, and that the vocabulary version is supported.
  - For each profile (or the named one): builds its exact environment, then runs a trivial no-op task through its adapter (e.g. "write `{"ok":true}` to result.json"). It reports success, duration, which auth mode was effective, and which env var names were present or denied.
  - Reports, per vendored process, which steps currently have **zero** eligible profiles on this machine.
  - **Executable resolution:** shows where each harness CLI was found (§5.5.1) or every place it was searched.
  - **Gate preflight:** for profiles eligible for workspace steps, runs the project's gate commands (e.g. `project.test_command`, with a dry/collect-only variant when the project declares one in `project.preflight`) **through the worker's own adapter and permission args**, so a permission mode that would block the gates is caught before a full run is wasted.
  - **Supervisor and hooks:** confirms the supervisor can start detached processes and that configured completion hooks are reachable (a no-op ping where the hook supports it).
  - Problems found are classified (platform vs configuration) and platform problems can be recorded as platform incidents (§25.3).

### 11.3 `skills/baton-director/SKILL.md` (Agent Skills format)

```markdown
---
name: baton-director
description: Run, resume, or adopt Baton processes as Director — keep every work item moving, route steps to capable workers, dispatch and follow long-running work, handle gates, findings and escalations, explain the process in plain language, route questions to the right SME, and keep the owner informed. Use whenever the user asks to start, continue, resume, adopt into a project, check, or ask about Baton work.
---

# Baton Director

You coordinate. You are the expert on the process, and NOT the expert on any step's subject matter or on the platform.
Drive Baton with the `baton` CLI (`--json`) on the runtime host, or its MCP tools. Both are equivalent.

## Hard rules
- Never perform step work yourself. Every step's output must come from dispatch / submit.
- Never compose or edit a context packet. Baton builds packets. If a step cannot start, report the HandoffError's missing inputs.
- Never fabricate a human decision, disposition or waiver. Record only the owner's actual words.
- Retry guidance must be additive; never restate or summarize inputs.
- Only choose workers from eligible_workers. Never edit worker profiles, preferences, permissions or the lockfile without the owner's instruction.
- Never add, remove, skip or reorder steps or roles. Inclusion comes only from triage, the recipe and sub-process expansion; changes go through request_retriage or revise_step.
- Act only within the project's action permissions (push, tag, merge, deploy). Anything outside them is a request to the owner.

## Work items
- The project has many runs (work items) at different positions. Start each session with `board`; pick up whatever needs you.
- New work is a new run (start, then triage). Never fold unrelated work into an active run.
- If an earlier step of a work item turns out to be wrong, propose revise_step for that run, with the reason. It never affects other runs.

## Long-running work
- dispatch returns immediately. If you can stay attached, use wait; otherwise end your turn. The runtime will wake you through the completion hook, or the next session's `board` will show the result.
- Never treat a dispatch as finished until Baton records its completion. If a step timed out or failed, read its classification: subject failures are retried or escalated per the recipe; platform failures go to the platform SME; configuration problems go to the owner.

## Process questions (you answer these)
- Explain where a work item has been, where it is, and where it could go, from explain/status/board. Name the next decision the owner will face.
- Base explanations on the record, never on memory or guesswork. If the record doesn't say, say so.

## Questions for experts (you route these)
- Subject matter → ask_sme(subject=project). Infrastructure, tools, accounts, deployment → ask_sme(subject=platform). How Baton or the recipe itself should work → ask_sme(subject=process).
- Never answer these from your own inference. Say so plainly ("I'm not the expert on this, so I'll ask one"). Choose references by step names, titles and the recipe; do not read subject content to choose them.
- Relay answers faithfully, labeled as the SME's. Do not add your own analysis.
- If an answer should change the project, ask the owner; promote only with explicit agreement.
- Do not use SME content in later routing decisions. After a consultation, prefer resuming from a fresh session.
- When you hit friction with the process (a confusing step, a skipped step, a redundant gate), record it with process_feedback.

## Starting, resuming or adopting
1. detect, then doctor. Both are silent when healthy; only interrupt the owner if they report a problem.
2. board → for each run that needs action: resume it (lease). If a lease is held by another Director, report holder and expiry; take over only with the owner's approval and a stated reason.
3. Existing project without Baton runs: adopt. Present the proposed baseline as ONE decision. Record the answer verbatim.

## Loop (per run)
1. status → ready steps, running work, awaiting_human items, open findings, drift warnings.
2. awaiting_human: present the question, the relevant record and options; record the answer verbatim.
3. open blocking findings: let the recipe's loop handle them (repeat_until); if the owner must decide (accepted-risk, rejection disputes), ask.
4. ready step: eligible_workers → choose (respect preference order unless there is a stated reason not to) → dispatch. Starting work the process already calls for is not a question for the owner; mention it as FYI only if the owner asked to see routing.
5. gate failure: if attempts remain, retry (may switch worker; optional additive guidance); otherwise escalate with reasons.
6. no eligible worker: escalate; explain which capabilities are missing.
7. scope appears to have changed: offer request_retriage.
8. run complete: run_summary → present to owner; release lease.

## Communicating with the owner
- Follow the project's communication contract (`.baton/communication.md`) exactly; it overrides the defaults below.
- Defaults: quiet when healthy. Brief status, then a clearly labeled list of actions for the owner (one step per line, pasteable commands alone in their own block, placeholders that are not valid shell syntax), then the single decision owed. If there is nothing for them to do, say so in one line.
- For manual verification, list only steps runnable against what is live now, each with how you confirmed it is ready.
- Escalations: what failed, why (gate reasons / classification), options, your recommendation about the *process*; never a subject-matter or platform verdict.
```

Also write `skills/baton-worker/SKILL.md` (the §6 protocol rules, the meaning of `exit_criteria`, `deadline` and `protected_paths`, and "stop and report a mismatch instead of improvising") for harness workers.

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

**Phase 14: Consultation.** `ask_sme` (project subject), follow-ups, promotion, relay and handoff modes.
✅ A consult packet contains only Director-selected references plus the record index, with hashes. A follow-up requesting an extra item includes it. A non-promoted answer is unreachable from any step input; a promoted answer appears as a human decision. Transcript review shows the Director relayed answers without adding subject-matter content.

**Phase 15: Projects, board, concurrent runs, `revise_step`.** (§21)
✅ Two runs of different recipes progress independently in one repo. The workspace lock serializes two write-mode steps from different runs. Checkpoint commits never include another run's files. `revise_step` on a design marks only that run's dependent steps stale; a stale step can be confirmed by a human decision without re-running.

**Phase 16: Sub-processes.** (§22) Build this **before** Phase 7 if adopting a project mid-increment is an early goal.
✅ A plan with three slices expands into three instances, run one at a time. A code-review step returning an open high finding triggers iteration 2, whose implement packet contains that finding. `max_iterations` escalates. Revising the plan to change one slice and add another re-expands correctly (unchanged instance kept, changed instance stale, new one added).

**Phase 17: Async execution and liveness.** (§23)
✅ A dispatch survives the Director's shell exiting (killed parent, hang-up). Completion hooks fire on success, gate failure, timeout and crash. Each liveness row in §23.2 is reproduced in a test. An S-effort step past its deadline is terminated and classified. Without hooks, detaching prints the warning.

**Phase 18: Findings, waivers, protected files, independence.** (§24, §7.3)
✅ A rejected finding without valid evidence is refused. `accepted-risk` without an owner decision is refused. A waiver unblocks exactly one gate occurrence. Modifying a protected path is detected in warn and fail modes. A code review by the same vendor as the implementer is refused unless waived.

**Phase 19: SMEs, platform area, process feedback.** (§25)
✅ An `executable_not_found` failure opens a platform incident, preselects facts and logs for the platform SME, and blocks only the affected step. A promoted platform fact appears in the next platform SME packet and in `platform.facts`. Process feedback and statistics appear in a process-SME packet. A skipped blocking gate is surfaced to the owner immediately.

**Phase 20: Communication contract, permissions, cross-platform, `baton check`.** (§26)
✅ The runtime refuses a push that `permissions` denies and records allowed pushes. A docs-only change is recognized from the globs. `baton check` passes on a clean repo and fails on a tampered event, a missing CAS blob and a planted secret sentinel. The full suite passes on Linux and native Windows CI runners.

---

## 13. Testing Strategy

- **Unit:** loader and lint, vocabulary matching, routing, hashing, the state machine, gates, env construction, publishing and drift detection.
- **Property-based** (`hypothesis`): packet determinism; required-input removal; any sequence of legal events rebuilds to the same state; `foreach` re-expansion is stable for unchanged items.
- **Fake adapter:** scripted good, bad-schema, wrong-hash and blocked results, plus timeouts, crashes, hangs, findings lists and exit 127.
- **Process-control tests:** supervisor detachment, deadline termination of a whole process tree, and marker/PID liveness classification on POSIX and Windows.
- **Secret-leak test:** run a full toy process with sentinel secret values, then assert the sentinels appear nowhere in the repo working tree or the git history.
- **Golden files:** `INSTRUCTIONS.md`, step records, summary.
- **Live tests** (opt-in env var): real LiteLLM and harness adapters.

---

## 14. Open Decisions (ask the human before choosing)

1. Parallelism: sub-process `concurrency` and concurrent runs are supported (§21, §22). Should the Director also be allowed to dispatch independent top-level steps of one run in parallel? Suggested: yes, subject to the workspace lock.
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
12. SME handoff mode: which harnesses support spawning a separate session or bot, and how its transcript returns. Ship relay mode first; handoff per harness later.
13. Consultation retention: commit full SME transcripts with the run (suggested, redacted), or only the question and final answer.
14. Research scope limits: maximum files and bytes scanned, and file types considered, before research asks the human to narrow it.
15. Worktree isolation for concurrent write-mode steps (§21.2): ship it, or keep the single workspace lock only? Suggested: lock only at first.
16. Effort bands and `extend_once` defaults (§23.4). Suggested: S 45 min, M 2 h, L 4 h, extend once.
17. Automatic platform-SME invocation on platform failures (hook) versus Director-initiated only. Suggested: Director-initiated unless `on_platform_failure` is configured.
18. Protected-path violation default: `warn` (suggested, matching existing practice) or `fail`.
19. Who may set `fixed` and `rejected` dispositions: the next iteration's worker with evidence (suggested), or only the Director with evidence.
20. Where the platform SME's own credentials and channels live (it may itself be an agent with its own access); Baton only routes to it.

---

## 15. Security & Safety Notes

- Script gates execute commands from process packages, so treat **vendored packages as trusted code**. Review them before vendoring, and keep the lockfile hash check (`baton doctor`) on.
- Harness workers may run with broad permissions. Prefer `isolation: container` or a dedicated user, with the workspace scoped.
- **Everything committed passes `redact.py`.** It strips known secret values (the resolved secrets for the current process) and known token patterns. Raw unredacted logs stay in `~/.baton/logs/`.
- Secrets are never written anywhere under the project tree. The Phase 6b and §13 tests enforce this.
- Packets and results may contain sensitive project data. Treat `.baton/runs/` like the rest of the repo's confidential content.
- Completion hooks and `command` adapters execute shell commands: machine-level hooks may reference secrets; project-level hooks may not (the loader rejects `secret:` there).
- Action permissions (§26.2) bound what the runtime and Director may do to the repository and its remotes; the defaults never merge, deploy or force-push.
- An SME (especially a platform SME) may hold its own credentials outside Baton. Baton never passes secrets into SME packets; it passes facts, incidents and redacted logs.

---

## 16. Definition of Done

- All phases' acceptance criteria pass.
- `README.md` covers install (pinned), registering the MCP server per harness, writing worker profiles, `baton doctor`, authoring a neutral process package, vendoring a package into a project and resuming a run on a new machine.
- One software and one non-software example package ship with the runtime.
- Swapping the Director harness, or any step's worker, requires only local config changes. Recipe changes require no runtime changes.
- Adopting into an existing project with a crosswalk requires exactly one human decision (the baseline), and a healthy project produces no routine prompts.
- A remote Director with only shell access to the runtime host can run a multi-slice work item to completion across several of its own sessions, woken by completion hooks, with no owner action other than the recipe's decisions.

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
│   ├── project.yaml                  # paths, project vars, permissions, hooks (non-secret), limits, contacts, sme
│   ├── communication.md              # owner communication contract (§26.1)
│   ├── project/events.jsonl          # project-level events (§21.1)
│   ├── platform/facts.md             # platform facts (§25.3)
│   ├── process/lessons.md            # project-level process lessons (§25.4)
│   ├── preferences.yaml              # optional, non-secret routing preferences
│   ├── processes/<id>@<version>/     # vendored, pinned process packages
│   ├── runs/<run_id>/                # events.jsonl, cas/, steps/, docs/
│   ├── workers.local.yaml            # GITIGNORED
│   └── cache/                        # GITIGNORED (SQLite, running markers, locks)
├── docs/specs/ docs/design/ plans/ cad/ …   # published deliverables (§19)
└── .gitattributes                    # LFS rules for .baton/runs/**/cas large blobs + binary deliverables
```

| Item | Commit? |
|---|---|
| Process packages (pinned) + `baton.lock` | ✅ |
| Skills, `AGENTS.md` pointer, MCP project config | ✅ |
| `project.yaml`, `preferences.yaml`, `communication.md` | ✅ |
| `.baton/project/`, `.baton/platform/`, `.baton/process/` | ✅ (redacted) |
| `.baton/runs/**` (events, CAS, packets, results, docs) | ✅ (redacted) |
| Published deliverables at project paths | ✅ |
| Baton runtime source | ❌ install it pinned (`uv tool install baton==X` or equivalent); vendor only for offline use or a fork |
| Worker profiles (`~/.baton/workers.yaml`, `.baton/workers.local.yaml`) | ❌ |
| Secrets, raw logs, SQLite cache, running markers, machine-level hooks | ❌ |

`baton init` creates this structure, the `.gitignore` entries and the `.gitattributes` LFS rules. `baton vendor <package-dir>` copies a package, runs the neutrality lint and records its hash in the lockfile.

---

## 18. Run Persistence & Handoff Between Directors

### 18.1 Goal

Any capable Director, on any machine, can clone the repo and continue a run reliably from the last checkpoint. With concurrent work items (§21), everything here applies per run; project-level files use a short project lock.

### 18.2 Checkpoint commits (`gitops.py`)

- After `step_passed` + publish, `human_decision`, `step_escalated` and `run_completed`, the runtime stages `.baton/runs/<run_id>/` plus the published deliverables, then commits with a structured message, e.g. `baton(<run_id>): design passed [attempt 1, worker openai-api-strong]`.
- A `checkpoint_committed` event (with the commit SHA) is appended **in the next commit**, since the SHA isn't known until after committing. Alternatively, record SHAs only in git and let `resume` read `git log`. Choose one and document it.
- Workspace steps (code) commit their own changes; their `commit_sha` is recorded in the step output, and the checkpoint commit follows.
- Never commit with uncommitted unrelated changes present; refuse and report instead (or use a dedicated branch; see §14).
- Pushing follows the project's action permissions (§26.2); checkpoint commits of `.baton/` and published docs normally qualify as docs-only.

### 18.3 Run lease (`lease.py`)

- A lease is an event: `lease_claimed {director_id, harness, host, expires_at}`. Mutating engine calls require a valid lease held by the caller.
- `renew_lease` extends it. `release_lease` on completion or pause.
- If an unexpired lease is held by someone else, mutation is refused. `take_over_lease(reason)` records the takeover; the director skill requires human approval first.
- Leases travel via git, so they coordinate *sequential* handoff, not real-time concurrency. Two Directors racing on unsynced clones will be caught at merge by the event hash chain. `resume` refuses a run whose chain has diverged and asks for human resolution.

### 18.4 `resume(run_id)`

1. Verify the event hash chain and every CAS blob's hash.
2. Rebuild the SQLite cache.
3. Any attempt in `dispatched`, `running` or `submitted` is checked against its running marker (§23.2): still alive → left running; finished with a result → intake completes now; otherwise `attempt_orphaned` (retryable), with the failure classified.
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

`detect()` inspects the filesystem, git and the event logs and returns the project situation plus, for each run, its situation and a recommended next action (the board, §21.2, is the human-readable form). It is deterministic and fast. Running work is judged by its marker (§23.2), and open platform incidents (§25.3) are reported.

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
- **Seeding into sub-processes.** A work item adopted mid-way (e.g. the third of three slices has been implemented and reviewed but not yet accepted by the owner) is seeded at the granularity it actually reached: the source step (the plan) is imported, the group is expanded from it, finished instances are imported whole, and a partly finished instance has its completed steps imported while the rest start normally. A gate that already passed outside Baton is imported with its evidence; a pending owner approval stays a pending human gate.
- **Seeding findings and waivers.** Review findings and their dispositions are imported with the step they belong to. Steps approved before a gate existed are imported with a recorded waiver for that gate (§24.3), proposed in the baseline.
- **One work item per run.** An adopted project usually has several work items: finished ones (left as history, not seeded), at most a few in flight (each becomes its own run, seeded), and new ones (started normally). The baseline lists each in-flight item and its proposed seeds as part of the single decision.

### 20.6 Consultation (project subject; generalized in §25)

Subject-matter questions always go to a consult worker. The Director's value is knowing **where** the relevant knowledge lives; the consultant's value is understanding **what** it means.

- **The Director selects, the runtime assembles.** `ask_sme(subject="project", question, refs, run_id, mode)` (other subjects: §25). The Director chooses `refs` by name from the record and recipe (e.g. `steps.design.artifacts.design_doc`, `steps.requirements.output`, `human.d_014`, published deliverables, and for consults only `project:<path-or-glob>`) without reading their content. The runtime resolves them into a hashed consult packet.
- **Plain provenance, not Baton.** Each item carries a neutral label (what it is, which step produced it, its standing: "approved design, attempt 2", "edited by a human after publishing", "imported from prior process"). The consultant needs no knowledge of Baton.
- **Safety net.** The packet includes an index of everything else on record (titles and references only). The answer schema is `{answer, confidence, sources_used[], requested_refs[], suggests_retriage}`. If `requested_refs` is non-empty, the Director approves a follow-up (or asks the human), and `sme_followup` includes those items plus the prior turns.
- **Routing.** The consultant is chosen by `eligible_workers` against the recipe's `sme.project` requirements, then `project.yaml`, then the vocabulary default. No independence constraint.
- **Isolation from the run.** Consult answers are recorded (`sme_requested` / `sme_answered`, transcript in `.baton/runs/<id>/sme/`) but are **not** referenceable as step inputs. They affect the run only through `promote_sme(as: decision | revision)` with the human's explicit agreement (`sme_promoted`).
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

---

## 21. Projects and Work Items

### 21.1 Model and layout

A **project** is one repository. It holds any number of **runs**; each run is one **work item** (a feature, an increment, a fix, a small chore) following one recipe. Work items move independently: a small fix can be triaged, built and shipped while a larger increment sits at its third slice. Nothing ever moves the *project* backward.

```
.baton/
├── project.yaml                  # paths, project vars, permissions, hooks (non-secret), limits, contacts
├── communication.md              # owner communication contract (§26.1)
├── project/events.jsonl          # project-level events: platform incidents, process feedback (hash-chained)
├── platform/facts.md             # platform facts (§25.3)
├── process/lessons.md            # project-level process lessons (§25.4)
└── runs/<run_id>/                # one per work item (events, cas, steps, docs, sme)
```

Each run's `run_started` event records the work item: `{title, kind, slug, recipe, recipe_version}`. `kind` is free text from the recipe's run inputs (e.g. `feature`, `fix`).

### 21.2 The board and concurrency

`baton board` lists every non-terminal run: work item, recipe, current position (including sub-process progress such as "slices 2/3, s3 at accept"), running work, pending owner decisions, lease holder. `--needs-me` filters to runs with a pending human decision. The board is the first thing a Director reads each session.

Concurrency rules:
- **Leases are per run.** A Director may hold several.
- **One working tree, one writer.** Workspace steps in write mode take a project-level **workspace lock**; a second write-mode step (in any run) waits until it is free. Read-mode steps don't take it. An optional `workspace_isolation: worktree` in `project.yaml` gives each write-mode step its own git worktree instead **[VERIFY merge strategy before enabling]**.
- **Git operations are serialized** by a short project lock. Checkpoint commits stage only the committing run's directory and its own published deliverables, never another run's files.
- Optional `limits` in `project.yaml` (e.g. `active_runs: 3`) make `start` refuse beyond the limit, with an explanation.

### 21.3 Correcting an earlier step: `revise_step`

When a later step shows that an earlier one in the **same work item** was wrong (slice 2 reveals a design flaw), the Director proposes, and the owner approves, `revise_step(run, step_path, reason)`:
1. The target step gets a new attempt. Its packet includes the previous result and the stated reason (`revision_of`). The old result becomes `superseded`.
2. Every step in that run whose inputs depend on the target, directly or transitively, becomes `stale`. Inside sub-processes, instances that do not depend on it are untouched.
3. When the revised step passes, each stale step is either re-run (`ready`) or confirmed unchanged by a human decision. This is useful when a wording fix in a design does not invalidate completed slices.
4. The reason is recorded without blame (`step_revised`). Other runs are never affected.

Revising a step whose output fed a `foreach` (e.g. the plan) re-expands the group (§22.2).

---

## 22. Sub-processes (Cross-Worker Iteration)

### 22.1 Declaration

A step entry with its own `steps:` list is a **sub-process** (group). Options:

| Key | Meaning |
|---|---|
| `foreach` | Reference to an array in an ancestor step's validated output; one **instance** per item. Each item must have a unique `id`. |
| `foreach_if_source_skipped` | `once` (run a single instance with `item` = run inputs) or `skip` (skip the group). |
| `concurrency` | Max instances active at once (a work-in-progress limit). Default 1. |
| `repeat_until` | Condition over gates of steps inside the group (e.g. `group.steps.code_review.gates.passed`). After each iteration, if false, start another. |
| `repeat_from` | Step id where a new iteration starts (default: the first step). |
| `max_iterations` | Required with `repeat_until` (1–10). Reaching it escalates (`iteration_limit_reached`). |

Inside a group, steps use `item`, `group.steps.<id>.*` and `group.previous_iteration.findings` (§5.2).

### 22.2 `foreach` expansion

When the source step passes, the runtime expands the group deterministically: one instance per item, ordered as in the array, recorded in `group_expanded` with each item's id and content hash. Instances start as concurrency allows.

If the source step is later revised (§21.3), the group is re-expanded against the new array:
- **Same id, same hash:** keeps its state.
- **Same id, changed content:** that instance becomes `stale`.
- **Removed id:** `superseded`.
- **New id:** added.

### 22.3 `repeat_until` iteration

Two kinds of repetition are deliberately separate:
- **Attempts:** the same step tried again after its own gate failed (e.g. tests failed). Bounded by `max_attempts`.
- **Iterations:** the group's loop runs again because its exit condition is not met (e.g. the independent code review still has open high findings). Bounded by `max_iterations`.

Each new iteration receives the previous iteration's open findings and gate reasons as `group.previous_iteration.findings`, so the implementer fixes exactly what the reviewer found. Previous iterations stay in the record.

### 22.4 Aggregate state

- An instance is `passed` when its last iteration's steps all passed.
- The group is `passed` when every instance is `passed`, `superseded` or `skipped`.
- Downstream steps may reference the group only as a whole (`steps.<group>.outputs`).
- `explain` and the board describe groups in plain terms ("3 slices: 2 accepted, 1 in review, iteration 2 of 3").

### 22.5 Limits

- Groups nest at most one level (a group may not contain a group).
- `foreach` and `repeat_until` may be combined; the loop then runs per instance.
- Iteration *inside* a worker is not modeled. The worker gets `exit_criteria` and a `deadline` in its manifest and is free to loop internally until it meets them or runs out of time.

---

## 23. Async Execution and Liveness

### 23.1 Dispatch model

`dispatch` returns as soon as the worker is started. A small **per-dispatch supervisor** process (no daemon) is started detached from the caller's session:
- POSIX: new session and process group (`setsid`).
- Windows: detached process group flags **[VERIFY]**.

The supervisor starts the worker, maintains the running marker, enforces the deadline, runs intake when the worker exits, fires completion hooks and exits. A Director whose turn or shell ends does not affect it.

### 23.2 Running marker and heartbeat

While a dispatch is live, the supervisor keeps `.baton/cache/running/<dispatch_id>.json` (machine-local, gitignored) containing `host`, `supervisor_pid`, `worker_pid`, `run_id`, `step_path`, `started`, `deadline` and a `heartbeat` timestamp refreshed every 30 s. The marker is removed after intake completes. A `step_running` event is recorded once the worker is confirmed alive; heartbeats are not written to the event log.

Liveness, as reported by `status`, `board` and `resume`:

| Marker | Process | Result | Classification |
|---|---|---|---|
| present | alive | – | running (or overdue if past deadline) |
| present | dead | written | missed completion → resume intake |
| present | dead | none | died silently → `orphaned`, classify (§23.5) |
| absent | – | intake done | finished |

### 23.3 Completion hooks

After intake, the supervisor fires hooks on **every** outcome (passed, gate failed, needs human, timed out, failed). Hooks are configured outside recipes:
- **Project-level, non-secret:** `.baton/project.yaml` `hooks:`.
- **Machine-level, may reference secrets:** `~/.baton/hooks.yaml`, e.g. a webhook URL that wakes a remote Director.

```yaml
hooks:
  on_complete: "curl -fsS -m 20 -X POST -d run=$BATON_RUN_ID -d step=$BATON_STEP_PATH -d outcome=$BATON_OUTCOME secret:director_wake_url"
  on_needs_human: ""          # optional; falls back to on_complete
  on_platform_failure: ""     # optional; e.g. wake the platform SME
```

Hooks run through the platform shell from the repo root. `secret:<name>` references are allowed only in the machine-level file; they are substituted at execution and never logged. Hook environment: `BATON_RUN_ID`, `BATON_STEP_PATH`, `BATON_OUTCOME`, `BATON_CLASSIFICATION`, `BATON_DISPATCH_ID`, `BATON_REPO`, `BATON_RECORD` (path to the step record). Hook failures are recorded (`completion_hook_failed`) and never change the step's outcome.

If no hook is configured and the Director dispatches without `--wait`, `dispatch` prints a warning: the result will only be seen at the next `board`/`status`. Silent misses are avoided by design, not by discipline.

### 23.4 Effort and timeouts

Steps declare `effort: S | M | L`, or `effort_from` an item field. Bands come from `project.yaml` (defaults S = 45 min, M = 2 h, L = 4 h). At the deadline the supervisor:
1. If the worker is alive and `extend_once: true` is set, records an overdue notice, fires `on_complete` with outcome `overdue`, and extends by one band.
2. Otherwise terminates the worker's process group, records `step_timed_out`, runs intake on whatever result exists (normally none) and classifies the failure.

### 23.5 Failure classification

`classify.py` applies deterministic rules, in order, and records `failure_classified`:

| Class | Typical signals | Goes to |
|---|---|---|
| `configuration` | Unknown profile, missing secret, invalid project.yaml | Owner (with exact fix) |
| `platform` | Executable not found (exit 127), auth/login failures, sandbox or permission denials on gate commands, network/DNS errors, disk full, killed by the OS, supervisor died | Platform SME (§25), with an incident opened |
| `subject` | Gate failed, schema invalid, worker reported `failed` or `blocked` | The recipe's normal path: retry, iterate or escalate |
| `unknown` | Nothing matched | Platform SME first, then owner |

Adapters contribute signal patterns for their CLI (e.g. known auth-error text). Rules are data, so new patterns can be added without code changes. A platform failure gets at most **one** automatic retry, and only when the platform SME records a fix. Otherwise the step waits on the incident.

---

## 24. Reviews, Findings, Waivers and Protected Files

### 24.1 Findings schema (fixed, runtime-owned)

```json
{
  "findings": [
    {"id": "F1", "severity": "high", "location": "src/auth.py:42", "title": "…", "detail": "…", "suggested_fix": "…"}
  ],
  "coverage": {"complete": true, "notes": ""}
}
```

- Severities: `critical | high | medium | low`. Reviewers must return this JSON. Nothing is parsed from free text, which removes a whole class of "no findings" parsing errors.
- `coverage.complete: false` (e.g. the reviewer could not run socket tests because its profile lacks `loopback_network`) is shown in the record and makes the gate result read "partial".

### 24.2 Dispositions

Each finding starts `open`. Allowed dispositions:

| Disposition | Requirement |
|---|---|
| `fixed` | A reference (commit or file:line). In a `repeat_until` loop, the next review iteration confirms it. |
| `rejected` | **Evidence**: a `file:line` that exists at the reviewed commit, or a test reference. Validated by the runtime. |
| `accepted-risk` | A recorded **owner** decision id. Workers and Directors cannot set it alone. |

A findings gate passes when no finding with a severity in `block_on` is `open`. Advisory findings gates never block, but their dispositions are still recorded.

### 24.3 Waivers

`waive_gate(run, step_path, gate, reason)` requires a human decision and records `gate_waived`. Uses include grandfathering a step that was approved before a gate existed (common at adoption), or allowing a self-review once. A waiver applies to one gate occurrence only; it never changes the recipe.

### 24.4 Protected files

A workspace step may declare `protect: [globs]` with `on_violation: warn | fail` (default `warn`). The runtime hashes matching files before dispatch and after the worker exits; any change records `protected_path_modified` with the diff summary.
- `warn`: the step continues but carries an owner decision, approve or revert, before the group or run can pass.
- `fail`: the gate fails.

This generalizes "locked acceptance specs": an approval gate can record the hash set of protected paths at approval time, and later steps must preserve it.

### 24.5 Review statistics

Per reviewer profile and per step, the runtime keeps counts of findings by severity, dispositions (fixed, rejected, accepted-risk) and iterations to clean. They feed the process SME (§25.4); they are never used to block.

---

## 25. Subject-Matter Experts and the Platform Area

### 25.1 Subjects

`ask_sme(subject, question, refs, run_id?, mode)` generalizes §20.6 consultation to three built-in subjects:

| Subject | Expert on | Default packet scope |
|---|---|---|
| `project` | The work's domain | Selected run records, published deliverables, `project:` file refs |
| `platform` | Development and deployment infrastructure: hosts, CLIs, auth, networks, deployment platforms | Platform facts, open incidents, `doctor` output, redacted run logs, non-secret profile config |
| `process` | Baton and the recipe | Events, step records, process feedback, review statistics, the recipe |

Requirements per subject come from the recipe (`sme.<subject>`), then `project.yaml` (`sme:` may name `preferred_profiles`, e.g. a dedicated platform agent), then vocabulary defaults. An SME profile can use any adapter, including a `command` adapter that relays to another agent or a `manual` adapter for a human expert. Everything else from §20.6 applies unchanged: the Director selects references, the runtime assembles hashed packets, answers are recorded but not referenceable until promoted, and `relay` and `handoff` modes are available.

**Promotion targets:** a human decision, an artifact revision, a **platform fact**, or a **process proposal** (a suggested recipe or configuration change for the owner to approve; recipe changes are made as a new recipe version and re-vendored, never in place).

**Direct interaction:** a platform SME may need to work with a worker, the Director or the owner (e.g. guide the owner through a login). In `handoff` mode the SME session is opened with the relevant contacts. In any mode, its conclusions return to Baton as a recorded answer and, where durable, a promoted platform fact.

### 25.2 Automatic routing

- A step failure classified `platform` or `unknown` (§23.5) opens a platform incident. The Director then asks the platform SME, with the incident, the failing dispatch's redacted logs and the relevant facts preselected by the runtime.
- If `on_platform_failure` is configured, the hook can wake the platform SME directly.

### 25.3 The platform area

Platform knowledge belongs to the project, not to any run:
- **`.baton/platform/facts.md`:** durable facts, one entry each with source and date. Examples: "codex is installed under nvm v22 on the runtime host"; "service X listens on 8080 inside the container, 8000 outside"; "headless coding agent needs bypass permissions to run tests". Facts arrive by promotion from the platform SME, by owner edit, or are auto-recorded by the runtime as `observed` (e.g. resolved executable paths).
- **Incidents:** project events (`platform_incident_opened` / `platform_incident_resolved`) with affected runs and steps, the classification and the resolution. Steps blocked on an incident show it on the board.
- **Use:** any step may take `platform.facts` as an input. Platform SME packets include facts and open incidents automatically. `doctor` reports open incidents.

### 25.4 The process SME (introspection)

Process improvement is consultation with `subject=process`, not a separate subsystem:
- **Inputs it sees:** `process_feedback` events recorded by Directors, workers (through `notes`) or the owner (kinds: `friction`, `skipped_step`, `waste`, `confusing`); skip records with `informed_owner: true|false`; and statistics the runtime keeps automatically (attempts, iterations, timeouts and their classes, time per step, review statistics).
- **When:** on demand, at run completion if the recipe includes a retrospective step that consults it, or on a cadence the owner chooses.
- **Outputs:** answers and **process proposals**. The owner approves each before anything changes. Project-level lessons go to `.baton/process/lessons.md` ("when X, do Y, because Z", with origin and confirmation count). Lessons confirmed across projects are promoted into the recipe package by its maintainer.
- **Safety-relevant skips** (any skipped blocking gate or human approval) are surfaced to the owner immediately by the runtime, not left for a retrospective.

---

## 26. Owner Communication, Permissions, Cross-Platform and `baton check`

### 26.1 Communication contract

`.baton/communication.md` (project-owned; a recipe may ship a default) defines how the Director writes to the owner. The Director skill must follow it. Baton's default, adopted from the owner's existing practice:
- **Shape:** brief status (or omit); a labeled list of the owner's actions, one step per line, each pasteable command alone in its own block; the single decision owed at the end. If there is nothing to do, a one-line "no action" statement.
- **Placeholders** that are not valid shell syntax (`PASTE_TOKEN_HERE`, never `$TOKEN`).
- **First mention** of anything new the owner must do or understand: where it lives (product, UI path, file or CLI), what it does, and the exact value or action.
- **Manual verification** lists only steps runnable against what is live now, each with how readiness was confirmed; blocked steps are labeled with what unblocks them.
- **Reversed defaults** get a one-line "Before → After" in the approval ask.
- **Risk mitigations the agents propose** are presented as a decision with their cost and a narrower alternative, never absorbed silently.

`project.yaml` `contacts:` names who receives what (e.g. `owner: owner`, `platform: <profile>`), using human or agent profiles.

### 26.2 Action permissions

```yaml
# .baton/project.yaml
permissions:
  push:
    docs_only: allow            # allow | ask | deny
    after_verified: allow       # code changes once the work item's verification steps have passed
    other: ask
  tag: ask
  force_push: deny
  merge: deny
  deploy: deny
docs_only_globs: ["docs/**", "**/*.md", ".baton/runs/**", ".baton/platform/**", ".baton/process/**"]
```

- The runtime enforces these for its own git operations (checkpoint commits, pushes) and records `permission_used`.
- For actions outside the runtime, the Director skill must check the permission first; `ask` becomes a request to the owner (`permission_requested`), and `deny` is never attempted.
- "Docs only" means every changed path matches `docs_only_globs`.

### 26.3 Cross-platform requirements

The runtime host may be Linux, macOS, native Windows or WSL:
- Store and compare paths in POSIX form; accept backslashes on input.
- Write text as UTF-8 **without BOM** with LF endings; tolerate a BOM on read.
- Run git with explicit settings (`-c core.autocrlf=false`) so committed files are byte-stable across platforms.
- Never rely on shebangs; entry points come from the installed package (`baton`, `python -m baton`, or `py -m baton` on Windows).
- Detached processes and process-tree termination use platform-specific code paths (§23.1), tested on both families.
- Directory permissions: `0700` on POSIX; best-effort user-only ACLs on Windows.
- In WSL, keep repos on the Linux filesystem, not `/mnt/c`; `doctor` warns otherwise.

### 26.4 `baton check`

A non-interactive consistency check for pre-commit hooks and CI. Exit 0 when clean, 1 with one `ERROR <path>: <message>` line per problem. Checks:
- Event hash chains (runs and project) and CAS integrity.
- Lockfile versus vendored package hashes, and the neutrality lint on vendored packages.
- Published deliverables versus their recorded hashes (drift is a warning unless `--strict`).
- No secrets under `.baton/` (sentinel and pattern scan).
- No run in an impossible state (e.g. a passed step whose blocking gate has no recorded outcome).
- `project.yaml` and `communication.md` present and valid.

It never needs network access or worker profiles, so it runs anywhere the repo is checked out.
