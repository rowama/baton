# Proposal: recipe-builder Recipe

Nov 5, 2026 · @Rob

## Goal and scope

Ship a catalog recipe, `recipe-builder`, that turns an owner's one-line description of a process into a validated, vendorable Baton recipe the owner has approved in plain language. It fills the gap the design already reserves: fit-check's `fits` verdict points to "recipe authoring (§15.3)", which does not exist yet.

**In scope**

- Authoring a new recipe from a bare description.
- Specializing an existing recipe (vendored or in the catalog) instead of starting from scratch.
- Producing every package file: `recipe.yaml`, prompts, schemas, static files.
- Proving the package loads and plans at every level before the owner sees it.

**Out of scope**

- Changing a recipe during a live run (the Director never modifies a process, §1.4 #10).
- Runtime features: the builder is an ordinary recipe and needs no new concept (§2).
- Publishing to a public repo or recipe owner upstream; that is a separate, later change.
- Self-improvement of recipes from run evidence (held as its own change).

The guiding rule is the same as for every recipe: the builder's own friction must pay for itself (§1.1 #2). A flower-bed recipe should take minutes of owner time, not an interview.

## Where it starts

The builder accepts the owner's words alone and uses richer context when it exists, so every entry path lands in the same run.

| Entry path | How the run starts | What it carries in |
| --- | --- | --- |
| fit-check says `fits`, no recipe matches | The Director offers recipe authoring as the verdict's next step | The idea and fit-check's profile, including its confirmed `assumptions` |
| Framing proposes it for a part | Proposed like any catalog recipe once shipped; vendored on selection (decision 0042) | The part's label and description, in the owner's terms |
| Owner asks directly ("I need a process for…") | `baton start recipe-builder` with the owner's words | The idea only |

**Run inputs** (`schemas/run_inputs.json`)

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | Short name for the work item |
| `idea` | yes | The owner's words, verbatim |
| `profile` | no | A fit-check profile; the first step uses it instead of re-asking |
| `base_recipe` | no | `id@version` of a recipe to specialize, when the owner or framing named one |

To propose specializing, the first step needs summaries of the vendored and catalog recipes. Framing gets these because the runtime builds its run inputs (§11.6); an ordinary recipe has no such input source today. This is the one runtime touch the proposal needs (see *Runtime impact*).

## Steps

Six steps, two owner approvals, and one bounded design–audit loop. Elicitation is not a step: any worker that cannot infer something returns `blocked` with structured questions (decision 0031), and the Director takes them to the owner.

| Step | Levels | Worker does | Output | Gates |
| --- | --- | --- | --- | --- |
| `profile` (triage) | all | Checks existing recipes first; restates the goal, scope, trigger, end state and success measure; infers first with a basis for each inference; separates this job's facts from the class of jobs; reads any earlier process plan; detects related processes and asks: one process or several, and if several, which to build now; offers a generality ladder and proposes the owner's balance point; rates the level | Ledger v1, `level`, restated goal, proposed rung (or an existing recipe), process plan when split | schema; human: "Is this what the process should do?" |
| `research` | standard, complex | Finds how this class of work is normally done: stages, standards, rules, common failures, who usually signs off | Ledger v2 with `researched` entries and sources | schema |
| `design` (in loop) | all | Designs the process for the chosen rung, in plain terms first: stages, who does each (person, AI, automatic check), what each needs and hands on, owner decisions, what happens on failure | Process design doc, ledger update | schema |
| `audit` (judge) | all | Independent review of the design against the ledger, the chosen rung and the readiness checklist | `baton:findings` | findings, block on critical and high; human (standard, complex): "Is this the process you want?" |
| `generate` | all | Translates the approved design into a Baton package, including its scope block, and writes it to the project | Package files, commit, process summary | schema; script: `baton plan`, ledger check, instance-leak check; review (complex): package matches design |
| `accept` | all | The owner reads a plain-language walkthrough of the finished process, including which jobs it covers | Owner decision | human: "Use this process?" |

At standard and complex levels the owner approves the design before generation, because changing a design is cheaper than changing a package. That approval is a human gate on the `audit` judge, after its findings pass; rejecting it starts the next iteration at `design` with the owner's note, the same way `accept` works in `software-feature`. At simple level the final `accept` is the only approval beyond confirming the goal.

Above the lowest level, triage also carries an implicit owner approval of the level (decision 0008). The Director folds it into the same conversation as the goal confirmation, so the owner sees one exchange, not two.

## How general a recipe should be

The right level of generality is the owner's call, not Baton's. A new recipe is cheap in Baton, and the owner may never share it or contribute it to the catalog. So the builder does not push toward reuse. Its job is to find the **owner's balance point**: the narrowest recipe that covers every job the owner expects to run through it, and no narrower.

**What sets the range a recipe can cover.** One step graph absorbs variation in four places: run inputs (what this job is), complexity levels (steps and gates added or skipped), worker judgment inside a step, and, past that, a different recipe. A recipe can widen until a step, gate or decision-maker would have to change in a way levels cannot express. A flower bed and a shed share one graph (survey, design, materials, build, photograph), so "backyard project" is a valid recipe. A kitchen remodel brings permits, trades and inspections, so "home project" is past the edge.

Within that range, the owner decides where to sit.

**How the builder finds the balance point**

1. **Check what already exists.** If a vendored or catalog recipe covers the job as is, or with new levels, the builder says so first. Authoring is the last resort.
2. **Listen for the owner's horizon.** `profile` looks for signals in the owner's words: other jobs they mention ("and maybe a shed next spring"), repetition ("we do this for every client"), other people or sites, or a one-off ("just this bed"). Each signal is a `class` ledger entry with its basis.
3. **Offer a short ladder, in the owner's terms.** Two or three rungs, each naming the jobs it covers and what it costs the owner now: "Just flower beds", "Any garden bed", "Yard projects, including a shed". No rung is labeled better.
4. **Default to the narrowest rung that covers what the owner said.** With no signal of other jobs, the builder proposes the narrow rung and moves on. It asks only when the signals point both ways.
5. **Widen on evidence, later.** When a future idea nearly fits an owner's recipe, framing or the builder offers to widen that recipe as a new version, instead of authoring a sibling. Generality grows from the owner's real jobs, not from a guess made on day one.

**What generality must not cost.** Too narrow and the second job needs a new recipe. Too broad and the prompts cannot say anything specific, so the gates check little. Either way, the specifics of *this* job belong in run inputs, never in the recipe text. Sharing or contributing a recipe is a separate, optional act the owner may never take.

## Related processes: one recipe or several

Some ideas hold several independent but related processes. "Set up a business to sell a software service, and run it" holds setting up the business, building the service, and running the business. The builder detects this and lets the owner choose. As with generality, it is the owner's call.

**Detection.** `profile` flags a candidate split when parts of the idea have different end states, different people or schedules, or could be done on their own; `design` can raise one later if a stage turns out to stand alone. Each part is named in the owner's terms, with what it hands to the others.

**The owner's choice**

| Choice | What the builder does | What the owner takes on |
| --- | --- | --- |
| One process | Designs one recipe that stitches the parts together, drawing on existing recipes that cover parts (as groups, levels and steps) | One process to follow |
| Separate processes | Records the split, then asks which one to build in this run; builds only that one | Several processes in the project, each started and followed on its own, handing work on through published documents (a fair warning, until Baton has a manager for many processes) |

**The decision scopes only this build.** Choosing separate processes does not start building all of them. The owner picks one now; the others wait.

**Nothing is lost.** The split, the parts, the options offered and the owner's words are recorded as usual (a confirmed ledger entry and the gate's `human_decision`) and published as a **process plan** in the project. A later run of the builder reads the plan first, says which parts are still unbuilt, and offers to build one, so the owner never has to describe the business again.

