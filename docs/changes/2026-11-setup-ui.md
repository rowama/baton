---
id: 2026-11-setup-ui
title: "A local setup page lets the owner connect subscriptions and API accounts and manage the models Baton may use, without editing any file"
status: done
level: major
decisions: ["0121", "0122", "0123", "0124", "0125"]
touches: [principles.md, design/runtime.md, design/versioning.md, design/director-interface.md, design/workers.md, design/platform-and-security.md, design/layouts.md]   # §0, §1.1, §1.3, §2, §13.1, §13.2, §6.1, §6.4, §15.2, §4.4, §8.4, §14.1
---

# A local setup page lets the owner connect subscriptions and API accounts and manage the models Baton may use, without editing any file

> **Proposed, 2026-11-10; revised the same day with the owner's direction:** reworded principles (open question 1), no limit on the UI's technology, key rotation and removal in scope, starting CLI logins out of scope. Request only (level major). It depends on [2026-11-model-listings](2026-11-model-listings.md) for the breadth of models it shows; a first version can ship over today's known-workers data. It is related to, and does not replace, [2026-11-zero-friction-setup](2026-11-zero-friction-setup.md) (on hold): a later version of that change could use this page as its landing point.

## Request

### Problem

Connecting a worker today means CLI commands and, for API accounts, a secret the owner must store themselves:

- an environment variable `BATON_SECRET_<NAME>`, the OS keyring, or the file `~/.baton/secrets/<name>` (§6.1);
- then `baton workers declare <name> --provider <p> --credential secret:<name>`;
- then `baton workers setup`.

The Director skill walks the owner through this, but it must not take a key in conversation, so the owner still does the storing by hand. Choosing among models, or keeping one out of routing, means `.baton/preferences.yaml` (§8.4). Seeing what is available, what it costs and what has been verified means reading `workers status` output.

