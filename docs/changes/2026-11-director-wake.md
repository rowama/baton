---
id: 2026-11-director-wake
title: "A detached Director notices when work finishes, or tells the owner first that it might not"
status: proposed
level: standard
decisions: ["0057", "0058", "0059"]   # exit-code opt-out; warn, never refuse; owner warned before an unwoken dispatch
touches: [design/runtime.md, design/director-interface.md]   # §8.7, §13.1, §13.3, §13.4; also the repo README.md
---

# A detached Director notices when work finishes, or tells the owner first that it might not

## Request

### Problem

From the bug eval [2026-11-04-director-wake-on-needs-human](../bug-evals/2026-11-04-director-wake-on-needs-human.md). A cloud chat agent directing over a remote shell ran `baton dispatch … --wait --json` as a background job and ended its turn. Twice the worker finished, Baton recorded the result and opened an owner decision, and the CLI exited 4. Nothing woke the Director: no completion hook was configured (`init` writes them empty), the harness's own job wake didn't arrive, and the harness showed exit 4 as `failed`. The owner waited about 47 minutes and then had to ask.

Baton's part (the bug eval's root cause A):
- **No warning under `--wait`.** `dispatch` warns that no hook is configured only without `--wait` (`src/baton/engine.py:2378`; the same at `:3484` for `ask_sme`), and in text mode only on stderr. A `--wait` run in a background job is exactly the detached case.
- **The warning's test is wrong.** `supervisor.hooks_configured` counts any hook, so a project with only `on_platform_failure` set gets no warning, yet `choose_hook` fires nothing for a step waiting on the owner. (Found while writing this doc; not in the bug eval.)
- **`doctor` is silent** about having no hooks at all.
- **Nothing says exit 4 is a success path.** The skill and README never say that exit 4 from `dispatch --wait` / `wait` means "finished, the owner is needed now". Harnesses that treat non-zero as failure mislabel it.
- **The skill assumes a hook exists.** It says "the completion hook or the next `board` brings you back" and never says what to do when no hook exists.
- **`BATON_HARNESS` is undocumented**, so the lease showed harness `cli` for a detached chat agent.

The owner's requirement (decision [0059](../decisions/0059-warn-owner-before-unwoken-dispatch.md)): "I don't need detached directors failing to notice when a worker finishes. ... As a fallback, I do need the director to let me know when it might not wake. It needs to issue that warning before it dispatches, so I will know to check back."

**Limits.** Baton cannot wake a Director without a channel: a completion hook, or a harness wake that works. This change makes sure a Director knows whether it has one *before* it dispatches. Without one, it stays attached, or it warns the owner first. The platform asks (bug eval P1–P4: wake on job completion whatever the exit code, an inbound wake URL) and the operator actions (O1–O4) are outside this repo.

### Acceptance criteria

1. **Wake path before dispatch.** `eligible` (and `sme-eligible`) report `wake {configured, hook?, notice?, expected?}`. `configured` is true only when a hook would fire for a step that ends waiting on the owner (`on_needs_human` or `on_complete`, project or machine level). When it is false, `notice` is a plain-language message for the owner. The message says the Director might not notice when the work finishes and gives how long the work may take, from the step's effort band, noting it can run over once when `extend_once` is on. Manual steps get no notice.
2. **Warnings without exceptions.** `dispatch` and `ask_sme` warn whenever `wake.configured` is false, with or without `--wait`. The warning goes in JSON `warnings` and to stderr in text mode. A project whose only hook is `on_platform_failure` counts as having no wake path.
3. **`doctor`** warns when no hook would wake a Director. The warning becomes a problem when an active run's lease names a harness other than `cli`.
4. **Exit codes.** With `BATON_OWNER_EXIT=0`, every command that would exit 4 for a needed owner decision exits 0, and `needs_owner: true` stays in the JSON. Without it, nothing changes. The exit codes are documented as a table in §13.1, the README and the skill, which say plainly that 4 means "finished, the owner is needed", not failure.
5. **Director skill.**
   - Before detaching, the Director checks `wake`. With no wake path (no hook, and no harness wake it has seen work), it stays attached with `wait`.
   - If it will end its turn anyway, it first gives the owner `wake.notice` in conversation, before dispatching.
   - Exit 4 (or `needs_owner`) from `dispatch --wait` / `wait` means go to the owner now.
   - A detached Director sets `BATON_DIRECTOR` and `BATON_HARNESS`.
