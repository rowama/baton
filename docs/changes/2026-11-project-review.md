---
id: 2026-11-project-review
title: "An owner who wants guidance can run a project review that recommends which processes to start next, with the documents they would build on"
status: proposed
level: major
decisions: ["0150", "0069", "0044", "0062", "0066", "0068", "0142", "0148"]
touches: [principles.md, design/recipes.md, design/adoption-and-framing.md, design/runtime.md, design/director-interface.md]
manual: [recipes/project-review.md, recipes/baton-frame.md, user/start-with-a-goal.md, user/check-on-your-work.md, admin/director-commands.md, reference/commands.md]
---

# An owner who wants guidance can run a project review that recommends which processes to start next, with the documents they would build on

## Request

### Problem

Framing (§11.6) turns a goal into parts and starts the ones the owner picks. After that, the owner is on their own. In the water-vending example, they have to work out for themselves that marketing waits on site decisions, that the operations-process work needs the project's policies, and which documents each new process should build on. Each new process starts without that context unless the owner remembers to supply it.

An owner who thinks in project-management terms wants a recurring "where are we, and what's next?" step. Decision [0150](../decisions/0150-project-review-opt-in.md) settles the shape. It is opt-in, never built in by default. Each review is a short, repeatable run, not a process lasting the life of the project. The Director offers it when framing finds several parts. Recommendations may suggest an order only inside a review the owner chose (0069 stands otherwise). Decision 0148 deferred *proposals that carry document bindings* to this change.

Project documents (`2026-11-project-documents`) and tailoring axes (`2026-11-tailoring-axes`) are done. Project policy (`2026-11-project-policy`) is proposed. A review reports its governing recipes when that change exists, and works without it.

### Acceptance criteria

