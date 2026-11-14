---
id: 2026-11-quick-runs
title: "An owner can choose a quick guided run instead of a full process for a part of the project, and its result counts as a project document"
status: proposed
level: major
decisions: ["0145", "0142", "0146", "0144", "0147", "0141"]
touches: [design/recipes.md, design/director-interface.md, design/layouts.md, design/persistence.md]
manual: [recipes/recipe-builder.md, recipes/quick-run.md, user/start-with-a-goal.md, admin/recipes-and-vendoring.md, admin/director-commands.md, reference/commands.md]
---

# An owner can choose a quick guided run instead of a full process for a part of the project, and its result counts as a project document

## Request

### Problem

Not every part of a project deserves a rigorous process. An owner setting up a small business may want a business plan good enough to start on, not a researched, reviewed, multi-step one. Today the only way to get Baton's help with a part is to find or build a full recipe for it, through recipe builder, which researches, designs, audits and generates a process. For a one-off document, that costs more than it saves (principle 2).

The owner's direction (Decision [0145](../decisions/0145-quick-runs-through-recipe-builder.md), from `docs/catchall/project-process-linkage.md` §5 E):
- recipe builder offers the choice early, after it checks existing recipes: a full process or a quick guided run;
- a quick run follows a harness-neutral **guidance document**, never a harness-specific skill;
- a catalog of guidance documents ships beside the recipe catalog, and the builder uses one that fits or writes one;
- a shipped one-step recipe dispatches the guidance to a worker, so the result is an accepted deliverable with provenance, not something the owner has to attest;
- no new concept.

Because the result is a deliverable, it is a project document (`2026-11-project-documents`, done), so a later rigorous process can build on a quick one's output, and the other way round.

### Acceptance criteria

- **Guidance documents have a format.** A guidance document is Markdown with front matter (`format: baton-guide/1`, `id`, `version`, `title`, `description`, `produces`: what the run returns). The body covers purpose, what to produce, what good looks like, and what to ask the owner. A check refuses missing fields and vendor names (the recipe neutrality lint, §5.3).
- **A catalog of guides ships.** The package ships a starter set of guides. `guides()` (CLI `baton guides`, MCP, API) lists the shipped guides and the project's own, each with id, version, title, description, `produces` and where it lives.
- **Recipe builder sees the guides.** A new input, `catalog.guides`, gives a step the same listing. Recipe builder's first step reads it beside `catalog.summaries`.
- **Recipe builder offers the choice.** In a new version, `recipe-builder@4`, the `profile` step checks existing recipes first, as today. It then recommends a full process or a quick guided run, saying in the owner's terms what each costs and gives. The owner chooses; the choice is never applied without them. On the quick path, the builder skips research, design, audit and generation. It adopts a fitting guide or writes one, publishes it into the project as a deliverable, and asks the owner to approve it. Projects with `recipe-builder@3` pinned keep it.
- **A quick run follows a guide.** A shipped recipe, `quick-run`, takes a title and the owner's request as run inputs and the guide as a required project document (role `guide`), plus optional context documents (role `context`, `many`). Its one step dispatches them to a worker. The worker returns the deliverable, which the owner approves or sends back with a note. On approval it is published and listed by `documents()` as a deliverable, needing no attestation.
- **It stays quick.** `quick-run` has no triage, no research and no review gate: one dispatch, one owner approval, and attempts bounded as for any step.
- **The Director knows both paths.** The Director skill says when a quick run is worth offering, how to start one from a builder run's guide (binding the guide by role), and that work done entirely outside Baton still enters through `attest`.
- **Manual and design are current.** §5.7 describes the guides and both recipes; the manual has a topic for `quick-run`, an updated recipe-builder topic, and an owner's guide to choosing.

### Open questions

New questions this change raises, each with a suggested answer, to be put to the owner in one batch before Design.

1. **How does recipe builder skip the full path when the owner chooses quick?** A run skips steps only by its ratings (§5.5), and recipe builder rates one scale (`simple`, `standard`, `complex`) at `profile`. *Suggested:* `recipe-builder@4` rates one axis, `approach`, with scale `[quick, simple, standard, complex]` and `confirm_lowest: true`. `quick` then always waits on the owner, and the full-path steps apply from `simple` up. *Rationale:* it uses tailoring as built (0144, 0147) and makes the choice the owner's, recorded with a reason. The cost: a `simple` build, which applies at once today, will ask the owner once to approve the rating. Design should fold that into the profile's existing question so the owner still answers once.
2. **What may a quick run produce?** *Suggested:* one Markdown document in this change, the guide's `produces` naming it. Other media later, if guides need them. *Rationale:* recipes declare artifacts statically. Most "good enough" parts (a plan, a brief, a procedure) are documents, and one artifact keeps `quick-run` one step.
3. **Where are quick-run results and project guides published?** A publish target must be a `paths.*` key that `project.yaml` maps, or `start` is refused. *Suggested:* results to `paths.documents`, defaulting to `docs` when unmapped, as `paths.process_plans` does (0069). Project guides to `guides/<slug>.md`, beside `recipes/plans/`. *Rationale:* no setup step before the first quick run, and project guides sit where `guides()` looks.
4. **Which guides ship first?** *Suggested:* a small, general set: a lean business plan, a marketing plan, a standard operating procedure, a project charter and a decision record. More are added from real use. *Rationale:* they cover the owner's water-vending example end to end and are useful in most projects. A larger catalog is cheap to grow once the format has proved itself.
5. **May an owner start `quick-run` with a catalog guide directly, without recipe builder?** *Suggested:* yes. `guides()` can copy a shipped guide into the project's `guides/` as an owner-attested project document (`guides copy <id> --note`), and `quick-run` then binds it. Recipe builder remains the path for choosing or writing one. *Rationale:* when a fitting guide exists, a builder run only to copy it is friction (principle 2). Attesting the copy keeps the rule that a guide is a project document.
6. **Does the quick run's worker see the workspace?** *Suggested:* no (`workspace: none`). Context arrives only through the `context` role. *Rationale:* quick, bounded and reproducible. What the run used is exactly what was bound.

