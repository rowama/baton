---
id: "0171"
title: "Request pages: one server for the machine serving several projects at a lasting address from the project's name, a list that refreshes itself, no local-page extensions yet, no desktop window, files uploaded through the page, the owner's own answer needs no lease"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"1-concur as long as the project's URL key is bookmarkable and human friendly; i.e., same obvious url for a project's lifetime. Request id doesn't need to be human readable. 2-concur. 3-Expound on extensions and hints. 4-concur. 5-concur.\"; then: \"1-option b. a platform trait doesn't define the project; fallback to directory name. 3-concur\"; on the lease, Slice 1: \"yes. a.\""
sections: ["§10", "§10.2", "§13.1", "§13.9", "§4.4"]
---

# 0171. Request pages: one server for the machine serving several projects at a lasting address from the project's name, a list that refreshes itself, no local-page extensions yet, no desktop window, files uploaded through the page, the owner's own answer needs no lease

## Context

`2026-11-interaction-ui` builds the first graphical renderer of interaction requests (Decision [0169](0169-interaction-requests.md), item 6) as pages of `baton ui` (§13.9). The draft raised four open questions; checking it against the finished `2026-11-interaction-requests` changed three suggested answers and raised a fifth:

- Restarting `baton ui` in another project, as first suggested, would break §13.9's rule that the Director's `ui` never restarts a running page (the owner may be part way through connecting an account).
- Nothing fills a request's `extensions`: every request is built with `{}`, and a recipe's hints file accepts only the closed set of Decision [0170](0170-interaction-requests-details.md), item 3. Whether a table may add rows already follows from the schema.
- A person's step may ask for files, which a renderer offers through its own picker (0170, item 11).

`project.yaml` holds no name of the project; its `project:` section holds the project's variables (`test_command`, …).

While building Slice 1 a sixth question came up: a run's changes are made under its lease (§10.2), held by the Director working on it, so an answer given on the page (a process with its own identity) would be refused with "run is leased to …" exactly when the Director sends the owner there. The answer file run in a terminal had the same gap. `answer` only records the decision, refreshes the run's records and makes the checkpoint commit; it starts nothing (a person's step's submission lets queued workspace dispatches the Director already made proceed, as `submit` does).

## Decision

1. **One server for the machine, several projects.** One `baton ui` process and port serve the machine's views and the requests of every project made known to it; a project becomes known when `baton ui` or the Director's `ui(request)` runs in it. Running in another project never restarts the server.
2. **A lasting, readable address per project.** A project's pages are at `/p/<name>/…`, where `<name>` is `project.name` from `project.yaml` (slugified), falling back to the project folder's name when it has none: a trait of the machine (where the folder is) does not define the project. `baton init` writes `project: {name: <folder name>}`. The machine remembers which folder each name is (`~/.baton/ui-projects.yaml`), so a bookmark keeps working across restarts and after the folder moves; a second project of the same name on one machine gets `-2`. A request's id need not be readable.
3. **The list refreshes itself:** every 5 seconds while its tab is visible. A request's page does not poll: a request that changed while open is refused on Confirm as stale, and the page says so and shows the current one.
4. **No `extensions.local_page` in this change.** The page renders from the schema and the closed hints and ignores `extensions`. The slot stays reserved by the format (0169, item 3); the way for a recipe to fill it is not built until a recipe needs a setting the hints cannot express, and then only that setting.
5. **No desktop window in this change.** A later `baton ui --window` may use pywebview when it is installed.
6. **Files through the page.** The page offers a file picker for a person's step's declared files; the browser uploads each to the local server, which keeps it in a private temporary folder (0700), at most 100 MiB a file, and passes its path to `answer` as an attachment; the copy is removed once the answer is recorded or refused.
7. **The owner's own answer needs no lease.** An answer through any renderer but the Director's conversation (`via` other than `conversation`: the local page, the answer file) is the owner's: recorded under the run lock with `recorded_by: owner`, it neither needs, claims nor renews a Director's lease, and the Director holding the run finds the decision on its next call. A lease coordinates Directors, and the owner is not one; the run lock orders the writes and a request's id refuses an answer to what has changed. A lease stays coordination, not security.
