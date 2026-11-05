---
id: 2026-11-codex-director-sandbox
title: "Codex as Director: detect its sandbox and connect Baton through MCP"
status: in-progress
level: standard
decisions: ["0053", "0054"]   # codex-director-via-mcp; sandbox-detection (slice 1), owner decisions 2026-11-04
touches: [design/director-interface.md, design/platform-and-security.md]   # §13.2, §13.3, §13.4, §15; also the repo README.md
---

# Codex as Director: detect its sandbox and connect Baton through MCP

## Request

**Problem.** In the first real use, Codex acting as Director ran `baton detect --json` and `baton doctor --json`. Both crashed with an unhandled traceback:

    OSError: [Errno 30] Read-only file system: '/home/rob/.baton/logs/doctor/claude-code-sub-auth.log'

Codex then told the owner, in passing, that "Baton cannot write logs", and carried on as if nothing were wrong.

**Cause.**
- In Codex's default `workspace-write` mode, commands may edit files only in the current directory and in configured `writable_roots`; anything else needs approval. Sources: [workspace-write prompt template](https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/permissions/sandbox_mode/workspace_write.md), [Codex sandbox docs](https://learn.chatgpt.com/docs/sandboxing).
- Child processes inherit the same sandbox ([Codex sandbox docs](https://learn.chatgpt.com/docs/sandboxing)).
- `doctor` writes its logs under `~/.baton/logs/doctor/` (`src/baton/doctor.py`), which is outside the project, so the write fails.

**Why it is blocking, not cosmetic.** Every `dispatch` from that shell would start the supervisor and the workers inside the same sandbox. They need to write `~/.baton/logs/<run>/…`, and harness workers need their own home directories and network access. This is inferred, not yet reproduced. It affects anyone who uses Codex as Director over the CLI.

**Decision (owner, 2026-11-04).** Codex directs Baton through MCP (`baton mcp`, §13.2), not through shell commands. Decision: [0053](../decisions/0053-codex-director-via-mcp.md).
- A Codex maintainer states that "MCPs operate outside of the Codex exec sandbox" ([openai/codex #4152](https://github.com/openai/codex/issues/4152)).
- Codex's own commands stay sandboxed. No config file editing is needed: setup is one command, `codex mcp add baton -- baton mcp`.

**Acceptance criteria.**
1. With an unwritable Baton home or no network, `detect` and `doctor` never crash. Each reports one blocking problem, `director_sandboxed`, with the owner message below and a non-zero exit. The healthy path still prints one line.
2. The owner message is plain language and recommends connecting Baton as a Codex tool, giving the exact command.
3. The director skill treats a blocking `detect` problem as the first thing to resolve with the owner, before any other work. When both an MCP server and a shell are available, it prefers MCP.
4. The README has a short "Using Codex as Director" section.
5. A live test (`BATON_LIVE=1`): Codex connected over MCP, with its sandbox on (`workspace-write`), completes `fit-check` with a real worker dispatch.

## Design

**Owner message** (the runtime returns it as data; the Director relays it in conversation):

> **Baton can't run from inside this AI tool's sandbox.**
> Codex limits the commands it runs: they can only change files in this project folder, and usually can't reach the internet. Baton needs both: it keeps its working files in your home folder (`~/.baton`), and the AI helpers it starts need the internet.
>
> **Fix (recommended): connect Baton to Codex as a tool.** Codex runs connected tools outside its sandbox, so Baton works fully and Codex stays sandboxed for everything else. Run this once in your own terminal, then restart Codex:
> `codex mcp add baton -- baton mcp`
>
> Other ways, if you prefer:
> - Approve Baton's commands when Codex asks. Expect frequent prompts.
> - Run Codex without its sandbox (`codex --sandbox danger-full-access`). Codex can then change anything on your computer.

**Detection.**
- Probe first, before anything that writes logs:
  - Can a file be created under the Baton home (`BATON_HOME`, default `~/.baton`)?
  - Is network access available? This check is cheap, local where possible, and has a short timeout.
- The home write refused with `EROFS`, `EACCES` or `EPERM`, or the network refused, means `director_sandboxed` (decision [0054](../decisions/0054-sandbox-detection.md); it settles criterion 1's "no network" as *refused* network). The network probe connects a UDP socket to a TEST-NET address: no packet is sent, a sandbox refuses it with a permission error, an offline machine answers "unreachable". Offline is an ordinary warning; other home-write errors (disk full) are an ordinary problem.
- `CODEX_SANDBOX_NETWORK_DISABLED=1` is a hint that the caller is Codex ([Codex commit](https://forge.lthn.ai/core/core-agent-ide/commit/fde48aaa0d0becdf51ce930d6d987ee07d6d031f)). It is experimental, so use it only to tailor the message, never as the test.
- Without that hint, say "this AI tool's sandbox" and still name the MCP fix generically: connect Baton as an MCP tool.
- Every write to the Baton home in `detect` and `doctor` goes through one helper that turns `OSError` into this problem. No tracebacks reach the Director.

**Decision options** for `director_sandboxed` get Phase 17 labels (§13.8): "Connect Baton to Codex (recommended)", "Approve when asked", "Turn off the sandbox". They are informational: nothing is recorded, and the owner acts outside Baton.

**Why not other fixes.**
- Moving logs into the project fixes only the symptom; workers still lack network and their home directories.
- "Approve when asked" is unreliable as the main path. "Don't ask again" covers only the exact command for that session, and the prefix option appears only sometimes ([openai/codex #38328](https://github.com/openai/codex/issues/38328)). Saved rules are reported as not honored for commands that leave the sandbox ([openai/codex #15298](https://github.com/openai/codex/issues/15298)).

**Docs to update.**
- §13.4 `doctor`: the sandbox probe.
- §13.2: Codex registration is no longer [VERIFY]; the command is the one above.
- §13.3 skill: the blocking-problem and prefer-MCP rules.
- §15: a note on harness sandboxes.

**Risk.** The "MCP runs outside the sandbox" claim rests on a maintainer statement and one third-party macOS report, so acceptance criterion 5 must pass on Linux before the README recommends it. If it fails, reopen the decision.

## Plan

1. **Probe and problem:** the home-write helper, the network probe, `director_sandboxed` with message and labels, in `detect` and `doctor`. Tests: read-only home, no network, healthy. Accept: criteria 1–2.
2. **Skill and README:** the skill rules, the "Using Codex as Director" section, §13.2 registration. Accept: criteria 3–4; the skill test names any new calls.
3. **Live check:** Codex over MCP with its sandbox on, `fit-check` end to end on Linux. Accept: criterion 5. The owner reviews the transcript.

## Log

### Probe and problem

- **Commit:** `2026-11-codex-director-sandbox: probe and problem`
- **Summary:** `sandbox_probe` (home write, refused network) runs first in `detect` and `doctor` (`src/baton/doctor.py`, `src/baton/adopt.py`); `director_sandboxed` stops both with one problem, a `blocking` payload (owner message, Codex-tailored when `CODEX_SANDBOX_NETWORK_DISABLED=1`, fix, cause, options) and exit 1; the CLI's text output carries the message. Every doctor log write goes through `_home_log`. Labels: `defaults/labels.yaml` `director_sandboxed`. Docs: §13.4, §13.8 label kinds; decision 0054. Tests: `tests/test_sandbox.py` (a real read-only home for `doctor`, `detect` and `detect` outside a project; each sandbox errno; refused network and socket creation; the Codex message; offline is a warning; a refused log write mid-doctor, sandbox and disk-full; the helper; text output; the healthy path; the labels' wording).
- **Review:** not yet reviewed.
- **Accepted:** not yet (criteria 1–2 are this slice's; the owner accepts).
