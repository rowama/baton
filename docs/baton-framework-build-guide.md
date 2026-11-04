# Baton: Build Guide for a Vendor-Neutral, Director-Led Multi-Step Process Framework

> **Revision 4 (consolidation).** Same design as Revision 3, reorganized into one coherent structure: a stated set of principles, a capped concept set with a glossary, a small core plus optional layers, merged duplicate sections, a single event list, a single API table, one build order, and explicit versioning so real projects can trial new Baton versions on a branch. History: Rev 2 (model-neutral recipes, routing, isolation, repo persistence, publishing); Rev 2.1 (renamed from "Relay"); Rev 2.2 (adoption, complexity tailoring, consultation); Rev 3 (work items, sub-processes, async execution, findings reviews, SMEs, platform area, permissions; informed by the owner's `eng-process` and its use on `mmbridge`); Rev 4.1 (2026-11-04: the conversation layer, §13.8, and framing new work, §11.6, built in Phase 17; prompted by the first real-project run, whose `fit-check` exchange was unusable for an owner thinking about a business).
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

1. **Invisible when healthy.** After install, the owner should not notice Baton unless something truly needs them. Checks are silent when fine; owner attention is spent only on real decisions: gates the recipe defines, escalations, the one-time adoption baseline, and choosing work items when a goal is framed.
2. **Friction must pay for itself.** Every setup step, prompt or file the owner touches must save more effort than it costs. Prefer generalizing an existing mechanism over adding a parallel one.
3. **Arbitrarily complex processes, simple runtime.** Recipes can express multi-agent processes of any size (iteration, fan-out, reviews, many concurrent work items). The runtime stays small and conventional: one event log format, one packet protocol, one state machine, no daemon, no server. **Everything that does work is a dispatch of a packet to a worker** (steps, reviews, research, triage, expert consultation); everything else is bookkeeping over the event log.
4. **Evolve by trial.** Runtime, recipes and formats are versioned and pinned per project and per run, so a real project can try a new Baton version on a branch and merge or discard it (§14).
5. **Deterministic machinery, human conversation** (owner decision, 2026-11-04). Two layers, kept separate. The runtime, and everything that crosses into it (packets, results, events, decisions), stays structured and deterministic; explicitly deterministic and explicitly inferential work stay separated, as everywhere else in this guide. The owner's side is a conversation run by the Director, who talks like a good project manager with a stakeholder: plain language in the owner's terms, structure (choices, checklists) where it helps, open talk where that helps, and no Baton vocabulary. The seam between the layers is the **confirm-back** (§13.8): nothing the Director understood from conversation is recorded until the owner confirms it. The owner may be a layperson; nothing in the owner's path assumes otherwise.

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
| **Deliverables in the project** | Documents, drawings, photos, etc. that workers return are published to real project paths; the run holds their provenance. Code that workspace steps write in place is recorded by its commit instead. |
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

Experts (§12) add none either: a *consultation* is a series of SME dispatches (turns); an *incident* is a platform record; a person is reached through a proxy SME, never directly.

Adoption (§11) adds no concept: an *adoption run* is a run of a built-in recipe whose one step is research, a *crosswalk* is a recipe (or project) file, and the *baseline* is one owner decision over a proposal file.

Framing (§11.6) adds none either: a *framing run* is a run of a built-in recipe whose one step proposes work items, and choosing among them is one owner decision.

These concepts are **internal vocabulary**: recipe authors, Directors and the runtime use them; owners never need them. The Director speaks in the owner's terms (§13.8) unless the owner chooses the terse operator style (§13.6).

Machinery that exists but owners and recipe authors never configure per run: supervisor processes, running markers, file locks (per run, project, workspace), the workspace queue (§8.9), the SQLite cache.

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
| **L6 Tailoring and adoption** | Complexity levels, triage, detect, research, crosswalks, seeding, baseline, framing (§11.6) | Existing projects; varied formality; goals that hold several work items |
| **L7 Experts** | SME consultation (project, platform, process), platform facts and incidents, process feedback | Questions, platform issues, improvement |
| **L8 Deliverables** | Publishing to project paths, drift detection | Documents, drawings, photos, etc. returned as artifacts |

---

## 3. Roles and Topology

- **Owner:** owns goals, makes decisions at gates and escalations. Talks to the Director in their own terms (and, when needed, to an SME through it); needs no Baton vocabulary.
- **Director:** any harness with the `baton-director` skill that can reach the runtime by shell (CLI) or MCP. Expert at running processes, routing work and facilitating the owner's decisions, the way a project manager engages a stakeholder (§13.8); impartial; **never performs step work** and never answers subject questions itself.
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
│   ├── reviews.py           # review steps, findings lines and statuses, evidence, waivers, protected files
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
│   ├── versions.py          # lockfile, format families and windows, migrations, upgrade
│   ├── launcher.py          # the `baton` command: runs the version baton.lock pins (§14.1)
│   ├── engine.py            # the API (§13.1) used by CLI and MCP
│   ├── worker_runner.py     # child-process entrypoint for API workers
│   ├── adapters/            # base, litellm_api, subprocess_harness, claude_code, codex, command, manual
│   ├── cli.py   mcp_server.py   check.py   doctor.py
├── vocab/baton-capabilities-1.yaml
├── formats/baton-recipe-1.schema.json   formats/baton-findings-1.schema.json   formats/baton-crosswalk-1.schema.json   # generated from models (§15.3)
├── classify/rules-1.yaml    # failure signal patterns
├── builtin/baton-adopt/     # the built-in adoption recipe (§11.1): research step, baton-research/1 schema
├── builtin/baton-frame/     # the built-in framing recipe (§11.6): frame step, baton-frame/1 schema
├── skills/baton-director/SKILL.md   skills/baton-worker/SKILL.md
├── defaults/communication.md        # default owner communication contract, conversational (written by `baton init`)
├── defaults/communication-operator.md   # the terse operator style, for owners who choose it (§13.6)
├── defaults/labels.yaml     # plain-language labels for decision options (§13.8)
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
├── .agents/skills/baton-director/  .agents/skills/baton-worker/   # vendored by baton init/upgrade (init also writes the AGENTS.md pointer; under adoption the baseline proposes it)
├── .baton/
│   ├── baton.lock                    # runtime version, format versions, vocab version, recipe hashes, step-id signatures (§5.8)
│   ├── project.yaml                  # paths, project vars, permissions, hooks (non-secret), limits, contacts, sme, effort bands
│   ├── communication.md              # owner communication contract (starts as the default)
│   ├── preferences.yaml              # optional routing preferences (non-secret)
│   ├── recipes/<id>@<version>/       # vendored, pinned recipes
│   ├── project/events.jsonl          # project-level events (platform incidents, facts, process feedback)
│   ├── project/sme/<c_id>/  project/cas/   # consultations without a run (§12.1), and their blobs
│   ├── adoption/<run_id>/baseline.yaml  # baseline proposal of an adoption (§11.5)
│   ├── platform/facts.md             # platform facts
│   ├── process/lessons.md            # project-level process lessons
│   ├── process/proposals/            # promoted process proposals (§12.2)
│   ├── runs/<run_id>/                # events.jsonl, cas/, steps/, sme/<c_id>/turn-<n>/ and handoff.md, docs/
│   ├── .gitattributes                # `* -text`: git never converts line endings in hashed files (§15.1)
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
├── mcp.yaml          # `token: secret:<name>`: the bearer token for `baton mcp --http` (§13.2)
├── launcher.yaml     # optional: where the launcher installs runtime versions from (`source`, `extras`, `python`; §14.1)
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
    repeat_until: group.steps.code_review.gates.passed and group.steps.accept.gates.passed
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
        gates:                                         # a judge: rejecting sends the slice back to implement
          - { type: schema }
          - { type: human, prompt: "Accept this slice as done? Rejecting sends it back to implement with your note." }
```

Step keys: `id`, `title`, `depends_on`, `applies_to`, `requires`, `prompt`, `inputs`, `output_schema`, `artifacts`, `gates`, `workspace` (`none` | `read` | `write`; default `none`), `protect`, `effort` / `effort_from`, `independence`, `doc_template`. Group keys: §5.4.

### 5.2 Input references (closed grammar)

| Reference | Resolves to |
|---|---|
| `run.inputs.<key>` | Validated run input |
| `steps.<id>.output[.<json.path>]` | Output of a passed or imported step |
| `steps.<id>.artifacts.<name>` | CAS blob from a passed or imported step (never the published copy) |
| `steps.<group>.outputs` | From outside a group: one entry per live instance in item order, `{id, item, outputs: {<step_id>: output}}`, each step's accepted output in the instance's final iteration (superseded instances left out) |
| `item[.<json.path>]` | Inside a `foreach` group: the current item of the innermost `foreach` instance, with its runtime `id` set (§5.8) |
| `group.steps.<id>.output` / `.artifacts.<name>` | Inside a group: a sibling's result in the same instance and iteration (a sibling listed before `repeat_from` ran only in `i1`, and that result is used) |
| `group.previous_iteration.findings` | Inside a `repeat_until` group: `{iteration, findings, gate_reasons, owner_note?}` from the previous iteration's judges (every finding they returned, each with its `step`; the reasons their gates failed; the owner's note when the iteration started after an iteration-limit `retry`). `not_applicable` in iteration 1 |
| `static.<path>` | File shipped in the recipe |
| `human.<decision_id>` | A recorded human decision (including an expert answer the owner promoted as a decision, §12.2) |
| `human_revision.<step>.<artifact>` | The latest human edit to a published artifact that was explicitly ingested (§10.5); `not_applicable` while none is |
| `research.findings` | Adoption research result (§11.2) |
| `platform.facts` | The project's platform facts (§12.3) |

"Required" applies only when the source step is included at the run's complexity level. Inputs from skipped steps are omitted and listed as `not_applicable` in the manifest. Expert answers are deliberately **not** referenceable; they enter a run only when promoted (§12.2).

### 5.3 Load-time validation and neutrality lint

The loader (`recipe.py`) rejects a recipe unless:
- Every `steps.<id>` reference names an ancestor via `depends_on` (transitively); there are no cycles; files exist; schemas are valid JSON Schema 2020-12.
- Gate types are known; every capability used is in the declared vocabulary.
- `publish.to` uses only `paths.*`, `run.*` (`id`, `slug`, `title`, `kind`, `inputs`) and `project.*` variables, and only on top-level steps (`publish.in_group`, §10.4).
- Complexity: the triage step exists, has no `applies_to`, outputs `level` constrained to the declared levels; every `applies_to` uses declared levels; for each level, every included step is reachable (`baton plan <recipe>` prints the per-level step and gate table).
- Ids: per §5.8 (unique, no positional ids; `foreach` items declare an optional `id`).
- Groups: per §5.4; `item` and `group.*` appear only inside groups; `independence.from_step` names the step itself or an ancestor (in the same group if inside one); `protect` appears only on `workspace: write` steps. With `repeat_from`, every step named in `repeat_until` must be at or after it (`group.judge_not_repeated`), and a step listed before it may not depend on one at or after it (`group.depends_on_repeated`).
- **Neutrality:** no keys `worker`, `model`, `adapter`, `provider`, `profile`, `api_key`, `auth`; no values matching the vocabulary's vendor denylist. Prompts and templates are scanned too, with warnings only (prose may mention a vendor).

### 5.4 Groups (sub-processes)

A step with its own `steps:` is a group.

| Key | Meaning |
|---|---|
| `foreach` | Array in an ancestor's validated output; one **instance** per item; instance ids are runtime-assigned (§5.8) |
| `foreach_if_source_skipped` | `once` (single instance, `item` = run inputs) or `skip` (the group is `skipped`). Required when the source can be skipped |
| `concurrency` | Max instances active at once (WIP limit); default 1. An instance is active from its first iteration until it passes or is abandoned; one escalated at its iteration limit keeps its slot |
| `repeat_until` | Condition over gates of steps in the group (`group.steps.<id>.gates.passed`, joined by `and`); the steps it names are the iteration's **judges** |
| `repeat_from` | Where a new iteration starts (default: first step). An iteration after the first runs `repeat_from` and every step listed after it |
| `max_iterations` | Required with `repeat_until` (1–10); reaching it escalates |

A group without `foreach` has a single instance. Every instance, including that one and the `once` instance, gets a runtime-assigned id (§5.8).

**Judges** (owner decision, 2026-11-02). When a judge's declared blocking gate (findings, review, human or script) fails, the judge did its work and the iteration's work is not done: its result is kept (`step_passed` with `condition.gates_passed: false`), the steps after it in that iteration never start, and the next iteration starts at `repeat_from` carrying the open findings and gate reasons. Rejected results, schema failures, failed workers and timeouts still retry the judge as attempts.

Groups nest at most one level (supported with the same rules). `foreach` and `repeat_until` may be combined (the loop runs per instance). Runtime semantics: §8.5.

**Attempts versus iterations.** An *attempt* retries one step after its own gate fails (tests failed). An *iteration* reruns part of a group because the group's exit condition isn't met (the independent review still has open high findings). Each is bounded separately.

### 5.5 Complexity levels and triage

- The recipe owns its scale and criteria (in the triage prompt). The runtime only applies the result.
- After triage passes (`complexity_set`), every step and gate whose `applies_to` excludes the level is marked `skipped`. Steps without `applies_to` always run. The Director has no say.
- **Approval** (§18 #8): a triage result at the lowest level is applied at once (`complexity_set`, `approval: auto`). Above it, once the triage step's declared gates pass, an implicit human gate (`gate: "triage"`) asks the owner to approve the level; approving records `step_passed` then `complexity_set`. Rejecting fails the gate: triage gets another attempt with the owner's note as feedback (owner decision, 2026-11-02). In a run created by adoption the level is approved by the baseline instead (§11.5). `revise` is refused on the triage step; re-triage is the way to change a level.
- **Skipping:** steps and groups excluded at the level are marked `skipped` as soon as the level is set (`step_skipped {level, cause}`; a group's own path carries it); steps inside groups are marked when their instance's iteration starts. A skipped group's steps never get events.
- **Re-triage** (owner decision, 2026-11-02): `retriage(run, reason)` reruns triage behind a human gate. It records `retriage_requested {reason, previous_level}` and a `step_revised` of the triage step (`retriage: true`; no dependent is made stale), so triage gets a new attempt whose packet holds the previous result and the reason (§7.1); until it is decided, the triage step is not accepted, so nothing that depends on it can start. The new result always waits on the owner (implicit `triage` gate, whatever the level). **Approve:** `step_passed`, `retriage_applied {level, previous_level, decision_seq, skipped, unskipped, pre_retriage}`, then `step_skipped` / `step_unskipped` for every step that has not started: no attempt dispatched (`blocked_on_deps`, `ready` never dispatched, `skipped`), including steps of a live instance's current iteration; an unexpanded group is skipped or unskipped as one. Started, passed and imported steps never change; passed and imported steps the new level would have skipped or gated differently are listed in `pre_retriage` and flagged in their records. **Reject:** the old level stands and the triage step's earlier result is accepted again (`step_passed` repeating it, `retriage_rejected`). Refused while any attempt of the run is in flight, while another re-triage is pending, or before a level is set.
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
1. **`describe`:** a worker profiles the idea, mainly *each occurrence*: how often it happens, how much judgment it needs, how long it takes, which agents and people are involved, whether a repo audit trail is a benefit. Output: a structured profile of the idea. **It infers first** (owner decision, 2026-11-04): it fills the profile from the idea as far as it reasonably can, lists each inference under `assumptions` (`{field, value, basis}`) for the Director to confirm, and asks only about what it cannot infer, as structured questions (§7.2) in the owner's terms. The rubric's words ("occurrence", "audit trail", "live integration") are internal: a question about a water-vending idea asks about opening a site or serving a customer, not about an "occurrence". An idea that holds several kinds of work (setting up a business *and* running it) is not forced into one profile: the worker says so (`status: blocked`, one question offering the parts as options), and the Director suggests framing it (§11.6).
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

**`software-feature`** is the §5.1 recipe exactly, shipped with working prompts and review rubrics. Its slice acceptance is a judge (owner decision, 2026-11-03, found in Phase 16): in the original example `accept` had no gate, so a person answering `accepted: false` still passed the slice; with the human gate in `repeat_until`, rejecting it starts the next iteration at `implement` with the owner's note.

Because it is small, `fit-check` is also the builder's first end-to-end recipe: with the `manual` adapter it is the Phase 4 toy run, and with an API worker it is the first real run in Phase 5.

### 5.8 Identifiers

Ids name **roles, never positions**. Recipes and plans change over time; an id that encodes order or sequence gets renumbered or reused, and history then attaches to different work. Every rule below exists to keep provenance unambiguous across recipe versions and plan revisions.

- **Step ids** are readable role names (`design`, `code_review`), unique across the whole recipe including groups. The loader rejects positional ids (`step.positional_id`): a positional word (`step`, `stage`, `phase`, `part`, `task`) followed by digits as the whole id or its first segment (`step1`, `phase_3`, `step01_design`); `s` or `p` followed by digits as the whole id (`s2`, `p_3`); or any id ending in `_<digits>` (`review_2`). Role names that merely contain digits (`oauth2_setup`, `s3_upload`) are fine. Readability matters because ids appear in references, step paths, records and the Director's explanations; opaque ids would make recipes hard to author and review.
- **A retired id is never reused** for a different step in a later recipe version. The lockfile records, for every vendored recipe version, its step ids and a per-step signature (kind step/group, enclosing group, output schema hash, required capabilities). When a recipe is vendored or upgraded (§14.2), the runtime compares against all recorded versions and flags: a kept id whose signature changed; an id that was retired and now reappears. Each flag needs an owner decision, recorded with the vendoring.
- **Anything aggregated across runs keys on the qualified id** `<recipe_id>@<version>/<step_path>`, never the bare id: review statistics (§9.2), process statistics and lessons (§12.4), crosswalk targets (§11.3). Inside a run, the run's pinned recipe version and hash (§14.2) qualify every id.
- **`foreach` instance ids are assigned by the runtime**, never by workers. At first expansion each item gets an opaque random token (e.g. `x7f3a9c2`), recorded in `group_expanded`; it is not derived from order or content. Groups without `foreach` get one too. The item stored for an instance (what `item` resolves to) carries its id; change detection compares items without it. The source step's item schema must declare `id` as an *optional* string property and must not require it (`group.foreach_items_need_id`, `group.foreach_id_required`). When the source step is revised, its packet includes the previous items with their ids; the worker echoes the id of every item it keeps (changed or not) and omits `id` on new items. Intake rejects an unknown or duplicated id (an id on the first expansion is unknown). People see item titles; the board shows the title with the id.
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

A location found through a `path.search` source is recorded once as an observed platform fact (§12.3).

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
  - **Read and none steps are enforced by the runtime, not by flags.** The attempt's `result/` lies inside the project, so every mode must allow some writes and no CLI flag confines them to `result/`. For workers that can touch files (harness and `command` adapters), the runtime snapshots the working tree (HEAD, plus every changed or untracked path with its content hash, excluding the attempt directory; ignored files are not seen) before and after the worker runs. Any difference fails the implicit `workspace` gate and **escalates** the step (`workspace_modified`, listing the paths). HEAD moving only through Baton's own checkpoint commits (`baton(…): …` subjects, descending from the earlier HEAD; this run's or another's) is not a difference (found in Phase 14: consulting an expert about a just-completed run releases its lease again, and that checkpoint was blamed on the expert). The runtime never reverts the change; the owner inspects it. Write steps are not checked here (protected paths, §9.4, are). The snapshot's `git status` uses the repository's own line-ending settings, not `core.autocrlf=false` (found on Windows CI in Phase 16: files the owner's git committed with `autocrlf=true` are CRLF in the tree and LF in the index, and a forced override reported them modified only when git happened to re-hash them, so two snapshots of an untouched tree could differ); the hashes are of the raw bytes either way.
  - **Failure signals**: lines such as "Not logged in" or "Invalid API key" classify an exit without a result as `platform` / `auth_failed`.
- **`command`**: a configured command line with placeholders (`{prompt_file}`, `{packet}`, `{result}`, `{workspace}`), for other tools or for relaying to another agent. It is split like a POSIX shell would split it (no shell runs it; on Windows a backslash is an ordinary character, so `C:\tools\x.exe` stays intact); placeholders are substituted per word with POSIX-form paths (`{workspace}` is empty for `none` steps); the first word is the executable, resolved per §6.2.
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

`questions_for_human` (owner decision, 2026-11-04) is structured, so the Director can hold a conversation from it without knowing the step's subject:

```json
{"id": "q1", "ask": "Will each site be one machine, or several?", "why": "Sets how much equipment planning is needed",
 "best_guess": "One machine per site at first", "options": [{"id": "one", "label": "One machine"}, {"id": "several", "label": "Several"}],
 "multi_select": false, "priority": "needed"}
```

`id` (unique in the result), `ask` and `why` are required; `best_guess`, `options` (each `{id, label}`), `multi_select` (default false) and `priority` (`needed` | `helpful`, default `needed`) are optional. `ask`, `why` and labels use the owner's terms, never the recipe's internal vocabulary. A bare string is accepted and normalized to `{id: "q<n>", ask: <string>, why: ""}`, so existing workers keep working; intake (§8.10) rejects an entry that is neither. Answers come back confirmed and structured (`prior_feedback.answers`, §13.8).

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
escalated        → ready (after a decision) | abandoned | verifying (a waiver of the held failed gate, §9.3)
verifying        ⇄ awaiting_human (human gate)
blocked_on_deps  → skipped    (complexity level)        skipped → blocked_on_deps (approved re-triage)
ready            → skipped    (approved re-triage; only a step never dispatched)
blocked_on_deps  → imported   (adoption seed)
passed|imported  → superseded (revised)                 passed|imported → stale (an upstream step was revised)
superseded       → ready      (the revised step's new attempt)
stale            → ready | passed (re-run when dispatched, or confirmed by a human decision)
```

- **Review steps** (§9.1) have the path `<step_path>~review` (`~review.<gate index>` when the step has several review gates) and follow the same machine. While one runs, the reviewed step stays `verifying`. Each attempt of the reviewed step gets its own review: a passed review is marked `stale` and readied again.
- `escalated → verifying` (`verification_started`) is legal only for a step holding an attempt (attempt ≥ 1, carried on the event).
- `skipped` and `imported` satisfy `depends_on`; `stale` and `superseded` do not. A group's state is derived, never stored (§8.5).
- A `stale` step is never readied automatically (owner decision, 2026-11-02). Once its dependencies are satisfied it is **runnable**: it is listed with the ready steps, and dispatching it records `step_ready` (`rerun`) before the attempt; or the owner confirms it unchanged (`decide <step> confirm`), which records the decision and a `step_passed` repeating the earlier accepted result (`confirmed`). Confirming is refused until its dependencies are satisfied again. It is not a pending owner decision.
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

Some step events record facts without a transition but are legal only in certain states (`worker_selected`, `packet_built` in `ready`; `deadline_extended` in `running`; `gate_passed`, `gate_failed`, `result_rejected`, `findings_recorded`, `protected_path_modified` in `verifying`; `gate_waived` and `finding_dispositioned` are facts recorded in any state; `failure_classified` after an attempt ends; `dispatch_queued` in `ready`; `dispatch_dequeued` in any state, also after the run ends). Run level: `run_started` is first and once; after `run_completed` or `run_abandoned` no step event is accepted.

### 8.2 Events (the single list)

Every event: `format` (`baton-events/N`), `seq`, `ts`, `run_id` (`null` in the project log), `step_path`, `attempt`, `type`, `actor` (`runtime` / `human` / `worker[:<profile>]` / `director[:<id>]`), `data`, `prev_sha256`, `sha256`.

Each event is one line of canonical JSON (sorted keys, no insignificant whitespace, UTF-8, LF). `sha256` is the SHA-256 of the event's canonical JSON without the `sha256` key; `prev_sha256` is the previous event's `sha256` (`null` first); `seq` starts at 1 with no gaps. Any edit, deletion, insertion or reordering is detectable, including an edit to the last event; only truncation of whole trailing events needs an outside anchor (the checkpoint commits, §10.1). The per-event `format` lets one log hold several versions after a migration (§14.2).

| Area | Event types |
|---|---|
| Run | `run_started` (work item, recipe, versions, branch, `max_attempts`), `run_completed`, `run_abandoned` |
| Leases | `lease_claimed`, `lease_renewed`, `lease_taken_over`, `lease_released` |
| Steps | `step_ready`, `dispatch_queued`, `dispatch_dequeued`, `worker_selected`, `packet_built`, `dispatched`, `step_running`, `result_submitted`, `verification_started`, `result_rejected`, `gate_passed`, `gate_failed`, `human_gate_opened`, `step_passed`, `step_escalated`, `step_abandoned`, `step_timed_out`, `attempt_orphaned`, `failure_classified`, `deadline_extended` |
| Tailoring | `complexity_set` (`level`, `approval` `auto`\|`owner`\|`baseline`, `reasons?`, `decision_seq?`), `step_skipped` / `step_unskipped` (`level`, `cause` `complexity`\|`retriage`), `retriage_requested` (`reason`, `previous_level`), `retriage_applied` (`level`, `previous_level`, `decision_seq`, `skipped`, `unskipped`, `pre_retriage`) |
| Groups | `group_expanded` (on the group path: `mode` `foreach`\|`once`\|`skip`\|`single`, `source`, `source_sha256`, `items` `[{id, sha256, content_sha256, title?}]`, and on re-expansion `kept`/`changed`/`added`/`superseded`), `iteration_started` (on the instance path: `iteration`, `from`, `budget_base`), `iteration_limit_reached` (on the instance path: `iteration`, `max_iterations`, `judged`, `judged_seq`, `reasons`) |
| Corrections | `step_revised`, `step_stale` |
| Reviews | `findings_recorded` (on the recording step: `line`, `gate`, `findings` `[{id, severity, title, location?, status, reopened?, carried?}]`, `counts`, `open`, `blocking`, `partial`, `coverage_notes?`, `reviewed_commit?`, `previous_seq?`, `resolved?`, and for a review gate `review`, `review_attempt`, `reviewer`), `finding_dispositioned` (on the recording step: `line`, `finding`, `evaluation_seq`, `disposition`, `evidence?`, `decision_id?`, `by` `worker`\|`director`\|`owner`, `provisional?`), `gate_waived` (`gate`, `reason`, `decision_id`, `scope` `held`\|`next`, `attempt?`, `judged_seq?`), `protected_path_modified` (`changed`, `mode`) |
| Human | `human_decision`, `human_revision_ingested` (on the step: `artifact`, `path`, `sha256`, `revision`, `feed` `revision_inputs`\|`dependents`, `possibly_stale`, `decision_id`, `source` `drift`\|`sme`) |
| Deliverables | `artifact_published` (on the step: `artifact`, `path`, `sha256`, `attempt`, `passed_seq`, `unchanged?`, `kept?`, `overwrote?`, `alternate?`, `revision?`, `decision_id?`), `drift_detected` (on the step: `artifact`, `path`, `published_sha256`, `current_sha256`) |
| Adoption | `situation_detected` (adoption run: the `detect` result, scope counts), `research_recorded` (§11.1), `step_imported` (§11.4), `baseline_established` (§11.5) |
| Framing | `framing_selected` (framing run: `decision_id`, `selected`, `runs` `[{part, run, recipe}]`, `gaps` `[{part, reason}]`, §11.6); `run_started.framing {run, part}` on each run it starts |
| Answers | `human_decision {kind: answers, answers: [{id, answer, owner_words}], note, decision_id}` (on the step whose questions were answered; precedes the retry it feeds, §13.8) |
| Experts | `sme_requested` (`consultation`, `turn`, `subject`, `mode` `relay`\|`handoff`, `question`, `refs`/`auto`/`attachments` `[{ref, label, path, sha256}]`, `worker`, `vendor`, `model`, `packet_sha256`, `dispatch_id`, `contact?`; a handoff: `path`, `handoff_sha256`), `sme_answered` (`consultation`, `turn`, `status` `answered`\|`rejected`\|`failed`\|`blocked`, `answer_sha256`, `result_sha256`, `confidence`, `sources_used`, `requested_refs`, `suggests_retriage`, `awaiting?`, `artifacts?`, `reasons?`, `classification?`), `sme_promoted` (`consultation`, `turn`, `target`, `note`, `content_sha256`, `decision_id?`, `path?`) |
| Machinery | `completion_hook_fired`, `completion_hook_failed`, `checkpoint_committed`, `permission_used` / `permission_requested` (project log: `action`, `rule`, and for a push `category`, `remote`, `branch`, `upstream`, `commits`, `paths`, `outside_docs?`, `unverified?`; for a Director action `detail?`; `decision_id` when the owner approved an `ask`), `migrated` (run-level, any run state; `family` `events`\|`lock`\|`recipe`, `from`, `to`, `path`; for a log, in that log: `upto_seq`, `upto_sha256`, `sha256` of the upcast copy; for the lockfile or a vendored recipe, in the project log, a recipe also `recipe`, `sha256`, `source_sha256`; §14.2) |
| Project log | `human_decision {kind: permission, action, decision: approve, note, decision_id}` (an owner's approval of an `ask` action, §13.7), `human_decision {kind: vendor, recipe, decision: approve, note, decision_id, flags}` (§14.2), `platform_fact_recorded` (`fact`, `source`, `observed?`), `platform_incident_opened` (`incident`, `run`, `step_path`, `attempt`, `class`, `code`, `message`, `refs`), `platform_incident_resolved` (`incident`, `fix`, `retried`), `process_feedback` (`kind`, `text`, `run?`, `step_path?`, `qualified?`, `gate?`, `informed_owner?`), `step_skip_recorded` (`feedback_seq`, `run`, `step_path`, `gate`, `blocking`, `surfaced`, `informed_owner`); expert events of consultations without a run (§12.1) |

### 8.3 Store

- Run directory `.baton/runs/<run_id>/`: `events.jsonl`, `cas/<sha[:2]>/<sha>` (atomic writes), `steps/`, `sme/`, `docs/`. Project log: `.baton/project/events.jsonl`.
- SQLite (`.baton/cache/state.db`) is a derived cache; `store.rebuild()` replays events; events always win. Every append is checked by the state machine before it is written, so a log holds only legal sequences; the cache is used only while it matches the log's size, otherwise the run is replayed. It is keyed on the runtime version and event format that built it, so another runtime on the same worktree (§14.1) replays the logs itself.
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

Implemented in `groups.py` (derived view) and `engine.refresh` (events). Paths: `<group>/<instance>/i<n>/<step>`; an instance's own path is `<group>/<instance>`.

- **Expansion:** when the group's dependencies are satisfied and the `foreach` source passes, the runtime creates one instance per item in array order (`group_expanded`, with item ids and content hashes; each item stored in CAS). A skipped source follows `foreach_if_source_skipped`. Instances start (`iteration_started`, iteration 1) in item order as `concurrency` allows.
- **Re-expansion** whenever the source's accepted output differs from the one the last expansion was built from (after a revision), matched by the runtime-assigned ids the worker echoed (§5.8): same id and content → kept; same id, changed → the instance's accepted steps (as of its current iteration) become `stale` and re-run in place; id not echoed → `superseded` (its steps never run again and its decisions are no longer pending); item without an id → added with a new id. Unknown or duplicated ids are rejected at intake.
- **Iteration:** when a judge's gate fails (§5.4), the iteration ends and, below `max_iterations`, `iteration_started` begins the next one at `repeat_from` with `group.previous_iteration.findings`. Earlier iterations stay in the record. At the limit, `iteration_limit_reached` escalates the instance: a pending decision with `ref` = the instance path and options `retry` (a fresh budget of `max_iterations`, starting at `repeat_from`; the note reaches the next iteration as `owner_note`) or `abandon` (the instance is abandoned, so the group cannot pass; the owner revises the plan or abandons the run). Accepting the work as is arrives with waivers (§9.3).
- **Current work:** a step inside a group is dispatchable only when every enclosing instance is live and started, the path belongs to the instance's current iteration, each enclosing group's dependencies are met and its expansion is up to date, and the iteration has not been ended by a judge.
- **Aggregate state:** an instance is `not_started`, `active`, `escalated` (iteration limit), `passed` (every step of its current iteration satisfied, no failed judge), `abandoned` or `superseded`. The group is `blocked_on_deps` until expanded, `skipped` (source skipped with `skip`), `passed` when every live instance is `passed` (an empty `foreach` passes at once), else `active`. Status and the run summary describe it plainly ("3 instances: 1 passed, 1 active, 1 not started; Logout: iteration 2 of 3").

### 8.6 Packet builder (the critical module)

`build_packet(run, step_path, profile)`:
1. Assert dependencies are satisfied and the profile is eligible (re-checked here, never trusted from the caller).
2. Resolve every input. If any required input is unresolvable, raise `HandoffError` listing **all** missing inputs; write nothing.
3. Copy blobs from CAS (never from published copies); render `INSTRUCTIONS.md`; copy the output schema.
4. Hash, write `manifest.json`, make the packet read-only; record `worker_selected` and `packet_built`.

Property tests: same state + same profile ⇒ same `packet_sha256`; removing any required input ⇒ `HandoffError`.

### 8.7 Dispatch, supervision, completion and timeouts

- **Dispatch** returns once the worker has started, with its dispatch id, effort and deadline (`dispatch(…, wait=true)` / `--wait` blocks until the outcome is recorded). A small **per-dispatch supervisor** (no daemon) is started detached from the caller (POSIX: new session; Windows: a detached process in its own group that breaks away from the caller's job object, falling back to staying in the job when the job forbids breaking away), so a Director's shell ending does not affect it. It receives the worker's constructed environment through a pipe (never written to disk), starts the worker, keeps the running marker, enforces the deadline, runs intake when the worker exits, fires hooks, writes records, makes the checkpoint commit and exits. The supervisor is the runtime finishing work a Director started: it writes events as `runtime` / `worker:<profile>` under a short per-run file lock (`.baton/cache/locks/`) and needs no lease. `wait(run, dispatch_id?, timeout?)` lets an attached Director block until completion. **Manual workers** get no supervisor and no timeout; their packet deadline is informational.
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
  Which hook: a `platform` classification uses `on_platform_failure`; a step now waiting on the owner (human gate or escalation) uses `on_needs_human`; otherwise `on_complete` (§18 #11). Environment: the caller's, plus `BATON_RUN_ID`, `BATON_STEP_PATH`, `BATON_OUTCOME` (`passed` \| `gate_failed` \| `needs_human` \| `needs_review` (a review step is ready for the Director to dispatch) \| `timed_out` \| `failed` (ended without a result) \| `overdue` \| `not_started` (a queued dispatch was dropped, §8.9) \| `answered` (an expert consultation turn, §12.1; `failed` when it has no answer)), `BATON_CLASSIFICATION`, `BATON_INCIDENT` (the platform incident the outcome opened, §12.3), `BATON_STEP_STATE` (the step's state after the outcome), `BATON_DISPATCH_ID`, `BATON_REPO`, `BATON_RECORD` (the step record, already regenerated). Each run is recorded as `completion_hook_fired` or `completion_hook_failed` (hook name, source, outcome, exit code; never the command). Hook failures never change outcomes. Detaching with no hook configured prints a warning (the result appears at the next `status`/`board`, or `wait`).
- **Effort and timeouts:** steps declare `effort` (`S` / `M` / `L`) or `effort_from`; a step with neither, or whose `effort_from` does not resolve to one of them, gets `effort.default` (M). Bands come from `project.yaml` (`effort: { bands: {S: 45m, M: 2h, L: 4h}, extend_once: true, default: M }`; durations as `90s`, `45m`, `2h`). The deadline is dispatch time plus the band. At the deadline: if alive and `extend_once` is on (and not yet used), record `deadline_extended {previous_deadline, deadline, band}`, fire the hook with outcome `overdue` and extend by one band; otherwise terminate the worker's process tree, record `step_timed_out` and classify (`subject` / `timeout`; retried while attempts remain).

### 8.8 Failure classification

`classify.py` applies data-driven rules (`classify/rules-1.yaml`, format `baton-classify-rules/1`, plus adapter `failure_signals`), in order:

| Class | Typical signals | Goes to |
|---|---|---|
| `configuration` | Unknown profile, missing secret, invalid project config | Owner, with the exact fix |
| `platform` | Executable not found (exit 127), auth/login failure, sandbox or permission denial on a gate command, network/DNS, disk full, killed by the OS, supervisor died | Platform SME; incident opened (§12.3) |
| `subject` | Gate failed, schema invalid, worker reported `failed`/`blocked`, timed out | Recipe's normal path: retry, iterate, escalate |
| `unknown` | Nothing matched | Platform SME first, then owner |

A platform failure gets at most one automatic retry, and only after the platform SME records a fix; otherwise the step waits on the incident. Every `platform` and `unknown` classification opens an incident; resolving it with the fix readies the step once (§12.3).

A worker process that exits without writing `result.json` records `attempt_orphaned`, then `failure_classified`, then `step_escalated` with the class as its reason. The class comes from, in order: the API runner's failure line; the adapter's `failure_signals`; the rules' output patterns (disk full, DNS, network, TLS, out of memory, sandbox and permission denials); the rules' exit codes (127 and cmd.exe's 9009 `executable_not_found`, 126 `not_executable`) and killing signals (SIGKILL as `killed`); otherwise `unknown` with the last output line. Messages are redacted. A **failed script gate** is classified only by rules marked `scope: gate`: exit codes, signals, and output patterns specific enough to mean the command itself could not run (cmd.exe's "is not recognized as an internal or external command", since `cmd /c` then exits 1). Such a gate is `platform` and escalates. General patterns are not applied to gates, since a test suite may legitimately print them. Any other gate failure is `subject`. A worker over its time limit records `step_timed_out` and is retried like a failed gate while attempts remain. Raw worker output goes only to `~/.baton/logs/<run_id>/<step_path>/attempt-<n>.log` (the supervisor's own output beside it, `.supervisor.log`; hook output under `hooks/`).

### 8.9 Work items, concurrency and corrections

- **Runs** are independent work items; `run_started` records `{title, kind, slug, recipe, recipe_sha256, runtime, formats, capabilities_vocab, branch, max_attempts, inputs_sha256}` (the validated run inputs are a CAS blob). `baton board` lists all non-terminal runs (position including group progress, running work, pending decisions, lease holder; `--needs-me` filters to pending owner decisions).
- **Locks:** leases are per run (a Director may hold several). Write-mode workspace steps take a project **workspace lock**: one writer per working tree, across all runs and within one run (§18 #10: lock only; worktree isolation is deferred). Git operations and project-level files use a short **project lock**. Checkpoint commits stage only the committing run's files and its own deliverables, under the project lock. Optional `limits.active_runs` in `project.yaml`: `start` refuses a new run while that many are active.
- **Workspace queue** (owner decision, 2026-11-02). Dispatching a write-mode step while the working tree is held (or while others are already queued) does not fail: the request (run, step, worker, guidance, Director) joins a first-in-first-out queue in `.baton/cache/`, `dispatch_queued {queue_id, worker, holder, position}` is recorded, and the call returns `queued` with the holder. The step stays `ready`; `status` and `board` show it queued. The lock is held from dispatch through intake and gates (a manual worker: until `submit`) and released by whatever ends the attempt: the supervisor after intake, `submit`, or reconciliation (`resume`, `wait`) of a dead supervisor; a holder whose process is gone is treated as released. The releasing process then starts the next entry itself (no daemon): it builds the packet and the worker's environment at that moment from the record and re-checks routing and the lease, as the queuing Director. Starting records `dispatch_dequeued {queue_id, started: true, dispatch_id}`; an entry that can no longer start (the step moved on, the worker is no longer eligible, the run ended, the lease is held elsewhere) is dropped with `dispatch_dequeued {started: false, reason}` and the hook fires with outcome `not_started`. `cancel(run, step_path)` withdraws a queued request; abandoning a run drops its entries. Read and none steps never wait for the lock.
- **`revise(run, step_path, reason)`** (owner-approved; like `take_over`, the runtime requires the reason and the director skill requires the owner's approval): the step gets a new attempt whose packet includes the previous result and the reason (§7.1); the old result becomes `superseded`; every accepted dependent step in that run becomes `stale` (`step_stale`); stale steps, once their dependencies pass, are re-run when dispatched or confirmed unchanged by the owner (§8.1); the reason is recorded without blame. Other runs are never affected. Revising a `foreach` source re-expands its group (§8.5): that group's instances are not marked stale at revision time, re-expansion judges each one. Refused while any dependent attempt is in flight. Built for top-level steps; revising a step inside a group is refused (owner decision, 2026-11-02: deferred; correct in-group work by revising the group's source or through the iteration loop).

### 8.10 Intake

1. Check `protocol` and `packet_sha256`; validate `output` against the schema (Draft 2020-12, format checks on). For a `foreach` source, echoed item ids must be current and unique (§5.8).
2. Verify required artifacts; ingest into CAS. Check a worker's `dispositions` (§7.2, §9.2). Check protected paths (§9.4).
3. `blocked` → `escalated` with the questions, normalized and validated (§7.2). Otherwise run gates in order (blocking gates stop at the first failure; advisory gates always run and record).
4. All blocking gates pass → `step_passed` → publish (§10.4) → record (§10.6) → checkpoint (§10.1) → dependents ready; group bookkeeping (§8.5); hooks fire.

Recording: `result_submitted` carries the hashes of the stored `result.json`, the output and each registered artifact; the implicit provenance check is recorded as a `gate_passed` with `gate: "provenance"`; declared gates are recorded by index. `step_passed` repeats the output and artifact hashes, and is the only thing downstream packets resolve from. Envelope, hash, schema and artifact problems are one `result_rejected` listing every reason. A rejected result, a failed blocking gate (except on a judge, §5.4), a `failed` worker or a rejected human gate returns the step to `ready` (its reasons become the next packet's `prior_feedback`) while attempts remain, else `escalated` (`attempts_exhausted`). A gate command that cannot be rendered or has a bad `cwd` escalates at once (`configuration`). A human gate's decision is referenced by the step path of the step awaiting it; `human_decision` records the owner's words verbatim, followed by the gate's `gate_passed` / `gate_failed`.

---

## 9. Gates and Reviews

### 9.1 Gate types

| Type | Behaviour | Passes when |
|---|---|---|
| `schema` | Recorded at intake | Output valid |
| `script` | Runs a command (`cwd`, `timeout_s`) under a clean env; output redacted into CAS | Exit 0 |
| `review` | The runtime readies a **review step** `<step_path>~review` and the step waits in `verifying`. The Director picks a reviewer from `eligible` (`reviewer_requires`, `independence`) and dispatches it like any step; its packet holds the step's inputs, the result under review and the rubric (§7.1); it returns `baton:findings`. A rejected reviewer result is retried as the review's own attempt; abandoning an escalated review fails this gate | No finding at a `block_on` severity is open (§9.2) |
| `findings` | For a step whose own output is findings (e.g. a code-review step). Records `findings_recorded` | Same rule |
| `human` | Step waits in `awaiting_human`; the Director records the owner's decision | Approved |
| `provenance` | Implicit: every referenced artifact was registered through intake | Always enforced |
| `workspace` | Implicit on `read` and `none` steps done by a worker that can touch files (§6.3) | The working tree is unchanged; otherwise the step escalates (`workspace_modified`) |
| `protected` | Implicit on steps with `protect` (§9.4) | No change; in `warn` mode, the owner approves the change |

Common options: `advisory: true` (records, never blocks); `applies_to: [levels]`; any blocking `script`, `review`, `findings`, `independence` or `protected` occurrence can be waived (§9.3). Gate reasons and open findings become `prior_feedback` on retry or `group.previous_iteration.findings` in a loop.

### 9.2 Findings and dispositions

Runtime-owned findings schema (`baton:findings`); reviewers must return it, so nothing is parsed from prose:

```json
{
  "findings": [ {"id": "F1", "severity": "high", "location": "src/auth.py:42", "title": "…", "detail": "…", "suggested_fix": "…"} ],
  "coverage": {"complete": true, "notes": ""}
}
```

Severities: `critical | high | medium | low`. `coverage.complete: false` (e.g. a reviewer that could not run socket tests) marks the result "partial" in every record.

**Lines and ids.** The repeated evaluations of one review form a *line*: `<step_path>#<gate>` at top level, `<instance path>/<step id>#<gate>` inside a group (the same across iterations). A finding is its line plus the id the reviewer gave it; each reviewer gets the previous evaluation with its dispositions (`prior_findings`, §7.1) and reuses the id of a finding it still sees.

**Statuses.** At each evaluation a reported finding is `open`, except one the owner accepted as a risk at the previous evaluation, which stays `accepted-risk` while it is reported again. A previous finding the new review does not report is `resolved` (a `fixed` or `rejected` claim on it is thereby *confirmed*). A disposition takes effect only at the next evaluation (owner decision, 2026-11-02): nothing waits for dispositions, a failed gate retries or ends the iteration at once, and accepting the current failure as is takes a waiver (§9.3). Only the latest evaluation of a line can be dispositioned.

| Disposition | Requirement |
|---|---|
| `fixed` | A commit that exists, or a `file:line` in the current tree; confirmed by the next review not reporting it |
| `rejected` | A `file:line` that exists at the reviewed commit (the git HEAD recorded when the review was dispatched; the working tree outside git), or a test reference `path::name` whose file exists now and contains the name |
| `accepted-risk` | An owner decision id: `decide <step_path>#<finding> accept-risk --note "<owner's words>"` records the decision and the disposition; `disposition … accepted-risk --evidence <decision id>` cites it. Nobody else can set it |

Set by a worker (in `result.json`, §7.2) or by the Director relaying evidence (`disposition`). A Director's `fixed`/`rejected` closes the finding in the record until a later review reports it again.

**Worker dispositions are provisional** (§18 #12). A worker may set `fixed` or `rejected` in its result with evidence, and intake checks that the evidence exists. That alone never closes a finding: an independent review must confirm it. If the next review re-reports the same finding id, the finding is open again, whatever the worker said. A worker disposition with no later review to confirm it does not close the finding; only the Director (relaying evidence) or the owner can close it there. A worker and a reviewer who keep disagreeing are settled only by the owner, with `accepted-risk` or a waiver; in a loop, the iteration limit escalates the disagreement. A disposition never makes a finding unconditionally closed on a worker's word alone. Mediating disputes is deliberately not built (§18 #18).

Per reviewer profile and qualified step (`<recipe_id>@<version>/<step_path>`, §5.8), the runtime keeps counts by severity and disposition, plus iterations to clean. These feed the process SME and never block. (Everything they need is in `findings_recorded` and `finding_dispositioned`; the statistics are derived on demand for the process SME, §12.4.)

### 9.3 Waivers

`waive(run, step_path, gate, reason)` needs an owner decision and covers one gate occurrence only (e.g. grandfathering a step approved before a gate existed, or allowing one self-review). It never changes the recipe; waivers show in every dependent record.

Owner decisions (2026-11-02):
- **Naming.** `gate` is a declared gate's index, its type when the step declares exactly one of that type, `independence` (the step's own; a review gate's reviewer independence is waived on the review step `<step>~review`) or `protected`. Waivable: `script`, `review` and `findings` gates, `independence`, `protected`. Human gates are decided, not waived; schema failures are rejections.
- **Decision.** As with `revise`, the runtime requires the reason, recorded verbatim as a `human_decision` (`kind: waiver`) followed by `gate_waived`; the director skill requires the owner's approval first.
- **Which occurrence.** The failed occurrence the step still holds, if any (`scope: held`): an escalated step whose last attempt failed this gate (`attempts_exhausted`) resumes verification of that attempt with its later gates; a judge at its iteration limit counts as passed and the iteration goes on (refused when later blocking gates of that judge never ran). Otherwise the next occurrence (`scope: next`): consumed by the next evaluation of that gate whatever its outcome (a would-be failure is recorded as `gate_passed` with `waived` and the reasons; a pass with `waiver_unused`), or for `independence` by the next dispatch of the step, whichever worker is chosen. One pending waiver per step path and gate.

### 9.4 Protected files

`protect: [globs]` (warn) or `protect: {paths: [globs], on_violation: warn | fail}` (default `warn`). Globs use `*`, `?` and `**`, relative to the project root. The runtime hashes matching files (outside `.git` and `.baton`) when the attempt is dispatched (recorded in `dispatched`) and again at intake. A change records `protected_path_modified`. In `warn` mode the step waits on the owner like a human gate (owner decision, 2026-11-02): `approve` keeps the change and the step goes on; `reject` fails the gate (the owner or the next attempt reverts it). In `fail` mode the gate fails. A pending `protected` waiver lets one change through. *Deferred:* an approval gate that records the protected hash set at approval time (e.g. locked acceptance specs) for later steps to preserve.

---

## 10. Persistence, Handoff and Deliverables

### 10.1 Checkpoint commits

After `step_passed` (with publishing), `human_decision`, `step_escalated`, `iteration_limit_reached`, `run_completed`, `run_abandoned` and `lease_released` (so a handoff travels through git), the runtime stages the run's directory and its published deliverables and commits with a structured message (`baton(<run_id>): <step_path> passed [attempt 1, claude-code-sub]`). One API call makes at most one checkpoint commit, its subject listing each trigger. Changed project-level records (`.baton/project/`, `.baton/platform/`, `.baton/process/`) are committed with it; a call that touches no run commits them on their own (`baton(project): …`, §12.2). On by default, to the current branch (`project.yaml` `checkpoints: { commit: true }`; §18 #6).
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

Publishing is for artifacts a worker returns in `result/artifacts/` (documents, drawings, photos). **Workspace steps' output *is* the project tree** (code a coding agent writes and commits in place, recorded by `commit_sha`) and does not use `publish`.

Owner decisions (2026-11-03):
- **Start.** A `paths.*` key a recipe publishes to that `project.yaml` does not map refuses `start` (`configuration.publish_path`). Targets must stay inside the project and outside `.git` and `.baton`.
- **When.** After every `step_passed` of a step with publish artifacts, whatever the route (intake, an approved human gate, a waiver, a confirmed stale step), in the same call and before its checkpoint, so the commit includes the deliverable. Each one records `artifact_published {artifact, path, sha256, attempt, unchanged?}` on the step (`unchanged` when the file already held those bytes and was not rewritten). Imported steps (adoption seeds) are not published: their files already live where the prior process put them. `publish` inside a group is a load error (`publish.in_group`): its targets cannot vary per instance.
- **Conflicts.** Writing is silent only when the target is absent, already holds exactly the artifact's bytes, or was last published (across all runs) by this same run and step and still has the hash Baton wrote (a revised step replacing its own untouched version). Anything else is a conflict: a file Baton never wrote, one another run published, one edited since. The step stays `passed` (downstream steps read CAS, never the published copy), and a pending owner decision `publish:<step_path>.<artifact>` offers `overwrite`, `keep` (the existing file stays; recorded as `artifact_published {kept: true}` with no write) or `alternate` (written beside it as `<stem>.<run_id><suffix>`, or at `--path`, itself checked for conflicts). The run does not complete while a conflict is pending.

### 10.5 Two copies and drift

The CAS copy is the immutable record and is always what downstream steps consume. The published copy is the living file. A changed hash (or a deleted file) is drift.

Owner decisions (2026-11-03):
- **Detection.** `status`, `detect` (situation `drift`) and `check` (a warning; an error under `--strict`) compute it without recording. Any mutating call on the run (including `resume`) records `drift_detected {artifact, path, published_sha256, current_sha256}` on the step once per new hash (`current_sha256: null` for a deleted file). Drift is tracked only while the run is active: once it completes, its published files belong to the project and editing them is normal.
- **Decision.** Drift is a pending owner decision `drift:<step_path>.<artifact>`. It blocks no step but holds run completion (nothing can be ingested after the run ends). The owner chooses:
  - **Leave it:** `decide <run> drift:<step_path>.<artifact> leave --note "<words>"`. Downstream keeps the CAS version; that hash is acknowledged and a later edit is new drift.
  - **Ingest it as a revision:** `ingest_revision(run, step_path, artifact, note, feed?)` (`baton ingest-revision <run> <step_path> <artifact> --note "<words>" [--feed dependents]`) records `human_decision {kind: drift, decision: ingest}` and `human_revision_ingested {artifact, path, sha256, revision, feed, possibly_stale, decision_id, source}`, with the file stored in CAS. A deleted file can only be left.
- **What it feeds.** `human_revision.<step>.<artifact>` resolves to the latest ingested revision; with none it is `not_applicable` (an unedited deliverable is normal, never a missing input). With `feed: dependents`, every dependent of that step that has not started (no attempt dispatched) also receives the latest revision for its `steps.<step>.artifacts.<name>` inputs, labeled as the owner's revision. Passed and imported dependents are flagged *possibly stale* in `status` and their records: a flag only, not the `stale` state; the owner may `revise`.
- **From an expert.** `promote_sme(…, target=revision, artifact=<step_path>.<name>, from?)` ingests an expert's artifact (`--from <name>`) or answer (`--text`) the same way (`source: sme`) and writes it to the published path, with the conflict rule above.

### 10.6 Records and explain

- **Step record** (`docs/<step_path>.md`): worker profile (name and non-secret hash), attempts, inputs with hashes, output, artifacts (CAS hash and published path), deliverables (publishes, kept files, drift, ingested revisions, possibly-stale flags), gates and findings, waivers, decisions.
- **Run summary** (`docs/SUMMARY.md`): work item, recipe and versions, timeline, per-step table, escalations, leases.
- Both are derived, regenerable and committed.
- `explain(run)` returns **process facts only** (completed, imported and skipped steps; current position; pending decisions; remaining steps at this level and what other levels would add or drop; possible branches: owner gates, findings that send work back, iteration limits, a level not yet set). It never includes step outputs, artifacts or run inputs, so the Director can describe progress without loading subject matter. Structured data plus a `text` rendering (golden-tested).

---

## 11. Adoption and Triage of Existing Projects; Framing New Work

### 11.1 Flow

```
detect (deterministic, silent) ─► doctor (silent if healthy)
   ├─ project with Baton runs ─────────────► board → resume runs → continue
   └─ project without Baton ─► research ─► triage (per in-flight work item) ─► baseline (ONE owner decision) ─► continue
```

`detect()` inspects files, git and event logs and returns the project situation (`no_baton`, `baton`, `adopting`) plus, per non-terminal run, `idle | active_here | active_elsewhere | orphaned_attempts | diverged | drift`, along with machine readiness (`doctor` without no-op runs) and open platform incidents. `diverged` is a run whose hash chain or CAS fails verification (e.g. two unsynced clones); `drift` is an otherwise idle run whose published deliverables changed (any run with drift lists the paths and gets a warning, §10.5). It records nothing. Healthy situations print one line.

**Mechanics** (owner decision, 2026-11-02). Adoption is ordinary Baton work, so it needs no new concept:
1. `adopt(recipe, crosswalk?, scope?)` (`baton adopt <recipe ref or dir> [--crosswalk <name or path>] [--scope <path>…]`) runs `init` if `.baton/` is missing, vendors a recipe given as a directory, checks the research scope (§18 #14), and starts an **adoption run**: a run of the runtime's built-in recipe `baton-adopt@1` (shipped in `builtin/`, loaded like a vendored recipe but never vendored). Its run inputs are the target recipe's summary (steps, levels, schemas, artifacts, gates), the crosswalk, the candidate files the runtime matched from it, the scope and the `detect` result; `situation_detected` records the latter. While an adoption run is active, `adopt` returns its status instead of starting another.
2. Its one step, `research` (§11.2), is dispatched by the Director like any step.
3. When research passes, the runtime records it (`research_recorded {research_sha256, runs, gaps}` in the adoption run) and starts one **work-item run** of the target recipe per in-flight work item, with the run inputs research proposed (`run_started.adoption {run, work_item}`, then `research_recorded {research_sha256, work_item}`; `research.findings` resolves to that blob, the research output plus `work_item`). A proposed input that does not validate is a gap, not a run. Until the baseline, a work-item run readies only its triage step; triage applies no level there.
4. The Director dispatches each run's triage. When none is left pending, the runtime writes the **baseline proposal** `.baton/adoption/<adoption run>/baseline.yaml` (§11.5) and the adoption run waits on the owner (pending decision `baseline`).
5. The owner reads it, may edit it, and makes the one decision: `establish_baseline(adoption, note)` (`baton establish-baseline <adoption run> --note "<owner's words>"`).

The adoption run completes when the baseline is established; it is never seeded or triaged itself.

### 11.2 Research

Research gathers **evidence**, not judgment. It is a built-in first step of adoption and answers one question per recipe: *which of this recipe's step outputs already exist here, where, and in what state?* It also covers existing agent configuration, candidate path mappings and candidate commands.
- It is read-only (`workspace: read`, `workspace_read` capability), with a deterministic check that the tree is unchanged.
- **Scope** (§18 #14): the non-ignored files under the scope paths (default: the whole project, never `.git` or `.baton`) are counted before the run starts; over 10,000 files or 200 MB, `adopt` refuses with the counts and asks for `--scope`.
- Output (`research.findings`, runtime-owned schema `baton-research/1`): `evidence[] {path, sha256, kind, maps_to?, confidence}`, `work_items[] {key, title, status (finished | in_flight), position?, inputs?}` (in-flight items carry the proposed run inputs), `proposed_seeds[]` (§11.4), `agent_config[] {path, kind, note?}`, `path_candidates {key: path}`, `command_candidates {name: command}`, `gaps[]`.

### 11.3 Crosswalks

For projects run under a known prior process, a crosswalk (shipped with a recipe or kept in the project) maps that process's artifacts and approval records to recipe steps (by qualified id, §5.8), gates and instances. With one, research mostly confirms matches instead of interpreting. It is the single biggest friction reducer for adoption. Crosswalks pass the neutrality lint. (A crosswalk for the owner's `eng-process` is a separate guide.)

Format `baton-crosswalk/1` (owner decision, 2026-11-02), in `<recipe>/crosswalks/<id>.yaml` (validated when the recipe loads) or anywhere in the project (validated at `adopt`):

```yaml
format: baton-crosswalk/1
id: eng-process
prior_process: "eng-process (feature folders, slice folders, APPROVED files)"
maps:
  - match: "docs/features/*/request.md"        # glob relative to the project root; each * or ** is a capture
    step: software-feature@1/requirements      # qualified step id; in a group: <recipe>@<v>/<group>/<step>
    artifact: requirements_doc                 # or `output: true`, or `gate: <index>` (approval evidence)
    work_item: "{1}"                           # template over the captures: the work item key
  - match: "docs/features/*/slices/*/review.json"
    step: software-feature@1/slices/code_review
    output: true
    work_item: "{1}"
    item: "{2}"                                # in a foreach group: the item's key in the prior process
```

The runtime matches every rule (in scope) and gives research the **candidates**: `{path, sha256, rule, step, artifact | output | gate, work_item, item?}`. A rule naming an unknown step, artifact or gate, or another recipe, is an error.

### 11.4 Seeding

A **seed** (`proposed_seeds[]`) is `{work_item, step, item?, output?, artifacts? {name: path}, evidence? [path], gates? [{gate, evidence [path]}]}`: `step` is a top-level step id or `<group>/<step>`; `item` is the 0-based index of the instance's item in the seeded `foreach` source's output (resolved once, when the baseline is applied, to the runtime-assigned instance id).
- A seeded step becomes `imported` (`step_imported`, actor `human`, attested by the baseline decision). Its data holds the output and artifact hashes (as `step_passed`), the evidence files with hashes and `attested {adoption, decision_id}`.
- Its artifacts enter CAS; its `output` must validate against the step's schema. A nonconforming seed is not imported; the baseline offers to rerun that step. So is a seed whose step is excluded at the work item's level, whose dependencies are neither seeded nor skipped, whose files are missing, or whose item index is out of range.
- Gates that can run on a seed (schema, script) do run, when the proposal is written (a failed script gate refuses the seed). Review, findings and human gates passed outside Baton are imported with their evidence. A script, review or findings gate without evidence gets a proposed waiver (applied as `gate_waived {scope: imported}` with the baseline's decision id). A human gate without evidence is listed as attested by the baseline itself (human gates are decided, never waived).
- Steps approved before a gate existed get a proposed waiver (§9.3).
- **Groups:** seeding works at the granularity actually reached. The plan is imported, the group is expanded from it, finished instances are imported whole, and a partly finished instance has its completed steps imported while the rest start normally. The seeds are kept in the run's `baseline_established`, so an instance that starts later (under `concurrency`) still has its finished steps imported when it starts, in its first iteration only. Seeds reach one level of groups.
- *Not built yet (Phase 11):* a pending owner approval staying a pending human gate. Today a human gate without evidence is listed under `attested` in the baseline, so the owner's baseline decision covers it; to have it asked separately, the owner drops that seed and the step runs normally.
- **Work items:** finished ones stay as history (listed in the baseline, not seeded). Each in-flight one becomes its own run, triaged and seeded. New ones start normally.

### 11.5 The baseline

One owner decision that ends adoption. It covers:
- proposed `project.yaml` (paths, commands; action permissions keep the defaults `init` wrote, §13.7);
- agent-config merges (the `AGENTS.md` pointer line, §4.3, appended or created);
- each in-flight work item with its complexity level and reasons, its seeds and its resulting plan (steps to run or skip);
- proposed waivers;
- known gaps.

It is blameless: it records what exists, what is assumed and what is missing. The proposal is `.baton/adoption/<adoption run>/baseline.yaml` (format `baton-baseline/1`): `adoption`, `recipe`, `research_sha256`, `project_yaml {paths, project}`, `agents_md {path, action: append | create | none}`, `history[]` (finished items), `work_items[] {key, run, title, level, level_reasons, create, seeds[] {step, item?, import, reasons?, output_sha256?, artifacts?, evidence?, gates?}, waivers[] {step, item?, gate, reason}, attested[], plan {run, skip, imported}}`, `gaps[]`, `files {path: sha256}` (every file a seed or evidence reads). The owner may edit any part: change a level (a declared one), drop a seed or waiver (the step then runs), set `create: false` (that run is abandoned), or change the proposed configuration. `establish_baseline` re-checks the file (format, levels, seeds against their schemas; a seed's file whose hash changed since the proposal refuses the whole baseline, naming `adopt` to regenerate it), then applies it in one call: `human_decision {kind: baseline}` with the owner's words verbatim and `baseline_established {baseline_sha256, runs, note}` in the adoption run (its baseline file stored in its CAS); in each work-item run, `baseline_established {adoption, decision_id, level}`, `complexity_set {approval: baseline}`, the skips, the imports in dependency order (group expansions and instance starts interleaved as the record calls for), the waivers; `project.yaml` and `AGENTS.md` updated; one checkpoint commit covering all of it. From then on everything is ordinary Baton.

### 11.6 Framing new work

Owners bring goals, not work items. "Start a pure-water vending business" holds several pieces of work of different kinds: setting up the business, buying sites and equipment, marketing, and running it day to day. Forcing such a goal through one recipe (or one `fit-check` profile) produces questions the owner cannot answer. **Framing** turns the owner's goal into work items they choose from. It is ordinary Baton work, like adoption (§11.1), and adds no concept.

1. `frame(words)` (`baton frame --note "<owner's words>"`) starts a **framing run** of the built-in recipe `baton-frame@1` (in `builtin/`, loaded like `baton-adopt`, never vendored). Its run inputs are the owner's words verbatim and a summary of each vendored recipe (id, description, levels, run-input schema), plus `fit-check`'s rubric. While a framing run awaits its decision, `frame` returns its status instead of starting another.
2. Its one step, `frame`, is dispatched by the Director like any step. Output (`baton-frame/1`): `goal` (the goal restated plainly, for the Director to confirm), `parts[] {id, label, description, kind (project | operations | unclear), proposal {recipe?, inputs?, fit_check?}, reasons}`, `assumptions[]`. `label` and `description` use the owner's terms. A part with a fitting vendored recipe proposes it with run inputs; any other part proposes a `fit-check` run with the part as its idea. Operations (running the business day to day) are not Baton work (§1.3): such a part proposes `fit-check`, whose `operations_engine` verdict leads to a project that builds that system (§5.7). The worker may return `blocked` with questions (§7.2) like any step.
3. The step has an implicit human gate, `select`. The Director confirms the goal, then lets the owner choose any or all parts, in conversation, and confirms back (§13.8). `decide <framing run> frame select --items <part ids> --note "<owner's words>"` records `human_decision` and `framing_selected`, and the runtime starts one run per selected part with its proposed recipe and inputs (`run_started.framing {run, part}`). A proposed input that does not validate, or a recipe no longer vendored, is a gap reported to the owner, not a run. Selecting nothing ends framing with no runs. `reject` with a note retries `frame` with the note as feedback, as for triage (§5.5).
4. The framing run completes when the selection is applied. The runs it started are ordinary work items; each runs its own triage where its recipe has one.

The Director offers framing when an owner states a goal rather than a task, or when a step reports that an idea holds several kinds of work (§5.7). Starting a known recipe directly (`start`) is unchanged.

---

## 12. Experts: Project, Platform and Process

### 12.1 Consulting an expert

`ask_sme(subject, question, refs, run?, mode, worker?, contact?)` consults an SME worker. Subjects, and the references the runtime allows each one (anything else is refused, `sme.ref_not_allowed`):

| Subject | Expert on | References the Director may select |
|---|---|---|
| `project` | The work's domain | `step:<step_path>` (an accepted output and its artifacts), `record:<step_path>`, `summary`, `project:<file>` (a project file, outside `.git` and `.baton`; published deliverables are project files) |
| `platform` | Development and deployment infrastructure: hosts, CLIs, auth, networks, deployment | `facts`, `incident:<id>`, `log:<run_id>:<step_path>[@<attempt>]` (the machine-local worker output, redacted, last 64 KiB), `profile:<name>` (non-secret fields), `doctor` (`--no-run`) |
| `process` | Baton and the recipe | `events`, `record:<step_path>`, `summary`, `feedback`, `stats` (§12.4), `lessons`, `recipe` / `recipe:<id>@<version>` |

`step:`, `record:`, `summary` and `events` name the consultation's run (`--run`); without one they are refused.

- **The Director selects; the runtime assembles.** The Director picks references by name without reading their content. The runtime resolves them into a hashed packet (`baton-packet/1`, `kind: sme`; the same `packet_sha256` formula as §7.1), each item with a neutral provenance label ("accepted Profile the idea, attempt 1: output", "…, imported from prior process", "project file README.md (working tree)"), plus `index.json`: everything else on record that the subject may ask for, by title only. **Platform packets always include** the facts and each open incident with its failed attempt's log ("included automatically"). Everything assembled is redacted (§15.2).
- **Answer schema** (`baton:sme-answer/1`): `{answer, confidence (low|medium|high), sources_used[], requested_refs[], suggests_retriage, awaiting? {who, what}}`. The result envelope is §7.2's; the expert may return artifacts under any names (drafts, notes). A result that does not validate is recorded as `rejected`, a worker that ends without one as `failed` with its classification (§8.8); neither is an answer.
- **Follow-ups:** `sme_followup(consultation, question?, refs?, attach?)` is the next turn, approved by the Director (no owner decision). Its packet carries the earlier turns (each question and answer, the expert's artifacts, earlier attachments) plus the new references and attachments. Requested refs reach the expert only this way.
- **Routing:** the requirements are the recipe's `sme.<subject>` (a consultation about a run), else the vocabulary's `sme_defaults`. Eligible profiles meet them; `project.yaml` `sme.<subject>.preferred_profiles` (e.g. a dedicated platform agent) come first. `--worker` picks one; otherwise the first eligible (a follow-up keeps the previous turn's worker while it is eligible). `sme_eligible(subject, run?)` lists them. Any adapter works except `manual`: **an SME is never a person** (owner decision, 2026-11-03; see *People* below). The packet's workspace mode is `read` when the requirements include `workspace_read`, else `none`, and the working-tree check of §6.3 applies.
- **Execution:** a turn is dispatched like a step: asynchronous under a supervisor (§8.7), with the default effort band as its time limit (never extended), `--wait` / `sme <consultation> --wait` to block, and the completion hook fired with outcome `answered` or `failed` (`BATON_STEP_PATH` is `sme/<consultation>`). It is outside the step state machine: events `sme_requested` and `sme_answered`, no step state.
- **Where it lives:** with a run, `runs/<run_id>/sme/<consultation>/turn-<n>/{packet,result}/`, events in the run log, blobs in its CAS (holding the run's lease, as for any change to a run). Without a run, the same under `.baton/project/sme/`, events in the project log, blobs in `.baton/project/cas/`. Transcripts are kept in full, redacted (§18 #13).
- **Modes** (§18 #17). `relay` (default) is the formal mode: the Director is the go-between and every turn's answer is recorded. `handoff`: when the owner would rather talk to the expert directly, `sme_handoff(consultation)` (or `ask_sme … mode=handoff` to start that way) renders one copy-and-paste prompt **generated by the runtime**, never written by the Director: the expert's role and rules, the assembled material, the questions and earlier turns. It is saved as `<consultation>/handoff.md` and recorded (`sme_requested {mode: handoff, handoff_sha256}`); that file is the whole record, and nothing from the conversation returns except through promotion. The runtime refuses a handoff, with the reason, when the expert relies on capabilities a pasted prompt cannot carry (`shell`, `code_exec`, `workspace_read`, `repo_workspace`, `file_write`: "A pastable handoff is impossible: this expert relies on shell to answer…"), unless the expert is a black box behind the `command` adapter, whose reliance Baton cannot know.
- **People** (owner decision, 2026-11-03). Baton never engages a person as an SME. A person is consulted through a **proxy**: an ordinary expert consultation that names them (`--contact "<name, role, how to reach them>"`, given by the owner per consultation and kept only in that record). The proxy drafts what the owner needs for the exchange (an email, a letter, a talking-points sheet) as artifacts and sets `awaiting {who, what}`; the consultation then shows as `awaiting_reply`. **Proxies draft; they never send.** The person's reply comes back as the next turn: the owner attaches it (`sme-followup <consultation> --attach reply.eml`; stored verbatim, redacted, hashed, labeled "supplied by the owner; the reply of <contact>"), or a proxy with its own access reads it and includes it verbatim as an artifact. Later rounds are further follow-ups. Being a proxy is not a mode: any turn may return owner-facing artifacts and `awaiting`.
- **Outside the step graph:** consultation cannot satisfy gates and needs no recipe change.

### 12.2 Isolation and promotion

Answers are recorded (`sme_requested`, `sme_answered`) but **not referenceable** by steps: no input reference reaches them. They affect the work only through `promote_sme(consultation, target, note, text?, turn?)`, with the owner's agreement in their own words (`--note`, recorded verbatim; the default content is the latest answer, `--text` replaces it, e.g. for something said in a handoff conversation). Targets:

| Target | Records | Then |
|---|---|---|
| `decision` (a consultation about a run) | `human_decision {kind: sme, decision, note, decision_id}` and `sme_promoted` in the run | Steps may take it as `human.<decision_id>` |
| `fact` | `platform_fact_recorded` in the project log, an entry in `.baton/platform/facts.md` | In every later platform packet |
| `lesson` | An entry in `.baton/process/lessons.md` (origin, date, confirmations) | In process packets (`lessons`) |
| `proposal` | `.baton/process/proposals/<consultation>-turn-<n>.md` | Applied by the recipe's maintainer as a new recipe version and re-vendored, never edited in place |
| `revision` (a consultation about a run; `--artifact <step_path>.<name>`, content from `--from <expert artifact>`, `--text` or the answer) | `human_decision {kind: sme, decision: revision}`, `human_revision_ingested {source: sme}`, the file written to the published path (`artifact_published {revision}`), `sme_promoted` | Steps take it as `human_revision.<step>.<artifact>` (or, with `--feed dependents`, in place of the artifact, §10.5). Refused while that file has drifted |
 Project-level records written without a run are committed by a project checkpoint (`baton(project): …`); otherwise they ride along with the run's next checkpoint (§10.1).

The Director relays answers faithfully and does not use them for routing. Since state lives in the record, it can resume in a fresh session afterwards; leakage is minimized, though the relayed answer passes through its context once.

### 12.3 The platform area

- **Facts** (`.baton/platform/facts.md`): durable infrastructure knowledge, one entry each with source and date ("codex is under nvm v22 on the runtime host"; "the service listens on 8080 in the container"). Facts come from promotion, from `platform_fact(text, source)` (the owner's words, recorded by the Director), or from runtime observation: an executable found only through `path.search` (§6.2) is recorded once, marked `observed`. Each is also a `platform_fact_recorded` event.
- **Incidents** (project log): `platform_incident_opened {incident, run, step_path, attempt, class, code, message, refs}` is opened automatically for every `platform` or `unknown` classification of a step's attempt, and for a dispatch refused because the machine lacks something (e.g. `executable_not_found` at dispatch; `attempt: null`). `refs` preselects what the platform SME needs: `facts` and the failed attempt's `log:`. An escalated step whose incident is open shows it (`status`, `board`: "waits on platform incident inc_…"); `board` lists open incidents; `doctor` and `detect` report them as warnings. Hooks carry `BATON_INCIDENT`, so `on_platform_failure` can wake the platform SME directly with the incident.
- **One automatic retry** (§8.8; owner decision, 2026-11-03): `platform_incident resolve <id> --fix "<what was fixed>"` records `platform_incident_resolved {fix, retried}` and readies each step that incident escalated (`step_ready {after_incident}`, a fresh attempt budget), once; the Director then dispatches it. A new failure opens a new incident. The owner's `decide <step> retry` still works while the incident is open.
- **Use:** steps may take `platform.facts` as input. Platform SME packets include facts and open incidents automatically.

### 12.4 The process SME and process feedback

Process improvement is consultation with `subject=process`, not a separate subsystem.
- **Inputs:** `process_feedback` events in the project log (kinds `friction`, `skipped_step`, `waste`, `confusing`) from the Director (`feedback(kind, text, run?, step?, gate?, informed_owner?)`), from workers (`process_feedback` in `result.json`, recorded at intake with the qualified step id), or from the owner; plus statistics the runtime derives on demand from every run's events (the `stats` reference): per qualified step id `<recipe>@<v>/<step_path>` (instances and iterations dropped, §5.8) attempts, passes, rejections, gate failures, timeouts, escalations by reason, failure classes, mean and longest time per attempt; iterations per group instance; and per reviewer profile and findings line, findings by severity, dispositions by kind and evaluations to clean (§9.2). No command of its own.
- **When:** on demand, at run completion if the recipe has a retrospective step, or on the owner's cadence.
- **Outputs:** answers and process proposals, each approved by the owner. Project-level lessons go to `.baton/process/lessons.md` ("when X, do Y, because Z", with origin and confirmation count). Lessons confirmed across projects are promoted into the recipe by its maintainer.
- **Immediate surfacing** (owner decision, 2026-11-03). Baton enforces its own gates, so a skipped blocking gate or human approval can only happen outside it and be reported: `feedback skipped_step "<what happened>" --run <run> --step <step> [--gate <index or type>] [--informed-owner]`. It records `process_feedback` and `step_skip_recorded {feedback_seq, run, step_path, gate, blocking, surfaced}`. Unless the named gate is advisory, the runtime fires `on_needs_human` at once (outcome `needs_human`) and keeps an owner notice pending in `status` and `board --needs-me` until the owner acknowledges it: `decide <run> skip:<seq> acknowledge --note "<words>"`. The notice blocks nothing.

---

## 13. The Director Interface

### 13.1 The API (engine; one table)

Every call is available as a CLI command (`--json` output; exit codes 0 ok, 1 problem, 2 usage, 3 lease held elsewhere, 4 needs owner decision) and as an MCP tool.

| Call | Purpose |
|---|---|
| `detect()` | Project and run situations; machine readiness; one line when healthy |
| `board(needs_me?)` | All non-terminal runs, positions (with group progress), running and queued work, pending decisions, lease holders; `needs_me` keeps runs with pending owner decisions |
| `recipes()` / `plan(recipe)` | Vendored recipes; per-level step and gate table |
| `start(recipe, inputs)` | New run (work item); claims its lease |
| `status(run)` / `explain(run)` | State, pending items, findings, drift / process-facts narrative |
| `eligible(run, step_path)` | Ordered eligible profiles with reasons |
| `dispatch(run, step_path, worker, wait=false)` | Build packet, start supervised worker; returns a dispatch id (or `queued` behind the workspace lock, §8.9) |
| `cancel(run, step_path)` | Withdraw a queued dispatch |
| `wait(run, dispatch_id?, timeout?)` | Block until completion (attached Directors) |
| `submit(run, step_path, result_dir)` | For manual/external workers |
| `decide(run, ref, decision, note)` | Record an owner decision verbatim (gates: `approve`/`reject`; escalations: `retry` with a fresh attempt budget, the note becoming the next packet's feedback, or `abandon`; an instance at its iteration limit (`ref` = instance path): `retry` with a fresh iteration budget, or `abandon`; a finding (`ref` = `<step_path>#<finding>`): `accept-risk`; a runnable stale step: `confirm` (keep the earlier result, §8.1); a skip notice (`ref` = `skip:<seq>`): `acknowledge` (§12.4); a publish conflict (`ref` = `publish:<step_path>.<artifact>`): `overwrite`, `keep` or `alternate` (`path?`); drift (`ref` = `drift:<step_path>.<artifact>`): `leave` (§10.4, §10.5); a `blocked` step's questions: `retry` with `--answers <file>`, the owner's confirmed answers (§13.8); a framing run's `frame` gate: `select --items <ids>` (§11.6); later: baseline items). Every pending decision in `status` and `board` lists its `options` as `[{decision, label, effect}]`: `label` and `effect` in plain language (§13.8) |
| `retry(run, step_path, worker?, guidance?)` | New attempt; guidance is additive only |
| `retriage(run, reason)` / `revise(run, step_path, reason)` | Re-triage (§5.5; the new level waits on the owner's `decide <run> <triage step> approve\|reject`); correct an earlier step in this run |
| `disposition(run, step_path, finding, disposition, evidence?)` / `waive(run, step_path, gate, reason)` | Reviews (§9): `step_path` is the step that recorded the finding; `finding` its id (or `<gate>:<id>`) |
| `ingest_revision(run, step_path, artifact, note, feed?)` | Accept a drifted published file as a human revision, the note being the owner's words (§10.5) |
| `ask_sme(subject, question, refs, run?, mode, worker?, contact?, wait?)` / `sme_followup(consultation, question?, refs?, attach?)` / `sme_status(consultation, wait?)` (CLI `sme`) / `sme_handoff(consultation)` / `sme_eligible(subject, run?)` / `promote_sme(consultation, target, note, text?, turn?)` | Experts (§12): consult (relay or handoff), follow up, read the record, a runtime-made handoff prompt, eligible experts, promotion with the owner's words |
| `platform_fact(text, source)` / `platform_incident(list\|show\|resolve, id?, fix?)` / `feedback(kind, text, run?, step?, gate?, informed_owner?)` | Project-level records (§12.3, §12.4) |
| `adopt(recipe, crosswalk?, scope?)` / `establish_baseline(adoption, note)` | Adoption (§11): start an adoption run, or report the active one; apply the baseline proposal as the owner's one decision |
| `frame(words)` | Framing (§11.6): start a framing run from the owner's goal in their words, or report the one awaiting its decision |
| `resume(run)` / `lease(…)` / `abandon(run, reason)` | Continuity |
| `record(run, step_path)` / `summary(run)` / `trace(run)` | Records; readable event tail |
| `doctor(profile?)` / `check()` | Machine readiness (§13.4); repository consistency (§13.5) |
| `push(approved?, note?)` / `permission(action, detail?, approved?, note?)` | Action permissions (§13.7): the runtime pushes the current branch under `permissions.push`; the Director checks a tag, merge, deploy or force push before doing it. `ask` returns `needs_owner` (exit 4); the owner's approval is the same call with `approved` and their words |
| `init()` / `vendor(recipe_dir, approved?, note?)` / `upgrade(to?)` / `migrate(dry_run?)` | Setup and versioning (§14): a vendoring that changes or reuses step ids returns `needs_owner` until repeated with `approved` and the owner's words; `upgrade` pins this runtime (the launcher runs `--to <v>` under `<v>`); `migrate` brings stored files below the readable window to the current formats |

No call lets the Director write step outputs, artifacts or events directly. Quiet by default: `detect`, `doctor`, `resume`, `status` and `check` print one line when healthy (a completed run's status leaves out its group progress).

### 13.2 CLI and MCP

- The CLI is the primary interface for a Director with a shell on the runtime host. It finds the project from `--project` / `BATON_PROJECT` or the nearest directory holding `.baton/project.yaml`; machine-local files come from `BATON_HOME` (default `~/.baton`).
- The MCP server (`baton mcp`; the official Python SDK `mcp` 2.x, checked against 2.3.0, installed with the optional extra `baton[mcp]`) exposes the same calls as tools, one per call with the CLI's names (`-` → `_`) and arguments. Results are the CLI's `--json` payloads; a refusal is a tool error whose text is the JSON payload with `exit_code` (1 problem, 3 lease held elsewhere); `needs_owner` stands for exit code 4. Every tool call opens the project afresh, like one CLI invocation: the server holds no state, and work it dispatched runs on under its supervisors.
- Owner decisions (2026-11-03):
  - **stdio** (default): the harness starts `baton mcp` as a child process for its session. This is not a daemon: it lives and dies with the session.
  - **HTTP** (`baton mcp --http [--port 8765]`), for Directors without shell access: streamable HTTP, started and stopped by the owner in the foreground on the runtime host, never detached or restarted by Baton, and nothing depends on it running. It binds a **loopback address only** (`--host` must be loopback): without TLS the token would cross the network in the clear, so remote access goes through a TLS proxy or tunnel of the owner's choice. Native HTTPS can be added later without other changes. Every request needs `Authorization: Bearer <token>`; the token comes only from `~/.baton/mcp.yaml` (`token: secret:<name>`, resolved like profile secrets, at least 16 characters), and the server refuses to start without one.
  - The Director identity is the server process's `--director` / `BATON_DIRECTOR`, its harness `BATON_HARNESS`.
- Registration per harness **[VERIFY]**: Claude Code `.mcp.json` or `claude mcp add baton -- baton mcp`; Codex `[mcp_servers.baton]` in its config; Hermes `hermes mcp add baton --command "baton mcp"`.

### 13.3 Skills

**`skills/baton-director/SKILL.md`** (Agent Skills format; vendored into projects):

```markdown
---
name: baton-director
description: Run, resume, or adopt Baton work as Director — keep every work item moving, route steps to capable workers, follow long-running work, handle gates, findings and escalations, talk with the owner in their own terms the way a project manager engages a stakeholder, route questions to the right expert, and keep the owner informed. Use whenever the user asks to start, continue, resume, adopt, check, or ask about Baton work.
---

# Baton Director

You coordinate. You are the expert on the process — not on any step's subject matter, and not on the platform.
Use the `baton` CLI with `--json` on the runtime host, or the equivalent MCP tools (`baton mcp`; same names, same arguments).

## Hard rules
- Never perform step work yourself. Every step's output comes from dispatch/submit.
- Never compose or edit a packet, a result or anything under `.baton/`. If a step cannot start, report the missing inputs.
- Never fabricate an owner decision, disposition, waiver or approval. Record only the owner's actual words.
- Retry guidance is additive; never restate or summarize inputs.
- Choose workers only from `eligible`. Never edit profiles, preferences, permissions or the lockfile without the owner's instruction.
- Never add, remove, skip or reorder steps or roles. Changes go through retriage or revise.
- Act only within the project's action permissions. `ask` means request it; `deny` means never.

## Each session
1. `detect`, then `doctor`. Silent when healthy; interrupt the owner only for a real problem.
2. `board`. For each run that needs you: `resume` it. If its lease is held elsewhere, report holder and expiry; take over only with the owner's approval.
3. New work is a new run (`start`, then triage). Never fold unrelated work into an active run. When the owner states a goal rather than a task ("I want to start a water vending business"), offer to frame it (`frame`), and use the owner's own words as its input.

## Per run
1. `status` → ready steps, running work, pending owner decisions, open findings, drift.
2. Pending owner decision: hold the conversation it needs (see *Talking to the owner*), confirm back, then record it (`decide <run> <ref> <decision> --note "<owner's words>"`). A `blocked` step's questions: take them up with the owner, confirm the answers, write them to a file outside `.baton/` and `decide <run> <step> retry --answers <file> --note "<owner's words>"`.
3. Ready step: `eligible` → choose (respect preference order unless there is a stated reason) → `dispatch`. Starting work the process already calls for is not a question for the owner.
4. Dispatch returns at once. If you can stay attached, `wait`; otherwise end your turn — the completion hook or the next `board` brings you back. Never treat work as finished until Baton records it.
5. A manual worker (a person) does the step: tell them where the packet is; they write the result; `submit` hands it in. Never write it for them.
6. Gate failure: retry while attempts remain (another eligible worker if useful); review loops are handled by the recipe; otherwise escalate.
7. Failure classified `platform` or `unknown`: consult the platform SME with the incident; `configuration`: tell the owner the exact fix.
8. An earlier step was wrong: propose `revise` for this run with the reason. Scope changed: propose `retriage`.
9. Run complete: `summary` → present to the owner; release the lease.

## Pushing and other repo actions
- Push only through `push`; it sorts the commits (docs only, verified by passed steps, other) and applies `permissions.push`.
- Before a tag, merge, deploy or force push, call `permission <action> --detail "<what you will do>"`.
- `allow`: go ahead. `ask` (exit 4): ask the owner; if they approve, repeat the same call with `--approved --note "<owner's words>"`. `deny`: never attempt it, and say so.

## Questions
- About the process (where things are, what's next): answer from `explain`/`status`/`board`, never from memory. If the record doesn't say, say so.
- Subject matter → `ask_sme project`. Infrastructure, tools, accounts, deployment → `ask_sme platform`. How Baton or the recipe should work → `ask_sme process`.
- Never answer these from your own inference. Say plainly that you'll ask an expert. Choose references by name; don't read subject content to choose them. Relay answers faithfully, labeled as the expert's. Promote only with the owner's agreement. Don't use expert content for routing; after a consultation, prefer resuming fresh.
- If the owner would rather talk to the expert directly, run `sme-handoff` and give them the runtime's prompt unchanged; never write one yourself. If it is refused, relay the reason and continue in relay mode.
- When a person's input is needed, consult a proxy (`--contact`, as the owner names them); the owner sends what it drafts. Never contact anyone yourself. Bring their reply back with `sme-followup --attach`.
- Record process friction with `feedback`.

## Talking to the owner
You are the owner's project manager: you understand Baton and the work's structure, and you speak the owner's language. You are impartial; you help the owner decide, you never steer.
- Talk in the owner's terms. Baton's words (run, step, attempt, dispatch, escalate, retry, abandon, packet, gate, worker, profile names) are yours, not theirs; use them only if the owner does. Use each option's `label`, not its decision name.
- Turn structure into conversation. A list of questions from a worker is material for a conversation, not a message to forward: take what is needed now, a topic at a time; offer a worker's `best_guess` for confirmation instead of asking; offer choices when the question has them (several at once when `multi_select`); leave `helpful` questions until the `needed` ones are settled.
- Confirm back before recording. Restate what you understood as a short yes/no ("So: one machine per site to start, and you'll handle the permits yourself?"). Record only what the owner confirmed, with their words. Small conversational inferences (what to talk about next) need no confirmation; anything recorded does.
- Don't answer subject questions. If the owner asks what something means for the work itself, say you'll ask an expert, and route it (see *Questions*).
- Keep the machinery out of sight. Don't report dispatches, workers, attempts or hooks unless the owner asks; report progress in terms of their work.
- Follow `.baton/communication.md`: it says how this owner likes to be told things, and may choose the terse operator style.
```

**`skills/baton-worker/SKILL.md`**: the packet protocol rules (§7); the meaning of `exit_criteria`, `deadline`, `workspace` and `protected_paths`; "stop and report a mismatch instead of improvising"; report friction in `process_feedback`; never contact people, push, tag, merge or deploy.

Both ship in the runtime (`skills/`); `init` copies them into `.agents/skills/` when missing (an edited copy is kept; `upgrade` re-vendors, §14). The shipped director skill is the text above (a test keeps every call it names in the API).

### 13.4 `doctor`

Per machine and profile; silent when healthy (`baton doctor [--profile <name>] [--no-run]`; `--no-run` skips the no-op round trips, which for API profiles are small real model calls).
- Lockfile versus the running runtime version, recipe hashes, supported format and vocabulary versions.
- For each profile: build its exact environment, resolve its executable (§6.2), run a no-op task through its adapter; report auth mode, duration, env names present or denied.
- **Effective auth mode**: what the worker would really use under its exact environment. Harness CLIs are asked (`claude auth status --json`, `codex login status`; a local query, run even with `--no-run`); API profiles report `api_key` with the resolved names; manual profiles `none`. A `cli_login` profile whose CLI would use an API key is a problem (billing would switch; add the key to `env_deny`); one that is not logged in is a problem naming the login command.
- **Gate preflight** for write-capable profiles (harness profiles claiming `repo_workspace`): run `project.preflight` (or the test command) through the worker's own adapter and write-mode args, so a mode that would block gates is caught before a full run is wasted. The worker is asked to run `python -m baton.probe --marker <file> --nonce <n> -- <command>`, which runs the command and writes its exit code to a marker under `.baton/cache/`. The runtime also runs the command itself, as a script gate would. No marker: the mode blocked the command. A different exit code: the sandbox changed its outcome. Either is a problem. Both failing alike is a warning.
- Supervisor can detach (a test supervisor must start in its own session); hooks reachable (valid `hooks.yaml`, `secret:` references resolve, each command's program is found; hooks are never fired); open platform incidents (warnings); steps with no eligible profile on this machine.
- WSL repos on `/mnt/c` (warning).

### 13.5 `check`

For pre-commit and CI; needs no network or profiles. Exit 0 when clean, otherwise one `ERROR <path>: <message>` line per problem. Checks:
- hash chains and CAS integrity;
- lockfile versus vendored recipes, and the neutrality lint;
- drift of active runs' published deliverables (a warning unless `--strict`, §10.5);
- no secrets under `.baton/` (sentinels and patterns);
- no impossible states;
- `project.yaml` and `communication.md` present and valid;
- `.baton/.gitattributes` holds `* -text` (§15.1);
- format versions readable by this runtime.

### 13.6 Owner communication contract

`.baton/communication.md` is created from Baton's default at `init` and owned by the project. It says how this owner likes to be told things; the Director follows it, within the conversation layer (§13.8). Two styles ship (owner decision, 2026-11-04):

**Conversational** (`defaults/communication.md`, the default): guidance on tone and judgment, not a message template.
- Talk as a project manager talks with a stakeholder: plain language in the owner's terms, warm and brief, no Baton vocabulary.
- One topic at a time; choices where the question has them; open questions where the owner is still thinking.
- Offer best guesses to confirm rather than asking from scratch; confirm back before anything is recorded.
- Healthy progress is reported briefly, in terms of the owner's work, or not at all.
- When the owner must act outside the conversation (a command, a setting, a purchase), the operator rules below for actions, placeholders and first mention apply to that part.
- Risk mitigations the agents propose are a decision for the owner, in plain terms with their cost and a narrower alternative, never absorbed silently.

**Operator** (`defaults/communication-operator.md`, chosen by copying it over `communication.md`): the terse shape, adopted from the owner's existing developer practice, for owners who want it:
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

Owner decisions (2026-11-03):
- **Pushing is explicit.** `push` (`baton push`) pushes the current branch to its upstream (or, for a branch new on the remote, to `origin` or the only remote, setting the upstream); nothing pushes automatically, and it never forces. It sorts the commits being pushed (`<upstream>..HEAD`, else every commit no ref of the remote has) into the least privileged category covering them all: `docs_only` (every changed path matches `docs_only_globs`); `after_verified` (every other commit is a Baton checkpoint, or the `commit_sha` of a passed step in any run, so a recipe's gates vouched for it); `other`.
- **Outcomes.** `deny` is refused (exit 1) and records nothing. `allow` records `permission_used` in the project log and commits it (`baton(project): permission used: …`) before pushing, so the record travels with the push. `ask` records `permission_requested` and returns `needs_owner` (exit 4) without pushing; the Director asks the owner and, on approval, repeats the call with `--approved --note "<owner's words>"`, which records `human_decision {kind: permission}` then `permission_used` with its `decision_id` (as with `waive`, the runtime requires the words and the director skill requires the actual approval). Approval never lifts a `deny`.
- **Director actions** outside the runtime (`tag`, `merge`, `deploy`, `force_push`): `permission(action, detail?)` (`baton permission <action> --detail "<what>"`) applies the same rule and records the same events; `push` is not checked this way (the runtime pushes).
- **Defaults** (written by `init`): as above, with `.baton/project/**` added to `docs_only_globs` because project checkpoints write there.

### 13.8 The conversation layer

Principle 5 (§1.1) in practice. The Director stands between the runtime's structured world and the owner's conversational one, like a project manager between engineers and a stakeholder: it understands the machinery, speaks the stakeholder's language, and translates in both directions. It is impartial (it helps the owner decide and never steers), and it does not answer subject questions (§13.3, *Questions*).

**Deterministic on the runtime side.** Everything the Director needs to hold the conversation comes from the runtime as data, so it never has to read subject matter or invent options:
- **Questions** a worker asks (`questions_for_human`, §7.2): each with why it matters, a best guess and choices, in the owner's terms.
- **Assumptions** a worker made (`assumptions` in outputs that declare them, e.g. `fit-check`'s profile and `baton-frame`'s output): what to confirm rather than ask.
- **Decision options** in `status` and `board`: `[{decision, label, effect}]`. Labels come from `defaults/labels.yaml` (e.g. escalation `retry` → "Try again with your answers", `abandon` → "Set this aside for now"; human gate `approve` → "Looks right", `reject` → "Not yet: here's what to change"). A recipe may give its own for a human gate: `{type: human, prompt, labels: {approve: "…", reject: "…"}}`. The runtime never shows the owner anything itself; labels are material for the Director.
- **Process facts** from `explain` (§10.6), for "where are we?" questions.

**Fuzzy on the owner side.** How to hold the conversation is the Director's judgment, guided by `communication.md` (§13.6) and the skill: order and pace, which questions to ask and which guesses to confirm, when a checklist helps and when open talk does, what to leave out. Nothing here is enforced in code, and nothing should be; phrasing is not a reliability concern.

**The confirm-back seam.** Before anything from the conversation is recorded, the Director restates it and the owner confirms. The runtime holds its side deterministically:
- Answers to a `blocked` step's questions go back as a file passed to `decide <run> <step> retry --answers <file> --note "<owner's words>"`: `[{id, answer, owner_words}]`, where `answer` is the confirmed restatement and `owner_words` quotes what the owner said for it, including the confirmation. The runtime checks every id against the step's last questions, refuses an answer without `owner_words` and refuses a missing `needed` question unless `--partial` is given, then records `human_decision {kind: answers}` and readies the step with the answers in `prior_feedback.answers` (§7.1).
- Every other decision already carries the owner's words (`--note`), as before. As with `waive`, the runtime requires the words; the skill requires that they are a real confirmation.
- The escalation stays pending for as many conversational turns as it takes. Nothing is recorded until the owner confirms; a deliberately partial answer set is recorded only with `--partial` (§18 #24).

**Review.** Whether the conversation felt right is judged on transcripts, not enforced: the live test (§17) and the owner's review look for Baton vocabulary reaching the owner, questions forwarded unconverted, decisions recorded without a confirm-back, and subject questions answered by the Director.

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

**Launcher.** The `baton` command installed on a machine is a thin launcher. It reads `baton.lock` in the current repo and runs that exact runtime version, installing it into `~/.baton/versions/` on first use (via `uv`). `BATON_VERSION` overrides it for one invocation. Different projects, branches and worktrees on one machine can therefore use different Baton versions without conflict.

Owner decisions (2026-11-03, §18 #15):
- **The launcher is the package's own entry point** (`baton.launcher:main`, also `python -m baton`). Before anything else it finds the project (`--project`, `BATON_PROJECT`, or the nearest `.baton/project.yaml`), reads `runtime` from `baton.lock` and, when that is the running version (the healthy case), runs in-process. Otherwise it re-runs the same command line under `~/.baton/versions/<v>/` (that version's own Python, `-m baton`). Which version: `BATON_VERSION` if set; `upgrade --to <v>` runs under `<v>` (so the new runtime vendors its own skills), `upgrade` alone under the launcher's own version; `init`, or no project, the launcher's own version; otherwise the lockfile's.
- **Installing** a missing version uses uv (checked against uv 0.13.7): `uv venv <dir>`, then `uv pip install --python <dir's python> "baton[<extras>] @ <source>"`. `~/.baton/launcher.yaml` (optional, machine-local) sets `source` (a URL template with `{version}`; default `git+https://github.com/rowama/baton@v{version}`, so releases are tagged `v<version>`), `extras` (e.g. `[mcp, api]`) and `python` (for `uv venv`); `BATON_UV` names the uv executable. Without uv the launcher refuses, naming uv's install page and the directory a version may be installed into by hand. A version directory counts as installed once it holds `.baton-installed` (written after the installed runtime reports the expected version); installs are serialized by a file lock.
- **No loops.** The re-run process gets `BATON_LAUNCHED=<v>`, refuses if it is not that version, and removes the variable, so hooks and gates it starts launch afresh.
- Worktrees have their own `.baton/cache/`, so two worktrees of one project run two versions side by side.

### 14.2 Compatibility and migration

- A runtime reads all older format versions it declares as supported, and continues runs started under them.
- A run keeps its recipe version and hash for its whole life. Upgrading a recipe mid-run requires an owner decision and is recorded.
- Vendoring or upgrading a recipe compares its step-id signatures with every version recorded in the lockfile; changed or reused ids need an owner decision (§5.8).
- When a format cannot be read, the runtime refuses and names `baton migrate`. Migration is explicit, previewable (`--dry-run`), recorded (`migrated`), committed separately, and never rewrites earlier events: it appends a migration record and writes new-format files alongside.

Owner decisions (2026-11-03):
- **Format families and the readable window** (§18 #15). The stored formats a project keeps are families: event logs (`baton-events/N`, per event), the lockfile (`baton-lock/N`) and vendored recipes (`baton-recipe/N`). Each has a current version and a chain of upcasters (`N → N+1`) kept from version 1 forever. A runtime reads the **current and previous** version directly, upcasting in memory; its new events are written in the current format, so one log may hold two versions. An older version is refused with `format.needs_migration` (`events.needs_migration`, `lock.needs_migration` in `check`), naming `baton migrate`; a version newer than the runtime is refused (`format.too_new`; `*.unknown_format` in `check`), naming the launcher. The packet protocol is per attempt and not migrated (in-flight attempts are finished first).
- **`migrate`** (`baton migrate [--dry-run]`): `--dry-run` reports every file below the window and writes nothing. Otherwise (refused while workers are running, or when something is too new to migrate): an event log gets an upcast copy of all its events so far alongside (`events.migrated-<seq>.jsonl`, each event keeping its `seq` and `sha256`) and a `migrated` record appended to it; readers verify the hash chain on the original lines (it does not depend on the format) and interpret earlier events from the copy named by the latest `migrated` record, whose hash it must match. A vendored recipe gets `.baton/recipes/<ref>.migrated.json` (the upcast recipe plus the hash of the `recipe.yaml` it came from), outside the package hash, so runs keep their pinned hash. The lockfile is rewritten in the current format with the current formats. Each is recorded as `migrated`; one commit holds exactly the migration (`baton(migrate): …`).
- **`upgrade`** (`baton upgrade [--to <v>]`) runs under the target version (the launcher sees to it; `--to` naming another version is refused, `upgrade.wrong_runtime`). It refuses when the project holds a format the target cannot read or migrate (`upgrade.unreadable`, e.g. a downgrade too far), then sets `runtime` and `formats` in the lockfile and re-vendors both skills (replacing edited copies, listed in the result). Nothing else changes, in one commit (`baton(project): upgrade runtime <a> -> <b>`). Files that now need migration are reported with the hint.
- **Step-id signatures** (§5.8). Vendoring compares the new version's per-step signatures with every recorded version of that recipe: `signature_changed` (a kept id whose kind, enclosing group, output schema hash or required capabilities differ) and `retired_id_reused` (an id an earlier version had, absent from every recorded version since, back again). Either returns `needs_owner` (exit 4) with the flags and vendors nothing; repeating with `--approved --note "<owner's words>"` records `human_decision {kind: vendor, …}` in the project log and keeps `decision {decision_id, note, flags}` in the lockfile entry. As with `push`, the runtime requires the words and the director skill the actual approval.
- **Recipe upgrade mid-run** is deferred: a run keeps its recipe version and hash for its whole life (`run.recipe_mismatch`); new work items use the new version.

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
- Git runs with explicit settings (`-c core.autocrlf=false`), except the working-tree snapshot's `git status` (§6.3). Clones are made by other tools with their own settings (Git for Windows converts line endings by default), so `baton init` writes `.baton/.gitattributes` with `* -text`: hash-chained logs, CAS blobs and vendored recipes are checked out byte for byte everywhere, and `check` reports the rule missing.
- On Windows, harness CLIs are often npm `.cmd` shims run through `cmd.exe`, which ends an argument at a newline and expands `%VAR%`. Prompts passed on a command line are therefore one line with no `%`, `^`, `&`, `|`, `<` or `>` (the task prompt, the no-op prompt and doctor's preflight prompt, which puts its command between backticks) **[VERIFY with the real CLIs on Windows]**.
- Script gates and hooks run under the platform shell: `/bin/sh` on POSIX, `cmd.exe /d /s /c` on Windows. Recipe authors write gate commands for the shells their projects use.
- No shebang reliance: entry points come from the package (`baton`, `python -m baton`, `py -m baton`).
- Detaching, liveness, file locks and process-tree termination have POSIX and Windows code paths (Windows: detached process group with job break-away, `OpenProcess`/`GetExitCodeProcess`, `msvcrt.locking`, `taskkill /T`), all tested on native Windows in CI (`.github/workflows/tests.yml`: Ubuntu and Windows, the lowest and newest supported Python). The "survives its caller" test closes a kill-on-close job object holding the caller, as Windows terminals and CI runners do.
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

**Phase 8 — Groups (L3).** Expansion, re-expansion, instances, concurrency, iterations with judges, iteration-limit escalation and decisions, group input references. Pulled forward (owner decision, 2026-11-02): the `findings` gate without dispositions (Phase 9 adds dispositions, waivers and `review` gates) and `revise` for top-level steps without confirming stale steps by decision (Phase 10).
✅ A three-slice plan expands to three instances run one at a time; a code review with an open high finding starts iteration 2 whose implement packet contains it; `max_iterations` escalates; revising the plan (one slice changed, one added) re-expands correctly; instance ids are runtime-assigned, and a revision echoing an unknown or duplicated id is rejected.

**Phase 9 — Reviews (L4).** Review and findings gates, dispositions, waivers, protected files, independence. Built (owner decisions, 2026-11-02): `review` gates as runtime-made review steps; worker dispositions provisional until a review confirms them (§18 #12); dispositions effective at the next evaluation; waivers for the held failure, else the next occurrence; `warn` protection waits on the owner. Review statistics are derivable from the record and computed in Phase 12.
✅ A rejection without valid evidence is refused; `accepted-risk` without an owner decision is refused; a waiver unblocks exactly one occurrence; protected-path changes are caught in `warn` and `fail` modes; a same-vendor code review is refused unless waived; a partial-coverage review shows as partial.

**Phase 10 — Work items (L5).** Concurrent runs, board, workspace and project locks, `revise`. Built (owner decisions, 2026-11-02): lock only (§18 #10); a busy workspace queues the dispatch and the releasing process starts the next one; stale steps stay stale until dispatched or confirmed; `revise` inside groups stays refused.
✅ Two runs of different recipes progress independently in one repo; two write-mode steps from different runs are serialized; checkpoint commits never include another run's files; `revise` on a design marks only that run's dependents stale, and a stale step can be confirmed by decision without rerunning.

**Phase 11 — Tailoring and adoption (L6).** Triage application, `applies_to`, re-triage, `detect`, research, crosswalks, seeding (including groups), baseline. Built (owner decisions, 2026-11-02): rejecting a triage level retries triage; re-triage always waits on the owner and reject keeps the old level; adoption is an adoption run of the built-in `baton-adopt` recipe, then one work-item run per in-flight item, triaged, then one baseline decision over `baseline.yaml`; crosswalk format `baton-crosswalk/1`; research scope 10k files / 200 MB (§18 #14); `backyard-project` has three levels.
✅ The backyard recipe at `minor` (flower bed) and `major` (shed) runs different, correct step sets; re-triage adds future steps only. Adoption of a fixture project from a different prior process, using a crosswalk, imports work at the right granularity (including a partly finished slice), refuses a nonconforming seed, and needs exactly **one** owner decision. `detect` on a healthy project prints one line.

**Phase 12 — Experts (L7).** `ask_sme` for all three subjects, follow-ups, promotion, platform facts and incidents, process feedback and statistics. Built (owner decisions, 2026-11-03): relay turns dispatched like steps outside the state machine; a runtime-generated handoff prompt, refused for experts that rely on working on this machine (§18 #17); full redacted transcripts (§18 #13); no person as an SME, proxies that draft and never send, replies attached by the owner; references selected by name per subject (§12.1); Director-approved follow-ups; promotion to decision, fact, lesson or proposal (artifact revisions with Phase 13); resolving an incident readies its step once; statistics derived on demand; a skipped blocking gate reported via `feedback` fires `on_needs_human` and stays as an owner notice until acknowledged.
✅ Packets contain only Director-selected references plus the index, with hashes; a non-promoted answer is unreachable from any step; an `executable_not_found` failure opens an incident and preselects facts and logs for the platform SME; a promoted platform fact appears in the next platform packet; a skipped blocking gate is surfaced to the owner immediately.

**Phase 13 — Deliverables (L8).** Publishing, conflicts, drift, revision ingestion. Built (owner decisions, 2026-11-03): artifacts only (workspace steps' code is recorded by its commit); published after every `step_passed` (imports never), top-level steps only; silent overwrite only of this run's and step's own untouched file; a conflict is a pending owner decision (`overwrite`/`keep`/`alternate`) that keeps the step passed; drift computed by read-only calls, recorded by mutating ones, tracked while the run is active; `leave` or `ingest_revision`; `human_revision.*` is `not_applicable` until a revision exists; `--feed dependents` reaches only steps not yet started, and passed dependents are flagged possibly stale; pending conflicts and drift hold run completion; an expert's answer can be promoted to a revision.
✅ Deliverables appear at mapped paths; a pre-existing file is never silently overwritten; editing a published file triggers drift, and ingesting it feeds a later step.

**Phase 14 — Director surface.** MCP server (stdio; optional authenticated HTTP), director and worker skills, communication contract default, action permissions. Built (owner decisions, 2026-11-03): explicit `push` with docs-only / after-verified / other categories and `ask` settled by repeating the call with the owner's words; `permission` for Director actions; `init` vendors the skills and writes the `AGENTS.md` pointer (not under adoption); MCP over stdio, and over HTTP only as an owner-started, loopback-only, token-guarded foreground process; `explain` (§10.6), which earlier phases had not built. Two-harness check: scripted MCP and CLI Directors in the suite, plus an opt-in live test (`BATON_LIVE=1`) with Claude Code over MCP and Codex over the CLI, whose transcripts the owner reviews.
✅ The runtime refuses a push that permissions deny and records allowed ones; docs-only changes are recognized; Directors in two different harnesses complete the same recipe with different worker assignments using only CLI or MCP; transcript review shows no Director did step work or answered subject questions itself.

**Phase 15 — Versioning.** Launcher, `upgrade`, `migrate`, compatibility rules.
Built (owner decisions, 2026-11-03): the launcher re-runs the command under the version `baton.lock` pins, installing it with uv from a configurable source; format families read current and previous directly, older ones need `migrate`, which writes upcast copies alongside and records `migrated`; `upgrade` runs under its target and changes only the lockfile and skills; vendoring that changes or reuses a step id needs the owner's words; mid-run recipe upgrade deferred.
✅ Two worktrees of one project run two runtime versions side by side on one machine; an old run continues under a newer runtime; an unreadable format is refused with the migrate hint; `migrate --dry-run` changes nothing; the §14.3 trial workflow merges cleanly; vendoring a recipe version that changes a kept step id's signature, or reuses a retired id, requires an owner decision.

**Phase 16 — Real use.** Example recipes `fit-check`, `software-feature` and `backyard-project` (§5.7); a remote-Director scenario.
Built (owner decisions, 2026-11-03): `software-feature` moves from a test fixture to `examples/` with real prompts and rubrics and is the suite's only copy; slice acceptance is a judge (§5.7); each recipe runs end to end through the CLI with scripted workers and a scripted Director (`software-feature` at every level, `backyard-project` at every level, `fit-check` per verdict) and loads with no lint warnings; the remote Director is a fresh shell-only process per session, woken by completion hooks (a wake inbox standing in for a webhook) or by the owner's replies; an opt-in live run (`BATON_LIVE=1`) of `software-feature` at `minor` with Claude Code implementing and Codex triaging and reviewing; the README covers §19; runtime bugs found by real use are fixed and recorded (the working-tree snapshot's line endings, §6.3; a completed run's status in one line, §13.1).
✅ All three recipes run end-to-end and pass the lint with zero runtime changes. A remote Director with only shell access completes a multi-slice work item across several of its own sessions, woken by hooks, with no owner action beyond the recipe's decisions. The full suite passes on Linux and native Windows CI.

**Phase 17 — Conversation layer and framing.** Prompted by the first real-project run (2026-11-04): an owner starting a pure-water vending business got five abstract `fit-check` questions at once ("which piece of work is one occurrence?"), plumbing reports ("dispatched describe to claude-code-sub, attempt 1"), and "Decision owed: `retry` or `abandon`". The runtime's mechanism is unchanged; this phase gives it a human-facing side (§1.1 principle 5). Scope:
- Structured `questions_for_human` with string normalization (§7.2); `prior_feedback.answers` (§7.1); `decide … retry --answers` with its checks and `human_decision {kind: answers}` (§13.8).
- Decision `options` with plain-language labels in `status` and `board`; `defaults/labels.yaml`; optional `labels` on human gates (§13.8).
- The conversational `defaults/communication.md` and `defaults/communication-operator.md` (§13.6).
- The director skill's new *Talking to the owner* section and related edits (§13.3), shipped in `skills/`.
- `fit-check`'s `describe`: infer first, `assumptions` in the profile schema, questions in the owner's terms, several kinds of work reported as one question (§5.7).
- Framing: `frame`, the built-in `baton-frame@1` recipe and `baton-frame/1` schema, the `select` gate, `framing_selected`, run creation and gaps (§11.6).
✅ The water-vending scenario, scripted: from the owner's words, framing proposes parts in plain language; selecting two starts two runs with the right recipes, and a part with an invalid proposed input is reported as a gap, not a run. A `fit-check` run whose `describe` returns `blocked` with structured questions and assumptions is resumed through `decide … retry --answers`, and the next packet carries exactly the confirmed answers; an answer without `owner_words`, an unknown question id or a missing `needed` answer (without `--partial`) is refused. Bare-string questions from an existing worker still work. Every pending decision in `status --json` lists options with labels. With `communication-operator.md` in place, the operator style's shape is unchanged. Opt-in live test (`BATON_LIVE=1`): a real Director runs the scenario with a scripted owner; the owner reviews the transcript for the four points in §13.8 *Review*.

---

## 17. Testing Strategy

- **Unit:** loader and lint, vocabulary, routing and independence, hashing, the state machine, groups, gates and findings, env and PATH construction, classification rules, permissions, publishing and drift.
- **Property-based** (`hypothesis`): packet determinism; required-input removal; any legal event sequence rebuilds to the same state; `foreach` re-expansion is stable for unchanged items.
- **Fake adapter:** scripted good, bad-schema, wrong-hash, blocked, findings, timeout, crash, hang and exit-127 results.
- **Process control:** detachment, process-tree termination and marker liveness on POSIX and Windows.
- **Secret leak:** sentinel secrets through a full run; absent from the working tree and git history.
- **Golden files:** `INSTRUCTIONS.md`, records, summary, `explain` output.
- **Conversation review** (opt-in, with live tests): transcripts of a real Director with a scripted owner, reviewed by the owner against §13.8 *Review*. Not a pass/fail gate in CI: phrasing is judged, not enforced.
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
10. Worktree isolation for concurrent write-mode steps. [lock only at first] **Decided (2026-11-02):** lock only; worktree isolation is deferred (it needs a merge strategy). A write step dispatched while the tree is held is queued, first in first out, and started by the process that releases the lock (§8.9).
11. Automatic platform-SME invocation on platform failures. [only when `on_platform_failure` is configured] **Decided (2026-11-02):** as suggested; Baton invokes no SME itself. A `platform` failure fires `on_platform_failure` when configured, otherwise `on_complete` (§8.7).
12. Who may set `fixed` and `rejected`: the next iteration's worker with evidence, or only the Director? [worker with evidence] **Decided (2026-11-02):** worker with evidence, strengthened: a worker's `fixed`/`rejected` is provisional until an independent review confirms it (a re-reported finding id reopens it); with no later review it does not close the finding; persistent worker–reviewer disagreement goes to the owner (§9.2).
13. SME transcript retention: full (redacted) or question and answer only. [full, redacted] **Decided (2026-11-03):** full, redacted: every turn's packet and result are kept under the consultation's `sme/` directory (§12.1).
14. Research scope limits before asking the owner to narrow. [10k files / 200 MB] **Decided (2026-11-02):** as suggested. Counted over the non-ignored files in scope; above either limit `adopt` refuses with the counts and the `--scope` hint (no decision is recorded) (§11.2).
15. Launcher installation mechanism and how many older format versions a runtime must read. [uv-managed; current and previous] **Decided (2026-11-03):** as suggested. The launcher installs a missing version with uv into `~/.baton/versions/<v>/` from a `source` template in `~/.baton/launcher.yaml` (default the runtime's git repo at tag `v<version>`); without uv it refuses with the install hint. A runtime reads the current and previous version of each stored format; older ones are refused naming `baton migrate` (§14.1, §14.2).
16. Optional OpenTelemetry export of events. [off]
17. SME handoff mode support per harness. [relay first; handoff per harness later] **Decided (2026-11-03):** relay is the formal mode. Handoff needs nothing per harness: the runtime (never the Director) generates a copy-and-paste prompt from the consultation, saved as `handoff.md`, which is the whole record; nothing returns except through promotion. The runtime refuses it, with the reason, when the expert relies on `shell`, `code_exec`, `workspace_read`, `repo_workspace` or `file_write`, unless the expert is a `command` black box. SMEs are never people; a person is consulted through a proxy SME that drafts and never sends (§12.1).
18. **Conditionally deferred risk: erroneous worker dispositions** (discussed 2026-11-02). *Risk:* a worker's `fixed` or `rejected` disposition is wrong but survives (e.g. the confirming review misses it), so a real problem slips through. *Mitigation today:* dispositions are provisional until an independent review confirms them, and persistent disagreement escalates to the owner (§18 #12). *Options discussed and set aside:* (a) the Director judges a dispute itself. The owner's view is that a well-presented dispute needs no subject expertise, the same as a juror or arbiter, but the Director's impartiality must remain sacrosanct, so the Director does not judge. (b) The Director mediates by routing: the runtime opens a pending dispute, and the Director sends it to an independent arbiter worker (a dispatch at `<step>~arbiter`, different vendor from worker and reviewer, returning uphold/reopen with reasons) or escalates it to the owner. The worker and the reviewer must present their evidence so that no subject expertise is needed to decide. This adds a "dispute" concept (§2). *Trigger to revisit:* the owner sees cases where problems slip through because of erroneous worker dispositions. Then reopen this item with these options; (b) is the leading candidate.
19. **Format versions for Phase 17's additions** (structured questions, `answers`, human-gate `labels`, framing events). [Additive within the current `baton-packet/1`, `baton-recipe/1` and `baton-events/1`, no version bump: every addition is optional or a new event type, and the lockfile already pins the runtime that reads them.]
20. **Communication style scope.** Per project (one `communication.md`), or per contact, so a developer owner can use the operator style while a client on the same project gets the conversational one? [Per project for now; per contact when a project has more than one person deciding.]
21. **Who owns decision labels.** [Runtime defaults in `defaults/labels.yaml`; a recipe may label its own human gates; no project-level override yet.]
22. **Framing and `fit-check`.** Should framing replace `fit-check` for goals? [No: `fit-check` stays a standalone recipe for a single idea; framing proposes a `fit-check` run for any part without a fitting recipe.]
23. **Framing with one part.** If `frame` proposes a single part, does the owner still choose? [Yes, as one confirm-back: "So we'll start on X?" Selecting is the owner's decision even with one option.]
24. **Partial answers.** May the owner leave a `needed` question unanswered? [Yes, with `--partial`; the step gets the confirmed answers and may ask again.]

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
  - framing a goal into work items, and choosing the conversational or operator communication style;
  - resuming on a new machine;
  - trialing a new version on a branch.
- Three example recipes ship (§5.7): `fit-check`, `software-feature` (software) and `backyard-project` (non-software).
- Swapping the Director harness or any worker needs only machine-local configuration. New recipes need no runtime changes.
- Principle checks, demonstrated in Phase 16:
  - after setup, a healthy project produces no routine owner prompts;
  - adoption needs exactly one owner decision;
  - every owner touchpoint is a recipe gate, an escalation, the baseline or a framing selection;
  - an owner unfamiliar with Baton can frame a goal and answer a step's questions without meeting Baton's vocabulary, and every answer recorded was confirmed back (Phase 17).
