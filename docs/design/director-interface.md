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
| `adopt(recipe?, crosswalk?, scope?)` / `establish_baseline(adoption, note)` | Adoption (§11): start an adoption run, or report the active one (with no recipe: `recipe_needed` and the steps to find one); apply the baseline proposal as the owner's one decision |
| `frame(words)` | Framing (§11.6): start a framing run from the owner's goal in their words, or report the active one (goal, parts, next) |
| `resume(run)` / `lease(…)` / `abandon(run, reason)` | Continuity |
| `record(run, step_path)` / `summary(run)` / `trace(run)` | Records; readable event tail |
| `doctor(profile?)` / `check()` | Machine readiness (§13.4); repository consistency (§13.5) |
| `diag(since?, code?, run?, records?, limit?)` | What the runtime has been working around on this machine (§8.3; Decision: [0094](../decisions/0094-diagnostics-channel.md)): counts per diagnostic code over the last 7 usage days (or `since`: a number of usage days or a date) next to each code's usual rate per day, unusual codes first; `code` filters by prefix, `run` to one run's records, `records` adds the raw records (the newest `limit`, 200 by default, newest last); also the size and oldest age of the raw worker logs, which Baton reports and never deletes. Machine-local, read-only apart from the daily maintenance, exit 0. For the developer, a troubleshooting Director and the platform SME; owners never need it |
| `workers_status()` / `workers_setup(verify?)` / `workers_declare(name?, provider?, credential?, base_url?, models?, capabilities?, note?, remove?, nothing_more?)` / `workers_declare(profile, likely?, absent?)` | The worker resource manager (§6.4), machine scope: what is found, declared and generated, with each generated profile's capability states; the explicit run that generates profiles (live checks only for `verify`); declarations and "nothing more"; or, with `profile`, the owner's reset of capabilities to `likely` or declaration of them `absent` (§6.1; Decision: [0084](../decisions/0084-capability-states.md)). `baton workers …` needs no project (Decision: [0077](../decisions/0077-workers-command.md)) |
| `help(topic?, search?)` | The manual (§13.10), read-only: no arguments lists the topics, `search` finds topics by words, `topic` returns one topic or, as `topic#anchor`, one section. The Director answers "how do I..." about Baton from it, never from memory (Decision: [0131](../decisions/0131-director-reads-the-manual.md)). Needs no owner decision (§13.7). `baton help` works outside a project; the Director's call needs one | `baton help` |
| `ui(detach?, idle_timeout?)` | The optional local setup page (§13.9): `baton ui` serves it in the foreground; the Director's `ui` starts it detached (or finds the running one) and returns its URL, which the Director gives the owner ("open this link to connect your accounts"). Never needed by any other call |
| `push(approved?, note?)` / `permission(action, detail?, approved?, note?)` | Action permissions (§13.7): the runtime pushes the current branch under `permissions.push`; the Director checks a tag, merge, deploy or force push before doing it. `ask` returns `needs_owner` (exit 4); the owner's approval is the same call with `approved` and their words |
| `init(bare?)` / `vendor(recipe_dir, approved?, note?)` / `upgrade(to?)` / `migrate(dry_run?)` | Setup and versioning (§14): `init` also vendors the starter recipes unless `bare` (§11.6); a vendoring that changes or reuses step ids returns `needs_owner` until repeated with `approved` and the owner's words; `upgrade` pins this runtime (the launcher runs `--to <v>` under `<v>`); `migrate` brings stored files below the readable window to the current formats |

