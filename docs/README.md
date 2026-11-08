# Baton docs

How the docs are laid out, and where every § lives. Section numbers (§) are stable: code, tests, skills and the README cite them, so a heading's number never changes, and a new section takes the next free number in its file. `tests/test_docs.py` checks that every § reference resolves through the index below and that relative links in `docs/` resolve.

## Map

| Path | Purpose | When to read |
|---|---|---|
| [principles.md](principles.md) | Ground rules (§0), principles, guarantees, non-goals and key design decisions (§1), the concept budget (§2) | Always |
| [design/](design/) | The design, one file per topic (§3–§15), plus the testing strategy and definition of done (§17, §19) | The files a change doc lists under `touches:`, and any § you follow from them |
| [decisions/](decisions/) | One record per owner decision (`NNNN-<slug>.md`: context, decision, date, status). `status: proposed` is an open decision: never decide it silently | The records a change doc lists under `decisions:`; any `proposed` record the work touches |
| [changes/](changes/) | One change doc per piece of work (`YYYY-MM-<slug>.md`), from [TEMPLATE.md](changes/TEMPLATE.md): request, design, plan and log. [REGISTER.md](changes/REGISTER.md) lists every change with its status | The register, to find work or a status; then the one you are working on |
| [history/build-phases.md](history/build-phases.md) | §16: the build order of Phases 1–17, frozen | When you need to know how something was first built |

The design files:

| File | Topic |
|---|---|
| [design/roles-and-topology.md](design/roles-and-topology.md) | §3 Roles and Topology |
| [design/layouts.md](design/layouts.md) | §4 Layouts |
| [design/recipes.md](design/recipes.md) | §5 Recipes |
| [design/workers.md](design/workers.md) | §6 Worker Profiles and Execution |
| [design/packets.md](design/packets.md) | §7 The Packet Protocol |
| [design/runtime.md](design/runtime.md) | §8 Runtime |
| [design/gates-and-reviews.md](design/gates-and-reviews.md) | §9 Gates and Reviews |
| [design/persistence.md](design/persistence.md) | §10 Persistence, Handoff and Deliverables |
| [design/adoption-and-framing.md](design/adoption-and-framing.md) | §11 Adoption and Triage of Existing Projects; Framing New Work |
| [design/experts.md](design/experts.md) | §12 Experts: Project, Platform and Process |
| [design/director-interface.md](design/director-interface.md) | §13 The Director Interface |
| [design/versioning.md](design/versioning.md) | §14 Versioning and Trying New Versions |
| [design/platform-and-security.md](design/platform-and-security.md) | §15 Cross-Platform and Security |
| [design/testing.md](design/testing.md) | §17 Testing Strategy, §19 Definition of Done |

## § index

