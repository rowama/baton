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

## Worker profiles

Profiles live on each machine, in `~/.baton/workers.yaml` (project-specific overrides in the gitignored `.baton/workers.local.yaml`), never in a repository. A profile says how to run one worker and what it can honestly do on this machine (§6.1):

```yaml
claude-code-sub:                       # a coding agent on its subscription login
  adapter: claude_code
  vendor: anthropic                    # used for reviewer independence
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }
  env_deny: [ANTHROPIC_API_KEY]        # a stray key would switch billing to the API
  path: { search: [nvm] }              # find CLIs installed under nvm

codex-sub:
  adapter: codex
  vendor: openai
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, long_form_writing, technical_reasoning]
  tier: strong
  auth: { mode: cli_login }
  env_deny: [OPENAI_API_KEY, CODEX_API_KEY]
  path: { search: [nvm] }

api-writer:                            # a model API call
  adapter: litellm_api
  vendor: some-vendor
  model: "<provider>/<model>"
  capabilities: [structured_output, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: api_key, env: { PROVIDER_API_KEY: "secret:provider_main" } }

owner:                                 # a person: the manual adapter
  adapter: manual
  vendor: human
  capabilities: [human_judgment, long_form_writing, vision, file_write]
```

Secrets are referenced as `secret:<name>` and resolved at spawn time from `BATON_SECRET_<NAME>`, the OS keyring (service `baton`) or `~/.baton/secrets/<name>`. Workers start from a clean or allow-listed environment, so one step's key never reaches another step. The `command` adapter runs any other tool through a command line with `{packet}`, `{result}`, `{workspace}` and `{prompt_file}` placeholders.

## Check the machine and the repository

```sh
baton doctor            # per profile: environment, executable, auth mode, a no-op run; one line when healthy
baton doctor --no-run   # skip the no-op runs (no model calls)
baton check             # for pre-commit and CI: hash chains, CAS, lockfile, lint, secrets; exit 0 when clean
```

`doctor` reports what each worker would really bill (a `cli_login` profile that would pick up an API key is a problem) and, for coding agents, whether their permission mode lets the project's test command run (gate preflight).

## Run work

A Director is any harness with the `baton-director` skill (vendored by `init`) that can run `baton` in a shell on this machine, or reach `baton mcp`. Ask it to start a work item; underneath, it runs:

```sh
baton start software-feature --inputs '{"title": "Sign in", "kind": "feature", "feature_request": "Let users sign in and out."}'
baton status <run>
baton eligible <run> <step>
baton dispatch <run> <step> --worker <profile>      # returns once started; add --wait to block
baton decide <run> <step> approve --note "<the owner's words>"
baton board                                          # every active work item
```

Dispatch is asynchronous: a detached supervisor finishes the work, records it and commits a checkpoint. A Director whose turn ends while work runs (a cloud chat agent with a shell on this machine, for example) is woken by a **completion hook** in `.baton/project.yaml` or `~/.baton/hooks.yaml` (§8.7):

```yaml
hooks:
  on_complete: "curl -fsS -m 20 -X POST -d run=$BATON_RUN_ID -d step=$BATON_STEP_PATH -d outcome=$BATON_OUTCOME secret:director_wake_url"
```

(`secret:` values are allowed only in the machine-level `hooks.yaml`.) For Directors without a shell, `baton mcp` serves the same calls over MCP (stdio; `--http` binds loopback only and needs a bearer token from `~/.baton/mcp.yaml`).

## Frame a goal

Owners usually bring goals, not tasks. Tell the Director what you want, in your own words ("I want to start a pure-water vending business"), and it frames it:

```sh
baton frame --note "<the owner's goal, in their words>"
baton eligible <framing run> frame
baton dispatch <framing run> frame --worker <profile>
baton decide <framing run> frame select --items setup,running --note "<the owner's words>"
```

A worker breaks the goal into pieces of work, each proposing a recipe (a shipped one is vendored when you choose it) or a quick `fit-check`. The Director confirms the goal with you, lets you choose, and starts one work item per chosen piece. A piece that can't start yet (its details don't fit the recipe, or the recipe publishes to paths `project.yaml` doesn't map) is reported to you as a gap, never started.

## Talking with the owner

The Director talks with the owner like a project manager with a stakeholder: in the owner's terms, a topic at a time, offering best guesses to confirm, and confirming back before anything is recorded. When a step needs answers, the Director records the confirmed ones from a file: `baton decide <run> <step> retry --answers answers.json --note "<owner's words>"`, where each answer is `{id, answer, owner_words}` (`--partial` leaves a question open on purpose). Every pending decision in `status` and `board` comes with plain-language labels (`defaults/labels.yaml`; a recipe may label its own human gates).

