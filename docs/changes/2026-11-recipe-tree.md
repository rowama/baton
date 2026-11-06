---
id: 2026-11-recipe-tree
title: "Recipes form a tree: broad recipes that specialized ones are derived from by copy"
status: proposed            # ON HOLD: intertwined with the recipe development recipe
level: major
decisions: []               # none yet; see Design > Decisions for the records this would need
touches: [design/recipes.md, design/adoption-and-framing.md, design/versioning.md, design/platform-and-security.md]
---

# Recipes form a tree: broad recipes that specialized ones are derived from by copy

> **On hold.** Intertwined with the **recipe development recipe** (the "recipe for authoring recipes" of §11.6 and §15.3), which Rob plans to add soon. That recipe would be the producer of derived recipes, so the tree's mechanics largely belong to it: this change may shrink to a `parent:` field plus a rebase step once that recipe exists. Related: [2026-11-self-improvement](2026-11-self-improvement.md) (also on hold), whose local lines are the bottom level of the same tree and whose cases route up it.

## Request

### Problem

Today a goal or idea either matches a vendored or catalog recipe, or it doesn't. Framing proposes a fitting recipe or a `fit-check` run (§11.6), and `fit-check`'s `fits` verdict leads to "an existing recipe, or recipe authoring" (§5.7). Authoring from nothing is the expensive path, and it's where a non-expert owner most needs help.

Much of a recipe is process structure, not domain knowledge: steps, gates and handoffs like research → options → decide → plan → execute → review. Rob can write that structure without being a subject-matter expert. Broad recipes holding it would give specialized recipes a starting point, and give fit-check and framing an outcome between "a recipe fits" and "write one from scratch".

### Acceptance criteria

- Fit-check and framing can return one of four outcomes for the owner: Baton isn't a fit; Baton has a recipe you can use; Baton has a broad recipe to build on; Baton fits but needs a new recipe from scratch.
- A derived recipe is an ordinary, complete recipe with a recorded parent and parent version; it runs with no knowledge of its parent.
- Changing a parent never changes a derived recipe until an explicit rebase.
- A rebase replays the child's changes onto the new parent version and reports conflicts for a person to resolve.

### Open questions

- **Is the tree worth it?** Broad recipes risk being too generic to help: the value is in the specialization, and authoring it is the hard part. The reasons to keep the idea alive: authoring gets a starting point, and cases (see self-improvement) route to the level that owns the wording.
- What are the first broad recipes? A generic root (any project), plus a few by kind of work?
- Who resolves rebase conflicts: the recipe's maintainer, or the recipe development recipe run again?

## Design

### Positions so far (discussed 2026-11-05; not yet decisions)

**Broad recipes need no SME.** They hold structure, which is process knowledge. Domain knowledge goes into the specializations, authored through the recipe development recipe.

**Four owner-facing outcomes, three mechanisms.** With a generic root recipe, "a new recipe from scratch" is just "derive from the root". The owner still sees four options because they read clearly; the runtime has one derive mechanism. The mapping onto today's flow (framing proposes `recipe` or `fit_check`; fit-check's verdicts `fits`, `fits_per_occurrence`, `operations_engine`) is to be worked out with the recipe development recipe: likely framing and fit-check gain a "derive from `<broad recipe>`" proposal, and `fits` without a fitting recipe proposes a recipe development run seeded with the chosen parent.

**Derive by copy, not live inheritance.** A derived recipe is a fork with a recorded parent version, like a git fork with an `upstream` remote. It is not like JS prototypes or class inheritance, where a lookup that misses on the child falls through to the parent at runtime, so editing the parent changes every child at once. Live inheritance is where brittleness comes from. With a copy, parent changes reach the child only through an explicit rebase.

Sketch (illustrative, field names not decided):

```yaml
id: water-vending-site-setup
version: 1
parent: { id: project-setup, version: 2 }   # recorded when derived; changes only on rebase
```

**One tree, one rebase.** Upstream → derived → local line ([2026-11-self-improvement](2026-11-self-improvement.md)) is one tree, with one rebase-on-upgrade mechanism at every level: replay the child's changes onto the new parent version, run the child's cases, drop what the parent made redundant, surface conflicts.

**Cases route up the tree.** If confusing wording was inherited from a parent, the case belongs to the parent's maintainer. The analyst then works at the right level automatically.

**Boundary.** Deriving a recipe adds or changes steps and gates. That is deliberate authoring with the owner's confirmation (Principle 5 confirm-back, §13.8), never automatic self-improvement, which stays wording-only (§1.4 #10).

**Versioning interplay.** A derived recipe has its own id, so vendoring's step-id signature checks (§14.2) apply within its own versions, not against its parent. A rebase produces a new version of the child, subject to those checks as usual.

**Concepts (§2).** No new concept if "derived recipe" is just a recipe with a `parent:` field and the root is just a catalog recipe. A rebase is a recipe upgrade, which the budget already covers implicitly.

### Doc edits (anticipated)

- `design/recipes.md` §5.1: optional `parent:` entry; §5.7: broad recipes in the catalog.
- `design/adoption-and-framing.md` §11.6: framing proposes "derive from a broad recipe".
- `design/recipes.md` §5.7 (`fit-check`): the four owner-facing outcomes.
- `design/versioning.md` §14: rebase of a derived recipe onto a new parent version.
- `design/platform-and-security.md` §15.3: the recipe development recipe as the producer of derived recipes.

### Decisions (to write once Rob decides; none exist yet)

- Derive by copy with a recorded parent version; no live inheritance.
- A generic root recipe exists, making "from scratch" a derivation from it.
- Fit-check and framing present four outcomes to the owner.

## Plan

Sketch only; depends on the recipe development recipe and gets criteria after Request and Design are approved (major).

### Parent field

- **Outcome:** a recipe may record `parent: {id, version}`; load, lint and vendoring accept it; it has no runtime effect.
- **Effort:** S

### Root and broad recipes

- **Outcome:** a generic root and one or two broad recipes ship in the catalog.
- **Effort:** M

### Derive in fit-check and framing

- **Outcome:** the four owner-facing outcomes; "build on a broad recipe" starts the recipe development recipe seeded with the parent.
- **Effort:** M

### Rebase

- **Outcome:** a derived recipe rebases onto a new parent version, with conflicts reported; shared with self-improvement's local lines.
- **Effort:** L

## Log
