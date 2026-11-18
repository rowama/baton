---
id: 2026-11-interaction-ui
title: "The owner can answer any of Baton's requests in a page of the local UI, the first graphical renderer"
status: proposed
level: major
decisions: ["0169", "0121", "0122", "0125"]
touches: [design/director-interface.md, design/platform-and-security.md, design/layouts.md]
manual: []
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

Each has a suggested answer, assumed until the owner decides.

1. **One server per machine, or per project?** *Suggested:* one `baton ui` process serves the machine's views and one project's requests; starting it in another project restarts it there, as `baton ui` already restarts itself. *Rationale:* it keeps the single-process, single-port model of §13.9.
2. **Does the page refresh on its own when a new request appears?** *Suggested:* the list polls `GET /api/interactions` every few seconds while open. *Rationale:* simple, needs no push channel, and the page is local.
3. **What may `extensions.local_page` hold?** *Suggested:* column widths and whether a table may add rows; nothing else in the first version. *Rationale:* a small, declarative set that cannot become a back door for script.
4. **Is a desktop window part of this change?** *Suggested:* no; a later option `baton ui --window`, using pywebview when it is installed. *Rationale:* it adds a dependency for little gain over a browser tab, and the page works without it.

### Out of scope

- **A terminal renderer, a desktop window, MCP elicitation:** later renderers on the same requests.
- **Project, run and recipe views** beyond the list of requests (Decision 0122 left them for later).
- **The delegate:** it answers requests through its own interface.

## Design

For the owner's approval, with the Request. It follows `2026-11-interaction-requests` and is refined against that change's final form.

### Shape

- **Routes** (JSON, calling the CLI's functions):

  | Route | Does | CLI equivalent |
  |---|---|---|
  | `GET /api/interactions` | Open requests of the project | `interactions --json` |
  | `GET /api/interactions/<id>` | One request | `interaction <id> --json` |
  | `GET /api/interactions/<id>/context/<item>` | One context item's content | `interaction <id> --item <item>` |
  | `POST /api/interactions/<id>/answer` | Record the confirmed answer | `answer <id> --file … --note …` |

- **Pages.** `/requests` (the list) and `/requests/<id>` (one request), in the same plain front end as the setup page.
- **Rendering** is one generic renderer of the subset, written once: a field per property, a table for a list of objects, groups from hints. It validates against the schema before Confirm, and the runtime validates again on `answer`.
- **Director.** `ui(request?)` returns `{url}` with the request's page; the skill says when to offer it: a request with a table, more than a few fields, or an image to look at.

### Doc edits

- `design/director-interface.md` §13.9 (the request pages, routes and project scope), §13.1 (`ui(request?)`), §13.3 (when the Director offers the page).
- `design/platform-and-security.md`: context items served by reference.
- `design/layouts.md`: the front end's new files.

### Manual edits

To be listed when the change is accepted. Expected: the owner's topic on answering Baton's questions your way, `admin/director-commands.md`, `reference/commands.md`.

### Decisions

- [0169](../decisions/0169-interaction-requests.md) (accepted): requests are renderer-neutral; this is the first GUI renderer.
- [0121](../decisions/0121-optional-ui-is-a-client.md), [0122](../decisions/0122-ui-scope-and-packaging.md), [0125](../decisions/0125-ui-adds-no-concept.md) (accepted): the local UI's place, packaging and limits.
- The four open questions above become one record when the owner answers them.

## Plan

Slices as proposed; refined once the Request and Design are approved and `2026-11-interaction-requests` is done.

### Slice 1: answering one request

- **Outcome:** the Director gives the owner a link, and the owner answers a decision or a form in the page.
- **Criteria:** the routes; project scope; the generic renderer for fields and choices; hints; Confirm with summary and note; `answer` with `via: local_page`; a non-renderable request offers the file; the safety checks on the new routes.
- **Effort:** M

### Slice 2: tables, context and the list

- **Outcome:** the owner answers a table-per-row request with images in view, and sees every open request.
- **Criteria:** tables with fixed and added rows; context tables, documents and images served by reference; the list and its polling; `extensions.local_page`; the Director skill; the manual.
- **Effort:** M

## Log

### Proposal drafted

- **Summary:** Written from the owner's direction of 2026-11-18 (Decision 0169, item 6), with the recommendation to build the first graphical renderer as a page of the existing local UI. No code changed.
- **Owner decision:** 2026-11-18, "Include a gui renderer as the baseline option either as part of this or as a separate proposal."
- **Accepted:** No; proposal only. Four open questions await the owner.
