# Project-level process linkage

Date: 2026-11-13

Status: exploration note for owner review. It records the direction the owner agreed in conversation on 2026-11-13 and breaks it into proposed changes, each with its open decisions and a suggested answer. No change doc, decision record or design doc is amended by this note. It supersedes `eng-process-full-range-exploration.md`, whose tailoring dimensions and examples are carried into §4 below.

## 1. The problem

A real project is made of many processes of different kinds. Setting up a water-vending business involves business setup, sites and equipment, marketing, and, later, developing the processes that will run the business. The later processes need what the earlier ones settled: marketing needs the business's constraints and target customers; developing operations processes needs the project's decisions and policies.

Baton today guarantees reliable handoff only **inside** a run. A step's declared inputs come from its own run, recorded human decisions, platform facts or the recipe catalog (design §5.2). Earlier runs' deliverables are published into the repo, so a worker with workspace read access *may* find them, but nothing declares the need, supplies the accepted version, stops the step when it is missing, or records which version was used. At project scale, the main guarantee stops exactly where it is most needed. That is too brittle.

Separately, eng-process is to be Baton's single software recipe, tailored deeply enough to serve everything from a personal utility to a consequential production system, while staying familiar at every scale.

## 2. Agreed direction (owner, 2026-11-13)

- **One software recipe.** eng-process, deeply tailored. A second software recipe needs a very strong reason; `software-feature` is retired once eng-process covers its ground.
- **A project holds any number of recipes, of any kind.** Some know nothing about the project; most have intentional links to it. Links are possible, never mandatory, never prohibited. "Arbitrarily complex interdependence" means any process may use any project document, not complex data structures.
- **Runs stay work items.** A project's life is many short runs, not one run that lasts forever. Modular and loosely coupled.
- **Project documents are visible inputs; a few policies control.** Upstream changes are reported, not propagated.
- **Tailoring has a few axes**, onto which the many concerns project. An axis rated low changes nothing.
- **Project guidance is an opt-in process**: short, repeatable project reviews that recommend which processes to run next. The owner chooses. Not built in by default; framing offers it when it finds several parts.
- **A choice of rigor per component.** Through recipe builder, the owner may choose a full Baton recipe or a quick, inference-driven run guided by a shared guidance document. The quick run's output becomes a project document like any other. As discussed, the owner attests it; E4 suggests an alternative that makes attestation unnecessary.

## 3. The model

```
framing ──lists parts──▶ runs of any recipes ──publish──▶ project documents
   │                          ▲    ▲                         │      │
   │                          │    └──── bound by role ──────┘      │
   └─offers─▶ project review ─┘ (recommends; owner chooses)         │
                     ▲                                              │
                     └──────────── reads project state ─────────────┘
              project policy (project.yaml) constrains every run
```

- A **project document** is an accepted deliverable of a run, or a file the owner has attested. Either way the record holds its path, content hash and where it came from.
- A recipe declares the project documents it would like **by role** ("business constraints: the decisions the business has settled"), never by another recipe's id or step. Shareability depends on this: a recipe that names another recipe's steps can only run beside that recipe.
- At run start (or later, before the step that needs it), each role is **bound** to a specific project document. The binding is recorded; the runtime supplies that version as an ordinary input.
- **Project policy** is a small set of rules in `project.yaml`, enforced in code.
- **Tailoring** is rated per run on the recipe's own axes; policy can set floors.
- The **project review** is a recipe like any other.

## 4. Tailoring: concerns project onto axes

The eng-process exploration listed nine concerns. Each feeds one axis; triage rates each axis with a reason, and only the axes rated above low change the process. The same steps run in the same order at every scale; only their depth and the safeguards change.

| Axis | Concerns that feed it | What it changes |
|---|---|---|
| Discovery | Uncertainty; existing evidence and readiness | Research, experiments, discovery depth |
| Coordination | Technical scope and coupling; longevity and maintenance | Architecture, a reviewed slice plan, documentation durability |
| Assurance | Consequence of failure; data and security; reversibility; reach and dependence | Verifier independence, security and negative tests, recovery evidence |
| Release | Delivery and obligations (and reach) | Owner release decision, push/deploy authorization, staged rollout |

Examples carried from the earlier note:

| Work | Discovery | Coordination | Assurance | Release |
|---|---|---|---|---|
| Personal inventory app from scratch | low | low (a few slices) | low | low |
| Disposable prototype on an unfamiliar API | high | low | low | low |
| Internal scheduling tool for a small team | medium | medium | medium (team depends on it) | medium |
| Utility that deletes duplicate files | low | low | high (irreversible data) | low |
| Minor change to tenant authorization | low | low | high (security boundary) | medium |
| Production storage migration | medium | high | high | high |

## 5. Proposed changes

Dependency order: A and C are independent of each other; B needs A and C; D and E need A; F needs A, B and C. A gives the most value.

