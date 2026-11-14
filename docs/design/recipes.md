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

A recipe may also declare the **project documents** it would like, by role (Decisions: [0142](../decisions/0142-project-documents-bound-by-role.md), [0146](../decisions/0146-project-document-details.md), [0148](../decisions/0148-project-documents-framing-deferred.md)). Additive in `baton-recipe/1`: a recipe without `project_inputs` loads, runs and hashes its packets exactly as before.

```yaml
project_inputs:
  - role: business_plan                  # lowercase id; steps reference it as project.business_plan
    description: "The business's settled plan: its constraints and target customers"
    media_type: text/markdown            # optional: the type a bound document must have
    required: true                       # default true: an unbound role stops the first step that needs it
    many: false                          # default false; true takes one or more documents, in binding order
```

A role says what document the recipe needs, never which recipe or step made it, so a recipe stays shareable (§5.3). A run binds each role to a project document (§10.4) with the owner's confirmation (§8.6, §13.3).

Instead of one scale, a recipe may rate complexity on a few **axes** of its own (Decisions: [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md)). Additive in `baton-recipe/1`: `complexity.levels` and `complexity.axes` are mutually exclusive, told apart by key, and a recipe with `levels` (a one-axis recipe) loads, runs and hashes its packets exactly as before. In a recipe with axes, `applies_to` (on steps, groups and gates) maps an axis to the values at which it applies (§5.5):

