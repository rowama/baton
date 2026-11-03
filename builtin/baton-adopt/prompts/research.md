# Research the existing project

This project is being adopted into Baton under the recipe described in the `recipe`
input. Gather **evidence, not judgment**: which of the recipe's step outputs already
exist here, where, and in what state. You may read the working tree; do not change it.

Inputs:
- `recipe`: the recipe's steps (with their output schemas, artifacts and gates), its complexity levels and its run-input schema.
- `candidates`: files the runtime matched from the crosswalk, each with its path, hash, the rule that matched and the step (and artifact, output or gate) it maps to. When a crosswalk exists, mostly **confirm** these rather than interpret.
- `crosswalk` (optional): the prior process's mapping, for context.
- `scope`: the paths you may look at.
- `situation`: what the runtime detected (git, existing Baton runs).

Return a `baton-research/1` object:
1. `evidence`: every file you relied on: `path`, `sha256` (as given in `candidates`, or of the file), `kind`, `maps_to` (the step, as `<step>` or `<group>/<step>`), `confidence` (`high`, `medium`, `low`).
2. `work_items`: each piece of work the prior process tracked, with a short `key` (letters, digits, `.`, `_`, `-`), its `title`, `status` (`finished` or `in_flight`), where it stands (`position`), and for in-flight items the run `inputs` the recipe's run-input schema asks for.
3. `proposed_seeds`: for each in-flight work item, one seed per step whose output already exists **completely**: `work_item`, `step` (`<step>` or `<group>/<step>`), for steps in a per-item group the `item` index (0-based, in the seeded source output's array), the step `output` (or `output_from`, a JSON file holding it), its `artifacts` (`{name: path}`), `evidence` paths, and for gates passed outside Baton `gates: [{gate, evidence: [paths]}]`. The output must match the step's schema exactly; do not seed partial work. Never seed the triage step.
4. `agent_config`: existing agent instructions (`AGENTS.md`, `CLAUDE.md`, …): `path`, `kind`, `note`.
5. `path_candidates`: logical path keys the recipe publishes to, mapped to where this project keeps such files; `command_candidates`: e.g. `test_command`, `preflight`.
6. `gaps`: what is missing, ambiguous or assumed. Blameless: describe, do not judge.