| # | Proposed change id | One line |
|---|---|---|
| A | `2026-11-project-documents` | Runs bind accepted or attested project documents as inputs, by role |
| B | `2026-11-project-policy` | A few project rules, enforced on every run |
| C | `2026-11-tailoring-axes` | Complexity becomes a few rated axes instead of one scale |
| D | `2026-11-project-review` | An opt-in recipe recommends which processes to run next |
| E | `2026-11-quick-runs` | Recipe builder offers a quick, guided run as an alternative to a full recipe |
| F | `2026-11-eng-process-recipe` (exists) | Amended to be the single software recipe, built on A, B and C |

Each section lists the open decisions with a suggested answer.

**Decided (owner, 2026-11-13):** A, B, C and E1–E4 as suggested; E5, no new concept (a guidance document is a recipe input). Recorded as decisions [0142](../decisions/0142-project-documents-bound-by-role.md) (A), [0143](../decisions/0143-project-policy.md) (B), [0144](../decisions/0144-tailoring-axes.md) (C) and [0145](../decisions/0145-quick-runs-through-recipe-builder.md) (E). A and C are change docs: `2026-11-project-documents` and `2026-11-tailoring-axes`. D is still open.

### A. Project documents and role binding

What it adds: a recipe section declaring roles; a step-input reference to a role; binding at run start or later; attestation of outside files; a runtime-derived list of the project's documents; reporting when a newer version of a bound document exists.

**A1. What can become a project document?** Suggested: an accepted, published deliverable of any run (automatically), or any file in the repo the owner attests (an owner decision recording their words and the file's hash). Rationale: attestation already exists for adoption (§11.4); it lets quick runs, hand-written documents and work done outside Baton take part on equal terms, and the record shows which kind each is.

**A2. How does a recipe declare and use a role?** Suggested: a recipe-level `project_inputs` list (`role`, `description`, `media_type`, `required`), referenced in step inputs as `project.<role>`. A recipe with no `project_inputs` behaves exactly as today. Alternative: a run input whose value is a document reference; smaller, but it hides the role from step-level declarations and the recipe lint. Rationale for the suggestion: inputs stay declared where they are used, and the loader can check every reference.

**A3. Who binds, and when?** Suggested: the Director proposes bindings at run start from the project's document list and the role descriptions, and confirms them back with the owner (§13.8); framing's selection and a project review may propose them too. A role may stay unbound until the first step that needs it is ready; a required unbound role then blocks that step the way a missing required input does, and the Director asks. Rationale: documents a run needs may not exist yet when it starts (marketing may start before site decisions are final).

**A4. What happens when a bound document changes upstream?** Suggested: nothing automatic. Status and the board show "this run used <document> v3; v4 exists". The owner may **rebind**, which within that run makes the consuming steps stale exactly like `revise`; other runs are never touched. Rationale: keeps "work items move; projects don't" and loose coupling; owner attention is spent only when it matters.

**A5. How does anyone find the project's documents?** Suggested: a runtime-derived listing (CLI, API and MCP, and a page in the process plan's style), built from run records and attestations, never a hand-kept index. Rationale: §1.4 #7, the repo is the system of record; a hand-kept index would drift.

**A6. Concept budget.** Suggested: one new concept, *project document*, in §2. Binding and roles are its mechanics, not separate concepts.

### B. Project policy

**B1. Which policies?** Suggested: start with three: floors on tailoring axes (per recipe, or for all recipes), release authority (who may push, merge or deploy, default ask), and the governing recipe for a kind of work (for example, software work uses eng-process). Add more only from real need.

