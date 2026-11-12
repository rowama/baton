---
id: admin.secrets
title: Where API keys are kept
audience: admin
summary: How Baton stores, resolves and protects provider keys on a machine.
related: [user.connect-an-account]
---

## Here, now {#here-now}

A key is stored on the machine that connected it, in the operating system's keyring when one is available, otherwise in `~/.baton/secrets/<name>`. It is never written to a project, a repository, an event, a log or a diagnostic, and the setup page never shows one after it is stored.

## Where keys are kept {#where-keys-are-kept}

Baton looks in this order for the key of an account named `<name>`:

1. The environment variable `BATON_SECRET_<NAME>`: upper-cased, with other characters turned into `_`.
2. The OS keyring, service `baton`. Needs the optional `keyring` package and a working backend.
3. The file `~/.baton/secrets/<name>`. The directory is mode 0700 and the file 0600.

Connecting an account (page or `baton workers connect`) writes to the keyring when it works, else to the file, and reports which. A dispatch that cannot find a key stops as a configuration problem and names all three places.

## Replacing and removing {#replacing-and-removing}

```baton
baton workers connect openrouter --name openrouter-main
baton workers disconnect openrouter-main --forget-key
```

Replacing a key checks the new one first; a bad one leaves the working key in place. `disconnect` removes the account's declaration, and the stored key only with `--forget-key`.

## What the setup page protects {#setup-page-protection}

The page listens on loopback only and checks a per-launch token and the `Host` and `Origin` headers on every request. A key sent from the page is held in memory only until it is stored, and request bodies are never logged.