6. **README.** The exit-code table; a "Directors that end their turn" section covering `BATON_DIRECTOR`, `BATON_HARNESS` and `BATON_OWNER_EXIT`; and two hook examples: a webhook (`curl` to `secret:director_wake_url`) and a local inbox file.
7. **The bug eval's scenario, scripted:** a detached scripted Director, with no hooks, dispatches a framing step with `--wait`.
   - `eligible` showed the notice, and the transcript shows the notice relayed to the owner before the dispatch.
   - The call exits 4, or 0 with `BATON_OWNER_EXIT=0`.
   - With an `on_needs_human` hook configured, the hook fires with outcome `needs_human` and `eligible` shows no notice.

### Open questions

None. The owner accepted the recommended scope (B1–B4, B5 as README examples, a warning rather than a refusal for B6, B7 and B8 left out) and added decision 0059.

## Design

### Doc edits

- `design/runtime.md` §8.7: "Detaching with no hook configured prints a warning" becomes: a *wake path* is a hook that fires for a step waiting on the owner. `dispatch` and `ask_sme` warn when there is none, with or without `--wait`.
- `design/director-interface.md`:
  - §13.1: an exit-code table that defines exit 4 as a success path and documents `BATON_OWNER_EXIT`; `eligible` / `sme_eligible` return `wake`.
  - §13.3: the skill's wake-path rules and the meaning of exit 4.
  - §13.4: the `doctor` wake-path check.
  - §13.8: `wake.notice` is material the Director relays to the owner, like a `blocking` message.

### Decisions

- [0057](../decisions/0057-owner-needed-exit-code-opt-out.md): `BATON_OWNER_EXIT=0`; the default stays 4.
- [0058](../decisions/0058-detached-director-warned-not-refused.md): a Director with no wake path is warned, never refused.
- [0059](../decisions/0059-warn-owner-before-unwoken-dispatch.md): the Director tells the owner before a dispatch it might not be woken for.

### Mechanism

- **One wake-path test.** `supervisor.wake_path(project) -> hook name | None` uses `choose_hook` with `needs_owner=True`, the outcome a Director must not miss. It replaces `hooks_configured` at every use.
- **`wake` in `eligible`.** For a process step this is `{configured, hook}`. Without a wake path it is `{configured: false, expected: "<band>", notice: "<owner text>"}`. Example notice: *"I might not notice when this part finishes. It can take up to about 2 hours (a little longer if it runs over). If you haven't heard from me by then, ask me to check on it."* The text has no Baton vocabulary and is computed deterministically. The skill makes the Director relay it.
- **Exit code.** `cli._done` and the other exit-4 paths (vendoring and permission `ask`, which also return `needs_owner`) read `BATON_OWNER_EXIT`. Accepted values are `0` and `4`; anything else is a usage error.
- **Doctor.** It warns: "no completion hook would wake a Director when work needs the owner". This becomes a problem when an active run's lease names a harness other than `cli`.

## Plan

### Wake path and warnings

- **Outcome:** Baton reports, before dispatch, whether anything will wake the Director, and warns when nothing will, in every mode.
- **Criteria:**
  - `wake` in `eligible` and `sme-eligible`, with and without hooks; the notice's duration comes from the step's band and `extend_once`; manual steps have no notice.
  - `dispatch`, `dispatch --wait` and `ask_sme` warn with no wake path; a project with only `on_platform_failure` warns.
  - `doctor` warns with no wake path, and reports a problem when an active run's lease harness isn't `cli`.
- **Effort:** M

### Exit codes

- **Outcome:** exit 4 is documented as a success path, and harnesses that treat non-zero as failure can opt out.
- **Criteria:**
  - `BATON_OWNER_EXIT=0` makes `dispatch --wait`, `wait`, `decide`, `push`, `permission` and `vendor` exit 0 when the owner is needed; `needs_owner` is still in the JSON.
  - An invalid value is a usage error.
  - The default stays 4.
  - §13.1 has the exit-code table.
- **Effort:** S

### Skill, README and the scenario

- **Outcome:** a Director never detaches silently without a wake path, and the owner hears beforehand when it might not be woken.
- **Criteria:**
  - The skill rules in criterion 5 are in the shipped skill and §13.3, and the skill test checks them.
  - The README sections in criterion 6 exist.
  - The scripted scenario in criterion 7 passes; it is based on Phase 16's remote-Director test.
- **Effort:** M

## Log

(empty)