**B2. Where does policy live, and how does it change?** Suggested: a `policy:` block in `project.yaml`, changed only through an owner decision that is recorded. Rationale: what controls must be deterministic configuration (§1.1 #5); the recorded decision gives it provenance.

**B3. Does a policy change affect runs already started?** Suggested: no. Policy is pinned at run start like the recipe version; a run started under older policy is reported, and the owner may re-triage it. Rationale: evolve by trial (§1.1 #4); no surprise mid-run.

**B4. Is "governing recipe" enforced?** Suggested: advisory. The Director proposes the governing recipe for that kind of work and says so when the owner picks another; the runtime does not refuse. Rationale: what "kind of work" an idea is is a judgment, not a deterministic fact; axis floors and release authority are enforceable, this is not.

**B5. Concept budget.** Suggested: *project policy* as one new concept in §2.

### C. Tailoring axes

**C1. Who defines the axes?** Suggested: the recipe, as it defines its levels today. eng-process declares the four axes above; `backyard-project` may declare others or keep one scale. A recipe with today's `levels` is a one-axis recipe and is unchanged. Rationale: vendor and domain neutrality; axes for software are not axes for a garden.

**C2. The scale on each axis?** Suggested: recipe-owned, like levels; eng-process uses low / medium / high.

**C3. How do `applies_to` conditions combine?** Suggested: a step or gate lists conditions per axis (`applies_to: { assurance: [high] }`); it applies when any listed axis matches (OR), and a step with no `applies_to` always runs. Rationale: safeguards add steps when any concern demands them; AND would let one low rating hide a serious risk ("don't average away a serious risk"). Gates that differ by axis (for example verifier independence) are separate gate entries with their own conditions, as today.

**C4. Who approves the ratings?** Suggested: triage gives a reason for every axis (schema-checked). All axes at their lowest is applied at once, as today; anything else waits on the owner. A policy floor raises a rating automatically and says why. Rationale: under-rating is the main way tailoring fails; requiring a reason per axis turns every "low" into a recorded claim.

**C5. Re-triage.** Suggested: per axis, with today's rules otherwise (Decision 0028): steps not yet started are skipped or unskipped; started and passed steps never change and are flagged. A worker's result may carry a structured "this changes the rating" signal, which the Director turns into a re-triage request. Rationale: today nothing detects a mid-run discovery.

**C6. Compatibility.** Suggested: additive within `baton-recipe/1` if the loader can tell the forms apart; otherwise a format version bump with both forms loading. Decide in Design.

### D. Project review

**D1. Opt-in, and who offers it?** Suggested: a catalog recipe, not built in. Framing offers it when it finds two or more parts; the owner may also start one at any time. Each review is a short run.

**D2. Decision 0069.** Suggested amendment: the process plan still lists and never orders. Inside a project review run, which the owner chose, recommendations may suggest an order with reasons ("marketing waits on site decisions"). Nothing ever starts automatically. Rationale: advice the owner asked for is not scheduling (§1.3); the default stays as 0069 says.

**D3. What does it read?** Suggested: a new runtime-built input, `project.summary`: the project's runs and their status, its project documents and bindings (including stale ones), its policy, and its process plans. Rationale: the review must see the project's state, and nothing supplies that today.

**D4. What does it produce?** Suggested: recommendations, plus optionally new parts, rendered into a process plan exactly as framing does and selected with the same gate. Rationale: one mechanism for "which processes now", whether from framing or a review.

**D5. Relationship to framing for mature projects (Decision 0044).** Suggested: the review is where proposing to bring existing work under a recipe belongs; 0044's deferred work is folded into D or follows it.

### E. Quick runs

The owner placed this choice in recipe builder (not fit-check or framing): framing lists the components; when the owner sets out to build the process for one, recipe builder lets them decide early whether a full recipe is worth it or whether a quick, inference-driven run that produces what is needed for attestation is enough.

**E1. Where in recipe builder?** Suggested: in `profile`, after it checks existing recipes: the builder offers "a full process" or "a quick guided run", with what each costs and gives. Choosing quick ends the builder with a guidance document instead of a recipe.

**E2. What is a guidance document?** Suggested: a harness-neutral Markdown document (purpose, what to produce, a checklist of what good looks like, what to ask the owner), usable by any Director or worker. Not a harness-specific skill. Rationale: vendor neutrality (§0 rule 4).

**E3. A catalog of guidance documents.** Recipe builder today searches the recipe catalog (`catalog.summaries`, Decision 0106), not guidance; none exists yet. Suggested: ship a guidance catalog beside the recipe catalog, listed to recipe builder in the same way; the builder uses one that fits or writes one, as it does for recipes.

**E4. Who runs the quick run?** As discussed: the Director's harness runs it outside Baton, and the owner attests the output (A1). Suggested instead: a shipped one-step recipe that dispatches the guidance document to a worker, so the output is an accepted deliverable with provenance and needs no attestation. Work done entirely outside Baton still enters through attestation (A1). Rationale: provenance at almost no cost in speed; attestation remains the path for everything else.

**E5. Concept budget.** Decided: no new concept; a guidance document is a recipe input.

### F. eng-process (amendments to the existing change)

- It is the single software recipe; its manual and §5.7 say when `software-feature` is retired (once eng-process's lowest ratings match `software-feature minor`: triage, then per slice implement, code review, accept).
- Its tailoring uses the four axes (C), not small/medium/large.
- It declares project roles (A) for settled architecture, conventions and project decisions, so later increments build on the inception run's accepted work instead of rediscovering it.
- Release authority comes from project policy (B), which answers part of its open question 3.
- Its existing open questions 1–4 remain open.
- Status until A, B and C are done: on hold.

## 6. Concept budget, in total

Two new concepts in §2: project document and project policy. Complexity level is generalized to axes, not replaced. The project review and quick runs are recipes.

## 7. Next steps

1. Owner reviews this note.
2. A and C become change docs (`proposed`, with register rows); their open decisions go to the owner in one batch, each with its suggested answer.
3. B, D and E follow as change docs once A's design is settled; F is amended then.
4. `eng-process-full-range-exploration.md` is deleted once the owner agrees this note supersedes it.
