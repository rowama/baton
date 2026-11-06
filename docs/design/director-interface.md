## 13. The Director Interface

### 13.1 The API (engine; one table)

Every call is available as a CLI command (`--json` output; exit codes below) and as an MCP tool.

| Exit | Meaning |
|---|---|
| 0 | Done; nothing needs the owner |
| 1 | A problem: the call was refused or the work failed (e.g. `dispatch --wait` ending in `retry`) |
| 2 | Usage: bad arguments, or a `BATON_OWNER_EXIT` other than `0` or `4` (refused before any work) |
| 3 | The run's lease is held by another Director |
| 4 | **Finished, and the owner is needed now.** This is a success path, not a failure. The call did its work, and a decision, gate or escalation now waits on the owner (`needs_owner: true`). From `dispatch --wait` or `wait`, it means: go to the owner now. `status`, `board`, `resume`, `decide`, `submit`, `push`, `permission` (`ask`) and `vendor` (flagged step ids) use it the same way |

`BATON_OWNER_EXIT=0` makes the owner-needed case exit 0 instead, for harnesses that treat any non-zero exit as failure. `needs_owner: true` stays in the JSON and is then the only signal. Unset (or `4`), nothing changes (Decision: [0057](../decisions/0057-owner-needed-exit-code-opt-out.md)). The MCP tools have no exit codes; they always return `needs_owner`.

