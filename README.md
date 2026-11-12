# Baton 

### *Vendor-Neutral, Director-Led Multi-Step Process Framework*

#### *AI Integration by Design, not by Accident*

- Guaranteed determinism where you need it.
- Drop in AI inference where you want it.
- True capabilities-based, multi-vendor routing
- Context efficiency by design, nothing arbitrary
- Undistracted, focused process Director, the Baton expert.

Baton is a small runtime that lets any agentic harness act as the **Director** of a multi-step process. Each step is done by a **worker**: a model API call, a headless coding agent, or a person. Processes are **recipes**: model-neutral, shareable packages of steps, inputs, gates and prompts. The runtime builds each worker's packet, checks each result, keeps an append-only, hash-chained record in your repository, and wakes the Director when work finishes. The design and every rule are in [`docs/`](docs/README.md): [`docs/principles.md`](docs/principles.md) for the principles, `docs/design/` for the design by topic, `docs/decisions/` for the owner's decisions. Section numbers below (§) are listed in the [§ index](docs/README.md#-index), which names the file holding each one.

---

## Install

Baton needs Python 3.11 or newer, git and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install "baton[mcp,api] @ git+https://github.com/rowama/baton"
baton --version
```

The `baton` command is a **launcher** (§14.1). Inside a project it reads `.baton/baton.lock` and runs exactly the runtime version pinned there, installing it into `~/.baton/versions/<version>/` the first time (from the git tag `v<version>`; set `source`, `extras` and `python` in `~/.baton/launcher.yaml` to install from elsewhere). Different projects, branches and worktrees can use different versions side by side. `BATON_VERSION=<v>` overrides the pin for one command.

Extras: `api` for model-API workers (`litellm`), `mcp` for `baton mcp`, `keyring` for the OS keyring secret store.

## Set up a project

```sh
cd my-project
baton init                           # --bare: vendor no starter recipes
git add -A && git commit -m "Use Baton"
```

`init` creates `.baton/` (project configuration, lockfile, owner communication contract, `.gitattributes`), copies the Director and worker skills into `.agents/skills/`, adds a one-line pointer to `AGENTS.md`, and vendors the starter recipe `fit-check`. Nothing else needs vendoring before you start: framing (below) proposes from the recipes shipped with Baton and vendors the ones you choose. Edit `.baton/project.yaml` to map the logical paths your recipes publish to and to set project variables:

```yaml
paths: { specs: docs/specs, designs: docs/design }
project: { test_command: "pytest -q", preflight: "pytest -q --collect-only" }
```

`project.yaml` is committed and must never hold secrets (`check` refuses them).

## The manual

The documentation for owners and administrators is the **manual**. It ships with Baton, so it matches the version you run and works offline:

- `baton ui` opens the setup page. Its **Manual** tab is the whole manual, with search, and a **?** beside each part of the page opens the short answer for it.
- `baton help` lists every topic in the terminal; `baton help <topic>` prints one; `baton help --search <words>` finds one. Every command's `--help` ends with the topic that explains it.
- Your AI assistant can read it too: ask "how do I...?".

It covers getting started, connecting accounts and subscriptions, starting with a goal or bringing in an existing project, answering questions, the shipped recipes, and, for an administrator, installation, files and what to commit, network and security, settings, setting up an assistant, troubleshooting, and a reference for every command, setting and variable. `python tools/build_site.py` builds the same manual as a static site. The design documents for people who build Baton are in [docs/](docs/README.md).

## Author a recipe

A recipe is a directory with `recipe.yaml`, JSON schemas, prompts and static files (§4.2, §5). Steps declare the **capabilities** they need, never a model or vendor; the loader's neutrality lint rejects `model:`, `provider:` and vendor strings. The essentials, from `software-feature`:

```yaml
id: software-feature
version: 1
format: baton-recipe/1
capabilities_vocab: baton-capabilities/1
run_inputs: { schema: schemas/run_inputs.json }

complexity:                              # the recipe's own scale; triage picks a level
  levels: [minor, standard, major]
  triage_step: triage

steps:
  - id: triage
    requires: { capabilities: [structured_output, technical_reasoning], tier: standard }
    prompt: prompts/triage.md
    inputs: [ { name: feature_request, from: run.inputs.feature_request, required: true } ]
    output_schema: schemas/triage_out.json   # level + reasons
    gates: [ { type: schema } ]

  - id: plan
    depends_on: [triage]
    applies_to: [standard, major]            # skipped at minor
    requires: { capabilities: [structured_output, technical_reasoning, workspace_read], tier: strong }
    workspace: read
    output_schema: schemas/plan_out.json     # slices: [{id?, title, outcome, criteria, effort}]
    gates:
      - { type: schema }
      - type: review                         # an independent reviewer returns findings
        block_on: [critical, high]
        reviewer_requires: { capabilities: [structured_output, technical_reasoning], tier: strong }
        independence: { from_step: plan, level: different_vendor }
        rubric: prompts/plan_review_rubric.md
      - { type: human, prompt: "Approve the plan and its slices?" }

  - id: slices                               # a group: one instance per planned slice
    depends_on: [plan]
    foreach: steps.plan.output.slices
    foreach_if_source_skipped: once
    repeat_until: group.steps.code_review.gates.passed and group.steps.accept.gates.passed
    repeat_from: implement
    max_iterations: 3
    steps: [ … implement (workspace: write, script gate), code_review (baton:findings), accept (a person) … ]
```

Rules worth knowing before you start:
- **Ids name roles**, never positions (`design`, not `step2`); a retired id is never reused (§5.8).
- **Inputs** use a closed reference grammar (`run.inputs.*`, `steps.<id>.output`, `steps.<id>.artifacts.<name>`, `item`, `group.*`, `static.*`, §5.2); the runtime assembles every packet, so a missing input stops the step instead of being guessed.
- **Gates:** `schema`, `script` (a command, e.g. the project's tests), `review` and `findings` (severities and dispositions, §9.2) and `human`. `advisory: true` records without blocking; `applies_to` limits a gate to some levels.
- **Groups** (`foreach`, `repeat_until`): an attempt retries one step after its own gate fails; an iteration reruns part of the group while a judge's gate fails, carrying the open findings forward (§5.4).
- **Deliverables:** `publish: { to: "{{ paths.specs }}/{{ run.slug }}-requirements.md" }` writes an artifact to a project path after the step passes and tracks edits to it (§10.4).

The recipe format is published as JSON Schema in `formats/baton-recipe-1.schema.json`.

## Development

```sh
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

CI runs the suite on Linux and native Windows. Live tests (real models and CLIs) are opt-in: `BATON_LIVE=1`.
