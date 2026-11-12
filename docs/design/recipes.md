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

Two optional keys describe a recipe to people and to later authoring; neither affects a run (Decisions: [0103](../decisions/0103-recipe-provenance.md), [0105](../decisions/0105-recipe-scope-and-parent-additive.md)). Both are additive in `baton-recipe/1`: a recipe without them loads as before.

```yaml
scope:                                   # what the recipe covers, in the owner's terms
  covers:  ["a flower bed", "a raised bed"]                        # example jobs (at least one)
  not_for: [{ job: "a kitchen remodel", use: "home-renovation" }]  # near misses; `use` optional
  varies_by: ["size", "whether a permit is needed"]                # absorbed by inputs and levels
parent: { id: backyard-project, version: 2 }   # built from this recipe; `parent: null` = built from nothing
```

An absent `parent` marks a recipe that predates the field; `null` and a named parent both record where it came from, and all three are roots as far as the runtime goes. The loader rejects any other key under `scope` or `parent` (`recipe.unknown_key`) a missing required key (`recipe.missing_key`) and a malformed value (`recipe.invalid_value`).

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
| `catalog.summaries` | A summary of each recipe the project can run (Decision: [0106](../decisions/0106-catalog-summaries-input.md)): every vendored recipe (its newest version), then every shipped recipe not vendored, as `{id, version, description, levels, run_inputs, vendored, scope}`, `scope` being the recipe's scope block (§5.1) or `null`. The same listing framing receives (§11.6), plus `scope`. Always resolvable: a project with no lockfile lists only the shipped recipes |

"Required" applies only when the source step is included at the run's complexity level. Inputs from skipped steps are omitted and listed as `not_applicable` in the manifest. Expert answers are deliberately **not** referenceable; they enter a run only when promoted (§12.2).

### 5.3 Load-time validation and neutrality lint

The loader (`recipe.py`) rejects a recipe unless:
- Every `steps.<id>` reference names an ancestor via `depends_on` (transitively); there are no cycles; files exist; schemas are valid JSON Schema 2020-12.
- Gate types are known; every capability used is in the declared vocabulary.
- `publish.to` uses only `paths.*`, `run.*` (`id`, `slug`, `title`, `kind`, `inputs`) and `project.*` variables, and only on top-level steps (`publish.in_group`, §10.4).
- Complexity: the triage step exists, has no `applies_to`, outputs `level` constrained to the declared levels; every `applies_to` uses declared levels; for each level, every included step is reachable (`baton plan <recipe>` prints the per-level step and gate table).
- Ids: per §5.8 (unique, no positional ids; `foreach` items declare an optional `id`).
- Groups: per §5.4; `item` and `group.*` appear only inside groups; `independence.from_step` names the step itself or an ancestor (in the same group if inside one); `protect` appears only on `workspace: write` steps. With `repeat_from`, every step named in `repeat_until` must be at or after it (`group.judge_not_repeated`), and a step listed before it may not depend on one at or after it (`group.depends_on_repeated`).
- A recipe being built can be checked by `baton recipe check <package> --ledger <file>` (Decision: [0108](../decisions/0108-recipe-check-command.md)), which a script gate runs. It reads a requirements ledger (a list of `{id, statement, kind, scope, status, basis, owner_words?}`, `scope` being `class` or `instance`, `status` one of `confirmed`, `researched`, `inferred`, `open`, `excluded`) and reports, one `ERROR <path>: <message>` line each: a malformed ledger or entry; an `open` entry; a `confirmed` entry without `owner_words`; and any `instance` entry whose `statement`, `value` or `owner_words` (at least 8 characters after lower-casing and collapsing whitespace) appears in the package's `prompts/` or `static/` files. Exit 0 when clean, 1 otherwise. It judges nothing else: whether a design meets its goals is a reviewer's work.
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

**Judges** (Decision: [0026](../decisions/0026-judges.md)). When a judge's declared blocking gate (findings, review, human or script) fails, the judge did its work and the iteration's work is not done: its result is kept (`step_passed` with `condition.gates_passed: false`), the steps after it in that iteration never start, and the next iteration starts at `repeat_from` carrying the open findings and gate reasons. Rejected results, schema failures, failed workers and timeouts still retry the judge as attempts.

