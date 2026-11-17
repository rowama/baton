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

Things to read: every `script` check's command, any [tool](#tools) it ships, any `command` adapter a profile would run for it, the files it publishes and where (`publish: to:`), and the capabilities each part requires. Recipes declare the capabilities they need, never a model or vendor, and Baton's loader rejects a recipe that names one.

## New versions and retired ids {#versions}

A published version is never edited in place; a change is a new version. When a new version changes a kept part's signature, or reuses an id an earlier version retired, vendoring needs the owner's decision: `vendor` exits 4 and lists the flags, then:

```baton
baton vendor path/to/recipe --approved --note "the owner's words"
```

## Tools a recipe ships {#tools}

Some work is better done by plain code than by an AI worker: a calculation, a file conversion, a comparison. A recipe can ship a **tool** for such a part: a Python script in `tools/<id>/` with a `tool.yaml` and a lock file of exact dependency versions with their hashes. The part names it with `tool: <id>`, and no worker can do that part instead.

Vendoring a recipe that brings a tool needs the owner's approval. `vendor` exits 4 and says, for each tool, what it does, what it needs installed and what it may touch; the owner's words approve it:

```baton
baton vendor path/to/recipe --approved --note "the owner's words"
```

A later version whose tool files are unchanged is not asked about again; a changed tool is.

A tool needs `uv` and a Python that matches its `runtime.version`. Baton never downloads a Python. If none matches, install one. On first use Baton builds the tool's environment from its lock file, installing only the pinned, hash-checked packages, in `~/.baton/tools/<lock hash>-py<x.y>/`. Every project and tool with the same lock and Python reuses that environment. To build it ahead of time, for example before going offline:

```baton
baton tools setup
```

`baton check`, `baton doctor` and `baton start` report a tool that cannot run on this machine, and say what to install or set. Such a part is refused when it is dispatched, and the run waits until it is fixed.

What a tool may touch is declared in its `reach`:
- **Files:** `workspace` is `none`, `read` or `write`, enforced as for any worker. A part that may not change the project and does is stopped for the owner to inspect.
- **Secrets:** a tool gets none except the ones it names. Each is stored like any other [secret](admin.secrets#here-now); a missing one is reported before the part runs.
- **Network:** declared and shown at vendoring, but **not enforced**. Baton cannot stop a script from reaching the network unless it runs in an isolated container. Read a tool that says `network: false` as a claim to check, not a guarantee.

A tool runs in an empty scratch folder, never in its own folder, so it cannot change the recipe. Every run records which tool ran, the hashes of its files and lock, the Python version and the environment.

A tool can ship **worked examples**: inputs, and the result it must give for them. Each example is a folder `tools/<id>/examples/<name>/`. It holds `input.json` for the plain values, `inputs/<input name>.<ext>` for each file the tool reads, `expected.json` for what the tool's `output.json` must equal, and `expected/<artifact>.<ext>` for each file it must write, compared byte for byte. To run every tool of a recipe on its examples, on this machine:

```baton
baton tools test path/to/recipe
```

Each example passes or fails, and a failure names the first difference, for example `artifact 'differences': line 4: expected '…', the tool wrote '…'`. The command exits 0 only when every example passes. With `--require-examples`, a tool that has no examples also fails; the recipe builder checks the tools it writes this way. Keep git from changing line endings in example files: this repository's `.gitattributes` has `**/tools/*/examples/** -text`, and Baton already protects vendored recipes in `.baton/`.

Two more options serve larger tools. `--tool <id>` tests only that tool. `--repeat <n>` runs each example `n` times, and every run must give the expected result, so a tool whose result changes from one run to the next fails, and the report says which run differed:

```baton
baton tools test path/to/recipe --tool reconcile --repeat 2
```

An **engineered tool**, which the recipe builder builds from the owner's own examples, carries a `contract.json` beside its `tool.yaml`. The contract says what the tool does, its inputs and outputs, what it may touch, every package it needs and why, and why it is still one tool. Each of its examples has an `about.json` that says whether the owner supplied it or the builder drafted it, and which of its files were copied from the owner's documents. Until the tool is written, the recipe loads with a warning, `tool.unbuilt`. `baton tools test --allow-unbuilt` lists such a tool and skips it, and `vendor` refuses the recipe until the tool is built. To check that an engineered tool has enough examples, and that the owner's files were copied exactly:

```baton
baton tools examples path/to/recipe --run <run>
```

Each engineered tool needs at least three examples, one of them marked as the awkward case. Every file copied from the owner must be byte for byte the document the run bound to the role `examples`. The report lists the examples the builder drafted, and those whose expected result was written from the owner's words, so the owner can approve them.

Whatever a tool starts must end before the tool does. A tool that leaves a process running fails, and the process is stopped. On Windows Baton holds the tool in a job object to do this, and elsewhere in a process group, so a process that deliberately detaches itself is not found.

## Helpers for recipe authors {#authors}

`baton recipe check <package> --ledger <file>` is a helper that a recipe's own checks run: it verifies that no requirement is open and that every confirmed one carries the owner's words. For an engineered tool it also enforces the parts of the tool budget that can be checked mechanically: the tool's `reach` is as its contract declares, every package the contract names is pinned in the lock, and the tool has at most 600 lines of code (its examples and its own tests not counted) unless the contract says why it is still one tool. The recipe format is published as JSON Schema in the runtime's `formats/` data, so an assistant can pre-check what it writes. Writing recipes is covered by the design documents; a guided path is the [recipe builder](recipes.recipe-builder#here-now).

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

When a run starts, or when a part first needs a document, the assistant proposes one from the project's documents (`baton documents`) and the owner confirms it. Each step receives the version the owner confirmed. A role describes the document it needs, never the recipe or step that made it: `baton vendor` refuses a role that names another recipe (`software_feature_design`, `fit-check@4`) or a step (`steps.setup`), so the recipe stays shareable. A recipe without `project_inputs` works as before. The role name `policy` is reserved: a step that declares the input `project.policy` receives the [project policy](admin.project-settings#policy) its run started under (its floors, governing recipes and permissions, with its hash), for example a release step that must state its authority. Nothing else puts the policy in a packet.

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

## Guidance documents {#guides}

A guide tells a worker how to produce one document well enough to use, without a full process: a lean business plan, a marketing plan, a standard operating procedure, a project charter, a decision record. Baton comes with these five; a project keeps its own in `guides/<id>.md`, beside its other files. `baton guides` lists both.

A guide is Markdown with front matter and four sections:

```markdown
---
format: baton-guide/1
id: shop-rota
version: 1
title: Shop rota
description: Who works which shift, week by week.
produces: a weekly rota (Markdown)
---

## Purpose
## What to produce
## What good looks like
## What to ask the owner
```

A guide that comes with Baton is named by its id; a project's may be named freely (`guides copy` uses the id, and recipe builder names the guide it writes after its own piece of work). Every field is required, every section must say something, and, as in a recipe, no model or vendor name may appear anywhere: a guide works with any worker. `baton guides check <file>` checks one, for a recipe's own checks to run; in a check that runs on a part's result, `baton guides check --artifact <name>` checks the guide that part returned, before it is published. A guide in `guides/` becomes something a run can build on once it is a project document: `baton guides copy <id> --note "<words>"` copies one that comes with Baton and records that the owner vouches for it.

