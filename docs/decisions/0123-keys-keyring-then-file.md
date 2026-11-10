---
id: "0123"
title: "The UI stores an API key in the OS keyring, else in an owner-only file, and keyring joins the launcher's default extras"
status: accepted
date: 2026-11-10
source: "change 2026-11-setup-ui (owner, 2026-11-10: accept the suggested answer)"
sections: ["§6.1", "§13.9", "§14.1"]
---

# 0123. The UI stores an API key in the OS keyring, else in an owner-only file, and keyring joins the launcher's default extras

## Context

Open question 4. Secrets resolve from `BATON_SECRET_<NAME>`, then the keyring, then `~/.baton/secrets/<name>` (§6.1); nothing yet wrote one.

## Decision

- Storing a key writes the OS keyring (service `baton`) when the `keyring` package and a working backend exist, otherwise `~/.baton/secrets/<name>` (directory 0700, file 0600). The answer says which was used; the key is never written to YAML, a log, an event or a diagnostic.
- A replacement key is checked before the stored one is overwritten.
- Disconnecting removes the resource declaration; the stored secret is removed only when the owner confirms.
- The launcher's default extras become `api` and `keyring` (amends 0116). `launcher.yaml`'s `extras` still replaces the default.
- The same store is available from the CLI (`baton workers connect`, key on stdin or a hidden prompt, never an argument), so every page action has a CLI equivalent.