```yaml
complexity:
  axes:                                  # each axis a recipe-owned scale, lowest to highest
    discovery: [low, medium, high]
    assurance: { scale: [low, medium, high], confirm_lowest: true }   # its lowest rating also asks the owner
  triage_step: triage                    # outputs ratings {axis: {value, reason}} (§5.5)
steps:
  - id: explore
    applies_to: { discovery: [medium, high] }
  - id: build
    gates:
      - { type: review, applies_to: { assurance: [high] }, reviewer_requires: { capabilities: [technical_reasoning, workspace_read] }, rubric: prompts/rubric.md }
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
| `catalog.summaries` | A summary of each recipe the project can run (Decision: [0106](../decisions/0106-catalog-summaries-input.md)): every vendored recipe (its newest version), then every shipped recipe not vendored, as `{id, version, description, levels, run_inputs, vendored, scope, project_inputs?}`, `scope` being the recipe's scope block (§5.1) or `null`, and `project_inputs` its roles when it declares any (§5.1). The same listing framing receives (§11.6), plus `scope` and `project_inputs`; framing's own listing does not carry roles yet (Decision: [0148](../decisions/0148-project-documents-framing-deferred.md)). Always resolvable: a project with no lockfile lists only the shipped recipes |
| `project.<role>` | The project document the run bound to a role the recipe declares in `project_inputs` (§5.1), from the run's record, never the living file (§8.6) |

"Required" applies only when the source step is included at the run's complexity level. Inputs from skipped steps are omitted and listed as `not_applicable` in the manifest. Expert answers are deliberately **not** referenceable; they enter a run only when promoted (§12.2).

### 5.3 Load-time validation and neutrality lint

The loader (`recipe.py`) rejects a recipe unless:
- Every `steps.<id>` reference names an ancestor via `depends_on` (transitively); there are no cycles; files exist; schemas are valid JSON Schema 2020-12.
- Gate types are known; every capability used is in the declared vocabulary.
- `publish.to` uses only `paths.*`, `run.*` (`id`, `slug`, `title`, `kind`, `inputs`) and `project.*` variables, and only on top-level steps (`publish.in_group`, §10.4).
- Complexity: `levels` or `axes`, never both (`complexity.levels_and_axes`) and not neither (`complexity.no_scale`). The triage step exists and has no `applies_to`. One scale: it outputs `level` constrained to the declared levels, and every `applies_to` is a list of declared levels (a map is `complexity.applies_to_by_axis`). Axes: names match `^[a-z][a-z0-9_]*$` and are not `level` (`complexity.reserved_axis`); every `applies_to` is a map (a list is `complexity.applies_to_list`) naming declared axes (`complexity.unknown_axis`) and values (`complexity.unknown_level`); the triage output schema requires `ratings`, an object with `additionalProperties: false` that requires every axis, each requiring `value` (enum exactly its scale) and `reason` (a string, `minLength` at least 1) (`complexity.ratings_schema_mismatch`); an axis nothing applies by is a warning (`complexity.axis_unused`). For each level, or each combination of ratings, every included step is reachable: a nested step never applies where an enclosing group does not (`complexity.unreachable`). `baton plan <recipe>` prints the per-level table; for a recipe with axes, what always runs and what each rating adds, or with `--rating axis=value` for every axis the table for that combination.
- Ids: per §5.8 (unique, no positional ids; `foreach` items declare an optional `id`).
- Groups: per §5.4; `item` and `group.*` appear only inside groups; `independence.from_step` names the step itself or an ancestor (in the same group if inside one); `protect` appears only on `workspace: write` steps. With `repeat_from`, every step named in `repeat_until` must be at or after it (`group.judge_not_repeated`), and a step listed before it may not depend on one at or after it (`group.depends_on_repeated`).
- A recipe being built can be checked by `baton recipe check <package> --ledger <file>` (Decision: [0108](../decisions/0108-recipe-check-command.md)), which a script gate runs. It reads a requirements ledger (a list of `{id, statement, kind, scope, status, basis, owner_words?}`, `scope` being `class` or `instance`, `status` one of `confirmed`, `researched`, `inferred`, `open`, `excluded`) and reports, one `ERROR <path>: <message>` line each: a malformed ledger or entry; an `open` entry; a `confirmed` entry without `owner_words`; and any `instance` entry whose `statement`, `value` or `owner_words` (at least 8 characters after lower-casing and collapsing whitespace) appears in the package's `prompts/` or `static/` files. The ledger file may be an object `{ledger, discovery}`; with `--require-discovery` it must be, and its `discovery` records (recipe-builder@3, §5.7) are checked: each record's fields and vocabulary; a choice that shapes the process is `decided`, with a comparison that lists options, cites dated sources or states its uncertainty and recommends, and a `decision` naming a confirmed `decision` entry that carries the owner's words; and a choice deferred to the recipe names research, decision and consuming steps that exist in `recipe.yaml`, the research step requiring `web_access`, the decision step having a `human` gate and taking the research output as a required input, and each consuming step taking the decision step's output as a required input. Exit 0 when clean, 1 otherwise. It judges nothing else: whether a design meets its goals, or a comparison is relevant and adequate, is a reviewer's work.
- Project documents: every `project.<role>` names a declared role (`ref.unknown_role`); roles are unique (`project_inputs.duplicate_role`); a malformed entry is `recipe.missing_key`, `recipe.unknown_key` or `recipe.invalid_value`. A role's name or description may not name another recipe or its steps (`neutrality.role_names_recipe`): a qualified reference (`<recipe>@<n>`, `<recipe>@<n>/<step>`), a step reference (`steps.<id>`, `group.steps.<id>`), or the id of a recipe shipped with or built into the runtime (with `_` read as `-`).
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
- **Axes** (Decisions: [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md)): instead of one scale, a recipe may declare a few axes, each with its own ordered scale (§5.1), so a concern that varies on its own changes only the steps and gates it affects. A run's **ratings** give each axis a value. A step, group or gate with `applies_to: {axis: [values], …}` applies when **any** listed axis's rating is among its values (OR across axes and within one; there is no AND); one with no `applies_to` always runs. Gates that differ by axis are separate gate entries (for example a same-vendor reviewer at `assurance: [medium]` and a different-vendor one at `assurance: [high]`; §8.4's independence levels are unchanged). Internally a recipe with `levels` is a recipe with one axis named `level`, so one code path applies both; its events and outputs keep their `level` field. Nothing but `applies_to` is rating-driven.
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
| `fit-check` | Decide whether the work an owner asks for suits Baton, before investing in it | A minimal recipe: one level, no groups, one human gate |
| `software-feature` | The §5.1 example: a feature from request to accepted slices | Complexity levels, groups, reviews, publishing |
| `backyard-project` | A non-software project (a flower bed vs a shed) | Manual workers, photo artifacts, human gates, levels |
| `recipe-builder` | Turn an owner's described process into a validated recipe they have approved | A judge loop (design and audit), a requirements ledger, script gates, a published process plan, `scope` and `parent` |

**`recipe-builder`** is the guided authoring path (§15.3; the change that added it is `2026-11-recipe-builder`). It is version 3 (version 2: a process to be run is not rewritten into a process for building something else, and the system a developed process will run on (a workflow engine, a BPMN or CMMN model, a set of procedures and software) is a fact about the deliverable, never a reason to refuse it; the recipe it produces is still a Baton recipe, not an exporter for an external engine, Decision: [0140](../decisions/0140-fit-check-assesses-requested-work.md); version 3: implementation discovery, below, Decision: [0141](../decisions/0141-implementation-discovery-timing.md)). A project's pinned `recipe-builder@2` keeps its behavior (§5.8). The owner talks about their work, never about recipes; the recipe is an ordinary one and adds no concept (§2). Its steps and gates:

| Step | Levels | Does | Gates |
|---|---|---|---|
| `profile` (triage) | all | Checks `catalog.summaries` for a recipe that already covers the job, including any discovery the job needs (a matching subject is not enough); restates the goal; infers first, with a basis for each inference; separates this job's facts (`instance`) from the class of jobs; finds the owner's generality (Decision: [0099](../decisions/0099-owner-owns-generality.md)); detects related processes and reads `recipes/plans/` (Decision: [0102](../decisions/0102-process-plan-location.md)); records `discovery` (below); rates `simple`, `standard` or `complex` | schema; human |
| `research` | standard, complex | Finds how the work is usually done; adds `researched` ledger entries with sources; compares ways to do each choice that shapes the process; asks the owner (`blocked`) and records their decision | schema |
| `shape` (group, at most 3 iterations) | all | `design` makes the process in plain terms, using `static/patterns.md`; `audit` (a different vendor) judges it against `static/readiness.md` and the patterns | schema; findings (block on critical, high); human (standard, complex) |
| `generate` | all | Writes the package to `recipes/drafts/<run slug>/` with its `scope` and `parent`, the final ledger beside it, and a plain-language walkthrough | schema; `baton plan`; `baton recipe check`; review (complex) |
| `accept` | all | The owner reads the walkthrough and decides | schema; human |

The requirements ledger carries every requirement, assumption and decision from `profile` to `generate`, so no step relies on a summary: each entry has a `scope`, a `status` (`confirmed`, `researched`, `inferred`, `open`, `excluded`) and a `basis`, and a worker may never promote its own `inferred` entry to `confirmed`. `baton recipe check` enforces the mechanical rules (§5.3). The builder never vendors: after `accept` the Director asks the owner and runs `vendor` on the draft (Decision: [0096](../decisions/0096-vendor-after-accept.md)), and a vendored recipe is never edited in place (Decision: [0097](../decisions/0097-builder-never-edits-vendored.md)). Scenario testing waits for `baton simulate` (Decision: [0098](../decisions/0098-no-scenario-testing-yet.md)).

**Implementation discovery (recipe-builder@3).** The owner may know the outcome without knowing how it could be done. The builder identifies material unresolved implementation choices; signals such as recurrence, integrations, durable records, approvals, regulation and bulk data identify *questions*, never a technology (no keyword selects a target). Each choice is a `discovery` record `{id, question, signals?, target_status, named_targets?, timing, timing_reason, graph_effect?, status, comparison?, decision?, generated?}` that `profile` creates, `research` and `design` carry, and the ledger file (`recipes/drafts/<slug>.ledger.json`, now `{ledger, discovery}`) keeps. `target_status` says how the owner named a target: `firm_constraint` (settled, never compared away), `preference`, `example` or `none`. `timing` is:
- `before_design`: the choice changes the stages, workers, deliverables or checks, so it is researched while the process is being authored and the owner decides it before the affected design. `research` fills `comparison` (criteria tied to the requirements; options of any kind, existing products, frameworks, standards, manual procedures or custom work, each with what building the process would need and its sources and the date each was read; exclusions; uncertainty; a recommendation), returns `blocked` with one structured question per choice, and, when the owner's confirmed answers arrive (`prior_feedback.answers`, recorded by the runtime), sets `status: decided` with a `decision` entry in the ledger (`kind: decision`, `confirmed`, with the owner's words). A choice that shapes the process makes the work at least `standard`: the profile's schema rejects `simple` alongside it, so research is reachable (a skipped step is never dispatched). The research and design schemas refuse an unanswered choice, so a shaping choice discovered later returns through `blocked` and a revision of research, never by adding stages.
- `in_generated_recipe`: one process shape accommodates the alternatives, so the generated recipe researches the options for each job, has the owner decide, and hands the choice to the stages that use it. The design names them in `generated {research_step, decision_step, consumers}` and `generate` writes them as ordinary steps (research, then a `human`-gated decision, then the consumers, each taking the decision as a required input); the walkthrough says when the owner will choose. `profile` recommends an existing recipe only if its own steps would do the discovery the job needs. Whether the target is a run input or part of the agreed scope follows the owner's chosen generality (Decision: [0099](../decisions/0099-owner-owns-generality.md)).
- `settled` and `not_needed` records carry only their reason. At least one record is always returned, so discovery cannot disappear silently; a small, settled job gets one line and no comparison.

`baton recipe check --require-discovery` (§5.3) enforces the form mechanically; `audit` (rubric checks 16 to 20) judges relevance, adequacy and timing. A recommendation is never the owner's choice, and a deliberate `in_generated_recipe` record is a settled requirement of the process, not an `open` entry the ledger check would stop. Excluded: an engine directory, built-in exporters, operating external systems, a universal preferred target, new SME subjects, dynamic recipe rewriting. Decision: [0141](../decisions/0141-implementation-discovery-timing.md); change: [2026-11-recipe-implementation-discovery](../changes/2026-11-recipe-implementation-discovery.md).

**`fit-check`** keeps itself to minutes, or it defeats its purpose. It is version 5 (version 2: the profile gained `assumptions`; version 3: `assess` takes the optional `catalog.summaries` input and a `fits` verdict names the existing recipe that covers the idea, as `recipe: {id, version}`, or `null` when none does; version 4: the optional `context` run input, a short text summary of an existing project the idea is about, written by the Director and never read from files by the worker, Decision: [0134](../decisions/0134-fit-check-takes-optional-project-context.md); version 5: it assesses the *work the owner asks for*, and `operations_engine` becomes the general `not_recommended`, Decision: [0140](../decisions/0140-fit-check-assesses-requested-work.md). A published version is never edited in place, §5.8, so a project's pinned `fit-check@4` and its recorded `operations_engine` verdicts keep their meaning), and `init` vendors it (§11.6):
1. **`describe`:** a worker establishes what work is being asked for and profiles one unit of *that* work. `scope` has a `kind` (`developing_a_process`, `executing_a_process` or `other_work`), a `statement`, and an optional `target`: where a developed process will run or be used (a workflow engine, a BPMN or CMMN model, a set of procedures, templates and software). The target describes the deliverable; it is never scored, so a finished process's volume, speed, inference needs or dedicated environment cannot disqualify the project that develops it. `work` holds frequency, judgment, dependent reasoning, handoffs, duration, participants and sign-offs, record value, and latency, integration and bulk-processing demands. **It infers first** (Decision: [0029](../decisions/0029-fit-check-infers-first.md)): it fills the profile from the request as far as it reasonably can, lists each inference under `assumptions` (`{field, value, basis}`) for the Director to confirm, and asks only about what it cannot infer, as structured questions (§7.2) in the owner's terms; a clear request needs none. The recipe's own words ("scope", "dependent reasoning", "bulk processing") are internal. A request that holds distinct work (building a process *and* running it, setting up a business *and* running it) is never forced into one profile and never silently narrowed: the worker says so (`status: blocked`, one question offering the parts as options), and the Director suggests framing it (§11.6).
2. **`assess`:** scores the profile against a fixed rubric (static file in the recipe), one reason per row, each stating which way the row leans and whether it rests on a `stated` fact or an `assumed` one:

   | Row | Leans Baton | Leans against Baton |
   |---|---|---|
   | coordination | Several workers or people, handoffs, sign-offs, consistency across steps | One worker, one short step, nothing to hand off |
   | dependent_reasoning | Later work depends on earlier reasoning that should be checked | Little reasoning, or independent pieces |
   | recurrence | Each occurrence substantial and worth its own run | So many or so small that a run each costs more than it returns |
   | duration | Minutes to days | Seconds; latency matters |
   | record | A repository record is a benefit | Needs live integration, uptime or bulk processing a run cannot supply |

   Frequency and duration are signals, never standalone cutoffs. Output: `verdict` (`fits` \| `fits_per_occurrence` \| `not_recommended`), `assessed_work` (which work was scored), reasons tied to rubric rows, and a concrete next step. `not_recommended` carries an `alternative` (a script, asking an assistant directly, an existing tool, a manual procedure, an operations engine) and, for work that was to be executed, may carry a `development_offer`; neither appears with another verdict.
3. **Human gate** on the verdict, with its own labels ("That verdict sounds right" / "I don't think that's right", §13.8). Next steps by verdict:
   - `fits`: an existing recipe that covers *all* the assessed work, or recipe authoring (§15.3) when none does. Missing recipe coverage, or a deliverable `software-feature` does not produce, is never a negative verdict, and `software-feature` is not forced onto work it does not cover.
   - `fits_per_occurrence`: each occurrence fits and is substantial, and something external starts the runs: a recipe plus an external scheduler that calls `baton start` for each occurrence. A scheduler does not make unsuitable execution fit.
   - `not_recommended`: the `alternative`. Accepting the verdict does not select the replacement project: developing a suitable process or system is a separate goal the Director confirms with the owner (§13.8) before anything starts, and adoption stops (§11.1).

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
