---
id: 2026-11-worker-setup
title: "Worker profiles set themselves up from the harnesses already logged in on the machine"
status: proposed
level: standard
decisions: []               # 0062+ recorded once the owner answers the open questions below
touches: [design/workers.md, design/director-interface.md, design/adoption-and-framing.md, design/layouts.md, principles.md]   # design/runtime.md too if Q6 is accepted
---

# Worker profiles set themselves up from the harnesses already logged in on the machine

## Request

### Problem

Before any work can run, the owner must write `~/.baton/workers.yaml` by hand: one profile per model, each with adapter, vendor, model string, tier, capabilities, context size, auth mode, `env_deny` and PATH sources (§6.1). Almost all of it is well-known data. If a machine has `claude` and `codex` logged in, Baton can already tell (each harness adapter has `auth_status_argv` / `parse_auth_status`, used by `doctor`, §13.4). The models those CLIs offer and what they can do are documented by their vendors.

Baton ships nothing that turns this into profiles. Nothing writes `workers.yaml`; `project.py` only reads it. §11.6 says that right after `init` "what a machine still needs is a worker profile able to do the framing step", so the first thing a new owner meets is hand-writing YAML. That breaks principle 1 (invisible when healthy) and principle 2 (friction must pay for itself): the owner supplies nothing Baton couldn't know.