No call lets the Director write step outputs, artifacts or events directly. Quiet by default: `detect`, `doctor`, `resume`, `status` and `check` print one line when healthy (a completed run's status leaves out its group progress).

### 13.2 CLI and MCP

- The CLI is the primary interface for a Director with a shell on the runtime host. It finds the project from `--project` / `BATON_PROJECT` or the nearest directory holding `.baton/project.yaml`; machine-local files come from `BATON_HOME` (default `~/.baton`).
- `baton recipe check <package> --ledger <file>` (§5.3; Decision: [0108](../decisions/0108-recipe-check-command.md)) is a helper that script gates run. No Director calls it, so it is CLI-only and has no MCP tool, like `workers` and `diag`-style machine commands. `baton workers connect <provider>` and `disconnect <name>` (§13.9; Decision: [0123](../decisions/0123-keys-keyring-then-file.md)) are CLI-only too, and a key never travels through MCP or the Director's conversation: the owner types it at a hidden prompt or pipes it on stdin (`--key-stdin`), or pastes it on the setup page.
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
- Choose workers only from `eligible`. Never edit profiles, preferences, permissions or the lockfile without the owner's instruction. Change a capability's state only with `workers_declare --profile <name> --likely|--absent <capability>`, and only when the owner asks.
- Never add, remove, skip or reorder steps or roles. Changes go through retriage or revise.
- Act only within the project's action permissions. `ask` means request it; `deny` means never.

## Each session
1. `detect`, then `doctor`. Silent when healthy; interrupt the owner only for a real problem. A `blocking` problem (e.g. `director_sandboxed`) comes before everything else: take it up with the owner first, relaying its `message` in conversation and offering its `options` by label, do no other work until it is resolved, then `detect` again.
2. `board`. For each run that needs you: `resume` it. If its lease is held elsewhere, report holder and expiry; take over only with the owner's approval.
3. New work is a new run (`start`, then triage). Never fold unrelated work into an active run. When the owner states a goal rather than a task ("I want to start a water vending business"), offer to frame it (`frame`), and use the owner's own words as its input.
4. A project with no work yet (just after `init`): ask the owner what they'd like help with, in their terms, and frame it. Nothing needs vendoring first: framing proposes from the recipes shipped with Baton and starts what the owner chooses. If no worker on this machine can do the framing step, say so plainly, with what `doctor` reports.
5. An owner who wants an existing project brought into Baton (`adopt`) needs a recipe first. Call `adopt` with none: it starts nothing and returns state `recipe_needed` with the steps. Write a short text summary of what the project already has (from `detect` and a top-level look at its layout, docs and tests; never read the files in depth), tell the owner what you assumed, and start a fit-check run with their idea and that summary as `context`. A `fits` verdict that names a recipe: `adopt` with it. A `fits` verdict with no recipe: start `recipe-builder` with the same summary, vendor what it produces once the owner accepts it, then `adopt`. Any other verdict, or the owner disagreeing: stop; nothing has been adopted.

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
- If they agree: `workers_status`, then tell them what was found (each helper, ready or not, and the fix it names) and ask whether they have other accounts to use, such as an OpenRouter account or an API key. Never take a key in conversation. Call `ui` and give them the link ("open this link to connect your accounts"): they paste the key there, and it is checked, stored safely and set up for them; or, if they prefer a terminal, they run `baton workers connect <provider>` themselves. When they say they are done, `workers_status` and tell them what is ready now.
- When they say there is nothing else, or decline setup, `workers_declare --nothing-more`. Don't ask again on this machine; revisit only when they ask.
- A live check costs a small model call each: run `workers_setup --verify <profile>` only when they agree to it.
- When `doctor`, `start` or framing's choice of parts carries `web_advice`, some of the work searches the web and no helper here can. Tell the owner plainly before that work starts, and strongly recommend its fix: install Claude Code or the Codex CLI, log in with their subscription, then `workers_setup`. Say why: those helpers can search the web, and Baton turns that on only for the steps that need it. In onboarding, give the same advice when the work they describe will need the web.
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
- About Baton itself (how to connect an account, what a setting or a message means, where something is): answer from the manual with `help` (`help --search <words>`, then `help <topic>`), never from memory, in the owner's terms. If the manual does not say, say so. The owner can read all of it in the setup page, which `ui` opens.
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
- **Unusual conditions** (§8.3; Decision: [0094](../decisions/0094-diagnostics-channel.md)). `doctor` runs the daily diagnostics maintenance and adds one warning, and nothing when healthy: `diagnostics: N unusual condition(s); see baton diag`, with `diag_unusual [{code, last_7d, baseline_per_day, first_seen?}]` in `--json`. A code is unusual when its count over the last 7 usage days (all projects on this machine) is at least 5 and either more than 3 times its per-usage-day rate over the 30 usage days before those, or it has no baseline (`first_seen`). `detect` leaves the warning out, as it does the wake warning (0061). `doctor --json` also carries `worker_logs {bytes, files, oldest_age_days}`: the raw worker output under `~/.baton/logs/`, reported and never pruned.
- **Web steps** (§6.3; change 2026-11-capability-confidence). When a vendored recipe has steps requiring `web_access` and no profile claims it in any state but `absent` (§6.1), `doctor` adds one warning, and `web_advice {steps, advice}`, recommending a subscription CLI (Claude Code or Codex) as the way to give those steps a worker, in plain words with why and how. `start` (and `start --from-plan`) carries the same `web_advice` for the recipe it starts, and framing's pending select decision carries it for the proposed parts whose recipes need the web; the Director passes it on before that work starts, and in onboarding (§13.3). Nothing is added when every web step has a worker, so a healthy `doctor` stays one line.
- **Worker setup** (§6.4; Decision: [0074](../decisions/0074-worker-research-and-resources-separate.md)). `worker_setup {setup_complete, nothing_more, offer_setup, generated, declared}` is read from `~/.baton/resources.yaml` and `~/.baton/workers/` alone (no discovery, no model call). `offer_setup` (not set up, and the owner has not said there is nothing to add) is structured only, never a warning, so a healthy result stays one line and `detect` stays quiet; the Director offers the setup conversation from it, once per machine (§13.3). With no ready worker, `doctor` reports a problem: before setup, pointing to `baton workers setup`; after it, pointing to `baton workers status`, without reopening the setup questions. `doctor` and `init` never run research or write profiles; `init`'s result carries the same `worker_setup` and a note while setup is still to do. `baton workers refresh` (CLI only, like `workers setup`) fetches the declared providers' model lists (§6.4, Decision: [0109](../decisions/0109-listing-sources.md)); it changes no profile, and caches the key endpoint's quota figures, which `worker_setup.quota` carries (a line per provider, dated). `baton workers disable|enable <resource>` switch an account's workers out of or back into routing (Decision: [0113](../decisions/0113-listing-filter-and-exclude.md)). `baton workers assess` and `baton workers check-overlay` (CLI only, Decision [0111](../decisions/0111-owner-run-assessment.md), [0120](../decisions/0120-assessment-recipe-fetched-pinned.md)) judge chosen models into the owner's overlay and validate an overlay file.
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

### 13.9 The local setup page (`baton ui`)

An optional client over the one core (§1.4 #13; Decisions: [0121](../decisions/0121-optional-ui-is-a-client.md), [0122](../decisions/0122-ui-scope-and-packaging.md), [0125](../decisions/0125-ui-adds-no-concept.md)). It lets the owner connect subscriptions and API accounts and manage the models Baton may use without editing a file. Baton works the same whether it exists or not: no runtime module imports `ui.py`, and the full suite passes without the front-end files.

**Process.** `baton ui [--no-open] [--port N] [--idle-timeout S]` serves a local app in the foreground, on port 47474 of `127.0.0.1` (`--port` changes it; 0 picks a free one), and opens the browser at `http://127.0.0.1:<port>/?t=<token>` (under WSL it asks the Windows side to open it). It exits when the owner presses Ctrl-C or closes the page with "Quit", or after `--idle-timeout S` if one is given (default: none, for `--detach` too); running `baton ui` again closes the running page first, so the new one is the current version. A launch can only extend the timeout, never shorten it: a restart keeps the running page's timeout unless the new one is longer (or 0, none), and when a requested timeout is not applied the caller is told (`timeout_honored: false`, `note`). The token is kept in `~/.baton/ui-token` (0600) and the cookie lasts a year, so a bookmark of the address keeps working across restarts. It is never started at login. The Director's `ui` action (MCP tool `ui`) always sets a timeout (default 15 minutes) and never restarts a running page: a second call returns the running one, extending its timeout if the new one is longer, and says so when it is not applied. `baton ui --detach` is the owner's detached start: no timeout unless given, restarts a running page. Both return `{url, pid, started, idle_timeout, timeout_honored, note?}`. The runtime state is one file, `~/.baton/ui.json` (0600: URL, pid, started), removed on exit.

**Safety, each checked on every request.**
- Loopback bind only.
- The one-time per-launch token (32 random bytes): the first `GET /?t=` sets it as an `HttpOnly`, `SameSite=Strict` cookie and redirects to `/` so it leaves the address bar; every other request needs the cookie (or `X-Baton-Token`), compared in constant time.
- The `Host` header must be `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding).
- A request with an `Origin` that is not the page's own is refused; state-changing requests (`POST`, `PUT`, `DELETE`) also need `X-Baton-UI: 1` and a JSON body. The server answers no CORS preflight and sends no `Access-Control-*` header.
- A stored key is never in a response, log, event or diagnostic: responses are built from `workers status`, which holds secret references only, and a key arriving in a request is held in memory only until it is stored. Request bodies are never logged.
- One machine's page manages that machine's resources only (§4.4).

**The API** (JSON; each route calls the same function as the CLI command in the right column, and the page holds no state of its own):

| Route | Does | CLI equivalent |
|---|---|---|
| `GET /api/state` | Providers (directory entries, declared accounts, harnesses with login state, version and, if not ready, the install or login step for this platform), models (every generated profile with provider, price, context, tier, capability states, last verified, switch) and preferences | `workers status --json` |
| `POST /api/accounts` | Connect: check the key with one cheap read, store it (§6.1), declare the resource, run setup | `workers connect` |
| `POST /api/accounts/<name>/key` | Replace the key: checked first, so a bad one leaves the old key working | `workers connect <name>` on an existing account |
| `DELETE /api/accounts/<name>` | Disconnect: remove the declaration; the stored secret too only with `forget_key` | `workers disconnect` |
| `POST /api/models/<profile>/enabled` | Turn a model off or on for routing (machine-level `exclude`) | `workers prefs --exclude / --include` |
| `POST /api/models/<profile>/verify` | The one live check | `workers setup --verify` |
| `PUT /api/preferences` | Cheapest or most-verified first, per-capability preferred models | `workers prefs` |
| `POST /api/quit` | End the process | |
| `GET /api/manual/tree`, `GET /api/manual/topic/<id>[?anchor=]`, `GET /api/manual/search?q=`, `GET /api/manual/context` | The manual reader (§13.10): the navigation, one topic (or one section of it) with its neighbours, a search, and the context map. Read-only: they serve only the shipped manual, by topic id, never a path from the request | `baton help` |

**Connecting an API account** checks the key with the provider's listing (or key-info) read, never a model call (§6.4 Listings), and says why in plain words when it is refused. Where the provider reports credit or free quota, the page shows it. Nothing about a key is shown after it is stored except where it is kept (keyring or file).

**Subscriptions (CLI harnesses)** are detected, not edited: for a harness that is installed but not logged in, the page shows the exact login command for this platform with a copy button; for one that is not installed, the install step. It re-checks when the owner returns to the page (`visibilitychange`). Starting a login from the page is out of scope (owner, 2026-11-10).

**Preferences.** The page edits the machine-level `~/.baton/preferences.yaml` (§8.4; Decision: [0124](../decisions/0124-machine-level-preferences.md)); per-project overrides remain a Director or CLI matter.

**Front end.** Plain HTML, CSS and JavaScript, no framework or build step, shipped as data (`baton/_data/ui`); it reads the API only. It lists providers, then models with filters (free only, maximum price, capability, tier, provider).

**Setup and Manual.** One header, one design system (light and dark following the system, phone to wide desktop, keyboard focus, accessible contrast) and a search box serve both parts (Decision: [0129](../decisions/0129-ui-serves-the-whole-manual.md)). `GET /manual` and `/manual/<part>/<slug>` serve the one page shell; its script reads the path and the manual routes above, and `#anchor` scrolls to a heading. The reader has a contents tree by part, the topic in a reading column, an on-this-page outline that follows the scroll, breadcrumbs, previous and next, and search by title, summary, heading and text (`/` focuses it). **Context help.** A "?" beside a part of Setup (a section, a provider's card, the capabilities column, the preference row) opens the manual's short answer for it in a side panel, with "Open the full guide" going to the reader at the same anchor. A control names a `data-help` id from `context.yaml` (`ui:`), or, on a provider's card, that provider's generated page (`providers.<name>`). A refusal the page shows carries "What does this mean?" when `context.yaml` (`errors:`) maps its code to a topic, and `baton workers connect` prints the same pointer (`More: baton help <topic>`, and `help` in `--json`). The page keeps no text of its own: it reads the map and the topics through the routes above. `Esc` or a click outside closes the panel and returns focus to the control.

`render.js` turns the Markdown subset (§13.10) into DOM nodes, never HTML strings, so nothing in a topic can inject markup; `tests/test_ui_render.py` runs it under node.

### 13.10 The manual and `baton help`

The owner's and the administrator's documentation: one corpus, `manual/`, written once and read three ways (Decisions: [0126](../decisions/0126-manual-one-corpus.md), [0127](../decisions/0127-manual-audiences-and-recipes.md), [0128](../decisions/0128-manual-markdown-subset-and-visual-bar.md), [0129](../decisions/0129-ui-serves-the-whole-manual.md), [0132](../decisions/0132-change-docs-name-their-manual-edits.md)). It adds no concept (§2). It ships as data (`baton/_data/manual`), so it matches the pinned runtime (§14.1) and works offline; nothing in the runtime requires it.

**Corpus.** `manual/<part>/<slug>.md` with parts `user/` (what an owner can and should do, by task), `providers/` (one generated page per entry of the provider directory, §6.4: where to get a key and what to expect), `recipes/` (one topic per shipped recipe, §5.7: its purpose, what the owner is asked, what it produces and needs, an example, and a parts table generated from the recipe itself, so the questions it lists cannot differ from the recipe's gates), `admin/` (configuration and operations for IT) and `reference/` (generated: commands, project settings, environment variables and diagnostic codes). A topic's front matter has `id` (`<part>.<slug>`), `title`, `audience` (`owner` for `user/` and `recipes/`, `admin` for the others), `summary`, and optionally `order` (reading order within its part), `related`, `aliases` (old topic ids) and `anchor_aliases` (old anchor to new). Three files sit beside the parts: `context.yaml`, `anchors.yaml` and `terms.yaml`.

**Markdown subset** (checked): `##` and `###` headings, each with an explicit anchor `{#lowercase-words}` unique in its topic (the title is the front matter's); paragraphs; bullet and numbered lists; tables; fenced code, bare or with one language; `**bold**`, `*em*`, `` `code` ``; links to `https://` or to a topic as `topic.id#anchor` (never a file path); notes as `> **Note:** ...` or `> **Warning:** ...`. No raw HTML. A guide topic opens with `## Here, now {#here-now}`: the short answer for the place the reader is in. Context help shows that section, and the guide reads the whole topic, so there is one text.

**Anchors never break.** `anchors.yaml` lists every anchor ever published (refreshed by `tools/manual_anchors.py`). A test fails when one stops resolving, directly or through `aliases` and `anchor_aliases`, and when a current anchor is missing from the list.

**Context map.** `context.yaml` says where each topic opens from: `errors` maps a refusal code to the topic that explains it, `ui` maps the setup page's `data-help` ids to topics; `commands` maps a CLI command to the topic its `--help` names (as `Manual: baton help <topic>`). Every command is either mapped or in `pending_commands`; that list only shrinks and is empty when the manual is complete.

**Generated topics** (Decision: [0133](../decisions/0133-generated-reference-is-committed.md)). `python tools/build_manual.py` writes `manual/providers/<name>.md` from the provider directory (`display_name`, `signup_url`, `base_url`, kind) and the hand-written quirks in `manual/provider-notes.yaml`; the files are committed and `tests/test_manual_gen.py` regenerates and compares, so a new or changed directory entry fails the build until the manual is regenerated. A local runtime's page says no key is needed. A recipe topic is written by hand in `manual/recipe-sources/<recipe id>.md` with a `%parts%` line, and the generator writes `manual/recipes/<recipe id>.md` with that line replaced by the table (parts and where the owner is asked, from `build_plan`); a shipped recipe with no source, or a table that no longer matches its recipe, is a stale manual.

**The generated reference** (`reference/`). `commands` is read from the CLI itself (every command, argument and option, with its help text and the manual topic that explains it; design § references are stripped); `project-settings` from the `ProjectConfig` model (key, type, default); `environment` and `diagnostics` from `manual/reference-notes.yaml`. The notes hold the words; the code holds the facts, and `manual_gen.coverage()` fails the build when they part: a command or option with no help text, a project setting, a `BATON_*` variable named in the source, or a `diag.note` code with no entry in the notes, and an entry for one the code no longer has. A table cell may hold `\|`. Doctor findings are free text, not codes, so they are described by hand in the troubleshooting topic.

**Checks** (`tests/test_manual.py`): the subset; every link, related and context pointer resolves; every `baton` example names real commands and options; owner-facing parts use none of `terms.yaml`'s internal terms (§2); the context map covers every command. `tests/test_docs.py` also requires a change doc in progress or done to name its manual edits.

**`baton help`.** `baton help` lists topics by part; `baton help <topic>[#anchor]` prints a topic or one section; `baton help --search <words>` finds topics; `--json` for tools.

The reader in `baton ui` (§13.9) serves every topic in full, read-only, and the Director reads the same topics through `help` (§13.1). The static site (below) is built from the same files.

**The static site** (Decision: [0130](../decisions/0130-manual-site-build.md)). `python tools/build_site.py [--out DIR] [--version X.Y]` (maintainers only, never shipped; it refuses to build a manual that does not validate) writes `<out>/<major.minor>/`: every topic at `manual/<part>/<slug>/` with its `#anchor`, the same page script and stylesheet as the setup page's Manual, and JSON files where the page reads the local API (`api/manual/tree.json`, `api/manual/topic/<id>.json`, `search.json`, searched in the browser with the server's scoring). Every page is under the version prefix (`window.BATON_BASE`), so one copy per released minor version can sit side by side; `versions.json` and an `index.html` forward to the newest. Choosing a host and publishing are the owner's separate step.