**Operations parts.** Baton does not run day-to-day operations itself (§1.3), so a part like "run the business" becomes a process that *builds* the operations: its deliverable is a business operations package (SOPs, templates, communication plans, and software where needed). The builder treats it like any other part. It can be stitched into one recipe or built as its own process, and any software element can go through `software-feature` or its own part.

## Process at a glance

&#91;embedded content: recipe-builder flow · 6 steps, 1 loop, 3 owner decisions\]

Findings or a rejected design send the loop back to `design`; reaching the third iteration without passing escalates to the owner instead of looping again.

## The requirements ledger

One structured artifact, the ledger, carries every requirement, assumption and decision from `profile` to `generate`, so no step relies on a summary of an earlier one. It is a recipe artifact passed by the runtime, not a new concept (§2).

Each entry: `{id, statement, kind, scope, status, basis, owner_words?, source?}`. The `basis` field follows fit-check's existing `assumptions {field, value, basis}` shape.

`scope` keeps the owner's job apart from the recipe:

- `class`: true of every job the recipe will cover ("every bed needs a soil check"). These shape the recipe.
- `instance`: true of this job only ("the bed is 3 m by 1 m, in full sun"). These become an example run input and a test case for the finished recipe, never recipe text.

An owner fact is `instance` by default. It becomes `class` only when the chosen rung says every covered job shares it.

