---
id: 2026-11-interaction-ui
title: "The owner can answer any of Baton's requests in a page of the local UI, the first graphical renderer"
status: in-progress
level: major
decisions: ["0169", "0170", "0171", "0121", "0122", "0125"]
touches: [design/director-interface.md, design/platform-and-security.md, design/layouts.md, design/persistence.md]
manual: [user/answer-questions-and-decide.md, admin/director-commands.md, admin/files-and-paths.md, admin/network-and-security.md, reference/commands.md]
---

# The owner can answer any of Baton's requests in a page of the local UI, the first graphical renderer

## Request

### Problem

After `2026-11-interaction-requests`, every ask of the owner is a renderer-neutral request, answered in conversation or through an answer file. Neither suits a long form or a table with a choice per row. The owner wants a graphical renderer shipped first (Decision [0169](../decisions/0169-interaction-requests.md), item 6), as the baseline: the best one to ship first, not the only one.

### Recommendation: a page of `baton ui`

The options considered:

| Option | For | Against |
|---|---|---|
| **A page of the existing local UI** (`baton ui`, §13.9) | No new dependency: standard-library server, plain HTML and JavaScript (Decision [0122](../decisions/0122-ui-scope-and-packaging.md)). Its safety model already exists: loopback only, per-launch token, Host and Origin checks. It works on every platform Baton supports, including WSL, where it opens the Windows browser. | It opens in a browser tab, not a window of its own. |
| A desktop window (pywebview) | A real window. | A new dependency, and on Linux a GTK or Qt backend; under WSL it needs WSLg. |
| NiceGUI | A richer toolkit, in Python, with a native-window mode. | A framework on FastAPI, Starlette and Uvicorn; it is HTML served by an HTTP server even in a native window, and its native mode uses pywebview ([NiceGUI: documentation](https://nicegui.io/documentation), [deployment](https://nicegui.io/documentation/section_configuration_deployment)). So it is a heavier route to the same page. |
| Flet | A richer toolkit, in Python. | A framework with its own runtime; not checked for this draft. |
| A terminal UI (Textual) | Stays in the terminal. | A new dependency; tables and images are poor in a terminal. |

**Recommended: a page of `baton ui`.** It is the only option that adds no dependency and reuses a safety model already built and reviewed. A desktop window can later wrap the same page (pywebview opens a URL), and a terminal renderer can be built on the same requests, so this choice closes nothing.

### Acceptance criteria

1. **The page renders any renderable request.** Message, context (text, tables, documents, images), the answer's fields as the subset allows (choices, text, numbers, booleans, several choices, groups, a table with a value per row), prefilled values, and decisions as buttons with their labels.
2. **Hints are honoured where they can be.** Order, groups, widgets, help and labels. A hint it does not know is ignored.
3. **A request it cannot render says so.** A request marked `renderable: false` shows the message and context and offers the answer file, with the command to use it.
4. **The owner confirms before anything is recorded.** The page shows what will be recorded and a Confirm button with an optional note, as `2026-11-interaction-requests` settles for confirmation, then calls `answer` with `via: local_page`.
5. **The page lists what is waiting.** A view of every open request in the project, newest first, each opening its own page.
6. **The Director can send the owner to a request.** `ui(request?)` starts the page, or finds the running one, and returns the link to that request, which the Director gives the owner ("open this link to match the receipt lines").
7. **The page is project-scoped where it needs to be.** `baton ui` started in a project, or with `--project <dir>`, serves that project's requests; started elsewhere it serves the machine's setup views only, as today.
8. **The page holds no state and adds no concept.** Every route calls the same function as the CLI (Decision [0125](../decisions/0125-ui-adds-no-concept.md)); closing the page loses nothing; the request stays open until answered.
9. **Same safety as today.** Every request checks loopback, token, Host and Origin as §13.9 does; context files are served only by request and item reference, never by a path from the browser.
10. **No script from recipes.** The page's own JavaScript ships with Baton; a request's `extensions.local_page` may only carry the declarative settings this change defines.
11. **Manual and design are current.**

### Open questions

All answered by the owner, 2026-11-18 (Decision [0171](../decisions/0171-interaction-ui-details.md)):

1. **One server per machine, or per project?** One for the machine, serving several projects; running in another project never restarts it. A project's address is lasting and readable: `/p/<name>/…`, from `project.name` in `project.yaml`, falling back to the folder's name (owner: "a platform trait doesn't define the project"). A request's id need not be readable.
2. **Does the list refresh on its own?** Yes, every 5 seconds while its tab is visible; a request's page learns of a change when Confirm is refused as stale.
3. **What may `extensions.local_page` hold?** Nothing in this change: the slot stays reserved by the format, and the way for a recipe to fill it waits for a recipe that needs it.
4. **Is a desktop window part of this change?** No; a later `baton ui --window`.
5. **Files for a person's step** (raised while refining): uploaded through the page to a private temporary folder, at most 100 MiB a file, and attached to the answer.
6. **The lease** (raised in Slice 1): the owner's own answer, given outside the Director's conversation, needs no Director's lease; it is recorded under the run lock with `recorded_by: owner` (item 7 of the decision).

### Out of scope

- **A terminal renderer, a desktop window, MCP elicitation:** later renderers on the same requests.
- **Project, run and recipe views** beyond the list of requests (Decision 0122 left them for later).
- **The delegate:** it answers requests through its own interface.

## Design

For the owner's approval, with the Request. Refined against `2026-11-interaction-requests` as built and Decision [0171](../decisions/0171-interaction-ui-details.md).

### Shape

- **Projects.** `baton ui` and `ui(request?)` run in a project register it with the running server (or the one they start): its name and folder in `~/.baton/ui-projects.yaml` (0600), kept across restarts. The name is `project.name` slugified, else the folder's name; a second folder claiming a name already held by another live folder gets `-2`; a folder that moved keeps its name. A registered folder that no longer holds a Baton project is shown as gone, never served. `baton init` writes `project: {name: <folder name>}`. The browser names a project only by its name, never a path.
- **Routes** (JSON, each calling the CLI's function, under the same safety checks as §13.9):

  | Route | Does | CLI equivalent |
  |---|---|---|
  | `GET /api/projects` | The projects the server knows, with their count of open requests | |
  | `GET /api/p/<name>/interactions` | Open requests of the project, newest first | `interactions --json` |
  | `GET /api/p/<name>/interactions/<id>` | One request | `interaction <id> --json` |
  | `GET /api/p/<name>/interactions/<id>/context/<item>` | One context item's content | `interaction <id> --item <item>` |
  | `POST /api/p/<name>/interactions/<id>/files/<file>` | Upload one declared file (raw body, at most 100 MiB) to a private temporary folder; returns a handle | |
  | `POST /api/p/<name>/interactions/<id>/answer` | Record the confirmed answer: `{choice, values, words, note, files: {name: handle}}` | `answer <id> --file … --attach … --note … --via local_page` |

- **Pages.** `/p/<name>/requests` (the list) and `/p/<name>/requests/<id>` (one request), in the same shell and design system as Setup and Manual; the header links to the requests of the known projects. A stale or answered request's page says so and links to the current one, if any.
- **Rendering** is one generic renderer of the subset (0170, item 2), written once, building DOM nodes, never HTML strings: a field per property, a table for a list of objects (fixed rows when the prefill or context gives them, otherwise rows the owner adds within `minItems`/`maxItems`), groups from hints, choices as buttons with their effects. It honours the closed hints (0170, item 3), ignores the rest and `extensions`, and validates before Confirm; the runtime validates again on `answer`. A request with `renderable: false` shows the message and context and the commands for the answer file.
- **Confirmation.** Confirm shows the summary (the `summary` hint's fields, or all), the chosen effect, and an optional note; `answer` records `via: local_page` (0170, item 1).
- **Context served by reference.** Text and tables inline. A `document` or `image` item is fetched by request and item id only; every response has a fixed content type and `X-Content-Type-Options: nosniff`. PNG, JPEG, GIF and WebP show inline; text and Markdown show as plain text; anything else, SVG included, is a download.
- **Uploads.** Each file is kept under a private temporary folder (0700) named by the request, removed after the answer is recorded or refused, or when the server exits; only the request's declared file names are accepted.
- **The owner's answer needs no lease.** `answer` with any `via` but `conversation` records under the run lock with `recorded_by: owner`, and neither needs, claims nor renews a Director's lease (0171, item 7); the answer file gains this too.
- **Director.** `ui(request?)` returns the setup page's `url` as today and this project's `requests_url`; with a request, `url` is that request's page. It never restarts a running server, and refuses a request that is not open. `baton ui --request <id>` does the same from a terminal. The skill offers the page for a request with a table, more than a few fields, files to give, or an image to look at.

### Doc edits

- `design/director-interface.md` §13.9 (projects, the request pages, routes, uploads), §13.1 (`ui(request?)`), §13.3 (when the Director offers the page).
- `design/platform-and-security.md`: context items served by reference; uploads.
- `design/layouts.md` §4.4: `~/.baton/ui-projects.yaml`; the front end's new files.
- `design/persistence.md` §10.4: `project.name`; §10.2: the owner's own answer and the lease.

### Manual edits

- `user/answer-questions-and-decide.md`: *Answering on a page* (the link, the checks, Confirm with a note, files from your computer, pictures and documents, the project's lasting address and its list, newest first and updating itself, `baton ui` in the project's folder, what the page cannot show); a changed question on the page.
- `admin/director-commands.md`: `ui --request`, the project's requests at `/p/<name>/requests`; an answer with any `--via` but `conversation` is the owner's own; `interactions` gives when each was opened.
- `admin/files-and-paths.md`: `~/.baton/ui-projects.yaml`.
- `admin/network-and-security.md`: the request pages name projects and items, never paths; fixed types for what they show; files the owner gives.
- `reference/commands.md`: `baton ui --request` (regenerated).

### Decisions

- [0169](../decisions/0169-interaction-requests.md), [0170](../decisions/0170-interaction-requests-details.md) (accepted): requests are renderer-neutral; this is the first GUI renderer.
- [0121](../decisions/0121-optional-ui-is-a-client.md), [0122](../decisions/0122-ui-scope-and-packaging.md), [0125](../decisions/0125-ui-adds-no-concept.md) (accepted): the local UI's place, packaging and limits.
- [0171](../decisions/0171-interaction-ui-details.md) (accepted): the answers to the five open questions.

## Plan

### Slice 1: answering one request

- **Outcome:** the Director gives the owner a link, and the owner answers a decision or a form in the page.
- **Criteria:** `project.name` and its fallback; projects registered and kept across restarts; the list, request and answer routes; the generic renderer for fields and choices; hints; Confirm with summary and note; `answer` with `via: local_page`, needing no lease; stale requests; a non-renderable request offers the file; `ui(request?)`; the safety checks on the new routes.
- **Effort:** M

### Slice 2: tables, context, files and the list page

- **Outcome:** the owner answers a table-per-row request with images in view, gives a person's step its files, and sees every open request.
- **Criteria:** context items served by reference with fixed types; uploads and their cleanup; the list page, newest first, and its polling; the Director skill; the rest of the manual. (Tables came with the generic renderer in Slice 1.)
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Written from the owner's direction of 2026-11-18 (Decision 0169, item 6), with the recommendation to build the first graphical renderer as a page of the existing local UI. No code changed.
- **Owner decision:** 2026-11-18, "Include a gui renderer as the baseline option either as part of this or as a separate proposal."
- **Accepted:** No; proposal only. Four open questions await the owner.

### Open questions answered

- **Summary:** The owner answered the five open questions (Decision 0171). Three suggested answers changed when the draft was checked against `2026-11-interaction-requests` as built: one server serving several projects (a restart would break §13.9's no-restart rule for the Director), no `extensions.local_page` (nothing fills it yet), and file uploads (new). The owner chose a project name in `project.yaml`, falling back to the folder's name, for a lasting address. Design and Plan refined. No code changed.
- **Accepted:** Not yet; awaiting the owner's approval of Request and Design.

### Slice 1: answering one request

- **Summary:** The owner answers a decision or a form on the local page, from a link the Director gives. `project.name` (written by `init` from the folder's name; else the folder's name) names the project in the page's addresses; `~/.baton/ui-projects.yaml` keeps name to folder across restarts (a moved folder takes its name back, a renamed project lets its old one go, a second of the same name gets `-2`). New routes `GET /api/projects`, `GET /api/p/<name>/interactions[/<id>[/context/<item>]]`, `POST …/answer` call the CLI's functions; the launch link keeps the page's path. `requests.js` is the generic renderer of the subset (fields, choices, groups, hints, tables with fixed or added rows), checks values before Confirm in plain words, and confirms with a summary and a note. The owner's own answer (any `via` but `conversation`) is recorded with `recorded_by: owner` and needs no Director's lease (Decision 0171, item 7, asked and decided during this slice: the page would otherwise be refused while the Director holds the run). `ui(request?)` (MCP, engine) and `baton ui --request` give the request's page; a request that is not open is refused.
- **Modules:** `ui.py` (registry, routes, page paths), `engine.py` (`ui(request)`, owner answers without the lease: `_owner_via`, `recorder`, `_hold`), `frame.py` (recorder), `project.py` (`project.name`, `project_name`, init), `cli.py` (`ui --request`, registration), `mcp_server.py`; front end `ui/requests.js`, `index.html`, `app.js`, `manual.js`, `app.css`.
- **Docs:** `director-interface.md` §13.1 (`ui`, `answer`), §13.9 (*Requests*); `persistence.md` §10.2, §10.4; `platform-and-security.md` §15.2; `layouts.md` §4.4; Decision 0171 item 7.
- **Tests:** `test_ui_requests.py` (name and fallback, registry, routes, owner answer and stale refusal, page paths and launch link, context items without paths, the Director's `ui(request)`); `test_ui_requests_js.py` under node (order, labels, groups, controls per field, validation messages, empty fields, summary rows, fixed table rows); `test_interactions.py` (the owner's answer needs no lease; conversation still does). Also driven by hand in jsdom against a live server (in a scratch folder, not a dependency): a gate, a blocked step's questions and a person's table, each recorded with `via: local_page`.
- **Not yet:** files (a person's step with files offers the answer file), images and documents as more than text, the list's refresh and order, the Director skill.

### Slice 2: files, context, the list and the Director

- **Summary:** A person's step's declared files are chosen on the page and uploaded at Confirm (`POST …/files/<file>`, raw body, at most 100 MiB, only declared names) into a private temporary folder, then attached to the answer by handle; uploads go once the answer is recorded or refused, and all when the page closes. Context items are served as themselves by id (`…/context/<item>/raw`) with fixed types, `nosniff` and a `sandbox` policy: PNG, JPEG, GIF and WebP inline, text as plain text, anything else (SVG included) a download; the page shows images inline and offers documents as text or a download. `interactions` gives each request's `opened` time; the list is newest first, shows the other known projects, and refreshes every 5 seconds while visible; the *Waiting for you* tab appears on every page once a project is known. The Director skill (and §13.3) offers the page for a table, many fields, files or something to look at, and does not confirm again what the owner confirmed there.
- **Modules:** `ui.py` (`Raw`, `_context_raw`, `Uploads`, `_upload`, files in `_answer`, upload header and size checks), `engine.py` (`opened`, `_opened_at`); front end `ui/requests.js` (images, downloads, file pickers and upload, the list), `app.css`; `skills/baton-director/SKILL.md`.
- **Docs:** `director-interface.md` §13.1 (`interactions`' `opened`), §13.3 (the skill), §13.9 (raw context, uploads, the list); `platform-and-security.md` §15.2.
- **Tests:** `test_ui_requests.py` (an uploaded photo answers a person's step and lands in its result; undeclared, wrong-type, empty and too-large uploads refused; uploads removed after a refused and a recorded answer; the following gate's photo served inline as `image/png`, its output as plain text; each media type's fixed type; `opened` in the list); `test_ui_requests_js.py` (newest first; required files named).