`.baton/communication.md` sets the style. The default is conversational. For the terse operator style (brief status, a list of your actions with each command in its own block, then the one decision owed), copy Baton's `defaults/communication-operator.md` over it.

## Using Codex as Director

Codex sandboxes the commands it runs: in its default `workspace-write` mode they can change only the project folder and usually can't reach the internet, and everything they start inherits that. Baton keeps its working files in `~/.baton` and its workers need the internet, so connect Baton to Codex as an MCP tool instead of letting Codex run `baton` in its shell. Codex runs MCP servers outside its sandbox, and stays sandboxed for everything else (§13.2). Once, in your own terminal:

```sh
codex mcp add baton -- baton mcp
```

Codex asks before every MCP tool call unless told otherwise (and `codex exec` refuses them), and `codex mcp add` has no option for that. So open `~/.codex/config.toml` and add one line under the `[mcp_servers.baton]` section the command wrote:

```toml
[mcp_servers.baton]
# … what codex mcp add wrote …
default_tools_approval_mode = "approve"
```

Then restart Codex. It calls Baton's tools directly, with the same names and arguments as the CLI. If Codex runs `baton detect` from its sandboxed shell anyway, Baton stops with `director_sandboxed` and this fix, rather than failing part way (§13.4). Checked live with `codex-cli` 0.166.0 on Linux: sandboxed Codex completes a run over MCP with a real worker (`tests/test_live_codex_mcp.py`).

## Example recipes

| Recipe | What it shows |
|---|---|
| [`fit-check`](examples/recipes/fit-check) | Decide in minutes whether an idea suits Baton. Two steps, one human gate; it infers first and asks only what it can't. Vendored by `init`. |
| [`software-feature`](examples/recipes/software-feature) | A feature from request to accepted, tested slices: three complexity levels, requirements and design published to project paths, reviews by a different vendor, a per-slice implement, review and accept loop. |
| [`backyard-project`](examples/recipes/backyard-project) | A non-software project (a flower bed or a shed): people as workers, photos as artifacts, permits and inspections at the highest level. |

`baton plan <recipe dir>` validates a recipe and prints the steps and gates at every level.

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

## Vendor a recipe

```sh
baton vendor path/to/recipe
```

Vendoring copies the recipe to `.baton/recipes/<id>@<version>/` and pins its hash in `baton.lock`. Recipes are trusted code (script gates run commands), so review them first. A new version that changes a kept step's signature or reuses a retired id needs the owner's decision: `vendor` exits 4 and lists the flags, then `baton vendor <dir> --approved --note "<owner's words>"`. Runs keep the recipe version they started with; new work items use the new one.

## Adopt an existing project

```sh
baton adopt path/to/recipe [--crosswalk <name or file>] [--scope docs/]
```

Adoption is an ordinary run of a built-in recipe (§11). A read-only research step finds which of the recipe's outputs already exist (a **crosswalk** maps a known prior process's files to recipe steps). Then each in-flight work item becomes its own run and is triaged, and the runtime writes a baseline proposal to `.baton/adoption/<run>/baseline.yaml`: configuration, levels, work imported as already done, proposed waivers and known gaps. The owner reads it, may edit it, and makes the **one** adoption decision:

```sh
baton establish-baseline <adoption run> --note "<owner's words>"
```

## Resume on another machine

Everything a run is lives in the repository (`.baton/runs/<run>/`, committed at checkpoints). On a new machine:

```sh
git clone <repo> && cd <repo>
baton doctor              # this machine's own worker profiles must be in ~/.baton/workers.yaml
baton resume <run>        # verify the record, reconcile in-flight work, claim the lease
```

A run is changed by one Director at a time (its **lease**); `baton lease <run> take-over --reason "…"` takes it over with the owner's approval.

## Try a new Baton version on a branch

```sh
git worktree add ../my-project-trial -b baton-trial
cd ../my-project-trial
baton upgrade --to <version>     # changes only the lockfile and the vendored skills
# run real work here; to keep it, merge the branch; to drop it, delete the branch and worktree
```

Stored formats are versioned; a runtime reads the current and previous version of each. Older files are refused with a hint to run `baton migrate` (`--dry-run` previews and changes nothing).

## Development

```sh
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

CI runs the suite on Linux and native Windows. Live tests (real models and CLIs) are opt-in: `BATON_LIVE=1`.
