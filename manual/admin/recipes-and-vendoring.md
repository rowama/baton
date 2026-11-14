---
id: admin.recipes-and-vendoring
title: Recipes, vendoring and trust
audience: admin
order: 90
summary: How a process is added to a project, pinned and verified, and what to review first.
related: [admin.network-and-security, recipes.software-feature]
---

## Here, now {#here-now}

A **recipe** is a shareable process: a folder with `recipe.yaml`, schemas, prompts and static files. A project uses a recipe by **vendoring** it: copying it to `.baton/recipes/<id>@<version>/` and pinning its hash in `baton.lock`. Runs keep the recipe version they started with.

```baton
baton vendor path/to/recipe
baton recipes
baton plan path/to/recipe
```

`vendor` copies and pins; `recipes` lists what the project has; `plan` validates a recipe and prints each level's parts and checks (for a recipe that rates work on several axes, see [below](#axes)). `baton init` vendors the starter process (`fit-check`); framing vendors a shipped recipe when the owner chooses a piece of work that uses it. The shipped ones are described in [Recipes](recipes.fit-check#here-now).

## Review before you vendor {#review}

> **Warning:** Recipes are trusted code. A recipe's script checks run commands on the machine. Read them first. `baton check` and `baton doctor` verify the vendored hashes afterwards, so a later edit is reported.

Things to read: every `script` check's command, any `command` adapter a profile would run for it, the files it publishes and where (`publish: to:`), and the capabilities each part requires. Recipes declare the capabilities they need, never a model or vendor, and Baton's loader rejects a recipe that names one.

## New versions and retired ids {#versions}

A published version is never edited in place; a change is a new version. When a new version changes a kept part's signature, or reuses an id an earlier version retired, vendoring needs the owner's decision: `vendor` exits 4 and lists the flags, then:

```baton
baton vendor path/to/recipe --approved --note "the owner's words"
```

## Helpers for recipe authors {#authors}

`baton recipe check <package> --ledger <file>` is a helper that a recipe's own checks run: it verifies that no requirement is open and that every confirmed one carries the owner's words. The recipe format is published as JSON Schema in the runtime's `formats/` data, so an assistant can pre-check what it writes. Writing recipes is covered by the design documents; a guided path is the [recipe builder](recipes.recipe-builder#here-now).

## Documents a recipe builds on {#project-inputs}

A recipe can ask for documents the project already settled, such as a business plan another process wrote or a policy the owner vouched for. It declares each one by role at the top level of `recipe.yaml`, and its steps use it as `project.<role>`:

```yaml
project_inputs:
  - role: business_plan
    description: "The business's settled plan: its constraints and target customers"
    media_type: text/markdown
    required: true      # the default; false makes it optional
    many: false         # true takes one or more documents
```

When a run starts, or when a part first needs a document, the assistant proposes one from the project's documents (`baton documents`) and the owner confirms it. Each step receives the version the owner confirmed. A role describes the document it needs, never the recipe or step that made it: `baton vendor` refuses a role that names another recipe (`software_feature_design`, `fit-check@4`) or a step (`steps.setup`), so the recipe stays shareable. A recipe without `project_inputs` works as before.

## Rating work on several axes {#axes}

A recipe usually sizes work on one scale (`levels`, such as minor, standard and major). When concerns vary independently, for example how much is unknown and how much verification a change needs, a recipe can rate the work on a few **axes** instead, and each part or check applies by the axis it serves:

```yaml
complexity:
  axes:
    discovery: [low, medium, high]
    assurance: { scale: [low, medium, high], confirm_lowest: true }
  triage_step: triage
steps:
  - id: explore
    applies_to: { discovery: [medium, high] }
```

A part applies when any axis it lists is rated at one of its values; a part with no `applies_to` always runs. A recipe declares `levels` or `axes`, never both. Its first part rates every axis with a reason, and the owner approves the ratings unless every axis is at its lowest; `confirm_lowest: true` makes the owner approve that axis's lowest rating too. `baton plan` shows what always runs and what each rating adds; to see one combination, give a rating for every axis:

```baton
baton plan path/to/recipe --rating discovery=low --rating assurance=high
```