Groups nest at most one level (supported with the same rules). `foreach` and `repeat_until` may be combined (the loop runs per instance). Runtime semantics: §8.5.

**Attempts versus iterations.** An *attempt* retries one step after its own gate fails (tests failed). An *iteration* reruns part of a group because the group's exit condition isn't met (the independent review still has open high findings). Each is bounded separately.

### 5.5 Complexity levels and triage

- The recipe owns its scale and criteria (in the triage prompt). The runtime only applies the result.
- After triage passes (`complexity_set`), every step and gate whose `applies_to` excludes the level is marked `skipped`. Steps without `applies_to` always run. The Director has no say.
- **Approval** (§18 #8): a triage result at the lowest level is applied at once (`complexity_set`, `approval: auto`). Above it, once the triage step's declared gates pass, an implicit human gate (`gate: "triage"`) asks the owner to approve the level; approving records `step_passed` then `complexity_set`. Rejecting fails the gate: triage gets another attempt with the owner's note as feedback (Decision: [0027](../decisions/0027-triage-rejection-retries.md)). In a run created by adoption the level is approved by the baseline instead (§11.5). `revise` is refused on the triage step; re-triage is the way to change a level.
- **Skipping:** steps and groups excluded at the level are marked `skipped` as soon as the level is set (`step_skipped {level, cause}`; a group's own path carries it); steps inside groups are marked when their instance's iteration starts. A skipped group's steps never get events.
- **Re-triage** (Decision: [0028](../decisions/0028-retriage.md)): `retriage(run, reason)` reruns triage behind a human gate. It records `retriage_requested {reason, previous_level}` and a `step_revised` of the triage step (`retriage: true`; no dependent is made stale), so triage gets a new attempt whose packet holds the previous result and the reason (§7.1); until it is decided, the triage step is not accepted, so nothing that depends on it can start. The new result always waits on the owner (implicit `triage` gate, whatever the level). **Approve:** `step_passed`, `retriage_applied {level, previous_level, decision_seq, skipped, unskipped, pre_retriage}`, then `step_skipped` / `step_unskipped` for every step that has not started: no attempt dispatched (`blocked_on_deps`, `ready` never dispatched, `skipped`), including steps of a live instance's current iteration; an unexpanded group is skipped or unskipped as one. Started, passed and imported steps never change; passed and imported steps the new level would have skipped or gated differently are listed in `pre_retriage` and flagged in their records. **Reject:** the old level stands and the triage step's earlier result is accepted again (`step_passed` repeating it, `retriage_rejected`). Refused while any attempt of the run is in flight, while another re-triage is pending, or before a level is set.
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

**Tooling capabilities** (`web_access`, `shell`, `file_write`, `code_exec`, `repo_workspace`, `workspace_read`) are provided by a harness's tools and the args its adapter passes, not by the model behind it: a harness provider's tool map in the known-workers data says which args turn each one on, and a step gets only the ones it requires (§6.3; Decision: [0085](../decisions/0085-harness-tool-maps.md)). Recipes name them like any other capability; the vocabulary is unchanged.

### 5.7 Shipped example recipes

| Recipe | Purpose | Exercises |
|---|---|---|
| `fit-check` | Decide whether an idea suits Baton, before investing in it | A minimal recipe: one level, no groups, one human gate |
| `software-feature` | The §5.1 example: a feature from request to accepted slices | Complexity levels, groups, reviews, publishing |
| `backyard-project` | A non-software project (a flower bed vs a shed) | Manual workers, photo artifacts, human gates, levels |
| `recipe-builder` | Turn an owner's described process into a validated recipe they have approved | A judge loop (design and audit), a requirements ledger, script gates, a published process plan, `scope` and `parent` |

**`recipe-builder`** is the guided authoring path (§15.3; the change that added it is `2026-11-recipe-builder`). The owner talks about their work, never about recipes; the recipe is an ordinary one and adds no concept (§2). Its steps and gates:

| Step | Levels | Does | Gates |
|---|---|---|---|
| `profile` (triage) | all | Checks `catalog.summaries` for a recipe that already covers the job; restates the goal; infers first, with a basis for each inference; separates this job's facts (`instance`) from the class of jobs; finds the owner's generality (Decision: [0099](../decisions/0099-owner-owns-generality.md)); detects related processes and reads `recipes/plans/` (Decision: [0102](../decisions/0102-process-plan-location.md)); rates `simple`, `standard` or `complex` | schema; human |
| `research` | standard, complex | Finds how the work is usually done; adds `researched` ledger entries with sources | schema |
| `shape` (group, at most 3 iterations) | all | `design` makes the process in plain terms, using `static/patterns.md`; `audit` (a different vendor) judges it against `static/readiness.md` and the patterns | schema; findings (block on critical, high); human (standard, complex) |
| `generate` | all | Writes the package to `recipes/drafts/<run slug>/` with its `scope` and `parent`, the final ledger beside it, and a plain-language walkthrough | schema; `baton plan`; `baton recipe check`; review (complex) |
| `accept` | all | The owner reads the walkthrough and decides | schema; human |

The requirements ledger carries every requirement, assumption and decision from `profile` to `generate`, so no step relies on a summary: each entry has a `scope`, a `status` (`confirmed`, `researched`, `inferred`, `open`, `excluded`) and a `basis`, and a worker may never promote its own `inferred` entry to `confirmed`. `baton recipe check` enforces the mechanical rules (§5.3). The builder never vendors: after `accept` the Director asks the owner and runs `vendor` on the draft (Decision: [0096](../decisions/0096-vendor-after-accept.md)), and a vendored recipe is never edited in place (Decision: [0097](../decisions/0097-builder-never-edits-vendored.md)). Scenario testing waits for `baton simulate` (Decision: [0098](../decisions/0098-no-scenario-testing-yet.md)).

**`fit-check`** keeps itself to minutes, or it defeats its purpose. It is version 4 (version 2: the profile gained `assumptions`; version 3: `assess` takes the optional `catalog.summaries` input and a `fits` verdict names the existing recipe that covers the idea, as `recipe: {id, version}`, or `null` when none does; version 4: the optional `context` run input, a short text summary of an existing project the idea is about, written by the Director and never read from files by the worker, so a `fits` verdict can name the recipe that covers existing work, Decision: [0134](../decisions/0134-fit-check-takes-optional-project-context.md); a published version is never edited in place, §5.8), and `init` vendors it (§11.6):
1. **`describe`:** a worker profiles the idea, mainly *each occurrence*: how often it happens, how much judgment it needs, how long it takes, which agents and people are involved, whether a repo audit trail is a benefit. Output: a structured profile of the idea. **It infers first** (Decision: [0029](../decisions/0029-fit-check-infers-first.md)): it fills the profile from the idea as far as it reasonably can, lists each inference under `assumptions` (`{field, value, basis}`) for the Director to confirm, and asks only about what it cannot infer, as structured questions (§7.2) in the owner's terms. The rubric's words ("occurrence", "audit trail", "live integration") are internal: a question about a water-vending idea asks about opening a site or serving a customer, not about an "occurrence". An idea that holds several kinds of work (setting up a business *and* running it) is not forced into one profile: the worker says so (`status: blocked`, one question offering the parts as options), and the Director suggests framing it (§11.6).
2. **`assess`:** scores the profile against a fixed rubric (static file in the recipe):

   | Fits Baton | Fits an operations engine |
   |---|---|
   | Few occurrences (at most daily) | Many (per order, ticket, event) |
   | Judgment-heavy, mixed agents, human sign-offs | Mostly automated, predictable |
   | Minutes to days per occurrence | Seconds; latency matters |
   | Repo audit trail is a benefit | Needs live-system integration, uptime, scale |

   Output: `verdict` (`fits` \| `fits_per_occurrence` \| `operations_engine`), reasons tied to rubric rows, and a suggested next step.
3. **Human gate** on the verdict, with its own labels ("That verdict sounds right" / "I don't think that's right", §13.8). Next steps by verdict:
   - `fits`: an existing recipe, or recipe authoring (§15.3).
   - `fits_per_occurrence`: a recipe plus an external scheduler that calls `baton start` for each occurrence.
   - `operations_engine`: start a `software-feature` run whose deliverable is that system, with the engine choice made in its design step.

**`software-feature`** is the §5.1 recipe exactly, shipped with working prompts and review rubrics. Its slice acceptance is a judge (Decision: [0030](../decisions/0030-slice-acceptance-judge.md), found in Phase 16): in the original example `accept` had no gate, so a person answering `accepted: false` still passed the slice; with the human gate in `repeat_until`, rejecting it starts the next iteration at `implement` with the owner's note.

Because it is small, `fit-check` is also the builder's first end-to-end recipe: with the `manual` adapter it is the Phase 4 toy run, and with an API worker it is the first real run in Phase 5.

**Planned `eng-process` recipe:** the proposed engineering workflow preserves eng-process phases and checkpoints using Baton state, handoff and worker machinery. It does not require the eng-process CLI or duplicate authoritative process-state files. Engineering deliverables remain project artifacts. The remaining process policy and implementation are proposed in [2026-11-eng-process-recipe](../changes/2026-11-eng-process-recipe.md). Decision: [0138](../decisions/0138-eng-process-uses-baton-machinery.md). Medium/large plan review is blocking; code review is advisory, with vendors selected through worker profiles. Decision: [0139](../decisions/0139-eng-process-review-policy.md).

### 5.8 Identifiers

Ids name **roles, never positions**. Recipes and plans change over time; an id that encodes order or sequence gets renumbered or reused, and history then attaches to different work. Every rule below exists to keep provenance unambiguous across recipe versions and plan revisions.

- **Step ids** are readable role names (`design`, `code_review`), unique across the whole recipe including groups. The loader rejects positional ids (`step.positional_id`): a positional word (`step`, `stage`, `phase`, `part`, `task`) followed by digits as the whole id or its first segment (`step1`, `phase_3`, `step01_design`); `s` or `p` followed by digits as the whole id (`s2`, `p_3`); or any id ending in `_<digits>` (`review_2`). Role names that merely contain digits (`oauth2_setup`, `s3_upload`) are fine. Readability matters because ids appear in references, step paths, records and the Director's explanations; opaque ids would make recipes hard to author and review.
- **A retired id is never reused** for a different step in a later recipe version. The lockfile records, for every vendored recipe version, its step ids and a per-step signature (kind step/group, enclosing group, output schema hash, required capabilities). When a recipe is vendored or upgraded (§14.2), the runtime compares against all recorded versions and flags: a kept id whose signature changed; an id that was retired and now reappears. Each flag needs an owner decision, recorded with the vendoring.
- **Anything aggregated across runs keys on the qualified id** `<recipe_id>@<version>/<step_path>`, never the bare id: review statistics (§9.2), process statistics and lessons (§12.4), crosswalk targets (§11.3). Inside a run, the run's pinned recipe version and hash (§14.2) qualify every id.
- **`foreach` instance ids are assigned by the runtime**, never by workers. At first expansion each item gets an opaque random token (e.g. `x7f3a9c2`), recorded in `group_expanded`; it is not derived from order or content. Groups without `foreach` get one too. The item stored for an instance (what `item` resolves to) carries its id; change detection compares items without it. The source step's item schema must declare `id` as an *optional* string property and must not require it (`group.foreach_items_need_id`, `group.foreach_id_required`). When the source step is revised, its packet includes the previous items with their ids; the worker echoes the id of every item it keeps (changed or not) and omits `id` on new items. Intake rejects an unknown or duplicated id (an id on the first expansion is unknown). People see item titles; the board shows the title with the id.
- **Attempts and iterations** (`attempt-1`, `i1`) are ordinal by nature: append-only, never renumbered or reused, so their order is their meaning.
