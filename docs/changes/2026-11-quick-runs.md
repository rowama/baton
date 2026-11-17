---
id: 2026-11-quick-runs
title: "An owner can choose a quick guided run instead of a full process for a part of the project, and its result counts as a project document"
status: in-progress
level: major
decisions: ["0145", "0163", "0162", "0142", "0146", "0144", "0147", "0141"]
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
- **Recipe builder offers the choice.** In a new version, `recipe-builder@5`, the `profile` step checks existing recipes first, as today. It then recommends a full process or a quick guided run, saying in the owner's terms what each costs and gives. The owner chooses; the choice is never applied without them. The owner is still asked once at `profile`: one question confirms what the process should do and the approach together. On the quick path, the builder skips research, design, audit and generation. It adopts a fitting guide or writes one, publishes it into the project as a deliverable, and asks the owner to approve it. Projects with `recipe-builder@4` pinned keep it.
- **A shipped guide can be used directly.** `guides copy <id> --note "<owner's words>"` copies a shipped guide into the project's `guides/` and records the owner's attestation of the copy, so `quick-run` can bind it without a recipe builder run.
- **A quick run follows a guide.** A shipped recipe, `quick-run`, takes a title and the owner's request as run inputs and the guide as a required project document (role `guide`), plus optional context documents (role `context`, `many`). Its one step dispatches them to a worker. The worker returns the deliverable, which the owner approves or sends back with a note. On approval it is published and listed by `documents()` as a deliverable, needing no attestation.
- **It stays quick.** `quick-run` has no triage, no research and no review gate: one dispatch, one owner approval, and attempts bounded as for any step.
- **The Director knows both paths.** The Director skill says when a quick run is worth offering, how to start one from a builder run's guide (binding the guide by role), and that work done entirely outside Baton still enters through `attest`.
- **Manual and design are current.** §5.7 describes the guides and both recipes; the manual has a topic for `quick-run`, an updated recipe-builder topic, and an owner's guide to choosing.

### Open questions (decided)

The six questions this change raised were put to the owner with suggested answers. The owner discussed 1 and 5 first and accepted all six (Decision [0163](../decisions/0163-quick-runs-details.md), 2026-11-17).

1. **How does recipe builder skip the full path when the owner chooses quick?** `recipe-builder@5` rates `approach: [quick, simple, standard, complex]` with `confirm_lowest: true`; `quick` requires `software: none` (Decision [0162](../decisions/0162-builder-step-design-details.md), item 3), and the full-path steps apply from `simple` up. Because every set of ratings now waits on the owner, `profile` drops its own human gate and the triage gate is its one question: what the process should do and the recommended approach, together.
2. **What may a quick run produce?** One Markdown document, named by the guide's `produces`. Other media later, if guides need them.
3. **Where are quick-run results and project guides published?** Results to `paths.documents`, defaulting to `docs` when unmapped, as `paths.process_plans` does (0069). Project guides to `guides/<slug>.md`.
4. **Which guides ship first?** A lean business plan, a marketing plan, a standard operating procedure, a project charter and a decision record.
5. **May an owner start `quick-run` with a catalog guide directly, without recipe builder?** Yes: `guides copy <id> --note` copies the shipped guide into `guides/` as an owner-attested project document, which `quick-run` binds by role. `quick-run` has one way to get its guide. Recipe builder remains the path for choosing or writing one.
6. **Does the quick run's worker see the workspace?** No (`workspace: none`); context arrives only through the `context` role.

## Design

Settled by the answers of Decision 0163. Approved by the owner with the Request on 2026-11-17.

### Shape