| § | File | Section |
|---|---|---|
| §0 | [principles.md](principles.md) | Ground Rules for the Building Agent |
| §1 | [principles.md](principles.md) | What We Are Building, and the Principles That Bound It |
| §1.1 | [principles.md](principles.md) | Principles (every feature is judged against these) |
| §1.2 | [principles.md](principles.md) | Guarantees |
| §1.3 | [principles.md](principles.md) | Non-goals |
| §1.4 | [principles.md](principles.md) | Key design decisions |
| §2 | [principles.md](principles.md) | Concepts (the Concept Budget) |
| §2.1 | [principles.md](principles.md) | Core and layers |
| §3 | [design/roles-and-topology.md](design/roles-and-topology.md) | Roles and Topology |
| §4 | [design/layouts.md](design/layouts.md) | Layouts |
| §4.1 | [design/layouts.md](design/layouts.md) | Runtime repository (installed as a pinned tool) |
| §4.2 | [design/layouts.md](design/layouts.md) | Recipe package (shareable, model-neutral) |
| §4.3 | [design/layouts.md](design/layouts.md) | Project (what lives in the adopting repo) |
| §4.4 | [design/layouts.md](design/layouts.md) | Machine-local (never in any repo) |
| §5 | [design/recipes.md](design/recipes.md) | Recipes |
| §5.1 | [design/recipes.md](design/recipes.md) | Example `recipe.yaml` |
| §5.2 | [design/recipes.md](design/recipes.md) | Input references (closed grammar) |
| §5.3 | [design/recipes.md](design/recipes.md) | Load-time validation and neutrality lint |
| §5.4 | [design/recipes.md](design/recipes.md) | Groups (sub-processes) |
| §5.5 | [design/recipes.md](design/recipes.md) | Complexity levels and triage |
| §5.6 | [design/recipes.md](design/recipes.md) | Capability vocabulary (`baton-capabilities/1`) |
| §5.7 | [design/recipes.md](design/recipes.md) | Shipped example recipes |
| §5.8 | [design/recipes.md](design/recipes.md) | Identifiers |
| §6 | [design/workers.md](design/workers.md) | Worker Profiles and Execution |
| §6.1 | [design/workers.md](design/workers.md) | Profiles (`~/.baton/workers.yaml`, overridable by `.baton/workers.local.yaml`) |
| §6.2 | [design/workers.md](design/workers.md) | Environment and PATH |
| §6.3 | [design/workers.md](design/workers.md) | Adapters |
| §6.4 | [design/workers.md](design/workers.md) | Worker setup |
| §7 | [design/packets.md](design/packets.md) | The Packet Protocol |
| §7.1 | [design/packets.md](design/packets.md) | Packet (runtime → worker) |
| §7.2 | [design/packets.md](design/packets.md) | Result (worker → runtime) |
| §8 | [design/runtime.md](design/runtime.md) | Runtime |
| §8.1 | [design/runtime.md](design/runtime.md) | The state machine |
| §8.2 | [design/runtime.md](design/runtime.md) | Events (the single list) |
| §8.3 | [design/runtime.md](design/runtime.md) | Store |
| §8.4 | [design/runtime.md](design/runtime.md) | Routing and independence |
| §8.5 | [design/runtime.md](design/runtime.md) | Groups at runtime |
| §8.6 | [design/runtime.md](design/runtime.md) | Packet builder (the critical module) |
| §8.7 | [design/runtime.md](design/runtime.md) | Dispatch, supervision, completion and timeouts |
| §8.8 | [design/runtime.md](design/runtime.md) | Failure classification |
| §8.9 | [design/runtime.md](design/runtime.md) | Work items, concurrency and corrections |
| §8.10 | [design/runtime.md](design/runtime.md) | Intake |
| §9 | [design/gates-and-reviews.md](design/gates-and-reviews.md) | Gates and Reviews |
| §9.1 | [design/gates-and-reviews.md](design/gates-and-reviews.md) | Gate types |
| §9.2 | [design/gates-and-reviews.md](design/gates-and-reviews.md) | Findings and dispositions |
| §9.3 | [design/gates-and-reviews.md](design/gates-and-reviews.md) | Waivers |
| §9.4 | [design/gates-and-reviews.md](design/gates-and-reviews.md) | Protected files |
| §10 | [design/persistence.md](design/persistence.md) | Persistence, Handoff and Deliverables |
| §10.1 | [design/persistence.md](design/persistence.md) | Checkpoint commits |
| §10.2 | [design/persistence.md](design/persistence.md) | Leases |
| §10.3 | [design/persistence.md](design/persistence.md) | Resume |
| §10.4 | [design/persistence.md](design/persistence.md) | Publishing |
| §10.5 | [design/persistence.md](design/persistence.md) | Two copies and drift |
| §10.6 | [design/persistence.md](design/persistence.md) | Records and explain |
| §11 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | Adoption and Triage of Existing Projects; Framing New Work |
| §11.1 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | Flow |
| §11.2 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | Research |
| §11.3 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | Crosswalks |
| §11.4 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | Seeding |
| §11.5 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | The baseline |
| §11.6 | [design/adoption-and-framing.md](design/adoption-and-framing.md) | Framing new work |
| §12 | [design/experts.md](design/experts.md) | Experts: Project, Platform and Process |
| §12.1 | [design/experts.md](design/experts.md) | Consulting an expert |
| §12.2 | [design/experts.md](design/experts.md) | Isolation and promotion |
| §12.3 | [design/experts.md](design/experts.md) | The platform area |
| §12.4 | [design/experts.md](design/experts.md) | The process SME and process feedback |
| §13 | [design/director-interface.md](design/director-interface.md) | The Director Interface |
| §13.1 | [design/director-interface.md](design/director-interface.md) | The API (engine; one table) |
| §13.2 | [design/director-interface.md](design/director-interface.md) | CLI and MCP |
| §13.3 | [design/director-interface.md](design/director-interface.md) | Skills |
| §13.4 | [design/director-interface.md](design/director-interface.md) | `doctor` |
| §13.5 | [design/director-interface.md](design/director-interface.md) | `check` |
| §13.6 | [design/director-interface.md](design/director-interface.md) | Owner communication contract |
| §13.7 | [design/director-interface.md](design/director-interface.md) | Action permissions |
| §13.8 | [design/director-interface.md](design/director-interface.md) | The conversation layer |
| §14 | [design/versioning.md](design/versioning.md) | Versioning and Trying New Versions |
| §14.1 | [design/versioning.md](design/versioning.md) | What is versioned |
| §14.2 | [design/versioning.md](design/versioning.md) | Compatibility and migration |
| §14.3 | [design/versioning.md](design/versioning.md) | Trying a new version on a real project |
| §15 | [design/platform-and-security.md](design/platform-and-security.md) | Cross-Platform and Security |
| §15.1 | [design/platform-and-security.md](design/platform-and-security.md) | Cross-platform |
| §15.2 | [design/platform-and-security.md](design/platform-and-security.md) | Security |
| §15.3 | [design/platform-and-security.md](design/platform-and-security.md) | Future: guided process authoring (design implications now) |
| §16 | [history/build-phases.md](history/build-phases.md) | Build Order |
| §17 | [design/testing.md](design/testing.md) | Testing Strategy |
| §18 | [README.md](README.md) | Open Decisions (ask the owner before choosing) |
| §19 | [design/testing.md](design/testing.md) | Definition of Done |

