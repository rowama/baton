---
id: 2026-11-setup-ui
title: "A local setup page lets the owner connect subscriptions and API accounts and manage the models Baton may use, without editing any file"
status: proposed
level: major
decisions: []               # proposed records to create once the owner answers the open questions below
touches: [principles.md, design/director-interface.md, design/workers.md, design/platform-and-security.md, design/layouts.md]   # §0, §1.1, §1.3, §2, §13.1, §13.2, §6.1, §6.4, §15.2, §4.4
---

# A local setup page lets the owner connect subscriptions and API accounts and manage the models Baton may use, without editing any file

> **Proposed, 2026-11-10.** Request only (level major). This change needs a principles amendment, which is the owner's decision (open question 1). It depends on [2026-11-model-listings](2026-11-model-listings.md) for the breadth of models it shows; a first version can ship over today's known-workers data. It is related to, and does not replace, [2026-11-zero-friction-setup](2026-11-zero-friction-setup.md) (on hold): a later version of that change could use this page as its landing point.

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

**Principles conflict.** As written, the principles forbid this change:
- §0 rule 3: "No web UI, no message broker, no database server, no long-running daemon";
- §1.1 #3: "no daemon, no server";
- §1.3: "No GUI".

`baton mcp` already serves HTTP on request (§13.2, the `mcp` extra brings `uvicorn`), so an on-demand local server is not new to Baton. A page for the owner is.

### What changes, in outline (not yet a Design)

1. **`baton ui` starts a local page, on demand.**
   - It binds to the loopback address only, on a free port, and opens the owner's browser at a URL that carries a one-time token.
   - The process runs only while the page is in use and exits after an idle timeout or when the owner closes it. It is not a daemon and is not started at login.
   - The Director can start it too (a `ui` action on the CLI and MCP, §13.1): it returns the URL, and the Director says "open this link to connect your accounts".
2. **The page is a fourth interface over the one core** (§1.4 #12).
   - Every action it takes calls the same engine functions as the CLI and MCP (`workers status`, `declare`, `setup`, `--verify`, preferences) and writes the same files.
   - Anything done on the page can also be done, and seen, from the CLI.
   - The page holds no state of its own.
3. **First page: the stable.**
   - **Providers:** each one Baton knows, whether connected, and what connecting it needs.
     - CLI subscriptions are detected, with their login state and version.
     - For API accounts, the owner pastes a key once. It is stored in the OS keyring when available, else the secrets file with owner-only permissions, and never written to any YAML, log or event (§6.1 redaction unchanged).
     - The key is checked with one cheap call (a listing or key-info read, not a model call), then declared and set up.
     - Where the provider reports it, the page shows remaining credit and free quota.
   - **Models:** every profile with these columns: provider, price (or "free" / "subscription"), context size, tier, capabilities with their state (likely, verified, absent), and when it was last verified.
     - Filters: free only, max price, capability, tier, provider.
     - Per model: on or off for routing (writes an exclusion preference), "check it works" (the existing `--verify`), and "assess it" (owner-run research, if [2026-11-model-listings](2026-11-model-listings.md) open question 3 is accepted).
   - **Preferences:** cheapest first or most-verified first, and per-capability preferred models. Everything is a choice on the page; the YAML is an implementation detail.
4. **CLI subscriptions are walked, not edited.**
   - For a harness that is installed but not logged in, the page shows the exact login command and can start it in a terminal **[VERIFY: each CLI's login command and whether it can be started non-interactively from a child process]**.
   - For one that is not installed, it shows the install step for this platform.
   - It re-checks when the owner comes back to the page.
5. **Safety by construction.** Every request is checked against all of these:
   - a loopback bind;
   - a per-launch token;
   - a `Host` header check against DNS rebinding;
   - no cross-origin access;
   - a key that is never sent back to the browser after it is stored.

   One machine's page manages that machine's resources only (§4.4).
6. **Thin and dependency-light.**
   - One static HTML page with plain JavaScript, shipped inside the package. No JavaScript toolchain and no build step.
   - Served by the standard library or by `uvicorn` from the existing `mcp` extra (open question 3).

### Acceptance criteria (draft)

1. On a machine with Claude Code logged in and nothing else configured, `baton ui` opens a page that shows Claude Code connected, its generated profiles, and an "add an account" choice for each API provider Baton knows. No file has been edited by the owner.
2. Pasting an OpenRouter key and pressing connect stores the key outside any YAML, checks it, declares the resource and runs setup. The models page then shows the new profiles. Afterwards, `baton workers status` on the CLI shows the same result.
3. Turning a model off on the page excludes it from routing. The exclusion is visible in `.baton/preferences.yaml` (or its machine-level equivalent; open question 5) and in the `worker_selected` event's exclusions.
4. A request without the launch token, or with a non-loopback `Host`, is refused. A stored key is never present in any response body, log, event or diagnostic (tested by scanning them all).
5. The `baton ui` process exits after the idle timeout and leaves nothing running.
6. Every action on the page has a CLI equivalent, and a test drives both against the same fixtures and compares the files they write.
7. The page works on Windows, macOS, Linux and WSL, with the browser opened on the host side under WSL **[VERIFY: WSL2 localhost forwarding in the default network mode]**.

### Open questions (each with a suggested answer)

1. **Principles amendment.** *Suggest:*
   - §0 rule 3 becomes "No hosted service, no message broker, no database server, no long-running daemon. A local page served on demand by `baton ui` is allowed: it is an interface over the core like the CLI and MCP, binds to the loopback address, keeps no state of its own and exits when idle."
   - §1.1 #3 gets the same carve-out.
   - §1.3 "No GUI" becomes "No GUI beyond the local setup page (§13.x)".
   - The broader owner-interaction UI is recorded as a direction, not a non-goal, without authorizing it here.
2. **Scope of the first version.** *Suggest:* the stable only (providers, models, preferences). Project, run and recipe views come later, as part of the broader UI direction.
3. **Server.** *Suggest:* the standard library `http.server` (`ThreadingHTTPServer`), so the page needs no extra. `uvicorn` would add an async stack for a page with a handful of JSON endpoints.
4. **Where keys go by default.** *Suggest:* the OS keyring when the `keyring` package and a backend are present; otherwise `~/.baton/secrets/<name>` with owner-only permissions, and the page says which was used. Should `keyring` join the launcher's default extras alongside `api` ([2026-11-model-listings](2026-11-model-listings.md) open question 8)? Suggest yes.
5. **Machine-level preferences.** Routing preferences today are per project (`.baton/preferences.yaml`), while the stable is per machine. *Suggest:* a machine-level preferences file (`~/.baton/preferences.yaml`) that project preferences override. The page edits the machine level, and per-project overrides stay a Director or CLI matter.
6. **Starting CLI logins.** *Suggest:* show the command and a "copy" button in the first version, and add "start it for me" per CLI once each login flow is checked on all platforms.
7. **Concept budget.** *Suggest:* the page adds no concept (§2). It is an interface, like the CLI. Record that in §2's interfaces note.

## Design

To be written once the principles amendment is decided and the Request is approved.

## Plan

Suggested first slice: `baton ui` serving the stable read-only (providers and models from `workers status --json`), with the token, loopback and idle-exit guarantees and their tests. The second slice adds connecting an API account.

## Log
