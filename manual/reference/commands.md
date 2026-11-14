---
id: reference.commands
title: Command reference
audience: admin
summary: Every baton command and option.
order: 10
generated: true
---

## Here, now {#here-now}

Every command takes `--json` for machine-readable output. Global options: `--project <path>` (or `BATON_PROJECT`), `--director <id>` (or `BATON_DIRECTOR`). Exit codes are in [setting up an assistant](admin.directors#exit-codes).

## baton abandon {#baton-abandon}

Abandon a run.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--reason <str>` | Why the work item is abandoned. |
| `--json` | Machine-readable output. |

## baton adopt {#baton-adopt}

Adopt this project: start the adoption run (research, then triage per work item, then one baseline decision), or show its progress.

Explained in the manual: [Bring in an existing project](user.bring-an-existing-project#here-now).

| Argument or option | What it does |
|---|---|
| `recipe <str>` | Recipe ref (vendored) or recipe directory (vendored first). Without one, nothing starts and the steps to find or build it are shown. |
| `--crosswalk <str>` | A crosswalk shipped with the recipe (by name) or a crosswalk file. |
| `--scope <str>` | Limit research to this path (repeatable). |
| `--json` | Machine-readable output. |

## baton ask-sme {#baton-ask-sme}

Consult an expert by subject; the runtime assembles what it sees.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `subject <str>` | project \| platform \| process |
| `question <str>` | The question, as the owner asked it. |
| `--ref <str>` | A reference the expert gets, by name (repeatable); see `baton sme-eligible`. |
| `--run <str>` | The run the question is about. |
| `--mode <str>` | relay (dispatch and record an answer) \| handoff (a prompt to paste elsewhere). |
| `--worker <str>` | Expert profile (default: the first eligible). |
| `--contact <str>` | A person consulted through the expert (name, role, how to reach them). |
| `--wait` | Block until the worker finishes and its result is recorded. |
| `--timeout <float>` | With --wait: seconds to wait at most. |
| `--json` | Machine-readable output. |

## baton attest {#baton-attest}

Record the owner's attestation of a project file, so processes can build on it (owner-approved).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `path <str>` | A file in the project, relative to its root. |
| `--note <str>` | The owner's words, recorded verbatim. |
| `--json` | Machine-readable output. |

## baton bind {#baton-bind}

Bind a role of a run's recipe to project documents, as the owner confirmed (owner-approved).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `role <str>` | A project document role the run's recipe declares. |
| `paths <str>` | The project document(s) to bind, as `documents` lists them; several only for a role that takes several. |
| `--note <str>` | The owner's confirmation, in their words (recorded verbatim). |
| `--json` | Machine-readable output. |

## baton board {#baton-board}

Every non-terminal run: position, running and queued work, owner decisions owed, lease holder.

Explained in the manual: [Check on your work](user.check-on-your-work#here-now).

| Argument or option | What it does |
|---|---|
| `--needs-me` | Only runs waiting on an owner decision. |
| `--json` | Machine-readable output. |

## baton cancel {#baton-cancel}

Withdraw a dispatch queued for the working tree.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `--json` | Machine-readable output. |

## baton check {#baton-check}

Repository consistency for pre-commit and CI: one ERROR line per problem, exit 0 when clean.

Explained in the manual: [Troubleshooting and diagnostics](admin.troubleshooting#here-now).

| Argument or option | What it does |
|---|---|
| `--strict` | Treat drift of published deliverables as an error. |
| `--json` | Machine-readable output. |

## baton decide {#baton-decide}

Record the owner's decision, verbatim.

Explained in the manual: [Answer questions and decide](user.answer-questions-and-decide#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `ref <str>` | What is being decided: the step path awaiting the owner, an instance path at its iteration limit, `<step>`#`<finding>`, skip:`<seq>`, publish:`<step>`.`<artifact>` or drift:`<step>`.`<artifact>`. |
| `decision <str>` | approve \| reject (gates); retry \| abandon (escalations); accept-risk (a finding); confirm (a runnable stale step); acknowledge (a skip notice); overwrite \| keep \| alternate (a publish conflict); leave (drift). |
| `--note <str>` | The owner's words, recorded verbatim. |
| `--path <str>` | alternate: the project path to publish at instead. |
| `--answers <path>` | retry of a blocked step: a JSON file [{id, answer, owner_words}] of the owner's confirmed answers (keep it outside .baton/). |
| `--partial` | With --answers: record a deliberately partial set (a needed question left open). |
| `--items <str>` | select (a framing run's frame gate): the chosen part ids, comma-separated; empty for none. |
| `--json` | Machine-readable output. |

## baton detect {#baton-detect}

The project's situation, each active run's situation and machine readiness. One line when healthy.

Explained in the manual: [Troubleshooting and diagnostics](admin.troubleshooting#here-now).

| Argument or option | What it does |
|---|---|
| `--json` | Machine-readable output. |

## baton diag {#baton-diag}

What Baton has been working around on this machine: counts per code against the usual rate, unusual first.

Explained in the manual: [Troubleshooting and diagnostics](admin.troubleshooting#here-now).

| Argument or option | What it does |
|---|---|
| `--since <str>` | A number of usage days, or a date (YYYY-MM-DD). Default: the last 7 usage days. |
| `--code <str>` | Only codes starting with this prefix. |
| `--run <str>` | Only records of this run. |
| `--records` | Show the raw records, newest last. |
| `--limit <int>` | With --records: the newest N (0: all). |
| `--json` | Machine-readable output. |

## baton dispatch {#baton-dispatch}

Build the step's packet and hand it to the worker; returns once it has started (or, with --wait, finished).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `--worker <str>` | Worker profile name. |
| `--wait` | Block until the worker finishes and its result is recorded. |
| `--json` | Machine-readable output. |

## baton disposition {#baton-disposition}

Record a finding's disposition; it takes effect at the next review of that finding.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path whose review recorded the finding. |
| `finding <str>` | Finding id (or `<gate>`:`<id>`). |
| `value <str>` | fixed \| rejected \| accepted-risk |
| `--evidence <str>` | fixed: commit or file:line; rejected: file:line or path::test; accepted-risk: the owner's decision id. |
| `--json` | Machine-readable output. |

## baton doctor {#baton-doctor}

Machine readiness: lockfile, profiles (env, executables, a no-op run each), uncovered steps. One line when healthy.

Explained in the manual: [When something is wrong](user.when-something-is-wrong#here-now).

| Argument or option | What it does |
|---|---|
| `--profile <str>` | Check only this worker profile. |
| `--no-run` | Skip the no-op round trips (no model calls). |
| `--json` | Machine-readable output. |

## baton documents {#baton-documents}

The project's documents: deliverables accepted steps published, and files the owner attested.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `--json` | Machine-readable output. |

## baton eligible {#baton-eligible}

Workers that may do a step, in preference order, with every exclusion's reasons.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `--json` | Machine-readable output. |

## baton establish-baseline {#baton-establish-baseline}

Apply the reviewed baseline: the owner's one adoption decision.

Explained in the manual: [Bring in an existing project](user.bring-an-existing-project#here-now).

| Argument or option | What it does |
|---|---|
| `adoption <str>` | The adoption run id. |
| `--note <str>` | The owner's decision, in their words (recorded verbatim). |
| `--json` | Machine-readable output. |

## baton explain {#baton-explain}

Process facts only: what is done, where the run is, what remains at this level and what other levels would change.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--json` | Machine-readable output. |

## baton feedback {#baton-feedback}

Record process feedback; a skipped blocking gate or approval is surfaced to the owner at once.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `kind <str>` | friction \| skipped_step \| waste \| confusing |
| `text <str>` | What happened. |
| `--run <str>` | The run it concerns. |
| `--step <str>` | The step it concerns. |
| `--gate <str>` | skipped_step: the gate skipped (index or type). |
| `--informed-owner` | skipped_step: the owner was told at the time. |
| `--json` | Machine-readable output. |

## baton frame {#baton-frame}

Frame a goal into pieces of work the owner chooses from: start the framing run, or show the one awaiting its decision.

Explained in the manual: [Start with a goal](user.start-with-a-goal#here-now).

| Argument or option | What it does |
|---|---|
| `--note <str>` | The owner's goal, in their own words (recorded verbatim). |
| `--json` | Machine-readable output. |

## baton help {#baton-help}

The manual: list its topics, print one, or search it. Reads the manual that ships with this version.

Explained in the manual: [Using this manual](user.using-the-manual#here-now).

| Argument or option | What it does |
|---|---|
| `topic <str>` | A topic, like user.connect-an-account, or one section of it: user.connect-an-account#key-refused. |
| `--search <str>` | Find topics that mention these words. |
| `--json` | Machine-readable output. |

## baton ingest-revision {#baton-ingest-revision}

Accept an edited published file as a human revision.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path whose published artifact was edited. |
| `artifact <str>` | Artifact name. |
| `--note <str>` | The owner's decision, in their own words (recorded verbatim). |
| `--feed <str>` | revision_inputs (only human_revision.* inputs) \| dependents (also not-yet-started dependents' artifact inputs). |
| `--json` | Machine-readable output. |

## baton init {#baton-init}

Create .baton/ with defaults in a project (and the starter recipes, unless --bare). Existing files are kept.

Explained in the manual: [Getting started](user.getting-started#here-now).

| Argument or option | What it does |
|---|---|
| `path <path>` | Project root (default: current directory). |
| `--bare` | Vendor no starter recipes (fit-check is vendored by default). |
| `--json` | Machine-readable output. |

## baton lease {#baton-lease}

Claim, release or take over a run's lease. Take over only with the owner's approval.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `action <str>` | claim \| release \| take-over |
| `--reason <str>` | Why (required for take-over). |
| `--json` | Machine-readable output. |

## baton mcp {#baton-mcp}

Serve the Director API as MCP tools: over stdio (started by the harness), or over HTTP on loopback (started by the owner).

Explained in the manual: [Setting up an AI assistant (the Director)](admin.directors#here-now).

| Argument or option | What it does |
|---|---|
| `--http` | Serve streamable HTTP instead of stdio (needs a token in ~/.baton/mcp.yaml). |
| `--host <str>` | With --http: loopback address to bind. |
| `--port <int>` | With --http: port. |

## baton migrate {#baton-migrate}

Bring stored files in formats this runtime no longer reads directly to the current formats.

Explained in the manual: [Install, versions and upgrades](admin.install-and-versions#here-now).

| Argument or option | What it does |
|---|---|
| `--dry-run` | Show what would be migrated; change nothing. |
| `--json` | Machine-readable output. |

## baton note {#baton-note}

Keep a note the owner asked for, word for word, in the project's notes file (offered once).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `text <str>` | The owner's words, verbatim. |
| `--keep-file <str>` | The owner's answer to the notes-file offer: yes \| no. |
| `--note <str>` | With --keep-file: the owner's words. |
| `--json` | Machine-readable output. |

## baton permission {#baton-permission}

Check (and record) an action the Director takes outside the runtime: allow, ask (exit 4) or deny (exit 1).

Explained in the manual: [What Baton may do to your repository](user.what-baton-may-do#here-now).

| Argument or option | What it does |
|---|---|
| `action <str>` | tag \| merge \| deploy \| force_push |
| `--detail <str>` | What exactly will be done (recorded). |
| `--approved` | The owner approved this `ask` action (with --note). |
| `--note <str>` | With --approved: the owner's words, recorded verbatim. |
| `--json` | Machine-readable output. |

## baton plan {#baton-plan}

Validate a recipe and print its step and gate table: per level, or for a recipe with axes, what each rating adds.

Explained in the manual: [Recipes, vendoring and trust](admin.recipes-and-vendoring#here-now).

| Argument or option | What it does |
|---|---|
| `recipe <str>` | Recipe directory, or a vendored recipe (id or id@version). |
| `--level <str>` | Show only this complexity level. |
| `--rating <str>` | For a recipe with axes: one axis=value per axis; prints the table for that combination. |
| `--json` | Machine-readable output. |

## baton platform-fact {#baton-platform-fact}

Record a durable platform fact (.baton/platform/facts.md).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `text <str>` | The fact, e.g. 'codex is under nvm v22 on the runtime host'. |
| `--source <str>` | Where it comes from. |
| `--json` | Machine-readable output. |

## baton platform-incident {#baton-platform-incident}

Platform incidents: opened automatically for platform and unknown failures; resolving readies the step once.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `action <str>` | list \| show \| resolve |
| `incident <str>` | Incident id (show, resolve). |
| `--fix <str>` | With resolve: what was fixed. |
| `--json` | Machine-readable output. |

## baton promote-sme {#baton-promote-sme}

Bring an expert's answer into the work, with the owner's agreement.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `consultation <str>` | Consultation id. |
| `target <str>` | decision \| fact \| lesson \| proposal \| revision |
| `--note <str>` | The owner's agreement, in their own words (recorded verbatim). |
| `--text <str>` | What to promote, if not the answer as given. |
| `--turn <int>` | Which turn's answer (default: the latest answered). |
| `--artifact <str>` | revision: the published artifact to revise, `<step_path>`.`<name>`. |
| `--from <str>` | revision: the expert's artifact to use as the content. |
| `--feed <str>` | revision: revision_inputs \| dependents. |
| `--json` | Machine-readable output. |

## baton push {#baton-push}

Push the current branch, if project.yaml permissions allow this kind of change (docs only, verified, other).

Explained in the manual: [What Baton may do to your repository](user.what-baton-may-do#here-now).

| Argument or option | What it does |
|---|---|
| `--approved` | The owner approved this `ask` action (with --note). |
| `--note <str>` | With --approved: the owner's words, recorded verbatim. |
| `--json` | Machine-readable output. |

## baton recipe {#baton-recipe}

Checks for a recipe being built.

Explained in the manual: [Recipes, vendoring and trust](admin.recipes-and-vendoring#here-now).

### baton recipe check {#baton-recipe-check}

Gate helper: no open ledger entry, every confirmed entry has the owner's words, no instance fact in the recipe, and discovery recorded and handed on.

Explained in the manual: [Recipes, vendoring and trust](admin.recipes-and-vendoring#here-now).

| Argument or option | What it does |
|---|---|
| `package <path>` | The recipe folder to check. |
| `--ledger <path>` | The requirements ledger (JSON). |
| `--require-discovery` | The ledger file must carry `discovery` records. |
| `--json` | Machine-readable output. |

## baton recipes {#baton-recipes}

List vendored recipes.

Explained in the manual: [Recipes, vendoring and trust](admin.recipes-and-vendoring#here-now).

| Argument or option | What it does |
|---|---|
| `--json` | Machine-readable output. |

## baton record {#baton-record}

Print a step's record.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `--json` | Machine-readable output. |

## baton resume {#baton-resume}

Verify a run, rebuild its cache, reconcile in-flight work and claim its lease.

Explained in the manual: [Long-running work and coming back](user.long-running-work#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--json` | Machine-readable output. |

## baton retriage {#baton-retriage}

Rerun triage; the new level applies, once the owner approves it, only to work not yet started.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--reason <str>` | Why the work's complexity should be assessed again (recorded, given to the worker). |
| `--json` | Machine-readable output. |

## baton retry {#baton-retry}

Start a new attempt of a step whose previous attempt was not accepted.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `--worker <str>` | Worker profile (default: the previous attempt's). |
| `--guidance <str>` | Additive guidance for the new attempt. |
| `--wait` | Block until the worker finishes and its result is recorded. |
| `--json` | Machine-readable output. |

## baton revise {#baton-revise}

Correct an earlier step of this run (owner-approved): new attempt, dependents become stale.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path of an accepted step to correct. |
| `--reason <str>` | Why the step is being revised (recorded, given to the worker). |
| `--json` | Machine-readable output. |

## baton sme {#baton-sme}

A consultation: its turns, the expert's answers and artifacts, and what it waits for.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `consultation <str>` | Consultation id. |
| `--wait` | Block until the worker finishes and its result is recorded. |
| `--timeout <float>` | With --wait: seconds to wait at most. |
| `--json` | Machine-readable output. |

## baton sme-eligible {#baton-sme-eligible}

Profiles that may answer as this subject's expert, in order.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `subject <str>` | project \| platform \| process |
| `--run <str>` | The run (its recipe may set the expert's requirements). |
| `--json` | Machine-readable output. |

## baton sme-followup {#baton-sme-followup}

The next turn of a consultation: earlier turns plus new refs, a question or attachments.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `consultation <str>` | Consultation id. |
| `--question <str>` | A follow-up question. |
| `--ref <str>` | A reference the expert gets, by name (repeatable); see `baton sme-eligible`. |
| `--attach <str>` | A file the owner supplies, e.g. a person's reply (repeatable). |
| `--worker <str>` | Expert profile (default: the previous turn's). |
| `--wait` | Block until the worker finishes and its result is recorded. |
| `--timeout <float>` | With --wait: seconds to wait at most. |
| `--json` | Machine-readable output. |

## baton sme-handoff {#baton-sme-handoff}

Print a copy-and-paste prompt to continue the consultation with the expert directly (refused when that cannot work).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `consultation <str>` | Consultation id. |
| `--json` | Machine-readable output. |

## baton start {#baton-start}

Start a run (a work item) and claim its lease.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `recipe <str>` | Vendored recipe (id or id@version). |
| `--inputs <str>` | Run inputs: a JSON object, or @file.json. |
| `--title <str>` | Work item title (default: inputs.title). |
| `--from-plan <str>` | A part of a process plan (`<part>` or `<framing run>`/`<part>`), started as proposed. |
| `--bind <str>` | `<role>`=`<path>`: bind a project document to a role the recipe declares (repeat for each role, and for each document of a role that takes several). Needs --note. |
| `--note <str>` | With --bind: the owner's confirmation, in their words (recorded verbatim). |
| `--json` | Machine-readable output. |

## baton status {#baton-status}

Where a run is: ready and running steps, owner decisions owed, lease.

Explained in the manual: [Check on your work](user.check-on-your-work#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--json` | Machine-readable output. |

## baton submit {#baton-submit}

Hand in a manual or external worker's result: intake and gates run now.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `--result <path>` | Result directory to copy in (default: the attempt's result/). |
| `--json` | Machine-readable output. |

## baton summary {#baton-summary}

Print the run summary.

Explained in the manual: [Check on your work](user.check-on-your-work#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--json` | Machine-readable output. |

## baton trace {#baton-trace}

Print the run's recent events, one line each.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--limit <int>` | Show the last N events (0: all). |
| `--json` | Machine-readable output. |

## baton ui {#baton-ui}

Open the local setup page: connect accounts and choose the models Baton may use. Stays on one address you can bookmark; running it again restarts it.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `--no-open` | Do not open the browser; print the link. |
| `--port <int>` | A port on 127.0.0.1 (default: 47474, so the page can be bookmarked; 0 picks a free one). |
| `--idle-timeout <float>` | Seconds without a request before the page closes itself (default: none; a running page is only ever extended). |
| `--detach` | Start it in the background and print the link (what a Director does). |
| `--stop` | Close the setup page that is running (for one started with --detach). |
| `--json` | Machine-readable output. |

## baton upgrade {#baton-upgrade}

Pin a runtime version in baton.lock and re-vendor the skills; nothing else changes.

Explained in the manual: [Install, versions and upgrades](admin.install-and-versions#here-now).

| Argument or option | What it does |
|---|---|
| `--to <str>` | Runtime version (default: the launcher's own). |
| `--json` | Machine-readable output. |

## baton vendor {#baton-vendor}

Vendor a recipe into .baton/recipes/ and pin it in baton.lock (changed or reused step ids need the owner: exit 4).

Explained in the manual: [Recipes, vendoring and trust](admin.recipes-and-vendoring#here-now).

| Argument or option | What it does |
|---|---|
| `recipe_dir <path>` | Recipe package directory. |
| `--approved` | The owner approved the flagged step-id changes. |
| `--note <str>` | With --approved: the owner's words, recorded verbatim. |
| `--json` | Machine-readable output. |

## baton wait {#baton-wait}

Block until dispatched work finishes and is recorded (for attached Directors).

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `--dispatch <str>` | Dispatch id (default: all running work of the run). |
| `--timeout <float>` | Give up after this many seconds (exit 1). |
| `--json` | Machine-readable output. |

## baton waive {#baton-waive}

Waive one gate occurrence (owner decision): the failed one the step holds, else the next.

Explained in the manual: [The commands an assistant uses](admin.director-commands#here-now).

| Argument or option | What it does |
|---|---|
| `run <str>` | Run id. |
| `step <str>` | Step path. |
| `gate <str>` | Gate index, gate type (when the step has one), independence or protected. |
| `--reason <str>` | The owner's decision, recorded verbatim. |
| `--json` | Machine-readable output. |

## baton workers {#baton-workers}

This machine's workers: what is found, declared and generated.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

### baton workers assess {#baton-workers-assess}

Judge chosen models into your overlay (fetches the recipe for this version; ).

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `models <str>` | model_ids to judge (as `baton workers status` lists them). |
| `--profile <str>` | Your worker profile that does the research (web_access, file_write, structured_output, technical_reasoning). |
| `--timeout <float>` | Seconds to wait for the worker. |
| `--json` | Machine-readable output. |

### baton workers check-overlay {#baton-workers-check-overlay}

Say why Baton would refuse an overlay file (the validator `workers assess` gives its worker; ).

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `file <path>` | An overlay file to validate. |
| `--json` | Machine-readable output. |

### baton workers connect {#baton-workers-connect}

Connect an API account: check the key, keep it in the keyring or an owner-only file, declare it and set up its models.
The key is never an argument; a bad replacement key leaves the working one in place.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `provider <str>` | The provider, e.g. openrouter, openai, anthropic. |
| `--name <str>` | The account's name (default `<provider>`-main). An existing name replaces its key. |
| `--base-url <str>` | For an endpoint that speaks the OpenAI API. |
| `--key-stdin` | Read the key from standard input (otherwise it is asked for, hidden). |
| `--no-key` | A local endpoint that needs no key. |
| `--json` | Machine-readable output. |

### baton workers declare {#baton-workers-declare}

Add, change or remove a resource discovery cannot find, or say there is nothing more.
With --profile: reset a capability to likely, or declare it absent.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `name <str>` | The resource's name, e.g. openrouter-main. |
| `--provider <str>` | Its provider, e.g. openrouter; `openai_compatible` for any endpoint that speaks the OpenAI API (needs --base-url). |
| `--credential <str>` | secret:`<name>` (never the key itself, ). |
| `--base-url <str>` | The endpoint of an `openai_compatible` resource (ends in /v1). |
| `--model <str>` | Limit to this model_id (repeatable). |
| `--capability <str>` | A machine-dependent capability it has here (repeatable). |
| `--note <str>` | A note kept with the resource. |
| `--remove` | Remove this resource. |
| `--nothing-more` | Record that there is nothing more to add (or undo that). |
| `--profile <str>` | Set capability states on this profile instead (with --likely / --absent). |
| `--likely <str>` | Reset this capability to likely, so it is tried again (repeatable). |
| `--absent <str>` | Declare this capability absent on the profile (repeatable). |
| `--json` | Machine-readable output. |

### baton workers disable {#baton-workers-disable}

Stop routing to a declared account's workers. Nothing is deleted; `enable` restores them (0113).

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `name <str>` | A declared resource, e.g. openrouter. |
| `--json` | Machine-readable output. |

### baton workers disconnect {#baton-workers-disconnect}

Remove an account. Its workers stay recorded, flagged as no longer offered, and routing stops using them.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `name <str>` | The account's name, as `baton workers status` lists it. |
| `--forget-key` | Also delete the stored key (otherwise it is kept). |
| `--json` | Machine-readable output. |

### baton workers enable {#baton-workers-enable}

Route to a declared account's workers again.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `name <str>` | A declared resource, e.g. openrouter. |
| `--json` | Machine-readable output. |

### baton workers prefs {#baton-workers-prefs}

Show or change this machine's routing preferences (~/.baton/preferences.yaml; a project's own file overrides it; ).

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `--exclude <str>` | Turn this worker off for routing on this machine (repeatable). |
| `--include <str>` | Turn it back on (repeatable). |
| `--cheapest-first` | Which to rank first among eligible workers. |
| `--prefer <str>` | CAPABILITY=worker1,worker2: preferred in that order; CAPABILITY= clears it (repeatable). |
| `--json` | Machine-readable output. |

### baton workers refresh {#baton-workers-refresh}

Fetch the model lists of the declared providers; `baton workers setup` then turns new models into workers.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `--json` | Machine-readable output. |

### baton workers setup {#baton-workers-setup}

Generate profiles for what this machine has and the owner declared; new models appear only here.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `--verify <str>` | Live-check this profile (repeatable; costs one small model call each). |
| `--verify-all` | Live-check every generated profile. |
| `--json` | Machine-readable output. |

### baton workers status {#baton-workers-status}

What is discovered, declared and generated, and whether setup is complete. Changes nothing.

Explained in the manual: [Connect an API account](user.connect-an-account#here-now).

| Argument or option | What it does |
|---|---|
| `--json` | Machine-readable output. |
