---
id: admin.network-and-security
title: Network and security
audience: admin
order: 20
summary: What Baton contacts, what runs on the machine, and how secrets, recipes and the setup page are protected.
related: [admin.secrets, admin.files-and-paths]
---

## Here, now {#here-now}

Baton runs no daemon, server or database of its own. It is files, git and processes started on demand. The only listening socket is the optional setup page, bound to loopback and closed when idle.

## What it talks to {#network}

- **Providers you connect.** Model API calls, and the model-list read that checks a key, go to the endpoint of each provider you connected (for a directory provider, its address is in its [provider page](providers.openrouter#here-now); for your own endpoint, the address you gave).
- **Coding assistants you use as helpers.** Each is a program on the machine that talks to its own service with its own login.
- **The web, only when a helper searches it.** Baton tells the owner before work that searches the web starts, if no helper on the machine can.
- **The install source.** `uv` fetches a runtime version the first time a project pins it (`~/.baton/launcher.yaml` names the source).

Nothing else leaves the machine. Packets and results travel as files between Baton and a helper's process.

## What runs on the machine {#processes}

- A short-lived **supervisor** process per dispatched piece of work, which ends when the work is recorded.
- Helpers: child processes with their own constructed environment, so one job's key never reaches another job.
- Script checks and hooks, run under the platform shell.
- `baton ui` and `baton mcp --http`, only while you run them. `baton mcp` over stdio runs for as long as the assistant that started it.

## Secrets {#secrets}

Keys come from `BATON_SECRET_<NAME>`, the OS keyring or a 0600 file, in that order. They are injected into a helper's environment only, never written to packets, events, logs or diagnostics, and resolved values are redacted from anything Baton records. See [where keys are kept](admin.secrets#where-keys-are-kept). `project.yaml` is committed, so Baton refuses a `secret:` reference in it; only machine-level files may reference secrets.

## Recipes are trusted code {#recipes}

A recipe's script checks run commands on the machine. Review a recipe before you vendor it. `baton check` and `baton doctor` verify the vendored hashes, so a recipe edited after vendoring is reported. A recipe the builder drafted is audited for exactly this, and is vendored only after the owner accepts it.

## Helpers may have wide permissions {#helper-permissions}

A coding assistant used as a helper may be able to edit files and run commands. For risky work, prefer a container or a dedicated user. Baton never weakens an assistant's own sandbox: if the shell it gives Baton is sandboxed, `baton detect` and `baton doctor` stop with `director_sandboxed`, and the assistant should reach Baton over MCP instead. See [setting up an assistant](admin.directors#codex).

## The setup page and MCP over HTTP {#local-servers}

`baton ui` binds `127.0.0.1` only, checks a per-launch token, the `Host` and `Origin` headers and a custom request header on every request, and never returns a stored key. `baton mcp --http` also binds loopback only and needs the bearer token from `~/.baton/mcp.yaml`.

## What Baton may do to the repository {#permissions}

The project's `permissions` bound what Baton and the assistant do to the repository and its remotes. The defaults never merge, deploy or force-push, and ask before anything but a documents-only or checked push. See [what Baton may do](user.what-baton-may-do#here-now).

## Diagnostics stay on the machine {#diagnostics}

Conditions Baton works around are recorded under `~/.baton/diag/`, never in the project, with every string redacted first, so a record can be handed to someone as it is. See [troubleshooting](admin.troubleshooting#diagnostics).
