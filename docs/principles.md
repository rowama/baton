# Baton: Principles

> **Always read this file.** It holds the ground rules (§0), the principles, guarantees and key design decisions (§1) and the concept budget (§2) that every change is judged against. The design itself is in `design/` (one file per topic; [README.md](README.md) maps every § to its file), decisions are in `decisions/`, and work in progress is described by change docs in `changes/`.
>
> **Baton** is a vendor-neutral, Director-led multi-step process framework.

## 0. Ground Rules for the Building Agent

1. **Do not invent APIs.** Before using any library (`mcp`, `litellm`, `jsonschema`, `typer`, etc.) or CLI (`claude`, `codex`, `hermes`, `uv`), check its installed version's docs or `--help`. Anything marked **[VERIFY]** must be confirmed against current docs before you rely on it.
2. **Determinism over prompting.** Anything that must be 100% reliable is enforced in code, never left to an LLM following instructions.
3. **Thin layer.** No web UI, no message broker, no database server, no long-running daemon. Filesystem, git, SQLite (as a cache only) and plain Python. Every dependency must justify itself.
4. **Vendor neutrality.** No model vendor is privileged in the core or in recipes. Vendors exist only in worker profiles and adapters.
5. **Small, tested increments.** Tests alongside each module; `pytest` green at every commit.
6. **Ask the human** when a requirement is ambiguous. Never silently decide an open decision (§18: a decision record in `docs/decisions/` with `status: proposed`).
7. **The name is a label, not a spec.** "Baton" evokes work passed between workers under a Director. Use the metaphor only to explain; never derive a design decision or a term from it. Code and docs use plain names (step, packet, result, worker, gate).
8. **Respect the concept budget (§2).** Do not introduce a new user-visible concept, file or command without updating §2 and justifying it against the principles in §1.

## 1. What We Are Building, and the Principles That Bound It

**Baton** is a small runtime that lets *any* agentic harness act as the **Director** of a multi-step process, while each step is done by a **Worker**: a model API call, a headless coding agent, or a human. Processes are **recipes**: shareable, model-neutral packages. Baton supplies the machinery that makes multi-agent work reliable and leaves the domain knowledge to recipes.

### 1.1 Principles (every feature is judged against these)

1. **Invisible when healthy.** After install, the owner should not notice Baton unless something truly needs them. Checks are silent when fine; owner attention is spent only on real decisions: gates the recipe defines, escalations, the one-time adoption baseline, and choosing work items when a goal is framed.
2. **Friction must pay for itself.** Every setup step, prompt or file the owner touches must save more effort than it costs. Prefer generalizing an existing mechanism over adding a parallel one.
3. **Arbitrarily complex processes, simple runtime.** Recipes can express multi-agent processes of any size (iteration, fan-out, reviews, many concurrent work items). The runtime stays small and conventional: one event log format, one packet protocol, one state machine, no daemon, no server. **Everything that does work is a dispatch of a packet to a worker** (steps, reviews, research, triage, expert consultation); everything else is bookkeeping over the event log.
4. **Evolve by trial.** Runtime, recipes and formats are versioned and pinned per project and per run, so a real project can try a new Baton version on a branch and merge or discard it (§14).
5. **Deterministic machinery, human conversation** (Decision: [0025](decisions/0025-deterministic-machinery-human-conversation.md)). Two layers, kept separate. The runtime, and everything that crosses into it (packets, results, events, decisions), stays structured and deterministic; explicitly deterministic and explicitly inferential work stay separated, as everywhere else in this guide. The owner's side is a conversation run by the Director, who talks like a good project manager with a stakeholder: plain language in the owner's terms, structure (choices, checklists) where it helps, open talk where that helps, and no Baton vocabulary. The seam between the layers is the **confirm-back** (§13.8): nothing the Director understood from conversation is recorded until the owner confirms it. The owner may be a layperson; nothing in the owner's path assumes otherwise.

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

Framing (§11.6) adds none either: a *framing run* is a run of a built-in recipe whose one step proposes work items, and choosing among them is one owner decision; the *catalog* is simply the recipes shipped with the runtime, and the *starter recipes* the ones `init` vendors.

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