| Status | Set by | Meaning | Can `generate` use it? |
| --- | --- | --- | --- |
| `confirmed` | The owner, through a confirm-back | The owner said so | Yes |
| `researched` | `research` | Backed by a cited source; not yet owner-approved | Yes, if not consequential |
| `inferred` | Any worker | A best guess with its basis | Only after confirmation, if consequential |
| `open` | Any worker | Unknown or unresolved | No: `audit` raises a high finding |
| `excluded` | The owner | Deliberately out of scope for this version | Recorded as a stated limit |

The rule that matters: a worker may not promote its own `inferred` entry to `confirmed`. Only an owner answer, recorded through `decide … retry --answers` or a human gate, does that. This keeps plausible guesses from hardening into requirements.

*Consequential* means the entry changes who does a step, what a gate checks, or what the owner gets at the end. `audit` judges this, not the worker that wrote the entry.

## Owner experience

The owner talks about their work, never about recipes. Nothing new is needed for this: the builder relies on the existing split between deterministic machinery and human conversation (Principle 5, decision 0025).

- **Workers decide what to ask; the Director decides how.** Questions arrive as structured `questions_for_human` with `best_guess` where the worker has one. The Director offers guesses for confirmation, one topic at a time, and checks each question before asking it.
- **The Director never designs.** It does not infer requirements, research the subject or fix a weak question itself; it sends the step back with a note (director skill, *Before you ask the owner anything*). Subject questions from the owner go to the `project` SME.
- **Infer first, ask little.** Research answers what it can before the owner is asked. The owner supplies intent, priorities, preferences and approvals, not facts a worker could look up.
- **The owner never reads YAML.** Both approvals show plain-language material: the restated goal, then a walkthrough of the process (who does what, what the owner decides, what happens when something fails, what is out of scope).
- **Confirm-back before anything is recorded** (§13.8). An owner's answer becomes a `confirmed` ledger entry only after the Director has read it back and the owner agreed.

Target (not yet measured): a simple run costs the owner three exchanges: confirm the goal, answer the few questions the worker could not infer, approve the walkthrough.

## Readiness

A recipe is ready when every check below passes. Mechanical checks are gates in code (ground rule 2, determinism over prompting); judgment checks are findings from an independent `audit`. The owner sees neither list, only the walkthrough.

