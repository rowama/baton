---
id: "0121"
title: "An optional UI is allowed as a client over the CLI and MCP; Baton never requires one"
status: accepted
date: 2026-11-10
source: "change 2026-11-setup-ui (owner, 2026-11-10: accept the suggested wording)"
sections: ["§0", "§1.1", "§1.3", "§1.4"]
---

# 0121. An optional UI is allowed as a client over the CLI and MCP; Baton never requires one

## Context

The principles forbade a web UI (§0 rule 3, §1.3) and a server (§1.1 #3). Their intent is that Baton must not *need* a UI, daemon or server to work. The owner wants an optional local setup page, and later perhaps a broader owner-interaction UI.

## Decision

- §0 rule 3 and §1.1 #3 now say Baton *needs* no web UI, daemon or server; optional clients built over the CLI and MCP are allowed, and the runtime never depends on them.
- §1.3 says "no *required* GUI".
- A new key design decision, §1.4 #13: a UI is a client, never a dependency. It changes state only through the same core functions as the CLI and MCP, and holds no state of its own.
- The broader owner-interaction UI is recorded as a direction the owner has named, not a non-goal, and is not authorized by this change.
