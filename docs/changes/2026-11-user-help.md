---
id: 2026-11-user-help
title: "One manual serves every owner and administrator question, in context from the page, as a guide, and as a reference, and stays current with every change"
status: done
level: major
manual: [recipes/fit-check.md, recipes/software-feature.md, recipes/backyard-project.md, recipes/recipe-builder.md, recipes/baton-adopt.md, recipes/baton-frame.md, user/what-is-baton.md, user/getting-started.md, user/using-the-manual.md, user/start-with-a-goal.md, user/bring-an-existing-project.md, user/answer-questions-and-decide.md, user/check-on-your-work.md, user/long-running-work.md, user/how-you-want-to-be-told.md, user/what-baton-may-do.md, user/when-something-is-wrong.md, providers/openrouter.md, provider-notes.yaml, user/connect-an-account.md, user/connect-a-subscription.md, user/choose-models.md, admin/secrets.md, context.yaml, anchors.yaml, terms.yaml, admin/accounts-and-costs.md, admin/director-commands.md, admin/directors.md, admin/files-and-paths.md, admin/install-and-versions.md, admin/machine-settings.md, admin/network-and-security.md, admin/platform-notes.md, admin/project-settings.md, admin/recipes-and-vendoring.md, admin/secrets.md, admin/troubleshooting.md, reference/commands.md, reference/diagnostics.md, reference/environment.md, reference/project-settings.md, reference-notes.yaml]
decisions: ["0126", "0127", "0128", "0129", "0130", "0131", "0132", "0133"]
touches: [principles.md, design/director-interface.md, design/layouts.md, design/versioning.md, design/testing.md]   # §0, §2, §13.2, §4.1, §14.1, §19
---

# One manual serves every owner and administrator question, in context from the page, as a guide, and as a reference, and stays current with every change

> **Proposed and accepted, 2026-11-11.** The owner concurred with every suggested answer and added three directions: write the manual sections for the current recipes; the web UI must look clean, professional and modern; and `baton ui` serves the manual fully. They are folded in below and recorded as decisions 0126 to 0133.

## Request

### Problem

Baton's help today is the CLI's `--help`, the root `README.md`, and the design docs in `docs/`. The design docs are written for the people who build Baton, and the README covers install and a tour. None of it answers the questions an owner or an IT administrator has when using Baton:

- **Where am I, and what do I do here?** The setup page (§13.9) has an Accounts section, a Models table and a Subscriptions list. An owner looking at it who wants OpenRouter working has nowhere to ask "how?" from that spot. The answer (what OpenRouter is, where to get a key, what the page checks, what "free only" means, why a model shows "unverified") is spread across the CLI, the design and the owner's memory.
- **What can I do with Baton at all?** There is no task-oriented guide: no "start a project", "answer a step's question", "pick cheaper models", "come back after a week".
- **What do I tell IT?** Machine paths, where secrets are kept, network destinations, what runs on the machine, how versions are pinned, what `doctor` messages mean: this is written down only as design.

The manual will also grow with every change, so keeping it current has to be a property of how changes are made here, not a thing someone remembers.

### Acceptance criteria