| Check | Kind | Where |
| --- | --- | --- |
| Package loads, passes the neutrality lint, and every step is reachable at every level | Script | `generate`: `baton plan <package>` |
| Ledger has no `open` entry; every `confirmed` entry carries the owner's words | Script | `generate`: a small checker shipped in the recipe's `static/` |
| No `instance` ledger value appears in the package's prompts or static files | Script | `generate`: instance-leak check in `static/` |
| Every goal maps to a step whose output shows it was met | Finding | `audit` |
| Every step's inputs have a producer; no circular dependency | Finding (design) then script (package) | `audit`, then `baton plan` |
| Every output has an acceptance check, not just "worker finished" | Finding | `audit` |
| Every foreseeable failure has a disposition: retry, revise, escalate, stop, or accepted risk | Finding | `audit` |
| Every consequential `inferred` entry was confirmed | Finding | `audit` |
| Loops are bounded and say what happens at the limit | Finding | `audit` |
| Too narrow: a job the owner placed inside the chosen rung would need a step the design lacks | Finding, block on high | `audit` |
| Too broad: a step's instructions cannot say anything specific to the work, so its check is empty | Finding, block on high | `audit` |
| Script gates in the new recipe run only commands the owner would expect | Finding, block on high | `audit` and `generate` review |
| The package implements the approved design and nothing more | Finding | `generate` review (complex) |

Complete means complete within the agreed scope: every material requirement and foreseeable failure is handled, and anything left out is an `excluded` ledger entry the walkthrough names.

The script-gate row matters for safety. Vendored recipes are trusted code because their script gates run commands (README, *Vendoring*), so a generated recipe gets the same scrutiny as one downloaded from elsewhere.

## Complexity levels

The recipe's scale is `simple`, `standard`, `complex`, rated by `profile` from the process being authored, not from the owner's experience. The runtime applies the level; the Director has no say (§5.5).

|  | simple | standard | complex |
| --- | --- | --- | --- |
| Example | Planting a flower bed | Building a she shed | A regulated product launch |
| Level approval | Automatic (decision 0008) | Owner | Owner |
| `research` | Skipped | Runs | Runs |
| Owner approves design | No | Yes | Yes |
| Audit independence | Different vendor | Different vendor | Different vendor |
| Loop limit (`max_iterations`) | 3 | 3 | 3 |
| Review of generated package | No | No | Yes, block on high |

The rating criteria live in `prompts/profile.md`. Signals for a higher level: several kinds of worker, physical-world steps, money or legal exposure, steps that cannot be undone, more than one decision-maker.

Audit independence and the loop limit are the same at every level because the format sets each once per step or group (`independence`, `max_iterations`, §5.4). Varying them by level would need a runtime change; the proposal does not ask for one.

## Recipe sketch

A first draft of `recipe.yaml`, written against the `fit-check` and `software-feature` examples. It is unvalidated; items marked **\[VERIFY\]** must be checked against the loader before building.