## Design

Provisional, for review with the Request; settled once the open questions are answered.

### Shape

- **Guides.** Shipped under `examples/guides/` (packaged like the recipe catalog). The project's own live under `guides/`. `guides.py` loads and checks both. `catalog.guides` resolves to `[{id, version, title, description, produces, where}]`, sorted by id.
- **`recipe-builder@4`.** `profile` gains the `catalog.guides` input, an `approach` rating with its reason, and, when `quick`, the chosen or new guide. A new step, `guide` (`applies_to: {approach: [quick]}`), writes or adapts the guide and publishes it to `guides/{{ run.slug }}.md` behind a human gate ("Use this guide?"). Research, shape, generate and accept apply at `simple` and above.
- **`quick-run@1`.** `run_inputs {title, request}`, `project_inputs [{role: guide, media_type: text/markdown}, {role: context, many: true, required: false}]`, one step `produce` (`workspace: none`, structured output plus long-form writing) whose artifact `deliverable` publishes to `{{ paths.documents }}/{{ run.slug }}.md`, with a human gate.
- **Director.** It offers `quick-run` on the builder's quick path, binding the guide the builder published (`start quick-run --bind guide=guides/<slug>.md`). It offers `guides copy` when a shipped guide fits as is.

### Doc edits

- `design/recipes.md` §5.2 (`catalog.guides`), §5.3 (the guide check), §5.7 (guides, `recipe-builder@4`, `quick-run`).
- `design/persistence.md` §10.4: the `paths.documents` default.
- `design/director-interface.md` §13.1–§13.3: `guides`, `guides copy`; the skill's quick-path advice.
- `design/layouts.md`: `examples/guides/`, the project's `guides/`.
- `docs/README.md`: new records.

### Manual edits

- `manual/recipes/quick-run.md` (new, from `manual/recipe-sources/`).
- `manual/recipes/recipe-builder.md`: the choice between a full process and a quick run.
- `manual/user/start-with-a-goal.md`: choosing how much rigor a part gets.
- `manual/admin/recipes-and-vendoring.md`: guidance documents, their format and where they live.
- `manual/admin/director-commands.md` and the generated `manual/reference/commands.md`: `guides`, `guides copy`.

### Decisions

- [0145](../decisions/0145-quick-runs-through-recipe-builder.md) (accepted): the choice in recipe builder, harness-neutral guides, the catalog, the one-step recipe, no new concept.
- [0142](../decisions/0142-project-documents-bound-by-role.md), [0146](../decisions/0146-project-document-details.md) (accepted): guides and results are project documents, bound by role.
- [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md) (accepted): the `approach` axis and `confirm_lowest`.
- [0141](../decisions/0141-implementation-discovery-timing.md) (accepted): recipe builder's discovery, unchanged on the full path.
- The open questions above become records when decided.

## Plan

Provisional slices, refined once the Request and Design are approved. Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: guidance documents and the catalog

- **Outcome:** guides have a checked format; a starter set ships; `guides()` and `catalog.guides` list them.
- **Criteria:** the check's refusals (fields, vendor names); shipped and project guides listed; `catalog.guides` deterministic; `guides copy` attests a copy.
- **Effort:** M

### Slice 2: the `quick-run` recipe

- **Outcome:** a quick run follows a bound guide and publishes an approved deliverable that later runs can bind.
- **Criteria:** loads and vendors; required `guide` role; optional `context`; one dispatch; approve publishes; reject retries with the note; the result is listed by `documents()` as a deliverable; `paths.documents` default.
- **Effort:** M

### Slice 3: `recipe-builder@4`'s quick path

- **Outcome:** recipe builder recommends full or quick, the owner chooses, and the quick path ends with an approved guide in the project.
- **Criteria:** the `approach` rating always waits on the owner at `quick`; the full path unchanged from `@3` at `simple` and above (its scenario tests pass); a fitting shipped guide adopted; a new guide written; `@3` runs keep `@3`.
- **Effort:** L

### Slice 4: the Director and the manual

- **Outcome:** the Director offers quick runs where they fit, and the manual explains the choice.
- **Criteria:** skill text and its §13.3 copy; manual topics and generated references; an end-to-end scenario: recipe builder takes the quick path, the guide is approved, a quick run produces a plan, and a later run binds that plan.
- **Effort:** S

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0145 and `docs/catchall/project-process-linkage.md` (§5 E), against what `2026-11-project-documents` and `2026-11-tailoring-axes` built. No code changed.
- **Owner decision:** 2026-11-14, "Write the B, D, E and F change proposals". The Request is not yet accepted; the open questions above are unanswered.
- **Accepted:** No; proposal only.
