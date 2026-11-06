---
id: 2026-11-worker-setup
title: "Machine-wide worker resources are maintained separately from project setup"
status: in-progress
level: standard
decisions: ["0074", "0075", "0076", "0077", "0078", "0079", "0080", "0081", "0082", "0083"]
touches: [design/workers.md, design/director-interface.md, design/adoption-and-framing.md, design/layouts.md, design/runtime.md, design/versioning.md, principles.md]
---

# Machine-wide worker resources are maintained separately from project setup

## Request

### Problem

Before any work can run, the owner must write `~/.baton/workers.yaml` by hand: one profile per model, each with adapter, vendor, model string, tier, capabilities, context size, auth mode, `env_deny` and PATH sources (§6.1). Much of this is shared knowledge about models and harnesses; the rest describes resources available on a particular machine or account. Neither belongs to an individual project.

Baton currently has no mechanism that combines those inputs into maintained profiles. Harness adapters can inspect local authentication through `auth_status_argv` / `parse_auth_status`, but inspection cannot discover every resource an owner can use. An OpenRouter account, for example, must be declared by the owner. Requiring hand-written YAML for both kinds of resources adds avoidable friction before framing can begin (§11.6).

Researching available models, matching resources to a machine, and confirming project readiness are distinct responsibilities. Research should update shared repository data for all installations. Machine setup should consume that data and maintain machine-wide profiles. Project initialization should confirm readiness without starting research or owning machine configuration.

Worker identity also currently conflates model identity with the identifier used to invoke it. `WorkerProfile` has `vendor` and `model`, but no explicit access provider; the API adapter passes `model` directly to LiteLLM. Independence checks compare declared model strings literally. The same underlying model accessed directly and through OpenRouter can therefore appear to be different models. This proposal extends to runtime identity and compatibility, not just research data and setup.

### Acceptance criteria

