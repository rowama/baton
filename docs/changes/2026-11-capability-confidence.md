---
id: 2026-11-capability-confidence
title: "Capabilities are likely until used; harness tooling is turned on per step and verified by use"
status: in-progress
level: standard
decisions: ["0081", "0082", "0084", "0085", "0086", "0087"]   # amends 0081
touches: [design/workers.md, design/runtime.md, design/director-interface.md, design/recipes.md, design/layouts.md, principles.md]
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

Answered by the owner, 2026-11-08 (all four as suggested):

1. `structured_output`: three schema-gate failures in a row on one profile, counted machine-wide; a pass resets the count ([0087](../decisions/0087-structured-output-by-schema-gate.md)).
2. A `verified` state does not expire; it stands until a failure or a harness version change, which returns it to `likely` ([0084](../decisions/0084-capability-states.md)).
3. The harness adapters switch to their event streams (`claude --output-format stream-json`, `codex exec --json`, both seen in the installed CLIs). Intake still reads only `result.json`; the stream is the attempt's log, scanned for tool evidence ([0085](../decisions/0085-harness-tool-maps.md)).
4. A tooling capability `absent` on every profile escalates at once, like `no_eligible_worker` (0002), with the subscription-CLI advice for web steps ([0086](../decisions/0086-capability-absent-reroutes.md)).

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

- [0084](../decisions/0084-capability-states.md): capabilities carry a state (`likely` / `verified` / `absent`), kept machine-wide outside profiles; routing excludes only `absent` and prefers `verified`; `verified` does not expire.
- [0085](../decisions/0085-harness-tool-maps.md): tooling capabilities belong to the harness, not the model. Their flags are researched data checked against the installed CLI. Adapters turn on only what a step requires, and verify by use, read from the harness event stream. Flag drift goes through a platform incident and the platform SME.
- [0086](../decisions/0086-capability-absent-reroutes.md): `capability_absent` re-routes without spending an attempt; reset on harness version change; absent everywhere escalates at once.
- [0087](../decisions/0087-structured-output-by-schema-gate.md): `structured_output` is absent after three schema-gate failures in a row on one profile.
- **Amend [0081](../decisions/0081-live-verification-on-request.md):** real dispatches are verification evidence; still no extra calls without `--verify`.
- **Unchanged [0082](../decisions/0082-machine-dependent-capabilities.md):** machine-dependent capabilities still need a declaration or a probe. A probe or a real use that passes records `verified` in the same store.

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

### 1. Capability states and routing

- **Commit:** 2026-11-capability-confidence: Capability states and routing
- **Summary:**
  - `capability_states.py`: the machine-wide store `~/.baton/capability-states.yaml` (`baton-capability-states/1`), locked writes; a claimed capability with no entry is `likely`; a state never adds a capability; an owner's reset to `likely` forgets the observation.
  - `WorkerProfile` carries the states as a private attribute that `Project.profiles` attaches, so profile files, content hashes and `worker_profile_sha256` are untouched.
  - Routing (`routing.py`): `absent` counts as missing, with when, how and the reset command in the reason; the profiles no preference names are ordered by how many required capabilities are `verified`, then by name; eligible entries show `capabilities` states. The packet builder, SME eligibility and `doctor` share the rule through `requirement_gaps`.
  - `baton workers status` shows each generated profile's states and every recorded one; `baton workers declare --profile <p> --likely|--absent <cap>`, the engine's `workers_declare(profile=…)` and the MCP tool set them.
  - `engine.observe_capability` records a dispatch's observation and, when the state changes, `capability_observed` in the project log with the run, step and attempt (used by slices 2 and 3).
  - Decisions 0084–0087 recorded from the owner's answers; 0081 amended. Docs: §6.1, §8.2, §8.4, §4.4, §13.1, the Director skill (§13.3), §2.
  - Also fixed `tests/test_resources_refresh.py`, which broke when the 2026-11-06 data added more OpenRouter routes: the reroute now changes one route, and the "new model" is one the data does not have.
  - Tests: `tests/test_capability_states.py` (likely by default, absent excluded with the reset hint, verified preferred after preferences, no profile file or hash change, no added capability, engine and CLI declare, one event per change with its attempt, a broken state file is configuration).
- **Review:** clean (self-review)
- **Accepted:** pending owner review

### 2. Harness tool maps, least-privilege flags, observed evidence

- **Commit:** 2026-11-capability-confidence: Harness tool maps, least-privilege flags, observed evidence
- **Summary:**
  - `known_workers.py`: a harness provider's `tools` map (`ToolArgs`: args, position, off args, help args and flag, evidence names, versions, sources), validated to tooling capabilities on harness providers only. `defaults/known-workers.yaml` seeds `web_access` for `claude_code` (`--allowedTools` / `--disallowedTools WebSearch,WebFetch`) and `codex` (`--search` before `exec`, marked [VERIFY]), entered by hand from the installed CLIs' `--help` until 2026-11-cli-model-routes research replaces them.
  - Adapters (`adapters/harness.py`): `ToolPlan` / `plan_tools` turn on the mapped tools a step needs and the profile claims and turn the others off; dispatches use the event streams (`--output-format stream-json --verbose`, `--json`); `--version` parsing; `harness_flag_rejected` failure signals.
  - Engine: dispatches (and SME turns) record `tools` and `harness_version`; at completion `tool_evidence.py` scans the attempt's log, and `observe_capability` records `verified` or `absent`. A denial discards the attempt as `capability_absent`, readies the step with `not_counted` (state.py moves the budget base), opens no incident, and escalates at once as `no_eligible_worker` when nobody is left. A rejected flag is a platform incident and marks the tools absent. Routing first resets states observed under another harness version.
  - Setup (`resources.py`): discovery reads each CLI's version and checks each mapped flag in its `--help`; a harness profile gets a tool-map capability only when the flag is shown, and `workers setup` reports the ones not offered.
  - Docs: §6.3, §6.4, §8.4, §8.8, §5.6.
  - Tests: `tests/test_tool_evidence.py` (Claude Code uses, denials, non-denial errors, noise; Codex events); `tests/test_harness_tools.py` (web tools turned on and verified with the attempt recorded, no record without use, denial re-routes without spending an attempt and opens no incident, absent everywhere escalates at once, rejected flag opens an incident and marks absent, a new harness version resets observed states but not the owner's, setup offers a tool only when `--help` shows its flag); `tests/test_harness.py` updated for the stream and off args, with tool-plan and version tests. The fake harness answers `--version` and `--help`, prints scripted events, rejects a scripted flag, and accepts flags before `exec`.
- **Review:** clean (self-review). Not verified live: that `codex exec` honours the top-level `--search`, and the exact event shapes of the real CLIs' streams; the first real web step records what it sees.
- **Accepted:** pending owner review

### 3. Structured output by schema-gate evidence

- **Commit:** 2026-11-capability-confidence: Structured output by schema-gate evidence
- **Summary:**
  - `intake.py` notes whether a step's output schema was checked and passed; `result_rejected` and the provenance `gate_passed` carry `output_schema`.
  - `capability_states.schema_gate` counts failures per profile machine-wide (`failures` on the `structured_output` entry); a pass resets the count; the third failure in a row records `absent`. `engine.observe_schema_gate` runs after every intake (supervised completion and `submit`) and records `capability_observed` on the change.
  - Docs: §6.1.
  - Tests (`tests/test_capability_states.py`): two failures change nothing, the third makes it absent and routes to the other profile with one event carrying attempt 3; a pass resets the count; counts are per profile; a tool map may not name a model-quality capability.
- **Review:** clean (self-review)
- **Accepted:** pending owner review