## 18. Open Decisions

§18 of the build guide listed the decisions the owner had to make; each is now a decision record, numbered to match (§18 #N is record N). Suggested answers were given in brackets, and a `proposed` record's suggestion is assumed until the owner decides. New decisions take the next free number.

| § | Record | Status |
|---|---|---|
| §18 #1 | [0001 Inputs too large for an API worker are a hard error](decisions/0001-large-api-inputs.md) | accepted |
| §18 #2 | [0002 No eligible worker escalates the step, never fails the run](decisions/0002-no-eligible-worker.md) | accepted |
| §18 #3 | [0003 Independent top-level steps of one run may run in parallel](decisions/0003-parallel-top-level-steps.md) | accepted |
| §18 #4 | [0004 The runtime maintainer owns the capability vocabulary and classification rules](decisions/0004-vocabulary-maintenance.md) | accepted |
| §18 #5 | [0005 Leases last one hour, renewed on activity; takeover approval is skill-enforced](decisions/0005-lease-defaults.md) | accepted |
| §18 #6 | [0006 Checkpoint commits are on by default, to the current branch](decisions/0006-checkpoint-commits.md) | accepted |
| §18 #7 | [0007 Git LFS is optional, with a 5 MB threshold](decisions/0007-git-lfs.md) | accepted |
| §18 #8 | [0008 Triage auto-accepts at the lowest level and asks the owner above it](decisions/0008-triage-approval.md) | accepted |
| §18 #9 | [0009 Effort bands are 45 min / 2 h / 4 h, extended once](decisions/0009-effort-bands.md) | accepted |
| §18 #10 | [0010 Concurrent write steps share one workspace lock; worktree isolation deferred](decisions/0010-workspace-lock-only.md) | accepted |
| §18 #11 | [0011 Baton invokes no platform SME itself; on_platform_failure does](decisions/0011-platform-sme-invocation.md) | accepted |
| §18 #12 | [0012 Worker dispositions are provisional until an independent review confirms them](decisions/0012-worker-dispositions.md) | accepted |
| §18 #13 | [0013 Expert transcripts are kept in full, redacted](decisions/0013-sme-transcripts.md) | accepted |
| §18 #14 | [0014 Adoption research is limited to 10k files / 200 MB](decisions/0014-research-scope.md) | accepted |
| §18 #15 | [0015 The launcher installs with uv; runtimes read the current and previous format](decisions/0015-launcher-and-format-window.md) | accepted |
| §18 #16 | [0016 Optional OpenTelemetry export of events](decisions/0016-opentelemetry-export.md) | proposed |
| §18 #17 | [0017 Relay is the formal expert mode; handoff is a runtime-made prompt](decisions/0017-sme-handoff.md) | accepted |
| §18 #18 | [0018 Erroneous worker dispositions: mediation deferred](decisions/0018-erroneous-worker-dispositions.md) | deferred |
| §18 #19 | [0019 Phase 17 additions need no format version bump](decisions/0019-phase-17-format-versions.md) | accepted |
| §18 #20 | [0020 One communication style per project](decisions/0020-communication-style-scope.md) | accepted |
| §18 #21 | [0021 Decision labels: runtime defaults plus recipe gate labels](decisions/0021-decision-labels.md) | accepted |
| §18 #22 | [0022 fit-check stays standalone; framing proposes it](decisions/0022-framing-and-fit-check.md) | accepted |
| §18 #23 | [0023 A single framed part still needs the owner's selection](decisions/0023-framing-single-part.md) | accepted |
| §18 #24 | [0024 Partial answers are allowed with --partial](decisions/0024-partial-answers.md) | accepted |

Decisions recorded inline in the guide (0025–0052; each design doc links its record where the note was), then later ones:

| Record | Status |
|---|---|
| [0025 Deterministic machinery, human conversation](decisions/0025-deterministic-machinery-human-conversation.md) | accepted |
| [0026 A judge's failed blocking gate ends the iteration and keeps its result](decisions/0026-judges.md) | accepted |
| [0027 Rejecting a triage level retries triage](decisions/0027-triage-rejection-retries.md) | accepted |
| [0028 Re-triage reruns triage behind a human gate](decisions/0028-retriage.md) | accepted |
| [0029 fit-check's describe infers first and asks only what it cannot infer](decisions/0029-fit-check-infers-first.md) | accepted |
| [0030 software-feature's slice acceptance is a judge](decisions/0030-slice-acceptance-judge.md) | accepted |
| [0031 questions_for_human is structured](decisions/0031-structured-questions.md) | accepted |
| [0032 A stale step is never readied automatically](decisions/0032-stale-steps-not-auto-readied.md) | accepted |
| [0033 A busy workspace queues write dispatches](decisions/0033-workspace-queue.md) | accepted |
| [0034 revise inside groups is deferred](decisions/0034-revise-in-groups-deferred.md) | accepted |
| [0035 A disposition takes effect at the next evaluation](decisions/0035-dispositions-next-evaluation.md) | accepted |
| [0036 Waiver naming, recording and scope](decisions/0036-waivers.md) | accepted |
| [0037 A protected-path change in warn mode waits on the owner](decisions/0037-protected-warn-waits-on-owner.md) | accepted |
| [0038 Publishing: when, where and conflicts](decisions/0038-publishing.md) | accepted |
| [0039 Drift of published deliverables](decisions/0039-drift.md) | accepted |
| [0040 Adoption is an adoption run plus one baseline decision](decisions/0040-adoption-mechanics.md) | accepted |
| [0041 Crosswalk format baton-crosswalk/1](decisions/0041-crosswalk-format.md) | accepted |
| [0042 Framing vendors a catalog recipe on selection](decisions/0042-vendoring-on-selection.md) | accepted |
| [0043 init vendors the starter recipes](decisions/0043-starter-recipes-at-init.md) | accepted |
| [0044 Framing existing projects is deferred](decisions/0044-framing-mature-projects-deferred.md) | accepted |
| [0045 An SME is never a person; people are reached through a proxy](decisions/0045-sme-never-a-person.md) | accepted |
| [0046 Resolving a platform incident readies its step once](decisions/0046-platform-incident-one-retry.md) | accepted |
| [0047 A skipped blocking gate is surfaced to the owner immediately](decisions/0047-skipped-gate-surfacing.md) | accepted |
| [0048 MCP over stdio, and over loopback HTTP with a token](decisions/0048-mcp-transports.md) | accepted |
| [0049 Two owner communication styles ship: conversational and operator](decisions/0049-communication-styles.md) | accepted |
| [0050 Explicit push with categories; permission checks for Director actions](decisions/0050-action-permissions.md) | accepted |
| [0051 The launcher is the package's own entry point](decisions/0051-launcher-mechanics.md) | accepted |
| [0052 Format families, migrate, upgrade and step-id signatures](decisions/0052-format-window-migrate-upgrade.md) | accepted |
| [0053 Codex directs Baton through MCP, not shell commands](decisions/0053-codex-director-via-mcp.md) | accepted |
| [0054 What counts as a sandboxed Director](decisions/0054-sandbox-detection.md) | accepted |
| [0055 The Codex README section ships before the live check, marked unverified](decisions/0055-codex-readme-before-live-check.md) | accepted |
| [0056 Codex setup includes a config line so Baton's tools need no per-call approval](decisions/0056-codex-tool-approval.md) | accepted |
| [0057 BATON_OWNER_EXIT=0 makes owner-needed exit 0; the default stays 4](decisions/0057-owner-needed-exit-code-opt-out.md) | accepted |
| [0058 A Director with no wake path is warned, never refused](decisions/0058-detached-director-warned-not-refused.md) | accepted |
| [0059 The Director tells the owner before a dispatch it might not be woken for](decisions/0059-warn-owner-before-unwoken-dispatch.md) | accepted |
| [0060 No wake notice or warning when the work is a person's](decisions/0060-wake-notice-skips-manual-workers.md) | accepted |
| [0061 No wake path is a doctor warning; detect shows it only as a problem](decisions/0061-wake-warning-in-doctor-not-detect.md) | accepted |
| [0062 Framing's select keeps its mechanism; only its presentation is fixed](decisions/0062-framing-mechanism-kept-presentation-fixed.md) | accepted |
| [0063 Baton manages no backlog as a feature, but may write a backlog and notes as deliverables](decisions/0063-backlog-and-notes-are-deliverables.md) | accepted |
| [0064 Framing publishes its breakdown; unchosen parts can be started later](decisions/0064-framing-publishes-its-breakdown.md) | accepted |
| [0065 Owner notes: recorded verbatim, only when asked, in an opt-in notes file; never fed into a step](decisions/0065-owner-notes.md) | accepted |
| [0066 A part is started later with start --from-plan, from the framing run's record](decisions/0066-start-from-plan.md) | accepted |
| [0067 note(text): no tag, an append-only file, no confirm-back](decisions/0067-note-call.md) | accepted |
| [0068 The runtime renders framing's breakdown from the record; no new framing version](decisions/0068-breakdown-rendered-by-runtime.md) | accepted |
| [0069 Framing's breakdown is a process plan: it lists process starts, never orders or schedules them](decisions/0069-process-plan-lists-not-schedules.md) | accepted |
| [0070 The owner's answer to the notes-file offer is a project decision](decisions/0070-notes-offer-recorded-as-project-decision.md) | accepted |
| [0071 next is an optional option field; framing's options carry it first](decisions/0071-next-on-framing-options.md) | accepted |
| [0072 A process-plan conflict at --from-plan waits on the run it started](decisions/0072-plan-republish-conflict-on-started-run.md) | accepted |
| [0073 A process plan's goal slug is shortened by rule, never summarized](decisions/0073-goal-slug-shortened-not-summarized.md) | accepted |
| [0074 Worker research, machine resource management and project setup are separate](decisions/0074-worker-research-and-resources-separate.md) | accepted |
| [0075 Profiles separate a model's identity from the route used to reach it](decisions/0075-model-identity-separate-from-route.md) | accepted |
| [0076 An unknown model identity is never proof of independence](decisions/0076-unknown-identity-not-independent.md) | accepted |
| [0077 The resource manager is baton workers status, setup and declare](decisions/0077-workers-command.md) | accepted |
| [0078 Machine resources are declared in ~/.baton/resources.yaml, each with an explicit kind](decisions/0078-machine-resources-file.md) | accepted |
| [0079 Generated profiles live one per file in ~/.baton/workers/, owned by content hash](decisions/0079-generated-profiles-directory.md) | accepted |
| [0080 Known-workers data: models, providers and routes, with research and verification kept apart](decisions/0080-known-workers-format.md) | accepted |
| [0081 Live verification runs only on request; unverified generated profiles are eligible, flagged](decisions/0081-live-verification-on-request.md) | accepted |
| [0082 Machine-dependent capabilities need an owner declaration or a passing probe](decisions/0082-machine-dependent-capabilities.md) | accepted |
| [0083 The maintainer researcher is one Baton dispatch through a profile the maintainer names](decisions/0083-researcher-dispatches-through-a-profile.md) | accepted |
| [0084 Capabilities carry a state, likely, verified or absent, kept machine-wide outside profiles](decisions/0084-capability-states.md) | accepted |
| [0085 Tooling capabilities belong to the harness: researched tool maps, least privilege, verified by use](decisions/0085-harness-tool-maps.md) | accepted |
| [0086 capability_absent re-routes without spending an attempt; absent everywhere escalates at once](decisions/0086-capability-absent-reroutes.md) | accepted |
| [0087 structured_output is absent after three schema-gate failures in a row on one profile](decisions/0087-structured-output-by-schema-gate.md) | accepted |
| [0088 A researched capability needs a basis, not proof, and ships as likely](decisions/0088-capability-basis.md) | accepted |
| [0089 Research is refused when a harness's creator has a model with no pinned harness route and no stated gap](decisions/0089-harness-coverage-check.md) | accepted |
| [0090 Harness CLI flags are researched data, reviewed in the diff; drift goes to the platform SME](decisions/0090-harness-flags-are-researched-data.md) | accepted |
| [0091 The researcher gets tool maps, starting URLs and LiteLLM entries; model availability is verified by use](decisions/0091-researcher-inputs-and-model-listing.md) | accepted |
