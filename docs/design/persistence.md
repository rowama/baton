## 10. Persistence, Handoff and Deliverables

### 10.1 Checkpoint commits

After `step_passed` (with publishing), `human_decision`, `step_escalated`, `iteration_limit_reached`, `run_completed`, `run_abandoned` and `lease_released` (so a handoff travels through git), the runtime stages the run's directory and its published deliverables and commits with a structured message (`baton(<run_id>): <step_path> passed [attempt 1, claude-code-sub]`). One API call makes at most one checkpoint commit, its subject listing each trigger. Changed project-level records (`.baton/project/`, `.baton/platform/`, `.baton/process/`) are committed with it; a call that touches no run commits them on their own (`baton(project): …`, §12.2). On by default, to the current branch (`project.yaml` `checkpoints: { commit: true }`; §18 #6).
- Commit SHAs are read back from `git log` on resume, not written into the next event. This keeps commits self-contained. `checkpoint_committed` is appended just before the commit it belongs to (no SHA); if the commit then fails, the next checkpoint carries it.
- Workspace steps commit their own code; their `commit_sha` is in the step output, and the checkpoint commit follows.
- Never commit with unrelated uncommitted changes; refuse and report. The commit names its paths (`git commit --only`), so unstaged or untracked work elsewhere is never swept in; changes *staged* for other paths, a merge/rebase in progress or a missing git identity refuse the checkpoint, which is reported in the call's result and retried at the next trigger.
- Git LFS is optional (§18 #7): with `git lfs` installed, stored blobs at or above `lfs.threshold_mb` (default 5) are listed in the run's own `.gitattributes` before staging.
- Pushing follows action permissions (§13.7); checkpoint commits normally qualify as docs-only.

### 10.2 Leases

A lease is an event `lease_claimed {director_id, harness, host, branch, expires_at}`. Mutating calls on a run require its lease: a free or expired lease is claimed automatically, the holder's lease is renewed (`lease_renewed`) once half its term has passed, and an unexpired lease held by another Director (or by the same Director on another branch) refuses with exit code 3. The term is `project.yaml` `leases.minutes` (default 60; §18 #5). `take_over(reason)` records a takeover (`lease_taken_over`, with the previous holder and the reason); the director skill requires owner approval first, the runtime only requires the reason. The runtime releases the lease when a run completes or is abandoned. The Director identity is `--director` / `BATON_DIRECTOR` (default `<user>@<host>`); the harness name is `BATON_HARNESS`. Leases travel through git, so they coordinate *sequential* handoff. **A run lives on one branch at a time**: continuing it on another branch requires releasing it on the first. Divergent hash chains (two Directors on unsynced clones) are caught by `resume` and `check`, and need owner resolution.

### 10.3 Resume

1. Verify the hash chain and every CAS blob.
2. Rebuild the cache.
3. Reconcile live work with running markers (§8.7): still alive → left running; finished with a result → intake now; otherwise `orphaned`, classified (`platform` / `supervisor_died`) and escalated for an owner decision (`decide <step> retry`).
4. Check published deliverables for drift.
5. Claim the lease, or report the holder.
6. Return status.

A new machine needs only the pinned runtime and its own worker profiles: clone → `baton doctor` → `baton resume <run>`.

### 10.4 Publishing

Artifacts may declare `publish.to` using **logical** path keys mapped in `project.yaml`:

```yaml
paths: { specs: docs/specs, designs: docs/design, plans: docs/plans, drawings: cad/drawings }
project: { test_command: "pytest -q", preflight: "pytest -q --collect-only" }
run_slug: "{{ run.inputs.title | slugify }}"
```

Publishing is for artifacts a worker returns in `result/artifacts/` (documents, drawings, photos), plus one document the runtime renders itself: a framing run's process plan (§11.6), published as the `frame` step's `process_plan` under the same rules. **Workspace steps' output *is* the project tree** (code a coding agent writes and commits in place, recorded by `commit_sha`) and does not use `publish`.

Decision: [0038](../decisions/0038-publishing.md).
- **Start.** A `paths.*` key a recipe publishes to that `project.yaml` does not map refuses `start` (`configuration.publish_path`). Targets must stay inside the project and outside `.git` and `.baton`.
- **When.** After every `step_passed` of a step with publish artifacts, whatever the route (intake, an approved human gate, a waiver, a confirmed stale step), in the same call and before its checkpoint, so the commit includes the deliverable. Each one records `artifact_published {artifact, path, sha256, attempt, unchanged?}` on the step (`unchanged` when the file already held those bytes and was not rewritten). Imported steps (adoption seeds) are not published: their files already live where the prior process put them. `publish` inside a group is a load error (`publish.in_group`): its targets cannot vary per instance.
- **Conflicts.** Writing is silent only when the target is absent, already holds exactly the artifact's bytes, or was last published (across all runs) by this same run and step and still has the hash Baton wrote (a revised step replacing its own untouched version). Anything else is a conflict: a file Baton never wrote, one another run published, one edited since. The step stays `passed` (downstream steps read CAS, never the published copy), and a pending owner decision `publish:<step_path>.<artifact>` offers `overwrite`, `keep` (the existing file stays; recorded as `artifact_published {kept: true}` with no write) or `alternate` (written beside it as `<stem>.<run_id><suffix>`, or at `--path`, itself checked for conflicts). The run does not complete while a conflict is pending.

**Project documents** (Decisions: [0142](../decisions/0142-project-documents-bound-by-role.md), [0146](../decisions/0146-project-document-details.md)). A published deliverable is also a *project document*: a file one run can build on from another (§5.2, §8.6). It becomes one when its step is accepted and published, whether or not its run has completed. The owner can make any other file in the repo one by attesting it.
- **Identity and versions.** A project document is its path; a moved file is a new document. Its versions, oldest first by time, are every `artifact_published` at that path (not `kept`) in any run, every owner-ingested revision of it (`human_revision_ingested` with `source: drift`, §10.5), and every attestation of it. The latest is its accepted version. Code written by workspace steps is not a project document automatically; the owner may attest a file from the tree.
- **Attestation.** `attest(path, note)` (`baton attest <path> --note "<owner's words>"`) records `human_decision {kind: attest}` and `document_attested {path, sha256, note, decision_id}` in the project log, stores the bytes in the project CAS (`.baton/project/cas/`) and commits them as a project checkpoint. A path outside the project, inside `.git` or `.baton`, a missing file or a directory, and a missing note are refused. Attesting the same path again records a newer version. There is no withdrawal: a newer attestation supersedes an older one, and a deleted file is listed as deleted.
- **Listing.** `documents()` derives the list from every run's log and the project log, never from a hand-kept index: for each document its `path`, `kind` (`deliverable` or `attested`, from its latest version), `media_type` (the artifact's declared type, else the file's), `version` (how many there are), `accepted_sha256`, the living file's `sha256` and `state` (`unchanged`, `edited` or `deleted`), `accepted_at` and `source` (`{kind: deliverable, run, step, artifact}` or `{kind: attested, decision_id, note}`).

### 10.5 Two copies and drift

The CAS copy is the immutable record and is always what downstream steps consume. The published copy is the living file. A changed hash (or a deleted file) is drift.

Decision: [0039](../decisions/0039-drift.md).
- **Detection.** `status`, `detect` (situation `drift`) and `check` (a warning; an error under `--strict`) compute it without recording. Any mutating call on the run (including `resume`) records `drift_detected {artifact, path, published_sha256, current_sha256}` on the step once per new hash (`current_sha256: null` for a deleted file). Drift is tracked only while the run is active: once it completes, its published files belong to the project and editing them is normal.
- **Decision.** Drift is a pending owner decision `drift:<step_path>.<artifact>`. It blocks no step but holds run completion (nothing can be ingested after the run ends). The owner chooses:
  - **Leave it:** `decide <run> drift:<step_path>.<artifact> leave --note "<words>"`. Downstream keeps the CAS version; that hash is acknowledged and a later edit is new drift.
  - **Ingest it as a revision:** `ingest_revision(run, step_path, artifact, note, feed?)` (`baton ingest-revision <run> <step_path> <artifact> --note "<words>" [--feed dependents]`) records `human_decision {kind: drift, decision: ingest}` and `human_revision_ingested {artifact, path, sha256, revision, feed, possibly_stale, decision_id, source}`, with the file stored in CAS. A deleted file can only be left.
- **What it feeds.** `human_revision.<step>.<artifact>` resolves to the latest ingested revision; with none it is `not_applicable` (an unedited deliverable is normal, never a missing input). With `feed: dependents`, every dependent of that step that has not started (no attempt dispatched) also receives the latest revision for its `steps.<step>.artifacts.<name>` inputs, labeled as the owner's revision. Passed and imported dependents are flagged *possibly stale* in `status` and their records: a flag only, not the `stale` state; the owner may `revise`.
- **From an expert.** `promote_sme(…, target=revision, artifact=<step_path>.<name>, from?)` ingests an expert's artifact (`--from <name>`) or answer (`--text`) the same way (`source: sme`) and writes it to the published path, with the conflict rule above.

**Upstream change** (Decision: [0142](../decisions/0142-project-documents-bound-by-role.md)). A run keeps the version of a project document it bound (§8.6). When that document moves on (a later publication or attestation, or the living file edited or deleted), `status` (`upstream_changes` `[{run, role, path, change, bound_version, bound_sha256, current_version, current_accepted_sha256, current_sha256}]`, `change` being `newer_version`, `edited` or `deleted`), `board` and `check` (a warning, also under `--strict`: `document.upstream_changed`) say so for active runs. Like drift it is computed on demand and recorded nowhere, but unlike drift nothing follows from it: nothing becomes stale, no run is blocked or held from completing, and a completed run reports nothing. The owner may rebind (§8.9).

### 10.6 Records and explain

- **Step record** (`docs/<step_path>.md`): worker profile (name and non-secret hash), attempts, inputs with hashes (a project document's with its path, version, provenance and whether it was edited since accepted, §8.6), output, artifacts (CAS hash and published path), deliverables (publishes, kept files, drift, ingested revisions, possibly-stale flags), gates and findings, waivers, decisions.
- **Run summary** (`docs/SUMMARY.md`): work item, recipe and versions, timeline, per-step table, project documents (for a recipe that declares roles: each role and every binding of it, with its document, version, hash, provenance and the owner's words), escalations, leases.
- Both are derived, regenerable and committed.
- `explain(run)` returns **process facts only** (completed, imported and skipped steps; current position; pending decisions; remaining steps at this level and what other levels would add or drop; possible branches: owner gates, findings that send work back, iteration limits, a level not yet set). It never includes step outputs, artifacts or run inputs, so the Director can describe progress without loading subject matter. Structured data plus a `text` rendering (golden-tested).
