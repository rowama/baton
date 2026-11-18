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
| `waits check` | Check each part that is waiting for something outside to happen, once, and exit: one that is met is taken in and the work goes on; one past its deadline goes to the owner. Safe to run at any time; two never overlap |
| `waits schedule` | Show the scheduler entry that would run `waits check` regularly on this computer; `--install` and `--remove` only when the owner asked ([scheduling the check](admin.scheduling-checks#here-now)) |

## The owner's decisions {#decisions}

| Command | What it does |
|---|---|
| `decide <run> <step> <decision> --note "<words>"` | Record an owner decision, with their words |
| `decide <run> <step> select --items <ids> --note "<words>"` | Record which proposed pieces of work the owner chose (a breakdown's `frame` step, a project review's `recommend` step); the chosen ones start, with the documents they build on |
| `interactions` | Every open request for the owner, in every active run (`--run` for one): its id, what it is about, its message and when it was opened or last changed. `status` and `board` give each pending decision's `request_id` too |
| `interaction <id>` | One request in full, in the `baton-interaction/1` format: the message, what to show, the choices with what each does, and the fields a choice needs (a blocked part's questions, the pieces to choose from) |
| `answer <id> --choice <choice> --note "<words>"` | Record the owner's answer to a request, as `decide` would; `--file <answer.yaml>` gives the fields (`{choice, values, words, partial, artifacts}`), `--via` names where the owner answered (default: in conversation, where the owner's words are required; `answer_file` when the owner filled the file in themselves). An answer with any `--via` but `conversation` is the owner's own: it is recorded with `recorded_by: owner` and needs no assistant's claim on the work, so it is never refused for one. A request that was answered, or changed since it was read, is refused (`interaction.stale`) and the open ones are named |
| `answer <id> --template` | Write an answer file to fill in (`answer-<id>.yaml`, or `--out <path>`): every field with its prefilled value and a comment saying what it is; nothing is recorded |
| `answer <id> --file <answer.yaml> --attach <name>=<path>` | A person's part: its fields as `values`, and each file it asks for by path; taken in as `submit` would take a result folder |
| `ui --request <id>` | Open the local page at one open request, for the owner to answer and confirm there (the assistant's `ui` call takes `request` too, and returns the page's link). Run in a project, `baton ui` also serves that project's requests at `/p/<name>/requests`, where `<name>` is `project.name` or the folder's name |
| `interaction <id> --item <item>` | One thing a request shows (the instructions, an input, what was produced, a file), by its item id: text inline, or the file's path |
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
| `guides` | The guides a quick run can follow: the project's own, in `guides/`, and the ones that come with Baton, each with what it produces; files in `guides/` that are not valid guides are named |
| `guides copy <id> --note "<words>"` | Copy a guide that comes with Baton into the project's `guides/` and record that the owner vouches for it, with their words, so a quick run can use it; never replaces a file already there |

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