- One body of documentation, the **manual**, is written once and read three ways: **in context** (a help control next to each part of the setup page opens the topic for where the owner is, with the steps for that place), as a **guide** (what an owner can and should do, by task), and as a **reference** for administrators (configuration, files, paths, security, platform, troubleshooting, generated command and setting references).
- Every topic and every heading in it has a stable anchor. A link such as `help/admin/secrets#where-keys-are-kept` is the same in the setup page, in `baton help`, and on a documentation web site built from the same files. An anchor, once published, never stops resolving (renames leave an alias).
- From the setup page, the owner gets to "make OpenRouter work" in one click from the Accounts section, and the topic is correct for the provider the owner is looking at.
- `baton help` lists, searches and prints topics in the terminal, and every CLI command's `--help` names the topic that explains it. The Director can read the manual (read-only) so it answers an owner's "how do I…" from the manual and not from its own inference (§1.1 #5, §12).
- The manual's text for what the program states (commands and their options, configuration keys, files and paths, environment variables, doctor findings, diagnostics codes) is generated from the code's own definitions, so it cannot drift; the prose around it is covered by checks (below).
- A change that alters what an owner sees or an administrator configures cannot be finished without its manual edits. This is enforced by a test, not by memory, and written into AGENTS.md and the change template.
- The manual ships with the runtime and is the version of the manual for the pinned runtime (§14.1). It works offline.
- `baton ui` serves the whole manual: a full reader (navigation, search, outline, links by anchor) beside Setup, read-only and offline, in a clean, professional, modern design (light and dark, phone to wide desktop, accessible). The context panel opens the same topics in the same renderer.
- Every shipped recipe (`fit-check`, `software-feature`, `backyard-project`, `recipe-builder`, `baton-adopt`, `baton-frame`) has a manual topic saying what it is for, what the owner will be asked, what it produces and what it needs; a test fails for a shipped recipe with none.
- The owner-facing part uses the owner's words, not Baton's internal vocabulary (§2, §13.8), and a check reports internal terms used there.

### Open questions

All seven are answered (owner, 2026-11-11: concur with each suggestion), with three additions:

1. Location: top-level `manual/`. [0126](../decisions/0126-manual-one-corpus.md)
2. Audiences: user, admin and, added by the owner, a topic for each current recipe; recipe-author docs later. [0127](../decisions/0127-manual-audiences-and-recipes.md)
3. Rendering: restricted Markdown subset, small shipped renderer, to a clean, professional, modern standard. [0128](../decisions/0128-manual-markdown-subset-and-visual-bar.md)
4. Web site built from the same files, hosting separate; and, added by the owner, `baton ui` serves the manual fully. [0130](../decisions/0130-manual-site-build.md), [0129](../decisions/0129-ui-serves-the-whole-manual.md)
5. The Director's read-only `help` action. [0131](../decisions/0131-director-reads-the-manual.md)
6. `manual:` on every change doc, from this change on. [0132](../decisions/0132-change-docs-name-their-manual-edits.md)
7. Generated reference committed and checked for drift. [0133](../decisions/0133-generated-reference-is-committed.md)

## Design

### The shape: one corpus, three entry points

The three layers the owner asked for are three *views* of one set of files. Writing three corpora would triple the upkeep and guarantee disagreement.

```
manual/
  user/        what an owner can and should do, by task        (guide)
  admin/       configuration, files, security, platform, ops   (reference and runbooks)
  recipes/     one topic per shipped recipe: purpose, what you will be asked, what it makes
  reference/   generated: commands, settings, paths, env, doctor, diagnostics, recipe step tables
  context.yaml where in the UI / CLI / doctor output -> which topic and anchor
  anchors.yaml every anchor ever published, with its current location (aliases)
```

- **Topic file** (`manual/<part>/<slug>.md`): Markdown with front matter: `id` (permanent, e.g. `user.connect-an-account`), `title`, `audience` (`owner` or `admin`), `summary` (one sentence, shown in lists and search), `related`, and `aliases` and `anchor_aliases` (old ids and anchors). Where a topic opens from is kept in one place, `context.yaml`. One topic is one task or one question, a screen or two long.
- **Anchors.** Every heading carries an explicit, stable id (`## Where keys are kept {#where-keys-are-kept}`); the URL form is `<part>/<slug>#<anchor>`. Ids are never renamed in place: a rename adds the old id as an alias, and a test fails if a published anchor stops resolving (the same rule as § numbers, which never renumber).
- **A topic's opening is written for context.** Its first section, `## Here, now` ... is the short answer, what to do on this screen. Below it is the full story. In context help the panel opens at the short answer with "More" going to the rest of the topic; the guide reads the same topic from the top. There is no separate context text to keep in step.

### Layer 1: context

- Each part of the setup page carries a `data-help` id (`ui.accounts`, `ui.accounts.connect`, `ui.models.filters`, `ui.models.unverified`, ...). A "?" control beside it opens a side panel over the page with the topic for that id, with links to related topics and a "Open the full guide" link. The panel is part of the front end; it reads the manual only through the local API.
- **Per-provider topics are generated** from the provider directory (§6.4, Decision [0117](../decisions/0117-provider-directory.md)): sign-up URL, what the key looks like, what the page checks, whether the provider reports credit, and which models are free. The hand-written part of a provider topic is only the provider's quirks (for OpenRouter: free models rate limits, the `:free` suffix, that credit shows only after a key check). So the OpenRouter topic opens from the OpenRouter card, and a new directory entry gets a topic page with no writing.
- State-aware hints: the page already knows when a harness is not logged in or a key was refused. Its message carries the anchor of the topic that explains that state (a refused key links `user.connect-an-account#key-refused`). The messages come from the same core functions as the CLI (§13.9), so `baton workers connect` and `doctor` print the same `help:` pointer.
- Routes (§13.9's table gains two, both `GET`, read-only): `/api/help/<id>` and `/api/help/search?q=`.

### The manual reader in `baton ui` (all layers, read in full)

`baton ui` becomes two parts, **Setup** and **Manual**, under one header with a search box (Decision [0129](../decisions/0129-ui-serves-the-whole-manual.md)). The Manual is a full reader over every shipped topic, so an owner or IT person can read the whole manual from the same local page, offline, without a web site.

- **Layout:** a left navigation tree (User guide, Recipes, Admin guide, Reference), the topic in a comfortable reading column, an on-this-page outline on the right (collapsing on narrow screens), breadcrumbs, previous and next, and search across titles, summaries and text (a small index built when `baton ui` starts). Deep links are real URLs, `/manual/<part>/<slug>#<anchor>`, so a link from the context panel, a `baton help <topic> --open`, or a bookmark all land on the same place.
- **Visual bar** ([0128](../decisions/0128-manual-markdown-subset-and-visual-bar.md)): a considered type scale and measure, restrained colour, clear code blocks with copy buttons, distinct notes and warnings, light and dark themes following the system, layouts from phone to wide desktop, visible keyboard focus and accessible contrast. The Setup page gets the same design system, so the two read as one product. Slice 2 is accepted only once the owner has seen it running.
- **Same safety, same state:** the reader is read-only; its routes (`GET /api/manual/tree`, `/api/manual/<part>/<slug>`, `/api/manual/search?q=`) serve only shipped files under the manual, never a path from the request, and every §13.9 safety check applies unchanged (token, Host and Origin). No state is kept. The idle timeout counts reading as activity.
- **Still optional:** the manual is also readable with `baton help` and on the site, and nothing requires the page to exist (§1.4 #13).

### Layer 2: user guide (owner)

Task-oriented, in the owner's words (§13.8), and about what the owner can and should do, not how Baton works inside. Outline (the Plan fixes the exact list):

- Getting started: install, first project, what to expect (the Director, you, the steps you will be asked about).
- Connecting what does the work: subscriptions, API accounts (a topic per provider, generated), keys and where they are kept, replacing and removing a key.
- Choosing models: cheapest vs. most-verified, free models, turning a model off, "check it works".
- Doing work: bringing an existing project in, framing a goal, starting work, answering a step's question, reviewing, what "waiting on you" means, coming back later or from another machine.
- When something is wrong: what a message means, what to try, when to ask IT.

### Recipes: one topic per shipped recipe

Owner-facing, in the same plain words ([0127](../decisions/0127-manual-audiences-and-recipes.md)). Each of the six shipped recipes (`fit-check`, `software-feature`, `backyard-project`, `recipe-builder`, and the built-in `baton-adopt` and `baton-frame`) gets a topic that says: what the process is for and when to choose it; what you will be asked and when (the owner's decisions and gates, in plain terms); what it produces and where it goes; what it needs (capabilities, in terms of which kinds of worker); a worked example; and what can go wrong. A table of steps, gates and complexity levels is generated from the recipe itself (§5.5), so it cannot disagree with the recipe. A test fails for a shipped recipe with no topic, or one whose generated table is out of date.

### Layer 3: admin guide

For an administrator or IT, written from the machine's side:

- Install and the launcher; version pinning; what is installed where (§4, §14.1); upgrading and trying a version.
- Where everything lives: `~/.baton/`, the project's `.baton/`, files and permissions, what is safe to commit (§4.3, §4.4).
- Secrets: keyring, file, environment; what the setup page stores and shows (§6.1, §13.9).
- Network: the destinations Baton and its workers contact; the setup page binds loopback only and exposes nothing (§15.2).
- Accounts and providers; model access, quotas, costs and who pays for what.
- Platform notes: Windows, WSL, macOS, Linux; what runs as a process, what stays resident (nothing).
- Security model for review: isolation, protected files, the Director's permissions (§13.7, §15.2).
- Troubleshooting: `doctor` and `check` findings, diagnostics (§8.3), exit codes.
- Reference (generated): every command and option; every configuration key; every path; every environment variable; every doctor finding and diagnostic code.

### `baton help` and the Director

- `baton help` lists topics by part; `baton help <id-or-anchor>` prints one; `baton help --search <words>`; `--json` for tools. It reads the manual shipped with the pinned runtime, so it matches the installed version.
- Every command's `--help` ends with `Manual: baton help <id>`, taken from `context.yaml`; a test fails for a command with none.
- The Director's `help` action (CLI and MCP) returns a topic's text. The Director skill is told to answer "how do I..." from it. It is read-only and does not need an owner decision (§13.7).

### Keeping it current (the part that matters most)

Documentation that depends on discipline decays. Each of these is a failing test or a template field, so the next change cannot skip it:

1. **Change doc field.** The template gets `manual:` in its front matter and a `### Manual edits` heading under Design, next to `### Doc edits`. A change cannot move to `done` with `manual:` empty; `manual: none: <why>` is allowed for changes with no visible effect, and the owner sees the reason in the register review. AGENTS.md's "Doing a change" says each slice's commit includes its manual edits.
2. **Generated reference.** Commands and options (from the CLI definitions), settings and file formats (from the JSON schemas and models), paths (from one list in the code), environment variables, doctor findings and diagnostic codes are generated into `manual/reference/` by `tools/build_manual.py`. A test regenerates and compares, and fails on drift. A new CLI option, key or diagnostic code with no description is a failing test.
3. **Coverage.** A test fails when: a CLI command has no manual topic; a `data-help` id in `ui/` has no topic; a topic names a `context` that no longer exists; a doctor finding or diagnostic code is not in the troubleshooting reference.
4. **Executable examples.** A fenced block marked `baton` is parsed, and each command and option in it must exist in the current CLI, so an example cannot name a renamed flag.
5. **Links and anchors.** Every link and anchor in the manual resolves; every published anchor in `anchors.yaml` still resolves (directly or by alias). This extends `tests/test_docs.py`.
6. **Vocabulary.** `manual/user/` must not use the internal terms from §2 (a short list in `manual/terms.yaml`), because owners never need them; `manual/admin/` may.
7. **Ground rule.** §0 gets a rule: a change that alters what an owner sees or an administrator configures edits the manual in the same slice; §19 (Definition of Done) replaces its README list with the manual's coverage list. The root README shrinks to install, a short tour and a pointer to the manual.

### Versioning and the web site

- The manual is shipped data (`baton/_data/manual`, like `ui`), versioned with the runtime and pinned with it (§14.1), so a project on an older pin reads the older manual. `baton help` and the page need no network.
- `tools/build_site.py` (maintainers only, like `tools/worker-research`) turns the same files into a static site with the same URLs and anchors, and builds one copy per released minor version. Choosing a host and publishing are outside this change.

### Concept budget

The manual adds no concept: it is documentation, and `baton help` an interface, like the setup page (Decision [0125](../decisions/0125-ui-adds-no-concept.md)). §2's interfaces note records it, as §0 rule 8 requires for a new command.

### Doc edits

- `principles.md` §0: new rule (manual edited in the same slice as the change); §2: `baton help` and the manual add no concept.
- `design/director-interface.md` §13.9: Setup and Manual parts, the manual reader, the help panel, `data-help` ids and the read routes; §13.2: `help` action (CLI and MCP) and the `Manual:` footer on `--help`; a new section after §13.9, "The manual and help": the corpus, anchors, context map, routes, `baton help`, and the keep-current checks.
- `design/layouts.md` §4.1: `manual/` and `tools/build_manual.py`, `tools/build_site.py`; shipped as `baton/_data/manual`.
- `design/versioning.md` §14.1: the manual is versioned and pinned with the runtime.
- `design/testing.md` §19: the manual replaces the README coverage list; its checks are part of the definition of done.
- `docs/README.md`: `manual/` row in the map, the new section in the § index. `AGENTS.md`, `TEMPLATE.md`: the `manual:` field and Manual edits heading. `tests/test_docs.py`: the register-style check for `manual:`.

### Manual edits

The change creates the manual; its own edits are the slices below. Slice 1 seeds four topics for the setup page's current sections (`user/connect-an-account`, `user/connect-a-subscription`, `user/choose-models`, `admin/secrets`) with the context map, the anchor registry and the terms list.

### Decisions

[0126](../decisions/0126-manual-one-corpus.md) the corpus; [0127](../decisions/0127-manual-audiences-and-recipes.md) audiences and recipe topics; [0128](../decisions/0128-manual-markdown-subset-and-visual-bar.md) the Markdown subset and the visual bar; [0129](../decisions/0129-ui-serves-the-whole-manual.md) the full reader in `baton ui`; [0130](../decisions/0130-manual-site-build.md) the site build; [0131](../decisions/0131-director-reads-the-manual.md) the Director's `help`; [0132](../decisions/0132-change-docs-name-their-manual-edits.md) the `manual:` rule; [0133](../decisions/0133-generated-reference-is-committed.md) committed generated reference. All accepted 2026-11-11.

## Plan

Each slice is one commit with its code, tests, design-doc edits, Log entry and any register update.

### Slice 1: the corpus, its anchors, its checks and `baton help`

- **Outcome:** `manual/` exists with the topic format, the anchor registry (`anchors.yaml`), the context map and the terms list; the validators run in the quick gate; `baton help` lists, prints and searches; `--help` footers; the keep-current rule is in AGENTS.md, the template, §0 and §19, with the `manual:` check on change docs. A few seed topics cover the setup page's current sections. The manual ships in the wheel.
- **Criteria:** a broken link or anchor, a removed published anchor, a topic outside the Markdown subset, a command with no topic, and a change doc moved to `done` without `manual:` each fail a test; `baton help user.connect-an-account` prints the topic; the manual is in `baton/_data/manual`.
- **Effort:** L

### Slice 2: the manual reader and the design system in `baton ui`

- **Outcome:** Setup and Manual parts under one header; the reader (tree, topic, outline, search, previous and next, deep links); the Markdown-subset renderer; one design system for both parts, light and dark, responsive and accessible.
- **Criteria:** every shipped topic is served and renders; a path outside the manual is refused; the §13.9 safety checks pass unchanged for the new routes; search finds titles and text; the owner has seen it running and accepted the look.
- **Effort:** L

### Slice 3: context help and the OpenRouter walk-through

- **Outcome:** `data-help` ids, the help panel, state-aware hints (a refused key, a harness not logged in) that carry an anchor, per-provider topics generated from the directory; the same `help:` pointer from `workers connect` and `doctor`.
- **Criteria:** every `data-help` id resolves; the panel opens the right topic per section; the OpenRouter topic is generated and reachable from its card; a refused key links to its explanation.
- **Effort:** L

### Slice 4: the user guide

- **Outcome:** the owner-facing guide outlined above, with the vocabulary lint passing.
- **Effort:** L

### Slice 5: the recipe topics

- **Outcome:** a topic for each of the six shipped recipes, with generated step and gate tables.
- **Criteria:** a shipped recipe with no topic, or a stale table, fails a test.
- **Effort:** M

### Slice 6: the admin guide and the generated reference

- **Outcome:** the admin topics and `tools/build_manual.py` generating commands, settings, paths, environment variables, doctor findings and diagnostic codes, with the drift and coverage tests.
- **Effort:** L

### Slice 7: the Director's `help` action and the site build

- **Outcome:** `help` in the CLI and MCP and the skill's instruction; `tools/build_site.py` produces the static site with identical URLs and anchors.
- **Effort:** M

## Log

### Slice 1: the corpus, its anchors, its checks and `baton help`

- **Commit:** `2026-11-user-help: Slice 1, the manual corpus, anchors, checks and baton help`
- **Summary:** `src/baton/manual.py` (topics, the checked Markdown subset, anchors and aliases, search, the context map) and `manual_cli.py` (examples checked against the CLI); `baton help` (list, print a topic or a section, `--search`, `--json`); every command's `--help` ends with `Manual: baton help <topic>` for mapped commands; `manual/` ships as `baton/_data/manual`. Four seed topics, `context.yaml` (every other command is in `pending_commands`, to be emptied by slice 6), `anchors.yaml` (refreshed by `tools/manual_anchors.py`) and `terms.yaml`. The keep-current rule is in AGENTS.md, the template (`manual:` and `### Manual edits`), §0 rule 9, §19 and `tests/test_docs.py` (a change in progress or done must name its manual edits; the changes done before it are exempt). Design: new §13.10, §13.2, §4.1, §14.1, §2. Tests: `tests/test_manual.py` (the shipped manual is valid; each kind of break in format, link, anchor, example, vocabulary and context map is reported; a renamed anchor needs an alias; `baton help` and the `--help` footer).
- **Review:** clean.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed".

### Slice 2: the manual reader and the design system in `baton ui`

- **Commit:** `2026-11-user-help: Slice 2, the manual reader and one design system in baton ui`
- **Summary:** `baton ui` is now Setup and Manual under one header with a search box. Server: `GET /api/manual/tree`, `/api/manual/topic/<id>`, `/api/manual/search?q=` and the page shell at `/manual` and `/manual/<part>/<slug>`, behind the unchanged token, Host and Origin checks; query strings now reach routes as `?name` arguments. Front end: `render.js` (the Markdown subset to DOM nodes), `manual.js` (tree, topic, outline with scroll-spy, breadcrumbs, previous and next, deep links, search with keyboard use, narrow-screen contents drawer), a new `app.css` design system for both parts, light and dark. `manual.py` gains `tree`, `page` and the optional `order` front-matter field. Also fixed: the Setup cards printed the word "null" where a control was absent (`h()` now skips null kids). Seen running in headless Chrome at desktop, dark and phone widths.
- **Tests:** `tests/test_ui.py` (the reader's routes, refusals without the token, a bad Host, a path in a topic id, no write method); `tests/test_ui_render.py` (the renderer under node: sections and anchors, topic and external links, nested inline text terminates, HTML in a topic stays text, tables, notes and code).
- **Review:** one bug found and fixed while looking at it: `inline()` shared one global regex between its recursive calls, which corrupted `lastIndex` and looped on nested bold and code; it now builds one per call, and the renderer test covers it.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed". This closing also stands for decision 0128's check that the owner has seen the page running.

### Slice 3: context help and the OpenRouter walk-through

- **Commit:** `2026-11-user-help: Slice 3, context help and generated provider pages`
- **Summary:** Setup has a "?" beside its sections, each provider's card, the capabilities column and the preference row; each opens the manual's short answer in a side panel (`help.js`) with "Open the full guide" to the reader at the same anchor; panel links stay in the panel. `GET /api/manual/context` serves the map; `/api/manual/topic/<id>?anchor=` serves one section. A refusal the manual explains carries "What does this mean?" (`context.yaml` `errors:`), and `baton workers connect` prints the same pointer (`More: baton help ...`, and `help` in `--json`). `manual_gen.py` and `tools/build_manual.py` write 18 provider pages (`manual/providers/`) from the provider directory and `manual/provider-notes.yaml`; the directory gains `display_name` for the direct APIs and Groq, and OpenRouter gains `display_name` and `signup_url` (https://openrouter.ai/keys answered on 2026-11-11), so its card now shows "Get a key". The seed topics now use the page's own labels (Use, Capabilities, Checked, Prefer a model for...). Seen running: the OpenRouter card opens its page in the panel (desktop, dark, phone).
- **Tests:** `tests/test_manual_gen.py` (pages match the directory; every provider has a page with its command; a new directory entry makes the manual stale; local runtimes say no key; the page's `data-help` ids equal the map's keys; every mapped error code is a real code), `tests/test_ui.py` (a section by anchor, the context map), `tests/test_ui_accounts.py` (the CLI's pointer in text and JSON).
- **Review:** clean.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed".

### Slice 4: the user guide

- **Commit:** `2026-11-user-help: Slice 4, the user guide`
- **Summary:** Eleven new owner-facing topics in `manual/user/`: what Baton is and who does what, getting started, using the manual, starting with a goal, bringing in an existing project, answering questions and deciding (every choice's label and effect, from `defaults/labels.yaml`), checking on your work, long-running work and coming back, how you want to be told, what Baton may do to your repository (the permission defaults from `init`), and when something is wrong (the `doctor` messages, the sandboxed Codex fix). Thirteen commands moved from `pending_commands` to mapped, so each one's `--help` now names its topic. `terms.yaml` also bars worker, gate, dispatch, escalation, attempt and work item from owner-facing prose. The generic provider's card and page are now titled "OpenAI-compatible service". Claims were checked against `baton init`, `doctor`, `board`, `defaults/labels.yaml`, the Director skill and the README, not written from memory.
- **Tests:** `tests/test_manual.py` (the whole manual validates, including the stricter terms list, every example's commands and options, every link and anchor).
- **Review:** clean.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed".

### Slice 5: the recipe topics

- **Commit:** `2026-11-user-help: Slice 5, a topic for each shipped recipe`
- **Summary:** One owner-facing topic for each of `fit-check`, `software-feature`, `backyard-project`, `recipe-builder`, `baton-adopt` and `baton-frame` (purpose, what you will be asked, what it produces, what it needs, an example, what to do when it goes wrong). The prose is in `manual/recipe-sources/`; `manual_gen.py` writes `manual/recipes/` with each topic's parts table generated from the recipe (`build_plan`): its parts, the sizes they apply at, and the human gates, so the questions listed are the recipe's own. A shipped recipe with no source, or a table that no longer matches its recipe, makes `tests/test_manual_gen.py` fail until `python tools/build_manual.py` is run. Facts were checked against each recipe's plan, run inputs, prompts and §5.7, not remembered.
- **Tests:** `tests/test_manual_gen.py` (all six shipped recipes have a topic with a generated table; a new shipped recipe, and a changed recipe, each make the manual stale).
- **Review:** clean.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed".

### Slice 6: the admin guide and the generated reference

- **Commit:** `2026-11-user-help: Slice 6, the admin guide and the generated reference`
- **Summary:** Eleven admin topics: install and versions (the launcher, extras, upgrade, `migrate`, trying a version on a branch), files and what to commit, network and security, platform notes, project settings, machine settings and profiles, accounts and who pays, setting up an assistant (reaching Baton, Codex over MCP, hooks, exit codes), troubleshooting and diagnostics, recipes and vendoring, and the commands an assistant uses; with the existing secrets topic. Four generated reference pages: every command and option (read from the CLI), every `project.yaml` key with its type and default (read from `ProjectConfig`), the environment variables, and the diagnostic codes (the last two from `manual/reference-notes.yaml`). `manual_gen.coverage()` fails when a project setting, a `BATON_*` variable in the source, or a `diag.note` code has no description, or when a command or option has no help text; it found two real gaps at once (`baton workers declare --base-url` and `--note`, now documented in the CLI). Every command is now mapped to a topic and `pending_commands` is empty; a test keeps it so. Tables accept `\|` in a cell (renderer and checker). Doctor findings are free text, not codes, so they are described by hand in the troubleshooting topic. Claims were taken from the design documents, the CLI's own help and the code, not remembered.
- **Tests:** `tests/test_manual_gen.py` (the reference matches the code; coverage is empty; a new variable, setting, option or diagnostic code, and a stale entry, each fail it; escaped pipes), `tests/test_manual.py` (every command has a topic).
- **Review:** clean.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed".

### Slice 7: the Director's `help` action, the site build and the README

- **Commit:** `2026-11-user-help: Slice 7, the Director's help action, the static site and a shorter README`
- **Summary:** `help(topic?, search?)` is an API call, an MCP tool and the CLI's `baton help`, all through `manual.help_payload`, so the words are the same on every interface; the Director skill (and its copy in §13.3) says to answer "how do I..." about Baton from it, never from memory. `tools/build_site.py` writes the manual as a static site under a version prefix (every topic at `/<version>/manual/<part>/<slug>/` with its anchor, JSON beside the pages where the page script reads the local API, browser-side search with the server's scoring, `versions.json` and a forwarding `index.html`); the page scripts are prefix-aware and share one source with `baton ui`. The reader's contents list now folds by part. The README keeps the install, the project set-up, a pointer to the manual and the recipe-authoring guide (not yet in the manual, decision 0127), and drops what the manual now holds; `doctor` points at `baton help admin.directors#wake` instead of the README, and the wake-up test reads the manual. §19 and §13.10 carry the finished rules.
- **Tests:** `tests/test_director_surface.py` (MCP lists `help`; its words equal the CLI's; a missing topic is `help.no_topic`), `tests/test_manual_site.py` (every topic has its page and data; the site is self-contained under its prefix; search data and the version index; a manual that does not validate is not published; the scripts are prefix-aware), `tests/test_real_use.py` (the wake-up test reads the manual).
- **Review:** clean.
- **Accepted:** owner, 2026-11-13, closing the change: "it should be closed". `status: done`.


- 2026-11-12, follow-up (owner request): `baton ui` now listens on port 47474 by default (`--port` overrides, 0 = free), has no idle timeout by default (`--idle-timeout S` opts in; the Director's action always sets one, default 15 minutes), and running it again closes the running page first (`ui.replace_running`). The token is kept in `~/.baton/ui-token` (0600) and the cookie lasts a year, so a bookmark survives restarts. Manual: using-the-manual, network-and-security, files-and-paths, regenerated commands reference. Design §13.9 and tests in `test_ui.py`.
- 2026-11-12, correction: timeouts. `baton ui --detach` has no timeout unless given; the Director's `ui` always has one and never restarts a running page. `merge_timeout`: a launch can only extend a running page's timeout (kept in `ui.json`, re-read by the page), and the caller is told when its timeout was not applied. A restarting `baton ui` inherits the old page's timeout unless extended.
- 2026-11-12, repair (red full run on `2e79c36`): the detached-start test launched the page on the fixed default port, so it failed whenever a real `baton ui` held 47474. `ui.start_detached` takes an optional `port` (default unchanged) and the test passes `port=0`, a free port.
