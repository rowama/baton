## 14. Versioning and Trying New Versions

### 14.1 What is versioned

| Thing | Version recorded in | Pinned by |
|---|---|---|
| Runtime | `baton.lock` (`runtime`) | project |
| Packet protocol (`baton-packet/N`) | manifests, results | run |
| Event schema (`baton-events/N`) | `run_started`, project log | run |
| Recipe format (`baton-recipe/N`) and recipe version | `recipe.yaml`, lockfile, `run_started` | project; run |
| Capability vocabulary (`baton-capabilities/N`) | recipe, lockfile | project |
| Skills | vendored with the runtime version | project |

**Launcher.** The `baton` command installed on a machine is a thin launcher. It reads `baton.lock` in the current repo and runs that exact runtime version, installing it into `~/.baton/versions/` on first use (via `uv`). `BATON_VERSION` overrides it for one invocation. Different projects, branches and worktrees on one machine can therefore use different Baton versions without conflict.

Decision: [0051](../decisions/0051-launcher-mechanics.md) (with §18 #15).
- **The launcher is the package's own entry point** (`baton.launcher:main`, also `python -m baton`). Before anything else it finds the project (`--project`, `BATON_PROJECT`, or the nearest `.baton/project.yaml`), reads `runtime` from `baton.lock` and, when that is the running version (the healthy case), runs in-process. Otherwise it re-runs the same command line under `~/.baton/versions/<v>/` (that version's own Python, `-m baton`). Which version: `BATON_VERSION` if set; `upgrade --to <v>` runs under `<v>` (so the new runtime vendors its own skills), `upgrade` alone under the launcher's own version; `init`, or no project, the launcher's own version; otherwise the lockfile's.
- **Installing** a missing version uses uv (checked against uv 0.13.7): `uv venv <dir>`, then `uv pip install --python <dir's python> "baton[<extras>] @ <source>"`. `~/.baton/launcher.yaml` (optional, machine-local) sets `source` (a URL template with `{version}`; default `git+https://github.com/rowama/baton@v{version}`, so releases are tagged `v<version>`), `extras` (e.g. `[mcp, api]`) and `python` (for `uv venv`); `BATON_UV` names the uv executable. Without uv the launcher refuses, naming uv's install page and the directory a version may be installed into by hand. A version directory counts as installed once it holds `.baton-installed` (written after the installed runtime reports the expected version); installs are serialized by a file lock.
- **No loops.** The re-run process gets `BATON_LAUNCHED=<v>`, refuses if it is not that version, and removes the variable, so hooks and gates it starts launch afresh.
- Worktrees have their own `.baton/cache/`, so two worktrees of one project run two versions side by side.

### 14.2 Compatibility and migration

- A runtime reads all older format versions it declares as supported, and continues runs started under them.
- A run keeps its recipe version and hash for its whole life. Upgrading a recipe mid-run requires an owner decision and is recorded.
- Vendoring or upgrading a recipe compares its step-id signatures with every version recorded in the lockfile; changed or reused ids need an owner decision (§5.8).
- When a format cannot be read, the runtime refuses and names `baton migrate`. Migration is explicit, previewable (`--dry-run`), recorded (`migrated`), committed separately, and never rewrites earlier events: it appends a migration record and writes new-format files alongside.

Decision: [0052](../decisions/0052-format-window-migrate-upgrade.md).
- **Format families and the readable window** (§18 #15). The stored formats a project keeps are families: event logs (`baton-events/N`, per event), the lockfile (`baton-lock/N`) and vendored recipes (`baton-recipe/N`). Each has a current version and a chain of upcasters (`N → N+1`) kept from version 1 forever. A runtime reads the **current and previous** version directly, upcasting in memory; its new events are written in the current format, so one log may hold two versions. An older version is refused with `format.needs_migration` (`events.needs_migration`, `lock.needs_migration` in `check`), naming `baton migrate`; a version newer than the runtime is refused (`format.too_new`; `*.unknown_format` in `check`), naming the launcher. The packet protocol is per attempt and not migrated (in-flight attempts are finished first).
- **`migrate`** (`baton migrate [--dry-run]`): `--dry-run` reports every file below the window and writes nothing. Otherwise (refused while workers are running, or when something is too new to migrate): an event log gets an upcast copy of all its events so far alongside (`events.migrated-<seq>.jsonl`, each event keeping its `seq` and `sha256`) and a `migrated` record appended to it; readers verify the hash chain on the original lines (it does not depend on the format) and interpret earlier events from the copy named by the latest `migrated` record, whose hash it must match. A vendored recipe gets `.baton/recipes/<ref>.migrated.json` (the upcast recipe plus the hash of the `recipe.yaml` it came from), outside the package hash, so runs keep their pinned hash. The lockfile is rewritten in the current format with the current formats. Each is recorded as `migrated`; one commit holds exactly the migration (`baton(migrate): …`).
- **`upgrade`** (`baton upgrade [--to <v>]`) runs under the target version (the launcher sees to it; `--to` naming another version is refused, `upgrade.wrong_runtime`). It refuses when the project holds a format the target cannot read or migrate (`upgrade.unreadable`, e.g. a downgrade too far), then sets `runtime` and `formats` in the lockfile and re-vendors both skills (replacing edited copies, listed in the result). Nothing else changes, in one commit (`baton(project): upgrade runtime <a> -> <b>`). Files that now need migration are reported with the hint.
- **Step-id signatures** (§5.8). Vendoring compares the new version's per-step signatures with every recorded version of that recipe: `signature_changed` (a kept id whose kind, enclosing group, output schema hash or required capabilities differ) and `retired_id_reused` (an id an earlier version had, absent from every recorded version since, back again). Either returns `needs_owner` (exit 4) with the flags and vendors nothing; repeating with `--approved --note "<owner's words>"` records `human_decision {kind: vendor, …}` in the project log and keeps `decision {decision_id, note, flags}` in the lockfile entry. As with `push`, the runtime requires the words and the director skill the actual approval.
- **Worker identity** (Decision: [0075](../decisions/0075-model-identity-separate-from-route.md)). Profiles gained `creator`, `model_id`, `provider` and `resource` (§6.1), and `worker_selected` and `sme_requested` record them; the fields are additive, so no format version changed. A profile's `vendor` is read as `creator`. `worker_selected` also gained `excluded` (`[{profile, reasons}]`), additive in the same way: an older event is read as `excluded` unknown. An older event is read as `creator` = its `vendor`, model identity unknown; no migration guesses an identity, and one would need evidence for each record.
- **Recipe upgrade mid-run** is deferred: a run keeps its recipe version and hash for its whole life (`run.recipe_mismatch`); new work items use the new version.

### 14.3 Trying a new version on a real project

1. `git worktree add ../<project>-trial -b baton-trial`
2. In the trial worktree: `baton upgrade --to <version>`. This updates the lockfile and re-vendors skills, with no other changes.
3. Run real work there: new work items, or existing runs moved to the branch (release the lease on main first; a run lives on one branch at a time).
4. **Adopt:** merge the branch. New runs merge cleanly because each run has its own directory. **Abandon:** delete the branch and worktree; nothing leaks except machine-local logs.

Recipes are trialed the same way: vendor a new recipe version on a branch, start new work items with it, then merge or discard.
