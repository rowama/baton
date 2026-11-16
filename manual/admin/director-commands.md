---
id: admin.director-commands
title: The commands an assistant uses
audience: admin
order: 100
summary: What each command that the Director calls does, grouped by purpose. The assistant runs these; an owner seldom does.
related: [admin.directors, reference.commands]
---

## Here, now {#here-now}

An owner talks to an assistant, and the assistant runs these commands (or the same calls as MCP tools, with the same names and arguments). They are listed here so an administrator can read a transcript or script around them. Every option is in the [command reference](reference.commands#here-now).

## Seeing where things stand {#seeing}

| Command | What it does |
|---|---|
| `detect` | The project's situation, each active run's situation and machine readiness; one line when healthy |
| `board` | Every active piece of work: position, running and queued work, owner decisions owed |
| `status <run>` | One run: ready and running parts, owner decisions owed, who holds it |
| `explain <run>` | Process facts only: what is done, where the run is, what remains and what other sizes would change |
| `trace <run>` | The run's recent events, one line each |
| `record <run> <step>` | A part's readable record |
| `summary <run>` | The finished work, in order |

## Doing the work {#doing}

| Command | What it does |
|---|---|
| `start <recipe>` | Start a run (a piece of work) and claim it |
| `start --from-plan <part>` | Start a part left for later in a plan (a breakdown's or a project review's), as it was proposed; a part that builds on project documents needs `--note "<words>"` |
| `vendor project-review --note "<words>"` | Add a recipe shipped with Baton to the project by its name, with the owner's words as their approval (how a project review is added the first time) |
| `eligible <run> <step>` | The helpers that may do a part, in preference order, with every exclusion's reason |
| `dispatch <run> <step>` | Build the part's inputs and hand them to a helper; returns once started (`--wait` blocks) |
| `wait <run>` | Block until dispatched work finishes and is recorded |
| `submit` | Hand in a person's result: intake and checks run now |
| `cancel` | Withdraw a dispatch queued for the working tree |
| `retry` | Start a new attempt of a part that was not accepted |

## The owner's decisions {#decisions}

| Command | What it does |
|---|---|
| `decide <run> <step> <decision> --note "<words>"` | Record an owner decision, with their words |
| `decide <run> <step> select --items <ids> --note "<words>"` | Record which proposed pieces of work the owner chose (a breakdown's `frame` step, a project review's `recommend` step); the chosen ones start, with the documents they build on |
| `waive` | Waive one failed check, as an owner decision |
| `disposition` | Record how a review finding was handled |
| `revise` | Correct an earlier part of a run, with approval: a new attempt, and what depended on it becomes stale |
| `retriage` | Rerun the sizing; the new size applies, once approved, only to work not yet started (`--axis` names the ratings to look at again) |
| `abandon` | Abandon a run |
| `ingest-revision` | Accept an edited, published file as a human revision |
| `lease` | Claim, release or take over a run's hold; taking over needs the owner's approval |

## Project documents {#documents}

| Command | What it does |
|---|---|
| `documents` | The project's documents: files a finished part published, and files the owner vouched for, each with when it was accepted and whether it was edited or deleted since |
| `attest <path> --note "<words>"` | Record that the owner vouches for a file in the project, with their words, so later work can build on it; again on the same file records a newer version |
| `bind <run> <role> <path>… --note "<words>"` | Give a run the project document the owner confirmed for one of its recipe's roles; at start, `start <recipe> --bind <role>=<path> --note "<words>"` does the same |

## Project policy {#policy}

| Command | What it does |
|---|---|
| `policy` | The rules every run follows (rating floors, governing recipes, permissions), each with the owner's decision that last changed it; `unconfirmed` when `project.yaml` was edited by hand or never recorded |
| `policy set --note "<words>"` | Change a rule with the owner's words: `--floor RECIPE.AXIS=VALUE`, `--remove-floor`, `--governing "WORK=RECIPE"`, `--remove-governing`, `--permission ACTION=allow\|ask\|deny`; records it, rewrites `project.yaml` and commits both |
| `policy confirm --note "<words>"` | Record a hand edit of the policy (or a policy never recorded) as the owner's decision |

## Experts {#experts}

| Command | What it does |
|---|---|
| `ask-sme <subject> "<question>"` | Consult an expert by subject: `project`, `platform` or `process` |
| `sme-eligible` | The profiles that may answer as a subject's expert |
| `sme`, `sme-followup`, `sme-handoff` | Read a consultation, take its next turn, or print a prompt to continue with the expert directly |
| `promote-sme` | Bring an expert's answer into the work, with the owner's agreement |
| `platform-fact`, `platform-incident` | Record a durable platform fact; list and resolve platform incidents |
| `feedback`, `note` | Record process feedback; keep a note the owner asked for, word for word |

## Where an assistant starts {#start}

Each session an assistant runs `detect`, then `doctor`, then `board`. It interrupts the owner only for a real problem or a decision that is theirs. See [setting up an assistant](admin.directors#here-now).