```yaml
id: recipe-builder
version: 1
format: baton-recipe/1
capabilities_vocab: baton-capabilities/1
description: Turn a described process into a validated recipe the owner approves.

run_inputs:
  schema: schemas/run_inputs.json        # title, idea, profile?, base_recipe?

defaults:
  max_attempts: 3

complexity:
  levels: [simple, standard, complex]
  triage_step: profile                   # [VERIFY] triage step may also emit non-level output

steps:
  - id: profile
    title: Understand the process
    requires: { capabilities: [structured_output, long_form_writing, technical_reasoning], tier: strong }
    prompt: prompts/profile.md
    inputs:
      - { name: idea,        from: run.inputs.idea,        required: true }
      - { name: profile,     from: run.inputs.profile,     required: false }
      - { name: base_recipe, from: run.inputs.base_recipe, required: false }
      - { name: recipes,     from: catalog.summaries,      required: false }   # [VERIFY] needs the runtime input source
    output_schema: schemas/profile_out.json   # level, reasons, goal, ledger
    gates:
      - { type: schema }
      - { type: human, prompt: "Is this what the process should do?",
          labels: { approve: "Yes, that's it", reject: "Not quite" } }

  - id: research
    title: Learn how this work is usually done
    depends_on: [profile]
    applies_to: [standard, complex]
    requires: { capabilities: [structured_output, long_form_writing, web_access], tier: strong }
    prompt: prompts/research.md
    inputs:
      - { name: ledger, from: steps.profile.output, required: true }
    output_schema: schemas/research_out.json  # ledger with researched entries + sources
    gates: [ { type: schema } ]

  - id: shape
    title: Design and audit the process
    depends_on: [profile, research]          # a skipped research counts as satisfied
    repeat_until: group.steps.audit.gates.passed
    repeat_from: design
    max_iterations: 3
    steps:
      - id: design
        requires: { capabilities: [structured_output, long_form_writing, technical_reasoning], tier: strong }
        prompt: prompts/design.md
        inputs:
          - { name: profile,       from: steps.profile.output,              required: true }
          - { name: research,      from: steps.research.output,             required: false }
          - { name: open_findings, from: group.previous_iteration.findings, required: false }
        output_schema: schemas/design_out.json
        artifacts:
          - { name: design_doc, required: true, media_type: text/markdown }
        gates: [ { type: schema } ]
      - id: audit
        depends_on: [design]
        requires: { capabilities: [structured_output, technical_reasoning], tier: strong }
        independence: { from_step: design, level: different_vendor }
        prompt: prompts/audit.md
        inputs:
          - { name: design, from: group.steps.design.output, required: true }
          - { name: rubric, from: static.readiness.md,       required: true }
        output_schema: baton:findings
        gates:
          - { type: findings, block_on: [critical, high] }
          - { type: human, applies_to: [standard, complex],
              prompt: "Is this the process you want? Saying no sends it back with your note." }

  - id: generate
    title: Build the recipe package
    depends_on: [shape]
    requires: { capabilities: [structured_output, file_write, shell, repo_workspace], tier: strong }
    workspace: write
    prompt: prompts/generate.md
    inputs:
      - { name: design,  from: steps.shape.output, required: true }   # [VERIFY] how a group's final result is referenced
      - { name: profile, from: steps.profile.output, required: true }
    output_schema: schemas/generate_out.json   # commit_sha, package_path, summary
    artifacts:
      - { name: walkthrough, required: true, media_type: text/markdown }
    gates:
      - { type: schema }
      - { type: script, run: "baton plan recipes/drafts/{{ run.slug }}", timeout_s: 120 }  # [VERIFY] run.* in script gates
      - { type: script, run: "python static/check_ledger.py", timeout_s: 60 }            # [VERIFY] path of recipe static files at gate time
      - type: review
        applies_to: [complex]
        block_on: [critical, high]
        reviewer_requires: { capabilities: [structured_output, technical_reasoning, workspace_read], tier: strong }
        independence: { from_step: generate, level: different_vendor }
        rubric: prompts/package_review_rubric.md

  - id: accept
    title: Owner approves the finished process
    depends_on: [generate]
    requires: { capabilities: [human_judgment] }
    prompt: prompts/accept.md
    inputs:
      - { name: walkthrough, from: steps.generate.artifacts.walkthrough, required: true }
    output_schema: schemas/accept_out.json
    gates:
      - { type: schema }
      - { type: human, prompt: "Use this process?",
          labels: { approve: "Yes, use it", reject: "Change something first" } }
```

Package layout:

```
recipe-builder/
├── recipe.yaml
├── prompts/      profile.md  research.md  design.md  audit.md  generate.md
│                 package_review_rubric.md  accept.md
├── schemas/      run_inputs.json  profile_out.json  research_out.json  design_out.json
│                 generate_out.json  accept_out.json  ledger.json
└── static/       readiness.md  check_ledger.py
```

## Runtime impact, open decisions and next steps

The builder adds no concept, command or file type to the concept budget (§2). It needs two small runtime additions, one format change and eight decisions.

**Runtime addition**

- An input source that gives an ordinary recipe step the summaries of vendored and catalog recipes, the same summaries framing already receives (§11.6). Without it, the builder can author from scratch but cannot check existing recipes first or propose specializing.
- The same summaries for fit-check. Today its inputs are only `title` and `idea`, so its `fits` verdict ("an existing recipe, or recipe authoring") cannot name the existing recipe. On the standalone path nothing matches a recipe after fit-check; only framing does.

**Format change: a scope block for recipes**

