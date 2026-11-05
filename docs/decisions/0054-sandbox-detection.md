---
id: "0054"
title: "What counts as a sandboxed Director"
status: accepted
date: 2026-11-04
source: "change 2026-11-codex-director-sandbox, slice 1"
sections: ["§13.4"]
---

# 0054. What counts as a sandboxed Director

## Context

The change doc for `director_sandboxed` was ambiguous in three places. Its acceptance criterion 1 says an unwritable Baton home *or no network* means the sandbox, while its Detection section says both failing, or a failed home write. It names `EROFS` and `EACCES` for the home write, but macOS's sandbox refuses writes with `EPERM`. And it says the write helper turns *any* `OSError` into the sandbox problem, which would call a full disk a sandbox. A local network probe can tell a sandbox from an offline machine: connecting a UDP socket only looks up a route, and a sandbox refuses it with a permission error, while an offline machine answers "network unreachable".

## Decision

- **Network:** only a *refused* network (`EPERM`/`EACCES`/`EROFS` from creating or connecting the probe socket) counts as the sandbox. A machine that is merely offline gets an ordinary warning.
- **Home write:** `EROFS`, `EACCES` and `EPERM` all count, so Codex on macOS is caught as well as on Linux.
- **Other errors** writing the Baton home (disk full, etc.) are an ordinary `cannot write <path>: <reason>` problem, never a traceback.
- Either sandbox signal alone is enough: `director_sandboxed`.
