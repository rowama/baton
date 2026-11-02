# Baton: Build Guide for a Vendor-Neutral, Director-Led Multi-Step Process Framework

> **Revision 4 (consolidation).** Same design as Revision 3, reorganized into one coherent structure: a stated set of principles, a capped concept set with a glossary, a small core plus optional layers, merged duplicate sections, a single event list, a single API table, one build order, and explicit versioning so real projects can trial new Baton versions on a branch. History: Rev 2 (model-neutral recipes, routing, isolation, repo persistence, publishing); Rev 2.1 (renamed from "Relay"); Rev 2.2 (adoption, complexity tailoring, consultation); Rev 3 (work items, sub-processes, async execution, findings reviews, SMEs, platform area, permissions; informed by the owner's `eng-process` and its use on `mmbridge`).
>
> **Audience:** a fresh AI coding session (Claude Code, Codex, Hermes, etc.) building this framework from scratch.
> **Read the whole document before writing code.** Then follow the build order (§16). Each phase has acceptance criteria; do not start a phase until the previous one passes.

---

## 0. Ground Rules for the Building Agent

1. **Do not invent APIs.** Before using any library (`mcp`, `litellm`, `jsonschema`, `typer`, etc.) or CLI (`claude`, `codex`, `hermes`, `uv`), check its installed version's docs or `--help`. Anything marked **[VERIFY]** must be confirmed against current docs before you rely on it.
2. **Determinism over prompting.** Anything that must be 100% reliable is enforced in code, never left to an LLM following instructions.
3. **Thin layer.** No web UI, no message broker, no database server, no long-running daemon. Filesystem, git, SQLite (as a cache only) and plain Python. Every dependency must justify itself.
4. **Vendor neutrality.** No model vendor is privileged in the core or in recipes. Vendors exist only in worker profiles and adapters.
5. **Small, tested increments.** Tests alongside each module; `pytest` green at every commit.
6. **Ask the human** when a requirement is ambiguous. Never silently decide anything listed in §18 (Open Decisions).
7. **The name is a label, not a spec.** "Baton" evokes work passed between workers under a Director. Use the metaphor only to explain; never derive a design decision or a term from it. Code and docs use plain names (step, packet, result, worker, gate).
8. **Respect the concept budget (§2).** Do not introduce a new user-visible concept, file or command without updating §2 and justifying it against the principles in §1.

---

## 1. What We Are Building, and the Principles That Bound It

**Baton** is a small runtime that lets *any* agentic harness act as the **Director** of a multi-step process, while each step is done by a **Worker**: a model API call, a headless coding agent, or a human. Processes are **recipes**: shareable, model-neutral packages. Baton supplies the machinery that makes multi-agent work reliable and leaves the domain knowledge to recipes.

### 1.1 Principles (every feature is judged against these)

1. **Invisible when healthy.** After install, the owner should not notice Baton unless something truly needs them. Checks are silent when fine; owner attention is spent only on real decisions: gates the recipe defines, escalations, and the one-time adoption baseline.
2. **Friction must pay for itself.** Every setup step, prompt or file the owner touches must save more effort than it costs. Prefer generalizing an existing mechanism over adding a parallel one.
3. **Arbitrarily complex processes, simple runtime.** Recipes can express multi-agent processes of any size (iteration, fan-out, reviews, many concurrent work items). The runtime stays small and conventional: one event log format, one packet protocol, one state machine, no daemon, no server. **Everything that does work is a dispatch of a packet to a worker** (steps, reviews, research, triage, expert consultation); everything else is bookkeeping over the event log.
4. **Evolve by trial.** Runtime, recipes and formats are versioned and pinned per project and per run, so a real project can try a new Baton version on a branch and merge or discard it (§14).

### 1.2 Guarantees

| Guarantee | Mechanism |
|---|---|
| **Reliable context handoff** | The runtime (not the Director) assembles each step's packet from the recipe's declared inputs; a missing required input stops the step. Packets are content-hashed. |
| **Standard communication** | One file-based protocol (packet in, result out) for every kind of worker. |
| **Model-neutral, shareable recipes** | Recipes declare required *capabilities*, never models or vendors; a lint enforces it. |
| **Dynamic, enforced routing** | The Director picks a worker from the runtime-computed eligible set; the runtime enforces eligibility and records the choice. |
| **Per-step isolation** | Each worker runs as a child process with its own constructed environment and auth (API key or CLI subscription login). |
| **Tailored formality** | A triage step rates complexity on the recipe's own scale; the runtime includes or skips steps and gates accordingly. |
| **Cross-worker iteration** | Sub-processes repeat a group of steps per item (e.g. per slice) or until a review is clean, bounded and enforced. |
| **Concurrent work items** | A project holds many runs (features, fixes) at different positions; the project never "steps back". |
| **Long-running work** | Dispatch is asynchronous; the runtime supervises, times out, classifies failures and wakes the Director. |
| **Expert routing** | Questions go to experts by subject (project, platform, process). The Director routes and never answers from its own inference. |
| **Observability and continuity** | Append-only, hash-chained event logs and content-addressed artifacts live in the repo; any capable Director on any machine can resume. |
| **Deliverables in the project** | Documents, source code, drawings, etc. are published to real project paths; the run holds their provenance. |
| **Low-friction adoption** | Existing projects are adopted in place; existing work is imported as attested results behind one owner decision. |

### 1.3 Non-goals

- Not an agent framework. Baton runs no LLM loop of its own. Iteration *inside* a worker (a coding agent looping until its tests pass) is the worker's business; Baton supplies the exit criteria and a time budget.
- Not a general scheduler. Steps run when the Director dispatches them; the runtime only supervises dispatched work.
- No GUI; no backlog or idea management (owners use tools of their choice).

### 1.4 Key design decisions

1. **The runtime owns handoff.** The Director says "begin step X with worker P"; Baton decides what goes in the packet. This removes the main failure mode: a Director that summarizes, forgets or paraphrases context.
2. **Files are the protocol.** Every harness can read and write files; packets and results are inspectable, diffable directories.
3. **Content addressing and provenance.** Every artifact is stored by SHA-256; a result must echo its packet's hash; only artifacts registered through intake count. A Director that bypasses Baton cannot satisfy a gate.
4. **Recipes hold the process; the runtime and project hold the machinery.** Hooks, timeouts, PATH handling, permissions and platform facts never appear in a recipe, so recipes stay portable.
5. **Routing is chosen by the Director, constrained by the runtime.**
6. **Isolation by construction.** Workers never inherit the Director's environment by default, so one step's API key cannot change another step's billing.
7. **The repo is the system of record.** Event logs and artifacts are committed at checkpoints; SQLite is a rebuildable cache.
8. **Async by default.** Any dispatch may outlive the Director's session; the runtime owns completion.
9. **Structured over parsed.** Workers and reviewers return schema-validated JSON; nothing important is scraped from free text.
10. **The Director never modifies a process.** No adding, removing or reordering steps or roles. Variation comes only from complexity levels, sub-process expansion and expert consultation.
11. **Work items move; projects don't.** Correcting an earlier step is local to one run (`revise`).
12. **CLI and MCP are equal Director interfaces** over one core.

---

## 2. Concepts (the Concept Budget)

These are all the concepts a recipe author, Director or owner may encounter. Adding one requires updating this section (§0 rule 8).

| Concept | Meaning |
|---|---|
| **Project** | One repository using Baton. Holds runs, project configuration, platform facts. |
| **Recipe** | A versioned, model-neutral process package: steps, inputs, gates, schemas, prompts, templates. |
| **Run** | One **work item** (feature, increment, fix) following one recipe. Has its own event log and position. |
| **Step** | One unit of work in a recipe, done by one worker per attempt. |
| **Group** | A step containing steps (a sub-process). Expands into **instances** (`foreach`) and/or repeats in **iterations** (`repeat_until`). |
| **Attempt** | One try at a step. A failed gate may trigger another attempt. |
| **Packet / Result** | The files a worker receives / returns. |
| **Gate** | A check a step must pass: schema, script, review findings, human approval (plus implicit provenance, workspace and protected-file checks). |
| **Worker profile** | Machine-local definition of one worker: adapter, model or CLI, capabilities, auth, environment. |
| **Capability** | A named ability from a versioned vocabulary; recipes require them, profiles claim them. |
| **Director** | The coordinating agent. Process expert; never does step work. |
| **SME** | An expert worker consulted by subject: `project`, `platform` or `process`. |
| **Event log** | Append-only, hash-chained JSONL per run and per project; the source of truth. |
| **CAS** | Content-addressed artifact store inside each run. |
| **Lease** | Which Director may change a run right now. |
| **Owner** | The human who makes the decisions. |

Machinery that exists but owners and recipe authors never configure per run: supervisor processes, running markers, file locks (per run, project, workspace), the SQLite cache.

### 2.1 Core and layers

The runtime is built as a small **core** plus **layers**. A recipe or project that does not use a layer pays nothing for it.

| Part | Contents | Needed for |
|---|---|---|
| **Core** | Recipes (steps, inputs, schema/script/human gates), packets, intake, event log, CAS, state machine, CLI, manual and one harness adapter, checkpoint/resume | Everything |
| **L1 Routing and isolation** | Worker profiles, capabilities, eligibility, env construction, PATH resolution, API and harness adapters | Multi-vendor work |
| **L2 Async** | Supervisor, liveness, completion hooks, effort timeouts, failure classification | Long or remote-Director work |
| **L3 Sub-processes** | `foreach`, `repeat_until`, instances, iterations | Slice loops, review-fix loops |
| **L4 Reviews** | Findings gates, dispositions, waivers, protected files, reviewer independence | Independent review |
| **L5 Work items** | Concurrent runs, board, workspace lock, `revise` | Real projects |
| **L6 Tailoring and adoption** | Complexity levels, triage, detect, research, crosswalks, seeding, baseline | Existing projects; varied formality |
| **L7 Experts** | SME consultation (project, platform, process), platform facts and incidents, process feedback | Questions, platform issues, improvement |
| **L8 Deliverables** | Publishing to project paths, drift detection | Documents, source code, drawings, etc. |

---

## 3. Roles and Topology

- **Owner:** owns goals, makes decisions at gates and escalations. Talks to the Director (and, when needed, to an SME through it).
- **Director:** any harness with the `baton-director` skill that can reach the runtime by shell (CLI) or MCP. Expert at running processes, routing work and communicating; **never performs step work**.
- **Runtime:** deterministic Python installed on the **runtime host**, the machine where the repo and CLI-harness workers live.
- **Worker:** executes one attempt of one step under one profile; stateless with respect to the run.
- **SMEs:** workers consulted by subject. A **platform** SME is an IT-type expert (it may itself be an agent with its own access) that works with workers, the Director and the owner to resolve infrastructure problems. A **process** SME has Baton and the recipe as its subject.

```
Owner ⇄ Director (local or remote agent)
           │  baton CLI over shell, or MCP
           ▼
       Runtime (runtime host) ── repo: .baton/ (events, CAS, records)
           │  spawn detached supervisor → worker child process (profile env + auth)
           ▼
       Worker (API model | headless agent | human)  →  result/
           │
       Runtime: intake → gates → record → publish → checkpoint commit → completion hook wakes Director
```

**Typical topology:** the Director may be remote (e.g. a cloud chat agent) as long as it can run `baton` on the runtime host through a shell. Because a remote Director's turn can end while work is still running, the runtime wakes it with a completion hook (§8.7). MCP over HTTP is optional, for Directors without shell access.

---

## 4. Layouts

### 4.1 Runtime repository (installed as a pinned tool)

```
baton/
├── pyproject.toml   README.md
├── src/baton/
│   ├── models.py            # pydantic models for everything below
│   ├── data.py              # shipped data lookup; strict YAML (duplicate keys rejected)
│   ├── refs.py              # input-reference grammar (§5.2) parser
│   ├── recipe.py            # load, validate, neutrality lint, per-level plan, group validation
│   ├── vocab.py             # capability vocabulary
│   ├── profiles.py          # worker profiles, secrets, env construction, PATH resolution
│   ├── routing.py           # eligibility, preferences, independence
│   ├── store.py             # event logs (run + project), CAS, SQLite cache rebuild
│   ├── state.py             # the one state machine
│   ├── groups.py            # foreach / repeat_until expansion and aggregate state
│   ├── packet.py            # packet builder (the critical module)
│   ├── intake.py            # result validation, gates, findings
│   ├── supervisor.py        # detached per-dispatch supervisor, markers, deadlines, hooks
│   ├── classify.py          # failure classification rules (data-driven)
│   ├── project.py           # project root, project.yaml, lockfile access, vendoring, profile loading
│   ├── locks.py             # run leases, workspace lock, project lock
│   ├── publish.py           # deliverables + drift
│   ├── adopt.py             # detect, research/seed/baseline helpers
│   ├── sme.py               # expert consultation; platform facts/incidents; process feedback
│   ├── permissions.py       # action permissions
│   ├── gitops.py            # checkpoint commits, pushes
│   ├── redact.py            # secret redaction for anything committed
│   ├── docs.py              # step records, run summaries, explain
│   ├── versions.py          # lockfile, launcher, format versions, migrations
│   ├── engine.py            # the API (§13.1) used by CLI and MCP
│   ├── worker_runner.py     # child-process entrypoint for API workers
│   ├── adapters/            # base, litellm_api, subprocess_harness, claude_code, codex, command, manual
│   ├── cli.py   mcp_server.py   check.py   doctor.py
├── vocab/baton-capabilities-1.yaml
├── formats/baton-recipe-1.schema.json   formats/baton-findings-1.schema.json   # generated from models (§15.3)
├── classify/rules-1.yaml    # failure signal patterns
├── skills/baton-director/SKILL.md   skills/baton-worker/SKILL.md
├── defaults/communication.md        # default owner communication contract (written by `baton init`)
├── examples/recipes/fit-check/   examples/recipes/software-feature/   examples/recipes/backyard-project/
└── tests/
```

### 4.2 Recipe package (shareable, model-neutral)

```
<recipe>/
├── recipe.yaml       # id, version, format version, steps (§5)
├── schemas/*.json    prompts/*.md    templates/*.md.j2    static/…
└── crosswalks/*.yaml # optional, for adopting projects from a known prior process (§11.3)
```

### 4.3 Project (what lives in the adopting repo)

```
<project>/
├── AGENTS.md                         # one-line pointer: "This repo uses Baton; see .agents/skills/baton-director"
├── .agents/skills/baton-director/  .agents/skills/baton-worker/   # vendored by baton init/upgrade
├── .baton/
│   ├── baton.lock                    # runtime version, format versions, vocab version, recipe hashes, step-id signatures (§5.8)
│   ├── project.yaml                  # paths, project vars, permissions, hooks (non-secret), limits, contacts, sme, effort bands
│   ├── communication.md              # owner communication contract (starts as the default)
│   ├── preferences.yaml              # optional routing preferences (non-secret)
│   ├── recipes/<id>@<version>/       # vendored, pinned recipes
│   ├── project/events.jsonl          # project-level events (platform incidents, process feedback)
│   ├── platform/facts.md             # platform facts
│   ├── process/lessons.md            # project-level process lessons
│   ├── runs/<run_id>/                # events.jsonl, cas/, steps/, sme/, docs/
│   ├── workers.local.yaml            # GITIGNORED: project-specific profile overrides
│   └── cache/                        # GITIGNORED: SQLite, running markers, locks
├── <published deliverables at the project's own paths>
└── .gitattributes                    # LFS rules for large blobs and binary deliverables
```

**Principle: commit what the process *is* and what it has *produced*; never commit who runs it or how they pay.**

| Item | Commit? |
|---|---|
| Recipes, lockfile, skills, AGENTS.md pointer, MCP project config (if used) | ✅ |
| `project.yaml`, `communication.md`, `preferences.yaml` | ✅ |
| `.baton/runs/`, `.baton/project/`, `.baton/platform/`, `.baton/process/` | ✅ (redacted) |
| Published deliverables | ✅ |
| Runtime source | ❌ installed and pinned (§14) |
| Worker profiles, secrets, machine-level hooks, raw logs, cache, running markers | ❌ |

### 4.4 Machine-local (never in any repo)

```
~/.baton/
├── workers.yaml      # worker profiles
├── hooks.yaml        # machine-level completion hooks; may reference secrets
├── secrets/          # optional file-based secret store (0700)
├── homes/<profile>/  # optional relocated CLI config homes [VERIFY per CLI]
├── versions/         # installed runtime versions used by the launcher (§14.1)
└── logs/             # unredacted raw worker output
```

---

## 5. Recipes

### 5.1 Example `recipe.yaml`

```yaml
id: software-feature
version: 1
format: baton-recipe/1
capabilities_vocab: baton-capabilities/1
description: Take a feature request to an accepted, tested change.

run_inputs:
  schema: schemas/run_inputs.json      # e.g. title, kind, feature_request

defaults:
  max_attempts: 3

complexity:                            # recipe-owned scale, lowest to highest (§5.5)
  levels: [minor, standard, major]
  triage_step: triage

sme:                                   # optional per-subject expert requirements (§12)
  project: { capabilities: [long_form_writing, technical_reasoning, workspace_read], tier: strong }

steps:
  - id: triage
    title: Assess complexity
    requires: { capabilities: [structured_output, technical_reasoning], tier: standard }
    prompt: prompts/triage.md
    inputs:
      - { name: feature_request, from: run.inputs.feature_request, required: true }
      - { name: research,        from: research.findings,          required: false }   # present on adoption
    output_schema: schemas/triage_out.json        # level + reasons
    gates: [ { type: schema } ]

  - id: requirements
    title: Clarify requirements
    depends_on: [triage]
    applies_to: [standard, major]
    requires: { capabilities: [structured_output, long_form_writing], tier: strong, min_context_tokens: 64000 }
    prompt: prompts/requirements.md
    inputs:
      - { name: feature_request, from: run.inputs.feature_request, required: true }
    output_schema: schemas/requirements_out.json
    artifacts:
      - { name: requirements_doc, required: true, media_type: text/markdown,
          publish: { to: "{{ paths.specs }}/{{ run.slug }}-requirements.md" } }
    gates:
      - { type: schema }
      - { type: human, applies_to: [major], prompt: "Approve requirements before design?" }

  - id: design
    title: Technical design
    depends_on: [requirements]
    applies_to: [major]
    requires: { capabilities: [structured_output, long_form_writing, technical_reasoning], tier: strong }
    prompt: prompts/design.md
    inputs:
      - { name: requirements_doc, from: steps.requirements.artifacts.requirements_doc, required: true }
    output_schema: schemas/design_out.json
    artifacts:
      - { name: design_doc, required: true, media_type: text/markdown,
          publish: { to: "{{ paths.designs }}/{{ run.slug }}-design.md" } }
    gates:
      - { type: schema }
      - type: review                       # §9.2: findings with severities and dispositions
        advisory: true                     # recorded, never blocks
        reviewer_requires: { capabilities: [structured_output, technical_reasoning], tier: strong }
        independence: { from_step: design, level: different_vendor }
        rubric: prompts/design_review_rubric.md

  - id: plan
    title: Plan vertical slices
    depends_on: [design]
    applies_to: [standard, major]
    requires: { capabilities: [structured_output, long_form_writing, technical_reasoning, workspace_read], tier: strong }
    workspace: read
    prompt: prompts/plan.md
    inputs:
      - { name: requirements_doc, from: steps.requirements.artifacts.requirements_doc, required: true }
      - { name: design_doc,       from: steps.design.artifacts.design_doc,             required: true }
    output_schema: schemas/plan_out.json   # slices: [{id, title, outcome, criteria[], effort}]
    gates:
      - { type: schema }
      - type: review
        block_on: [critical, high]
        reviewer_requires: { capabilities: [structured_output, technical_reasoning], tier: strong }
        independence: { from_step: plan, level: different_vendor }
        rubric: prompts/plan_review_rubric.md
      - { type: human, prompt: "Approve the plan and its slices?" }

  - id: slices                             # a group (§5.4)
    title: Deliver each slice
    depends_on: [triage, requirements, design, plan]    # skipped dependencies count as satisfied
    foreach: steps.plan.output.slices
    foreach_if_source_skipped: once        # minor work: one instance with item = run inputs
    concurrency: 1
    repeat_until: group.steps.code_review.gates.passed
    repeat_from: implement
    max_iterations: 3
    steps:
      - id: implement
        effort_from: item.effort           # S | M | L → timeout band (§8.7)
        requires: { capabilities: [tool_use, file_write, shell, code_exec, repo_workspace], tier: strong }
        workspace: write
        protect: ["tests/acceptance/specs/**"]       # §9.4
        prompt: prompts/implement.md
        inputs:
          - { name: slice,           from: item,                              required: true }
          - { name: feature_request, from: run.inputs.feature_request,        required: true }
          - { name: design_doc,      from: steps.design.artifacts.design_doc, required: true }
          - { name: open_findings,   from: group.previous_iteration.findings, required: false }
        output_schema: schemas/implement_out.json    # includes commit_sha
        gates:
          - { type: schema }
          - { type: script, run: "{{ project.test_command }}", timeout_s: 900 }
      - id: code_review
        depends_on: [implement]
        requires: { capabilities: [structured_output, technical_reasoning, workspace_read], tier: strong }
        workspace: read
        independence: { from_step: implement, level: different_vendor }
        prompt: prompts/code_review.md
        inputs:
          - { name: slice,  from: item,                         required: true }
          - { name: change, from: group.steps.implement.output, required: true }
        output_schema: baton:findings      # the runtime-owned findings schema (§9.2)
        gates: [ { type: findings, block_on: [critical, high] } ]
      - id: accept
        depends_on: [code_review]
        requires: { capabilities: [human_judgment] }  # only human profiles have it
        prompt: prompts/slice_acceptance.md            # runnable-now steps only (§13.6)
        inputs:
          - { name: slice,  from: item,                           required: true }
          - { name: review, from: group.steps.code_review.output, required: true }
        output_schema: schemas/acceptance_out.json
```

Step keys: `id`, `title`, `depends_on`, `applies_to`, `requires`, `prompt`, `inputs`, `output_schema`, `artifacts`, `gates`, `workspace` (`none` | `read` | `write`; default `none`), `protect`, `effort` / `effort_from`, `independence`, `doc_template`. Group keys: §5.4.

### 5.2 Input references (closed grammar)

| Reference | Resolves to |
|---|---|
| `run.inputs.<key>` | Validated run input |
| `steps.<id>.output[.<json.path>]` | Output of a passed or imported step |
| `steps.<id>.artifacts.<name>` | CAS blob from a passed or imported step (never the published copy) |
| `steps.<group>.outputs` | List of each instance's final outputs (from outside a group) |
| `item[.<json.path>]` | Inside a `foreach` group: the current item |
| `group.steps.<id>.output` / `.artifacts.<name>` | Inside a group: a sibling's result in the same instance and iteration |
| `group.previous_iteration.findings` | Inside a `repeat_until` group: open findings and gate reasons from the previous iteration |
| `static.<path>` | File shipped in the recipe |
| `human.<decision_id>` | A recorded human decision |
| `human_revision.<step>.<artifact>` | A human edit to a published artifact that was explicitly ingested (§10.5) |
| `research.findings` | Adoption research result (§11.2) |
| `platform.facts` | The project's platform facts (§12.3) |

"Required" applies only when the source step is included at the run's complexity level. Inputs from skipped steps are omitted and listed as `not_applicable` in the manifest. Expert answers are deliberately **not** referenceable; they enter a run only when promoted (§12.2).

### 5.3 Load-time validation and neutrality lint

The loader (`recipe.py`) rejects a recipe unless:
- Every `steps.<id>` reference names an ancestor via `depends_on` (transitively); there are no cycles; files exist; schemas are valid JSON Schema 2020-12.
- Gate types are known; every capability used is in the declared vocabulary.
- `publish.to` uses only `paths.*`, `run.*` and `project.*` variables.
- Complexity: the triage step exists, has no `applies_to`, outputs `level` constrained to the declared levels; every `applies_to` uses declared levels; for each level, every included step is reachable (`baton plan <recipe>` prints the per-level step and gate table).
- Ids: per §5.8 (unique, no positional ids; `foreach` items declare an optional `id`).
- Groups: per §5.4; `item` and `group.*` appear only inside groups; `independence.from_step` names the step itself or an ancestor (in the same group if inside one); `protect` appears only on `workspace: write` steps.
- **Neutrality:** no keys `worker`, `model`, `adapter`, `provider`, `profile`, `api_key`, `auth`; no values matching the vocabulary's vendor denylist. Prompts and templates are scanned too, with warnings only (prose may mention a vendor).

### 5.4 Groups (sub-processes)

A step with its own `steps:` is a group.

| Key | Meaning |
|---|---|
| `foreach` | Array in an ancestor's validated output; one **instance** per item; instance ids are runtime-assigned (§5.8) |
| `foreach_if_source_skipped` | `once` (single instance, `item` = run inputs) or `skip` |
| `concurrency` | Max instances active at once (WIP limit); default 1 |
| `repeat_until` | Condition over gates of steps in the group; if false after an iteration, another starts |
| `repeat_from` | Where a new iteration starts (default: first step) |
| `max_iterations` | Required with `repeat_until` (1–10); reaching it escalates |

Groups nest at most one level. `foreach` and `repeat_until` may be combined (the loop runs per instance). Runtime semantics: §8.5.

**Attempts versus iterations.** An *attempt* retries one step after its own gate fails (tests failed). An *iteration* reruns part of a group because the group's exit condition isn't met (the independent review still has open high findings). Each is bounded separately.

### 5.5 Complexity levels and triage

- The recipe owns its scale and criteria (in the triage prompt). The runtime only applies the result.
- After triage passes (`complexity_set`), every step and gate whose `applies_to` excludes the level is marked `skipped`. Steps without `applies_to` always run. The Director has no say.
- **Re-triage:** `retriage(run, reason)` reruns triage on the current record behind a human gate. On approval, not-yet-started steps are re-evaluated; passed and imported steps never change (their records are flagged "pre-retriage" if the new level would have treated them differently).
- Keep levels few (three is a good default), each visibly different in steps or gates.

### 5.6 Capability vocabulary (`baton-capabilities/1`)

```yaml
id: baton-capabilities/1
capabilities:
  structured_output:   "Reliably returns JSON conforming to a supplied schema"
  long_form_writing:   "Produces coherent multi-page documents"
  technical_reasoning: "Sound multi-step technical analysis"
  tool_use:            "Can call tools / functions"
  file_write:          "Can write files to a given directory"
  shell:               "Can execute shell commands"
  code_exec:           "Can run code and observe results"
  repo_workspace:      "Can operate inside a git working tree and commit"
  workspace_read:      "Can read (not modify) files in a working tree"
  loopback_network:    "Can bind and connect to localhost ports (socket/integration tests)"
  vision:              "Accepts image inputs"
  web_access:          "Can fetch / search the web"
  human_judgment:      "A person: manual verification, acceptance, physical-world work"
tiers: [basic, standard, strong]
numeric:
  min_context_tokens: "Profile context_tokens must be >= this"
sme_defaults:
  project:  { capabilities: [long_form_writing, technical_reasoning], tier: strong }
  platform: { capabilities: [technical_reasoning, shell], tier: strong }
  process:  { capabilities: [long_form_writing, technical_reasoning], tier: strong }
vendor_denylist: ["openai/", "anthropic/", "gpt-", "claude-", "gemini", "grok", "llama", "mistral"]
```

Unknown names are load errors for recipes and profiles. New capabilities mean a new vocabulary version; the runtime supports several side by side.

### 5.7 Shipped example recipes

| Recipe | Purpose | Exercises |
|---|---|---|
| `fit-check` | Decide whether an idea suits Baton, before investing in it | A minimal recipe: one level, no groups, one human gate |
| `software-feature` | The §5.1 example: a feature from request to accepted slices | Complexity levels, groups, reviews, publishing |
| `backyard-project` | A non-software project (a flower bed vs a shed) | Manual workers, photo artifacts, human gates, levels |

**`fit-check`** keeps itself to minutes, or it defeats its purpose:
1. **`describe`:** a worker interviews the owner about the idea, mainly about *each occurrence*: how often it happens, how much judgment it needs, how long it takes, which agents and people are involved, whether a repo audit trail is a benefit. Output: a structured profile of the idea.
2. **`assess`:** scores the profile against a fixed rubric (static file in the recipe):

   | Fits Baton | Fits an operations engine |
   |---|---|
   | Few occurrences (at most daily) | Many (per order, ticket, event) |
   | Judgment-heavy, mixed agents, human sign-offs | Mostly automated, predictable |
   | Minutes to days per occurrence | Seconds; latency matters |
   | Repo audit trail is a benefit | Needs live-system integration, uptime, scale |

   Output: `verdict` (`fits` \| `fits_per_occurrence` \| `operations_engine`), reasons tied to rubric rows, and a suggested next step.
3. **Human gate** on the verdict. Next steps by verdict:
   - `fits`: an existing recipe, or recipe authoring (§15.3).
   - `fits_per_occurrence`: a recipe plus an external scheduler that calls `baton start` for each occurrence.
   - `operations_engine`: start a `software-feature` run whose deliverable is that system, with the engine choice made in its design step.

Because it is small, `fit-check` is also the builder's first end-to-end recipe: with the `manual` adapter it is the Phase 4 toy run, and with an API worker it is the first real run in Phase 5.

### 5.8 Identifiers

Ids name **roles, never positions**. Recipes and plans change over time; an id that encodes order or sequence gets renumbered or reused, and history then attaches to different work. Every rule below exists to keep provenance unambiguous across recipe versions and plan revisions.

- **Step ids** are readable role names (`design`, `code_review`), unique across the whole recipe including groups. The loader rejects positional ids (`step.positional_id`): a positional word (`step`, `stage`, `phase`, `part`, `task`) followed by digits as the whole id or its first segment (`step1`, `phase_3`, `step01_design`); `s` or `p` followed by digits as the whole id (`s2`, `p_3`); or any id ending in `_<digits>` (`review_2`). Role names that merely contain digits (`oauth2_setup`, `s3_upload`) are fine. Readability matters because ids appear in references, step paths, records and the Director's explanations; opaque ids would make recipes hard to author and review.
- **A retired id is never reused** for a different step in a later recipe version. The lockfile records, for every vendored recipe version, its step ids and a per-step signature (kind step/group, enclosing group, output schema hash, required capabilities). When a recipe is vendored or upgraded (§14.2), the runtime compares against all recorded versions and flags: a kept id whose signature changed; an id that was retired and now reappears. Each flag needs an owner decision, recorded with the vendoring.
- **Anything aggregated across runs keys on the qualified id** `<recipe_id>@<version>/<step_path>`, never the bare id: review statistics (§9.2), process statistics and lessons (§12.4), crosswalk targets (§11.3). Inside a run, the run's pinned recipe version and hash (§14.2) qualify every id.
- **`foreach` instance ids are assigned by the runtime**, never by workers. At first expansion each item gets an opaque random token (e.g. `x7f3a9c2`), recorded in `group_expanded`; it is not derived from order or content. The source step's item schema must declare `id` as an *optional* string property and must not require it (`group.foreach_items_need_id`, `group.foreach_id_required`). When the source step is revised, its packet includes the previous items with their ids; the worker echoes the id of every item it keeps (changed or not) and omits `id` on new items. Intake rejects an unknown or duplicated id. People see item titles; the board shows the title with the id.
- **Attempts and iterations** (`attempt-1`, `i1`) are ordinal by nature: append-only, never renumbered or reused, so their order is their meaning.

---

## 6. Worker Profiles and Execution

### 6.1 Profiles (`~/.baton/workers.yaml`, overridable by `.baton/workers.local.yaml`)

```yaml
openai-api-strong:
  adapter: litellm_api
  vendor: openai                       # used for independence checks
  model: "openai/…"                    # [VERIFY current model strings]
  capabilities: [structured_output, long_form_writing, technical_reasoning, tool_use]
  tier: strong
  context_tokens: 200000
  auth: { mode: api_key, env: { OPENAI_API_KEY: "secret:openai_main" } }

codex-sub:
  adapter: codex
  vendor: openai
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }            # the CLI's stored subscription login
  env_deny: [OPENAI_API_KEY, CODEX_API_KEY]   # a stray key could switch billing to the API
  executable: codex                    # the preset's default
  path: { search: [nvm] }
  # args omitted: the codex preset's defaults (§6.3); args.write / args.read / args.none override per mode

claude-code-sub:
  adapter: claude_code
  vendor: anthropic
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, loopback_network, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }
  env_deny: [ANTHROPIC_API_KEY]
  executable: claude
  path: { search: [nvm] }
  args: { write: ["--permission-mode", "bypassPermissions"] }   # the preset's default; shown as an example

owner:
  adapter: manual
  vendor: human
  person: owner
  capabilities: [human_judgment, long_form_writing, vision, file_write]
  tier: strong
```

| Field | Notes |
|---|---|
| `auth.mode` | `api_key` (resolved secrets injected) \| `cli_login` (CLI's stored credentials) \| `none` |
| `env_mode` | `clean` (default for `api_key`) \| `allowlist` (default for `cli_login`; passes `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `LANG`, `TERM` plus `env_allow`) \| `inherit` (escape hatch). `env_deny` is always applied last. |
| `auth.config_home` | Relocated CLI config dir so several logins coexist: `CLAUDE_CONFIG_DIR` for `claude_code`, `CODEX_HOME` for `codex` (both seen in the installed CLIs; switching logins with them is untested) |
| `executable`, `path.search`, `path.prepend` | Harness CLI resolution (§6.2) |
| `args.write` / `args.read` / `args.none` | Adapter args per workspace mode (permission and sandbox modes). Each replaces the preset's built-in default for that mode only (§6.3) |
| `isolation` | `none` \| `user` \| `container` |
| `capabilities` | Must be **true on this machine** (e.g. a sandbox that cannot bind localhost must not claim `loopback_network`) |
| `env_deny` | Exact names or `fnmatch` patterns (`*_API_KEY`); removes a name whatever put it there (inherit, `env_allow`, `auth.env`) |
| `options` | Non-secret adapter options (`litellm_api`: keyword arguments for the completion call, e.g. `base_url`, `temperature`) |
| secrets | `secret:<name>`, allowed only in `auth.env`; resolved at spawn time from the variable `BATON_SECRET_<NAME>` (upper-cased, other characters `_`), then the OS keyring (service `baton`; needs the optional `keyring` package), then the file `~/.baton/secrets/<name>`. A missing secret refuses the dispatch as `configuration`, naming all three places. Never written to packets, events or logs; resolved values are redacted from anything the runtime records |

CLI logins are usually files under the home directory; some platforms use an OS keychain that needs the user's session **[VERIFY]**. `doctor` (§13.4) proves each profile works on each machine.

### 6.2 Environment and PATH

`profiles.build_env(profile)`: start empty (`clean` / `allowlist`) or from the parent (`inherit`); copy allowed variables; build `PATH`; inject resolved secrets for `api_key`; set the config-home variable if any; **remove `env_deny` last**; add `BATON_PACKET_DIR`, `BATON_RESULT_DIR`, `BATON_WORKSPACE` (the last only for workspace steps). Only variable **names** are logged: `dispatched` records the env mode, the names present, the names denied, the names holding secrets and the resolved executable, plus the profile's declared `auth_mode` and the step's `workspace_mode`. On Windows, `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, `TEMP` and `TMP` are always passed, since a child process cannot start without them **[VERIFY]**.

**PATH resolution** is explicit because version-managed CLIs (e.g. Node via nvm) are not on PATH in non-login shells:
1. Absolute `executable` → use it.
2. Found on the base PATH (`path.prepend` + minimal system PATH; `path.prepend` + the parent's PATH under `inherit`) → use it.
3. Each `path.search` source (`~` is the user's home, `HOME`/`USERPROFILE`, never the Baton home) (`nvm` → `$NVM_DIR/versions/node/*/bin`, `~/.nvm/versions/node/*/bin`, newest version first by numeric order, and `$NVM_HOME/v*` for nvm-windows **[VERIFY]**; `pyenv` → `$PYENV_ROOT/versions/*/bin`, `~/.pyenv/versions/*/bin`; `asdf` → `$ASDF_DATA_DIR/shims` or `~/.asdf/shims`; explicit dirs, `~` allowed) → prepend the first dir that has it. Any other source name is a profile load error.
4. Otherwise fail with `executable_not_found` (a **platform** failure, §8.8), listing every place searched (a source whose root does not exist is listed as its pattern).

Resolved locations may be recorded as observed platform facts (§12.3).

### 6.3 Adapters

```python
class WorkerAdapter(Protocol):
    name: str
    def command(self, profile, packet_dir, result_dir, workspace, mode) -> list[str]: ...
    def postprocess(self, profile, packet_dir, result_dir, proc_result) -> None: ...
    failure_signals: list[dict]          # patterns for classification (§8.8)
```

- **`litellm_api`**: runs `python -m baton.worker_runner` as the child (installed with the optional extra `baton[api]`). It builds messages from `INSTRUCTIONS.md` plus the text of every input not already inlined there, requests structured output where `litellm` reports support **[VERIFY per model]** (otherwise the reply schema goes in the prompt), and writes artifacts and `result.json` itself. The model replies with one JSON object: `status`, `output`, `artifacts` (text by declared name), `notes`, `questions_for_human`; a reply that is not a JSON object is a `failed` result (the step's problem, retried). **Inputs too large to inline are a hard error (§18 #1):** a non-UTF-8 input, or messages over `context_tokens × 2` bytes (roughly half the window; 256 KiB when `context_tokens` is not declared). The runtime checks this when dispatching, before anything is recorded, and refuses with a hint to choose a worker that reads files. Failures that are not the step's (authentication, network or provider errors, an unknown model, `litellm` missing) write no result; the child prints one line `baton-worker: failure=<class> code=<code> message=<redacted text>` and exits non-zero.
- **`subprocess_harness`** with presets **`claude_code`** (`claude -p <prompt> <args>`) and **`codex`** (`codex exec <args> --skip-git-repo-check --color never <prompt>`); flags checked against `claude` 2.1.316 and `codex-cli` 0.166.0. Prompt: "Read <packet>/INSTRUCTIONS.md and follow it exactly; write outputs to <result>/ …". `cwd` is the attempt directory for `workspace: none`, the project root for `read` and `write`. `executable` defaults to `claude` / `codex`; `model` is passed as `--model`. The CLI uses its stored login (`auth.mode: cli_login`, env `allowlist`) or an injected key (`api_key`); `auth.mode: none` is a configuration error.
  - **Built-in args per mode** (a profile's `args.<mode>` replaces one mode's default): `claude_code` write `--permission-mode bypassPermissions`, read and none `--permission-mode acceptEdits`; `codex` `--sandbox workspace-write` for every mode.
  - **Read and none steps are enforced by the runtime, not by flags.** The attempt's `result/` lies inside the project, so every mode must allow some writes and no CLI flag confines them to `result/`. For workers that can touch files (harness and `command` adapters), the runtime snapshots the working tree (HEAD, plus every changed or untracked path with its content hash, excluding the attempt directory; ignored files are not seen) before and after the worker runs. Any difference fails the implicit `workspace` gate and **escalates** the step (`workspace_modified`, listing the paths). The runtime never reverts the change; the owner inspects it. Write steps are not checked here (protected paths, §9.4, are).
  - **Failure signals**: lines such as "Not logged in" or "Invalid API key" classify an exit without a result as `platform` / `auth_failed`.
- **`command`**: a configured command line with placeholders (`{prompt_file}`, `{packet}`, `{result}`, `{workspace}`), for other tools or for relaying to another agent. It is split like a POSIX shell would split it (no shell runs it); placeholders are substituted per word (`{workspace}` is empty for `none` steps); the first word is the executable, resolved per §6.2.
- **`manual`**: prints the packet path and waits for `submit`. Used for humans and physical-world work.

Adapters never interpret results; intake does.

---

## 7. The Packet Protocol

### 7.1 Packet (runtime → worker)

```
.baton/runs/<run_id>/steps/<step_path>/attempt-<n>/packet/
├── manifest.json   INSTRUCTIONS.md   output_schema.json
└── inputs/<name>.json | <name>.<ext>
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
- Inputs resolve only from the run's record: run inputs from the CAS blob named in `run_started`, step outputs and artifacts from the hashes in the source step's `step_passed` (or `step_imported`) event. Small JSON inputs (up to 16 KiB) are inlined in `INSTRUCTIONS.md`.
- `prior_feedback`: gate reasons from the previous attempt, or the revision reason (§8.9).

`INSTRUCTIONS.md` contains: role and step title; the rendered step prompt (small JSON inputs inlined, large ones referenced by path); protocol rules (where inputs are, where to write, echo `packet_sha256`, write `result.json` last, do not modify `packet/`, do not modify protected paths); the output schema; prior feedback.

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
  "process_feedback": []
}
```

`status` is `completed`, `blocked` (needs an owner answer) or `failed`. Workers write only inside `result/`, except `workspace: write` steps, whose changes are checked by gates and recorded through `commit_sha` in `output`. `process_feedback` lets workers report friction (§12.4).

---

## 8. Runtime

### 8.1 The state machine

```
blocked_on_deps → ready → dispatched → running → submitted → verifying → passed
                    ↑          │          ├→ timed_out ──────────┤ (classified)
                    │          └──────────┴→ orphaned ───────────┤
                    └── retry (attempt+1) ◄──────────────────────┤ gate failed, attempts < max
                                                                 └→ escalated
ready            → escalated  (no eligible worker, §8.4)
escalated        → ready (after a decision) | abandoned
verifying        ⇄ awaiting_human (human gate)
blocked_on_deps  → skipped    (complexity level)        skipped → blocked_on_deps (approved re-triage)
blocked_on_deps  → imported   (adoption seed)
passed|imported  → superseded (revised)                 passed|imported → stale (an upstream step was revised)
superseded       → ready      (the revised step's new attempt)
stale            → ready | passed (re-run, or confirmed by a human decision)
```

- `skipped` and `imported` satisfy `depends_on`; `stale` and `superseded` do not.
- `escalated` reasons: attempts exhausted, `blocked` result, no eligible worker, iteration limit, platform failure, a read or none step that changed the working tree (`workspace_modified`, §6.3).
- Only `engine.py` performs transitions; each appends exactly one event. Illegal transitions raise. Test every edge.
- A step with no events is `blocked_on_deps`. Attempt numbers are assigned at `dispatched` (previous + 1); `worker_selected` and `packet_built` carry that next number, events about the attempt in flight carry the current one. The attempt budget (`max_attempts`, recorded in `run_started`) restarts whenever a step becomes `ready` other than by retry.

| Edge | Event |
|---|---|
| → `ready` (any source) | `step_ready` |
| `ready` → `dispatched` → `running` → `submitted` | `dispatched`, `step_running`, `result_submitted` |
| `submitted` → `verifying` | `verification_started` |
| `verifying` → `awaiting_human` | `human_gate_opened` |
| `awaiting_human` → `verifying` | `gate_passed` / `gate_failed` (the human gate's outcome; `human_decision` itself is a fact, never a transition) |
| → `passed` | `step_passed` (from `stale`, with the confirming decision in `data`) |
| → `timed_out` / `orphaned` / `escalated` / `abandoned` | `step_timed_out`, `attempt_orphaned`, `step_escalated`, `step_abandoned` |
| → `skipped` / `blocked_on_deps` (from `skipped`) / `imported` | `step_skipped`, `step_unskipped`, `step_imported` |
| → `superseded` / `stale` | `step_revised`, `step_stale` |

Some step events record facts without a transition but are legal only in certain states (`worker_selected`, `packet_built` in `ready`; `deadline_extended` in `running`; `gate_*`, `result_rejected`, `findings_recorded` in `verifying`; `failure_classified` after an attempt ends). Run level: `run_started` is first and once; after `run_completed` or `run_abandoned` no step event is accepted.

### 8.2 Events (the single list)

Every event: `format` (`baton-events/N`), `seq`, `ts`, `run_id` (`null` in the project log), `step_path`, `attempt`, `type`, `actor` (`runtime` / `human` / `worker[:<profile>]` / `director[:<id>]`), `data`, `prev_sha256`, `sha256`.

Each event is one line of canonical JSON (sorted keys, no insignificant whitespace, UTF-8, LF). `sha256` is the SHA-256 of the event's canonical JSON without the `sha256` key; `prev_sha256` is the previous event's `sha256` (`null` first); `seq` starts at 1 with no gaps. Any edit, deletion, insertion or reordering is detectable, including an edit to the last event; only truncation of whole trailing events needs an outside anchor (the checkpoint commits, §10.1). The per-event `format` lets one log hold several versions after a migration (§14.2).

| Area | Event types |
|---|---|
| Run | `run_started` (work item, recipe, versions, branch, `max_attempts`), `run_completed`, `run_abandoned` |
| Leases | `lease_claimed`, `lease_renewed`, `lease_taken_over`, `lease_released` |
| Steps | `step_ready`, `worker_selected`, `packet_built`, `dispatched`, `step_running`, `result_submitted`, `verification_started`, `result_rejected`, `gate_passed`, `gate_failed`, `human_gate_opened`, `step_passed`, `step_escalated`, `step_abandoned`, `step_timed_out`, `attempt_orphaned`, `failure_classified`, `deadline_extended` |
| Tailoring | `complexity_set`, `step_skipped`, `step_unskipped`, `retriage_requested`, `retriage_applied` |
| Groups | `group_expanded`, `iteration_started`, `iteration_limit_reached` |
| Corrections | `step_revised`, `step_stale` |
| Reviews | `findings_recorded`, `finding_dispositioned`, `gate_waived`, `protected_path_modified` |
| Human | `human_decision`, `human_revision_ingested` |
| Deliverables | `artifact_published`, `drift_detected` |
| Adoption | `situation_detected`, `research_recorded`, `step_imported`, `baseline_established` |
| Experts | `sme_requested`, `sme_answered`, `sme_promoted` |
| Machinery | `completion_hook_fired`, `completion_hook_failed`, `checkpoint_committed`, `permission_used`, `permission_requested`, `migrated` |
| Project log | `platform_fact_recorded`, `platform_incident_opened`, `platform_incident_resolved`, `process_feedback`, `step_skip_recorded` |

### 8.3 Store

- Run directory `.baton/runs/<run_id>/`: `events.jsonl`, `cas/<sha[:2]>/<sha>` (atomic writes), `steps/`, `sme/`, `docs/`. Project log: `.baton/project/events.jsonl`.
- SQLite (`.baton/cache/state.db`) is a derived cache; `store.rebuild()` replays events; events always win. Every append is checked by the state machine before it is written, so a log holds only legal sequences; the cache is used only while it matches the log's size, otherwise the run is replayed.
- Large binaries are expected in Git LFS (rules written by `baton init`).

### 8.4 Routing and independence

`eligible_workers(run, step)`:
1. Load profiles (machine, then `.baton/workers.local.yaml`).
2. Keep profiles with all required capabilities, sufficient tier and numeric minimums (`repo_workspace` for write steps, `workspace_read` for read steps).
3. Apply **independence**: if the step or gate declares `independence: {from_step, level}`, exclude profiles that match the worker of `from_step`'s current result at that level (`different_profile` | `different_model` | `different_vendor`). Self-review is refused unless waived (§9.3).
4. Order by `.baton/preferences.yaml` (`prefer.by_step`, `prefer.by_capability`, `exclude`). Preferences reorder or exclude only; they never add an ineligible profile.
5. Return the ordered list with reasons and exclusion reasons. Empty → `escalated` (`no_eligible_worker`; §18 #2: the run never fails for this). `eligible` records the escalation for a ready step; the owner's `decide <step> retry` readies it again once a capable profile exists.

The worker of a result is read from the run's record, not from the current machine: `worker_selected` records the profile name, `vendor` and `model`. For `different_model`, two workers match when they are the same profile or both declare the same `model`; for `different_vendor`, when vendors match case-insensitively. `dispatch` refuses a worker outside the eligible set, with its exclusion reasons. `by_step` keys are step ids or step paths.

### 8.5 Groups at runtime

- **Expansion:** when the `foreach` source passes, the runtime creates one instance per item in array order (`group_expanded`, with item ids and content hashes). Instances start as `concurrency` allows.
- **Re-expansion** after the source is revised, matched by the runtime-assigned ids the worker echoed (§5.8): same id and hash → kept; same id, changed → `stale`; id not echoed → `superseded`; item without an id → added with a new id. Unknown or duplicated ids are rejected at intake.
- **Iteration:** after the group's steps finish, `repeat_until` is evaluated; if false and below `max_iterations`, a new iteration starts at `repeat_from` with `group.previous_iteration.findings`. Earlier iterations stay in the record.
- **Aggregate state:** an instance is `passed` when its last iteration passed; the group is `passed` when all instances are `passed`, `superseded` or `skipped`. `explain` and the board describe it plainly ("3 slices: 2 accepted, 1 in review, iteration 2 of 3").

### 8.6 Packet builder (the critical module)

`build_packet(run, step_path, profile)`:
1. Assert dependencies are satisfied and the profile is eligible (re-checked here, never trusted from the caller).
2. Resolve every input. If any required input is unresolvable, raise `HandoffError` listing **all** missing inputs; write nothing.
3. Copy blobs from CAS (never from published copies); render `INSTRUCTIONS.md`; copy the output schema.
4. Hash, write `manifest.json`, make the packet read-only; record `worker_selected` and `packet_built`.

Property tests: same state + same profile ⇒ same `packet_sha256`; removing any required input ⇒ `HandoffError`.

### 8.7 Dispatch, supervision, completion and timeouts

- **Dispatch** returns once the worker has started, with its dispatch id, effort and deadline (`dispatch(…, wait=true)` / `--wait` blocks until the outcome is recorded). A small **per-dispatch supervisor** (no daemon) is started detached from the caller (POSIX: new session; Windows: detached process group **[VERIFY]**), so a Director's shell ending does not affect it. It receives the worker's constructed environment through a pipe (never written to disk), starts the worker, keeps the running marker, enforces the deadline, runs intake when the worker exits, fires hooks, writes records, makes the checkpoint commit and exits. The supervisor is the runtime finishing work a Director started: it writes events as `runtime` / `worker:<profile>` under a short per-run file lock (`.baton/cache/locks/`) and needs no lease. `wait(run, dispatch_id?, timeout?)` lets an attached Director block until completion. **Manual workers** get no supervisor and no timeout; their packet deadline is informational.
- **Running marker** `.baton/cache/running/<dispatch_id>.json`: host, supervisor and worker PIDs, step path, attempt, started, deadline (and whether it was extended), heartbeat (every 30 s). For `read`/`none` steps the tree snapshot taken before the worker started is kept beside it. Removed after intake and hooks.

| Marker | Process (supervisor) | Result | Meaning |
|---|---|---|---|
| present | alive | – | running (overdue if past deadline) |
| present | dead | written | missed completion → finish intake now |
| present | dead | none | died silently → `orphaned`, classified `platform` / `supervisor_died`, escalated |
| absent | – | intake done | finished |

  Reconciliation (`resume`, `wait`) applies this table on this host (a marker from another host is reported, not judged). A worker still alive under a dead supervisor is terminated first. A running process attempt with no marker counts as a dead supervisor. Hooks fire for outcomes recorded by reconciliation too.
- **Completion hooks** fire after intake on every outcome (passed, gate failed, needs human, timed out, failed), and with outcome `overdue` when a deadline is extended. Project-level (non-secret) hooks go in `project.yaml`; machine-level hooks (may reference `secret:` values, substituted shell-quoted at execution, never logged) go in `~/.baton/hooks.yaml`. When both are configured, both fire. A hook is a shell command line.
  ```yaml
  hooks:
    on_complete: "curl -fsS -m 20 -X POST -d run=$BATON_RUN_ID -d step=$BATON_STEP_PATH -d outcome=$BATON_OUTCOME secret:director_wake_url"
    on_needs_human: ""         # optional; falls back to on_complete
    on_platform_failure: ""    # optional; e.g. wake the platform SME; falls back to on_complete
  ```
  Which hook: a `platform` classification uses `on_platform_failure`; a step now waiting on the owner (human gate or escalation) uses `on_needs_human`; otherwise `on_complete` (§18 #11). Environment: the caller's, plus `BATON_RUN_ID`, `BATON_STEP_PATH`, `BATON_OUTCOME` (`passed` \| `gate_failed` \| `needs_human` \| `timed_out` \| `failed` (ended without a result) \| `overdue`), `BATON_CLASSIFICATION`, `BATON_STEP_STATE` (the step's state after the outcome), `BATON_DISPATCH_ID`, `BATON_REPO`, `BATON_RECORD` (the step record, already regenerated). Each run is recorded as `completion_hook_fired` or `completion_hook_failed` (hook name, source, outcome, exit code; never the command). Hook failures never change outcomes. Detaching with no hook configured prints a warning (the result appears at the next `status`/`board`, or `wait`).
- **Effort and timeouts:** steps declare `effort` (`S` / `M` / `L`) or `effort_from`; a step with neither, or whose `effort_from` does not resolve to one of them, gets `effort.default` (M). Bands come from `project.yaml` (`effort: { bands: {S: 45m, M: 2h, L: 4h}, extend_once: true, default: M }`; durations as `90s`, `45m`, `2h`). The deadline is dispatch time plus the band. At the deadline: if alive and `extend_once` is on (and not yet used), record `deadline_extended {previous_deadline, deadline, band}`, fire the hook with outcome `overdue` and extend by one band; otherwise terminate the worker's process tree, record `step_timed_out` and classify (`subject` / `timeout`; retried while attempts remain).

### 8.8 Failure classification

`classify.py` applies data-driven rules (`classify/rules-1.yaml`, format `baton-classify-rules/1`, plus adapter `failure_signals`), in order:

| Class | Typical signals | Goes to |
|---|---|---|
| `configuration` | Unknown profile, missing secret, invalid project config | Owner, with the exact fix |
| `platform` | Executable not found (exit 127), auth/login failure, sandbox or permission denial on a gate command, network/DNS, disk full, killed by the OS, supervisor died | Platform SME; incident opened (§12.3) |
| `subject` | Gate failed, schema invalid, worker reported `failed`/`blocked`, timed out | Recipe's normal path: retry, iterate, escalate |
| `unknown` | Nothing matched | Platform SME first, then owner |

A platform failure gets at most one automatic retry, and only after the platform SME records a fix; otherwise the step waits on the incident.

A worker process that exits without writing `result.json` records `attempt_orphaned`, then `failure_classified`, then `step_escalated` with the class as its reason. The class comes from, in order: the API runner's failure line; the adapter's `failure_signals`; the rules' output patterns (disk full, DNS, network, TLS, out of memory, sandbox and permission denials); the rules' exit codes (127 `executable_not_found`, 126 `not_executable`) and killing signals (SIGKILL as `killed`); otherwise `unknown` with the last output line. Messages are redacted. A **failed script gate** is classified by exit codes and signals only (a gate command that cannot be found or run is `platform` and escalates; output patterns are not applied, since a test suite may legitimately print them); any other gate failure is `subject`. A worker over its time limit records `step_timed_out` and is retried like a failed gate while attempts remain. Raw worker output goes only to `~/.baton/logs/<run_id>/<step_path>/attempt-<n>.log` (the supervisor's own output beside it, `.supervisor.log`; hook output under `hooks/`).

### 8.9 Work items, concurrency and corrections

- **Runs** are independent work items; `run_started` records `{title, kind, slug, recipe, recipe_sha256, versions, branch, max_attempts, inputs_sha256}` (the validated run inputs are a CAS blob). `baton board` lists all non-terminal runs (position including group progress, running work, pending decisions, lease holder; `--needs-me` filters to pending owner decisions).
- **Locks:** leases are per run (a Director may hold several). Write-mode workspace steps take a project **workspace lock** (one writer per working tree; optional `workspace_isolation: worktree` **[VERIFY merge strategy]**). Git operations and project-level files use a short **project lock**. Checkpoint commits stage only the committing run's files and its own deliverables. Optional `limits.active_runs` in `project.yaml`.
- **`revise(run, step_path, reason)`** (owner-approved): the step gets a new attempt whose packet includes the previous result and the reason; the old result becomes `superseded`; every dependent step in that run becomes `stale`; stale steps are re-run or confirmed unchanged by a human decision; the reason is recorded without blame. Other runs are never affected. Revising a `foreach` source re-expands its group (§8.5).

### 8.10 Intake

1. Check `protocol` and `packet_sha256`; validate `output` against the schema (Draft 2020-12, format checks on).
2. Verify required artifacts; ingest into CAS. Check protected paths (§9.4).
3. `blocked` → `escalated` with the questions. Otherwise run gates in order (blocking gates stop at the first failure; advisory gates always run and record).
4. All blocking gates pass → `step_passed` → publish (§10.4) → record (§10.6) → checkpoint (§10.1) → dependents ready; group bookkeeping (§8.5); hooks fire.

Recording: `result_submitted` carries the hashes of the stored `result.json`, the output and each registered artifact; the implicit provenance check is recorded as a `gate_passed` with `gate: "provenance"`; declared gates are recorded by index. `step_passed` repeats the output and artifact hashes, and is the only thing downstream packets resolve from. Envelope, hash, schema and artifact problems are one `result_rejected` listing every reason. A rejected result, a failed blocking gate, a `failed` worker or a rejected human gate returns the step to `ready` (its reasons become the next packet's `prior_feedback`) while attempts remain, else `escalated` (`attempts_exhausted`). A gate command that cannot be rendered or has a bad `cwd` escalates at once (`configuration`). A human gate's decision is referenced by the step path of the step awaiting it; `human_decision` records the owner's words verbatim, followed by the gate's `gate_passed` / `gate_failed`.

---

## 9. Gates and Reviews

### 9.1 Gate types

| Type | Behaviour | Passes when |
|---|---|---|
| `schema` | Recorded at intake | Output valid |
| `script` | Runs a command (`cwd`, `timeout_s`) under a clean env; output redacted into CAS | Exit 0 |
| `review` | Dispatches a review packet (inputs, result, rubric) to a reviewer chosen with `reviewer_requires` and `independence`; reviewer returns findings (§9.2) | No finding at a `block_on` severity is open |
| `findings` | For a step whose own output is findings (e.g. a code-review step) | Same rule |
| `human` | Step waits in `awaiting_human`; the Director records the owner's decision | Approved |
| `provenance` | Implicit: every referenced artifact was registered through intake | Always enforced |
| `workspace` | Implicit on `read` and `none` steps done by a worker that can touch files (§6.3) | The working tree is unchanged; otherwise the step escalates (`workspace_modified`) |
| `protected` | Implicit on steps with `protect` (§9.4) | No change, or `warn` mode |

Common options: `advisory: true` (records, never blocks); `applies_to: [levels]`; any blocking gate occurrence can be waived (§9.3). Gate reasons and open findings become `prior_feedback` on retry or `group.previous_iteration.findings` in a loop.

### 9.2 Findings and dispositions

Runtime-owned findings schema (`baton:findings`); reviewers must return it, so nothing is parsed from prose:

```json
{
  "findings": [ {"id": "F1", "severity": "high", "location": "src/auth.py:42", "title": "…", "detail": "…", "suggested_fix": "…"} ],
  "coverage": {"complete": true, "notes": ""}
}
```

Severities: `critical | high | medium | low`. `coverage.complete: false` (e.g. a reviewer that could not run socket tests) marks the result "partial" in every record.

| Disposition | Requirement |
|---|---|
| `fixed` | A reference (commit or `file:line`); in a loop, confirmed by the next review iteration |
| `rejected` | Evidence: a `file:line` that exists at the reviewed commit, or a test reference (validated) |
| `accepted-risk` | An owner decision id; nobody else can set it |

Per reviewer profile and qualified step (`<recipe_id>@<version>/<step_path>`, §5.8), the runtime keeps counts by severity and disposition, plus iterations to clean. These feed the process SME and never block.

### 9.3 Waivers

`waive(run, step_path, gate, reason)` needs an owner decision and covers one gate occurrence only (e.g. grandfathering a step approved before a gate existed, or allowing one self-review). It never changes the recipe; waivers show in every dependent record.

### 9.4 Protected files

`protect: [globs]` with `on_violation: warn | fail` (default `warn`). The runtime hashes matching files before and after the worker runs. A change records `protected_path_modified`. In `warn` mode the instance cannot pass until the owner approves or reverts; in `fail` mode the gate fails. An approval gate may record the protected hash set at approval time (e.g. locked acceptance specs), and later steps must preserve it.

---

## 10. Persistence, Handoff and Deliverables

### 10.1 Checkpoint commits

After `step_passed` (with publishing), `human_decision`, `step_escalated`, `run_completed`, `run_abandoned` and `lease_released` (so a handoff travels through git), the runtime stages the run's directory and its published deliverables and commits with a structured message (`baton(<run_id>): <step_path> passed [attempt 1, claude-code-sub]`). One API call makes at most one checkpoint commit, its subject listing each trigger. On by default, to the current branch (`project.yaml` `checkpoints: { commit: true }`; §18 #6).
- Commit SHAs are read back from `git log` on resume, not written into the next event. This keeps commits self-contained. `checkpoint_committed` is appended just before the commit it belongs to (no SHA); if the commit then fails, the next checkpoint carries it.
- Workspace steps commit their own code; their `commit_sha` is in the step output, and the checkpoint commit follows.
- Never commit with unrelated uncommitted changes; refuse and report. The commit names its paths (`git commit --only`), so unstaged or untracked work elsewhere is never swept in; changes *staged* for other paths, a merge/rebase in progress or a missing git identity refuse the checkpoint, which is reported in the call's result and retried at the next trigger.
- Git LFS is optional (§18 #7): with `git lfs` installed, stored blobs at or above `lfs.threshold_mb` (default 5) are listed in the run's own `.gitattributes` before staging.
- Pushing follows action permissions (§13.7); checkpoint commits normally qualify as docs-only.

### 10.2 Leases

A lease is an event `lease_claimed {director_id, harness, host, branch, expires_at}`. Mutating calls on a run require its lease: a free or expired lease is claimed automatically, the holder's lease is renewed (`lease_renewed`) once half its term has passed, and an unexpired lease held by another Director (or by the same Director on another branch) refuses with exit code 3. The term is `project.yaml` `leases.minutes` (default 60; §18 #5). `take_over(reason)` records a takeover (`lease_taken_over`, with the previous holder and the reason); the director skill requires owner approval first, the runtime only requires the reason. The runtime releases the lease when a run completes or is abandoned. The Director identity is `--director` / `BATON_DIRECTOR` (default `<user>@<host>`); the harness name is `BATON_HARNESS`. Leases travel through git, so they coordinate *sequential* handoff. **A run lives on one branch at a time**: continuing it on another branch requires releasing it on the first. Divergent hash chains (two Directors on unsynced clones) are caught by `resume` and `check`, and need owner resolution.

### 10.3 Resume

1. Verify the hash chain and every CAS blob.
2. Rebuild the cache.
3. Reconcile live work with running markers (§8.7): still alive → left running; finished with a result → intake now; otherwise `orphaned`, classified (`platform` / `supervisor_died`) and escalated for an owner decision (`decide <step> retry`).
4. Check published deliverables for drift.
5. Claim the lease, or report the holder.
6. Return status.

A new machine needs only the pinned runtime and its own worker profiles: clone → `baton doctor` → `baton resume <run>`.

### 10.4 Publishing

Artifacts may declare `publish.to` using **logical** path keys mapped in `project.yaml`:

```yaml
paths: { specs: docs/specs, designs: docs/design, plans: docs/plans, drawings: cad/drawings }
project: { test_command: "pytest -q", preflight: "pytest -q --collect-only" }
run_slug: "{{ run.inputs.title | slugify }}"
```

- A missing key is a start-time error.
- Targets must stay inside the project.
- An existing target not last written by Baton with the same hash is a conflict, escalated (overwrite / keep / alternate name) and never overwritten silently.
- Publishing records `artifact_published {path, sha256}`.
- Workspace steps' output *is* the project tree and does not use `publish`.

### 10.5 Two copies and drift

The CAS copy is the immutable record and is always what downstream steps consume. The published copy is the living file. A changed hash gives `drift_detected`, and the owner chooses:
- **Leave it:** downstream keeps the CAS version.
- **Ingest it as a revision:** it enters CAS (`human_revision_ingested`), steps declaring `human_revision.*` inputs (or not-yet-started dependents, if the owner chooses) receive it, and already-passed dependents are flagged possibly stale.

### 10.6 Records and explain

- **Step record** (`docs/<step_path>.md`): worker profile (name and non-secret hash), attempts, inputs with hashes, output, artifacts (CAS hash and published path), gates and findings, waivers, decisions.
- **Run summary** (`docs/SUMMARY.md`): work item, recipe and versions, timeline, per-step table, escalations, leases.
- Both are derived, regenerable and committed.
- `explain(run)` returns **process facts only** (completed, imported and skipped steps; current position; pending decisions; remaining steps at this level and what other levels would add; possible branches). The Director can therefore describe progress without loading subject matter.

---

## 11. Adoption and Triage of Existing Projects

### 11.1 Flow

```
detect (deterministic, silent) ─► doctor (silent if healthy)
   ├─ project with Baton runs ─────────────► board → resume runs → continue
   └─ project without Baton ─► research ─► triage (per in-flight work item) ─► baseline (ONE owner decision) ─► continue
```

`detect()` inspects files, git and event logs and returns the project situation plus, per run, `idle | active_here | active_elsewhere | orphaned_attempts | diverged | drift`, along with machine readiness (`doctor`) and open platform incidents. Healthy situations print one line.

### 11.2 Research

Research gathers **evidence**, not judgment. It is a built-in first step of adoption and answers one question per recipe: *which of this recipe's step outputs already exist here, where, and in what state?* It also covers existing agent configuration, candidate path mappings and candidate commands.
- It is read-only (`workspace: read`, `workspace_read` capability), with a deterministic check that the tree is unchanged.
- Output (`research.findings`): `evidence[] {path, sha256, kind, maps_to?, confidence}`, `work_items[]` (finished, in flight, with positions), `proposed_seeds[]`, `agent_config`, `path_candidates`, `command_candidates`, `gaps[]`.

### 11.3 Crosswalks

For projects run under a known prior process, a crosswalk (shipped with a recipe or kept in the project) maps that process's artifacts and approval records to recipe steps (by qualified id, §5.8), gates and instances. With one, research mostly confirms matches instead of interpreting. It is the single biggest friction reducer for adoption. Crosswalks pass the neutrality lint. (A crosswalk for the owner's `eng-process` is a separate guide.)

### 11.4 Seeding

- A seeded step becomes `imported` (`step_imported`, worker `human`, attested in the baseline).
- Its artifacts enter CAS; its `output` must validate against the step's schema. A nonconforming seed is not imported; the baseline offers to rerun that step.
- Gates that can run on a seed (schema, script) do run. Review and human gates passed outside Baton are imported with their evidence, including findings and dispositions.
- Steps approved before a gate existed get a proposed waiver (§9.3).
- **Groups:** seeding works at the granularity actually reached. The plan is imported, the group is expanded from it, finished instances are imported whole, and a partly finished instance has its completed steps imported while the rest start normally. A pending owner approval stays a pending human gate.
- **Work items:** finished ones stay as history (not seeded). Each in-flight one becomes its own run, triaged and seeded. New ones start normally.

### 11.5 The baseline

One owner decision that ends adoption. It covers:
- proposed `project.yaml` (paths, commands, permissions);
- agent-config merges;
- each in-flight work item with its complexity level and reasons, its seeds and its resulting plan (steps to run or skip);
- proposed waivers;
- known gaps.

It is blameless: it records what exists, what is assumed and what is missing. The owner may edit any part. `establish_baseline` applies it, records the decision verbatim (`baseline_established`) and commits. From then on everything is ordinary Baton.

---

## 12. Experts: Project, Platform and Process

### 12.1 Consulting an expert

`ask_sme(subject, question, refs, run?, mode)` consults an SME worker. Subjects:

| Subject | Expert on | Packet scope the runtime allows |
|---|---|---|
| `project` | The work's domain | Selected run records, published deliverables, `project:<path>` refs |
| `platform` | Development and deployment infrastructure: hosts, CLIs, auth, networks, deployment | Platform facts, open incidents, `doctor` output, redacted run logs, non-secret profile config |
| `process` | Baton and the recipe | Events, records, process feedback, review statistics, the recipe |

- **The Director selects; the runtime assembles.** The Director picks references by name (step names, titles, the recipe) without reading their content. The runtime resolves them into a hashed packet, each item with a neutral provenance label ("approved design, attempt 2", "imported from prior process"), plus an index of everything else on record (titles only).
- **Answer schema:** `{answer, confidence, sources_used[], requested_refs[], suggests_retriage}`. Requested refs lead to an approved follow-up (`sme_followup`) that includes them and the prior turns.
- **Routing:** `eligible_workers` against the recipe's `sme.<subject>`, then `project.yaml` (`sme.<subject>.preferred_profiles`, e.g. a dedicated platform agent), then vocabulary defaults. Any adapter works, including `command` (relay to another agent) and `manual` (a human expert).
- **Modes:** `relay` (default; the Director is the go-between) or `handoff` (the adapter opens a separate session the owner talks to directly; the transcript returns as the answer). A platform SME may need to work directly with a worker, the Director or the owner; it does so in handoff mode, and its conclusions return as a recorded answer.
- **Outside the step graph:** consultation cannot satisfy gates and needs no recipe change.

### 12.2 Isolation and promotion

Answers are recorded (`sme_requested`, `sme_answered`; transcripts in `runs/<id>/sme/` or the project log) but **not referenceable** by steps. They affect the work only through `promote_sme` with the owner's agreement, into one of: a human decision, an artifact revision, a platform fact, or a **process proposal** (recipe or configuration change, applied as a new recipe version and re-vendored, never edited in place).

The Director relays answers faithfully and does not use them for routing. Since state lives in the record, it can resume in a fresh session afterwards; leakage is minimized, though the relayed answer passes through its context once.

### 12.3 The platform area

- **Facts** (`.baton/platform/facts.md`): durable infrastructure knowledge, one entry each with source and date ("codex is under nvm v22 on the runtime host"; "the service listens on 8080 in the container"). Facts come from promotion, owner edits, or runtime observation (resolved executable paths, marked `observed`).
- **Incidents** (project log): opened automatically for `platform`/`unknown` failures, with affected runs and steps, logs and resolution. A step blocked on an incident shows it on the board.
- **Use:** steps may take `platform.facts` as input. Platform SME packets include facts and open incidents automatically. `doctor` reports open incidents. If `on_platform_failure` is configured, the hook can wake the platform SME directly.

### 12.4 The process SME

Process improvement is consultation with `subject=process`, not a separate subsystem.
- **Inputs:** `process_feedback` (friction, skipped step with `informed_owner`, waste, confusing) from Directors, workers or the owner, plus statistics the runtime keeps anyway (attempts, iterations, timeouts and their classes, time per step, review statistics), all keyed by qualified step id (§5.8).
- **When:** on demand, at run completion if the recipe has a retrospective step, or on the owner's cadence.
- **Outputs:** answers and process proposals, each approved by the owner. Project-level lessons go to `.baton/process/lessons.md` ("when X, do Y, because Z", with origin and confirmation count). Lessons confirmed across projects are promoted into the recipe by its maintainer.
- **Immediate surfacing:** a skipped *blocking* gate or human approval is surfaced to the owner by the runtime at once, not left for a retrospective.

---

## 13. The Director Interface

### 13.1 The API (engine; one table)

Every call is available as a CLI command (`--json` output; exit codes 0 ok, 1 problem, 2 usage, 3 lease held elsewhere, 4 needs owner decision) and as an MCP tool.

| Call | Purpose |
|---|---|
| `detect()` | Project and run situations; machine readiness; one line when healthy |
| `board()` | All non-terminal runs, positions, running work, pending decisions |
| `recipes()` / `plan(recipe)` | Vendored recipes; per-level step and gate table |
| `start(recipe, inputs)` | New run (work item); claims its lease |
| `status(run)` / `explain(run)` | State, pending items, findings, drift / process-facts narrative |
| `eligible(run, step_path)` | Ordered eligible profiles with reasons |
| `dispatch(run, step_path, worker, wait=false)` | Build packet, start supervised worker; returns a dispatch id |
| `wait(run, dispatch_id?, timeout?)` | Block until completion (attached Directors) |
| `submit(run, step_path, result_dir)` | For manual/external workers |
| `decide(run, ref, decision, note)` | Record an owner decision verbatim (gates: `approve`/`reject`; escalations: `retry` with a fresh attempt budget, the note becoming the next packet's feedback, or `abandon`; later: questions, baseline items, confirmations of stale steps) |
| `retry(run, step_path, worker?, guidance?)` | New attempt; guidance is additive only |
| `retriage(run, reason)` / `revise(run, step_path, reason)` | Re-triage; correct an earlier step in this run |
| `disposition(run, step_path, finding, disposition, evidence?)` / `waive(run, step_path, gate, reason)` | Reviews (§9) |
| `ingest_revision(run, step_path, artifact)` | Accept a drifted published file (§10.5) |
| `ask_sme(subject, question, refs, run?, mode)` / `sme_followup(…)` / `promote_sme(…)` | Experts (§12) |
| `platform_fact(…)` / `platform_incident(…)` / `feedback(kind, text, run?)` | Project-level records |
| `adopt(recipe, crosswalk?)` / `establish_baseline(decision)` | Adoption (§11) |
| `resume(run)` / `lease(…)` / `abandon(run, reason)` | Continuity |
| `record(run, step_path)` / `summary(run)` / `trace(run)` | Records; readable event tail |
| `doctor(profile?)` / `check()` | Machine readiness (§13.4); repository consistency (§13.5) |
| `init()` / `vendor(recipe_dir)` / `upgrade(to?)` / `migrate()` | Setup and versioning (§14) |

No call lets the Director write step outputs, artifacts or events directly. Quiet by default: `detect`, `doctor`, `resume`, `status` and `check` print one line when healthy.

### 13.2 CLI and MCP

- The CLI is the primary interface for a Director with a shell on the runtime host. It finds the project from `--project` / `BATON_PROJECT` or the nearest directory holding `.baton/project.yaml`; machine-local files come from `BATON_HOME` (default `~/.baton`).
- The MCP server (official Python SDK **[VERIFY]**) exposes the same calls over stdio, with an optional authenticated HTTP transport (bearer secret; localhost or private network) for Directors without shell access.
- Registration per harness **[VERIFY]**: Claude Code `.mcp.json` or `claude mcp add baton -- baton mcp`; Codex `[mcp_servers.baton]` in its config; Hermes `hermes mcp add baton --command "baton mcp"`.

### 13.3 Skills

**`skills/baton-director/SKILL.md`** (Agent Skills format; vendored into projects):

```markdown
---
name: baton-director
description: Run, resume, or adopt Baton work as Director — keep every work item moving, route steps to capable workers, follow long-running work, handle gates, findings and escalations, explain the process in plain language, route questions to the right expert, and keep the owner informed. Use whenever the user asks to start, continue, resume, adopt, check, or ask about Baton work.
---

# Baton Director

You coordinate. You are the expert on the process — not on any step's subject matter, and not on the platform.
Use the `baton` CLI with `--json` on the runtime host, or the equivalent MCP tools.

## Hard rules
- Never perform step work yourself. Every step's output comes from dispatch/submit.
- Never compose or edit a packet. If a step cannot start, report the missing inputs.
- Never fabricate an owner decision, disposition or waiver. Record only the owner's actual words.
- Retry guidance is additive; never restate or summarize inputs.
- Choose workers only from `eligible`. Never edit profiles, preferences, permissions or the lockfile without the owner's instruction.
- Never add, remove, skip or reorder steps or roles. Changes go through retriage or revise.
- Act only within the project's action permissions. `ask` means request it; `deny` means never.

## Each session
1. `detect`, then `doctor`. Silent when healthy; interrupt the owner only for a real problem.
2. `board`. For each run that needs you: resume it. If its lease is held elsewhere, report holder and expiry; take over only with the owner's approval.
3. New work is a new run (`start`, then triage). Never fold unrelated work into an active run.

## Per run
1. `status` → ready steps, running work, pending owner decisions, open findings, drift.
2. Pending owner decision: present the question, the relevant record and options; record the answer verbatim.
3. Ready step: `eligible` → choose (respect preference order unless there is a stated reason) → `dispatch`. Starting work the process already calls for is not a question for the owner.
4. Dispatch returns at once. If you can stay attached, `wait`; otherwise end your turn — the completion hook or the next `board` brings you back. Never treat work as finished until Baton records it.
5. Gate failure: retry while attempts remain (another eligible worker if useful); review loops are handled by the recipe; otherwise escalate.
6. Failure classified `platform` or `unknown`: consult the platform SME with the incident; `configuration`: tell the owner the exact fix.
7. An earlier step was wrong: propose `revise` for this run with the reason. Scope changed: propose `retriage`.
8. Run complete: `summary` → present to the owner; release the lease.

## Questions
- About the process (where things are, what's next): answer from `explain`/`status`/`board`, never from memory. If the record doesn't say, say so.
- Subject matter → `ask_sme project`. Infrastructure, tools, accounts, deployment → `ask_sme platform`. How Baton or the recipe should work → `ask_sme process`.
- Never answer these from your own inference. Say plainly that you'll ask an expert. Choose references by name; don't read subject content to choose them. Relay answers faithfully, labeled as the expert's. Promote only with the owner's agreement. Don't use expert content for routing; after a consultation, prefer resuming fresh.
- Record process friction with `feedback`.

## Talking to the owner
Follow `.baton/communication.md` exactly.
```

**`skills/baton-worker/SKILL.md`**: the packet protocol rules (§7); the meaning of `exit_criteria`, `deadline` and `protected_paths`; "stop and report a mismatch instead of improvising"; report friction in `process_feedback`.

### 13.4 `doctor`

Per machine and profile; silent when healthy (`baton doctor [--profile <name>] [--no-run]`; `--no-run` skips the no-op round trips, which for API profiles are small real model calls).
- Lockfile versus the running runtime version, recipe hashes, supported format and vocabulary versions.
- For each profile: build its exact environment, resolve its executable (§6.2), run a no-op task through its adapter; report auth mode, duration, env names present or denied.
- **Effective auth mode**: what the worker would really use under its exact environment. Harness CLIs are asked (`claude auth status --json`, `codex login status`; a local query, run even with `--no-run`); API profiles report `api_key` with the resolved names; manual profiles `none`. A `cli_login` profile whose CLI would use an API key is a problem (billing would switch; add the key to `env_deny`); one that is not logged in is a problem naming the login command.
- **Gate preflight** for write-capable profiles (harness profiles claiming `repo_workspace`): run `project.preflight` (or the test command) through the worker's own adapter and write-mode args, so a mode that would block gates is caught before a full run is wasted. The worker is asked to run `python -m baton.probe --marker <file> --nonce <n> -- <command>`, which runs the command and writes its exit code to a marker under `.baton/cache/`. The runtime also runs the command itself, as a script gate would. No marker: the mode blocked the command. A different exit code: the sandbox changed its outcome. Either is a problem. Both failing alike is a warning.
- Supervisor can detach (a test supervisor must start in its own session); hooks reachable (valid `hooks.yaml`, `secret:` references resolve, each command's program is found; hooks are never fired); open platform incidents; steps with no eligible profile on this machine.
- WSL repos on `/mnt/c` (warning).

### 13.5 `check`

For pre-commit and CI; needs no network or profiles. Exit 0 when clean, otherwise one `ERROR <path>: <message>` line per problem. Checks:
- hash chains and CAS integrity;
- lockfile versus vendored recipes, and the neutrality lint;
- drift (a warning unless `--strict`);
- no secrets under `.baton/` (sentinels and patterns);
- no impossible states;
- `project.yaml` and `communication.md` present and valid;
- format versions readable by this runtime.

### 13.6 Owner communication contract

`.baton/communication.md` is created from Baton's default at `init` and owned by the project. The Director follows it exactly. The default, adopted from the owner's existing practice:
- **Shape:** brief status (or omit); a labeled list of the owner's actions, one step per line, each pasteable command alone in its own block; then the single decision owed. With nothing to do, one "no action" line.
- **Placeholders** that are not valid shell syntax (`PASTE_TOKEN_HERE`, never `$TOKEN`).
- **First mention** of anything new the owner must do or understand: where it lives (product, UI path, file or CLI), what it does, and the exact value or action.
- **Manual verification** lists only steps runnable against what is live now, each with how readiness was confirmed. Blocked steps say what unblocks them.
- **A reversed default** gets a one-line "Before → After".
- **Risk mitigations the agents propose** are a decision with their cost and a narrower alternative, never absorbed silently.
- Healthy progress is reported briefly or not at all.

`project.yaml` `contacts:` maps roles to people or agents (`owner`, `platform`).

### 13.7 Action permissions

```yaml
permissions:
  push: { docs_only: allow, after_verified: allow, other: ask }   # allow | ask | deny
  tag: ask
  force_push: deny
  merge: deny
  deploy: deny
docs_only_globs: ["docs/**", "**/*.md", ".baton/runs/**", ".baton/platform/**", ".baton/process/**"]
```

The runtime enforces these for its own git operations and records `permission_used`. The Director checks them before acting outside the runtime: `ask` becomes `permission_requested`, and `deny` is never attempted. "Docs only" means every changed path matches the globs.

---

## 14. Versioning and Trying New Versions

### 14.1 What is versioned

| Thing | Version recorded in | Pinned by |
|---|---|---|
| Runtime | `baton.lock` (`runtime`) | project |
| Packet protocol (`baton-packet/N`) | manifests, results | run |
| Event schema (`baton-events/N`) | `run_started`, project log | run |
| Recipe format (`baton-recipe/N`) and recipe version | `recipe.yaml`, lockfile, `run_started` | project; run |
| Capability vocabulary (`baton-capabilities/N`) | recipe, lockfile | project |
| Skills | vendored with the runtime version | project |

**Launcher.** The `baton` command installed on a machine is a thin launcher. It reads `baton.lock` in the current repo and runs that exact runtime version, installing it into `~/.baton/versions/` on first use (e.g. via `uv` **[VERIFY]**). `BATON_VERSION` overrides it for one invocation. Different projects, branches and worktrees on one machine can therefore use different Baton versions without conflict.

### 14.2 Compatibility and migration

- A runtime reads all older format versions it declares as supported, and continues runs started under them.
- A run keeps its recipe version and hash for its whole life. Upgrading a recipe mid-run requires an owner decision and is recorded.
- Vendoring or upgrading a recipe compares its step-id signatures with every version recorded in the lockfile; changed or reused ids need an owner decision (§5.8).
- When a format cannot be read, the runtime refuses and names `baton migrate`. Migration is explicit, previewable (`--dry-run`), recorded (`migrated`), committed separately, and never rewrites earlier events: it appends a migration record and writes new-format files alongside.

### 14.3 Trying a new version on a real project

1. `git worktree add ../<project>-trial -b baton-trial`
2. In the trial worktree: `baton upgrade --to <version>`. This updates the lockfile and re-vendors skills, with no other changes.
3. Run real work there: new work items, or existing runs moved to the branch (release the lease on main first; a run lives on one branch at a time).
4. **Adopt:** merge the branch. New runs merge cleanly because each run has its own directory. **Abandon:** delete the branch and worktree; nothing leaks except machine-local logs.

Recipes are trialed the same way: vendor a new recipe version on a branch, start new work items with it, then merge or discard.

---

## 15. Cross-Platform and Security

### 15.1 Cross-platform

The runtime host may be Linux, macOS, native Windows or WSL.
- Paths are stored and compared in POSIX form; backslashes are accepted on input.
- Text is written as UTF-8 without BOM, with LF endings; a BOM is tolerated on read.
- Git runs with explicit settings (`-c core.autocrlf=false`).
- No shebang reliance: entry points come from the package (`baton`, `python -m baton`, `py -m baton`).
- Detaching and process-tree termination have POSIX and Windows code paths, both tested in CI.
- Directories are `0700` on POSIX, with user-only ACLs on Windows where possible.
- In WSL, keep repos on the Linux filesystem.

### 15.2 Security

- **Vendored recipes are trusted code** (script gates run their commands). Review them before vendoring; `check` and `doctor` verify their hashes.
- Harness workers may have broad permissions; prefer `isolation: container` or a dedicated user for risky work.
- **Everything committed passes `redact.py`.** Raw logs stay in `~/.baton/logs/`. Secrets never enter the project tree, packets or SME packets. Tests prove this with sentinel secrets across the working tree and git history.
- Hooks and `command` adapters run shell commands. Only machine-level configuration may reference secrets; the loader rejects `secret:` in `project.yaml`.
- Action permissions bound what the runtime and Director do to the repo and its remotes. The defaults never merge, deploy or force-push.
- An SME (especially a platform SME) may hold its own credentials outside Baton. Baton gives it facts, incidents and redacted logs, never secrets.


### 15.3 Future: guided process authoring (design implications now)

A planned future use: an agent interviews the owner, finds gaps, and writes a new recipe; process diagrams help the owner review it. This needs no work now, but three implementation choices keep it cheap later:
1. **Define the recipe format by models that emit a JSON Schema** (e.g. pydantic `model_json_schema()`), and publish it with each format version (`baton-recipe/N`), rather than encoding the rules only in loader code. Any agent can then author and pre-check recipes. Cross-reference rules the schema cannot express stay in the loader, with precise error messages.
2. **Make `baton plan` build a structured plan object first, then render it.** Text output today; diagram output (e.g. Mermaid, per complexity level) later becomes a renderer, not a redesign.
3. **Keep the fake adapter general enough to drive whole runs** (scripted outcomes per step, findings, timeouts). A future `baton simulate` (a dry run of any recipe through its branches, loops and levels) then reuses it.

---

## 16. Build Order

One order, core first, then layers in the order real use needs them. Every phase keeps all earlier tests green.

**Phase 1 — Recipes.** Models, recipe loader, validation (§5.3), neutrality lint, vocabulary, complexity validation, group validation, `baton plan`. Formats carry version identifiers from day one.
✅ A valid example loads; at least twelve broken recipes are each rejected with a specific error (including a `model:` key, an unknown capability, a vendor string, a bad `foreach` source, a missing `max_iterations`, an `item` reference outside a group, a positional step id, a `foreach` item schema that requires `id`). A profile claiming an unknown capability is rejected.

**Phase 2 — Event store and state.** Event logs (run and project), hash chains, CAS, the state machine (§8.1), cache rebuild.
✅ Every legal transition passes and every illegal one raises. Deleting the cache and rebuilding gives identical status. A tampered event fails the chain check.

**Phase 3 — Packets and intake.** Packet builder, `INSTRUCTIONS.md`, intake, schema/script/human/provenance gates.
✅ Deterministic `packet_sha256`; a missing required input raises `HandoffError` listing all missing inputs; hash mismatch and schema failure are rejected with reasons; a human gate blocks until decided; unregistered artifacts never satisfy a gate.

**Phase 4 — Core CLI and continuity.** CLI (`--json`, exit codes), manual adapter, records, checkpoint commits, leases, resume, `check`.
✅ The `fit-check` recipe (§5.7) completes entirely by hand through the CLI with the manual adapter, including a forced failure and retry; a fresh clone resumes it; `check` passes clean and fails on a tampered event, a missing blob and a planted secret sentinel.

**Phase 5 — Routing and isolation (L1).** Profiles, env construction, PATH resolution, secrets, routing with preferences and independence, `litellm_api` adapter, `doctor` (no-op runs, executable resolution).
✅ `clean`/`allowlist`/`inherit` produce the expected variable *names*; `env_deny` always wins; a CLI found only under nvm resolves, and a missing one fails as `platform` listing every path searched; secrets never appear under `.baton/` or in git history; a step completes with two different vendors' API models.

**Phase 6 — Harness adapters.** `claude_code`, `codex`, `command`; read/write modes; gate preflight in `doctor`.
✅ In one run, one step runs through a CLI subscription login and another through an API key; `doctor` reports each profile's effective auth mode; a permission mode that blocks the test command is caught by preflight before any real run.

**Phase 7 — Async (L2).** Supervisor, running markers, completion hooks, effort timeouts, classification rules.
✅ A dispatch survives its caller's shell exiting; hooks fire for passed, gate failed, needs human, timed out and crashed; each liveness row in §8.7 is reproduced; an overdue S step is extended once, then terminated and classified; detaching with no hook prints the warning.

**Phase 8 — Groups (L3).**
✅ A three-slice plan expands to three instances run one at a time; a code review with an open high finding starts iteration 2 whose implement packet contains it; `max_iterations` escalates; revising the plan (one slice changed, one added) re-expands correctly; instance ids are runtime-assigned, and a revision echoing an unknown or duplicated id is rejected.

**Phase 9 — Reviews (L4).** Review and findings gates, dispositions, waivers, protected files, independence.
✅ A rejection without valid evidence is refused; `accepted-risk` without an owner decision is refused; a waiver unblocks exactly one occurrence; protected-path changes are caught in `warn` and `fail` modes; a same-vendor code review is refused unless waived; a partial-coverage review shows as partial.

**Phase 10 — Work items (L5).** Concurrent runs, board, workspace and project locks, `revise`.
✅ Two runs of different recipes progress independently in one repo; two write-mode steps from different runs are serialized; checkpoint commits never include another run's files; `revise` on a design marks only that run's dependents stale, and a stale step can be confirmed by decision without rerunning.

**Phase 11 — Tailoring and adoption (L6).** Triage application, `applies_to`, re-triage, `detect`, research, crosswalks, seeding (including groups), baseline.
✅ The backyard recipe at `minor` (flower bed) and `major` (shed) runs different, correct step sets; re-triage adds future steps only. Adoption of a fixture project from a different prior process, using a crosswalk, imports work at the right granularity (including a partly finished slice), refuses a nonconforming seed, and needs exactly **one** owner decision. `detect` on a healthy project prints one line.

**Phase 12 — Experts (L7).** `ask_sme` for all three subjects, follow-ups, promotion, platform facts and incidents, process feedback and statistics.
✅ Packets contain only Director-selected references plus the index, with hashes; a non-promoted answer is unreachable from any step; an `executable_not_found` failure opens an incident and preselects facts and logs for the platform SME; a promoted platform fact appears in the next platform packet; a skipped blocking gate is surfaced to the owner immediately.

**Phase 13 — Deliverables (L8).** Publishing, conflicts, drift, revision ingestion.
✅ Deliverables appear at mapped paths; a pre-existing file is never silently overwritten; editing a published file triggers drift, and ingesting it feeds a later step.

**Phase 14 — Director surface.** MCP server (stdio; optional authenticated HTTP), director and worker skills, communication contract default, action permissions.
✅ The runtime refuses a push that permissions deny and records allowed ones; docs-only changes are recognized; Directors in two different harnesses complete the same recipe with different worker assignments using only CLI or MCP; transcript review shows no Director did step work or answered subject questions itself.

**Phase 15 — Versioning.** Launcher, `upgrade`, `migrate`, compatibility rules.
✅ Two worktrees of one project run two runtime versions side by side on one machine; an old run continues under a newer runtime; an unreadable format is refused with the migrate hint; `migrate --dry-run` changes nothing; the §14.3 trial workflow merges cleanly; vendoring a recipe version that changes a kept step id's signature, or reuses a retired id, requires an owner decision.

**Phase 16 — Real use.** Example recipes `fit-check`, `software-feature` and `backyard-project` (§5.7); a remote-Director scenario.
✅ All three recipes run end-to-end and pass the lint with zero runtime changes. A remote Director with only shell access completes a multi-slice work item across several of its own sessions, woken by hooks, with no owner action beyond the recipe's decisions. The full suite passes on Linux and native Windows CI.

---

## 17. Testing Strategy

- **Unit:** loader and lint, vocabulary, routing and independence, hashing, the state machine, groups, gates and findings, env and PATH construction, classification rules, permissions, publishing and drift.
- **Property-based** (`hypothesis`): packet determinism; required-input removal; any legal event sequence rebuilds to the same state; `foreach` re-expansion is stable for unchanged items.
- **Fake adapter:** scripted good, bad-schema, wrong-hash, blocked, findings, timeout, crash, hang and exit-127 results.
- **Process control:** detachment, process-tree termination and marker liveness on POSIX and Windows.
- **Secret leak:** sentinel secrets through a full run; absent from the working tree and git history.
- **Golden files:** `INSTRUCTIONS.md`, records, summary, `explain` output.
- **Live tests** (opt-in): real API models and harness CLIs.

---

## 18. Open Decisions (ask the owner before choosing)

Suggested answers are in brackets; the guide assumes them until told otherwise.

1. Large inputs for API workers: hard error, auto-chunking, or require a file-capable worker? [hard error] **Decided (2026-11-02):** hard error, as suggested (§6.3).
2. No eligible worker: escalate or fail the run? [escalate] **Decided (2026-11-02):** escalate; the run never fails for this (§8.4).
3. Dispatching independent top-level steps of one run in parallel (beyond groups and concurrent runs)? [allowed, subject to the workspace lock] **Decided (2026-11-02):** allowed, as suggested; write-mode steps are serialized once the workspace lock exists (Phase 10).
4. Who maintains the capability vocabulary and classification rules, and how changes are proposed. **Decided (2026-11-01):** the runtime maintainer; changes are proposed as a PR to the runtime repo that adds a new version file (published versions are never edited).
5. Lease duration and renewal defaults; whether takeover approval is also enforced in the runtime. [1 h, renewed on activity; skill-enforced] **Decided (2026-11-02):** as suggested (§10.2).
6. Automatic checkpoint commits on by default; commit to the current branch or a `baton/<run>` branch? [on; current branch] **Decided (2026-11-02):** as suggested (§10.1).
7. Git LFS: required or optional, and size threshold. [optional; 5 MB] **Decided (2026-11-02):** as suggested; `baton init` notes when git-lfs is missing (§10.1).
8. Triage approval: auto-accept at the lowest level, gate above? [yes; always part of the baseline at adoption] **Decided (2026-11-01):** yes, as suggested; `baton plan` shows the implicit approval gate above the lowest level.
9. Effort bands and `extend_once`. [45 min / 2 h / 4 h; extend once] **Decided (2026-11-02):** as suggested; steps that declare no effort get the M band (`effort.default`); manual workers are never timed out; an extension is recorded as `deadline_extended` (§8.7). The effort scale stays the runtime's fixed `S`/`M`/`L` for now. A possible later change (not built): recipes declare their own ordered effort scale (default `[S, M, L]`), `project.yaml` maps the names to durations, and an unmapped name falls back by position. Effort stays independent of triage complexity levels: levels choose steps and gates, effort budgets one step's time.
10. Worktree isolation for concurrent write-mode steps. [lock only at first]
11. Automatic platform-SME invocation on platform failures. [only when `on_platform_failure` is configured] **Decided (2026-11-02):** as suggested; Baton invokes no SME itself. A `platform` failure fires `on_platform_failure` when configured, otherwise `on_complete` (§8.7).
12. Who may set `fixed` and `rejected`: the next iteration's worker with evidence, or only the Director? [worker with evidence]
13. SME transcript retention: full (redacted) or question and answer only. [full, redacted]
14. Research scope limits before asking the owner to narrow. [10k files / 200 MB]
15. Launcher installation mechanism and how many older format versions a runtime must read. [uv-managed; current and previous]
16. Optional OpenTelemetry export of events. [off]
17. SME handoff mode support per harness. [relay first; handoff per harness later]

---

## 19. Definition of Done

- All phases' acceptance criteria pass, on Linux and native Windows.
- README covers:
  - installing the launcher and `baton init`;
  - writing worker profiles;
  - `doctor` and `check`;
  - authoring a neutral recipe (including groups, complexity levels and reviews);
  - vendoring a recipe;
  - adopting an existing project;
  - resuming on a new machine;
  - trialing a new version on a branch.
- Three example recipes ship (§5.7): `fit-check`, `software-feature` (software) and `backyard-project` (non-software).
- Swapping the Director harness or any worker needs only machine-local configuration. New recipes need no runtime changes.
- Principle checks, demonstrated in Phase 16:
  - after setup, a healthy project produces no routine owner prompts;
  - adoption needs exactly one owner decision;
  - every owner touchpoint is a recipe gate, an escalation or the baseline.