Routing a step to one model rather than another of the same vendor (e.g. a strong model for design, a cheaper one for summaries) also needs one profile per model (§6.3: a profile's `model` is passed as `--model`; with no `model`, the CLI picks). Today each of those is another hand-written profile.

### Acceptance criteria

1. On a machine with no `~/.baton/workers.yaml` and a logged-in `claude` and/or `codex`, setup writes one profile per model listed for that harness in the shipped known-workers file. The framing step then has an eligible worker, and the owner has edited no file.
2. A harness that is not installed, or not logged in, gets no profiles. Setup says so in one plain line, with the login command.
3. Setup never changes or removes a profile it did not write. Profiles it did write can be refreshed when the known-workers file changes; any profile the owner has edited is left alone.
4. After setup, `doctor` is silent (one line) on a healthy machine.
5. The known-workers file is validated by a test: every capability and tier is in the pinned vocabulary, every adapter exists, every model string carries the CLI version and date it was checked against (ground rule 1).
6. The director skill and §13.3 say how and when the Director offers setup, consistent with its rule against editing profiles without the owner's instruction.
7. `pytest` green.

### Open questions

Each has a suggested answer and its rationale. Each becomes a decision record (`status: proposed` until answered).

1. **Name of the shipped file.** "Catalog" already means the recipes shipped with the runtime (§2, §11.6).
   *Suggested:* `defaults/known-workers.yaml` ("known workers"), and no new concept in §2: it is data the runtime ships, like the recipe catalog and starter recipes. One sentence added to §2 says so.
   *Rationale:* avoids overloading "catalog"; keeps the concept budget flat.

2. **When setup runs and who approves.** The skill says "Never edit profiles … without the owner's instruction" (§13.3).
   *Suggested:* `doctor` reports a missing or empty machine profile file as one problem, `no_workers`, with a plain-language message naming what it found ("Claude Code and Codex are signed in on this computer") and one option, "Use them". The Director relays it once. On the owner's yes it calls `doctor --setup` (MCP: `doctor(setup=true)`), which writes the file. No new command; `init` stays per-project and does not touch the machine file.
   *Rationale:* `doctor` already owns machine readiness and already queries auth. One short owner yes keeps the skill rule honest. The alternative, writing silently when no file exists, is less friction but makes a billing-relevant choice without the owner.

3. **Model strings: exact ids or CLI aliases.**
   *Suggested:* exact model ids, each with `checked: {cli: "<name> <version>", date}`.
   *Rationale:* `worker_selected` records the model, and `different_model` independence compares declared `model` fields (§8.4). An alias that silently moves to a new model makes both records misleading. Cost: the file needs updating when vendors release models. Whether each CLI's `--model` accepts the exact ids is **[VERIFY]** against the installed versions.

4. **Which models setup writes.** I have not confirmed that every model a CLI offers is usable on every subscription plan; treat that as unknown.
   *Suggested:* for each candidate model, run `doctor`'s existing no-op round trip, and write only the profiles that succeed. A model that fails is listed in one line, not written.
   *Rationale:* the claim "capabilities must be true on this machine" (§6.1) extends naturally to "the model is usable on this login". Cost: one small call per model at setup, against the owner's quota.

5. **Machine-dependent capabilities.** Some capabilities depend on the machine or sandbox, not the model (e.g. `loopback_network`).
   *Suggested:* the known-workers file lists only model- and harness-intrinsic capabilities. Machine-dependent ones are added by setup only when a probe confirms them, or are left for the owner.
   *Rationale:* §6.1 forbids claiming what isn't true on this machine, and a wrong claim routes a step to a worker that will fail it.

6. **Default ordering among eligible profiles.** Tier is a minimum (§8.4 "sufficient tier"), so a `strong` profile is eligible for `standard` steps too. With several generated profiles, cheap steps will often land on the strongest model unless preferences say otherwise.
   *Suggested:* when `.baton/preferences.yaml` doesn't decide, order eligible profiles lowest sufficient tier first. Preferences still win.
   *Rationale:* gives sensible cost behaviour with no owner configuration. If you'd rather keep this separate, it can be its own change.

7. **Telling generated profiles from hand-written ones.**
   *Suggested:* generated profiles carry `generated: known-workers@<version>` plus a hash of their generated content. Setup refreshes a profile only when the marker is present and the content still matches the hash; otherwise it leaves the profile alone (criterion 3).
   *Rationale:* lets the known-workers file evolve without ever overwriting the owner's edits. Adds one optional profile field.

8. **API-key workers (`litellm_api`).**
   *Suggested:* out of scope. Setup covers harness CLI logins only. API profiles still need a secret the owner chooses to provide.
   *Rationale:* keys are billing decisions and secrets; detecting them from the environment would undercut isolation by construction (§1.4 #6).

9. **Vendor neutrality.** The known-workers file names vendors and models inside the runtime.
   *Suggested:* allowed. §0 rule 4 places vendors "only in worker profiles and adapters", and this file is profile data shipped beside the adapters. The `vendor_denylist` lint still applies to recipes only.
   *Rationale:* recipes stay model-neutral, which is what the rule protects.

## Design

Filled in after the owner answers the open questions. Expected doc edits:

### Doc edits

- `design/workers.md` §6.1: profiles may be generated; the `generated` marker (Q7). A new section, the next free number in the file, *Setup from known workers*: file format, detection via each adapter's auth status, probe (Q4), write and refresh rules.
- `design/director-interface.md` §13.1: `doctor(profile?, setup?)`. §13.3: the skill's profile rule gains "except setup the owner approved". §13.4: the `no_workers` problem and `--setup`.
- `design/adoption-and-framing.md` §11.6: after `init`, a machine without profiles is set up through `doctor`, not by hand.
- `design/layouts.md` §4.1: `defaults/known-workers.yaml`. §4.4: `workers.yaml` may be written by setup.
- `principles.md` §2: one sentence: worker setup adds no concept.
- `design/runtime.md` §8.4 (only if Q6 is accepted): default ordering.

### Decisions

- 0062 onward, one per open question above.

## Plan

### Known-workers file and its checks

- **Outcome:** `defaults/known-workers.yaml` ships, with entries for the `claude_code` and `codex` presets, each model string checked against the installed CLI.
- **Criteria:**
  - criterion 5
- **Effort:** S

### Setup writes profiles for logged-in harnesses

- **Outcome:** `doctor --setup` detects logged-in harnesses, probes their models (if Q4 is accepted) and writes the profiles, marked as generated.
- **Criteria:**
  - criteria 1, 2, 3 and 4
- **Effort:** M

### Director offers setup

- **Outcome:** `doctor` reports `no_workers` with its plain-language message and option. The skill and §13.3 tell the Director to relay it and run setup on the owner's yes.
- **Criteria:**
  - criterion 6
- **Effort:** S

### Default ordering by lowest sufficient tier (only if Q6 is accepted)

- **Outcome:** with no preference deciding, `eligible` lists the lowest sufficient tier first.
- **Criteria:**
  - a test with generated profiles of two tiers and a `standard` step
- **Effort:** S

## Log
