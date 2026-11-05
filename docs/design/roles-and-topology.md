## 3. Roles and Topology

- **Owner:** owns goals, makes decisions at gates and escalations. Talks to the Director in their own terms (and, when needed, to an SME through it); needs no Baton vocabulary.
- **Director:** any harness with the `baton-director` skill that can reach the runtime by shell (CLI) or MCP. Expert at running processes, routing work and facilitating the owner's decisions, the way a project manager engages a stakeholder (§13.8); impartial; **never performs step work** and never answers subject questions itself.
- **Runtime:** deterministic Python installed on the **runtime host**, the machine where the repo and CLI-harness workers live.
- **Worker:** executes one attempt of one step under one profile; stateless with respect to the run.
- **SMEs:** workers consulted by subject. A **platform** SME is an IT-type expert (it may itself be an agent with its own access) that works with workers, the Director and the owner to resolve infrastructure problems. A **process** SME has Baton and the recipe as its subject.

```
Owner ⇄ Director (local or remote agent)
           │  baton CLI over shell, or MCP
           ▼
       Runtime (runtime host) ── repo: .baton/ (events, CAS, records)
           │  spawn detached supervisor → worker child process (profile env + auth)
           ▼
       Worker (API model | headless agent | human)  →  result/
           │
       Runtime: intake → gates → record → publish → checkpoint commit → completion hook wakes Director
```

**Typical topology:** the Director may be remote (e.g. a cloud chat agent) as long as it can run `baton` on the runtime host through a shell. Because a remote Director's turn can end while work is still running, the runtime wakes it with a completion hook (§8.7). MCP over HTTP is optional, for Directors without shell access.
