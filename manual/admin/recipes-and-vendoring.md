---
id: admin.recipes-and-vendoring
title: Recipes, vendoring and trust
audience: admin
order: 90
summary: How a process is added to a project, pinned and verified, and what to review first.
related: [admin.network-and-security, recipes.software-feature]
anchor_aliases: {tools: programs}
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

Things to read: every `script` check's command, any [program](#programs) it ships, any `command` adapter a profile would run for it, the files it publishes and where (`publish: to:`), and the capabilities each part requires. Recipes declare the capabilities they need, never a model or vendor, and Baton's loader rejects a recipe that names one.

## New versions and retired ids {#versions}

A published version is never edited in place; a change is a new version. When a new version changes a kept part's signature, or reuses an id an earlier version retired, vendoring needs the owner's decision: `vendor` exits 4 and lists the flags, then:

```baton
baton vendor path/to/recipe --approved --note "the owner's words"
```

## Retiring a recipe {#retiring}

When one recipe replaces another, the old one says so in a new version of its own:

```yaml
id: software-feature
version: 3
retired: { replaced_by: software }
```

From then on new work goes to the replacement, and nothing that already uses the old one breaks:

- `baton recipes` marks it `[retired: software replaces it]`, and the list of processes your assistant and the builder read marks it too.
- Framing and project reviews never propose it. A proposal that names it anyway is refused, naming the replacement.
- `baton vendor` and `baton start` still work, with a warning naming the replacement; a project with the old recipe pinned keeps running it.
- A new version shipped with Baton can retire a recipe your project vendored earlier: the newest version known to the project decides.

A recipe cannot be replaced by itself. A recipe shipped with Baton is replaced only by another shipped recipe that is not retired itself; vendoring a recipe whose replacement is neither vendored nor shipped warns you.

## Programs a recipe ships {#programs}

Some work is better done by plain code than by an AI worker: a calculation, a file conversion, a comparison. A recipe can ship a **program** for such a part: a Python script in `programs/<id>/` with a `program.yaml` and a lock file of exact dependency versions with their hashes. The part names it with `program: <id>`, and no worker can do that part instead.

Vendoring a recipe that brings a program needs the owner's approval. `vendor` exits 4 and says, for each program, what it does, what it needs installed and what it may touch; the owner's words approve it:

```baton
baton vendor path/to/recipe --approved --note "the owner's words"
```

A later version whose program files are unchanged is not asked about again; a changed program is.

A program needs `uv` and a Python that matches its `runtime.version`. Baton never downloads a Python. If none matches, install one. On first use Baton builds the program's environment from its lock file, installing only the pinned, hash-checked packages, in `~/.baton/programs/<lock hash>-py<x.y>/`. Every project and program with the same lock and Python reuses that environment. To build it ahead of time, for example before going offline:

```baton
baton programs setup
```

`baton check`, `baton doctor` and `baton start` report a program that cannot run on this machine, and say what to install or set. Such a part is refused when it is dispatched, and the run waits until it is fixed.

