## 15. Cross-Platform and Security

### 15.1 Cross-platform

The runtime host may be Linux, macOS, native Windows or WSL.
- Paths are stored and compared in POSIX form; backslashes are accepted on input.
- Text is written as UTF-8 without BOM, with LF endings; a BOM is tolerated on read.
- Git runs with explicit settings (`-c core.autocrlf=false`), except the working-tree snapshot's `git status` (§6.3). Clones are made by other tools with their own settings (Git for Windows converts line endings by default), so `baton init` writes `.baton/.gitattributes` with `* -text`: hash-chained logs, CAS blobs and vendored recipes are checked out byte for byte everywhere, and `check` reports the rule missing.
- On Windows, harness CLIs are often npm `.cmd` shims run through `cmd.exe`, which ends an argument at a newline and expands `%VAR%`. Prompts passed on a command line are therefore one line with no `%`, `^`, `&`, `|`, `<` or `>` (the task prompt, the no-op prompt and doctor's preflight prompt, which puts its command between backticks) **[VERIFY with the real CLIs on Windows]**.
- Script gates and hooks run under the platform shell: `/bin/sh` on POSIX, `cmd.exe /d /s /c` on Windows. Recipe authors write gate commands for the shells their projects use.
- No shebang reliance: entry points come from the package (`baton`, `python -m baton`, `py -m baton`).
- Detaching, liveness, file locks and process-tree termination have POSIX and Windows code paths (Windows: a new process group with its own hidden console and job break-away, `OpenProcess`/`GetExitCodeProcess`, `msvcrt.locking`, `taskkill /T`), all tested on native Windows in CI (`.github/workflows/tests.yml`: Ubuntu and Windows, the lowest and newest supported Python). The "survives its caller" test closes a kill-on-close job object holding the caller, as Windows terminals and CI runners do. A supervisor is not started as a `DETACHED_PROCESS`: under a venv, `sys.executable` is a launcher, and the interpreter it starts would get a new, visible console window for the supervisor's whole life (change [2026-11-windows-supervisor-console](../changes/2026-11-windows-supervisor-console.md)).
- On Windows a file that another process has open cannot be replaced or deleted (`PermissionError`). The running marker (§8.7) is read by dispatch and reconciliation while its supervisor rewrites it, so the supervisor replaces and removes it with a short retry (about 2 s) instead of dying with the worker unsupervised (change [2026-11-windows-running-marker](../changes/2026-11-windows-running-marker.md)).
- Directories are `0700` on POSIX, with user-only ACLs on Windows where possible.
- In WSL, keep repos on the Linux filesystem.

### 15.2 Security

- **Vendored recipes are trusted code** (script gates run their commands). Review them before vendoring; `check` and `doctor` verify their hashes.
- Harness workers may have broad permissions; prefer `isolation: container` or a dedicated user for risky work.
- **Everything committed passes `redact.py`.** Raw logs stay in `~/.baton/logs/`. Secrets never enter the project tree, packets or SME packets. Tests prove this with sentinel secrets across the working tree and git history.
- Hooks and `command` adapters run shell commands. Only machine-level configuration may reference secrets; the loader rejects `secret:` in `project.yaml`.
- Action permissions bound what the runtime and Director do to the repo and its remotes. The defaults never merge, deploy or force-push.
- **Diagnostics** (§8.3; Decision: [0094](../decisions/0094-diagnostics-channel.md)) stay in `~/.baton/diag/`, never in the project, and every string in a record passes `redact_text` before it is written, so a record can be handed to an SME as it is.
- An SME (especially a platform SME) may hold its own credentials outside Baton. Baton gives it facts, incidents and redacted logs, never secrets.
- **Harness sandboxes.** A Director's harness may sandbox the commands it runs (Codex's `workspace-write`: writes only in the project, usually no network), and everything those commands start inherits it, supervisors and workers included. Baton never weakens a harness sandbox: a sandboxed shell gets `director_sandboxed` from `detect`/`doctor` (§13.4), and the harness directs Baton through MCP instead, whose server runs outside the sandbox while the harness's own commands stay confined (§13.2; Decision: [0053](../decisions/0053-codex-director-via-mcp.md)). Turning the sandbox off is the owner's choice, offered but never recommended.


### 15.3 Future: guided process authoring (design implications now)

A planned future use: an agent interviews the owner, finds gaps, and writes a new recipe; process diagrams help the owner review it. This needs no work now, but three implementation choices keep it cheap later:
1. **Define the recipe format by models that emit a JSON Schema** (e.g. pydantic `model_json_schema()`), and publish it with each format version (`baton-recipe/N`), rather than encoding the rules only in loader code. Any agent can then author and pre-check recipes. Cross-reference rules the schema cannot express stay in the loader, with precise error messages.
2. **Make `baton plan` build a structured plan object first, then render it.** Text output today; diagram output (e.g. Mermaid, per complexity level) later becomes a renderer, not a redesign.
3. **Keep the fake adapter general enough to drive whole runs** (scripted outcomes per step, findings, timeouts). A future `baton simulate` (a dry run of any recipe through its branches, loops and levels) then reuses it.