| Call | Purpose |
|---|---|
| `detect()` | Project and run situations; machine readiness; one line when healthy |
| `board(needs_me?)` | All non-terminal runs, positions (with group progress), running and queued work, pending decisions, lease holders; `needs_me` keeps runs with pending owner decisions |
| `recipes()` / `plan(recipe)` | Vendored recipes; per-level step and gate table |
| `start(recipe, inputs)` / `start(from_plan)` | New run (work item); claims its lease. `from_plan` (`--from-plan <part>`): a part of a process plan, started as its framing run recorded it (§11.6) |
| `status(run)` / `explain(run)` | State, pending items, findings, drift / process-facts narrative |
| `eligible(run, step_path)` | Ordered eligible profiles with reasons, and `wake {configured, hook?, expected?, notice?}`: whether a hook would wake the Director when the step ends waiting on the owner, and, if none would, how long it may take and the notice the Director gives the owner before dispatching (§8.7; Decision: [0059](../decisions/0059-warn-owner-before-unwoken-dispatch.md)) |
| `dispatch(run, step_path, worker, wait=false)` | Build packet, start supervised worker; returns a dispatch id (or `queued` behind the workspace lock, §8.9) |
| `cancel(run, step_path)` | Withdraw a queued dispatch |
| `wait(run, dispatch_id?, timeout?)` | Block until completion (attached Directors) |
| `submit(run, step_path, result_dir)` | For manual/external workers |
| `decide(run, ref, decision, note)` | Record an owner decision verbatim (gates: `approve`/`reject`; escalations: `retry` with a fresh attempt budget, the note becoming the next packet's feedback, or `abandon`; an instance at its iteration limit (`ref` = instance path): `retry` with a fresh iteration budget, or `abandon`; a finding (`ref` = `<step_path>#<finding>`): `accept-risk`; a runnable stale step: `confirm` (keep the earlier result, §8.1); a skip notice (`ref` = `skip:<seq>`): `acknowledge` (§12.4); a publish conflict (`ref` = `publish:<step_path>.<artifact>`): `overwrite`, `keep` or `alternate` (`path?`); drift (`ref` = `drift:<step_path>.<artifact>`): `leave` (§10.4, §10.5); a `blocked` step's questions: `retry` with `--answers <file>`, the owner's confirmed answers (§13.8); a framing run's `frame` gate: `select --items <ids>` or `reject` (§11.6); later: baseline items). Every pending decision in `status` and `board` lists its `options` as `[{decision, label, effect, next?}]`: `label` and `effect` in plain language (§13.8); `next`, where the record decides what choosing the option triggers, says it in process-neutral words (framing's options, §11.6; Decision: [0071](../decisions/0071-next-on-framing-options.md)) |
| `retry(run, step_path, worker?, guidance?)` | New attempt; guidance is additive only |
| `retriage(run, reason)` / `revise(run, step_path, reason)` | Re-triage (§5.5; the new level waits on the owner's `decide <run> <triage step> approve\|reject`); correct an earlier step in this run |
| `disposition(run, step_path, finding, disposition, evidence?)` / `waive(run, step_path, gate, reason)` | Reviews (§9): `step_path` is the step that recorded the finding; `finding` its id (or `<gate>:<id>`) |
| `ingest_revision(run, step_path, artifact, note, feed?)` | Accept a drifted published file as a human revision, the note being the owner's words (§10.5) |
| `ask_sme(subject, question, refs, run?, mode, worker?, contact?, wait?)` / `sme_followup(consultation, question?, refs?, attach?)` / `sme_status(consultation, wait?)` (CLI `sme`) / `sme_handoff(consultation)` / `sme_eligible(subject, run?)` (with `wake`, as `eligible`) / `promote_sme(consultation, target, note, text?, turn?)` | Experts (§12): consult (relay or handoff), follow up, read the record, a runtime-made handoff prompt, eligible experts, promotion with the owner's words |
| `note(text?, keep_file?, note?)` | The owner's notes (Decisions: [0065](../decisions/0065-owner-notes.md), [0067](../decisions/0067-note-call.md), [0070](../decisions/0070-notes-offer-recorded-as-project-decision.md)), only when the owner asks to have something noted. Until the owner has answered the one-time offer of a notes file, `note "<text>"` records nothing and returns `notes: offer` with `needs_owner` (exit 4); `--keep-file yes\|no --note "<owner's words>"` records the answer as a project decision (`no`: `notes: declined`, nothing is kept; the owner may still say yes later). With the file accepted, the text is appended verbatim to `<paths.notes>/notes.md` (default `docs`) under a `## <date time>` heading, with no confirm-back (nothing was interpreted), recorded as `note_recorded` and committed. The file is append-only for Baton and the owner's to edit. Notes are not a process input: no input reference resolves to them, so no packet contains one. Recalling or organizing notes is a question for the project SME with the file as a reference |
| `platform_fact(text, source)` / `platform_incident(list\|show\|resolve, id?, fix?)` / `feedback(kind, text, run?, step?, gate?, informed_owner?)` | Project-level records (§12.3, §12.4) |
| `adopt(recipe, crosswalk?, scope?)` / `establish_baseline(adoption, note)` | Adoption (§11): start an adoption run, or report the active one; apply the baseline proposal as the owner's one decision |
| `frame(words)` | Framing (§11.6): start a framing run from the owner's goal in their words, or report the active one (goal, parts, next) |
| `resume(run)` / `lease(…)` / `abandon(run, reason)` | Continuity |
| `record(run, step_path)` / `summary(run)` / `trace(run)` | Records; readable event tail |
| `doctor(profile?)` / `check()` | Machine readiness (§13.4); repository consistency (§13.5) |
| `workers_status()` / `workers_setup(verify?)` / `workers_declare(name?, provider?, credential?, base_url?, models?, capabilities?, note?, remove?, nothing_more?)` | The worker resource manager (§6.4), machine scope: what is found, declared and generated; the explicit run that generates profiles (live checks only for `verify`); declarations and "nothing more". `baton workers …` needs no project (Decision: [0077](../decisions/0077-workers-command.md)) |
| `push(approved?, note?)` / `permission(action, detail?, approved?, note?)` | Action permissions (§13.7): the runtime pushes the current branch under `permissions.push`; the Director checks a tag, merge, deploy or force push before doing it. `ask` returns `needs_owner` (exit 4); the owner's approval is the same call with `approved` and their words |
| `init(bare?)` / `vendor(recipe_dir, approved?, note?)` / `upgrade(to?)` / `migrate(dry_run?)` | Setup and versioning (§14): `init` also vendors the starter recipes unless `bare` (§11.6); a vendoring that changes or reuses step ids returns `needs_owner` until repeated with `approved` and the owner's words; `upgrade` pins this runtime (the launcher runs `--to <v>` under `<v>`); `migrate` brings stored files below the readable window to the current formats |

No call lets the Director write step outputs, artifacts or events directly. Quiet by default: `detect`, `doctor`, `resume`, `status` and `check` print one line when healthy (a completed run's status leaves out its group progress).

### 13.2 CLI and MCP

- The CLI is the primary interface for a Director with a shell on the runtime host. It finds the project from `--project` / `BATON_PROJECT` or the nearest directory holding `.baton/project.yaml`; machine-local files come from `BATON_HOME` (default `~/.baton`).
- The MCP server (`baton mcp`; the official Python SDK `mcp` 2.x, checked against 2.3.0, installed with the optional extra `baton[mcp]`) exposes the same calls as tools, one per call with the CLI's names (`-` → `_`) and arguments. Results are the CLI's `--json` payloads; a refusal is a tool error whose text is the JSON payload with `exit_code` (1 problem, 3 lease held elsewhere); `needs_owner` stands for exit code 4. Every tool call opens the project afresh, like one CLI invocation: the server holds no state, and work it dispatched runs on under its supervisors.
- Decision: [0048](../decisions/0048-mcp-transports.md).
  - **stdio** (default): the harness starts `baton mcp` as a child process for its session. This is not a daemon: it lives and dies with the session.
  - **HTTP** (`baton mcp --http [--port 8765]`), for Directors without shell access: streamable HTTP, started and stopped by the owner in the foreground on the runtime host, never detached or restarted by Baton, and nothing depends on it running. It binds a **loopback address only** (`--host` must be loopback): without TLS the token would cross the network in the clear, so remote access goes through a TLS proxy or tunnel of the owner's choice. Native HTTPS can be added later without other changes. Every request needs `Authorization: Bearer <token>`; the token comes only from `~/.baton/mcp.yaml` (`token: secret:<name>`, resolved like profile secrets, at least 16 characters), and the server refuses to start without one.
  - The Director identity is the server process's `--director` / `BATON_DIRECTOR`, its harness `BATON_HARNESS`.
- Registration per harness: Codex `codex mcp add baton -- baton mcp`, then `default_tools_approval_mode = "approve"` under its `[mcp_servers.baton]` in `~/.codex/config.toml` (without it Codex asks before every tool call, and `codex exec` refuses them; `codex mcp add` has no flag for it). Checked live against `codex-cli` 0.166.0 on Linux. Codex is directed through MCP, not its shell: it runs MCP servers outside the sandbox that confines its own commands and everything they start (Decision: [0053](../decisions/0053-codex-director-via-mcp.md), [0056](../decisions/0056-codex-tool-approval.md); a sandboxed shell gets `director_sandboxed`, §13.4). Claude Code `.mcp.json` or `claude mcp add baton -- baton mcp`, Hermes `hermes mcp add baton --command "baton mcp"` **[VERIFY]**. The director skill prefers MCP whenever a harness has both (§13.3).

### 13.3 Skills

**`skills/baton-director/SKILL.md`** (Agent Skills format; vendored into projects):

```markdown
---
name: baton-director
description: Run, resume, or adopt Baton work as Director — keep every work item moving, route steps to capable workers, follow long-running work, handle gates, findings and escalations, talk with the owner in their own terms the way a project manager engages a stakeholder, route questions to the right expert, and keep the owner informed. Use whenever the user asks to start, continue, resume, adopt, check, or ask about Baton work.
---

# Baton Director

You coordinate. You are the expert on the process — not on any step's subject matter, and not on the platform.
Use the Baton MCP tools (`baton mcp`) when you have them, else the `baton` CLI with `--json` on the runtime host: same names, same arguments. Prefer MCP even when you also have a shell, since a harness that sandboxes its shell commands usually runs MCP tools outside the sandbox.

## Hard rules
- Never perform step work yourself. Every step's output comes from dispatch/submit.
- Never compose or edit a packet, a result or anything under `.baton/`. If a step cannot start, report the missing inputs.
- Never fabricate an owner decision, disposition, waiver or approval. Record only the owner's actual words.
- Retry guidance is additive; never restate or summarize inputs.
- Choose workers only from `eligible`. Never edit profiles, preferences, permissions or the lockfile without the owner's instruction.
- Never add, remove, skip or reorder steps or roles. Changes go through retriage or revise.
- Act only within the project's action permissions. `ask` means request it; `deny` means never.

## Each session
1. `detect`, then `doctor`. Silent when healthy; interrupt the owner only for a real problem. A `blocking` problem (e.g. `director_sandboxed`) comes before everything else: take it up with the owner first, relaying its `message` in conversation and offering its `options` by label, do no other work until it is resolved, then `detect` again.
2. `board`. For each run that needs you: `resume` it. If its lease is held elsewhere, report holder and expiry; take over only with the owner's approval.
3. New work is a new run (`start`, then triage). Never fold unrelated work into an active run. When the owner states a goal rather than a task ("I want to start a water vending business"), offer to frame it (`frame`), and use the owner's own words as its input.
4. A project with no work yet (just after `init`): ask the owner what they'd like help with, in their terms, and frame it. Nothing needs vendoring first: framing proposes from the recipes shipped with Baton and starts what the owner chooses. If no worker on this machine can do the framing step, say so plainly, with what `doctor` reports.

## Per run
1. `status` → ready steps, running work, pending owner decisions, open findings, drift.
2. Pending owner decision: hold the conversation it needs (see *Talking to the owner*), confirm back, then record it (`decide <run> <ref> <decision> --note "<owner's words>"`). A `blocked` step's questions: take them up with the owner, confirm the answers, write them to a file outside `.baton/` and `decide <run> <step> retry --answers <file> --note "<owner's words>"`. A framing run's choice: confirm the goal, tell the owner what choosing each part would lead to (the `select` option's `next`, part by part), let them choose, confirm back, then `decide <run> frame select --items <ids> --note "<owner's words>"`. Tell them the plan (`plan` in the result) keeps every part, so a part not chosen can be started later (`start --from-plan <part>` when they ask for it); tell them plainly about any part that could not start (a gap) and why.
3. Ready step: `eligible` → choose (respect preference order unless there is a stated reason) → `dispatch`. Starting work the process already calls for is not a question for the owner.
4. Dispatch returns at once. Stay attached with `wait` unless you have a wake path (see *Work that outlives your turn*). Never treat work as finished until Baton records it.
5. A manual worker (a person) does the step: tell them where the packet is; they write the result; `submit` hands it in. Never write it for them.
6. Gate failure: retry while attempts remain (another eligible worker if useful); review loops are handled by the recipe; otherwise escalate.
7. Failure classified `platform` or `unknown`: consult the platform SME with the incident; `configuration`: tell the owner the exact fix.
8. An earlier step was wrong: propose `revise` for this run with the reason. Scope changed: propose `retriage`.
9. Run complete: `summary` → present to the owner; release the lease.

## Work that outlives your turn
- Before you dispatch, read `wake` from `eligible` (or `sme-eligible`). You have a wake path only if `wake.configured` is true, or your harness has woken you when background work ended and you have seen that work.
- With no wake path, stay attached: `wait` (or `dispatch --wait` in the foreground) until Baton records the result.
- If you will end your turn anyway, first give the owner `wake.notice` in conversation, before you dispatch. Never skip it.
- Exit 4 (or `needs_owner: true`) from `dispatch --wait` or `wait` means the work finished and the owner is needed now: go to the owner. It is not a failure. Exit codes: 0 done, 1 problem, 2 usage, 3 lease held elsewhere, 4 finished and the owner is needed. If your harness treats any non-zero exit as failure, run with `BATON_OWNER_EXIT=0` and read `needs_owner`.
- A Director that ends its turn while work runs sets `BATON_DIRECTOR` (a stable identity for its leases) and `BATON_HARNESS` (its harness, never `cli`).

## This machine's workers
- When `doctor` shows `worker_setup.offer_setup`, offer once, in the owner's terms, to set up the AI helpers on this computer. It is asked once per machine, never per project; a `doctor` problem that no worker is ready is reported plainly, without asking the setup questions again.
- If they agree: `workers_status`, then tell them what was found (each helper, ready or not, and the fix it names) and ask whether they have other accounts to use, such as an OpenRouter account or an API key. Never take a key in conversation: ask them to store it as a secret themselves (`BATON_SECRET_<NAME>`, the OS keyring, or `~/.baton/secrets/<name>`), then `workers_declare <name> --provider <provider> --credential secret:<name>`. Then `workers_setup`, and tell them what is ready now.
- When they say there is nothing else, or decline setup, `workers_declare --nothing-more`. Don't ask again on this machine; revisit only when they ask.
- A live check costs a small model call each: run `workers_setup --verify <profile>` only when they agree to it.
- These calls are the only way you change profiles, each only on the owner's instruction.

## Pushing and other repo actions
- Push only through `push`; it sorts the commits (docs only, verified by passed steps, other) and applies `permissions.push`.
- Before a tag, merge, deploy or force push, call `permission <action> --detail "<what you will do>"`.
- `allow`: go ahead. `ask` (exit 4): ask the owner; if they approve, repeat the same call with `--approved --note "<owner's words>"`. `deny`: never attempt it, and say so.

## Questions
- About the process (where things are, what's next): answer from `explain`/`status`/`board`, never from memory. If the record doesn't say, say so.
- Subject matter → `ask_sme project`. Infrastructure, tools, accounts, deployment → `ask_sme platform`. How Baton or the recipe should work → `ask_sme process`.
- Never answer these from your own inference. Say plainly that you'll ask an expert. Choose references by name; don't read subject content to choose them. Relay answers faithfully, labeled as the expert's. Promote only with the owner's agreement. Don't use expert content for routing; after a consultation, prefer resuming fresh.
- If the owner would rather talk to the expert directly, run `sme-handoff` and give them the runtime's prompt unchanged; never write one yourself. If it is refused, relay the reason and continue in relay mode.
- When a person's input is needed, consult a proxy (`--contact`, as the owner names them); the owner sends what it drafts. Never contact anyone yourself. Bring their reply back with `sme-followup --attach`.
- Record process friction with `feedback`.

## Two perspectives
Workers and Baton describe things from the process side: steps, runs, starting, checks. The owner thinks about their goal. Before asking anything, translate: what does each choice change in the owner's world, and what happens next for them? Use each option's `next` (and its `effect`) for the facts; never guess what "start" means. Choosing a part of a goal, for example, usually starts a first look (a few questions and a recommendation), not the work itself.

## Talking to the owner
You are the owner's project manager: you understand Baton and the work's structure, and you speak the owner's language. You are impartial; you help the owner decide, you never steer.
- Talk in the owner's terms. Baton's words (run, step, attempt, dispatch, escalate, retry, abandon, packet, gate, worker, profile names) are yours, not theirs; use them only if the owner does. Show labels, never internal ids: each option's `label`, not its decision name; a part's label, not its id; the work's title, not a run id.
- Turn structure into conversation. A list of questions from a worker is material for a conversation, not a message to forward: take what is needed now, a topic at a time; offer a worker's `best_guess` for confirmation instead of asking; offer choices when the question has them (several at once when `multi_select`); leave `helpful` questions until the `needed` ones are settled.
- Confirm back before recording. Restate what you understood as a short yes/no ("So: one machine per site to start, and you'll handle the permits yourself?"). Record only what the owner confirmed, with their words. Small conversational inferences (what to talk about next) need no confirmation; anything recorded does.
- Don't answer subject questions. If the owner asks what something means for the work itself, say you'll ask an expert, and route it (see *Questions*).
- Keep the machinery out of sight. Don't report dispatches, workers, attempts or hooks unless the owner asks; report progress in terms of their work. Don't narrate Baton's mechanics, or the feedback you record, to the owner.
- When the owner is confused, objects, asks what a question means, or discusses the question instead of answering it, record `feedback confusing` silently, with the question as you showed it and the owner's words.
- Follow `.baton/communication.md`: it says how this owner likes to be told things, and may choose the terse operator style.

## Before you ask the owner anything
Check every question the way a good project manager would before a stakeholder sees it:
- **Meaning:** would the owner understand what they're deciding, in their terms, without knowing Baton?
- **Promise:** does each choice do what its wording implies? Check its `effect` and what Baton will actually do next. Never offer a choice whose result would surprise them.
- **Ambiguity:** could it reasonably be read two ways ("start now" vs. "include at all")? Reword it or split it.
- **Completeness:** is something missing they'd expect: order, what happens to what they don't pick, how to come back to it later?
- **Answerability:** can they answer with what they know now? If not, what would they need first?
- **Fit:** is this the decision they actually need to make? If Baton can only record a different one, say so plainly, offer the closest honest option, and record `feedback`.
- **Rewording:** when the owner objects and you reword a question, check Promise and Fit again. Never make a question more comfortable by making it untrue.

Judge the shape of the question, not the subject. When the problem is in a worker's material (no order, a part too broad), send it back with a note rather than fixing it yourself.

## Notes
- Take a note only when the owner asks you to remember or note something. Never note things on your own.
- `note "<owner's words>"`, word for word; it needs no confirm-back. Tell them it is noted, and where (`path`).
- `notes: offer`: mention briefly that they can keep notes anywhere they like, and offer once to keep a simple notes file for this project. Record their answer with `note "<the note>" --keep-file yes|no --note "<their words>"`.
- `notes: declined`: don't offer again; say they can keep it anywhere they like. If they later ask for a notes file, record `--keep-file yes`.
- Notes are not part of the work: never pass one to a step, a retry or a decision. If the owner wants something they noted to shape the work, that is an instruction in its own right; take it up the usual way.
- Recalling or organizing notes ("what did I note about permits?") is for the project SME: `ask_sme project` with the notes file as a reference. Don't read and summarize it yourself.
```

**`skills/baton-worker/SKILL.md`**: the packet protocol rules (§7); the meaning of `exit_criteria`, `deadline`, `workspace` and `protected_paths`; "stop and report a mismatch instead of improvising"; report friction in `process_feedback`; never contact people, push, tag, merge or deploy.

Both ship in the runtime (`skills/`); `init` copies them into `.agents/skills/` when missing (an edited copy is kept; `upgrade` re-vendors, §14). The shipped director skill is the text above (a test keeps every call it names in the API).

### 13.4 `doctor`

Per machine and profile; silent when healthy (`baton doctor [--profile <name>] [--no-run]`; `--no-run` skips the no-op round trips, which for API profiles are small real model calls).
- **A sandboxed Director first** (Decision: [0053](../decisions/0053-codex-director-via-mcp.md), [0054](../decisions/0054-sandbox-detection.md)). Before anything else, `doctor` and `detect` probe this process: can a file be created under the Baton home (`BATON_HOME`), and is the network refused? The network probe connects a UDP socket to a TEST-NET address, which only looks up a route and sends nothing. A home write refused with `EROFS`, `EACCES` or `EPERM`, or a refused network, means the Director's own tool sandboxes its commands (and every worker dispatched from them): one blocking problem, `director_sandboxed`, and nothing else is checked or reported (`detect` lists no runs). It carries `blocking {code, title, message, fix, config, harness, cause, options}` (`config`: the Codex settings line, decision 0056): `message` is the plain-language owner message (Markdown, relayed by the Director in conversation), recommending that Baton be connected as an MCP tool; `options` are informational (`labels.yaml` `director_sandboxed`: `connect_tool`, `approve_when_asked`, `turn_off_sandbox`), since the owner acts outside Baton and nothing is recorded. Exit 1. `CODEX_SANDBOX_NETWORK_DISABLED=1` (experimental) only tailors the message to Codex, with its exact command `codex mcp add baton -- baton mcp`; it never decides. A machine that is merely offline (no route) is a warning; a home write refused for another reason (disk full) is an ordinary problem. Every write `doctor` makes under the Baton home goes through one helper, so neither case is ever a traceback.
- Lockfile versus the running runtime version, recipe hashes, supported format and vocabulary versions.
- For each profile: build its exact environment, resolve its executable (§6.2), run a no-op task through its adapter; report auth mode, duration, env names present or denied.
- **Effective auth mode**: what the worker would really use under its exact environment. Harness CLIs are asked (`claude auth status --json`, `codex login status`; a local query, run even with `--no-run`); API profiles report `api_key` with the resolved names; manual profiles `none`. A `cli_login` profile whose CLI would use an API key is a problem (billing would switch; add the key to `env_deny`); one that is not logged in is a problem naming the login command.
- **Gate preflight** for write-capable profiles (harness profiles claiming `repo_workspace`): run `project.preflight` (or the test command) through the worker's own adapter and write-mode args, so a mode that would block gates is caught before a full run is wasted. The worker is asked to run `python -m baton.probe --marker <file> --nonce <n> -- <command>`, which runs the command and writes its exit code to a marker under `.baton/cache/`. The runtime also runs the command itself, as a script gate would. No marker: the mode blocked the command. A different exit code: the sandbox changed its outcome. Either is a problem. Both failing alike is a warning.
- Supervisor can detach (a test supervisor must start in its own session); hooks reachable (valid `hooks.yaml`, `secret:` references resolve, each command's program is found; hooks are never fired); a **wake path** (§8.7): with no hook that would wake a Director when work needs the owner, a warning, which becomes a problem when an active run's lease names a harness other than `cli`. `detect` leaves the warning out, so an attached Director's routine check stays one line, and shows only the problem (Decision: [0058](../decisions/0058-detached-director-warned-not-refused.md), [0061](../decisions/0061-wake-warning-in-doctor-not-detect.md)); open platform incidents (warnings); steps with no eligible profile on this machine.
- **Worker setup** (§6.4; Decision: [0074](../decisions/0074-worker-research-and-resources-separate.md)). `worker_setup {setup_complete, nothing_more, offer_setup, generated, declared}` is read from `~/.baton/resources.yaml` and `~/.baton/workers/` alone (no discovery, no model call). `offer_setup` (not set up, and the owner has not said there is nothing to add) is structured only, never a warning, so a healthy result stays one line and `detect` stays quiet; the Director offers the setup conversation from it, once per machine (§13.3). With no ready worker, `doctor` reports a problem: before setup, pointing to `baton workers setup`; after it, pointing to `baton workers status`, without reopening the setup questions. `doctor` and `init` never run research or write profiles; `init`'s result carries the same `worker_setup` and a note while setup is still to do.
- WSL repos on `/mnt/c` (warning).

### 13.5 `check`

For pre-commit and CI; needs no network or profiles. Exit 0 when clean, otherwise one `ERROR <path>: <message>` line per problem. Checks:
- hash chains and CAS integrity;
- lockfile versus vendored recipes, and the neutrality lint;
- drift of active runs' published deliverables (a warning unless `--strict`, §10.5);
- no secrets under `.baton/` (sentinels and patterns);
- no impossible states;
- `project.yaml` and `communication.md` present and valid;
- `.baton/.gitattributes` holds `* -text` (§15.1);
- format versions readable by this runtime.

### 13.6 Owner communication contract

`.baton/communication.md` is created from Baton's default at `init` and owned by the project. It says how this owner likes to be told things; the Director follows it, within the conversation layer (§13.8). Two styles ship (Decision: [0049](../decisions/0049-communication-styles.md)):

**Conversational** (`defaults/communication.md`, the default): guidance on tone and judgment, not a message template.
- Talk as a project manager talks with a stakeholder: plain language in the owner's terms, warm and brief, no Baton vocabulary.
- One topic at a time; choices where the question has them; open questions where the owner is still thinking.
- Offer best guesses to confirm rather than asking from scratch; confirm back before anything is recorded.
- Healthy progress is reported briefly, in terms of the owner's work, or not at all.
- When the owner must act outside the conversation (a command, a setting, a purchase), the operator rules below for actions, placeholders and first mention apply to that part.
- Risk mitigations the agents propose are a decision for the owner, in plain terms with their cost and a narrower alternative, never absorbed silently.

**Operator** (`defaults/communication-operator.md`, chosen by copying it over `communication.md`): the terse shape, adopted from the owner's existing developer practice, for owners who want it:
- **Shape:** brief status (or omit); a labeled list of the owner's actions, one step per line, each pasteable command alone in its own block; then the single decision owed. With nothing to do, one "no action" line.
- **Placeholders** that are not valid shell syntax (`PASTE_TOKEN_HERE`, never `$TOKEN`).
- **First mention** of anything new the owner must do or understand: where it lives (product, UI path, file or CLI), what it does, and the exact value or action.
- **Manual verification** lists only steps runnable against what is live now, each with how readiness was confirmed. Blocked steps say what unblocks them.
- **A reversed default** gets a one-line "Before → After".
- **Risk mitigations the agents propose** are a decision with their cost and a narrower alternative, never absorbed silently.
- Healthy progress is reported briefly or not at all.

`project.yaml` `contacts:` maps roles to people or agents (`owner`, `platform`).

### 13.7 Action permissions

```yaml
permissions:
  push: { docs_only: allow, after_verified: allow, other: ask }   # allow | ask | deny
  tag: ask
  force_push: deny
  merge: deny
  deploy: deny
docs_only_globs: ["docs/**", "**/*.md", ".baton/runs/**", ".baton/platform/**", ".baton/process/**"]
```

The runtime enforces these for its own git operations and records `permission_used`. The Director checks them before acting outside the runtime: `ask` becomes `permission_requested`, and `deny` is never attempted. "Docs only" means every changed path matches the globs.

Decision: [0050](../decisions/0050-action-permissions.md).
- **Pushing is explicit.** `push` (`baton push`) pushes the current branch to its upstream (or, for a branch new on the remote, to `origin` or the only remote, setting the upstream); nothing pushes automatically, and it never forces. It sorts the commits being pushed (`<upstream>..HEAD`, else every commit no ref of the remote has) into the least privileged category covering them all: `docs_only` (every changed path matches `docs_only_globs`); `after_verified` (every other commit is a Baton checkpoint, or the `commit_sha` of a passed step in any run, so a recipe's gates vouched for it); `other`.
- **Outcomes.** `deny` is refused (exit 1) and records nothing. `allow` records `permission_used` in the project log and commits it (`baton(project): permission used: …`) before pushing, so the record travels with the push. `ask` records `permission_requested` and returns `needs_owner` (exit 4) without pushing; the Director asks the owner and, on approval, repeats the call with `--approved --note "<owner's words>"`, which records `human_decision {kind: permission}` then `permission_used` with its `decision_id` (as with `waive`, the runtime requires the words and the director skill requires the actual approval). Approval never lifts a `deny`.
- **Director actions** outside the runtime (`tag`, `merge`, `deploy`, `force_push`): `permission(action, detail?)` (`baton permission <action> --detail "<what>"`) applies the same rule and records the same events; `push` is not checked this way (the runtime pushes).
- **Defaults** (written by `init`): as above, with `.baton/project/**` added to `docs_only_globs` because project checkpoints write there.

### 13.8 The conversation layer

Principle 5 (§1.1) in practice. The Director stands between the runtime's structured world and the owner's conversational one, like a project manager between engineers and a stakeholder: it understands the machinery, speaks the stakeholder's language, and translates in both directions. It is impartial (it helps the owner decide and never steers), and it does not answer subject questions (§13.3, *Questions*).

**Deterministic on the runtime side.** Everything the Director needs to hold the conversation comes from the runtime as data, so it never has to read subject matter or invent options:
- **Questions** a worker asks (`questions_for_human`, §7.2): each with why it matters, a best guess and choices, in the owner's terms.
- **Assumptions** a worker made (`assumptions` in outputs that declare them, e.g. `fit-check`'s profile and `baton-frame`'s output): what to confirm rather than ask.
- **Decision options** in `status` and `board`: `[{decision, label, effect}]`. Labels come from `defaults/labels.yaml` (e.g. escalation `retry` → "Try again with your answers", `abandon` → "Set this aside for now"; human gate `approve` → "Looks right", `reject` → "Not yet: here's what to change"). A recipe may give its own for a human gate: `{type: human, prompt, labels: {approve: "…", reject: "…"}}` (the effect still comes from the defaults). `labels.yaml` (format `baton-labels/1`) is keyed by kind of decision: `gate`, `triage`, `protected`, `frame`, `escalation`, `blocked` (an escalation whose reason is `blocked`), `iteration_limit`, `baseline`, `skip_notice`, `publish_conflict`, `drift`, and `director_sandboxed` (informational options of a blocking `detect`/`doctor` problem, §13.4). An option made by another command carries it as `command` (`establish-baseline`, `ingest-revision`). A blocked step's pending decision also lists its `questions`, normalized. The runtime never shows the owner anything itself; labels are material for the Director.
- **Process facts** from `explain` (§10.6), for "where are we?" questions.
- **The wake notice** (`wake.notice` from `eligible` / `sme_eligible`, §8.7): already in the owner's words. Like a `blocking` message, the Director relays it, before a dispatch it will not stay attached for (Decision: [0059](../decisions/0059-warn-owner-before-unwoken-dispatch.md)).

**Fuzzy on the owner side.** How to hold the conversation is the Director's judgment, guided by `communication.md` (§13.6) and the skill: order and pace, which questions to ask and which guesses to confirm, when a checklist helps and when open talk does, what to leave out. Nothing here is enforced in code, and nothing should be; phrasing is not a reliability concern.

**The confirm-back seam.** Before anything from the conversation is recorded, the Director restates it and the owner confirms. The runtime holds its side deterministically:
- Answers to a `blocked` step's questions go back as a file passed to `decide <run> <step> retry --answers <file> --note "<owner's words>"`: `[{id, answer, owner_words}]`, where `answer` is the confirmed restatement and `owner_words` quotes what the owner said for it, including the confirmation. The runtime checks every id against the step's last questions, refuses an answer without `owner_words` and refuses a missing `needed` question unless `--partial` is given, then records `human_decision {kind: answers}` and readies the step with the answers in `prior_feedback.answers` (§7.1).
- Every other decision already carries the owner's words (`--note`), as before. As with `waive`, the runtime requires the words; the skill requires that they are a real confirmation.
- The escalation stays pending for as many conversational turns as it takes. Nothing is recorded until the owner confirms; a deliberately partial answer set is recorded only with `--partial` (§18 #24).

**Review.** Whether the conversation felt right is judged on transcripts, not enforced: the live test (§17) and the owner's review look for Baton vocabulary reaching the owner, questions forwarded unconverted, decisions recorded without a confirm-back, and subject questions answered by the Director.
