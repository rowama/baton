# Build the recipe package

Translate the approved design into a recipe package, and nothing more. The approved design is in
`shaped` (the last iteration's design and audit); the goal and chosen generality are in `profile`.
You work in the project; commit your work.

1. Write the package to `recipes/drafts/<run slug>/` (the run slug is the one `profile` was
   published under; use the same words, lower-case and hyphenated): `recipe.yaml`, `prompts/`,
   `schemas/` and `static/` as needed. Use the recipe format the other shipped recipes use. Name no
   model or vendor of a worker in the recipe: require capabilities, never a model. A product or
   standard the owner's work is *about* (a legitimate target of what the process delivers) may be named
   when the agreed scope is specific to it; otherwise the target is a run input.
2. Include a `scope` block that states what the recipe covers, what it is not for (naming a recipe
   that is, when you know one) and what varies by job. Set `parent: {id, version}` to the recipe in
   `profile.existing_recipe`/the base recipe when you built from one, otherwise `parent: null`.
3. A fact about the owner's one job (an `instance` ledger entry) goes in no prompt and no static
   file. Write it into an example run input instead.
4. Write the final ledger file to `recipes/drafts/<run slug>.ledger.json` and attach it as the
   `ledger` artifact: a JSON object `{"ledger": <the design's ledger, copied exactly>, "discovery":
   <the design's discovery records, copied exactly>}`. Do not edit either.
   A record with timing `in_generated_recipe` is part of the process: write its research stage
   (it requires `web_access`), its decision stage (a human gate, taking the research output as a
   required input) and the stages named in `generated.consumers`, each taking the decision stage's
   output as a required input, with the ids `generated` names. The target is a run input of the
   recipe, never a fixed value.
5. For each stage the design gives to a `program`, write the program and the step that runs it (§5.9 of
   the format; `spreadsheet-reconcile`'s `programs/csv_diff/` is a worked example):
   - `programs/<id>/<id>.py`: one file, the Python standard library only, no network, no secrets. It
     reads the inputs file named by its first argument (one JSON object keyed by input name; a
     file input is `{"path", "media_type"}`), writes `output.json` (a JSON object) and any
     artifacts (`<artifact>.<ext>`) into the folder named by its second argument, and nothing else.
     On input it cannot handle it prints a plain reason on stderr and exits 1. It does exactly what
     the design's `program.does` says, no more.
   - `programs/<id>/program.yaml`: `id`, `description` (the design's `does`), `runtime: { kind: python,
     version: ">=3.10" }`, `entry: ["python", "{program}/<id>.py", "{input}", "{output}"]`,
     `dependencies: { lock: requirements.lock }` and `reach` from the design
     (`{ workspace: none, network: false, secrets: [] }` unless the design says otherwise).
   - `programs/<id>/requirements.lock`: empty (a simple program needs only the standard library).
   - each of the design's examples as `programs/<id>/examples/<name>/`: `input.json` (the JSON
     inputs), `inputs/<input name>.<ext>` (each file input), `expected.json` (the output, exactly)
     and `expected/<artifact>.<ext>` (each artifact, byte for byte; Python's `csv` module ends
     lines with `\r\n`).
   - the step: `program: <id>` in place of `requires` and `prompt`, `workspace` equal to the program's
     `reach.workspace`, its inputs, an `output_schema` for `output.json`, its artifacts and a
     `schema` gate. A program that spends money or changes something others depend on runs only after
     a step where the owner approves (a `human` gate before it).
   Run `baton programs test recipes/drafts/<run slug> --require-examples --allow-unbuilt` yourself and
   fix the program (not the example) until every example passes; the runtime runs it again as a gate.
   An example the owner approved is never changed to fit the code.
   For a program the design gives as `kind: engineered`, write everything but its code and its
   examples: `program.yaml` (its `entry` naming `{program}/<id>.py`, which you do not write), the empty
   `requirements.lock`, the step, and `programs/<id>/contract.json`: `{"kind": "engineered", "does":
   <program.does>, "input_schema", "output_schema", "reach": <program.reach>, "packages",
   "budget_reason"}` and `size_reason` if the design gives one, copied from the design's `contract`.
   The owner's examples are placed next, and the program is built to them by another worker.
   List each engineered program to be built in your result's `engineered_programs`, in the order to build
   them: `{program, title}` (no `id`). When you built from a base recipe that has engineered programs, copy
   each program the design marks `unchanged` exactly, with its code and examples, and list only the
   `changed` and `new` ones; the gate reruns every program's examples. When a revision asks you to do a
   program's stage another way, remove that program's folder and step, write the stage as the revision
   says, with its `executor_choice` record, and leave the program out of `engineered_programs`.
6. Write the `walkthrough` artifact (markdown) for the owner: what the process does, who does each
   stage, what they decide, what happens when something fails, and what it covers and does not.
   Say plainly when and how the owner will choose how the work is done (decided now, in what they
   approved, or at a stage of the process before the work that depends on it), and what the process
   will do to find the options. Then two lists:
   - **Small programs in this process:** each program, what it does, what it needs installed (Python,
     nothing else, or the packages a program built to your examples needs) and what it may touch
     (for example "does not open your files and does not use the internet"). Say which programs will
     be built to examples you supply, and what those examples are.
   - **Parts an AI helper does that a program could do:** each one, what a program would have given
     (the same result every time, no cost each run, no AI service needed), what it would have cost,
     and why it was not used (your limit on programs, your choice, or too big for a small program).
   Leave out a list that would be empty. Mark the parts where letting your own AI assistant act for
   you would be risky, and say why. No file names, no jargon.

Run `baton plan recipes/drafts/<run slug>` yourself before you finish, and fix what it reports. The
runtime runs it again, and `baton recipe check`, as gates. Return the commit, the package path, the
ledger path, `engineered_programs` (empty when there are none) and a short summary.