- **Guides.** Shipped under `examples/guides/` (packaged like the recipe catalog). The project's own live under `guides/`. `guides.py` loads and checks both. `catalog.guides` resolves to `[{id, version, title, description, produces, where}]`, sorted by id.
- **`recipe-builder@5`.** `approach` gains `quick` below `simple`, with `confirm_lowest: true`; the profile schema requires `software: none` with `quick`. `profile` gains the `catalog.guides` input and, when `quick`, the chosen shipped guide or the brief for a new one. `profile` drops its declared human gate: the implicit triage gate, which now always opens, is its one owner question, and the Director presents it with the profile's summary and the recommended approach in the owner's terms. A new step, `guide` (`applies_to: {approach: [quick]}`), writes or adapts the guide and publishes it to `guides/{{ run.slug }}.md` behind a human gate ("Use this guide?"). Research, shape, generate and accept apply at `simple` and above. Version 4 is frozen as `tests/fixtures/recipes/recipe-builder-v4`, as versions 2 and 3 were.
- **`guides copy`.** `baton guides copy <id> --note "<owner's words>"` (CLI, MCP, API) copies a shipped guide to `guides/<id>.md` and attests it (§10.4), refusing to overwrite an existing file.
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
- [0163](../decisions/0163-quick-runs-details.md) (accepted): the answers to this change's six open questions.
- [0162](../decisions/0162-builder-step-design-details.md) (accepted): the `approach` axis that `quick` joins, and `software: none` with `quick`.
- [0142](../decisions/0142-project-documents-bound-by-role.md), [0146](../decisions/0146-project-document-details.md) (accepted): guides and results are project documents, bound by role.
- [0144](../decisions/0144-tailoring-axes.md), [0147](../decisions/0147-tailoring-axes-details.md) (accepted): the `approach` axis and `confirm_lowest`.
- [0141](../decisions/0141-implementation-discovery-timing.md) (accepted): recipe builder's discovery, unchanged on the full path.

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
- **Criteria:** the `approach` rating always waits on the owner at `quick`; one owner question at `profile` at every rating; `quick` refused with `software: simple`; the full path unchanged from `@4` at `simple` and above (its scenario tests pass); a fitting shipped guide adopted; a new guide written; `@4` runs keep `@4`.
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

### Open questions deferred

- **Summary:** The owner deferred this change's open questions to discuss questions 1 (how recipe builder skips the full path) and 5 (starting a quick run from a catalog guide without recipe builder) first. All six remain open. No code changed.
- **Owner decision:** 2026-11-14, "Defer for E and F until later. I have to discuss E1 and E5 first."
- **Accepted:** No; proposal only.

### Open questions answered