What a program may touch is declared in its `reach`:
- **Files:** `workspace` is `none`, `read` or `write`, enforced as for any worker. A part that may not change the project and does is stopped for the owner to inspect.
- **Secrets:** a program gets none except the ones it names. Each is stored like any other [secret](admin.secrets#here-now); a missing one is reported before the part runs.
- **Network:** declared and shown at vendoring, but **not enforced**. Baton cannot stop a script from reaching the network unless it runs in an isolated container. Read a program that says `network: false` as a claim to check, not a guarantee.

A program runs in an empty scratch folder, never in its own folder, so it cannot change the recipe. Every run records which program ran, the hashes of its files and lock, the Python version and the environment.

A program can ship **worked examples**: inputs, and the result it must give for them. Each example is a folder `programs/<id>/examples/<name>/`. It holds `input.json` for the plain values, `inputs/<input name>.<ext>` for each file the program reads, `expected.json` for what the program's `output.json` must equal, and `expected/<artifact>.<ext>` for each file it must write, compared byte for byte. To run every program of a recipe on its examples, on this machine:

```baton
baton programs test path/to/recipe
```

Each example passes or fails, and a failure names the first difference, for example `artifact 'differences': line 4: expected '…', the program wrote '…'`. The command exits 0 only when every example passes. With `--require-examples`, a program that has no examples also fails; the recipe builder checks the programs it writes this way. Keep git from changing line endings in example files: this repository's `.gitattributes` has `**/programs/*/examples/** -text`, and Baton already protects vendored recipes in `.baton/`.

Two more options serve larger programs. `--program <id>` tests only that program. `--repeat <n>` runs each example `n` times, and every run must give the expected result, so a program whose result changes from one run to the next fails, and the report says which run differed:

```baton
baton programs test path/to/recipe --program reconcile --repeat 2
```

An **engineered program**, which the recipe builder builds from the owner's own examples, carries a `contract.json` beside its `program.yaml`. The contract says what the program does, its inputs and outputs, what it may touch, every package it needs and why, and why it is still one program. Each of its examples has an `about.json` that says whether the owner supplied it or the builder drafted it, and which of its files were copied from the owner's documents. Until the program is written, the recipe loads with a warning, `program.unbuilt`. `baton programs test --allow-unbuilt` lists such a program and skips it, and `vendor` refuses the recipe until the program is built. To check that an engineered program has enough examples, and that the owner's files were copied exactly:

```baton
baton programs examples path/to/recipe --run <run>
```

Each engineered program needs at least three examples, one of them marked as the awkward case. Every file copied from the owner must be byte for byte the document the run bound to the role `examples`. The report lists the examples the builder drafted, and those whose expected result was written from the owner's words, so the owner can approve them.

Whatever a program starts must end before the program does. A program that leaves a process running fails, and the process is stopped. On Windows Baton holds the program in a job object to do this, and elsewhere in a process group, so a process that deliberately detaches itself is not found.

## Helpers for recipe authors {#authors}

`baton recipe check <package> --ledger <file>` is a helper that a recipe's own checks run: it verifies that no requirement is open and that every confirmed one carries the owner's words. For an engineered program it also enforces the parts of the program budget that can be checked mechanically: the program's `reach` is as its contract declares, every package the contract names is pinned in the lock, and the program has at most 600 lines of code (its examples and its own tests not counted) unless the contract says why it is still one program. The recipe format is published as JSON Schema in the runtime's `formats/` data, so an assistant can pre-check what it writes. Writing recipes is covered by the design documents; a guided path is the [recipe builder](recipes.recipe-builder#here-now).

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

## How a person's part is shown {#interaction-hints}

When a person does a part (a step a `manual` worker takes), or approves one at a human gate, Baton asks through an interaction request: what to fill in is the step's output schema, and the files it asks for are its declared artifacts. Any client may show it: the assistant in conversation, the answer file (`baton answer <id> --template`), or a page. A recipe may add advice on how to show it, in a hints file of its own:

```yaml
steps:
  - id: match
    output_schema: schemas/match.json
    artifacts: [{name: photo}]
    interaction: {hints: hints/match.yaml}
    gates:
      - type: human
        prompt: "Is the matching right?"
        interaction: {hints: hints/match.yaml}   # how to show what was produced
```

```yaml
# hints/match.yaml
order: [checked, matches]
groups: [{title: "The receipt", fields: [matches]}]
fields:
  matches: {widget: table, help: "One row per receipt line", label: "Receipt lines"}
summary: [matches]            # what to show before the owner confirms
```

The hints are `order`, `groups`, `fields` (each with `widget`: `radio`, `dropdown`, `checkboxes`, `textarea`, `table` or `slider`; `help`; `label`) and `summary`. They are advice: a client that ignores them still produces a valid answer. A field inside a group or a table row is named with a dot (`matches.item`). `baton vendor` refuses a hints file that names a field the step's output schema does not have, an unknown hint or widget, or a step without `output_schema` (`interaction.bad_hints`, `interaction.needs_output_schema`). A recipe ships no script for showing anything.

A form can hold: named fields; text (with choices, suggestions, a date); numbers with bounds; yes or no; several choices; a table of rows; a group of fields. An output schema that needs more (a `$ref`, conditions, a field of two types) still works: its request is marked `renderable: false`, and the person writes the values by hand in the answer file.

## Files an approval locks {#approved-files}

A human gate may lock the files its approval covers, so that nothing later in the run changes them without the owner deciding. Acceptance specs approved with a plan are the usual case:

```yaml
gates:
  - type: human
    prompt: "Are these the acceptance specs?"
    locks: { paths: ["tests/acceptance/specs/**"], on_violation: warn }   # or just: locks: ["tests/acceptance/specs/**"]
```

When the owner approves, Baton records every matching file with its hash. From then on, for the rest of the run:

- a step that changes, adds or deletes a matching file is caught when it finishes. With `warn` (the default) it waits for the owner to keep or undo the change; with `fail` that attempt fails;
- a change made between steps, by hand, stops the next step from starting until the owner keeps the change (`decide <run> lock:<step>#<gate> accept`) or the files are restored. The message names the commit to restore them from;
- writing a delivered file over a locked one asks the owner first, as for any file already there.

Revising the step whose gate locked the files releases the lock; approving it again locks the files as they are then. A lock cannot be waived. Globs follow the `protect` rules, are relative to the project and never match `.git` or `.baton`; `baton recipe check` refuses any other. `baton status` and `baton explain` show what is locked, by which approval, and any change found.

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