For a technically comfortable owner that is tolerable. For the layperson owner Baton is designed for (§1.1 #5), it is not. With [2026-11-model-listings](2026-11-model-listings.md), the stable could also grow from tens of profiles to hundreds, which a terminal list serves poorly.

The owner wants:
- every subscription (CLI) and every API account integrated without editing a config file;
- the model stable managed from one place;
- setup to be easier than Hermes, whose `hermes setup` / `hermes model` are interactive terminal pickers and whose secrets go to `~/.hermes/.env` through `hermes config set` ([Hermes quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)).

The owner also intends, later and not in this change, a Baton web interface for all owner interaction: stripped to what working with Baton processes needs, and not depending on a third-party chat interface or harness. A setup and admin page is the first step in that direction. Its first job is the stable of models and providers.

**Principles conflict.** As written, the principles forbid this change, though their intent still holds (open question 1):
- §0 rule 3: "No web UI, no message broker, no database server, no long-running daemon";
- §1.1 #3: "no daemon, no server";
- §1.3: "No GUI".

The intent of those rules still holds: Baton must not *need* a UI to function, and runs entirely through its CLI and MCP. What the owner wants changed is that the rules also forbid an *optional* client built on top of the CLI and MCP. That is how this change and any later owner-facing UI fit: Baton works the same whether a UI exists or not. `baton mcp` already serves HTTP on request (§13.2, the `mcp` extra brings `uvicorn`), so an on-demand local server is not new to Baton.

### What changes, in outline (not yet a Design)

1. **`baton ui` starts a local web app, on demand.**
   - It binds to the loopback address only, on a free port, and opens the owner's browser at a URL that carries a one-time token.
   - The process runs only while the page is in use and exits after an idle timeout or when the owner closes it. It is not a daemon and is not started at login.
   - The Director can start it too (a `ui` action on the CLI and MCP, §13.1): it returns the URL, and the Director says "open this link to connect your accounts".
2. **The app is an optional client over the one core** (§1.4 #12).
   - Every action it takes calls the same engine functions as the CLI and MCP (`workers status`, `declare`, `setup`, `--verify`, preferences) and writes the same files.
   - Anything done on the page can also be done, and seen, from the CLI.
   - The app holds no state of its own.
   - Baton never depends on it: no runtime behaviour, recipe or Director flow requires the app to exist or be running.
3. **First page: the stable.**
   - **Providers:** each one Baton knows, whether connected, and what connecting it needs.
     - CLI subscriptions are detected, with their login state and version.
     - For API accounts, the owner pastes a key once. It is stored in the OS keyring when available, else the secrets file with owner-only permissions, and never written to any YAML, log or event (§6.1 redaction unchanged).
     - The key is checked with one cheap call (a listing or key-info read, not a model call), then declared and set up.
     - Where the provider reports it, the page shows remaining credit and free quota.
     - **Managing a connected account:**
       - *Replace key*: the new key is checked before the old one is overwritten, so a bad paste never breaks a working account.
       - *Disconnect*: removes the declaration (`workers declare <name> --remove`) and, after confirmation, the stored secret.
       - In both cases, generated profiles that depended on the account are flagged, not deleted, under the existing refresh rules (§6.4).
     - Nothing about a key is shown after it is stored except where it is kept (keyring or file) and when it was last checked.
   - **Models:** every profile with these columns: provider, price (or "free" / "subscription"), context size, tier, capabilities with their state (likely, verified, absent), and when it was last verified.
     - Filters: free only, max price, capability, tier, provider.
     - Per model: on or off for routing (writes an exclusion preference), "check it works" (the existing `--verify`), and "assess it" (owner-run research, if [2026-11-model-listings](2026-11-model-listings.md) open question 3 is accepted).
   - **Preferences:** cheapest first or most-verified first, and per-capability preferred models. Everything is a choice on the page; the YAML is an implementation detail.
4. **CLI subscriptions are walked, not edited.**
   - For a harness that is installed but not logged in, the page shows the exact login command for this platform, with a copy button. Starting the login from the page is out of scope (owner, 2026-11-10).
   - For one that is not installed, it shows the install step for this platform.
   - It re-checks when the owner comes back to the page.
5. **Safety by construction.** Every request is checked against all of these:
   - a loopback bind;
   - a per-launch token;
   - a `Host` header check against DNS rebinding;
   - no cross-origin access;
   - a key that is never sent back to the browser after it is stored.

   One machine's page manages that machine's resources only (§4.4).
6. **The UI's technology is open** (owner, 2026-11-10). It may be a full web app: any framework, build step or dependencies, as long as:
   - it is an optional install (an extra or a separate package), so a Baton install without it is complete and loses nothing but the app;
   - its dependencies are kept out of the runtime's own;
   - all writes go through the core functions (point 2).

   Framework, packaging and server are Design choices (open question 3).

### Acceptance criteria (draft)

1. On a machine with Claude Code logged in and nothing else configured, `baton ui` opens a page that shows Claude Code connected, its generated profiles, and an "add an account" choice for each API provider Baton knows. No file has been edited by the owner.
2. Pasting an OpenRouter key and pressing connect stores the key outside any YAML, checks it, declares the resource and runs setup. The models page then shows the new profiles. Afterwards, `baton workers status` on the CLI shows the same result.
3. Turning a model off on the page excludes it from routing. The exclusion is visible in `.baton/preferences.yaml` (or its machine-level equivalent; open question 5) and in the `worker_selected` event's exclusions.
4. A request without the launch token, or with a non-loopback `Host`, is refused. A stored key is never present in any response body, log, event or diagnostic (tested by scanning them all).
5. The `baton ui` process exits after the idle timeout and leaves nothing running.
6. Every action on the page has a CLI equivalent, and a test drives both against the same fixtures and compares the files they write.
7. The page works on Windows, macOS, Linux and WSL, with the browser opened on the host side under WSL **[VERIFY: WSL2 localhost forwarding in the default network mode]**.
8. Replacing an account's key with an invalid one leaves the old key and the account working, and says why the new one was refused. Disconnecting an account removes its declaration and, once confirmed, its stored secret. Its generated profiles are then flagged as no longer offered (resource gone), and routing stops using them.
9. Baton's full test suite passes with the UI not installed, and no runtime module imports it.

### Open questions (each with a suggested answer)

1. **Principles wording.** Owner's direction (2026-11-10): the no-UI rules stay, as "Baton must not require one", and an optional UI over the CLI and MCP is allowed. *Suggested text:*
   - §0 rule 3: "Thin layer. Baton needs no web UI, message broker, database server or long-running daemon to work. Filesystem, git, SQLite (as a cache only) and plain Python. Optional clients (a local web app, §13.x) may be built over the CLI and MCP; the runtime never depends on them. Every dependency must justify itself."
   - §1.1 #3: "The runtime stays small and conventional, and needs no daemon or server", the rest unchanged.
   - §1.3: "No required GUI. Baton is complete through its CLI and MCP; a UI is an optional client."
   - A new key design decision in §1.4, after #12: "A UI is a client, never a dependency. It changes state only through the same core functions as the CLI and MCP."
   - The broader owner-interaction UI is recorded as a direction, not a non-goal, without authorizing it here.
2. **Scope of the first version.** *Suggest:* the stable only (providers, models, preferences). Project, run and recipe views come later, as part of the broader UI direction.
3. **Packaging and stack.** *Suggest:*
   - a JSON API served by `baton ui` from the runtime package (small, standard library or `uvicorn`), with the web app as a separately versioned front end in an extra (`baton[ui]`);
   - the API then becomes the seam a later owner-interaction UI builds on.

   The framework is a Design choice.
4. **Where keys go by default.** *Suggest:* the OS keyring when the `keyring` package and a backend are present; otherwise `~/.baton/secrets/<name>` with owner-only permissions, and the page says which was used. Should `keyring` join the launcher's default extras alongside `api` ([2026-11-model-listings](2026-11-model-listings.md) open question 8)? Suggest yes.
5. **Machine-level preferences.** Routing preferences today are per project (`.baton/preferences.yaml`), while the stable is per machine. *Suggest:* a machine-level preferences file (`~/.baton/preferences.yaml`) that project preferences override. The page edits the machine level, and per-project overrides stay a Director or CLI matter.
6. ~~Starting CLI logins.~~ Decided (owner, 2026-11-10): out of scope. The page shows the command with a copy button; a later change may add starting it.
7. **Concept budget.** *Suggest:* the page adds no concept (§2). It is an interface, like the CLI. Record that in §2's interfaces note.

## Design

Approved by the owner, 2026-11-10 ("Accept all. Go."): the open questions are decided in records 0121–0125 and the Design is the text now in `director-interface.md` §13.9.

### Doc edits

- `principles.md` §0 rule 3, §1.1 #3, §1.3, a new §1.4 #13, and §2's interfaces note: an optional UI is a client, never a dependency.
- `design/director-interface.md` §13.9 (new): the process, safety checks, API, connecting, subscriptions, preferences and front end; §13.1: the `ui` call.
- `design/workers.md` §6.1: the key store (keyring, else owner-only file) written by `workers connect` and the page.
- `design/runtime.md` §8.4: machine-level preferences merged with the project's.
- `design/layouts.md` §4.4: `~/.baton/preferences.yaml` and `ui.json`.
- `design/platform-and-security.md` §15.2: the page's request checks.
- `design/versioning.md` §14.1: the launcher's default extras are `api` and `keyring`.

### Decisions

- [0121](../decisions/0121-optional-ui-is-a-client.md) principles amendment; [0122](../decisions/0122-ui-scope-and-packaging.md) scope and packaging (a stdlib API and a dependency-free front end shipped in the wheel, not a separate extra: the one departure from the suggested answer, with its reason there); [0123](../decisions/0123-keys-keyring-then-file.md) key storage; [0124](../decisions/0124-machine-level-preferences.md) machine-level preferences; [0125](../decisions/0125-ui-adds-no-concept.md) no new concept.

## Plan

### Slice 1: `baton ui`, read-only

- **Outcome:** `baton ui` serves the stable (providers, models) from `workers status`, with the token, loopback, Host/Origin and idle-exit guarantees; the Director's `ui` action returns the URL.
- **Criteria:** requests without the token or with a foreign Host or Origin are refused; the process exits after the idle timeout; no runtime module imports `ui.py`; the front end is shipped as data.
- **Effort:** M

### Slice 2: connect, replace and disconnect an API account

- **Outcome:** `baton workers connect|disconnect` and the matching page actions store, check, declare and set up an account; keys never leave the store.
- **Criteria:** a key is in no YAML, response, log, event or diagnostic (scan); a bad replacement leaves the old key and account working; disconnecting flags generated profiles as resource gone; CLI and page write the same files.
- **Effort:** L

### Slice 3: models and preferences

- **Outcome:** machine-level preferences (`~/.baton/preferences.yaml`, merged under the project's); `baton workers prefs`; page controls for on/off, verify, ordering and filters; `worker_selected` exclusions name the level.
- **Criteria:** turning a model off excludes it from routing and shows in the exclusion reasons; the merge rules of 0124; CLI and page write the same file.
- **Effort:** M

### Slice 4: subscriptions walked

- **Outcome:** the page shows each harness's state with the install or login command for this platform and re-checks on return; launcher default extras include `keyring`; Director skill mentions `ui`; WSL browser opening.
- **Criteria:** the state payload carries the step per platform; the launcher default is `api, keyring`.
- **Effort:** S

## Log

### Slice 1: `baton ui`, read-only

- **Commit:** 2026-11-setup-ui: Slice 1, baton ui serves the stable read-only
- **Summary:** Decisions 0121–0125, the principles amendment and §13.9 and the other design edits are in this commit; the change is `in-progress`. `ui.py` is the stdlib server (token cookie, `Host`, `Origin`, custom header, no CORS, CSP, idle exit, `~/.baton/ui.json`, detached start for the Director), `baton ui` and the `ui` call (CLI, engine, MCP), and the front end (`ui/`, shipped as `baton/_data/ui`) shows subscriptions, accounts and the models table. `tests/test_ui.py` covers the request checks, the cookie hand-over, only-named-files, no-front-end operation, quit, idle exit, the private registration file, no runtime module importing the page, and a detached start.
- **Review:** clean.
- **Accepted:** the Design was approved by the owner, 2026-11-10 ("Accept all. Go.").

### Slice 2: connect, replace and disconnect an API account

- **Commit:** 2026-11-setup-ui: Slice 2, connect, replace and disconnect an API account
- **Summary:** `accounts.py` is the one core path (check with one free read, store, declare, refresh the list, set up; replace checks first; disconnect keeps the key unless asked). `profiles.py` gains `store_secret` (keyring, else a 0600 file in a 0700 directory, removing the other store's copy), `delete_secret` and `secret_places`. `baton workers connect|disconnect` (key on a hidden prompt or `--key-stdin`, never an argument or MCP) and the page routes call it; the page has connect, replace-key and disconnect controls. Key checks exist for OpenRouter, OpenAI, Anthropic and any `openai_compatible` endpoint; other providers say the key is tried at first use (`KEY_CHECKS`, marked [VERIFY] for the two direct APIs, which were not called live). Departure from the Request: the page does not show "when a key was last checked" (it would need a state file of its own); it shows where the key is kept. Tests (`tests/test_ui_accounts.py`): connect, refused key, bad and good replacement, disconnect and the `resource_gone` flag, an environment key not shadowed, keyring versus file, page and CLI writing the same files, a sentinel key absent from every response, file, log and diagnostic, and a keyless local endpoint.
- **Review:** clean.
- **Accepted:** done; the owner reviews the whole change.

### Slice 3: models and preferences

- **Commit:** 2026-11-setup-ui: Slice 3, models and machine-level preferences
- **Summary:** `routing.load_preferences(baton_dir, home)` merges `~/.baton/preferences.yaml` under the project's by 0124's rules (`merge_preferences`); the exclusion reason says "turned off for this machine" for the machine level, and that reason is what `worker_selected`'s `excluded` records. `prefs.py` edits the machine file; `baton workers prefs` and the page routes (`/api/models/<profile>/enabled`, `/verify`, `/api/preferences`) call it. The page has the models table with its filters (free only, maximum price, capability, tier, provider, turned off), the on/off switch, "Check it works" and the cheapest-first order. Per-capability preferred models are in the API and CLI (`--prefer CAP=a,b`); the page has no control for them yet (a later refinement, noted in Open items). `doctor` reads the merged preferences. Tests (`tests/test_ui_models.py`): on/off through the page and routing, unknown names, the merge rules, a project not lifting a machine exclusion, the eligibility reason, ordering and preferred models, the live check through `setup`, CLI and page writing the same file, and the state's columns.
- **Review:** clean.
- **Accepted:** done; the owner reviews the whole change.

### Slice 4: subscriptions walked, and the finish

- **Commit:** 2026-11-setup-ui: Slice 4, subscriptions walked and the Director offers the page
- **Summary:** `workers status` detections carry a `step` in the page's state (`ui.harness_step`): nothing, the login command, or the install command, worded for Windows, macOS, Linux or WSL, with a copy button; the page re-reads when the owner returns to it (`visibilitychange`) and has "Check again". The login commands are Baton's existing hints (`claude auth login`, `codex login`); the install commands are the tools' npm packages and are not live-verified (`HARNESS_STEPS`, marked [VERIFY]). The launcher's default extras are now `api` and `keyring` (0123; amends 0116; `test_versioning` updated). The Director skill and §13.3's copy now say to call `ui` and give the owner the link instead of asking the owner to store a secret by hand. The page gained the per-capability preferred-model control that Slice 3 left to the API. Tests added to `tests/test_ui.py`: steps per platform, state and re-check, the skill wording.
- **Review:** clean.
- **Accepted:** done; the owner reviews the whole change.

### Follow-up: first live use under WSL2

- **Fixed:** `open_browser` no longer tries `explorer.exe` (it opened a File Explorer window for the link); under WSL2 it tries `wslview`, `powershell.exe Start-Process`, then `cmd.exe /c start`. Added `baton ui --stop` (`ui.stop`) to close a detached page: SIGTERM to the pid in `ui.json`, then the file is removed. Test: `test_stop_ends_the_registered_page_and_clears_its_file`.

### Open items for the owner

- Not demonstrated live: opening the browser under WSL2 (acceptance criterion 7's **[VERIFY]**; `open_browser` tries `wslview`, `powershell.exe`, `cmd.exe`, then `webbrowser`, and prints the link in any case), the OpenAI and Anthropic key checks, and the npm install commands. Windows and macOS are covered only by the platform-neutral code paths.
- The page shows where a key is kept but not "when it was last checked" (Slice 2).
- Per-project preference overrides stay a CLI and Director matter, as decided.
