---
id: 2026-11-capability-confidence
title: "Capabilities are likely until used; harness tooling is turned on per step and verified by use"
status: proposed
level: standard
decisions: ["0081", "0082"]   # amends 0081; new records listed under Design > Decisions
touches: [design/workers.md, design/runtime.md, design/director-interface.md, design/recipes.md, principles.md]
---

# Capabilities are likely until used; harness tooling is turned on per step and verified by use

## Request

### Problem

A profile's capabilities are a flat list taken as true. There are two ways to get one: research has to find a source and write it into `known-workers.yaml`, or the owner has to edit YAML. Both fail for the capabilities that matter most to routing:

- **No generated profile has `web_access`.** The research report of 2026-11-06 left it out of every route, because its rules allow a capability only with documented evidence. So any step requiring `web_access` cannot be routed, including the `worker-research` step itself (log of 2026-11-worker-setup, follow-up "Researcher reports Baton errors in one line").
- **Tooling belongs to the harness, not the model.** `web_access`, `shell`, `file_write`, `code_exec`, `repo_workspace` and `workspace_read` are provided by Claude Code or Codex and the flags Baton passes them. The model behind the harness does not decide them. But the adapters pass only a permission or sandbox mode (`claude_code`: `--permission-mode`; `codex`: `--sandbox workspace-write`), so whether web tools are actually available is left to each CLI's defaults.
- **`structured_output` is missing from almost every new model** in the 2026-11-06 data, for the same evidence rule. Most steps require it.

Owners should not need to edit YAML to get a worker that can search the web. A capability that *should* be present ought to be usable, and checked by the work itself.

### Acceptance criteria

