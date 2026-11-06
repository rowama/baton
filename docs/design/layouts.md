## 4. Layouts

### 4.1 Runtime repository (installed as a pinned tool)

```
baton/
├── pyproject.toml   README.md
├── src/baton/
│   ├── models.py            # pydantic models for everything below
│   ├── data.py              # shipped data lookup; strict YAML (duplicate keys rejected)
│   ├── refs.py              # input-reference grammar (§5.2) parser
│   ├── recipe.py            # load, validate, neutrality lint, per-level plan, group validation
│   ├── vocab.py             # capability vocabulary
│   ├── profiles.py          # worker profiles, secrets, env construction, PATH resolution
│   ├── routing.py           # eligibility, preferences, independence
│   ├── known_workers.py     # known-workers data: schema and validation (§6.4)
│   ├── store.py             # event logs (run + project), CAS, SQLite cache rebuild
│   ├── state.py             # the one state machine
│   ├── groups.py            # foreach / repeat_until expansion and aggregate state
│   ├── packet.py            # packet builder (the critical module)
│   ├── intake.py            # result validation, gates, findings
│   ├── reviews.py           # review steps, findings lines and statuses, evidence, waivers, protected files
│   ├── supervisor.py        # detached per-dispatch supervisor, markers, deadlines, hooks
│   ├── classify.py          # failure classification rules (data-driven)
│   ├── project.py           # project root, project.yaml, lockfile access, vendoring, profile loading
│   ├── locks.py             # run leases, workspace lock, project lock
│   ├── publish.py           # deliverables + drift
│   ├── adopt.py             # detect, research/seed/baseline helpers
│   ├── frame.py             # framing (§11.6): recipe listing, the select gate, selection and run creation
│   ├── labels.py            # plain-language labels for decision options (§13.8)
│   ├── sme.py               # expert consultation; platform facts/incidents; process feedback
│   ├── permissions.py       # action permissions
│   ├── gitops.py            # checkpoint commits, pushes
│   ├── redact.py            # secret redaction for anything committed
│   ├── docs.py              # step records, run summaries, explain
│   ├── versions.py          # lockfile, format families and windows, migrations, upgrade
│   ├── launcher.py          # the `baton` command: runs the version baton.lock pins (§14.1)
│   ├── engine.py            # the API (§13.1) used by CLI and MCP
│   ├── worker_runner.py     # child-process entrypoint for API workers
│   ├── adapters/            # base, litellm_api, subprocess_harness, claude_code, codex, command, manual
│   ├── cli.py   mcp_server.py   check.py   doctor.py
├── vocab/baton-capabilities-1.yaml
├── formats/baton-recipe-1.schema.json   formats/baton-findings-1.schema.json   formats/baton-crosswalk-1.schema.json   # generated from models (§15.3)
├── classify/rules-1.yaml    # failure signal patterns
├── builtin/baton-adopt/     # the built-in adoption recipe (§11.1): research step, baton-research/1 schema
├── builtin/baton-frame/     # the built-in framing recipe (§11.6): frame step, baton-frame/1 schema
├── skills/baton-director/SKILL.md   skills/baton-worker/SKILL.md
├── defaults/communication.md        # default owner communication contract, conversational (written by `baton init`)
├── defaults/communication-operator.md   # the terse operator style, for owners who choose it (§13.6)
├── defaults/labels.yaml     # plain-language labels for decision options (§13.8)
├── defaults/known-workers.yaml   # shared, read-only data about models and routes (§6.4)
├── examples/recipes/fit-check/   examples/recipes/software-feature/   examples/recipes/backyard-project/   # the catalog: shipped in the package (§11.6)
├── tools/worker-research/   # maintainers only, never shipped: research.py and its one-step recipe propose known-workers updates (§6.4)
└── tests/
```

### 4.2 Recipe package (shareable, model-neutral)

```
<recipe>/
├── recipe.yaml       # id, version, format version, steps (§5)
├── schemas/*.json    prompts/*.md    templates/*.md.j2    static/…
└── crosswalks/*.yaml # optional, for adopting projects from a known prior process (§11.3)
```

### 4.3 Project (what lives in the adopting repo)

```
<project>/
├── AGENTS.md                         # one-line pointer: "This repo uses Baton; see .agents/skills/baton-director"
├── .agents/skills/baton-director/  .agents/skills/baton-worker/   # vendored by baton init/upgrade (init also writes the AGENTS.md pointer; under adoption the baseline proposes it)
├── .baton/
│   ├── baton.lock                    # runtime version, format versions, vocab version, recipe hashes, step-id signatures (§5.8)
│   ├── project.yaml                  # paths, project vars, permissions, hooks (non-secret), limits, contacts, sme, effort bands
│   ├── communication.md              # owner communication contract (starts as the default)
│   ├── preferences.yaml              # optional routing preferences (non-secret)
│   ├── recipes/<id>@<version>/       # vendored, pinned recipes
│   ├── project/events.jsonl          # project-level events (platform incidents, facts, process feedback)
│   ├── project/sme/<c_id>/  project/cas/   # consultations without a run (§12.1), and their blobs
│   ├── adoption/<run_id>/baseline.yaml  # baseline proposal of an adoption (§11.5)
│   ├── platform/facts.md             # platform facts
│   ├── process/lessons.md            # project-level process lessons
│   ├── process/proposals/            # promoted process proposals (§12.2)
│   ├── runs/<run_id>/                # events.jsonl, cas/, steps/, sme/<c_id>/turn-<n>/ and handoff.md, docs/
│   ├── .gitattributes                # `* -text`: git never converts line endings in hashed files (§15.1)
│   ├── workers.local.yaml            # GITIGNORED: project-specific profile overrides
│   └── cache/                        # GITIGNORED: SQLite, running markers, locks
├── <published deliverables at the project's own paths>   # incl. framing's process plans (paths.process_plans) and the owner's notes file (paths.notes); init maps both to docs (§11.6, §13.1)
└── .gitattributes                    # LFS rules for large blobs and binary deliverables
```

**Principle: commit what the process *is* and what it has *produced*; never commit who runs it or how they pay.**

| Item | Commit? |
|---|---|
| Recipes, lockfile, skills, AGENTS.md pointer, MCP project config (if used) | ✅ |
| `project.yaml`, `communication.md`, `preferences.yaml` | ✅ |
| `.baton/runs/`, `.baton/project/`, `.baton/platform/`, `.baton/process/` | ✅ (redacted) |
| Published deliverables | ✅ |
| Runtime source | ❌ installed and pinned (§14) |
| Worker profiles, secrets, machine-level hooks, raw logs, cache, running markers | ❌ |

### 4.4 Machine-local (never in any repo)

```
~/.baton/
├── workers.yaml      # worker profiles
├── hooks.yaml        # machine-level completion hooks; may reference secrets
├── secrets/          # optional file-based secret store (0700)
├── homes/<profile>/  # optional relocated CLI config homes [VERIFY per CLI]
├── mcp.yaml          # `token: secret:<name>`: the bearer token for `baton mcp --http` (§13.2)
├── launcher.yaml     # optional: where the launcher installs runtime versions from (`source`, `extras`, `python`; §14.1)
├── versions/         # installed runtime versions used by the launcher (§14.1)
└── logs/             # unredacted raw worker output
```
