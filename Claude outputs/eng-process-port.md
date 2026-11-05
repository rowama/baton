# Porting eng-process to a Baton Recipe

> **Status:** recipe `eng-process@1` written and validated (`examples/recipes/eng-process/`); crosswalk drafted; port
> decisions D1-D10 and Baton gaps G1-G9 below await the owner. Written against Baton at `55ebb8a` (Phase 7 complete)
> and eng-process kit **v2.5.9**, with `mmbridge` as the adoption test case.
>
> This is the separate guide the build guide promises in §11.3 ("A crosswalk for the owner's `eng-process` is a
> separate guide"). It is the instruction set for whoever finishes the port: read it whole, together with the build
> guide, before changing the recipe.

---

## 1. Goal and principle

Move the owner's projects from eng-process to Baton without losing anything that worked, and drop what Baton makes
unnecessary. The test for every item is the build guide's §1.1 principle 2: friction must pay for itself.

The kit already behaves like a hand-built Baton: files as protocol, approval checkpoints, independent review, headless
runners with wake hooks, PID markers and timeouts. Most of the kit's **machinery** is replaced by the Baton runtime;
the kit's **process** (phases, gates, prompts, templates, lessons) becomes the recipe.

| Kit layer | Goes to |
|---|---|
| Phases, skills' steps and exit criteria, templates, prompts | The recipe (`examples/recipes/eng-process/`) |
| Checkpoints CP-A … CP-P | Recipe gates (human, review, findings), plus the implicit triage approval |
| `PROJECT_STATE.md`, Approval log, `pending_approvals`, handoffs, `eng-resume`/`eng-handoff` | Baton event log, records, `status`/`explain`/`board`, leases, `resume` |
| `eng-check`, `eng-status`, `eng-new`, `eng-init` | `baton check`, `status`/`board`, packets, `baton init`/`vendor` |
| `eng-run`, `runners.toml`, hooks, `.running.md`, timeouts, wake pair | Dispatch, worker profiles, preferences, supervisor, completion hooks, effort bands, classification |
| Ulrik (platform admin) | Platform SME, `contacts.platform`, `on_platform_failure` hook, platform incidents |
| Owner-update shape (L-007/8/9/10) | `.baton/communication.md` (Baton's default already is this shape, §13.6) |
| `process-feedback.md`, design adoption, retro, lessons | `feedback` events, skip surfacing, process SME, `.baton/process/lessons.md`, the `retro` step |

---

## 2. What is delivered

| Path | What |
|---|---|
| `examples/recipes/eng-process/recipe.yaml` | The recipe: 3 levels, 10 top-level steps, the `slices` group |
| `examples/recipes/eng-process/schemas/*.json` | Run inputs and every step's output contract |
| `examples/recipes/eng-process/prompts/*.md` | One prompt per step, carrying the kit skill's steps and exit criteria |
| `examples/recipes/eng-process/static/*.md` | Kit templates (design doc, research, architecture, ADR, plan, verification report, retro, DoD), sizing table, review rubrics; made vendor- and owner-neutral |
| `examples/recipes/eng-process/crosswalks/eng-process-2.5.yaml` | Draft crosswalk for adopting kit projects (format pending Phase 11) |
| `tests/test_recipe_eng_process.py` | Loads with zero issues; each size runs the kit's path; checkpoints per size; plan review is the only blocking review; WIP 1; locked specs protected |
| this file | The port guide |

All files are new; nothing existing is modified, so this merges cleanly with any phase in progress.

`baton plan examples/recipes/eng-process` prints the per-size table. Summary:

| Step | small | medium | large | Human gate (kit checkpoint) | Other gates |
|---|---|---|---|---|---|
| `triage` | ✔ | ✔ | ✔ | implicit triage approval above small | schema |
| `discover` | | ✔ | ✔ | CP-A Product | schema |
| `scope` | | | ✔ | CP-A Scope | schema |
| `research` | | ✔ | ✔ | CP-R (large only) | schema |
| `architecture` | | | ✔ | CP-B | schema; review (advisory, different vendor) |
| `plan` | | ✔ | ✔ | CP-C | schema; **review blocking on critical/high, different vendor** |
| `slices` (per slice, WIP 1, ≤3 iterations) | once | ✔ | ✔ | | |
| ↳ `implement` | ✔ | ✔ | ✔ | | schema; script (test command); protected specs (warn) |
| ↳ `code_review` | | ✔ | ✔ | | findings (advisory) |
| ↳ `verify_slice` | | ✔ | ✔ | | findings blocking on critical/high |
| ↳ `accept` (owner) | | ✔ | ✔ | CP-S (as owner findings) | findings blocking on critical/high |
| `verify` | ✔ | ✔ | ✔ | CP-D | schema; script |
| `ship` | ✔ | ✔ | ✔ | CP-P (owner merges/tags) | schema; script |
| `retro` | | ✔ | ✔ | approve process changes and lessons | schema |

---

## 3. When the recipe can actually run

The recipe **loads and plans today** because the recipe format (Phase 1) already covers groups, reviews, findings,
complexity levels, protection and publishing. It **runs** only as the layers it uses are built:

| Needed for | Build phase (§16) |
|---|---|
| Any run: dispatch, intake, schema/script/human gates, async workers | 1–7 (done) |
| `slices` expansion, iterations, `previous_iteration.findings`, `steps.slices.outputs` | **8** (in progress) |
| review and findings gates, dispositions, waivers, `protect`, independence | 9 |
| several work items in one repo (an increment plus a small fix), `revise` | 10 |
| skipping steps by triage level, `retriage`, adoption with the crosswalk | 11 |
| platform SME, process feedback and lessons | 12 |
| publishing design/plan/research/verification docs to project paths, drift | 13 |
| director skill, communication contract, action permissions (push) | 14 |

**First real run: after Phase 13.** Phases 8–11 can be exercised earlier with the fake adapter on this recipe; it is a
good second fixture next to `software-feature` because it uses every gate type, `foreach_if_source_skipped: once`,
a two-step `repeat_until`, and complexity skips inside a group.

**Adoption of mmbridge: after Phase 11 and 13** (crosswalk + publishing), ideally after 14.

---

## 4. Concept crosswalk (kit → Baton)

### 4.1 Phases and checkpoints

| Kit | Recipe | Notes |
|---|---|---|
| §2 triage + sizing table | `triage` + `static/sizing.md`; levels `small/medium/large` | Output schema enforces the level enum (§5.5). |
| §2 readiness check | Not a step | Baton state cannot be "at a later phase" without its predecessors; adoption seeding (§11.4) replaces it. |
| 1 Discover, CP-A | `discover` | Interview via `blocked` + `questions_for_human` (D8). |
| 2 Scope ("part of CP-A for L") | `scope`, own human gate | D1. |
| 3 Research, CP-R (L; optional M) | `research`, human gate `applies_to: [large]` | `workspace: read`; the runtime proves the tree is unchanged. |
| 4 Architecture, CP-B, ADRs | `architecture`, `workspace: write` | ADR files are written and committed by the worker (G4). |
| 5 Plan, mandatory plan review, CP-C | `plan` with a blocking `review` gate | The kit's only gating review stays the only blocking review. |
| 6 Implement-slice, WIP 1, CP-S each | `slices` group, `concurrency: 1` | `foreach` over `plan.output.slices`; small runs once with triage's slice card. |
| slice-diff cross-model review (advisory) | `code_review`, advisory findings | Skipped for small, as in the kit. |
| eng-verify per slice before CP-S | `verify_slice` | Folds open high review findings into its own findings, which drive the loop. |
| CP-S | `accept` (owner, `human_judgment`) | D3. |
| 7 Verify, CP-D | `verify` | Requires `loopback_network` (L-011). |
| 8 Ship, CP-P | `ship` | Worker does not push (D7). |
| 9 Reflect | `retro` | Medium and large, as in the kit. |
| §4a back up to an earlier phase | `revise(run, step, reason)` / `retriage` | Blameless reason recorded; only that run is affected. |
| Design change after CP-A (sha256 in the log) | Drift detection + `ingest_revision` (§10.5) | Automatic; no hash to paste. |
| Grandfathered plan review waiver | `waive(run, plan, review, reason)` (§9.3) | |
| `accepted-risk` only with owner approval; `rejected` needs evidence | §9.2 dispositions | Same rules, enforced by the runtime. |
| Spec lock (`eng-spec lock`, CP-C speclock row) | CP-C approval + `protect` on `implement` (§9.4: approval records the protected hash set) | DSL interface: G3. |

### 4.2 State and session machinery

| Kit | Baton |
|---|---|
| `PROJECT_STATE.md` (phase, active slice, next action, blockers) | `baton status` / `explain` / `board` from the event log |
| Approval log, `pending_approvals`, log/status cross-check | `human_decision` events (owner's words verbatim) + gate states; nothing to keep in sync |
| Handoffs, `eng-resume`, `eng-handoff`, context hygiene (§7) | Packets: the runtime assembles each step's context; `resume` on any machine; no handoff to write |
| One phase per session | One step per dispatch, by construction |
| `owner_agent`, L-012 (one writer of shared state) | Leases (§10.2) and the per-run lock |
| Latest artifacts list, prior increments | Run records and summaries; `board` lists only live runs |
| Front matter `id/type/phase/status/...` | Dropped from published docs (D6); status lives in Baton |
| `eng-check` structural checks | `baton check`: hash chains, CAS, lockfile, neutrality, secrets, impossible states |
| `eng-new <type>` | Packets carry the template as an input; publishing names the file |
| `eng-init`, vendoring, `eng upgrade` | `baton init`, `vendor`, `upgrade`; recipe pinned in `baton.lock` |
| `TODOS.md` | Stays a project file; `scope` and `verify` output TODO lines for it |
| Owner inbox (`eng-inbox`), review-notes scratch file | Stay outside Baton (D10) |

### 4.3 Running workers

| Kit | Baton |
|---|---|
| `eng-run <role>`; roles implement / plan-review / code-review | `baton dispatch` for every step; reviews are gate dispatches |
| `runners.toml [roles]` (implement=claude, reviews=codex) | Machine profiles + `.baton/preferences.yaml` `prefer.by_step` |
| `implement_args`, `--permission-mode bypassPermissions`, `--sandbox` | Profile `args.write/read/none`; adapter presets already use these defaults (§6.3) |
| nvm PATH auto-prepend, `[env]` tables | Profile `path.search: [nvm]`, `env_allow`/`env_deny` (§6.2) |
| Refuse self-review unless `--allow-self-review` | `independence` levels; self-review only with a waiver |
| Run log in `thoughts/shared/runs/` | Step records under `.baton/runs/`; raw logs in `~/.baton/logs/` |
| `.running.md` PID marker, liveness classification | Running markers + reconciliation table (§8.7) |
| Wake pair: `[hooks] *_on_complete` + S/M/L timeout 45m/2h/4h | Completion hooks + effort bands with the same defaults (§18 #9) |
| "stay attached" default (L-006) | `dispatch --wait` / `wait`; detaching without a hook prints a warning |
| Platform failures to Ulrik with what failed / error / tried / machine | Classification `platform` → incident → `on_platform_failure` → platform SME (§8.8, §12.3) |
| Gate preflight under the runner's permission mode (L-001) | `baton doctor` gate preflight (§13.4) |
| `push_permission: ask/standing`, docs-only always | `permissions.push: {docs_only: allow, after_verified: allow, other: ask}` |

### 4.4 Learning loop

| Kit (§12) | Baton |
|---|---|
| `process-feedback.md` friction log | `feedback(kind, text)` events; workers' `process_feedback` |
| Design adoption, informed-owner skips, redesign flag after two skips | `step_skip_recorded` + review/process statistics; safety skips surfaced at once (§12.4) |
| Review hit-rate | Runtime review statistics per qualified step id (§9.2) |
| Predictions on ADRs and retros, scored later | Kept in the ADR and retro templates; `retro` scores them |
| Kit lessons (hypothesis → confirmed), owner approves | Project lessons in `.baton/process/lessons.md`; recipe changes as process proposals and new recipe versions (§12.2, §12.4) |
| Research provenance, staleness diff | `research` records `git_commit`; publishing and drift cover the rest |

---

## 5. The kit's lessons (L-001 … L-013)

| Lesson | Where it lives now |
|---|---|
| L-001 preflight gate commands under the runner's mode | `baton doctor` gate preflight (Phase 6, built) |
| L-002 trunk + tag may replace PR at CP-P | `ship` output `release_ref: tag`; CP-P prompt says "merge or tag" |
| L-003 injected clock, no sleep waits | `static/definition-of-done.md`; `implement` prompt |
| L-004 docs-only commits push without asking | `permissions.push.docs_only: allow` with `docs_only_globs` |
| L-005 start the plan review without asking | Director skill: "starting work the process already calls for is not a question" |
| L-006 stay attached unless a hook is configured | Supervisor + hooks; no-hook warning (Phase 7, built) |
| L-007 Action-for-owner shape, no shell-valid placeholders, first-mention detail | `.baton/communication.md` default (§13.6) |
| L-008 risk mitigation is a decision | `risks_needing_decision` in discover, architecture and plan outputs; communication contract |
| L-009 CP-S lists runnable-now steps only | `verify_slice` and `verify` prompts (`ready:`/`blocked:`); communication contract |
| L-010 Before → After for reversed defaults | `verify_slice` prompt; DoD; communication contract |
| L-011 sandbox without loopback = partial coverage | `coverage.complete: false` (§9.2); `verify` requires `loopback_network` |
| L-012 one writer of shared state | Leases and run locks; no shared state file exists |
| L-013 walking skeleton | `plan` prompt and plan-review rubric |

Kit lessons stay `hypothesis` in the kit. When the owner approves the port, copy L-001…L-013 into the recipe's
README-level history (or a future `static/lessons.md`) with their confirmation counts, so the process SME has them.

---

## 6. Port decisions for the owner (D1–D10)

Each was decided in the draft as stated; the alternative is one edit away. **Please confirm or change each.**

| # | Decision in the draft | Why | Alternative |
|---|---|---|---|
| D1 | `scope` has its own human gate (large) instead of folding into CP-A | Baton gates belong to one step; mmbridge already logs "CP-A (scope)" as a separate row | Drop the scope gate and approve scope at CP-B |
| D2 | Triage is approved by the owner for medium and large (implicit gate, §18 #8) | Runtime rule; kit only asked for large or risky small | A recipe-level `triage_approval` option (runtime change) |
| D3 | CP-S is an `accept` step done by the owner, who submits findings (empty = accepted; `high` = send it back) | A rejected human gate only retries its own step; findings send the slice back to `implement` with the owner's issues in the packet | Human gate on `verify_slice` (rejection re-verifies instead of re-implementing) |
| D4 | `code_review` and the plan review require a **different vendor** | Kit intent is cross-model review (implementer and reviewer from different vendors) | `different_model` or `different_profile` |
| D5 | `verify_slice` must be a **different profile** from `implement` | Kit: the verifier is not the implementer | `different_vendor` |
| D6 | Published docs carry no kit front matter | Status and approvals are Baton's; duplicates drift | Keep front matter as read-only provenance (the prompt adds it) |
| D7 | `ship` never pushes; the Director pushes within `permissions` | Workers must not bypass action permissions (§13.7) | A `push` capability for workers (runtime change) |
| D8 | Discover/plan interviews: worker returns `blocked` with questions; owner answers via `decide … retry --note` | No new mechanism | Route `discover` to a `manual` profile the owner drives with an agent, or SME handoff mode (§12.1) |
| D9 | `max_iterations: 3` for slices, `max_attempts: 3` everywhere | Kit: "after 3 failed fixes, stop" | Other limits |
| D10 | Owner inbox and review-notes stay plain project files outside Baton | Baton non-goal: no backlog or idea management (§1.3) | A tiny separate `inbox` recipe later |

---

## 7. Baton gaps the port surfaced (G1–G9)

These are places where the build guide does not yet say what happens. **G1–G3 touch Phase 8–9 work and are worth
deciding before those phases close.** None needs a new user-visible concept unless noted.

| # | Gap | Effect on the port | Options |
|---|---|---|---|
| **G1** | `publish.to` may use only `paths.*`, `run.*`, `project.*`; there is no instance variable | Per-slice reports and review findings cannot be published to their own files (they would collide); they stay in run records | (a) add `instance.id` / `item.<path>` to publish variables for steps inside a `foreach`; (b) accept records-only for per-slice documents (the draft) |
| **G2** | `repeat_until` names `verify_slice` and `accept`, which are **skipped at small**. The guide does not define whether a skipped step's gates count as passed in a condition | Small runs need the loop to end after one pass | (a) skipped steps satisfy `gates.passed` (consistent with "skipped satisfies `depends_on`", §8.1) — the draft assumes this; (b) loader rejects conditions over skippable steps (then the recipe needs another shape). **Phase 8 is the place to decide.** |
| **G3** | `protect` is file globs; the kit locks the DSL's **public interface** but not its private helpers or assertion bodies | Locking `dsl.py` would block legitimate changes | (a) protect specs + lock file only, review rubric checks the DSL (draft); (b) a protect mode with a check command (runtime change) |
| G4 | Artifacts are a fixed list; ADRs are a variable number of files | `architecture` is a `write` step that commits ADRs | Fine as is; or an artifact list declaration later |
| G5 | Owner findings for `accept` are JSON | Friction at every CP-S | `baton submit --findings` from plain lines (`high: <text>`), no new concept |
| G6 | Crosswalk format undefined | Draft format in `crosswalks/` | Define in Phase 11; update the draft |
| G7 | Runtime statistics (attempts, iterations, times, hit-rates) are not an input reference | `retro` reads `.baton/` files itself | Add `process.statistics` to the reference grammar (§5.2) |
| G8 | `read` steps that run tests may create untracked, non-ignored files (reports, caches) → `workspace_modified` escalation | `verify_slice`, `verify` | Projects ignore their test caches (document in `baton init`), or read steps exempt a configured glob list |
| G9 | No conditional gate (kit: confirm size for small work in a risk area) | Draft relies on the owner seeing `risk_area` at CP-D | Gate `applies_to` on an output predicate (runtime change; probably not worth it) |

---

## 8. Project setup under the recipe

### 8.1 `.baton/project.yaml` (non-secret, committed)

```yaml
paths:                                   # keep the kit's locations so existing docs stay put
  design: docs/design
  research: thoughts/shared/research
  architecture: docs/architecture
  plans: thoughts/shared/plans
  verification: thoughts/shared/verification
  retros: thoughts/shared/retros
project:
  test_command: "PASTE_PROJECT_TEST_COMMAND_HERE"     # from AGENTS.md Commands
  preflight: "PASTE_PROJECT_TEST_COMMAND_HERE --collect-only"
permissions:
  push: { docs_only: allow, after_verified: allow, other: ask }   # kit "standing"; use other: ask, after_verified: ask for "ask"
  tag: ask
  force_push: deny
  merge: deny
  deploy: deny
docs_only_globs: ["docs/**", "thoughts/**", "**/*.md", ".baton/runs/**", ".baton/platform/**", ".baton/process/**"]
effort: { bands: { S: 45m, M: 2h, L: 4h }, extend_once: true, default: M }
contacts: { owner: owner, platform: platform-admin }
sme:
  platform: { preferred_profiles: [PASTE_PLATFORM_ADMIN_PROFILE_HERE] }
hooks:
  on_complete: ""            # non-secret only; a wake URL with a secret goes in ~/.baton/hooks.yaml
```

Kit "docs-only" also listed templates, PROCESS, OWNER-GUIDE, AGENTS, LESSONS and skill wording; `**/*.md` covers them.

### 8.2 `.baton/preferences.yaml` (kit `runners.toml [roles]`)

```yaml
prefer:
  by_step:
    implement: [PASTE_IMPLEMENTER_PROFILE_HERE]        # kit implementer
    code_review: [PASTE_REVIEWER_PROFILE_HERE]         # kit cross_review runner
    verify_slice: [PASTE_PLANNER_PROFILE_HERE]         # kit planner verifies
    verify: [PASTE_PLANNER_PROFILE_HERE]
```

Profile names are machine-local (`~/.baton/workers.yaml`, §6.1); the recipe never names one. The plan review and
architecture review pick their reviewer through the gate's `reviewer_requires` and `independence`.

### 8.3 `.baton/communication.md`

Baton's default is already the kit's owner-update shape (L-007, L-008, L-009, L-010). Copy the kit's illustrative
"Wrong / Right" first-mention example from `templates/owner-update.md` into it if the owner wants that example kept.

---

## 9. Adopting a kit project (procedure; mmbridge first)

Do this on a branch, per the build guide's trial workflow (§14.3), once Phases 11 and 13 are done.

1. `git worktree add ../mmbridge-baton -b baton-trial` in mmbridge.
2. In the trial worktree: `baton init`, write `.baton/project.yaml` and `.baton/preferences.yaml` (§8), vendor the
   recipe (`baton vendor <baton>/examples/recipes/eng-process`), `baton doctor` until silent.
3. `baton adopt eng-process --crosswalk eng-process-2.5` → research (read-only) → triage per in-flight work item →
   **one** baseline decision (§11.5).
4. Expected baseline for mmbridge (from its state at kit v2.5.9, 2026-10-31):
   - **Finished increments** (MCP, v0.2.0; live bots, v0.3.0): history, not seeded.
   - **Increment B** (design `docs/design/2026-10-28-grok-webhook-multibot.md`): one run at `large`. Imported:
     `triage`, `discover` (CP-A), `scope` (CP-A scope, HOLD), `research` (CP-R), `architecture` (CP-B, ADR-0011,
     0013–0016), `plan` (CP-C with speclock `ee97d6ce…`; the plan review imported with its findings). Group expanded
     from the three slice cards: **B-s1 and B-s2 imported whole** (CP-S rows), **B-s3**: `implement`, `code_review`
     and `verify_slice` imported, `accept` **pending** (the open CP-S item becomes a pending owner decision).
   - **Small fix** `2026-10-30-http-wake-internal-hosts` (triaged small, CP-S approved): finished, history.
   - Proposed config: `push_permission: standing` → `after_verified: allow`; `runners.toml` roles → preferences;
     test command from AGENTS.md.
   - Known gaps: kit front matter left in old docs (harmless); handoffs and `PROJECT_STATE.md` retired, not deleted.
5. Continue B-s3's CP-S under Baton, then `verify`, `ship`, `retro`.
6. **Adopt** = merge the branch. **Abandon** = delete the branch and worktree; the kit is untouched on main.
7. After a successful increment under Baton, the owner decides whether to delete `.eng/`, `.claude/skills/eng-*`,
   `PROJECT_STATE.md` and handoffs (never part of adoption itself).

---

## 10. Remaining work, in order

1. **Owner:** decide D1–D10 and G1–G3 (G2 before Phase 8 closes).
2. **Phase 8 session:** add this recipe's `slices` group to the Phase 8 tests (fake adapter): small runs one instance
   from run inputs and ends after `implement` (G2); a `high` from `verify_slice` or `accept` starts iteration 2 whose
   `implement` packet carries it.
3. **Phase 9:** plan-review blocking, code review advisory, `protect` warn on specs.
4. **Phase 11:** turn `crosswalks/eng-process-2.5.yaml` into the real crosswalk format; build the adoption fixture
   from a trimmed copy of mmbridge's kit files (no source code needed).
5. **Phase 13:** publishing to the kit paths; drift on the design doc after CP-A.
6. **Build guide follow-ups** (after the phase in progress merges, to avoid conflicts): §5.7 mention this recipe as
   the owner's process recipe (not one of the three shipped examples, or add it); §11.3 link this guide.
7. Real run: one small fix and one medium increment on mmbridge's trial branch; then the retro step's lessons feed
   recipe version 2.

---

## 11. How this was verified

- `baton plan examples/recipes/eng-process`: loads with **0 errors, 0 warnings** (neutrality lint included).
- `tests/test_recipe_eng_process.py`: 7 tests (each size's step path, checkpoints per size, the one blocking review,
  WIP limit, protected specs).
- Full suite on the branch: all prior tests unchanged.