Today a recipe is discovered by its one-line `description` and run-input schema. `backyard-project`'s description lists examples ("a flower bed, a raised bed, a shed"), which works as a scope statement for three dissimilar recipes. It will not tell near neighbours apart (garden beds vs backyard projects; a website vs any software). Proposed optional block, written by the builder from the chosen rung:

```yaml
scope:
  covers:   ["a flower bed", "a raised bed", "a garden shed"]       # example jobs
  not_for:  [{ job: "a kitchen remodel", use: "home-renovation" }]  # near misses
  varies_by: ["size", "materials", "whether a permit is needed"]   # absorbed by inputs and levels
```

Framing, fit-check and the builder read the same block. A new format version (`baton-recipe/2`) is needed, unless the block can be optional in version 1.

**Open decisions** (each becomes a decision record, `status: proposed`)

1. **Where drafts live.** Proposed: `recipes/drafts/<run slug>/` in the project, committed by `generate`. Alternative: a new `paths.recipes` key in `project.yaml`.
2. **How a finished recipe is vendored.** Proposed: after `accept`, the Director asks the owner and runs `vendor` on the draft (owner approval recorded as with any vendoring). The builder never vendors on its own.
3. **Whether the builder may change a vendored recipe.** Proposed: no. Specializing or widening always produces a new recipe id or a new version, never an edit in place (§5.8).
4. **Scenario testing.** A dry run through every branch, loop and level would be the strongest check, but `baton simulate` is only planned (§15.3). Proposed: ship without it, and add it as a gate when it exists.
5. **Who owns generality.** Proposed: the owner. The builder defaults to the narrowest rung that covers the jobs the owner named, and never widens a recipe for the sake of the catalog.
6. **Matching rule when several recipes fit.** Proposed: prefer the owner's own recipes, then the most specific recipe that covers the whole job (it carries more domain knowledge), then the more general one. Ties go to the owner.
7. **Widening on evidence.** Proposed: when a new idea nearly fits an owner's recipe, framing or the builder offers a widened new version of it before proposing a new recipe. Needs the scope block to tell "nearly fits" from "fits".

Decision 8, continuing the list above:

8. **Where the process plan lives and how later builds find it.** Proposed: a published artifact at a fixed project path (for example `recipes/plans/<plan id>.md`), read by `profile` with `workspace: read`. Alternative: a run input the Director supplies from the plan. Stitching one large recipe also needs the full text of existing recipes, not just their summaries: vendored ones are readable in the project; catalog ones ship inside the runtime package, so this ties into runtime addition 1.

**Next steps**

- [ ] Settle the eight decisions and the scope-block format change.
- [ ] Resolve the \[VERIFY\] items against the loader.
- [ ] Write this up as a change doc in `docs/changes/` from `TEMPLATE.md`.
- [ ] Build the package and run it end to end on two real cases: a simple one and a standard one.
- [ ] Ship it in `examples/recipes/` so framing and fit-check can propose it.

## Sources

All from [rowama/baton](https://github.com/rowama/baton) at commit `03c4055`.

- `docs/principles.md`: ground rules, Principles 1–5, guarantees, key decisions, concept budget
- `docs/design/recipes.md`: groups, judges, complexity and triage (§5.4, §5.5), fit-check verdicts, identifiers (§5.8)
- `docs/design/gates-and-reviews.md`: gate types, findings, waivers
- `docs/design/director-interface.md`: `decide`, director skill rules on questions and talking to the owner
- `docs/design/packets.md`: `questions_for_human`, `prior_feedback.answers`
- `docs/design/adoption-and-framing.md`: framing inputs, vendoring on selection, catalog (§11.6)
- `docs/design/platform-and-security.md`: §15.3 guided process authoring
- `docs/design/runtime.md`: reviewer independence levels
- Decisions 0008, 0025, 0026, 0029, 0030, 0031, 0042, 0043
- `examples/recipes/fit-check/recipe.yaml`, `examples/recipes/software-feature/recipe.yaml`, `vocab/baton-capabilities-1.yaml`, `README.md` (*Vendoring*)