1. Each capability on a profile has a state: `likely` (from data or a declaration, not yet observed), `verified` (observed working, with date and evidence) or `absent` (observed failing). Shipped and declared capabilities start `likely`.
2. Routing treats `likely` and `verified` as eligible and `absent` as not eligible. Among otherwise equal candidates, a `verified` capability is preferred over a `likely` one.
3. Capability states are kept machine-wide, outside the profile files, so recording one never makes a generated profile look owner-edited (0079's content hash is unaffected).
4. Each harness provider in `known-workers.yaml` carries a **tool map**: for each tooling capability, the args that turn it on, the CLI version range and sources. It is researched data ([2026-11-cli-model-routes](2026-11-cli-model-routes.md)), not adapter code; the adapter only places the args in its command line. A step gets only the tools its `requires` names (least privilege). A step requiring `web_access` on a `claude_code` or `codex` profile runs with that harness's web tools explicitly enabled.
4a. **Revision drift.** `workers setup` checks each mapped flag against the installed CLI's `--help`; a missing flag means the capability is not offered on that machine. A flag that the CLI rejects at dispatch is classified `platform` / `harness_flag_rejected`, which opens a platform incident (§12.3). The platform SME is consulted on it and proposes the data fix. The capability goes `absent` on that profile until the fix lands or the CLI version changes.
5. **Tooling capabilities are verified by use.**
   - A successful tool call observed in a step that required the capability records `verified`.
   - A tool that is denied or unavailable records `absent`, classifies the attempt `platform` / `capability_absent`, and re-routes the step to the next eligible worker without spending one of the step's attempts.
   - A step that passed without using the tool records nothing.
6. Model-quality capabilities (`technical_reasoning`, `long_form_writing`) are never changed automatically. `structured_output` becomes `absent` only after repeated schema-gate failures on one profile (threshold in Open questions); one failure changes nothing.
7. No extra model calls are made to verify. Real dispatches are the checks, amending 0081. An explicit `--verify` still works as before.
8. The owner can see each capability's state (`baton workers status`) and can reset one to `likely` or declare it `absent` without editing YAML (`baton workers declare`, an engine call and an MCP tool).
9. An `absent` tooling capability goes back to `likely` when its harness's version changes, since an upgrade may add the tool.
10. **Web steps steer the owner to a subscription CLI.** When a recipe the owner is about to run has a step requiring `web_access` and no profile has `web_access` other than `absent`, the following strongly recommend installing and logging in to a subscription CLI (Claude Code or Codex) as the way to give such steps a worker:
    - framing or fit-check, when the plan is proposed;
    - `doctor`;
    - the Director's onboarding.

    Each says in plain words why, and how. `doctor` stays one line when healthy.
11. Every change of state is recorded in the project log with the attempt that produced it, so a run's record shows why a worker was or was not chosen.
12. Tests cover each criterion; `pytest` passes.

### Open questions

1. `structured_output`: how many consecutive schema-gate failures on one profile mark it `absent` (suggest 3, counted across projects)? And does a pass reset the count?
2. Should a `verified` state expire (e.g., after 90 days), or stand until a failure or a harness version change?
3. Evidence of tool use needs the harness's machine-readable output. Claude Code `--output-format stream-json` and `codex exec --json` **[VERIFY]**. Is switching the harness adapters to those formats acceptable, given that today intake reads only `result.json`?
4. When a tooling capability is `absent` on every profile, should a step requiring it escalate at once (as `no_eligible_worker` does now, Decision 0002), or wait for the owner to add a worker?

## Design

### Doc edits

- `design/workers.md` §6.1:
  - capability states (`likely` / `verified` / `absent`, with evidence) and the machine-wide state file `~/.baton/capability-states.yaml`, which is not part of any profile or its hash;
  - `workers status` shows the states.
- `design/workers.md` §6.3:
  - the adapter reads the harness provider's tool map from known-workers data (args are researched, not hard-coded);
  - the adapter adds only the args for capabilities the step requires;
  - setup's `--help` check, and `harness_flag_rejected` handled through a platform incident and the platform SME;
  - the adapter's `failure_signals` gain patterns for denied or unavailable tools (`capability_absent`);
  - harness output is read as an event stream for tool-call evidence (Open question 3).
- `design/workers.md` §6.4: data and declarations seed capabilities as `likely`; `--verify` unchanged; 0081 amended.
- `design/runtime.md` §8.4:
  - eligibility excludes `absent`;
  - `verified` is preferred over `likely` before the existing tie-breaks;
  - `independence_reason` and eligibility lines show the state.
- `design/runtime.md` §8.2: new event `capability_observed {profile, capability, state, evidence, attempt}`.
- `design/runtime.md` §8.8: class `platform` / `capability_absent` re-routes without spending an attempt.
- `design/director-interface.md` §13.x:
  - the onboarding and `doctor` recommendation for web steps (criterion 10);
  - the Director never edits capability states except through `workers declare` on the owner's instruction.
- `design/recipes.md` §5.6: a note that tooling capabilities are provided by adapters, not models. The vocabulary is unchanged (`web_access` already exists).
- `principles.md`: "a capability that should be there is usable, and the work checks it".

### Decisions

- **New:** capabilities carry a state (`likely` / `verified` / `absent`), kept machine-wide outside profiles; routing excludes only `absent` and prefers `verified`.
- **New:** tooling capabilities belong to the harness, not the model. Their flags are researched data checked against the installed CLI. Adapters turn on only what a step requires, and verify by use. Flag drift goes through a platform incident and the platform SME.
- **New:** `capability_absent` re-routes without spending an attempt; reset on harness version change.
- **Amend 0081:** real dispatches are verification evidence; still no extra calls without `--verify`.
- **Unchanged 0082:** machine-dependent capabilities still need a declaration or a probe. A probe or a real use that passes records `verified` in the same store.

## Plan

### 1. Capability states and routing

- **Outcome:**
  - The state store exists.
  - Profiles load capabilities as `likely` unless the store says otherwise.
  - Routing excludes `absent`, prefers `verified` and shows states.
  - `workers status` and `workers declare` read and set states.
- **Criteria:** 1, 2, 3, 8, 11 (state events), 12.
- **Effort:** M

### 2. Harness tool maps, least-privilege flags, observed evidence

- **Outcome:**
  - The `claude_code` and `codex` adapters read tool maps from known-workers data and pass only the required tools. The seed carries hand-entered maps until the first research run under 2026-11-cli-model-routes replaces them.
  - Setup checks the flags against `--help`.
  - Tool calls and denials are read from the harness event stream.
  - `capability_observed` is recorded; `capability_absent` re-routes; `harness_flag_rejected` opens a platform incident.
- **Criteria:** 4, 4a, 5, 7, 9, 12.
- **Effort:** M

### 3. Structured output by schema-gate evidence

- **Outcome:** repeated schema-gate failures on one profile mark `structured_output` `absent`, per the agreed threshold.
- **Criteria:** 6, 12.
- **Effort:** S

### 4. Web-step recommendation

- **Outcome:** framing or fit-check, `doctor` and onboarding recommend a subscription CLI when a planned step needs `web_access` and nothing can provide it.
- **Criteria:** 10, 12.
- **Effort:** S

## Log

<One entry per slice, written in the slice's own commit together with its code, tests and design doc edits.>
