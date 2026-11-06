---
id: 2026-11-zero-friction-setup
title: "Become a Baton director: setup with as little owner effort as possible"
status: proposed            # ON HOLD (owner, 2026-11-05): not to be designed further or implemented until the owner accepts it
level: major
decisions: []               # proposed records to create when this is picked up: see Design › Decisions
touches: [design/director-interface.md, design/layouts.md, design/workers.md, design/platform-and-security.md]   # §13.1, §13.3, §13.4, §4.1, §4.4, §6.1, §15; also README.md and a new BOOTSTRAP.md
---

# Become a Baton director: setup with as little owner effort as possible

> **On hold.** The owner wants to think about this further. Do not start Design or Plan work, and do not implement any part of it, until the owner sets `status: accepted`. Treat everything below as a starting point for that discussion, not as decided.

## Request

### Problem

Getting from "I have Baton" to "a Director is running my project" takes too many manual steps:
- install the launcher;
- create a project folder and run `baton init`;
- write `~/.baton/workers.yaml` by hand;
- connect the Director's harness (MCP registration, sandbox settings: see [2026-11-codex-director-sandbox](2026-11-codex-director-sandbox.md));
- set up hooks so a Director that ends its turn gets woken (see [2026-11-director-wake](2026-11-director-wake.md)).

An early decision accepted install friction when Baton generalizes what works. The owner now wants to push for the minimum. The first real project (pure-water vending) showed how much of that friction lands on the owner before any work starts.

**The owner's vision.**
- **10 stars:** open any AI chat and say "Become a Baton director". The AI finds the director skill and sets up a new or adopted project: where it lives, creating the folder, `init`, worker profiles, and hooks suited to the harness it runs in. It asks the owner's permission or help where needed, gives the owner exact instructions for anything it cannot do itself, and then starts the conversation about the work.
- **5 stars:** the owner connects Baton as a tool to their AI tool once, then says "Become a Baton director" and the rest of the 10-star version happens.

**Reality check** (discussed 2026-11-05). How close Baton can get depends on what the AI can do on the owner's machine, not on which AI it is:

| The AI has… | Examples | Reachable |
|---|---|---|
| A shell on the owner's machine | Claude Code, Codex CLI, Gemini CLI | Close to 10: it can install, create the folder, init and propose profiles; the owner approves; Codex needs one restart after connecting Baton as a tool |
| A bridge to the owner's machine from a cloud chat | A linked desktop chat app | Close to 10 for setup; waking it when work finishes still needs a hook, and most chat apps cannot be woken from outside |
| No access to the owner's machine | A plain web chat | Instructions only. Making it a real Director would need a hosted Baton, which the no-server principle rules out (§0, rule 3) |

Where Grok, Hermes and others land depends on their tool access, which is not yet researched.

### Acceptance criteria

To be settled with the owner. Candidates:
- From a fresh machine with only an agent harness that has a shell, "Become a Baton director: github.com/rowama/baton" leads to an initialized project with worker profiles and a running conversation about the work. The owner's only actions are one approval of a setup plan and any steps the plan says only the owner can do.
- `baton setup` is re-runnable: on a healthy machine and project it prints one line; after a partial setup it does only what is missing.
- Every step `setup` cannot do itself comes with exact instructions in plain language, and the setup plan marks which those are before anything runs.
- Worker profiles are proposed from what is actually installed and logged in on the machine, and are never written without the owner's confirmation. API keys are never written into a profile.
- An AI with no access to the owner's machine gives the owner the 5-star instructions, and does not pretend to set anything up.

### Open questions