1. A maintainer can explicitly launch a research AI agent in a source checkout to propose updates to `defaults/known-workers.yaml`, with sources, dates and verification evidence. Research systematically covers frontier providers, reasonably popular alternatives, hosted and open-weight models, and model categories capable of autonomous jobs, with explicit inclusion criteria and coverage gaps. The result is a reviewable repository change.
2. The researcher and any research-only dependencies are excluded from ordinary runtime installations. The reviewed known-workers file ships as read-only input. No separate private repository or special source-access restrictions are required.
3. An explicitly invoked worker resource manager combines the shipped list, locally discovered resources and persistent owner declarations to maintain generated profiles in `~/.baton/workers/`, one file per profile (0079; the owner's `~/.baton/workers.yaml` is never written). Initial harness support includes Claude Code and Codex; owner-declared providers such as OpenRouter are supported through the relevant adapters.
4. On a machine without completed resource setup, the Director offers a short setup conversation: it reports discovered resources and asks about additional providers or endpoints. Answers, including an explicit answer that there are no additional resources, persist machine-wide and are reused across projects.
5. Resource declarations reference credentials through the supported secret mechanism; they do not contain credential values. The resource manager distinguishes owner-declared availability, local detection and successful live verification.
6. The manager never changes or removes a profile it did not generate. Owner-edited generated profiles are preserved. Untouched generated profiles may receive metadata refreshes for existing resources, but adding newly available models requires an explicit resource-manager run. Installing a Baton update does not expand the worker pool.
7. `baton init` and `baton doctor` primarily confirm readiness and explain missing setup. Neither starts research or silently maintains profiles. A healthy `doctor` result remains one plain line.
8. Profiles and resource declarations are machine-wide and available to all projects. Project exceptions and cost-based worker selection are deferred; existing project budgeting remains unchanged.
9. Validation checks the known-workers schema, pinned capability and tier vocabulary, execution support, provenance and verification metadata. Entries eligible for profile generation must resolve to an existing adapter; researched entries without execution support are explicitly marked. Packaging checks confirm that the data ships and the researcher does not. Relevant tests and `pytest` pass.

10. Profiles distinguish model creator, canonical model identity, access provider, provider-specific invocation identifier, adapter and machine resource/account. The same underlying model reached directly and through an intermediary has the same canonical identity while retaining distinct execution routes.
11. `different_model` compares canonical model identities across routes; `different_vendor` compares model creators. Switching access providers alone satisfies neither constraint. Unknown identities and mutable aliases must not be treated as proof of independence.
12. Dispatch, worker-selection and expert-consultation records preserve the identity and execution route used at the time. Independence and replay use recorded facts rather than reinterpreting historical records through the latest known-workers list. Existing profiles and event histories have an explicit compatibility/migration policy with no guessed identity mappings.

### Agreed direction

1. **Separate repository research from installed resource management.** A maintainer-only utility under a proposed `tools/worker-research/` directory runs the research agent and produces changes to `defaults/known-workers.yaml`. Maintainers review those changes before release. Ordinary installations receive the data, not the researcher. Source users may deliberately run the utility; this is a packaging boundary, not an access-control system.
2. **Use a machine-wide worker resource manager.** This separate utility consumes shared known-worker data and machine-specific inputs, then maintains the generated profiles in `~/.baton/workers/`. It owns discovery, declarations, profile generation, verification and refresh rules. The Director provides a conversational interface to it.
3. **Persist owner declarations separately from generated profiles.** Resources that inspection cannot discover must be expressible by the owner. The persistent input records the provider or endpoint, credential reference and owner-known availability restrictions. Generated profiles are output, not the only record of the owner's intent.
4. **Offer onboarding when machine setup is missing or incomplete.** The first Director to encounter that state offers setup, reports what was discovered, and asks about additional resources. Persisted completion state prevents repeated questions in each project. The owner can revisit resource setup later.
5. **Keep project initialization and diagnosis focused on confirmation.** `init` remains per-project. `doctor` reports machine readiness and provides actionable setup information. Neither launches the research agent; profile maintenance is delegated to the resource manager under the owner's instruction.
6. **Bound refreshes.** Untouched generated profiles can receive metadata refreshes for existing resources. Newly available models are added only during an explicit resource-manager run. Owner-created and owner-edited profiles remain protected. A runtime upgrade alone does not add models.
7. **Keep resources machine-wide.** All projects use the machine's available profiles. Per-project exceptions are deferred. Projects continue to set budgets using existing mechanisms; this change adds no worker pricing data or cost-based routing policy.

8. **Separate model identity from access route throughout Baton.** Canonical model identity and creator support independence checks; provider-specific identifiers, adapters and resource bindings support execution. Apply this distinction consistently to profiles, known-workers data, routing, diagnostics and persisted worker identities.
9. **Implement in dependency-ordered slices.** Establish the identity and compatibility contract before generating profiles against it. Deliver each slice with its own reviewable outcome and meaningful checks; broad research coverage does not imply adding every modality's execution adapter in this change.

### Open questions

All eight were answered by the owner on 2026-11-06 (suggestions given with rationale, in one batch):

1. Installed interface → [0077](../decisions/0077-workers-command.md): `baton workers status | setup | declare`, with engine calls and MCP tools.
2. Machine input format → [0078](../decisions/0078-machine-resources-file.md): `~/.baton/resources.yaml`; the owner asked that each resource name its `kind` explicitly so later kinds fit the same file, and setup state is kept per kind.
3. Identifiers and evidence, and 7. known-workers schema → [0080](../decisions/0080-known-workers-format.md).
4. Verification and quota → [0081](../decisions/0081-live-verification-on-request.md): live checks only on `--verify`; unverified generated profiles are eligible, flagged.
5. Machine-dependent capabilities → [0082](../decisions/0082-machine-dependent-capabilities.md).
6. Generated ownership and refresh → [0079](../decisions/0079-generated-profiles-directory.md): the owner chose a directory `~/.baton/workers/` with one file per profile, so owner-edited files are simply left alone (this amends criterion 3, which named `workers.yaml`).
8. Identity schema and compatibility → [0075](../decisions/0075-model-identity-separate-from-route.md) and, strict, [0076](../decisions/0076-unknown-identity-not-independent.md).

The agreed direction is recorded as [0074](../decisions/0074-worker-research-and-resources-separate.md).

## Design

The boundaries are recorded in 0074; interfaces and schemas in 0075–0082. Each slice writes its part of the design into the design docs listed below. The concept tables in this section give the reasoning; the decision records hold the rules.

### Runtime model identity and execution routes

The following concepts are distinct; final field names remain open:

| Concept | Purpose |
|---|---|
| Model creator | Organization responsible for the model; used by `different_vendor` |
| Canonical model identity | Stable identity of the underlying model/revision across access routes; used by `different_model` |
| Access provider | Service through which the owner obtains access, such as OpenRouter or a direct model API |
| Provider-specific invocation identifier | Exact identifier passed to that service or harness; may differ from canonical identity |
| Adapter | Baton execution mechanism, such as `litellm_api` or a harness adapter |
| Machine resource/account | Owner's configured access binding, endpoint and credential reference |

For example, an Anthropic model accessed directly and the same model accessed through OpenRouter have the same creator and canonical identity, but different access providers, invocation identifiers and resource bindings. The known-workers list maps supported routes to canonical identities using attributable evidence. An aggregator may conceal or vary the underlying serving host; represent that uncertainty rather than equating the access provider with a known host or creator.

Adapters receive the route-specific invocation identifier. Authentication resolves against the machine resource. Capabilities and availability reflect the selected route and machine as well as the model; canonical identity alone does not establish that a route supports a capability.

Routing preserves the existing same-profile exclusion and compares canonical identities for `different_model` and creators for `different_vendor`. A change of endpoint, account, adapter or access provider does not establish model or creator independence. Define conservative behavior for unresolved identities and mutable aliases, with actionable diagnostics and the existing explicit waiver mechanism where applicable.

Persist identity and route snapshots wherever worker identity is recorded, including worker-selection and expert-consultation events. Historical comparisons must use those snapshots. A later catalog update must not rewrite the identity of a completed result. Profile loading, event readers/replay, diagnostics and migration must agree on a documented policy for legacy records; unknown historical identity remains unknown unless an explicit evidence-backed migration resolves it.

### Repository research utility

- Proposed location: `tools/worker-research/`, outside the installed runtime package and shipped skill directories.
- Invoked explicitly by a maintainer, including routine scheduled or manually launched research-agent runs.
- Reads vendor documentation and other attributable evidence, updates known-worker data, and runs its validation checks.
- Produces a reviewable source change. Research does not directly publish a release or modify machine profiles.
- Uses separate research-only dependencies if needed. The current package includes `src/baton` and explicitly shipped data directories; retain that boundary and test the resulting installation artifact.
- No private repository split is needed. A person with the source can intentionally run the utility, but it is absent from normal runtime installations.

### Research coverage and model inclusion

The researcher aims for comprehensive, systematic coverage rather than a shortlist of the initial supported harnesses. It covers frontier providers such as xAI, Anthropic, OpenAI, Google/Gemini and Meta, plus reasonably popular alternative providers, open-source and open-weight models, and hosting or distribution platforms such as Hugging Face and OpenRouter. These examples are a starting point, not a fixed allowlist. Each research run should reassess the landscape and record its sources, inclusion criteria and known coverage gaps; it must not claim exhaustive coverage without evidence.

Distinguish model creators, model identities, distribution platforms and execution providers/endpoints. A model distributed through Hugging Face or offered through multiple OpenRouter routes must not be mistaken for unrelated model identities. Availability and verification evidence belong to the relevant execution route as well as the model.

Model size and modality do not determine inclusion. Cover LLMs, SLMs, vision models and other model categories that can perform a bounded job autonomously. For example, processing images or transcribing a supplied audio file can qualify. An ongoing interactive session, such as live conversational transcription, has different runtime requirements and is outside this job-based scope unless separately supported. Record the capabilities and input/output requirements needed to route such jobs correctly.

Research coverage may exceed current adapter support. Distinguish researched models from models that the installed runtime can execute; unsupported entries must not generate dispatch-eligible profiles merely because they appear in the known-workers file. The schema and validation must express that distinction rather than requiring an executable adapter for every researched entry.

### Installed worker resource manager

Inputs:

- The installed version of `defaults/known-workers.yaml`, consumed read-only.
- Local discovery, including installed harnesses and authentication status.
- Persistent machine-wide owner declarations, credential references and setup state.

Output: one file per generated profile in `~/.baton/workers/` (0079), with provenance sufficient to preserve owner changes and distinguish declared, detected and live-verified availability.

An explicit manager run can discover resources, accept owner declarations, offer verification and add model profiles. Metadata refreshes are limited to untouched generated profiles for existing resources. Runtime installation or upgrade does not itself add models. The manager must explain unavailable harnesses or failed verification in plain language, offering installation or login instructions appropriate to the failure.

### Director onboarding and readiness

Missing or incomplete machine setup triggers an offer, not an automatic research or maintenance run. The Director describes discovered resources and asks whether the owner wants to use additional providers or endpoints. It passes the answers to the resource manager and records completion at machine scope, including a decision to add nothing else.

The Director's rule against editing profiles without the owner's instruction remains in force. An owner-approved resource-manager invocation supplies that instruction. `init` and `doctor` confirm readiness and expose enough structured information for this conversation; they do not own profile writes. A completed setup with no usable workers still reports a readiness problem without repeating answered onboarding questions.

### Scope and budgeting

Resource availability is shared by all projects on the machine. Per-project profile exceptions are deferred. Existing project budget controls remain as they are; known-workers data does not yet capture costs, and this proposal does not introduce price-based selection or change default tier ordering.

### Expected doc edits

- `design/workers.md` §6.1 and adapters: canonical identity, model creator, access provider, invocation identifier and compatibility for existing profiles. A new setup section covers resource declarations, generated profiles, provenance, ownership, discovery, verification and bounded refresh rules.
- `design/director-interface.md` §13.1–§13.4: resource-manager interface, onboarding conversation, profile-edit authorization and readiness reporting. Remove the original proposal's `doctor --setup` approach.
- `design/adoption-and-framing.md` §11.6: machine resource setup supports framing; project initialization confirms availability rather than requiring hand-written profiles.
- `design/layouts.md` §4.1 and §4.4: maintainer research tooling, shipped known-worker data, machine declarations/setup state and generated profiles.
- `design/runtime.md` §8: independence semantics, identity/route snapshots and historical comparisons, including expert worker records.
- `design/versioning.md`: profile and event compatibility, migration and any format-version changes required by the identity split.
- `principles.md`: shared model knowledge and machine resource management avoid repeated owner configuration while preserving owner control over resource use.

### Decisions

- 0074: the boundaries between research, the resource manager and project setup.
- 0075: identity fields (`creator`, `model_id`, `provider`, `model`, `resource`), canonical-identity rules, `vendor` as legacy alias, event snapshots, no format bump.
- 0076: unknown identity is never proof of independence.
- 0077: `baton workers status | setup | declare`.
- 0078: `~/.baton/resources.yaml` (`baton-resources/1`), explicit `kind`, setup state per kind.
- 0079: generated profiles one per file in `~/.baton/workers/`, content-hash ownership, bounded refresh.
- 0080: `defaults/known-workers.yaml` (`baton-known-workers/1`): models, providers, routes.
- 0081: live verification on request only; unverified profiles eligible, flagged.
- 0082: machine-dependent capabilities need a declaration or a probe.

## Plan

Implement as separately reviewable slices in the order below. Each slice must preserve a usable runtime and land its relevant design updates and checks. Do not combine schema migration, researcher automation and onboarding into one implementation change.

### 1. Identity and compatibility contract

- **Outcome:** settle schema, canonical identity rules, unknown/alias behavior, route mapping, legacy profile/event handling and any version changes. Define examples covering direct access and OpenRouter access to the same model, distinct models from one creator, and unresolved identities.
- **Depends on:** no implementation slice.
- **Criteria:** design contracts for 10–12; resolve open question 8.
- **Effort:** S

### 2. Runtime identity, execution and persisted records

- **Outcome:** implement profile parsing/compatibility, adapter invocation mapping, identity/route snapshots, event readers and migrations as required. Existing supported execution paths remain usable under the documented compatibility policy.
- **Depends on:** slice 1.
- **Criteria:** 10, 12 and relevant portions of 9. Verify profile compatibility, route-specific invocation and historical record handling.
- **Effort:** M

### 3. Independence and diagnostics

- **Outcome:** route by canonical model identity and creator; expose identity and access route in diagnostics. Preserve same-profile exclusions and handle unresolved identities according to the contract.
- **Depends on:** slice 2.
- **Criteria:** 11 and relevant portions of 12. Tests show that the same model through direct access and OpenRouter satisfies neither `different_model` nor `different_vendor`, that distinct models from one creator can satisfy only the former, and that historical comparisons remain stable after catalog updates.
- **Effort:** M

### 4. Known-workers schema, seed data and packaging

- **Outcome:** validated read-only data representing canonical models, creators and execution routes, with provenance and unsupported-model markers. Establish a small representative seed spanning harness, direct API and intermediary access before broad research population.
- **Depends on:** slice 1 for schema; slices 2–3 before using the data to create profiles.
- **Criteria:** data and packaging portions of 2, 9 and 10. Check route mappings, supported adapters and identity consistency.
- **Effort:** M

### 5. Maintainer researcher and broad coverage

- **Outcome:** separately invoked research utility proposes repository updates with attributable evidence, broad provider and model-category coverage, and explicit coverage gaps. Research-only dependencies and tooling stay outside runtime installations.
- **Depends on:** slice 4. Can proceed independently of machine onboarding once the data contract is stable.
- **Criteria:** 1, 2 and relevant portions of 9. Check the built installation artifact and validate researcher output.
- **Effort:** M

### 6. Machine resources and profile generation

- **Outcome:** an explicit resource-manager interface combines discovery and persistent owner declarations, resolves secret references and generates route-aware profiles with verification provenance. Owner-created profiles and naming collisions are preserved.
- **Depends on:** slices 2–4.
- **Criteria:** 3, 5, 8, 10 and relevant portions of 9. Verify direct and intermediary resources produce the same canonical identity for the same model without sharing credentials or invocation identifiers.
- **Effort:** M

### 7. Protected refresh and repeat runs

- **Outcome:** generated ownership/hash tracking, bounded metadata refreshes, owner-edit preservation and defined partial-failure/retirement behavior. Repeat runs are safe; runtime upgrades do not add models.
- **Depends on:** slice 6.
- **Criteria:** 6 and relevant portions of 9. Check unchanged reruns, edited profiles, metadata updates and newly listed models that remain absent until an explicit manager run.
- **Effort:** M

### 8. Director onboarding and readiness confirmation

- **Outcome:** the Director offers machine setup when needed, persists answers across projects and invokes the manager with owner authorization. `init` and `doctor` confirm readiness and explain missing resources.
- **Depends on:** slices 6–7; does not require exhaustive research coverage from slice 5.
- **Criteria:** 4, 7 and relevant portions of 9. Check onboarding across two projects, completed setup with no usable workers, and healthy diagnostics.
- **Effort:** M

New execution adapters for additional modalities, project-specific exceptions, worker cost data and price-based routing remain outside these slices. Broad research can describe unsupported autonomous job categories without making them dispatch eligible.

## Log

- Revised after owner discussion: separate repository research from installed machine resource management; include owner-declared resources such as OpenRouter; make onboarding and profiles machine-wide; retain existing budgeting; allow bounded metadata refreshes while requiring an explicit manager run to add newly available models. Keep research tooling in the source repository and exclude it from normal installations without introducing repository access restrictions.

- Extended after owner discussion: separate canonical model identity and creator from access provider and invocation identifiers throughout the runtime, including independence and historical records. Split implementation into eight dependent slices so identity/compatibility foundations precede resource generation and onboarding.

### 1. Identity and compatibility contract

- **Commit:** 2026-11-worker-setup: Identity and compatibility contract
- **Summary:** The owner answered the eight open questions (2026-11-06); recorded as decisions 0074–0082 and listed in `docs/README.md`. The change is `in-progress`; criterion 3 now names `~/.baton/workers/` (0079). Design text for each part lands with the slice that implements it. No code; the docs tests cover the new links.
- **Review:** clean
- **Accepted:** yes, 2026-11-06, the owner's answers: strict unknown identity, unverified-but-flagged eligibility, "New directory ~/.baton/workers; one yaml file per worker profile. Owner edited files are untouched.", and for resources.yaml an explicit resource kind so future kinds can drop in; the rest concurred.

### 2. Runtime identity, execution and persisted records

- **Commit:** 2026-11-worker-setup: Runtime identity, execution and persisted records
- **Summary:** `WorkerProfile` gains `creator` (required; `vendor` read as its legacy alias, both differing is a load error), `model_id` (canonical, `<creator>/<name>`, must start with the creator), `provider` and `resource`; `canonical_model()` gives `human/<person>` for `manual` profiles. `model` stays the invocation identifier the adapters pass on, so execution is unchanged. `routing.identity_record` writes the identity-and-route snapshot into `worker_selected` and `sme_requested` (still writing `vendor` and `model`); `identity_from_record` reads older events as creator = vendor, model identity unknown. `profile_sha256` keeps the key name `vendor`, so existing profile hashes are unchanged. Independence still compares as before; slice 3 changes it. Tests: alias, conflict and `model_id` errors; direct and OpenRouter profiles sharing one identity; the pre-change hash pinned; the recorded snapshot; legacy event reading; the expert snapshot.
- **Review:** clean
- **Accepted:** pending owner review

### 3. Independence and diagnostics

- **Commit:** 2026-11-worker-setup: Independence and diagnostics
- **Summary:** `routing.same_at` follows 0076: `different_vendor` compares creators, `different_model` compares canonical identities, and unknown is never proof of independence (no fallback to invocation strings); known, differing creators are different models. `independence_reason` names the recorded worker's creator and model and, when an identity is unknown, the fixes (`model_id` or the §9.3 waiver). Eligibility (`routing.route_summary`), SME eligibility and `doctor`'s profile report show creator, model identity and provider; CLI eligibility lines read `adapter, creator, model_id via provider`. Tests: the same model directly and through OpenRouter satisfies neither level; two models of one creator satisfy only `different_model`; legacy same-creator profiles are not independent and the reason says how to fix it; people are different models; a routed run excludes the OpenRouter route and keeps excluding it after this machine's profiles change.
- **Review:** clean
- **Accepted:** pending owner review

### 4. Known-workers schema, seed data and packaging

- **Commit:** 2026-11-worker-setup: Known-workers schema, seed data and packaging
- **Summary:** `src/baton/known_workers.py` defines and validates `baton-known-workers/1`: models, providers, routes and `machine_dependent`, with the checks in §6.4 (vocabulary, tiers, adapters for supported routes, model and provider references, creator prefixes, mutable aliases needing a creator, machine-dependent capabilities absent, provenance, duplicates). Seed `defaults/known-workers.yaml`: Claude Opus 5.5 and Sonnet 5.5 (direct API), Opus 5.5 through OpenRouter (same `model_id`, its own invocation), and the Claude Code and Codex harnesses on their default models (aliases, no `model_id`). The IDs and context sizes were checked on 2026-11-06 against platform.claude.com's models overview and OpenRouter's model page (which gives no context length); LiteLLM 1.106.6 lists the `openrouter` provider. No route is live-verified. Capabilities and tiers in the seed are judgment, as the file says. Amended 0082: the machine-dependent list lives in this data, because published vocabularies are never edited (§5.6). Tests: the seed validates and spans harness, direct and intermediary access; the wheel config ships `defaults/` and nothing from `tools/`; 16 rejection cases; an unsupported route for a model the runtime cannot run is valid.
- **Review:** clean
- **Accepted:** pending owner review

### 5. Maintainer researcher and broad coverage

- **Commit:** 2026-11-worker-setup: Maintainer researcher and broad coverage
- **Summary:** The owner chose (0083) that the researcher is one Baton dispatch through a profile the maintainer names. `tools/worker-research/` holds `research.py`, a one-step `worker-research` recipe (the prompt sets the coverage scope, the identity and route rules, and forbids touching `verified`; the report schema requires inclusion criteria, providers and categories covered, coverage gaps, and each change with its sources) and a README. The script runs the recipe in a scratch project, validates the proposal and refuses one that touches `verified`; a valid one replaces `defaults/known-workers.yaml` for `git diff` review, with the report under `reports/`. Broad coverage itself comes from the first real research run, which needs a maintainer and a web-capable profile; it was not run here. Tests: a fake command-adapter worker; a valid proposal is written with its report; an invalid one, and one that claims a live check, leave the file alone and are saved as refused; the recipe loads; a real offline `uv build --wheel` ships `known-workers.yaml` and nothing from `tools/` (skipped where it cannot build offline).
- **Review:** clean
- **Accepted:** pending owner review

### 6. Machine resources and profile generation

- **Commit:** 2026-11-worker-setup: Machine resources and profile generation
- **Summary:** `src/baton/resources.py` is the worker resource manager. `~/.baton/resources.yaml` (`baton-resources/1`) holds declarations, each with a required `kind` (`worker` so far), credentials only as `secret:<name>`, optional `models` allowlist, `base_url`, and machine-dependent capabilities only; setup state is kept per kind. Discovery finds each harness CLI (minimal PATH, `nvm`, `~/.local/bin`) and asks its auth status (no model call). `setup` plans profiles from supported routes, writes new ones to `~/.baton/workers/<name>.yaml` with the `generated` marker (availability `detected` or `declared`, content hash), skips owner-held names, live-checks only what `--verify`/`--verify-all` names (a failing new profile is not written), and records completion. `status` changes nothing. `declare` adds, changes or removes a resource, or records "nothing more". Profiles now load from `workers/`, then `workers.yaml`, then `.baton/workers.local.yaml`; the marker is not part of the profile hash. Known-workers providers gained `api_key_env` (LiteLLM 1.106.6 reads `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY`) and `env_deny`. CLI `baton workers status|setup|declare` needs no project; engine calls and MCP tools `workers_status|setup|declare`. A dry run in a scratch home on this machine found Claude Code (under `~/.local/bin`, which is why that directory is searched) and Codex logged in and generated both, and an OpenRouter declaration produced a profile with Opus 5.5's `model_id`. Tests: detected and missing harnesses, not logged in, direct and OpenRouter sharing identity but not credentials or invocations, the allowlist, literal credential and non-machine-dependent capability refused, explicit kinds, declared `loopback_network`, owner profiles never touched, verification only when asked and a failed new profile not written, generated profiles loaded and eligible unverified with `workers.yaml` winning, the hash without the marker, machine-wide setup state, CLI declare without a project. The MCP tool list test now includes the three tools.
- **Review:** clean
- **Accepted:** pending owner review