- **A review reads the project's state.** A new input, `project.summary`, gives a step the project's runs (recipe, title, status, where each is waiting, ratings), its project documents (path, kind, source, state), active runs' bindings and upstream changes, its process plans and their parts not yet started, and the policy once it exists. It is built by the runtime from the records, deterministically: the same records give the same blob.
- **A review recommends; the owner chooses.** A shipped catalog recipe, `project-review`, has one recommending step. Its output proposes runs, each with a label and description in the owner's terms, a recipe (or a fit check, or a quick run once `2026-11-quick-runs` exists), run inputs, proposed document bindings, reasons, and an optional order with what it waits on. An implicit selection gate lets the owner choose any or none, in conversation and confirmed back. The selected runs start exactly as recorded, with their bindings and the owner's words. Nothing starts without the owner's selection.
- **Selection is one mechanism.** Framing's selection (the `select` gate, starting runs, gaps, vendoring on selection, the runtime-rendered process plan, `start --from-plan`) becomes available to any recipe step that declares it proposes runs. `baton-frame@1` behaves, records and renders exactly as before (its tests and goldens unchanged).
- **Proposals may carry bindings.** A proposal's `bind {role: [paths]}` is checked at selection like `start --bind` (role declared, paths are project documents, media types fit, one or many). A binding that fails makes that part a gap with the reason, never a silent start without it. Framing gains bindings in a new version, `baton-frame@2`. Open `@1` runs keep `@1`.
- **The plan shows order only where chosen.** A review's process plan lists each recommended part with its reasons and, when the review suggests one, its position and what it waits on. A framing run's plan never shows an order (0069).
- **The Director offers it and never runs it unasked.** After a framing selection with two or more parts, and when the owner asks what to do next, the Director skill offers a project review in the owner's terms. It never starts one on its own judgment.
- **A review can take content, not only metadata.** `project-review` declares optional roles (for example the project's charter or plan, and its decisions as a `many` role), so an owner who has them gets a review grounded in their content.
- **Manual and design are current.** §11.6 is generalized, §1.3 and 0069's rule are stated with the review's exception, and the manual has a recipe topic for `project-review` plus an owner's guide to using it.

### Open questions

New questions this change raises, each with a suggested answer, to be put to the owner in one batch before Design.

1. **Where does the selection mechanism live?** *Suggested:* generalize framing's: a step may declare `proposes_runs: true`. Its output then follows the proposal schema, and the runtime supplies the selection gate, starts, gaps and plan rendering for it. Framing becomes its first user, unchanged. *Rationale:* principle 2 prefers generalizing to a parallel mechanism, and a deterministic start "exactly as recorded" (0066) is what makes recommendations safe to act on. The alternative, a recipe whose Director starts the chosen runs by hand, would lose that.
2. **Is the review a catalog recipe or built in?** *Suggested:* a catalog recipe (`project-review@1`), vendored on first use like any catalog recipe, so a project can specialize it with recipe builder. *Rationale:* project-management practice varies by organization and owner. A built-in recipe changes only with the runtime and can't be tailored. "Not built in by default" (0150) is met either way, since it runs only when chosen.
3. **What does `project.summary` include, and what not?** *Suggested:* metadata only, as listed above, never document contents. Contents reach the review only through its declared roles. *Rationale:* a bounded, deterministic input. Contents the owner has chosen to bind are what the review should reason from, not whatever happens to be in the repo.
4. **Does framing gain bindings now, as `baton-frame@2`?** *Suggested:* yes, in this change, since 0148 deferred it here. Framing's proposals may then carry bindings for parts that build on documents the project already has. *Rationale:* one proposal schema for both users of the mechanism. A new version keeps open `@1` runs intact (§5.8).
5. **Can a review recommend adopting existing work** (0044, framing for mature projects)? *Suggested:* not as a startable proposal in this change. The review may say in its reasons that existing work could be brought under a recipe, and the Director then follows the existing `adopt` flow (§11.1). *Rationale:* adoption is its own flow with a baseline decision. Making it a proposal kind is worth doing only once reviews are in use.
6. **How is the suggested order expressed?** *Suggested:* each proposal may carry `position` (1, 2, …) and `waits_on` (other proposals or existing runs, each with a reason). These are shown, never enforced. *Rationale:* advice in a form the plan can render and the owner can read, with no scheduling semantics (§1.3).

## Design

Provisional, for review with the Request; settled once the open questions are answered.

### Shape

- **The proposal schema** (`baton-proposals/1`) is framing's `parts[]`, generalized: `{id, label, description, kind, proposal {recipe?, inputs?, fit_check?, bind?}, reasons, position?, waits_on?}`. `baton-frame/1` output is its subset with no `bind`, `position` or `waits_on`.
- **The mechanism.** `frame.py`'s selection, planning, gaps, rendering and `start --from-plan` are re-keyed from "the run is `baton-frame@1`" to "the step declares `proposes_runs`". Events keep their names (`framing_selected`, `framing_started_later`, `run_started.framing`) so existing records read unchanged. Their meaning becomes "a proposing step's selection".
- **`project.summary`** is computed at packet build from the run logs, the project log and `documents()`, then stored in the run's CAS like any input. Its hash makes two reviews of the same state comparable.
- **Rendering.** The process plan renderer gains `position` and `waits_on` lines. It prints them only when present, which never happens for framing.
- **Director skill.** It offers a review after a multi-part framing selection and on "what next?", and relays recommendations with their reasons, never adding its own.

### Doc edits

- `principles.md` §1.3: recommendations inside an owner-chosen review are not scheduling; §2: no new concept (a review is a recipe, its selection is framing's, generalized).
- `design/recipes.md` §5.1 (`proposes_runs`), §5.2 (`project.summary`), §5.7 (`project-review`).
- `design/adoption-and-framing.md` §11.6: the selection mechanism generalized; `baton-frame@2` with bindings; order only in reviews.
- `design/runtime.md` §8.2: the generalized meaning of the framing events.
- `design/director-interface.md` §13.3: offering and relaying a review.
- `docs/README.md`: new records.

### Manual edits

- `manual/recipes/project-review.md` (new, from `manual/recipe-sources/`): what a review does, what it reads, what you are asked.
- `manual/recipes/baton-frame.md`: proposals that build on existing documents (`@2`).
- `manual/user/start-with-a-goal.md`: asking for a review after framing; reading a review's plan.
- `manual/user/check-on-your-work.md`: "what's next?" through a review.
- `manual/admin/director-commands.md` and the generated `manual/reference/commands.md`, if commands change.

### Decisions

- [0150](../decisions/0150-project-review-opt-in.md) (accepted): opt-in, short runs, offered after framing, order only inside a review.
- [0069](../decisions/0069-process-plan-lists-not-schedules.md), [0062](../decisions/0062-framing-mechanism-kept-presentation-fixed.md), [0066](../decisions/0066-start-from-plan.md), [0068](../decisions/0068-breakdown-rendered-by-runtime.md) (accepted): framing's rules, kept and generalized.
- [0044](../decisions/0044-framing-mature-projects-deferred.md) (accepted): mature-project framing, still deferred (open question 5).
- [0142](../decisions/0142-project-documents-bound-by-role.md), [0148](../decisions/0148-project-documents-framing-deferred.md) (accepted): bindings, and their deferral to this change.
- The open questions above become records when decided.

## Plan

Provisional slices, refined once the Request and Design are approved. Each slice carries its tests, design and manual edits and Log entry, and follows the quick, background and full gates in AGENTS.md.

### Slice 1: framing's selection, generalized

- **Outcome:** any step that declares `proposes_runs` gets selection, starts, gaps, plan rendering and `start --from-plan`.
- **Criteria:** a test recipe with a proposing step runs end to end; `baton-frame@1` records, renders and starts exactly as before (goldens); the loader checks `proposes_runs` steps.
- **Effort:** L

### Slice 2: proposals carry bindings; `baton-frame@2`

- **Outcome:** a selected part starts with its bindings, or is a gap with the reason.
- **Criteria:** each binding check at selection; a failing binding is a gap; `start --from-plan` binds as recorded; `baton-frame@2` proposes bindings; open `@1` runs unaffected.
- **Effort:** M

### Slice 3: `project.summary`

- **Outcome:** a step can read the project's state.
- **Criteria:** contents as listed; deterministic for the same records; no document contents; works before and after project policy exists.
- **Effort:** M

### Slice 4: the `project-review` recipe, the Director and the manual

- **Outcome:** an owner can run a review, choose from its recommendations, and see order and reasons in its plan.
- **Criteria:** the recipe loads, vendors and runs; positions and waits shown in a review's plan, never in framing's; optional roles; the skill offers it after a multi-part selection and never starts it unasked; manual topics; an end-to-end scenario: framing with three parts, one run done, a review recommends the next two with bindings and an order, the owner selects one.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Change doc written from Decision 0150 (recorded from the owner's statements of 2026-11-13) and `docs/catchall/project-process-linkage.md` (§5 D), against what `2026-11-project-documents` built and 0148 deferred. No code changed.
- **Owner decision:** 2026-11-14, "Write the B, D, E and F change proposals". The Request is not yet accepted; the open questions above are unanswered.
- **Accepted:** No; proposal only.