- Is the 10-star target the agents with a shell, with everything else served by the 5-star path?
- One approval of a whole setup plan, or approval per step? The suggestion is one plan approval, with any step that changes something outside the project (installing software, the AI tool's own settings) listed explicitly in that plan.
- Where should projects live by default (e.g. `~/projects/<slug>`), and does the owner want to be asked every time?
- Should the bootstrap page live in this repo (`BOOTSTRAP.md`) or at a separate stable URL?
- Which harnesses get first-class profiles first?
- Does this reopen the early decision that accepted install friction, or refine it?

## Design

Starting points only, to be confirmed when the change is accepted.

### Doc edits

- `design/director-interface.md` §13.1: a `setup` call (`baton setup [--plan] [--approved --note "<owner's words>"]`).
- `design/director-interface.md` §13.3: the director skill gains a "Setting up" section. Run `baton setup --plan`, present the plan in the owner's terms, get one approval, run it, walk the owner through what is left, then start framing or adoption.
- `design/director-interface.md` §13.4: `doctor` and `setup` share their probes; harness identity is a hint, probes decide.
- `design/layouts.md` §4.1: `harnesses/*.yaml` shipped with the runtime. §4.4: what `setup` writes machine-locally.
- `design/workers.md` §6.1: profiles proposed from detected CLIs and their login state.
- `design/platform-and-security.md` §15: what setup may change outside the project, and only with approval.
- `README.md`: "Fastest start" up front. A new `BOOTSTRAP.md`: an agent-readable page that any AI able to fetch a web page can follow.

### Components

1. **Bootstrap page for agents** (`BOOTSTRAP.md`, public URL). It solves the chicken-and-egg problem: the AI has no skill until Baton is installed. It says: check what you can do on this machine; if you can run commands, install Baton and run `baton setup --plan`; if you cannot, give the owner these instructions. Then follow the director skill.
2. **`baton setup`.** One deterministic, re-runnable command.
   - It probes: can run commands; can write `~/.baton`; network; git; uv; harness CLIs present and logged in; sandboxed; will the Director still be attached when work finishes.
   - It produces a setup plan whose steps are each marked `auto`, `needs_approval` or `owner_must_do`, with exact instructions for the last kind.
   - It runs the approved steps and reports what is left. It combines today's `init`, `doctor` and profile writing.
3. **Harness profiles as data** (`harnesses/<name>.yaml`).
   - Each profile holds: how to recognize the harness, whether to connect over MCP or the shell, sandbox notes, wake options, and setup steps per operating system.
   - Unknown harnesses fall back to a generic profile.
   - They are maintained like the capability vocabulary and grow one harness at a time.
4. **Harness identity is a hint; probes decide.**
   - The Director says who it is (`--harness codex`), and `setup` cross-checks environment fingerprints. These are ambiguous: a Claude desktop session exposes `CLAUDE_CODE_*` variables because Claude Code runs underneath it.
   - Whenever identity and probes disagree, the probes win.
5. **Worker profiles detected, not hand-written.** `setup` finds installed agent CLIs (`claude`, `codex`, `gemini`, …), checks their login state, and proposes `workers.yaml` entries with capabilities from the harness profile. The owner confirms. API-key profiles are proposed only as stubs with `secret:` references.
6. **Project placement by conversation.** The Director proposes a folder, confirms it, and `setup` creates it, runs `init`, then hands over to framing (§11.6) or adoption (§11).
7. **Hooks where the harness supports them.** Wake hooks are set up only when the harness profile says the platform can be woken from outside and the owner provides what that needs. Otherwise the Director stays attached or tells the owner when to check back, as today.

### Decisions

Proposed records to create when this change is accepted:
- **Setup approval granularity:** one approval of the whole plan, with steps outside the project listed explicitly (suggested).
- **Harness identity as a hint:** probes decide; identity only chooses wording and harness-specific steps (suggested).
- **Detected worker profiles:** proposed, never written without confirmation; no secrets written (suggested).
- **Install friction:** whether this supersedes or refines the earlier decision that accepted setup friction.

### Limits

- Creating a webhook that wakes a chat only works where the platform can resume a conversation from outside and the owner provides credentials. Most cannot, as far as is known.
- Changes outside the project (installing software, editing the AI tool's own settings) always need the owner's approval. The minimum is one approval, not zero.
- A plain web chat cannot be a Director without a hosted Baton (out of scope).

## Plan

To be written after the owner accepts Request and Design (level `major`). Suggested first slice: `baton setup` with worker-profile detection. It is useful on its own, before the bootstrap page and harness profiles exist.

## Log

(empty)