- **Summary:** Put questions 1 and 5 to the owner first. Question 1 was mostly settled by Decision 0162 (item 3); the remaining point was that a simple build would ask two questions once `quick` is the lowest rating, so `profile` drops its own gate and the triage gate is its one question. Question 5 was put with three options (copy by attestation, a shipped guide's id taken directly, no path but recipe builder). The owner accepted the suggested answers to all six. Recorded as Decision 0163. Request and Design updated: `recipe-builder@5` (version 4 was taken by `2026-11-builder-step-design`), `guides copy`, the one question at `profile`. No code changed.
- **Owner decision:** 2026-11-17, "Agree to all." (0163).
- **Accepted:** No; the Request and Design await the owner's approval.

### Accepted

- **Summary:** The owner approved the Request and Design as updated with Decision 0163's answers. No code changed.
- **Owner decision:** 2026-11-17, "Approved. proceed"
- **Accepted:** Yes.

### Slice 1: guidance documents and the catalog

- **Summary:** A guide is Markdown with front matter (`format: baton-guide/1`, `id`, `version`, `title`, `description`, `produces`) and four sections (purpose, what to produce, what good looks like, what to ask the owner). `guides.py` checks it, refusing a missing or unknown field, a bad id or version, an empty section and any vendor string (an error: a guide is all instruction). Five starter guides ship in `examples/guides/`: `lean-business-plan`, `marketing-plan`, `standard-operating-procedure`, `project-charter`, `decision-record`. `guides()` (CLI `baton guides`, MCP, API) lists the project's `guides/` and the shipped guides, sorted by id with a project guide first, and names project files that are not valid guides (or whose name is not their id). `catalog.guides` gives a step the same listing, valid guides only. `guides copy <id> --note` copies a shipped guide to `guides/<id>.md`, attests it with the owner's words and commits it; it never overwrites (`guide.exists`) and refuses an unknown id (`guide.unknown`). `baton guides check <file>` is a CLI-only gate helper, for the builder's `guide` step in Slice 3.
- **Modules:** new `guides.py`; `refs.py` (`catalog.guides`), `packet.py` (resolves it), `engine.py` (`Api.guides`, `Api.guides_copy`), `mcp_server.py` (`guides`, `guides_copy`), `cli.py` (`guides`, `guides copy`, `guides check`).
- **Design docs:** §5.2 (`catalog.guides`), §5.3 (the guide check), §5.7 (guidance documents), §13.1 (`guides`, `guides_copy`), §13.2 (`guides check` is CLI-only), §4.1 and §4.3 (`examples/guides/`, the project's `guides/`), §2 in `principles.md` (quick runs add no concept; rule 8 asks for it for a new command).
- **Manual:** `admin/recipes-and-vendoring.md` (guidance documents, their format and where they live), `admin/director-commands.md` (`guides`, `guides copy`), `context.yaml` (`guides` maps to the commands topic), `reference/commands.md` regenerated, `anchors.yaml`. `recipes/quick-run.md` leaves the change's `manual:` list until Slice 2 writes it (the list may name only files that exist).
- **Tests:** `tests/test_guides.py`: a good guide and its summary; CRLF read the same; each missing field, bad front matter (format, id, version, empty text, unknown key), no front matter, each missing or empty section, and a vendor name in front matter or body refused; the five starters ship and pass; the listing orders project and shipped guides and names invalid or misnamed files; `catalog.guides` in a packet equals the listing; a misspelt source is `ref.invalid`; `guides copy` copies, attests, commits, lists the copy, and refuses again, an unknown id and an empty note; `guides check` passes and fails; MCP, API and CLI list the same guides. `tests/test_director_surface.py`: the MCP tools include `guides` and `guides_copy`. `tests/test_refs_and_vocab.py`: `catalog.summaries` and `catalog.guides` parse with their name; another `catalog.*` does not.

### Slice 2: the `quick-run` recipe

- **Summary:** `quick-run@1` ships in the catalog: run inputs `title` and `request`, roles `guide` (required, Markdown) and `context` (optional, `many`), and one step, `produce` (`workspace: none`), returning a `summary`, a `checklist` of the guide's "What good looks like" and `assumptions`, with the artifact `deliverable` published to `{{ paths.documents }}/{{ run.slug }}.md` behind a schema gate and one human gate ("Is this good enough to use?"). No triage, research or review; `max_attempts: 3`. `paths.documents` defaults to `docs` when `project.yaml` does not map it (`publish.DEFAULT_PATHS`, `with_defaults`), so the first quick run needs no setup.
- **Modules:** `publish.py` (the `paths.documents` default in `missing_path_keys` and `render_target`). Recipe package: `examples/recipes/quick-run/` (`recipe.yaml`, `prompts/produce.md`, `schemas/run_inputs.json`, `schemas/produce_out.json`).
- **Design docs:** §5.7 (the catalog row and `quick-run@1`), §10.4 (the `paths.documents` default).
- **Manual:** `recipe-sources/quick-run.md` (new) and the generated `recipes/quick-run.md`; `reference-notes.yaml` (`paths`: the `documents` default) and the regenerated `reference/project-settings.md`; `anchors.yaml`. `recipes/quick-run.md` is back in the change's `manual:` list.
- **Tests:** `tests/test_quick_run.py`: the shipped recipe's one step, gates, roles, inputs, artifact and attempt bound; the `paths.documents` default and a mapping winning; end to end with the guide copied by `guides copy`: the packet holds the guide and no unbound context, a rejection retries with the owner's note as feedback, the approval publishes to `docs/<slug>.md`, `documents()` lists it as a deliverable of the run, and a later quick run binds it as `context` with its source; a run with no guide refuses the dispatch until one is bound, and a mapped `paths.documents` is used. The shipped-recipe lists in `test_conversation.py`, `test_real_use.py`, `test_manual_gen.py` and `test_project_documents.py` include `quick-run`.
